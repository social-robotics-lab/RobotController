"""Lease and cleanup behavior for the unused AppManager LED lock candidate."""

import struct

import pytest

from robot_controller.hardware.vsmd.app_manager_codec import (
    JAVA_SHORT_SERIALIZATION_PREFIX,
    SERIALIZED_NG,
    SERIALIZED_NULL,
    SERIALIZED_OK,
)
from robot_controller.hardware.vsmd.app_manager_lock import (
    LEASE_RELEASED,
    LEASE_RELEASE_FAILED,
    LEASE_RELEASE_OUTCOME_UNKNOWN,
    AppManagerLedLock,
    validate_timer_address,
)
from robot_controller.hardware.vsmd.errors import (
    AppManagerLockRejectedError,
    AppManagerOutcomeUnknownError,
    AppManagerProtocolError,
    AppManagerTimerAddressError,
    AppManagerUnlockError,
    VsmdValidationError,
)


def serialized_short(value):
    return JAVA_SHORT_SERIALIZATION_PREFIX + struct.pack(">h", value)


class FakeTransport(object):
    def __init__(self, results):
        self.results = list(results)
        self.requests = []

    def request(self, request_json):
        self.requests.append(bytes(request_json))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def make_lock(results, keys=None):
    transport = FakeTransport(results)
    key_values = iter(["fixture-key"] if keys is None else keys)
    lock = AppManagerLedLock(
        transport=transport, key_factory=lambda: next(key_values)
    )
    return lock, transport


def test_lock_ok_then_convert_short_returns_immutable_lease():
    lock, transport = make_lock([SERIALIZED_OK, serialized_short(502)])
    lease = lock.acquire_leds([14])
    assert lease.key == "fixture-key"
    assert lease.led_ids == (14,)
    assert lease.timer_address == 502
    assert lease.state == "active"
    assert b'"cmd":"INTERP_LOCK"' in transport.requests[0]
    assert b'"cmd":"INTERP_CNV_KEY_2_ADDR"' in transport.requests[1]
    with pytest.raises(AttributeError):
        lease.led_ids = (1,)


def test_generated_keys_are_ascii_and_unique_with_default_factory():
    transport = FakeTransport(
        [
            SERIALIZED_OK,
            serialized_short(496),
            SERIALIZED_OK,
            serialized_short(498),
        ]
    )
    lock = AppManagerLedLock(transport=transport)
    first = lock.acquire_leds([1])
    second = lock.acquire_leds([2])
    assert first.key != second.key
    assert first.key.startswith("python-led-")
    first.key.encode("ascii")
    second.key.encode("ascii")


def test_non_ascii_generated_key_is_rejected_before_network():
    lock, transport = make_lock([], keys=["bad-\N{SNOWMAN}"])
    with pytest.raises(VsmdValidationError):
        lock.acquire_leds([14])
    assert transport.requests == []


def test_lock_ng_is_rejected_without_convert_or_cleanup():
    lock, transport = make_lock([SERIALIZED_NG])
    with pytest.raises(AppManagerLockRejectedError):
        lock.acquire_leds([14])
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "convert_result",
    [SERIALIZED_NULL, serialized_short(494), serialized_short(501), serialized_short(560)],
)
def test_null_or_invalid_timer_address_performs_one_best_effort_unlock(
    convert_result,
):
    lock, transport = make_lock(
        [SERIALIZED_OK, convert_result, SERIALIZED_OK]
    )
    with pytest.raises(AppManagerTimerAddressError):
        lock.acquire_leds([14])
    assert len(transport.requests) == 3
    assert b'"cmd":"INTERP_UNLOCK"' in transport.requests[-1]
    assert b'\\"key\\":\\"fixture-key\\"' in transport.requests[-1]
    assert b'\\"ids\\":[14]' in transport.requests[-1]


def test_convert_timeout_performs_cleanup_then_preserves_unknown_outcome():
    lock, transport = make_lock(
        [
            SERIALIZED_OK,
            AppManagerOutcomeUnknownError("convert unknown"),
            SERIALIZED_OK,
        ]
    )
    with pytest.raises(AppManagerOutcomeUnknownError, match="convert unknown"):
        lock.acquire_leds([14])
    assert len(transport.requests) == 3


def test_failed_cleanup_with_unknown_result_raises_cleanup_unknown():
    lock, transport = make_lock(
        [
            SERIALIZED_OK,
            SERIALIZED_NULL,
            AppManagerOutcomeUnknownError("unlock unknown"),
        ]
    )
    with pytest.raises(
        AppManagerOutcomeUnknownError, match="cleanup outcome is unknown"
    ):
        lock.acquire_leds([14])
    assert len(transport.requests) == 3


def test_release_uses_owned_key_and_ids_and_succeeds_once():
    lock, transport = make_lock(
        [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
    )
    lease = lock.acquire_leds([14, 15])
    lease.release()
    lease.release()
    assert lease.state == LEASE_RELEASED
    assert lease.is_released
    assert lease.release_result == "OK"
    assert len(transport.requests) == 3
    assert b'\\"key\\":\\"fixture-key\\"' in transport.requests[-1]
    assert b'\\"ids\\":[14,15]' in transport.requests[-1]


def test_context_manager_releases_owned_lease():
    lock, transport = make_lock(
        [SERIALIZED_OK, serialized_short(496), SERIALIZED_OK]
    )
    with lock.acquire_leds([14]) as lease:
        assert lease.timer_address == 496
    assert lease.is_released
    assert len(transport.requests) == 3


def test_release_ng_is_failure_and_never_sends_second_unlock():
    lock, transport = make_lock(
        [SERIALIZED_OK, serialized_short(502), SERIALIZED_NG]
    )
    lease = lock.acquire_leds([14])
    with pytest.raises(AppManagerUnlockError):
        lease.release()
    assert lease.state == LEASE_RELEASE_FAILED
    assert not lease.is_released
    request_count = len(transport.requests)
    with pytest.raises(AppManagerUnlockError):
        lease.release()
    assert len(transport.requests) == request_count


@pytest.mark.parametrize("unlock_result", [SERIALIZED_NULL, serialized_short(502)])
def test_release_null_or_short_is_not_success(unlock_result):
    lock, transport = make_lock(
        [SERIALIZED_OK, serialized_short(502), unlock_result]
    )
    lease = lock.acquire_leds([14])
    with pytest.raises(AppManagerUnlockError):
        lease.release()
    assert lease.state == LEASE_RELEASE_FAILED
    assert not lease.is_released
    assert len(transport.requests) == 3


def test_release_timeout_is_unknown_and_never_sends_second_unlock():
    error = AppManagerOutcomeUnknownError("unlock timed out")
    lock, transport = make_lock(
        [SERIALIZED_OK, serialized_short(502), error]
    )
    lease = lock.acquire_leds([14])
    with pytest.raises(AppManagerOutcomeUnknownError):
        lease.release()
    assert lease.state == LEASE_RELEASE_OUTCOME_UNKNOWN
    assert lease.release_result == "UNKNOWN"
    request_count = len(transport.requests)
    with pytest.raises(AppManagerOutcomeUnknownError):
        lease.release()
    assert len(transport.requests) == request_count


def test_release_malformed_response_is_retained_as_unknown_without_retry():
    error = AppManagerProtocolError("malformed unlock response")
    lock, transport = make_lock(
        [SERIALIZED_OK, serialized_short(502), error]
    )
    lease = lock.acquire_leds([14])
    with pytest.raises(AppManagerProtocolError):
        lease.release()
    assert lease.state == LEASE_RELEASE_OUTCOME_UNKNOWN
    request_count = len(transport.requests)
    with pytest.raises(AppManagerProtocolError):
        lease.release()
    assert len(transport.requests) == request_count


@pytest.mark.parametrize("address", [496, 498, 502, 558])
def test_timer_address_range_and_alignment_accepts_valid_slots(address):
    assert validate_timer_address(address) == address


@pytest.mark.parametrize("address", [True, 495, 497, 559, 560])
def test_timer_address_range_and_alignment_rejects_invalid_values(address):
    with pytest.raises(AppManagerTimerAddressError):
        validate_timer_address(address)


@pytest.mark.parametrize("ids", [[], [True], [-1], [32], [14, 14]])
def test_invalid_ids_fail_before_any_live_or_fake_request(ids):
    lock, transport = make_lock([])
    with pytest.raises(VsmdValidationError):
        lock.acquire_leds(ids)
    assert transport.requests == []
