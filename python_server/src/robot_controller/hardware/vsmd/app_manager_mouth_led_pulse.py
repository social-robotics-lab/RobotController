"""Reusable, bounded Sota mouth-LED pulse operation.

Importing this module performs no I/O. The operation uses only injected typed
memory, AppManager locking, clocks, and controller dependencies.
"""

import collections
import time
import typing

from robot_controller.hardware.mouth_led_backend import (
    MAX_MOUTH_LED_DURATION_MS,
    MAX_MOUTH_LED_HOLD_MS,
    MAX_MOUTH_LED_LEVEL,
    MIN_MOUTH_LED_DURATION_MS,
    MIN_MOUTH_LED_HOLD_MS,
    MIN_MOUTH_LED_LEVEL,
    validate_mouth_led_duration,
    validate_mouth_led_hold,
    validate_mouth_led_level,
)
from robot_controller.hardware.vsmd.app_manager_codec import (
    APP_MANAGER_RESPONSE_OK,
)
from robot_controller.hardware.vsmd.app_manager_lock import (
    LEASE_RELEASED,
    validate_timer_address,
)
from robot_controller.hardware.vsmd.app_manager_vsmd_lock import (
    AppManagerVsmdLedLock,
    AppManagerVsmdLedLockLease,
    AppManagerLeaseInterpolationTimer,
)
from robot_controller.hardware.vsmd.errors import (
    VsmdMouthLedCleanupError,
    VsmdMouthLedStateError,
)
from robot_controller.hardware.vsmd.interpolation_timing import (
    milliseconds_to_control_ticks,
)
from robot_controller.hardware.vsmd.mouth_led import (
    SotaMouthLedController,
    VsmdLedLock,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    INTERP_LED_TARGET_BASE,
    MASTER_CONTROL_PERIOD_ADDRESS,
    MOUTH_LED_AUDIO_SOURCE_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_GLOBAL_LED_ID,
    SOTA_MOUTH_OUTPUT_ADDRESS,
    SOTA_MOUTH_REMAINING_TIME_ADDRESS,
    SOTA_MOUTH_TARGET_ADDRESS,
    SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


MIN_LIVE_LEVEL = MIN_MOUTH_LED_LEVEL
MAX_LIVE_LEVEL = MAX_MOUTH_LED_LEVEL
MIN_LIVE_DURATION_MS = MIN_MOUTH_LED_DURATION_MS
MAX_LIVE_DURATION_MS = MAX_MOUTH_LED_DURATION_MS
MIN_LIVE_HOLD_MS = MIN_MOUTH_LED_HOLD_MS
MAX_LIVE_HOLD_MS = MAX_MOUTH_LED_HOLD_MS
DEFAULT_LIVE_HOLD_MS = 500
PULSE_LOCAL_LOCK_KEY = "app-manager-mouth-led-live-probe"
MAX_ACTIVE_STATE_RECHECKS = 3
MIN_ACTIVE_COMPLETION_GRACE_SECONDS = 0.05
MAX_ACTIVE_COMPLETION_GRACE_SECONDS = 0.5
MAX_ACTIVE_POLL_INTERVAL_SECONDS = 0.05


_MouthLedPulseSnapshotBase = collections.namedtuple(
    "_MouthLedPulseSnapshotBase",
    ["selector", "target", "output", "trigger_pointer"],
)


class MouthLedPulseSnapshot(_MouthLedPulseSnapshotBase):
    """Immutable mouth-LED state read from confirmed VSMD addresses."""

    __slots__ = ()


_InterpolationObservationBase = collections.namedtuple(
    "_InterpolationObservationBase",
    [
        "trigger_pointer",
        "remaining_before",
        "output",
        "remaining_after",
        "timer_value",
        "observation_read_duration_ms",
        "poll_attempt",
    ],
)


class InterpolationObservation(_InterpolationObservationBase):
    """Immutable record of sequential reads; it is not an atomic snapshot."""

    __slots__ = ()

    @property
    def remaining_time(self):
        # type: () -> int
        """Compatibility alias for the final RemainingTime read."""
        return self.remaining_after

    @property
    def snapshot_read_duration_ms(self):
        # type: () -> float
        """Compatibility alias retained for existing diagnostic consumers."""
        return self.observation_read_duration_ms


ActiveInterpolationState = InterpolationObservation


_MouthLedPulseResultBase = collections.namedtuple(
    "_MouthLedPulseResultBase",
    [
        "preflight",
        "locked_trigger_pointer",
        "timer_address",
        "master_control_period_us",
        "timer_ticks",
        "normalization_required",
        "normalization_timer_ticks",
        "normalized_state",
        "normalization_observations",
        "normalization_completed",
        "active_state",
        "interpolation_reached_target",
        "active_snapshots",
        "hold_duration_ms",
        "hold_completed",
        "off_state",
        "off_snapshots",
        "fade_down_completed",
        "interpolation_output_safe_zero",
        "emergency_fade_down_attempted",
        "emergency_fade_down_completed",
        "postflight",
        "pulse_completed",
        "cleanup_completed",
        "level",
        "rise_ms",
        "fall_ms",
        "fall_timer_ticks",
        "routing_state_restored",
        "lock_released",
    ],
)


class MouthLedPulseResult(_MouthLedPulseResultBase):
    """Successful result after release and postflight validation."""

    __slots__ = ()

    @property
    def rise_timer_ticks(self):
        # type: () -> int
        return self.timer_ticks

    @property
    def rise_reached_target(self):
        # type: () -> bool
        return self.interpolation_reached_target

    @property
    def rise_observations(self):
        # type: () -> typing.Tuple[InterpolationObservation, ...]
        return self.active_snapshots

    @property
    def fall_observations(self):
        # type: () -> typing.Tuple[InterpolationObservation, ...]
        return self.off_snapshots


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
                "mouth LED pulse operation lease was already handed to the controller"
            )
        if key != self._local_key or tuple(led_ids) != self._lease.led_ids:
            raise VsmdMouthLedStateError(
                "controller requested a different mouth LED pulse operation lease"
            )
        self._handed_off = True
        return self._lease

    def release(self, key, led_ids):
        # type: (str, typing.Sequence[int]) -> None
        raise VsmdMouthLedStateError(
            "mouth LED pulse operation lease must be released by its owned lease"
        )


class SotaMouthLedPulseOperation(object):
    """Run exactly one preflight-guarded pulse through the real controller."""

    def __init__(
        self,
        memory,
        led_lock,
        level,
        duration_ms,
        hold_ms=DEFAULT_LIVE_HOLD_MS,
        fall_ms=None,
        sleep_function=time.sleep,
        monotonic_function=time.monotonic,
        controller_factory=SotaMouthLedController,
    ):
        # type: (VsmdTypedMemory, AppManagerVsmdLedLock, int, int, int, typing.Optional[int], typing.Any, typing.Any, typing.Any) -> None
        if not isinstance(memory, VsmdTypedMemory):
            raise TypeError("memory must be VsmdTypedMemory")
        if not isinstance(led_lock, AppManagerVsmdLedLock):
            raise TypeError("led_lock must be AppManagerVsmdLedLock")
        validate_mouth_led_level(level)
        validate_mouth_led_duration(duration_ms)
        validate_mouth_led_hold(hold_ms)
        if fall_ms is None:
            fall_ms = duration_ms
        validate_mouth_led_duration(fall_ms)
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
        self._fall_ms = fall_ms
        self._hold_ms = hold_ms
        self._sleep_function = sleep_function
        self._monotonic_function = monotonic_function
        self._controller_factory = controller_factory
        self._has_run = False
        self.preflight = None  # type: typing.Optional[MouthLedPulseSnapshot]
        self.postflight = None  # type: typing.Optional[MouthLedPulseSnapshot]
        self.locked_trigger_pointer = None  # type: typing.Optional[int]
        self.master_control_period_us = None  # type: typing.Optional[int]
        self.timer_ticks = None  # type: typing.Optional[int]
        self.fall_timer_ticks = None  # type: typing.Optional[int]
        self.normalization_required = False
        self.normalization_timer_ticks = None  # type: typing.Optional[int]
        self.normalized_state = None  # type: typing.Optional[InterpolationObservation]
        self.normalization_observations = []  # type: typing.List[InterpolationObservation]
        self.normalization_completed = False
        self.active_state = None  # type: typing.Optional[InterpolationObservation]
        self.active_snapshots = []  # type: typing.List[InterpolationObservation]
        self.interpolation_reached_target = False
        self.hold_completed = False
        self.off_state = None  # type: typing.Optional[InterpolationObservation]
        self.off_snapshots = []  # type: typing.List[InterpolationObservation]
        self.fade_down_completed = False
        self.interpolation_output_safe_zero = False
        self.emergency_state = None  # type: typing.Optional[InterpolationObservation]
        self.emergency_observations = []  # type: typing.List[InterpolationObservation]
        self.emergency_fade_down_attempted = False
        self.emergency_fade_down_completed = False
        self.primary_operation_error = None  # type: typing.Optional[BaseException]
        self.routing_state_restored = False
        self.lease = None  # type: typing.Optional[AppManagerVsmdLedLockLease]
        self.pulse_completed = False
        self.cleanup_completed = False

    def run(self, preflight_callback=None):
        # type: (typing.Optional[typing.Callable[[int, int], None]]) -> MouthLedPulseResult
        """Execute one pulse without retrying any lock or release operation."""
        if preflight_callback is not None and not callable(
            preflight_callback
        ):
            raise TypeError("preflight_callback must be callable")
        if self._has_run:
            raise VsmdMouthLedStateError(
                "mouth LED pulse operation instances may run only once"
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
        self.fall_timer_ticks = milliseconds_to_control_ticks(
            self._fall_ms, self.master_control_period_us
        )
        if preflight_callback is not None:
            preflight_callback(
                self.master_control_period_us, self.timer_ticks
            )

        self.lease = self._led_lock.acquire(
            PULSE_LOCAL_LOCK_KEY, (SOTA_MOUTH_GLOBAL_LED_ID,)
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
            PULSE_LOCAL_LOCK_KEY, self.lease
        )
        timer = None  # type: typing.Optional[AppManagerLeaseInterpolationTimer]
        try:
            timer = AppManagerLeaseInterpolationTimer(
                self._memory,
                self._led_lock,
                master_control_period_us=self.master_control_period_us,
            )
            self.normalization_required = self.preflight.output != 0
            self.normalization_timer_ticks = self.timer_ticks
            if self.normalization_required:
                self._memory.write_s16_at(
                    INTERP_LED_TARGET_BASE,
                    SOTA_MOUTH_GLOBAL_LED_ID,
                    0,
                )
                timer.set_duration(
                    SOTA_MOUTH_GLOBAL_LED_ID, self._duration_ms
                )
                self._sleep_function(self._duration_ms / 1000.0)
                (
                    self.normalized_state,
                    self.normalization_observations,
                ) = self._wait_for_interpolation(
                    timer_address,
                    0,
                    "normalization",
                    self.timer_ticks,
                )
            selector_before_switch = self._memory.read_u16(
                MOUTH_LED_SELECTOR_ADDRESS
            )
            if selector_before_switch != self.preflight.selector:
                raise VsmdMouthLedStateError(
                    "mouth selector changed during hidden normalization"
                )
            self.normalization_completed = True
        except BaseException as preparation_error:
            self._cleanup_normalization_failure(
                timer, preparation_error
            )

        try:
            controller = self._controller_factory(
                self._memory,
                timer,
                led_lock=handoff_lock,
                lock_key=PULSE_LOCAL_LOCK_KEY,
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
                self.timer_ticks,
            )
            self.interpolation_reached_target = True
            self._sleep_function(self._hold_ms / 1000.0)
            self.hold_completed = True
            controller.turn_off(self._fall_ms)
            self._sleep_function(self._fall_ms / 1000.0)
            try:
                self.off_state, self.off_snapshots = (
                    self._wait_for_interpolation(
                        timer_address,
                        0,
                        "fade-down",
                        self.fall_timer_ticks,
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
            self.primary_operation_error = error

        emergency_error = None  # type: typing.Optional[BaseException]
        if (
            operation_error is not None
            and controller.is_voice_sync_disabled
        ):
            self.emergency_fade_down_attempted = True
            try:
                controller.turn_off(self._fall_ms)
                self._sleep_function(self._fall_ms / 1000.0)
                (
                    self.emergency_state,
                    self.emergency_observations,
                ) = self._wait_for_interpolation(
                    timer_address,
                    0,
                    "emergency-fade-down",
                    self.fall_timer_ticks,
                )
                self.emergency_fade_down_completed = True
                self.interpolation_output_safe_zero = True
            except BaseException as error:
                emergency_error = error

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

        recovery_error = _combine_cleanup_errors(
            emergency_error, cleanup_error
        )
        try:
            _validate_release_success(self.lease)
        except BaseException as error:
            if cleanup_error is None:
                recovery_error = _combine_cleanup_errors(
                    recovery_error, error
                )
            if operation_error is not None:
                raise VsmdMouthLedCleanupError(
                    operation_error, recovery_error
                ) from recovery_error
            raise recovery_error

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
        recovery_error = _combine_cleanup_errors(
            recovery_error, postflight_error
        )
        if operation_error is not None and recovery_error is not None:
            raise VsmdMouthLedCleanupError(
                operation_error, recovery_error
            ) from recovery_error
        if recovery_error is not None:
            raise recovery_error
        if operation_error is not None:
            raise operation_error
        return MouthLedPulseResult(
            self.preflight,
            self.locked_trigger_pointer,
            timer_address,
            self.master_control_period_us,
            self.timer_ticks,
            self.normalization_required,
            self.normalization_timer_ticks,
            self.normalized_state,
            tuple(self.normalization_observations),
            self.normalization_completed,
            self.active_state,
            self.interpolation_reached_target,
            tuple(self.active_snapshots),
            self._hold_ms,
            self.hold_completed,
            self.off_state,
            tuple(self.off_snapshots),
            self.fade_down_completed,
            self.interpolation_output_safe_zero,
            self.emergency_fade_down_attempted,
            self.emergency_fade_down_completed,
            self.postflight,
            self.pulse_completed,
            self.cleanup_completed,
            self._level,
            self._duration_ms,
            self._fall_ms,
            self.fall_timer_ticks,
            self.routing_state_restored,
            self.lease.is_released is True,
        )

    def _read_snapshot(self):
        # type: () -> MouthLedPulseSnapshot
        return MouthLedPulseSnapshot(
            self._memory.read_u16(MOUTH_LED_SELECTOR_ADDRESS),
            self._memory.read_s16(SOTA_MOUTH_TARGET_ADDRESS),
            self._memory.read_s16(SOTA_MOUTH_OUTPUT_ADDRESS),
            self._memory.read_u16(SOTA_MOUTH_TRIGGER_POINTER_ADDRESS),
        )

    def _read_interpolation_observation(
        self, timer_address, poll_attempt
    ):
        # type: (int, int) -> InterpolationObservation
        """Read ordered fields without claiming they form an atomic snapshot."""
        started_at = self._monotonic_function()
        trigger_pointer = self._memory.read_u16(
            SOTA_MOUTH_TRIGGER_POINTER_ADDRESS
        )
        remaining_before = self._memory.read_u16(
            SOTA_MOUTH_REMAINING_TIME_ADDRESS
        )
        output = self._memory.read_s16(SOTA_MOUTH_OUTPUT_ADDRESS)
        remaining_after = self._memory.read_u16(
            SOTA_MOUTH_REMAINING_TIME_ADDRESS
        )
        timer_value = self._memory.read_u16(timer_address)
        finished_at = self._monotonic_function()
        return InterpolationObservation(
            trigger_pointer,
            remaining_before,
            output,
            remaining_after,
            timer_value,
            max(0.0, (finished_at - started_at) * 1000.0),
            poll_attempt,
        )

    def _wait_for_interpolation(
        self, timer_address, expected_output, phase_name, timer_ticks
    ):
        # type: (int, int, str, int) -> typing.Tuple[InterpolationObservation, typing.List[InterpolationObservation]]
        """Bound repeated sequential observations without automatic rewrites."""
        period_seconds = self.master_control_period_us / 1000000.0
        grace_seconds = min(
            MAX_ACTIVE_COMPLETION_GRACE_SECONDS,
            max(
                MIN_ACTIVE_COMPLETION_GRACE_SECONDS,
                (timer_ticks + 2) * period_seconds,
            ),
        )
        poll_interval = min(
            MAX_ACTIVE_POLL_INTERVAL_SECONDS,
            max(period_seconds, 0.001),
        )
        deadline = self._monotonic_function() + grace_seconds
        poll_attempt = 0
        observations = []  # type: typing.List[InterpolationObservation]
        while True:
            state = self._read_interpolation_observation(
                timer_address, poll_attempt
            )
            observations.append(state)
            if phase_name == "rise":
                self.active_state = state
                self.active_snapshots = list(observations)
            elif phase_name == "fade-down":
                self.off_state = state
                self.off_snapshots = list(observations)
                self.interpolation_output_safe_zero = state.output == 0
            elif phase_name == "normalization":
                self.normalized_state = state
                self.normalization_observations = list(observations)
            else:
                self.emergency_state = state
                self.emergency_observations = list(observations)
                if state.output == 0:
                    self.interpolation_output_safe_zero = True
            if (
                state.output == expected_output
                and state.remaining_before == 0
                and state.remaining_after == 0
                and state.trigger_pointer == timer_address
            ):
                return state, observations
            if state.trigger_pointer != timer_address:
                raise VsmdMouthLedStateError(
                    "{0} TriggerPointer did not match the lease timer".format(
                        phase_name
                    )
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
        # type: (MouthLedPulseSnapshot) -> None
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
        # type: (MouthLedPulseSnapshot, MouthLedPulseSnapshot) -> None
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

    def _cleanup_normalization_failure(self, timer, operation_error):
        # type: (typing.Optional[AppManagerLeaseInterpolationTimer], BaseException) -> typing.NoReturn
        """Clear preparatory writes and release once without changing selector."""
        cleanup_error = None  # type: typing.Optional[BaseException]
        if timer is not None and self.normalization_required:
            try:
                self._memory.write_s16_at(
                    INTERP_LED_TARGET_BASE,
                    SOTA_MOUTH_GLOBAL_LED_ID,
                    0,
                )
            except BaseException as error:
                cleanup_error = _combine_cleanup_errors(
                    cleanup_error, error
                )
            try:
                timer.set_duration(SOTA_MOUTH_GLOBAL_LED_ID, 0)
            except BaseException as error:
                cleanup_error = _combine_cleanup_errors(
                    cleanup_error, error
                )
        try:
            self.lease.release()
            _validate_release_success(self.lease)
        except BaseException as error:
            cleanup_error = _combine_cleanup_errors(
                cleanup_error, error
            )
        if cleanup_error is not None:
            raise VsmdMouthLedCleanupError(
                operation_error, cleanup_error
            ) from cleanup_error
        raise operation_error


def _combine_cleanup_errors(first_error, second_error):
    # type: (typing.Optional[BaseException], typing.Optional[BaseException]) -> typing.Optional[BaseException]
    """Preserve two recovery failures without introducing another error type."""
    if first_error is None:
        return second_error
    if second_error is None:
        return first_error
    return VsmdMouthLedCleanupError(first_error, second_error)


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

