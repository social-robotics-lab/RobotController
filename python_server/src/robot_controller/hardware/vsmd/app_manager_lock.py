"""Lease-based SotaAppManager LED interpolation lock candidate."""

import threading
import typing
import uuid

from robot_controller.hardware.vsmd.app_manager_codec import (
    APP_MANAGER_RESPONSE_NG,
    APP_MANAGER_RESPONSE_OK,
    decode_response,
    encode_convert_request,
    encode_lock_request,
    encode_unlock_request,
    validate_led_ids,
)
from robot_controller.hardware.vsmd.app_manager_transport import (
    AppManagerTcpTransport,
)
from robot_controller.hardware.vsmd.errors import (
    AppManagerConnectionError,
    AppManagerLockRejectedError,
    AppManagerOutcomeUnknownError,
    AppManagerProtocolError,
    AppManagerTimeoutError,
    AppManagerTimerAddressError,
    AppManagerUnexpectedResponseError,
    AppManagerUnlockError,
    VsmdValidationError,
)


INTERP_TIMER_ADDRESS_BASE = 496
INTERP_TIMER_ADDRESS_LAST = 558
INTERP_TIMER_ADDRESS_STEP = 2
INTERP_TIMER_SLOT_COUNT = 32

LEASE_ACTIVE = "active"
LEASE_RELEASED = "released"
LEASE_RELEASE_FAILED = "release_failed"
LEASE_RELEASE_OUTCOME_UNKNOWN = "release_outcome_unknown"
LEASE_RELEASE_RESULT_FAILED = "FAILED"
LEASE_RELEASE_RESULT_UNKNOWN = "UNKNOWN"


def _default_key_factory():
    # type: () -> str
    return "python-led-{0}".format(uuid.uuid4().hex)


def validate_timer_address(address):
    # type: (int) -> int
    """Validate one of the 32 aligned interpolation timer slots."""
    if isinstance(address, bool) or not isinstance(address, int):
        raise AppManagerTimerAddressError(
            "timer address must be a signed Short integer"
        )
    if (
        address < INTERP_TIMER_ADDRESS_BASE
        or address > INTERP_TIMER_ADDRESS_LAST
        or (address - INTERP_TIMER_ADDRESS_BASE)
        % INTERP_TIMER_ADDRESS_STEP
        != 0
    ):
        raise AppManagerTimerAddressError(
            "timer address {0} is outside aligned range {1}..{2}".format(
                address,
                INTERP_TIMER_ADDRESS_BASE,
                INTERP_TIMER_ADDRESS_LAST,
            )
        )
    return address


class AppManagerLedLockLease(object):
    """Immutable lock identity plus a single-attempt release lifecycle."""

    def __init__(self, owner, key, led_ids, timer_address):
        # type: (AppManagerLedLock, str, typing.Tuple[int, ...], int) -> None
        self._owner = owner
        self._key = key
        self._led_ids = tuple(led_ids)
        self._timer_address = timer_address
        self._state = LEASE_ACTIVE
        self._release_result = None  # type: typing.Optional[str]
        self._release_error = None  # type: typing.Optional[BaseException]
        self._state_lock = threading.Lock()

    @property
    def key(self):
        # type: () -> str
        return self._key

    @property
    def led_ids(self):
        # type: () -> typing.Tuple[int, ...]
        return self._led_ids

    @property
    def timer_address(self):
        # type: () -> int
        return self._timer_address

    @property
    def state(self):
        # type: () -> str
        with self._state_lock:
            return self._state

    @property
    def is_released(self):
        # type: () -> bool
        with self._state_lock:
            return self._state == LEASE_RELEASED

    @property
    def release_result(self):
        # type: () -> typing.Optional[str]
        with self._state_lock:
            return self._release_result

    def release(self):
        # type: () -> None
        """Send at most one unlock request, retaining a failed outcome."""
        with self._state_lock:
            if self._state == LEASE_RELEASED:
                return
            if self._state != LEASE_ACTIVE:
                if self._release_error is not None:
                    raise self._release_error
                raise AppManagerUnlockError(
                    "lease release was already attempted"
                )
            try:
                self._owner._release_lease(self)
            except BaseException as error:
                self._release_error = error
                if isinstance(
                    error,
                    (
                        AppManagerOutcomeUnknownError,
                        AppManagerProtocolError,
                        AppManagerUnexpectedResponseError,
                    ),
                ):
                    self._state = LEASE_RELEASE_OUTCOME_UNKNOWN
                    self._release_result = LEASE_RELEASE_RESULT_UNKNOWN
                else:
                    self._state = LEASE_RELEASE_FAILED
                    self._release_result = LEASE_RELEASE_RESULT_FAILED
                raise
            self._state = LEASE_RELEASED
            self._release_result = APP_MANAGER_RESPONSE_OK

    def __enter__(self):
        # type: () -> AppManagerLedLockLease
        return self

    def __exit__(self, exception_type, exception, traceback):
        # type: (typing.Any, typing.Any, typing.Any) -> bool
        self.release()
        return False


class AppManagerLedLock(object):
    """Acquire independent LED lock leases through SotaAppManager.

    This candidate is intentionally not installed as the production
    ``VsmdLedLock``. Each call creates a fresh ASCII key and the returned lease
    owns the exact immutable IDs needed for its one unlock attempt.
    """

    def __init__(self, transport=None, key_factory=None):
        # type: (typing.Any, typing.Any) -> None
        if transport is None:
            transport = AppManagerTcpTransport()
        if not hasattr(transport, "request"):
            raise TypeError("transport must provide request(bytes)")
        if key_factory is None:
            key_factory = _default_key_factory
        if not callable(key_factory):
            raise TypeError("key_factory must be callable")
        self._transport = transport
        self._key_factory = key_factory

    def acquire_leds(self, led_ids):
        # type: (typing.Sequence[int]) -> AppManagerLedLockLease
        """Lock IDs, convert the unique key, and return an owned lease."""
        validated_ids = validate_led_ids(led_ids)
        key = self._key_factory()
        self._validate_generated_key(key)

        lock_response = self._exchange(
            encode_lock_request(key, validated_ids)
        )
        if lock_response == APP_MANAGER_RESPONSE_NG:
            raise AppManagerLockRejectedError(
                "AppManager rejected LED lock for key {0!r} IDs {1!r}".format(
                    key, validated_ids
                )
            )
        if lock_response != APP_MANAGER_RESPONSE_OK:
            raise AppManagerUnexpectedResponseError(
                "LED lock response must be serialized OK or NG"
            )

        try:
            converted = self._exchange(encode_convert_request(key))
            if converted is None:
                raise AppManagerTimerAddressError(
                    "AppManager did not register lock key {0!r}".format(key)
                )
            timer_address = validate_timer_address(converted)
        except BaseException as acquisition_error:
            self._cleanup_failed_acquire(
                key, validated_ids, acquisition_error
            )
            raise

        return AppManagerLedLockLease(
            self, key, validated_ids, timer_address
        )

    def _release_lease(self, lease):
        # type: (AppManagerLedLockLease) -> None
        response = self._exchange(
            encode_unlock_request(lease.key, lease.led_ids)
        )
        if response == APP_MANAGER_RESPONSE_OK:
            return
        if response == APP_MANAGER_RESPONSE_NG:
            raise AppManagerUnlockError(
                "AppManager rejected unlock for key {0!r} IDs {1!r}".format(
                    lease.key, lease.led_ids
                )
            )
        raise AppManagerUnlockError(
            "unlock response must be serialized OK"
        )

    def _cleanup_failed_acquire(self, key, led_ids, acquisition_error):
        # type: (str, typing.Tuple[int, ...], BaseException) -> None
        try:
            response = self._exchange(encode_unlock_request(key, led_ids))
            if response != APP_MANAGER_RESPONSE_OK:
                raise AppManagerUnlockError(
                    "best-effort unlock did not return OK"
                )
        except AppManagerOutcomeUnknownError as cleanup_error:
            raise AppManagerOutcomeUnknownError(
                "lock acquisition failed and cleanup outcome is unknown"
            ) from cleanup_error
        except AppManagerProtocolError as cleanup_error:
            raise AppManagerOutcomeUnknownError(
                "lock acquisition failed and cleanup response was malformed"
            ) from cleanup_error
        except AppManagerUnexpectedResponseError as cleanup_error:
            raise AppManagerOutcomeUnknownError(
                "lock acquisition failed and cleanup response was unexpected"
            ) from cleanup_error
        except (
            AppManagerConnectionError,
            AppManagerTimeoutError,
        ) as cleanup_error:
            raise AppManagerUnlockError(
                "lock acquisition failed before cleanup could be submitted"
            ) from cleanup_error
        except AppManagerUnlockError:
            raise

    def _exchange(self, request_json):
        # type: (bytes) -> typing.Union[str, int, None]
        return decode_response(self._transport.request(request_json))

    @staticmethod
    def _validate_generated_key(key):
        # type: (typing.Any) -> None
        if not isinstance(key, str) or not key:
            raise VsmdValidationError(
                "generated AppManager key must be a non-empty string"
            )
        try:
            key.encode("ascii")
        except UnicodeEncodeError as error:
            raise VsmdValidationError(
                "generated AppManager key must contain ASCII only"
            ) from error
