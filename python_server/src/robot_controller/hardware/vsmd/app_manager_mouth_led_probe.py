"""Explicit, bounded live diagnostic for one Sota mouth-LED control sequence.

Importing this module performs no I/O. Both live endpoints are constructed
only after the command line includes ``--confirm-live-write``.
Success covers protocol, memory operations, cleanup, release, and postflight;
the CLI cannot verify physical illumination.
"""

import argparse
import collections
import math
import sys
import time
import typing

from robot_controller.hardware.vsmd.app_manager_codec import (
    APP_MANAGER_RESPONSE_OK,
)
from robot_controller.hardware.vsmd.app_manager_lock import (
    AppManagerLedLock,
    LEASE_RELEASED,
    LEASE_RELEASE_FAILED,
    LEASE_RELEASE_OUTCOME_UNKNOWN,
    validate_timer_address,
)
from robot_controller.hardware.vsmd.app_manager_transport import (
    AppManagerTcpTransport,
    DEFAULT_APP_MANAGER_HOST,
    DEFAULT_APP_MANAGER_PORT,
    DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.app_manager_vsmd_lock import (
    AppManagerVsmdLedLock,
    AppManagerVsmdLedLockLease,
    AppManagerLeaseInterpolationTimer,
)
from robot_controller.hardware.vsmd.constants import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_HOST,
    DEFAULT_MAX_LINE_LENGTH,
    DEFAULT_PORT,
    DEFAULT_READ_TIMEOUT_SECONDS,
    DEFAULT_WRITE_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.errors import (
    VsmdMouthLedCleanupError,
    VsmdMouthLedStateError,
    VsmdValidationError,
)
from robot_controller.hardware.vsmd.interpolation_timing import (
    milliseconds_to_control_ticks,
)
from robot_controller.hardware.vsmd.memory import VsmdMemoryClient
from robot_controller.hardware.vsmd.mouth_led import (
    SotaMouthLedController,
    VsmdLedLock,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    MASTER_CONTROL_PERIOD_ADDRESS,
    MOUTH_LED_AUDIO_SOURCE_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_GLOBAL_LED_ID,
    SOTA_MOUTH_OUTPUT_ADDRESS,
    SOTA_MOUTH_REMAINING_TIME_ADDRESS,
    SOTA_MOUTH_TARGET_ADDRESS,
    SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
)
from robot_controller.hardware.vsmd.transport import VsmdTcpTransport
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


MIN_LIVE_LEVEL = 1
MAX_LIVE_LEVEL = 16
MIN_LIVE_DURATION_MS = 50
MAX_LIVE_DURATION_MS = 200
MIN_LIVE_HOLD_MS = 100
MAX_LIVE_HOLD_MS = 1000
DEFAULT_LIVE_HOLD_MS = 500
PROBE_LOCAL_LOCK_KEY = "app-manager-mouth-led-live-probe"
MAX_ACTIVE_STATE_RECHECKS = 3
MIN_ACTIVE_COMPLETION_GRACE_SECONDS = 0.05
MAX_ACTIVE_COMPLETION_GRACE_SECONDS = 0.5
MAX_ACTIVE_POLL_INTERVAL_SECONDS = 0.05


_ProbeSnapshotBase = collections.namedtuple(
    "_ProbeSnapshotBase",
    ["selector", "target", "output", "trigger_pointer"],
)


class ProbeSnapshot(_ProbeSnapshotBase):
    """Immutable mouth-LED state read from confirmed VSMD addresses."""

    __slots__ = ()


_ActiveInterpolationStateBase = collections.namedtuple(
    "_ActiveInterpolationStateBase",
    [
        "output",
        "remaining_time",
        "trigger_pointer",
        "timer_value",
        "snapshot_read_duration_ms",
        "poll_attempt",
    ],
)


class ActiveInterpolationState(_ActiveInterpolationStateBase):
    """Immutable, complete interpolation snapshot from four VSMD reads."""

    __slots__ = ()


_ProbeResultBase = collections.namedtuple(
    "_ProbeResultBase",
    [
        "preflight",
        "locked_trigger_pointer",
        "timer_address",
        "master_control_period_us",
        "timer_ticks",
        "active_state",
        "interpolation_reached_target",
        "active_snapshots",
        "hold_duration_ms",
        "hold_completed",
        "off_state",
        "off_snapshots",
        "fade_down_completed",
        "interpolation_output_safe_zero",
        "postflight",
        "pulse_completed",
        "cleanup_completed",
    ],
)


class ProbeResult(_ProbeResultBase):
    """Successful result after release and postflight validation."""

    __slots__ = ()


class _SingleLeaseHandoffLock(VsmdLedLock):
    """Hand one already-validated lease to the existing controller once."""

    def __init__(self, local_key, lease):
        # type: (str, AppManagerVsmdLedLockLease) -> None
        self._local_key = local_key
        self._lease = lease
        self._handed_off = False

    @property
    def was_handed_off(self):
        # type: () -> bool
        return self._handed_off

    def acquire(self, key, led_ids):
        # type: (str, typing.Sequence[int]) -> AppManagerVsmdLedLockLease
        if self._handed_off:
            raise VsmdMouthLedStateError(
                "live probe lease was already handed to the controller"
            )
        if key != self._local_key or tuple(led_ids) != self._lease.led_ids:
            raise VsmdMouthLedStateError(
                "controller requested a different live probe lease"
            )
        self._handed_off = True
        return self._lease

    def release(self, key, led_ids):
        # type: (str, typing.Sequence[int]) -> None
        raise VsmdMouthLedStateError(
            "live probe lease must be released by its owned lease"
        )


class AppManagerMouthLedLiveProbe(object):
    """Run exactly one preflight-guarded pulse through the real controller."""

    def __init__(
        self,
        memory,
        led_lock,
        level,
        duration_ms,
        hold_ms=DEFAULT_LIVE_HOLD_MS,
        sleep_function=time.sleep,
        monotonic_function=time.monotonic,
        controller_factory=SotaMouthLedController,
    ):
        # type: (VsmdTypedMemory, AppManagerVsmdLedLock, int, int, int, typing.Any, typing.Any, typing.Any) -> None
        if not isinstance(memory, VsmdTypedMemory):
            raise TypeError("memory must be VsmdTypedMemory")
        if not isinstance(led_lock, AppManagerVsmdLedLock):
            raise TypeError("led_lock must be AppManagerVsmdLedLock")
        _validate_live_level(level)
        _validate_live_duration(duration_ms)
        _validate_live_hold(hold_ms)
        if not callable(sleep_function):
            raise TypeError("sleep_function must be callable")
        if not callable(monotonic_function):
            raise TypeError("monotonic_function must be callable")
        if not callable(controller_factory):
            raise TypeError("controller_factory must be callable")
        self._memory = memory
        self._led_lock = led_lock
        self._level = level
        self._duration_ms = duration_ms
        self._hold_ms = hold_ms
        self._sleep_function = sleep_function
        self._monotonic_function = monotonic_function
        self._controller_factory = controller_factory
        self._has_run = False
        self.preflight = None  # type: typing.Optional[ProbeSnapshot]
        self.postflight = None  # type: typing.Optional[ProbeSnapshot]
        self.locked_trigger_pointer = None  # type: typing.Optional[int]
        self.master_control_period_us = None  # type: typing.Optional[int]
        self.timer_ticks = None  # type: typing.Optional[int]
        self.active_state = None  # type: typing.Optional[ActiveInterpolationState]
        self.active_snapshots = []  # type: typing.List[ActiveInterpolationState]
        self.interpolation_reached_target = False
        self.hold_completed = False
        self.off_state = None  # type: typing.Optional[ActiveInterpolationState]
        self.off_snapshots = []  # type: typing.List[ActiveInterpolationState]
        self.fade_down_completed = False
        self.interpolation_output_safe_zero = False
        self.routing_state_restored = False
        self.lease = None  # type: typing.Optional[AppManagerVsmdLedLockLease]
        self.pulse_completed = False
        self.cleanup_completed = False

    def run(self, preflight_callback=None):
        # type: (typing.Optional[typing.Callable[[int, int], None]]) -> ProbeResult
        """Execute one pulse without retrying any lock or release operation."""
        if preflight_callback is not None and not callable(
            preflight_callback
        ):
            raise TypeError("preflight_callback must be callable")
        if self._has_run:
            raise VsmdMouthLedStateError(
                "live probe instances may run only once"
            )
        self._has_run = True
        self.preflight = self._read_snapshot()
        self._validate_preflight(self.preflight)
        self.master_control_period_us = self._memory.read_u32(
            MASTER_CONTROL_PERIOD_ADDRESS
        )
        self.timer_ticks = milliseconds_to_control_ticks(
            self._duration_ms, self.master_control_period_us
        )
        if preflight_callback is not None:
            preflight_callback(
                self.master_control_period_us, self.timer_ticks
            )

        self.lease = self._led_lock.acquire(
            PROBE_LOCAL_LOCK_KEY, (SOTA_MOUTH_GLOBAL_LED_ID,)
        )
        try:
            timer_address = validate_timer_address(
                self.lease.timer_address
            )
            self.locked_trigger_pointer = self._memory.read_u16(
                SOTA_MOUTH_TRIGGER_POINTER_ADDRESS
            )
            if self.locked_trigger_pointer != timer_address:
                raise VsmdMouthLedStateError(
                    (
                        "locked TriggerPointer 0x{0:04x} does not match "
                        "lease timer 0x{1:04x}"
                    ).format(self.locked_trigger_pointer, timer_address)
                )
        except BaseException as preparation_error:
            self._release_after_preparation_failure(preparation_error)

        handoff_lock = _SingleLeaseHandoffLock(
            PROBE_LOCAL_LOCK_KEY, self.lease
        )
        try:
            timer = AppManagerLeaseInterpolationTimer(
                self._memory,
                self._led_lock,
                master_control_period_us=self.master_control_period_us,
            )
            controller = self._controller_factory(
                self._memory,
                timer,
                led_lock=handoff_lock,
                lock_key=PROBE_LOCAL_LOCK_KEY,
            )
        except BaseException as preparation_error:
            self._release_after_preparation_failure(preparation_error)
        operation_error = None  # type: typing.Optional[BaseException]
        try:
            controller.disable_voice_sync()
            controller.set_brightness(self._level, self._duration_ms)
            self._sleep_function(self._duration_ms / 1000.0)
            (
                self.active_state,
                self.active_snapshots,
            ) = self._wait_for_interpolation(
                timer_address,
                self._level,
                "rise",
            )
            self.interpolation_reached_target = True
            self._sleep_function(self._hold_ms / 1000.0)
            self.hold_completed = True
            controller.turn_off(self._duration_ms)
            self._sleep_function(self._duration_ms / 1000.0)
            try:
                self.off_state, self.off_snapshots = (
                    self._wait_for_interpolation(
                        timer_address,
                        0,
                        "fade-down",
                    )
                )
            finally:
                if self.off_state is not None:
                    self.interpolation_output_safe_zero = (
                        self.off_state.output == 0
                    )
            self.fade_down_completed = True
            self.pulse_completed = True
        except BaseException as error:
            operation_error = error

        cleanup_error = None  # type: typing.Optional[BaseException]
        try:
            controller.close()
            self.cleanup_completed = True
        except BaseException as error:
            cleanup_error = error

        if not handoff_lock.was_handed_off:
            try:
                self.lease.release()
                _validate_release_success(self.lease)
            except BaseException as error:
                if cleanup_error is None:
                    cleanup_error = error

        if operation_error is not None and cleanup_error is not None:
            raise VsmdMouthLedCleanupError(
                operation_error, cleanup_error
            ) from cleanup_error
        if cleanup_error is not None:
            raise cleanup_error

        _validate_release_success(self.lease)

        # Failed/unknown release exits above. Do not perform extra reads in
        # that state: the server stack may still own the LED and success is
        # already impossible. The probe never attempts recovery or retry.
        postflight_error = None  # type: typing.Optional[BaseException]
        try:
            self.postflight = self._read_snapshot()
            self._validate_postflight(self.preflight, self.postflight)
            self.routing_state_restored = True
        except BaseException as error:
            postflight_error = error
        if operation_error is not None and postflight_error is not None:
            raise VsmdMouthLedCleanupError(
                operation_error, postflight_error
            ) from postflight_error
        if postflight_error is not None:
            raise postflight_error
        if operation_error is not None:
            raise operation_error
        return ProbeResult(
            self.preflight,
            self.locked_trigger_pointer,
            timer_address,
            self.master_control_period_us,
            self.timer_ticks,
            self.active_state,
            self.interpolation_reached_target,
            tuple(self.active_snapshots),
            self._hold_ms,
            self.hold_completed,
            self.off_state,
            tuple(self.off_snapshots),
            self.fade_down_completed,
            self.interpolation_output_safe_zero,
            self.postflight,
            self.pulse_completed,
            self.cleanup_completed,
        )

    def _read_snapshot(self):
        # type: () -> ProbeSnapshot
        return ProbeSnapshot(
            self._memory.read_u16(MOUTH_LED_SELECTOR_ADDRESS),
            self._memory.read_s16(SOTA_MOUTH_TARGET_ADDRESS),
            self._memory.read_s16(SOTA_MOUTH_OUTPUT_ADDRESS),
            self._memory.read_u16(SOTA_MOUTH_TRIGGER_POINTER_ADDRESS),
        )

    def _read_active_state(self, timer_address, poll_attempt):
        # type: (int, int) -> ActiveInterpolationState
        started_at = self._monotonic_function()
        output = self._memory.read_s16(SOTA_MOUTH_OUTPUT_ADDRESS)
        remaining_time = self._memory.read_u16(
            SOTA_MOUTH_REMAINING_TIME_ADDRESS
        )
        trigger_pointer = self._memory.read_u16(
            SOTA_MOUTH_TRIGGER_POINTER_ADDRESS
        )
        timer_value = self._memory.read_u16(timer_address)
        finished_at = self._monotonic_function()
        return ActiveInterpolationState(
            output,
            remaining_time,
            trigger_pointer,
            timer_value,
            max(0.0, (finished_at - started_at) * 1000.0),
            poll_attempt,
        )

    def _wait_for_interpolation(
        self, timer_address, expected_output, phase_name
    ):
        # type: (int, int, str) -> typing.Tuple[ActiveInterpolationState, typing.List[ActiveInterpolationState]]
        """Read complete snapshots and bound whether another poll may start."""
        period_seconds = self.master_control_period_us / 1000000.0
        grace_seconds = min(
            MAX_ACTIVE_COMPLETION_GRACE_SECONDS,
            max(
                MIN_ACTIVE_COMPLETION_GRACE_SECONDS,
                (self.timer_ticks + 2) * period_seconds,
            ),
        )
        poll_interval = min(
            MAX_ACTIVE_POLL_INTERVAL_SECONDS,
            max(period_seconds, 0.001),
        )
        deadline = self._monotonic_function() + grace_seconds
        poll_attempt = 0
        snapshots = []  # type: typing.List[ActiveInterpolationState]
        while True:
            state = self._read_active_state(timer_address, poll_attempt)
            snapshots.append(state)
            if phase_name == "rise":
                self.active_state = state
                self.active_snapshots = list(snapshots)
            else:
                self.off_state = state
                self.off_snapshots = list(snapshots)
                self.interpolation_output_safe_zero = state.output == 0
            if (
                state.output == expected_output
                and state.remaining_time == 0
                and state.trigger_pointer == timer_address
            ):
                return state, snapshots
            if state.trigger_pointer != timer_address:
                raise VsmdMouthLedStateError(
                    "{0} TriggerPointer did not match the lease timer".format(
                        phase_name
                    )
                )
            if state.remaining_time == 0:
                raise VsmdMouthLedStateError(
                    (
                        "{0} interpolation ended before reaching "
                        "output {1}"
                    ).format(phase_name, expected_output)
                )
            now = self._monotonic_function()
            if (
                poll_attempt >= MAX_ACTIVE_STATE_RECHECKS
                or now >= deadline
            ):
                raise VsmdMouthLedStateError(
                    "{0} interpolation completion deadline exceeded".format(
                        phase_name
                    )
                )
            remaining = deadline - now
            self._sleep_function(min(poll_interval, remaining))
            poll_attempt += 1

    @staticmethod
    def _validate_preflight(snapshot):
        # type: (ProbeSnapshot) -> None
        if snapshot.selector != MOUTH_LED_AUDIO_SOURCE_ADDRESS:
            raise VsmdMouthLedStateError(
                "preflight selector must be AudioDiff address 0x008a"
            )
        if snapshot.target != 0:
            raise VsmdMouthLedStateError(
                "preflight mouth target must be zero"
            )

    @staticmethod
    def _validate_postflight(preflight, postflight):
        # type: (ProbeSnapshot, ProbeSnapshot) -> None
        if postflight.selector != preflight.selector:
            raise VsmdMouthLedStateError(
                "postflight selector was not restored"
            )
        if postflight.target != 0:
            raise VsmdMouthLedStateError(
                "postflight mouth target is not zero"
            )
        if postflight.trigger_pointer != preflight.trigger_pointer:
            raise VsmdMouthLedStateError(
                "postflight TriggerPointer was not restored"
            )

    def _release_after_preparation_failure(self, operation_error):
        # type: (BaseException) -> typing.NoReturn
        try:
            self.lease.release()
            _validate_release_success(self.lease)
        except BaseException as cleanup_error:
            raise VsmdMouthLedCleanupError(
                operation_error, cleanup_error
            ) from cleanup_error
        raise operation_error


def _validate_release_success(lease):
    # type: (AppManagerVsmdLedLockLease) -> None
    """Require all independent release-success indicators to agree."""
    if (
        lease.state != LEASE_RELEASED
        or lease.is_released is not True
        or lease.release_result != APP_MANAGER_RESPONSE_OK
    ):
        raise VsmdMouthLedStateError(
            (
                "lease release was not explicitly successful: "
                "state={0!r} is_released={1!r} result={2!r}"
            ).format(
                lease.state,
                lease.is_released,
                lease.release_result,
            )
        )


def _validate_live_level(value):
    # type: (int) -> None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < MIN_LIVE_LEVEL
        or value > MAX_LIVE_LEVEL
    ):
        raise VsmdValidationError("level must be between 1 and 16")


def _validate_live_duration(value):
    # type: (int) -> None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < MIN_LIVE_DURATION_MS
        or value > MAX_LIVE_DURATION_MS
    ):
        raise VsmdValidationError(
            "duration-ms must be between 50 and 200"
        )


def _validate_live_hold(value):
    # type: (int) -> None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < MIN_LIVE_HOLD_MS
        or value > MAX_LIVE_HOLD_MS
    ):
        raise VsmdValidationError(
            "hold-ms must be between 100 and 1000"
        )


def _bounded_integer(name, minimum, maximum):
    # type: (str, int, int) -> typing.Callable[[str], int]
    def convert(text):
        # type: (str) -> int
        try:
            value = int(text, 10)
        except ValueError:
            raise argparse.ArgumentTypeError(
                "{0} must be an integer".format(name)
            )
        if value < minimum or value > maximum:
            raise argparse.ArgumentTypeError(
                "{0} must be between {1} and {2}".format(
                    name, minimum, maximum
                )
            )
        return value

    return convert


def _positive_float(text):
    # type: (str) -> float
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a number")
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(
            "timeout must be a positive finite number"
        )
    return value


def create_argument_parser():
    # type: () -> argparse.ArgumentParser
    """Build the explicit opt-in live-write CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Run one bounded Sota mouth-LED control sequence. No endpoint "
            "is opened unless --confirm-live-write is present. Success does "
            "not verify physical illumination."
        )
    )
    port = _bounded_integer("port", 1, 65535)
    parser.add_argument(
        "--app-manager-host", default=DEFAULT_APP_MANAGER_HOST
    )
    parser.add_argument(
        "--app-manager-port", type=port, default=DEFAULT_APP_MANAGER_PORT
    )
    parser.add_argument(
        "--app-manager-timeout",
        type=_positive_float,
        default=DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
    )
    parser.add_argument("--vsmd-host", default=DEFAULT_HOST)
    parser.add_argument("--vsmd-port", type=port, default=DEFAULT_PORT)
    parser.add_argument(
        "--vsmd-connect-timeout",
        type=_positive_float,
        default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--vsmd-read-timeout",
        type=_positive_float,
        default=DEFAULT_READ_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--vsmd-write-timeout",
        type=_positive_float,
        default=DEFAULT_WRITE_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--vsmd-max-line-length",
        type=_bounded_integer("vsmd-max-line-length", 1, 0x7FFFFFFF),
        default=DEFAULT_MAX_LINE_LENGTH,
    )
    parser.add_argument(
        "--led-id",
        type=_bounded_integer("led-id", 14, 14),
        default=SOTA_MOUTH_GLOBAL_LED_ID,
    )
    parser.add_argument(
        "--level",
        type=_bounded_integer(
            "level", MIN_LIVE_LEVEL, MAX_LIVE_LEVEL
        ),
        default=MAX_LIVE_LEVEL,
    )
    parser.add_argument(
        "--duration-ms",
        type=_bounded_integer(
            "duration-ms",
            MIN_LIVE_DURATION_MS,
            MAX_LIVE_DURATION_MS,
        ),
        default=MAX_LIVE_DURATION_MS,
    )
    parser.add_argument(
        "--hold-ms",
        type=_bounded_integer(
            "hold-ms",
            MIN_LIVE_HOLD_MS,
            MAX_LIVE_HOLD_MS,
        ),
        default=DEFAULT_LIVE_HOLD_MS,
    )
    parser.add_argument("--confirm-live-write", action="store_true")
    return parser


def _default_memory_factory(transport):
    # type: (VsmdTcpTransport) -> VsmdTypedMemory
    return VsmdTypedMemory(VsmdMemoryClient(transport))


def _print_snapshot(prefix, snapshot, output):
    # type: (str, typing.Optional[ProbeSnapshot], typing.Any) -> None
    if snapshot is None:
        return
    print(
        "{0}_selector=0x{1:04x}".format(prefix, snapshot.selector),
        file=output,
    )
    print("{0}_target={1}".format(prefix, snapshot.target), file=output)
    print("{0}_output={1}".format(prefix, snapshot.output), file=output)
    print(
        "{0}_trigger_pointer=0x{1:04x}".format(
            prefix, snapshot.trigger_pointer
        ),
        file=output,
    )


def _print_lease(lease, output):
    # type: (typing.Optional[AppManagerVsmdLedLockLease], typing.Any) -> None
    if lease is None:
        return
    print("lease_state={0}".format(lease.state), file=output)
    print("release_result={0}".format(lease.release_result), file=output)
    print(
        "lock_released={0}".format(
            str(lease.is_released is True).lower()
        ),
        file=output,
    )


def _print_interpolation_state(prefix, state, reached_target, output):
    # type: (str, typing.Optional[ActiveInterpolationState], bool, typing.Any) -> None
    if state is None:
        return
    print("{0}_output={1}".format(prefix, state.output), file=output)
    print(
        "{0}_remaining_time={1}".format(
            prefix, state.remaining_time
        ),
        file=output,
    )
    print(
        "{0}_trigger_pointer=0x{1:04x}".format(
            prefix, state.trigger_pointer
        ),
        file=output,
    )
    print(
        "{0}_timer_value={1}".format(prefix, state.timer_value),
        file=output,
    )
    print(
        "{0}_snapshot_read_duration_ms={1:.3f}".format(
            prefix, state.snapshot_read_duration_ms
        ),
        file=output,
    )
    print(
        "{0}_poll_attempt={1}".format(prefix, state.poll_attempt),
        file=output,
    )
    print(
        "{0}_reached_target={1}".format(
            prefix,
            str(reached_target is True).lower()
        ),
        file=output,
    )
    if prefix == "rise":
        print(
            "interpolation_reached_target={0}".format(
                str(reached_target is True).lower()
            ),
            file=output,
        )


def _print_timer_preflight(master_control_period_us, timer_ticks):
    # type: (int, int) -> None
    """Print the verified conversion before any lock or VSMD write."""
    print(
        "master_control_period_us={0}".format(
            master_control_period_us
        )
    )
    print("timer_ticks={0}".format(timer_ticks))
    print("rise_timer_ticks={0}".format(timer_ticks))


def main(
    argv=None,
    vsmd_transport_factory=VsmdTcpTransport,
    app_manager_transport_factory=AppManagerTcpTransport,
    memory_factory=_default_memory_factory,
    sleep_function=time.sleep,
):
    # type: (typing.Optional[typing.Sequence[str]], typing.Any, typing.Any, typing.Any, typing.Any) -> int
    """Run the live probe only after explicit confirmation."""
    arguments = create_argument_parser().parse_args(argv)
    print("Sota AppManager mouth LED live probe")
    if not arguments.confirm_live_write:
        print("live_write=false")
        print("result=failure")
        print("error=--confirm-live-write is required")
        return 2

    print("live_write=true")
    print("led_id={0}".format(arguments.led_id))
    print("level={0}".format(arguments.level))
    print("duration_ms={0}".format(arguments.duration_ms))
    print("transition_duration_ms={0}".format(arguments.duration_ms))
    print("hold_duration_ms={0}".format(arguments.hold_ms))
    print(
        "app_manager_endpoint={0}:{1}".format(
            arguments.app_manager_host, arguments.app_manager_port
        )
    )
    print(
        "vsmd_endpoint={0}:{1}".format(
            arguments.vsmd_host, arguments.vsmd_port
        )
    )

    probe = None  # type: typing.Optional[AppManagerMouthLedLiveProbe]
    try:
        vsmd_transport = vsmd_transport_factory(
            host=arguments.vsmd_host,
            port=arguments.vsmd_port,
            connect_timeout=arguments.vsmd_connect_timeout,
            read_timeout=arguments.vsmd_read_timeout,
            write_timeout=arguments.vsmd_write_timeout,
            max_line_length=arguments.vsmd_max_line_length,
        )
        app_manager_transport = app_manager_transport_factory(
            host=arguments.app_manager_host,
            port=arguments.app_manager_port,
            timeout=arguments.app_manager_timeout,
        )
        app_manager_lock = AppManagerLedLock(
            transport=app_manager_transport
        )
        adapter = AppManagerVsmdLedLock(app_manager_lock)
        with vsmd_transport:
            memory = memory_factory(vsmd_transport)
            probe = AppManagerMouthLedLiveProbe(
                memory,
                adapter,
                arguments.level,
                arguments.duration_ms,
                hold_ms=arguments.hold_ms,
                sleep_function=sleep_function,
            )
            result = probe.run(
                preflight_callback=_print_timer_preflight
            )
    except BaseException as error:
        if probe is not None:
            _print_snapshot("pre", probe.preflight, sys.stderr)
            if probe.master_control_period_us is not None:
                print(
                    "master_control_period_us={0}".format(
                        probe.master_control_period_us
                    ),
                    file=sys.stderr,
                )
            if probe.timer_ticks is not None:
                print(
                    "timer_ticks={0}".format(probe.timer_ticks),
                    file=sys.stderr,
                )
            if probe.locked_trigger_pointer is not None:
                print(
                    "locked_trigger_pointer=0x{0:04x}".format(
                        probe.locked_trigger_pointer
                    ),
                    file=sys.stderr,
                )
            _print_interpolation_state(
                "rise",
                probe.active_state,
                probe.interpolation_reached_target,
                sys.stderr,
            )
            _print_interpolation_state(
                "off",
                probe.off_state,
                probe.fade_down_completed,
                sys.stderr,
            )
            print(
                "hold_completed={0}".format(
                    str(probe.hold_completed).lower()
                ),
                file=sys.stderr,
            )
            print(
                "fade_down_completed={0}".format(
                    str(probe.fade_down_completed).lower()
                ),
                file=sys.stderr,
            )
            print(
                "interpolation_output_safe_zero={0}".format(
                    str(
                        probe.interpolation_output_safe_zero
                    ).lower()
                ),
                file=sys.stderr,
            )
            print(
                "routing_state_restored={0}".format(
                    str(probe.routing_state_restored).lower()
                ),
                file=sys.stderr,
            )
            _print_lease(probe.lease, sys.stderr)
        print("result=failure", file=sys.stderr)
        print(
            "error_type={0}".format(type(error).__name__),
            file=sys.stderr,
        )
        print("error={0}".format(error), file=sys.stderr)
        return 1

    _print_snapshot("pre", result.preflight, sys.stdout)
    print("lock_acquired=true")
    print("timer_address=0x{0:04x}".format(result.timer_address))
    print(
        "locked_trigger_pointer=0x{0:04x}".format(
            result.locked_trigger_pointer
        )
    )
    _print_interpolation_state(
        "rise",
        result.active_state,
        result.interpolation_reached_target,
        sys.stdout,
    )
    print("hold_duration_ms={0}".format(result.hold_duration_ms))
    print(
        "hold_completed={0}".format(
            str(result.hold_completed).lower()
        )
    )
    print("fall_timer_ticks={0}".format(result.timer_ticks))
    _print_interpolation_state(
        "off",
        result.off_state,
        result.fade_down_completed,
        sys.stdout,
    )
    print(
        "fade_down_completed={0}".format(
            str(result.fade_down_completed).lower()
        )
    )
    print(
        "interpolation_output_safe_zero={0}".format(
            str(result.interpolation_output_safe_zero).lower()
        )
    )
    print(
        "pulse_completed={0}".format(
            str(result.pulse_completed).lower()
        )
    )
    print("control_sequence_completed=true")
    print("physical_illumination=not_verified")
    print(
        "cleanup_completed={0}".format(
            str(result.cleanup_completed).lower()
        )
    )
    _print_lease(probe.lease, sys.stdout)
    _print_snapshot("post", result.postflight, sys.stdout)
    print("state_restored=true")
    print("routing_state_restored=true")
    print(
        "interpolation_output_restored={0}".format(
            str(
                result.postflight.output == result.preflight.output
            ).lower()
        )
    )
    print("result=success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
