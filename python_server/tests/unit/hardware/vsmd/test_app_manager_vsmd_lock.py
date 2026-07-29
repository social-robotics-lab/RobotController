"""AppManager lease adaptation to the existing mouth-LED abstractions."""

import inspect
import json
import struct

import pytest

from robot_controller import mock_server
from robot_controller.hardware.vsmd.app_manager_codec import (
    JAVA_SHORT_SERIALIZATION_PREFIX,
    SERIALIZED_NG,
    SERIALIZED_NULL,
    SERIALIZED_OK,
)
from robot_controller.hardware.vsmd.app_manager_lock import (
    AppManagerLedLock,
    LEASE_RELEASE_FAILED,
    LEASE_RELEASE_OUTCOME_UNKNOWN,
)
from robot_controller.hardware.vsmd.app_manager_vsmd_lock import (
    AppManagerLeaseInterpolationTimer,
    AppManagerVsmdLedLock,
)
from robot_controller.hardware.vsmd.errors import (
    AppManagerLockRejectedError,
    AppManagerOutcomeUnknownError,
    AppManagerTimerAddressError,
    AppManagerUnlockError,
    VsmdMouthLedCleanupError,
    VsmdMouthLedStateError,
)
from robot_controller.hardware.vsmd.memory import VsmdMemoryAccess
from robot_controller.hardware.vsmd.mouth_led import (
    SotaMouthLedController,
    UnavailableVsmdLedLock,
    VsmdLedLock,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    MASTER_CONTROL_PERIOD_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_TARGET_ADDRESS,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


def serialized_short(value):
    return JAVA_SHORT_SERIALIZATION_PREFIX + struct.pack(">h", value)


class FakeAppManagerTransport(object):
    def __init__(self, responses, events):
        self.responses = list(responses)
        self.events = events
        self.requests = []

    def request(self, request_json):
        request = bytes(request_json)
        self.requests.append(request)
        if b"INTERP_LOCK" in request:
            self.events.append(("app_manager", "LOCK"))
        elif b"INTERP_CNV_KEY_2_ADDR" in request:
            self.events.append(("app_manager", "CONVERT"))
        elif b"INTERP_UNLOCK" in request:
            self.events.append(("app_manager", "UNLOCK"))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeVsmdMemory(VsmdMemoryAccess):
    def __init__(self, events, selector=138, target=0):
        self.events = events
        self.data = bytearray(b"\x00" * 65536)
        self.data[
            MOUTH_LED_SELECTOR_ADDRESS:MOUTH_LED_SELECTOR_ADDRESS + 2
        ] = struct.pack("<H", selector)
        self.data[
            SOTA_MOUTH_TARGET_ADDRESS:SOTA_MOUTH_TARGET_ADDRESS + 2
        ] = struct.pack("<h", target)
        self.data[
            MASTER_CONTROL_PERIOD_ADDRESS:
            MASTER_CONTROL_PERIOD_ADDRESS + 4
        ] = struct.pack("<I", 16666)
        self.writes = []
        self.fail_write_number = None
        self.fail_read_address = None

    def read_bytes(self, address, size):
        self.events.append(("vsmd_read", address, size))
        if address == self.fail_read_address:
            raise RuntimeError("fake period read failed")
        return bytes(self.data[address:address + size])

    def write_bytes(self, address, payload):
        payload = bytes(payload)
        self.events.append(("vsmd_write", address, payload))
        self.writes.append((address, payload))
        if self.fail_write_number == len(self.writes):
            raise RuntimeError("fake VSMD write failed")
        self.data[address:address + len(payload)] = payload


def make_components(responses, key_factory=None):
    events = []
    transport = FakeAppManagerTransport(responses, events)
    if key_factory is None:
        key_factory = lambda: "fixture-key"
    app_manager_lock = AppManagerLedLock(
        transport=transport,
        key_factory=key_factory,
    )
    adapter = AppManagerVsmdLedLock(app_manager_lock)
    raw_memory = FakeVsmdMemory(events)
    memory = VsmdTypedMemory(raw_memory)
    timer = AppManagerLeaseInterpolationTimer(memory, adapter)
    controller = SotaMouthLedController(
        memory,
        timer,
        led_lock=adapter,
        lock_key="mouth-controller",
    )
    return controller, adapter, raw_memory, transport, events


def commands(transport):
    result = []
    for request in transport.requests:
        if b"INTERP_LOCK" in request:
            result.append("LOCK")
        elif b"INTERP_CNV_KEY_2_ADDR" in request:
            result.append("CONVERT")
        elif b"INTERP_UNLOCK" in request:
            result.append("UNLOCK")
    return result


def request_key(request):
    outer = json.loads(request.decode("ascii"))
    return json.loads(outer["subjson"])["key"]


def test_adapter_satisfies_existing_vsmd_led_lock_contract():
    unused_controller, adapter, unused_memory, unused_transport, unused_events = (
        make_components([])
    )
    assert isinstance(adapter, VsmdLedLock)


def test_lock_convert_vsmd_operations_and_unlock_use_lease_timer():
    controller, unused_adapter, memory, transport, events = make_components(
        [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
    )
    controller.disable_voice_sync()
    controller.set_brightness(16, 200)
    controller.close()
    assert commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]
    first_write = next(
        index for index, event in enumerate(events) if event[0] == "vsmd_write"
    )
    assert events.index(("app_manager", "CONVERT")) < first_write
    assert events[-1] == ("app_manager", "UNLOCK")
    assert (502, struct.pack("<H", 12)) in memory.writes
    assert (502, struct.pack("<H", 200)) not in memory.writes


def test_lock_rejection_causes_no_vsmd_write():
    controller, unused_adapter, memory, transport, unused_events = (
        make_components([SERIALIZED_NG])
    )
    with pytest.raises(AppManagerLockRejectedError):
        controller.disable_voice_sync()
    assert memory.writes == []
    assert commands(transport) == ["LOCK"]


@pytest.mark.parametrize(
    "converted",
    [SERIALIZED_NULL, serialized_short(501)],
)
def test_null_or_invalid_timer_causes_cleanup_but_no_vsmd_write(converted):
    controller, unused_adapter, memory, transport, unused_events = (
        make_components([SERIALIZED_OK, converted, SERIALIZED_OK])
    )
    with pytest.raises(AppManagerTimerAddressError):
        controller.disable_voice_sync()
    assert memory.writes == []
    assert commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]


def test_vsmd_failure_releases_once():
    controller, unused_adapter, memory, transport, unused_events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
        )
    )
    memory.fail_write_number = 1
    with pytest.raises(RuntimeError, match="fake VSMD write failed"):
        controller.disable_voice_sync()
    assert commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]


def test_release_failure_is_explicit():
    controller, unused_adapter, unused_memory, transport, unused_events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_NG]
        )
    )
    controller.disable_voice_sync()
    with pytest.raises(AppManagerUnlockError):
        controller.close()
    assert commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]


def test_release_failure_does_not_hide_original_vsmd_error():
    controller, unused_adapter, memory, transport, unused_events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_NG]
        )
    )
    controller.disable_voice_sync()
    memory.fail_write_number = len(memory.writes) + 1
    with pytest.raises(VsmdMouthLedCleanupError) as caught:
        controller.close()
    assert isinstance(caught.value.operation_error, RuntimeError)
    assert isinstance(caught.value.cleanup_error, AppManagerUnlockError)
    assert commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]


def test_lease_double_release_does_not_send_second_unlock():
    unused_controller, adapter, unused_memory, transport, unused_events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
        )
    )
    lease = adapter.acquire("local-key", [14])
    lease.release()
    lease.release()
    assert commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]


def test_successful_release_allows_reacquire():
    keys = iter(("python-led-first", "python-led-second"))
    unused_controller, adapter, unused_memory, transport, unused_events = (
        make_components(
            [
                SERIALIZED_OK,
                serialized_short(502),
                SERIALIZED_OK,
                SERIALIZED_OK,
                serialized_short(504),
            ],
            key_factory=lambda: next(keys),
        )
    )
    first_lease = adapter.acquire("first-local-key", [14])
    first_lease.release()
    request_count = len(transport.requests)

    second_lease = adapter.acquire("second-local-key", [14])

    assert len(transport.requests) == request_count + 2
    assert commands(transport) == [
        "LOCK",
        "CONVERT",
        "UNLOCK",
        "LOCK",
        "CONVERT",
    ]
    assert request_key(transport.requests[0]) == "python-led-first"
    assert request_key(transport.requests[3]) == "python-led-second"
    assert second_lease.key != first_lease.key


def test_release_ng_blocks_reacquire_without_network():
    unused_controller, adapter, unused_memory, transport, unused_events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_NG]
        )
    )
    lease = adapter.acquire("first-local-key", [14])
    with pytest.raises(AppManagerUnlockError):
        lease.release()
    request_count = len(transport.requests)

    with pytest.raises(VsmdMouthLedStateError):
        adapter.acquire("second-local-key", [14])

    assert len(transport.requests) == request_count
    assert commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]
    assert lease.state == LEASE_RELEASE_FAILED
    assert lease.release_result == "FAILED"
    assert not lease.is_released


def test_release_outcome_unknown_blocks_reacquire_without_network():
    unknown = AppManagerOutcomeUnknownError("fake outcome unknown")
    unused_controller, adapter, unused_memory, transport, unused_events = (
        make_components([SERIALIZED_OK, serialized_short(502), unknown])
    )
    lease = adapter.acquire("first-local-key", [14])
    with pytest.raises(AppManagerOutcomeUnknownError):
        lease.release()
    request_count = len(transport.requests)

    with pytest.raises(VsmdMouthLedStateError):
        adapter.acquire("second-local-key", [14])

    assert len(transport.requests) == request_count
    assert commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]
    assert lease.state == LEASE_RELEASE_OUTCOME_UNKNOWN
    assert lease.release_result == "UNKNOWN"
    assert not lease.is_released


def test_double_release_after_failure_sends_no_second_unlock():
    unused_controller, adapter, unused_memory, transport, unused_events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_NG]
        )
    )
    lease = adapter.acquire("local-key", [14])
    with pytest.raises(AppManagerUnlockError):
        lease.release()
    request_count = len(transport.requests)

    with pytest.raises(AppManagerUnlockError):
        lease.release()

    assert len(transport.requests) == request_count
    assert commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]


def test_context_manager_releases_once():
    unused_controller, adapter, unused_memory, transport, unused_events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
        )
    )
    with adapter.acquire("local-key", [14]) as lease:
        assert lease.timer_address == 502
    assert lease.is_released
    assert commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]


def test_duplicate_led_lease_is_rejected_inside_one_adapter():
    unused_controller, adapter, unused_memory, transport, unused_events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
        )
    )
    lease = adapter.acquire("first", [14])
    request_count = len(transport.requests)
    with pytest.raises(VsmdMouthLedStateError):
        adapter.acquire("second", [14])
    assert len(transport.requests) == request_count
    lease.release()


def test_legacy_release_rejects_changed_ids_without_network():
    unused_controller, adapter, unused_memory, transport, unused_events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
        )
    )
    lease = adapter.acquire("local-key", [14])
    request_count = len(transport.requests)
    with pytest.raises(VsmdMouthLedStateError):
        adapter.release("local-key", [13])
    assert len(transport.requests) == request_count
    lease.release()


def test_timer_without_active_lease_fails_before_vsmd_write():
    unused_controller, adapter, memory, unused_transport, unused_events = (
        make_components([])
    )
    timer = AppManagerLeaseInterpolationTimer(
        VsmdTypedMemory(memory), adapter
    )
    with pytest.raises(VsmdMouthLedStateError):
        timer.set_duration(14, 200)
    assert memory.writes == []


def test_lease_timer_reads_period_then_writes_converted_ticks():
    unused_controller, adapter, memory, transport, events = make_components(
        [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
    )
    lease = adapter.acquire("timer-test", [14])
    timer = AppManagerLeaseInterpolationTimer(
        VsmdTypedMemory(memory), adapter
    )
    timer.set_duration(14, 200)
    assert ("vsmd_read", MASTER_CONTROL_PERIOD_ADDRESS, 4) in events
    assert memory.writes[-1] == (502, b"\x0c\x00")
    lease.release()


def test_lease_timer_zero_duration_does_not_read_period():
    unused_controller, adapter, memory, unused_transport, events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
        )
    )
    lease = adapter.acquire("timer-zero", [14])
    timer = AppManagerLeaseInterpolationTimer(
        VsmdTypedMemory(memory), adapter
    )
    timer.set_duration(14, 0)
    assert (
        "vsmd_read",
        MASTER_CONTROL_PERIOD_ADDRESS,
        4,
    ) not in events
    assert memory.writes[-1] == (502, b"\x00\x00")
    lease.release()


def test_lease_timer_period_read_failure_writes_nothing():
    unused_controller, adapter, memory, unused_transport, unused_events = (
        make_components(
            [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
        )
    )
    lease = adapter.acquire("timer-read-failure", [14])
    memory.fail_read_address = MASTER_CONTROL_PERIOD_ADDRESS
    timer = AppManagerLeaseInterpolationTimer(
        VsmdTypedMemory(memory), adapter
    )
    with pytest.raises(RuntimeError, match="period read"):
        timer.set_duration(14, 200)
    assert memory.writes == []
    lease.release()


def test_default_and_composition_remain_unavailable_and_mock_only():
    assert isinstance(UnavailableVsmdLedLock(), VsmdLedLock)
    composition_source = inspect.getsource(mock_server)
    assert "AppManagerVsmdLedLock" not in composition_source
