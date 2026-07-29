"""Adapters from AppManager leases to the existing VSMD mouth-LED ports."""

import threading
import typing

from robot_controller.hardware.vsmd.app_manager_codec import validate_led_ids
from robot_controller.hardware.vsmd.app_manager_lock import (
    AppManagerLedLock,
    AppManagerLedLockLease,
    LEASE_ACTIVE,
)
from robot_controller.hardware.vsmd.errors import VsmdMouthLedStateError
from robot_controller.hardware.vsmd.interpolation_timing import (
    VsmdControlTickConverter,
)
from robot_controller.hardware.vsmd.mouth_led import (
    VsmdInterpolationTimer,
    VsmdLedLock,
    _validate_duration,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


class AppManagerVsmdLedLockLease(object):
    """Own one AppManager lease and release it without caller-supplied IDs."""

    def __init__(self, owner, local_key, app_manager_lease):
        # type: (AppManagerVsmdLedLock, str, AppManagerLedLockLease) -> None
        self._owner = owner
        self._local_key = local_key
        self._app_manager_lease = app_manager_lease
        self._released = False
        self._state_lock = threading.Lock()

    @property
    def key(self):
        # type: () -> str
        return self._app_manager_lease.key

    @property
    def led_ids(self):
        # type: () -> typing.Tuple[int, ...]
        return self._app_manager_lease.led_ids

    @property
    def timer_address(self):
        # type: () -> int
        return self._app_manager_lease.timer_address

    @property
    def is_released(self):
        # type: () -> bool
        with self._state_lock:
            return self._released

    @property
    def release_result(self):
        # type: () -> typing.Optional[str]
        return self._app_manager_lease.release_result

    @property
    def state(self):
        # type: () -> str
        return self._app_manager_lease.state

    @property
    def _is_active(self):
        # type: () -> bool
        return self._app_manager_lease.state == LEASE_ACTIVE

    def release(self):
        # type: () -> None
        """Release once using the immutable key and IDs owned by the lease."""
        with self._state_lock:
            if self._released:
                return
            self._app_manager_lease.release()
            self._owner._mark_released(self)
            self._released = True

    def __enter__(self):
        # type: () -> AppManagerVsmdLedLockLease
        return self

    def __exit__(self, exception_type, exception, traceback):
        # type: (typing.Any, typing.Any, typing.Any) -> bool
        self.release()
        return False


class AppManagerVsmdLedLock(VsmdLedLock):
    """Adapt lease-based AppManager locking to ``VsmdLedLock``.

    This object prevents overlapping IDs only among leases created by this
    adapter instance. It is not a cross-process mutex and is not installed in
    the production Composition Root.
    """

    def __init__(self, app_manager_lock):
        # type: (AppManagerLedLock) -> None
        if not isinstance(app_manager_lock, AppManagerLedLock):
            raise TypeError("app_manager_lock must be AppManagerLedLock")
        self._app_manager_lock = app_manager_lock
        self._state_lock = threading.RLock()
        self._leases_by_local_key = (
            {}
        )  # type: typing.Dict[str, AppManagerVsmdLedLockLease]
        self._reserved_led_ids = set()  # type: typing.Set[int]

    def acquire(self, key, led_ids):
        # type: (str, typing.Sequence[int]) -> AppManagerVsmdLedLockLease
        """Acquire and return a lease compatible with the mouth controller."""
        if not isinstance(key, str) or not key:
            raise VsmdMouthLedStateError(
                "adapter lock key must be a non-empty string"
            )
        validated_ids = validate_led_ids(led_ids)
        with self._state_lock:
            if key in self._leases_by_local_key:
                raise VsmdMouthLedStateError(
                    "adapter lock key is already active"
                )
            duplicates = self._reserved_led_ids.intersection(validated_ids)
            if duplicates:
                raise VsmdMouthLedStateError(
                    "LED IDs already have an active adapter lease: {0}".format(
                        tuple(sorted(duplicates))
                    )
                )
            self._reserved_led_ids.update(validated_ids)
        try:
            app_manager_lease = self._app_manager_lock.acquire_leds(
                validated_ids
            )
        except BaseException:
            with self._state_lock:
                self._reserved_led_ids.difference_update(validated_ids)
            raise
        lease = AppManagerVsmdLedLockLease(
            self, key, app_manager_lease
        )
        with self._state_lock:
            self._leases_by_local_key[key] = lease
        return lease

    def release(self, key, led_ids):
        # type: (str, typing.Sequence[int]) -> None
        """Compatibility path for legacy callers; prefer ``lease.release``."""
        validated_ids = validate_led_ids(led_ids)
        with self._state_lock:
            lease = self._leases_by_local_key.get(key)
        if lease is None:
            raise VsmdMouthLedStateError(
                "adapter lock key has no active lease"
            )
        if lease.led_ids != validated_ids:
            raise VsmdMouthLedStateError(
                "release IDs differ from the acquired lease"
            )
        lease.release()

    def timer_address_for(self, led_id):
        # type: (int) -> int
        """Return the active lease timer for one LED, or fail before write."""
        with self._state_lock:
            matches = [
                lease
                for lease in self._leases_by_local_key.values()
                if led_id in lease.led_ids
            ]
        matches = [lease for lease in matches if lease._is_active]
        if len(matches) != 1:
            raise VsmdMouthLedStateError(
                "LED ID {0} has no unique active timer lease".format(led_id)
            )
        return matches[0].timer_address

    def _mark_released(self, lease):
        # type: (AppManagerVsmdLedLockLease) -> None
        with self._state_lock:
            current = self._leases_by_local_key.get(lease._local_key)
            if current is lease:
                del self._leases_by_local_key[lease._local_key]
                self._reserved_led_ids.difference_update(lease.led_ids)


class AppManagerLeaseInterpolationTimer(VsmdInterpolationTimer):
    """Write duration to the timer address owned by the active lock lease."""

    def __init__(
        self, memory, led_lock, master_control_period_us=None
    ):
        # type: (VsmdTypedMemory, AppManagerVsmdLedLock, typing.Optional[int]) -> None
        if not isinstance(memory, VsmdTypedMemory):
            raise TypeError("memory must be VsmdTypedMemory")
        if not isinstance(led_lock, AppManagerVsmdLedLock):
            raise TypeError("led_lock must be AppManagerVsmdLedLock")
        self._memory = memory
        self._led_lock = led_lock
        self._tick_converter = VsmdControlTickConverter(
            memory, master_control_period_us
        )

    def set_duration(self, led_id, duration_ms):
        # type: (int, int) -> None
        _validate_duration(duration_ms)
        timer_address = self._led_lock.timer_address_for(led_id)
        timer_ticks = self._tick_converter.convert(duration_ms)
        self._memory.write_u16(timer_address, timer_ticks)
