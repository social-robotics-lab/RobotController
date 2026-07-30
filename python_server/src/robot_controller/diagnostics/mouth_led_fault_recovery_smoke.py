"""Fake-only Phase 7 mouth LED fault-recovery smoke diagnostic."""

import json
import struct
import sys
import typing

from robot_controller.hardware.vsmd.app_manager_codec import (
    INTERP_CONVERT_COMMAND,
    INTERP_LOCK_COMMAND,
    INTERP_UNLOCK_COMMAND,
    JAVA_SHORT_SERIALIZATION_PREFIX,
    SERIALIZED_NG,
    SERIALIZED_NULL,
    SERIALIZED_OK,
)
from robot_controller.hardware.vsmd.app_manager_lock import AppManagerLedLock
from robot_controller.hardware.vsmd.app_manager_mouth_led_pulse import (
    SotaMouthLedPulseOperation,
)
from robot_controller.hardware.vsmd.app_manager_vsmd_lock import (
    AppManagerVsmdLedLock,
)
from robot_controller.hardware.vsmd.errors import (
    AppManagerAcquireCleanupError,
    AppManagerLockRejectedError,
    AppManagerTimerAddressError,
    AppManagerUnlockError,
    VsmdMouthLedStateError,
)
from robot_controller.hardware.vsmd.memory import VsmdMemoryAccess
from robot_controller.hardware.vsmd.sota_memory_map import (
    MASTER_CONTROL_PERIOD_ADDRESS,
    MOUTH_LED_AUDIO_SOURCE_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_OUTPUT_ADDRESS,
    SOTA_MOUTH_REMAINING_TIME_ADDRESS,
    SOTA_MOUTH_TARGET_ADDRESS,
    SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


LED_ID = 14
PREVIOUS_TIMER_ADDRESS = 500
LEASE_TIMER_ADDRESS = 502


def _serialized_short(value):
    # type: (int) -> bytes
    return JAVA_SHORT_SERIALIZATION_PREFIX + struct.pack(">h", value)


def _request_parts(request):
    # type: (bytes) -> typing.Tuple[str, typing.Dict[str, typing.Any]]
    outer = json.loads(request.decode("ascii"))
    return outer["cmd"], json.loads(outer["subjson"])


class _FakeAppManagerArbiter(object):
    """In-memory cross-client lock arbitration with no I/O."""

    def __init__(self):
        self._ids_by_key = {}
        self._key_by_id = {}
        self._timer_by_key = {}
        self._next_timer = LEASE_TIMER_ADDRESS

    def exchange(self, request):
        # type: (bytes) -> bytes
        command, payload = _request_parts(request)
        key = payload["key"]
        if command == INTERP_LOCK_COMMAND:
            led_ids = tuple(payload["ids"])
            if any(led_id in self._key_by_id for led_id in led_ids):
                return SERIALIZED_NG
            self._ids_by_key[key] = led_ids
            for led_id in led_ids:
                self._key_by_id[led_id] = key
            self._timer_by_key[key] = self._next_timer
            self._next_timer += 2
            return SERIALIZED_OK
        if command == INTERP_CONVERT_COMMAND:
            timer_address = self._timer_by_key.get(key)
            if timer_address is None:
                return SERIALIZED_NG
            return _serialized_short(timer_address)
        if command == INTERP_UNLOCK_COMMAND:
            led_ids = tuple(payload["ids"])
            if self._ids_by_key.get(key) != led_ids:
                return SERIALIZED_NG
            del self._ids_by_key[key]
            del self._timer_by_key[key]
            for led_id in led_ids:
                del self._key_by_id[led_id]
            return SERIALIZED_OK
        raise AssertionError("unexpected fake AppManager command")


class _FakeArbitratingTransport(object):
    def __init__(self, arbiter):
        self._arbiter = arbiter
        self.requests = []

    def request(self, request):
        # type: (bytes) -> bytes
        request = bytes(request)
        self.requests.append(request)
        return self._arbiter.exchange(request)


class _FakeScriptedTransport(object):
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def request(self, request):
        # type: (bytes) -> bytes
        self.requests.append(bytes(request))
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class _FakePulseMemory(VsmdMemoryAccess):
    """Minimal deterministic memory model used only by this diagnostic."""

    def __init__(self):
        self.data = bytearray(b"\x00" * 65536)
        self.read_count = 0
        self.write_count = 0
        self._set_u16(
            MOUTH_LED_SELECTOR_ADDRESS, MOUTH_LED_AUDIO_SOURCE_ADDRESS
        )
        self._set_s16(SOTA_MOUTH_TARGET_ADDRESS, 0)
        self._set_s16(SOTA_MOUTH_OUTPUT_ADDRESS, 0)
        self._set_u16(SOTA_MOUTH_REMAINING_TIME_ADDRESS, 0)
        self._set_u16(
            SOTA_MOUTH_TRIGGER_POINTER_ADDRESS, PREVIOUS_TIMER_ADDRESS
        )
        self._set_u32(MASTER_CONTROL_PERIOD_ADDRESS, 16666)

    def read_bytes(self, address, size):
        # type: (int, int) -> bytes
        self.read_count += 1
        return bytes(self.data[address:address + size])

    def write_bytes(self, address, payload):
        # type: (int, bytes) -> None
        self.write_count += 1
        payload = bytes(payload)
        self.data[address:address + len(payload)] = payload
        if address == LEASE_TIMER_ADDRESS and payload != b"\x00\x00":
            target = struct.unpack(
                "<h",
                bytes(
                    self.data[
                        SOTA_MOUTH_TARGET_ADDRESS:
                        SOTA_MOUTH_TARGET_ADDRESS + 2
                    ]
                ),
            )[0]
            self._set_s16(SOTA_MOUTH_OUTPUT_ADDRESS, target)
            self._set_u16(SOTA_MOUTH_REMAINING_TIME_ADDRESS, 0)

    def _set_u16(self, address, value):
        # type: (int, int) -> None
        self.data[address:address + 2] = struct.pack("<H", value)

    def _set_s16(self, address, value):
        # type: (int, int) -> None
        self.data[address:address + 2] = struct.pack("<h", value)

    def _set_u32(self, address, value):
        # type: (int, int) -> None
        self.data[address:address + 4] = struct.pack("<I", value)


class _FakePulseTransport(object):
    def __init__(self, memory):
        self._memory = memory
        self.requests = []

    def request(self, request):
        # type: (bytes) -> bytes
        request = bytes(request)
        self.requests.append(request)
        command, unused_payload = _request_parts(request)
        if command == INTERP_LOCK_COMMAND:
            self._memory._set_u16(
                SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
                LEASE_TIMER_ADDRESS,
            )
            return SERIALIZED_OK
        if command == INTERP_CONVERT_COMMAND:
            return _serialized_short(LEASE_TIMER_ADDRESS)
        if command == INTERP_UNLOCK_COMMAND:
            self._memory._set_u16(
                SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
                PREVIOUS_TIMER_ADDRESS,
            )
            return SERIALIZED_OK
        raise AssertionError("unexpected fake pulse command")


def _adapter(transport, key):
    # type: (typing.Any, str) -> AppManagerVsmdLedLock
    return AppManagerVsmdLedLock(
        AppManagerLedLock(
            transport=transport, key_factory=lambda: key
        )
    )


def _commands(transport):
    # type: (typing.Any) -> typing.List[str]
    return [_request_parts(request)[0] for request in transport.requests]


def _check_same_process_conflict():
    # type: () -> None
    transport = _FakeArbitratingTransport(_FakeAppManagerArbiter())
    adapter = _adapter(transport, "same-process-key")
    lease = adapter.acquire("first-local", [LED_ID])
    request_count = len(transport.requests)
    try:
        adapter.acquire("second-local", [LED_ID])
    except VsmdMouthLedStateError:
        pass
    else:
        raise AssertionError("same-process overlap was accepted")
    assert len(transport.requests) == request_count
    lease.release()


def _check_cross_client_conflict():
    # type: () -> None
    arbiter = _FakeAppManagerArbiter()
    first_transport = _FakeArbitratingTransport(arbiter)
    second_transport = _FakeArbitratingTransport(arbiter)
    first = _adapter(first_transport, "cross-client-one")
    second = _adapter(second_transport, "cross-client-two")
    first_lease = first.acquire("first-local", [LED_ID])
    try:
        second.acquire("second-local", [LED_ID])
    except AppManagerLockRejectedError:
        pass
    else:
        raise AssertionError("cross-client conflict was accepted")
    assert _commands(second_transport) == [INTERP_LOCK_COMMAND]
    assert first_lease.state == "active"
    first_lease.release()


def _check_release_reacquire():
    # type: () -> None
    arbiter = _FakeAppManagerArbiter()
    first_transport = _FakeArbitratingTransport(arbiter)
    second_transport = _FakeArbitratingTransport(arbiter)
    first = _adapter(first_transport, "release-key-one")
    second = _adapter(second_transport, "release-key-two")
    first_lease = first.acquire("first-local", [LED_ID])
    first_lease.release()
    second_lease = second.acquire("second-local", [LED_ID])
    second_lease.release()
    assert first_lease.key != second_lease.key
    assert first_lease.timer_address != second_lease.timer_address


def _check_idempotent_release():
    # type: () -> None
    transport = _FakeArbitratingTransport(_FakeAppManagerArbiter())
    lease = _adapter(
        transport, "idempotent-key"
    ).acquire("local", [LED_ID])
    lease.release()
    lease.release()
    assert _commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def _check_convert_failure_cleanup():
    # type: () -> None
    transport = _FakeScriptedTransport(
        [SERIALIZED_OK, SERIALIZED_NULL, SERIALIZED_OK]
    )
    lock = AppManagerLedLock(
        transport=transport, key_factory=lambda: "convert-failure-key"
    )
    try:
        lock.acquire_leds([LED_ID])
    except AppManagerTimerAddressError:
        pass
    else:
        raise AssertionError("convert failure was accepted")
    assert _commands(transport).count(INTERP_UNLOCK_COMMAND) == 1

    cleanup_transport = _FakeScriptedTransport(
        [SERIALIZED_OK, SERIALIZED_NULL, SERIALIZED_NG]
    )
    cleanup_lock = AppManagerLedLock(
        transport=cleanup_transport,
        key_factory=lambda: "cleanup-failure-key",
    )
    try:
        cleanup_lock.acquire_leds([LED_ID])
    except AppManagerAcquireCleanupError as error:
        assert isinstance(
            error.acquisition_error, AppManagerTimerAddressError
        )
        assert isinstance(error.cleanup_error, AppManagerUnlockError)
    else:
        raise AssertionError("primary and cleanup failures were lost")
    assert _commands(cleanup_transport).count(
        INTERP_UNLOCK_COMMAND
    ) == 1


def _check_interrupt_cleanup():
    # type: () -> None
    raw_memory = _FakePulseMemory()
    transport = _FakePulseTransport(raw_memory)
    adapter = _adapter(transport, "interrupt-key")
    sleep_count = [0]
    interrupt = KeyboardInterrupt("fake diagnostic interrupt")

    def interrupt_hold(unused_seconds):
        # type: (float) -> None
        sleep_count[0] += 1
        if sleep_count[0] == 2:
            raise interrupt

    operation = SotaMouthLedPulseOperation(
        VsmdTypedMemory(raw_memory),
        adapter,
        level=16,
        duration_ms=200,
        hold_ms=500,
        fall_ms=200,
        sleep_function=interrupt_hold,
        monotonic_function=lambda: 0.0,
    )
    try:
        operation.run()
    except KeyboardInterrupt as error:
        assert error is interrupt
    else:
        raise AssertionError("KeyboardInterrupt became success")
    assert _commands(transport).count(INTERP_UNLOCK_COMMAND) == 1
    assert operation.cleanup_completed


def main(output=None):
    # type: (typing.Any) -> int
    """Run deterministic Fake-only recovery checks without live endpoints."""
    if output is None:
        output = sys.stdout
    print("live_network=false", file=output)
    print("live_write=false", file=output)
    checks = (
        ("same_process_conflict", _check_same_process_conflict),
        ("cross_client_conflict", _check_cross_client_conflict),
        ("release_reacquire", _check_release_reacquire),
        ("idempotent_release", _check_idempotent_release),
        ("convert_failure_cleanup", _check_convert_failure_cleanup),
        ("interrupt_cleanup", _check_interrupt_cleanup),
    )
    try:
        for name, check in checks:
            check()
            print("{0}=pass".format(name), file=output)
    except BaseException as error:
        print("result=failure", file=output)
        print(
            "error_type={0}".format(type(error).__name__), file=output
        )
        return 1
    print("result=success", file=output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
