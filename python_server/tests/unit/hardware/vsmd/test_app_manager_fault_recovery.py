"""Fake-only Phase 7 AppManager mouth-LED fault recovery tests."""

import json
import struct

import pytest

from robot_controller.hardware.vsmd.app_manager_codec import (
    INTERP_CONVERT_COMMAND,
    INTERP_LOCK_COMMAND,
    INTERP_UNLOCK_COMMAND,
    JAVA_SHORT_SERIALIZATION_PREFIX,
    SERIALIZED_NG,
    SERIALIZED_OK,
)
from robot_controller.hardware.vsmd.app_manager_lock import AppManagerLedLock
from robot_controller.hardware.vsmd.app_manager_vsmd_lock import (
    AppManagerVsmdLedLock,
)
from robot_controller.hardware.vsmd.errors import (
    AppManagerLockRejectedError,
    VsmdMouthLedStateError,
)


def _serialized_short(value):
    return JAVA_SHORT_SERIALIZATION_PREFIX + struct.pack(">h", value)


def _decode_request(request):
    outer = json.loads(request.decode("ascii"))
    return outer["cmd"], json.loads(outer["subjson"])


class FakeAppManagerSlotAllocator(object):
    """Observed timer-slot behavior shared by independent fake clients."""

    def __init__(self, lock_results=None):
        self._ids_by_key = {}
        self._timer_by_key = {}
        self._next_timer = 502
        self._lock_results = (
            {} if lock_results is None else dict(lock_results)
        )

    def exchange(self, request):
        command, payload = _decode_request(request)
        key = payload["key"]
        if command == INTERP_LOCK_COMMAND:
            ids = tuple(payload["ids"])
            configured = self._lock_results.get(key)
            if configured is not None:
                return configured
            self._ids_by_key[key] = ids
            self._timer_by_key[key] = self._next_timer
            self._next_timer += 2
            return SERIALIZED_OK
        if command == INTERP_CONVERT_COMMAND:
            timer = self._timer_by_key.get(key)
            if timer is None:
                return SERIALIZED_NG
            return _serialized_short(timer)
        if command == INTERP_UNLOCK_COMMAND:
            ids = tuple(payload["ids"])
            if self._ids_by_key.get(key) != ids:
                return SERIALIZED_NG
            del self._ids_by_key[key]
            del self._timer_by_key[key]
            return SERIALIZED_OK
        raise AssertionError("unexpected fake AppManager command")


class FakeSlotTransport(object):
    def __init__(self, allocator):
        self._allocator = allocator
        self.requests = []

    def request(self, request):
        request = bytes(request)
        self.requests.append(request)
        return self._allocator.exchange(request)


def _make_adapter(allocator, key):
    transport = FakeSlotTransport(allocator)
    lock = AppManagerLedLock(
        transport=transport, key_factory=lambda: key
    )
    return AppManagerVsmdLedLock(lock), transport


def _commands(transport):
    return [
        _decode_request(request)[0] for request in transport.requests
    ]


def test_same_adapter_overlap_fails_before_second_app_manager_call():
    allocator = FakeAppManagerSlotAllocator()
    adapter, transport = _make_adapter(allocator, "same-process-key")
    lease = adapter.acquire("first-local", [14])
    request_count = len(transport.requests)

    with pytest.raises(VsmdMouthLedStateError):
        adapter.acquire("second-local", [14])

    assert len(transport.requests) == request_count
    assert _commands(transport) == [
        INTERP_LOCK_COMMAND,
        INTERP_CONVERT_COMMAND,
    ]
    lease.release()


def test_independent_clients_receive_distinct_slots_for_same_led():
    allocator = FakeAppManagerSlotAllocator()
    first, first_transport = _make_adapter(allocator, "client-one-key")
    second, second_transport = _make_adapter(allocator, "client-two-key")
    first_lease = first.acquire("first-local", [14])
    second_lease = second.acquire("second-local", [14])

    assert first_lease.timer_address != second_lease.timer_address
    second_lease.release()
    first_lease.release()

    assert _commands(first_transport) == [
        INTERP_LOCK_COMMAND,
        INTERP_CONVERT_COMMAND,
        INTERP_UNLOCK_COMMAND,
    ]
    assert _commands(second_transport) == [
        INTERP_LOCK_COMMAND,
        INTERP_CONVERT_COMMAND,
        INTERP_UNLOCK_COMMAND,
    ]


def test_explicit_lock_ng_preserves_typed_rejection():
    allocator = FakeAppManagerSlotAllocator(
        {"client-two-key": SERIALIZED_NG}
    )
    first, first_transport = _make_adapter(
        allocator, "client-one-key"
    )
    second, second_transport = _make_adapter(
        allocator, "client-two-key"
    )
    first_lease = first.acquire("first-local", [14])

    with pytest.raises(AppManagerLockRejectedError):
        second.acquire("second-local", [14])

    assert _commands(second_transport) == [INTERP_LOCK_COMMAND]
    assert first_lease.state == "active"
    first_lease.release()
    assert _commands(first_transport)[-1] == INTERP_UNLOCK_COMMAND


def test_release_allows_new_client_reacquire_with_distinct_key_and_timer():
    allocator = FakeAppManagerSlotAllocator()
    first, first_transport = _make_adapter(allocator, "client-one-key")
    second, second_transport = _make_adapter(allocator, "client-two-key")

    first_lease = first.acquire("first-local", [14])
    first_lease.release()
    second_lease = second.acquire("second-local", [14])
    second_lease.release()

    assert _commands(first_transport) == [
        INTERP_LOCK_COMMAND,
        INTERP_CONVERT_COMMAND,
        INTERP_UNLOCK_COMMAND,
    ]
    assert _commands(second_transport) == [
        INTERP_LOCK_COMMAND,
        INTERP_CONVERT_COMMAND,
        INTERP_UNLOCK_COMMAND,
    ]
    assert first_lease.key != second_lease.key
    assert first_lease.timer_address != second_lease.timer_address


def test_release_is_idempotent_through_shared_fake_arbiter():
    allocator = FakeAppManagerSlotAllocator()
    adapter, transport = _make_adapter(allocator, "idempotent-key")
    lease = adapter.acquire("local", [14])
    lease.release()
    lease.release()
    assert _commands(transport).count(INTERP_UNLOCK_COMMAND) == 1
