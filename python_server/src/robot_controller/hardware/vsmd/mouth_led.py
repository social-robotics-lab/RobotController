"""Fail-closed Sota mouth-LED state model.

Production writes remain unavailable until the exact InterpLockerClient
protocol is verified. Tests inject a fake lock and timer to exercise the full
save, switch, restore, and release sequence without hardware I/O.
"""

import abc
import threading
import typing

from robot_controller.hardware.vsmd.errors import (
    VsmdLedLockUnavailableError,
    VsmdMouthLedCleanupError,
    VsmdMouthLedStateError,
    VsmdUnexpectedMouthSelectorError,
    VsmdValidationError,
)
from robot_controller.hardware.vsmd.interpolation_timing import (
    VsmdControlTickConverter,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    INTERP_LED_TARGET_BASE,
    INTERP_TARGET_TIME_BASE,
    MOUTH_LED_AUDIO_SOURCE_ADDRESS,
    MOUTH_LED_NORMAL_SOURCE_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_GLOBAL_LED_ID,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


DEFAULT_MOUTH_LED_LOCK_KEY = "robot-controller-python-mouth"


class VsmdLedLock(abc.ABC):
    """VSMD LED interpolation lock boundary.

    Implementations may coordinate TriggerPointer updates without providing a
    cross-process mutex.
    """

    @abc.abstractmethod
    def acquire(self, key, led_ids):
        # type: (str, typing.Sequence[int]) -> typing.Any
        """Acquire the requested IDs and optionally return an owned lease.

        Legacy and fake implementations may return ``None``. Lease-aware
        implementations return an object whose parameterless ``release()``
        releases the exact key and LED IDs captured during acquisition.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def release(self, key, led_ids):
        # type: (str, typing.Sequence[int]) -> None
        """Release the requested LED IDs."""
        raise NotImplementedError


class UnavailableVsmdLedLock(VsmdLedLock):
    """Production default until InterpLockerClient is exactly understood."""

    def acquire(self, key, led_ids):
        # type: (str, typing.Sequence[int]) -> None
        raise VsmdLedLockUnavailableError(
            "Verified InterpLockerClient protocol is not implemented"
        )

    def release(self, key, led_ids):
        # type: (str, typing.Sequence[int]) -> None
        raise VsmdLedLockUnavailableError(
            "Verified InterpLockerClient protocol is not implemented"
        )


class VsmdInterpolationTimer(abc.ABC):
    """Set the daemon's normal interpolation duration for one LED."""

    @abc.abstractmethod
    def set_duration(self, led_id, duration_ms):
        # type: (int, int) -> None
        """Set a validated interpolation duration."""
        raise NotImplementedError


class VsmdMemoryInterpolationTimer(VsmdInterpolationTimer):
    """Use the verified per-ID target-time memory array."""

    def __init__(self, memory, master_control_period_us=None):
        # type: (VsmdTypedMemory, typing.Optional[int]) -> None
        if not isinstance(memory, VsmdTypedMemory):
            raise TypeError("memory must be VsmdTypedMemory")
        self._memory = memory
        self._tick_converter = VsmdControlTickConverter(
            memory, master_control_period_us
        )

    def set_duration(self, led_id, duration_ms):
        # type: (int, int) -> None
        _validate_duration(duration_ms)
        timer_ticks = self._tick_converter.convert(duration_ms)
        self._memory.write_u16_at(
            INTERP_TARGET_TIME_BASE, led_id, timer_ticks
        )


class SotaMouthLedController(object):
    """Temporarily route and control mouth LED 14 through interpolation.

    Constructing this object performs no read or write. The default lock fails
    before any memory operation, preventing production use without a verified
    lock implementation.
    """

    def __init__(
        self,
        memory,
        timer,
        led_lock=None,
        lock_key=DEFAULT_MOUTH_LED_LOCK_KEY,
    ):
        # type: (VsmdTypedMemory, VsmdInterpolationTimer, typing.Optional[VsmdLedLock], str) -> None
        if not isinstance(memory, VsmdTypedMemory):
            raise TypeError("memory must be VsmdTypedMemory")
        if not isinstance(timer, VsmdInterpolationTimer):
            raise TypeError("timer must implement VsmdInterpolationTimer")
        if led_lock is None:
            led_lock = UnavailableVsmdLedLock()
        if not isinstance(led_lock, VsmdLedLock):
            raise TypeError("led_lock must implement VsmdLedLock")
        if not isinstance(lock_key, str) or not lock_key:
            raise ValueError("lock_key must be a non-empty string")
        self._memory = memory
        self._timer = timer
        self._led_lock = led_lock
        self._lock_key = lock_key
        self._led_ids = (SOTA_MOUTH_GLOBAL_LED_ID,)
        self._state_lock = threading.RLock()
        self._active = False
        self._lock_lease = None  # type: typing.Any
        self._original_selector = None  # type: typing.Optional[int]
        self._original_target = None  # type: typing.Optional[int]

    @property
    def is_voice_sync_disabled(self):
        # type: () -> bool
        with self._state_lock:
            return self._active

    def disable_voice_sync(self):
        # type: () -> None
        """Acquire LED 14, save state, and select interpolated output."""
        with self._state_lock:
            if self._active:
                return
            self._lock_lease = self._led_lock.acquire(
                self._lock_key, self._led_ids
            )
            selector = None
            target = None
            selector_write_attempted = False
            try:
                selector = self._memory.read_u16(
                    MOUTH_LED_SELECTOR_ADDRESS
                )
                if selector not in (
                    MOUTH_LED_AUDIO_SOURCE_ADDRESS,
                    MOUTH_LED_NORMAL_SOURCE_ADDRESS,
                ):
                    raise VsmdUnexpectedMouthSelectorError(
                        "Unexpected mouth selector {0}; refusing writes".format(
                            selector
                        )
                    )
                target = self._memory.read_s16_at(
                    INTERP_LED_TARGET_BASE, SOTA_MOUTH_GLOBAL_LED_ID
                )
                selector_write_attempted = True
                self._memory.write_u16(
                    MOUTH_LED_SELECTOR_ADDRESS,
                    MOUTH_LED_NORMAL_SOURCE_ADDRESS,
                )
            except BaseException as operation_error:
                if selector_write_attempted and selector is not None:
                    self._attempt_call(
                        self._memory.write_u16,
                        MOUTH_LED_SELECTOR_ADDRESS,
                        selector,
                    )
                if selector_write_attempted and target is not None:
                    self._attempt_call(
                        self._memory.write_s16_at,
                        INTERP_LED_TARGET_BASE,
                        SOTA_MOUTH_GLOBAL_LED_ID,
                        target,
                    )
                try:
                    self._release_current_lock()
                except BaseException as cleanup_error:
                    raise VsmdMouthLedCleanupError(
                        operation_error, cleanup_error
                    ) from cleanup_error
                raise
            self._original_selector = selector
            self._original_target = target
            self._active = True

    def set_brightness(self, value, duration_ms):
        # type: (int, int) -> None
        """Set a bounded target through the normal interpolation arrays."""
        _validate_brightness(value)
        _validate_duration(duration_ms)
        with self._state_lock:
            self._require_active()
            try:
                self._memory.write_s16_at(
                    INTERP_LED_TARGET_BASE,
                    SOTA_MOUTH_GLOBAL_LED_ID,
                    value,
                )
                self._timer.set_duration(
                    SOTA_MOUTH_GLOBAL_LED_ID, duration_ms
                )
            except BaseException as operation_error:
                try:
                    self.enable_voice_sync()
                except BaseException as cleanup_error:
                    raise VsmdMouthLedCleanupError(
                        operation_error, cleanup_error
                    ) from cleanup_error
                raise

    def turn_off(self, duration_ms):
        # type: (int) -> None
        """Interpolate mouth brightness to zero."""
        self.set_brightness(0, duration_ms)

    def enable_voice_sync(self):
        # type: () -> None
        """Restore routing and target, then release LED 14.

        Every restoration step is attempted. Selector restoration is attempted
        before original-target restoration so audio routing has priority.
        """
        with self._state_lock:
            if not self._active:
                return
            first_error = None  # type: typing.Optional[BaseException]
            try:
                self._memory.write_s16_at(
                    INTERP_LED_TARGET_BASE, SOTA_MOUTH_GLOBAL_LED_ID, 0
                )
                self._timer.set_duration(SOTA_MOUTH_GLOBAL_LED_ID, 0)
            except BaseException as error:
                first_error = error

            try:
                self._memory.write_u16(
                    MOUTH_LED_SELECTOR_ADDRESS,
                    self._original_selector,
                )
            except BaseException as error:
                if first_error is None:
                    first_error = error

            try:
                self._memory.write_s16_at(
                    INTERP_LED_TARGET_BASE,
                    SOTA_MOUTH_GLOBAL_LED_ID,
                    self._original_target,
                )
            except BaseException as error:
                if first_error is None:
                    first_error = error

            release_error = None  # type: typing.Optional[BaseException]
            try:
                self._release_current_lock()
            except BaseException as error:
                release_error = error
            finally:
                self._active = False
                self._original_selector = None
                self._original_target = None

            if release_error is not None:
                if first_error is not None:
                    raise VsmdMouthLedCleanupError(
                        first_error, release_error
                    ) from release_error
                raise release_error
            if first_error is not None:
                raise first_error

    def close(self):
        # type: () -> None
        """Restore voice sync idempotently."""
        self.enable_voice_sync()

    def __enter__(self):
        # type: () -> SotaMouthLedController
        self.disable_voice_sync()
        return self

    def __exit__(self, exception_type, exception, traceback):
        # type: (typing.Any, typing.Any, typing.Any) -> bool
        self.close()
        return False

    def _require_active(self):
        # type: () -> None
        if not self._active:
            raise VsmdMouthLedStateError(
                "voice sync must be disabled before changing brightness"
            )

    def _release_current_lock(self):
        # type: () -> None
        lease = self._lock_lease
        self._lock_lease = None
        if lease is not None:
            release = getattr(lease, "release", None)
            if not callable(release):
                raise VsmdMouthLedStateError(
                    "lock acquire returned an invalid lease"
                )
            release()
            return
        self._led_lock.release(self._lock_key, self._led_ids)

    @staticmethod
    def _attempt_call(callable_object, *args):
        # type: (typing.Any, *typing.Any) -> None
        try:
            callable_object(*args)
        except BaseException:
            pass


def _validate_brightness(value):
    # type: (int) -> None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 255
    ):
        raise VsmdValidationError(
            "brightness must be an integer between 0 and 255"
        )


def _validate_duration(duration_ms):
    # type: (int) -> None
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or duration_ms < 0
        or duration_ms > 0xFFFF
    ):
        raise VsmdValidationError(
            "duration_ms must be an integer between 0 and 65535"
        )
