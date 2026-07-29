"""Safety tests for the explicit live mouth-LED probe using Fakes only."""

import inspect
import json
import struct

import pytest

from robot_controller import mock_server
from robot_controller.hardware.vsmd import (
    app_manager_mouth_led_probe as module,
)
from robot_controller.hardware.vsmd.app_manager_codec import (
    APP_MANAGER_RESPONSE_OK,
    INTERP_CONVERT_COMMAND,
    INTERP_LOCK_COMMAND,
    INTERP_UNLOCK_COMMAND,
    JAVA_SHORT_SERIALIZATION_PREFIX,
    SERIALIZED_NG,
    SERIALIZED_NULL,
    SERIALIZED_OK,
)
from robot_controller.hardware.vsmd.app_manager_lock import (
    AppManagerLedLock,
    LEASE_RELEASED,
    LEASE_RELEASE_FAILED,
    LEASE_RELEASE_OUTCOME_UNKNOWN,
)
from robot_controller.hardware.vsmd.app_manager_vsmd_lock import (
    AppManagerVsmdLedLock,
)
from robot_controller.hardware.vsmd.errors import (
    AppManagerOutcomeUnknownError,
    AppManagerUnlockError,
    VsmdMouthLedCleanupError,
    VsmdMouthLedStateError,
)
from robot_controller.hardware.vsmd.memory import VsmdMemoryAccess
from robot_controller.hardware.vsmd.mouth_led import UnavailableVsmdLedLock
from robot_controller.hardware.vsmd.sota_memory_map import (
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_OUTPUT_ADDRESS,
    SOTA_MOUTH_TARGET_ADDRESS,
    SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


PRE_TRIGGER_POINTER = 500
LEASE_TIMER_ADDRESS = 502


def serialized_short(value):
    return JAVA_SHORT_SERIALIZATION_PREFIX + struct.pack(">h", value)


def command_from_request(request):
    return json.loads(request.decode("ascii"))["cmd"]


class FakeVsmdMemory(VsmdMemoryAccess):
    def __init__(self, selector=138, target=0):
        self.data = bytearray(b"\x00" * 65536)
        self.operations = []
        self.read_count = 0
        self.write_count = 0
        self.fail_read_number = None
        self.fail_write_numbers = set()
        self.set_u16(MOUTH_LED_SELECTOR_ADDRESS, selector)
        self.set_s16(SOTA_MOUTH_TARGET_ADDRESS, target)
        self.set_s16(SOTA_MOUTH_OUTPUT_ADDRESS, 0)
        self.set_u16(
            SOTA_MOUTH_TRIGGER_POINTER_ADDRESS, PRE_TRIGGER_POINTER
        )

    def read_bytes(self, address, size):
        self.read_count += 1
        self.operations.append(("READ", address, size))
        if self.fail_read_number == self.read_count:
            raise RuntimeError("fake VSMD read failed")
        return bytes(self.data[address:address + size])

    def write_bytes(self, address, payload):
        self.write_count += 1
        payload = bytes(payload)
        self.operations.append(("WRITE", address, payload))
        if self.write_count in self.fail_write_numbers:
            raise RuntimeError("fake VSMD write failed")
        self.data[address:address + len(payload)] = payload

    def set_u16(self, address, value):
        self.data[address:address + 2] = struct.pack("<H", value)

    def set_s16(self, address, value):
        self.data[address:address + 2] = struct.pack("<h", value)


class FakeAppManagerTransport(object):
    def __init__(
        self,
        memory,
        lock_response=SERIALIZED_OK,
        convert_response=None,
        unlock_response=SERIALIZED_OK,
        update_trigger_on_lock=True,
        after_unlock=None,
    ):
        self.memory = memory
        self.lock_response = lock_response
        self.convert_response = (
            serialized_short(LEASE_TIMER_ADDRESS)
            if convert_response is None
            else convert_response
        )
        self.unlock_response = unlock_response
        self.update_trigger_on_lock = update_trigger_on_lock
        self.after_unlock = after_unlock
        self.requests = []

    def request(self, request):
        request = bytes(request)
        self.requests.append(request)
        command = command_from_request(request)
        self.memory.operations.append(("APP", command))
        if command == INTERP_LOCK_COMMAND:
            if (
                self.lock_response == SERIALIZED_OK
                and self.update_trigger_on_lock
            ):
                self.memory.set_u16(
                    SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
                    LEASE_TIMER_ADDRESS,
                )
            return self._result(self.lock_response)
        if command == INTERP_CONVERT_COMMAND:
            return self._result(self.convert_response)
        if command == INTERP_UNLOCK_COMMAND:
            result = self._result(self.unlock_response)
            if result == SERIALIZED_OK:
                self.memory.set_u16(
                    SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
                    PRE_TRIGGER_POINTER,
                )
                if self.after_unlock is not None:
                    self.after_unlock(self.memory)
            return result
        raise AssertionError("unexpected AppManager command")

    @staticmethod
    def _result(value):
        if isinstance(value, BaseException):
            raise value
        return value


class FakeVsmdTransport(object):
    def __init__(self, calls=None, **kwargs):
        self.calls = calls
        self.kwargs = kwargs
        self.enter_count = 0
        self.close_count = 0
        if calls is not None:
            calls.append(kwargs)

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.close_count += 1
        return False


def make_probe(
    selector=138,
    target=0,
    lock_response=SERIALIZED_OK,
    convert_response=None,
    unlock_response=SERIALIZED_OK,
    update_trigger_on_lock=True,
    after_unlock=None,
    sleep_function=None,
):
    raw_memory = FakeVsmdMemory(selector=selector, target=target)
    app_transport = FakeAppManagerTransport(
        raw_memory,
        lock_response=lock_response,
        convert_response=convert_response,
        unlock_response=unlock_response,
        update_trigger_on_lock=update_trigger_on_lock,
        after_unlock=after_unlock,
    )
    app_lock = AppManagerLedLock(
        transport=app_transport,
        key_factory=lambda: "probe-test-key",
    )
    adapter = AppManagerVsmdLedLock(app_lock)
    sleeps = []
    if sleep_function is None:
        sleep_function = sleeps.append
    probe = module.AppManagerMouthLedLiveProbe(
        VsmdTypedMemory(raw_memory),
        adapter,
        level=16,
        duration_ms=200,
        sleep_function=sleep_function,
    )
    return probe, raw_memory, app_transport, sleeps


def commands(transport):
    return [command_from_request(request) for request in transport.requests]


def writes(memory):
    return [
        operation for operation in memory.operations
        if operation[0] == "WRITE"
    ]


def test_confirm_flag_absent_creates_no_transport_or_memory(capsys):
    calls = []

    def fail_factory(**unused_kwargs):
        calls.append("transport")
        raise AssertionError("factory must not be called")

    def fail_memory(unused_transport):
        calls.append("memory")
        raise AssertionError("memory must not be created")

    status = module.main(
        [],
        vsmd_transport_factory=fail_factory,
        app_manager_transport_factory=fail_factory,
        memory_factory=fail_memory,
    )
    assert status != 0
    assert calls == []
    assert "live_write=false" in capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments",
    [
        ["--led-id", "13"],
        ["--led-id", "15"],
        ["--level", "0"],
        ["--level", "17"],
        ["--duration-ms", "49"],
        ["--duration-ms", "201"],
    ],
)
def test_cli_rejects_values_outside_hard_live_limits(arguments):
    with pytest.raises(SystemExit):
        module.create_argument_parser().parse_args(arguments)


def test_cli_accepts_minimum_live_level_and_duration():
    arguments = module.create_argument_parser().parse_args(
        ["--level", "1", "--duration-ms", "50"]
    )
    assert arguments.level == 1
    assert arguments.duration_ms == 50


def test_preflight_reads_all_fields_before_lock_and_normal_flow_is_ordered():
    probe, memory, transport, sleeps = make_probe()
    result = probe.run()
    assert result.preflight == module.ProbeSnapshot(
        138, 0, 0, PRE_TRIGGER_POINTER
    )
    assert result.locked_trigger_pointer == LEASE_TIMER_ADDRESS
    assert result.postflight.selector == 138
    assert result.postflight.target == 0
    assert result.postflight.trigger_pointer == PRE_TRIGGER_POINTER
    assert sleeps == [0.2]
    assert commands(transport) == [
        INTERP_LOCK_COMMAND,
        INTERP_CONVERT_COMMAND,
        INTERP_UNLOCK_COMMAND,
    ]
    assert memory.operations[:4] == [
        ("READ", MOUTH_LED_SELECTOR_ADDRESS, 2),
        ("READ", SOTA_MOUTH_TARGET_ADDRESS, 2),
        ("READ", SOTA_MOUTH_OUTPUT_ADDRESS, 2),
        ("READ", SOTA_MOUTH_TRIGGER_POINTER_ADDRESS, 2),
    ]
    assert memory.operations[4:7] == [
        ("APP", INTERP_LOCK_COMMAND),
        ("APP", INTERP_CONVERT_COMMAND),
        ("READ", SOTA_MOUTH_TRIGGER_POINTER_ADDRESS, 2),
    ]
    unlock_index = memory.operations.index(
        ("APP", INTERP_UNLOCK_COMMAND)
    )
    assert len(memory.operations[unlock_index + 1:]) == 4
    assert all(
        operation[0] == "READ"
        for operation in memory.operations[unlock_index + 1:]
    )


def test_real_controller_receives_one_bounded_level_and_timer_duration():
    probe, memory, transport, unused_sleeps = make_probe()
    result = probe.run()
    target_on = (
        "WRITE", SOTA_MOUTH_TARGET_ADDRESS, struct.pack("<h", 16)
    )
    timer_on = (
        "WRITE", result.timer_address, struct.pack("<H", 200)
    )
    assert writes(memory).count(target_on) == 1
    assert writes(memory).count(timer_on) == 1
    assert commands(transport).count(INTERP_LOCK_COMMAND) == 1
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_probe_instance_cannot_pulse_or_lock_twice():
    probe, unused_memory, transport, unused_sleeps = make_probe()
    probe.run()
    request_count = len(transport.requests)
    with pytest.raises(VsmdMouthLedStateError, match="only once"):
        probe.run()
    assert len(transport.requests) == request_count
    assert commands(transport).count(INTERP_LOCK_COMMAND) == 1


@pytest.mark.parametrize("selector,target", [(3228, 0), (138, 1)])
def test_unsafe_preflight_does_not_lock_or_write(selector, target):
    probe, memory, transport, unused_sleeps = make_probe(
        selector=selector, target=target
    )
    with pytest.raises(VsmdMouthLedStateError):
        probe.run()
    assert transport.requests == []
    assert writes(memory) == []


def test_preflight_read_failure_does_not_lock_or_write():
    probe, memory, transport, unused_sleeps = make_probe()
    memory.fail_read_number = 3
    with pytest.raises(RuntimeError, match="read"):
        probe.run()
    assert transport.requests == []
    assert writes(memory) == []


@pytest.mark.parametrize(
    "lock_response,convert_response,expected_commands",
    [
        (SERIALIZED_NG, None, [INTERP_LOCK_COMMAND]),
        (
            SERIALIZED_OK,
            SERIALIZED_NULL,
            [
                INTERP_LOCK_COMMAND,
                INTERP_CONVERT_COMMAND,
                INTERP_UNLOCK_COMMAND,
            ],
        ),
        (
            SERIALIZED_OK,
            serialized_short(501),
            [
                INTERP_LOCK_COMMAND,
                INTERP_CONVERT_COMMAND,
                INTERP_UNLOCK_COMMAND,
            ],
        ),
    ],
)
def test_lock_or_convert_failure_performs_no_python_vsmd_write(
    lock_response, convert_response, expected_commands
):
    probe, memory, transport, unused_sleeps = make_probe(
        lock_response=lock_response,
        convert_response=convert_response,
    )
    with pytest.raises(BaseException):
        probe.run()
    assert writes(memory) == []
    assert commands(transport) == expected_commands


def test_locked_trigger_mismatch_writes_nothing_and_unlocks_once():
    probe, memory, transport, unused_sleeps = make_probe(
        update_trigger_on_lock=False
    )
    with pytest.raises(VsmdMouthLedStateError, match="TriggerPointer"):
        probe.run()
    assert writes(memory) == []
    assert commands(transport) == [
        INTERP_LOCK_COMMAND,
        INTERP_CONVERT_COMMAND,
        INTERP_UNLOCK_COMMAND,
    ]


def test_locked_trigger_read_failure_unlocks_once_without_write():
    probe, memory, transport, unused_sleeps = make_probe()
    memory.fail_read_number = 5
    with pytest.raises(RuntimeError, match="read"):
        probe.run()
    assert writes(memory) == []
    assert commands(transport) == [
        INTERP_LOCK_COMMAND,
        INTERP_CONVERT_COMMAND,
        INTERP_UNLOCK_COMMAND,
    ]


def test_vsmd_write_failure_attempts_exactly_one_unlock():
    probe, memory, transport, unused_sleeps = make_probe()
    memory.fail_write_numbers.add(2)
    with pytest.raises(RuntimeError, match="write"):
        probe.run()
    assert commands(transport).count(INTERP_LOCK_COMMAND) == 1
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_cleanup_failure_attempts_exactly_one_unlock():
    probe, memory, transport, unused_sleeps = make_probe()
    memory.fail_write_numbers.add(4)
    with pytest.raises(RuntimeError, match="write"):
        probe.run()
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_operation_and_cleanup_failure_preserve_both_errors():
    def fail_sleep(unused_seconds):
        raise RuntimeError("fake pulse failure")

    probe, memory, transport, unused_sleeps = make_probe(
        sleep_function=fail_sleep
    )
    memory.fail_write_numbers.add(4)
    with pytest.raises(VsmdMouthLedCleanupError) as caught:
        probe.run()
    assert isinstance(caught.value.operation_error, RuntimeError)
    assert isinstance(caught.value.cleanup_error, RuntimeError)
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


@pytest.mark.parametrize(
    "unlock_response,expected_error,expected_state",
    [
        (
            SERIALIZED_NG,
            AppManagerUnlockError,
            LEASE_RELEASE_FAILED,
        ),
        (
            AppManagerOutcomeUnknownError("fake unknown"),
            AppManagerOutcomeUnknownError,
            LEASE_RELEASE_OUTCOME_UNKNOWN,
        ),
    ],
)
def test_release_failure_is_fail_closed_without_retry(
    unlock_response, expected_error, expected_state
):
    probe, memory, transport, unused_sleeps = make_probe(
        unlock_response=unlock_response
    )
    with pytest.raises(expected_error):
        probe.run()
    assert probe.lease.state == expected_state
    assert not probe.lease.is_released
    assert commands(transport).count(INTERP_LOCK_COMMAND) == 1
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1
    assert len(transport.requests) == 3
    assert probe.postflight is None
    assert memory.read_count == 7


class InconsistentLease(object):
    def __init__(self, state, is_released, release_result):
        self.state = state
        self.is_released = is_released
        self.release_result = release_result


@pytest.mark.parametrize(
    "lease",
    [
        InconsistentLease(
            LEASE_RELEASED, False, APP_MANAGER_RESPONSE_OK
        ),
        InconsistentLease(LEASE_RELEASED, True, None),
        InconsistentLease(LEASE_RELEASED, True, "unexpected"),
        InconsistentLease(
            LEASE_RELEASE_FAILED, False, APP_MANAGER_RESPONSE_OK
        ),
        InconsistentLease(
            LEASE_RELEASE_OUTCOME_UNKNOWN,
            False,
            APP_MANAGER_RESPONSE_OK,
        ),
    ],
)
def test_only_explicit_release_success_state_is_accepted(lease):
    with pytest.raises(VsmdMouthLedStateError):
        module._validate_release_success(lease)


def test_explicit_release_success_state_is_accepted():
    lease = InconsistentLease(
        LEASE_RELEASED, True, APP_MANAGER_RESPONSE_OK
    )
    module._validate_release_success(lease)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda memory: memory.set_u16(MOUTH_LED_SELECTOR_ADDRESS, 1),
        lambda memory: memory.set_s16(SOTA_MOUTH_TARGET_ADDRESS, 1),
        lambda memory: memory.set_u16(
            SOTA_MOUTH_TRIGGER_POINTER_ADDRESS, 496
        ),
    ],
)
def test_postflight_mismatch_is_failure(mutation):
    probe, unused_memory, transport, unused_sleeps = make_probe(
        after_unlock=mutation
    )
    with pytest.raises(VsmdMouthLedStateError, match="postflight"):
        probe.run()
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_postflight_read_failure_is_not_success():
    probe, memory, transport, unused_sleeps = make_probe()
    memory.fail_read_number = 8
    with pytest.raises(RuntimeError, match="read"):
        probe.run()
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_postflight_output_difference_is_display_only():
    def change_output(memory):
        memory.set_s16(SOTA_MOUTH_OUTPUT_ADDRESS, 7)

    probe, unused_memory, unused_transport, unused_sleeps = make_probe(
        after_unlock=change_output
    )
    result = probe.run()
    assert result.postflight.output == 7


def test_confirmed_cli_uses_supplied_endpoints_and_reports_success(capsys):
    memory = FakeVsmdMemory()
    app_transport = FakeAppManagerTransport(memory)
    vsmd_calls = []
    app_calls = []

    def vsmd_factory(**kwargs):
        return FakeVsmdTransport(vsmd_calls, **kwargs)

    def app_factory(**kwargs):
        app_calls.append(kwargs)
        return app_transport

    status = module.main(
        [
            "--app-manager-host", "127.0.0.2",
            "--app-manager-port", "16495",
            "--app-manager-timeout", "1.5",
            "--vsmd-host", "127.0.0.3",
            "--vsmd-port", "16498",
            "--vsmd-connect-timeout", "1.1",
            "--vsmd-read-timeout", "1.2",
            "--vsmd-write-timeout", "1.3",
            "--led-id", "14",
            "--level", "16",
            "--duration-ms", "200",
            "--confirm-live-write",
        ],
        vsmd_transport_factory=vsmd_factory,
        app_manager_transport_factory=app_factory,
        memory_factory=lambda unused_transport: VsmdTypedMemory(memory),
        sleep_function=lambda unused_seconds: None,
    )
    output = capsys.readouterr().out
    assert status == 0
    assert "result=success" in output
    assert "lease_state=released" in output
    assert "release_result=OK" in output
    assert "post_output=0" in output
    assert vsmd_calls[0]["host"] == "127.0.0.3"
    assert vsmd_calls[0]["port"] == 16498
    assert app_calls == [
        {"host": "127.0.0.2", "port": 16495, "timeout": 1.5}
    ]


@pytest.mark.parametrize(
    "unlock_response",
    [
        SERIALIZED_NG,
        AppManagerOutcomeUnknownError("fake unknown"),
    ],
)
def test_cli_reports_failure_for_non_successful_release(
    unlock_response, capsys
):
    memory = FakeVsmdMemory()
    app_transport = FakeAppManagerTransport(
        memory, unlock_response=unlock_response
    )
    status = module.main(
        ["--confirm-live-write"],
        vsmd_transport_factory=lambda **kwargs: FakeVsmdTransport(
            **kwargs
        ),
        app_manager_transport_factory=lambda **unused_kwargs: app_transport,
        memory_factory=lambda unused_transport: VsmdTypedMemory(memory),
        sleep_function=lambda unused_seconds: None,
    )
    captured = capsys.readouterr()
    assert status != 0
    assert "result=failure" in captured.err
    assert commands(app_transport).count(INTERP_LOCK_COMMAND) == 1
    assert commands(app_transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_probe_does_not_force_adapter_reservations_or_enter_composition():
    source = inspect.getsource(module)
    assert "self._memory.write" not in source
    assert "_reserved_led_ids" not in source
    assert "_leases_by_local_key" not in source
    assert "_mark_released" not in source
    assert "app_manager_mouth_led_probe" not in inspect.getsource(
        mock_server
    )
    assert isinstance(UnavailableVsmdLedLock(), UnavailableVsmdLedLock)
