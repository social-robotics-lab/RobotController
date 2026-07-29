"""Explicit, bounded live diagnostic for one Sota mouth-LED pulse.

Importing this module performs no I/O. Both live endpoints are constructed
only after the command line includes ``--confirm-live-write``.
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
from robot_controller.hardware.vsmd.memory import VsmdMemoryClient
from robot_controller.hardware.vsmd.mouth_led import (
    SotaMouthLedController,
    VsmdLedLock,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    MOUTH_LED_AUDIO_SOURCE_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_GLOBAL_LED_ID,
    SOTA_MOUTH_OUTPUT_ADDRESS,
    SOTA_MOUTH_TARGET_ADDRESS,
    SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
)
from robot_controller.hardware.vsmd.transport import VsmdTcpTransport
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


MIN_LIVE_LEVEL = 1
MAX_LIVE_LEVEL = 16
MIN_LIVE_DURATION_MS = 50
MAX_LIVE_DURATION_MS = 200
PROBE_LOCAL_LOCK_KEY = "app-manager-mouth-led-live-probe"


_ProbeSnapshotBase = collections.namedtuple(
    "_ProbeSnapshotBase",
    ["selector", "target", "output", "trigger_pointer"],
)


class ProbeSnapshot(_ProbeSnapshotBase):
    """Immutable mouth-LED state read from confirmed VSMD addresses."""

    __slots__ = ()


_ProbeResultBase = collections.namedtuple(
    "_ProbeResultBase",
    [
        "preflight",
        "locked_trigger_pointer",
        "timer_address",
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
        sleep_function=time.sleep,
        controller_factory=SotaMouthLedController,
    ):
        # type: (VsmdTypedMemory, AppManagerVsmdLedLock, int, int, typing.Any, typing.Any) -> None
        if not isinstance(memory, VsmdTypedMemory):
            raise TypeError("memory must be VsmdTypedMemory")
        if not isinstance(led_lock, AppManagerVsmdLedLock):
            raise TypeError("led_lock must be AppManagerVsmdLedLock")
        _validate_live_level(level)
        _validate_live_duration(duration_ms)
        if not callable(sleep_function):
            raise TypeError("sleep_function must be callable")
        if not callable(controller_factory):
            raise TypeError("controller_factory must be callable")
        self._memory = memory
        self._led_lock = led_lock
        self._level = level
        self._duration_ms = duration_ms
        self._sleep_function = sleep_function
        self._controller_factory = controller_factory
        self._has_run = False
        self.preflight = None  # type: typing.Optional[ProbeSnapshot]
        self.postflight = None  # type: typing.Optional[ProbeSnapshot]
        self.locked_trigger_pointer = None  # type: typing.Optional[int]
        self.lease = None  # type: typing.Optional[AppManagerVsmdLedLockLease]
        self.pulse_completed = False
        self.cleanup_completed = False

    def run(self):
        # type: () -> ProbeResult
        """Execute one pulse without retrying any lock or release operation."""
        if self._has_run:
            raise VsmdMouthLedStateError(
                "live probe instances may run only once"
            )
        self._has_run = True
        self.preflight = self._read_snapshot()
        self._validate_preflight(self.preflight)

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
                self._memory, self._led_lock
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
        if operation_error is not None:
            raise operation_error

        _validate_release_success(self.lease)

        # Failed/unknown release exits above. Do not perform extra reads in
        # that state: the server stack may still own the LED and success is
        # already impossible. The probe never attempts recovery or retry.
        self.postflight = self._read_snapshot()
        self._validate_postflight(self.preflight, self.postflight)
        return ProbeResult(
            self.preflight,
            self.locked_trigger_pointer,
            timer_address,
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
            "Run one bounded Sota mouth-LED pulse. No endpoint is opened "
            "unless --confirm-live-write is present."
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
                sleep_function=sleep_function,
            )
            result = probe.run()
    except BaseException as error:
        if probe is not None:
            _print_snapshot("pre", probe.preflight, sys.stderr)
            if probe.locked_trigger_pointer is not None:
                print(
                    "locked_trigger_pointer=0x{0:04x}".format(
                        probe.locked_trigger_pointer
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
    print(
        "pulse_completed={0}".format(
            str(result.pulse_completed).lower()
        )
    )
    print(
        "cleanup_completed={0}".format(
            str(result.cleanup_completed).lower()
        )
    )
    _print_lease(probe.lease, sys.stdout)
    _print_snapshot("post", result.postflight, sys.stdout)
    print("state_restored=true")
    print("result=success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
