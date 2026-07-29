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
    MASTER_CONTROL_PERIOD_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_OUTPUT_ADDRESS,
    SOTA_MOUTH_REMAINING_TIME_ADDRESS,
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
    def __init__(
        self,
        selector=138,
        target=0,
        master_period=16666,
        rise_states=None,
        fall_states=None,
        initial_output=0,
    ):
        self.data = bytearray(b"\x00" * 65536)
        self.operations = []
        self.read_count = 0
        self.write_count = 0
        self.fail_read_number = None
        self.fail_write_numbers = set()
        self.timer_phase = 0
        self.active_state_index = 0
        self.rise_states = list(
            [(16, 0, LEASE_TIMER_ADDRESS, None)]
            if rise_states is None
            else rise_states
        )
        self.fall_states = list(
            [(0, 0, LEASE_TIMER_ADDRESS, None)]
            if fall_states is None
            else fall_states
        )
        self.set_u16(MOUTH_LED_SELECTOR_ADDRESS, selector)
        self.set_s16(SOTA_MOUTH_TARGET_ADDRESS, target)
        self.set_s16(SOTA_MOUTH_OUTPUT_ADDRESS, initial_output)
        self.set_u16(SOTA_MOUTH_REMAINING_TIME_ADDRESS, 0)
        self.set_u32(MASTER_CONTROL_PERIOD_ADDRESS, master_period)
        self.set_u16(
            SOTA_MOUTH_TRIGGER_POINTER_ADDRESS, PRE_TRIGGER_POINTER
        )

    def read_bytes(self, address, size):
        self.read_count += 1
        self.operations.append(("READ", address, size))
        if self.fail_read_number == self.read_count:
            raise RuntimeError("fake VSMD read failed")
        if (
            address == SOTA_MOUTH_OUTPUT_ADDRESS
            and self.timer_phase > 0
        ):
            active_states = (
                self.rise_states
                if self.timer_phase == 1
                else self.fall_states
            )
            if not active_states:
                return bytes(self.data[address:address + size])
            state_index = min(
                self.active_state_index, len(active_states) - 1
            )
            output, remaining, pointer, timer_value = (
                active_states[state_index]
            )
            self.active_state_index += 1
            self.set_s16(SOTA_MOUTH_OUTPUT_ADDRESS, output)
            self.set_u16(SOTA_MOUTH_REMAINING_TIME_ADDRESS, remaining)
            self.set_u16(SOTA_MOUTH_TRIGGER_POINTER_ADDRESS, pointer)
            if timer_value is not None:
                self.set_u16(LEASE_TIMER_ADDRESS, timer_value)
        return bytes(self.data[address:address + size])

    def write_bytes(self, address, payload):
        self.write_count += 1
        payload = bytes(payload)
        self.operations.append(("WRITE", address, payload))
        if self.write_count in self.fail_write_numbers:
            raise RuntimeError("fake VSMD write failed")
        self.data[address:address + len(payload)] = payload
        if address == LEASE_TIMER_ADDRESS and len(payload) == 2:
            timer_value = struct.unpack("<H", payload)[0]
            if timer_value != 0:
                self.timer_phase += 1
                self.active_state_index = 0
            else:
                self.timer_phase = 0

    def set_u16(self, address, value):
        self.data[address:address + 2] = struct.pack("<H", value)

    def set_s16(self, address, value):
        self.data[address:address + 2] = struct.pack("<h", value)

    def set_u32(self, address, value):
        self.data[address:address + 4] = struct.pack("<I", value)


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
    master_period=16666,
    active_states=None,
    fall_states=None,
    initial_output=0,
    lock_response=SERIALIZED_OK,
    convert_response=None,
    unlock_response=SERIALIZED_OK,
    update_trigger_on_lock=True,
    after_unlock=None,
    sleep_function=None,
    monotonic_function=None,
):
    raw_memory = FakeVsmdMemory(
        selector=selector,
        target=target,
        master_period=master_period,
        rise_states=active_states,
        fall_states=fall_states,
        initial_output=initial_output,
    )
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
    if monotonic_function is None:
        monotonic_function = lambda: 0.0
    probe = module.AppManagerMouthLedLiveProbe(
        VsmdTypedMemory(raw_memory),
        adapter,
        level=16,
        duration_ms=200,
        hold_ms=500,
        sleep_function=sleep_function,
        monotonic_function=monotonic_function,
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
        ["--hold-ms", "99"],
        ["--hold-ms", "1001"],
    ],
)
def test_cli_rejects_values_outside_hard_live_limits(arguments):
    with pytest.raises(SystemExit):
        module.create_argument_parser().parse_args(arguments)


def test_cli_accepts_minimum_live_level_and_duration():
    arguments = module.create_argument_parser().parse_args(
        ["--level", "1", "--duration-ms", "50", "--hold-ms", "100"]
    )
    assert arguments.level == 1
    assert arguments.duration_ms == 50
    assert arguments.hold_ms == 100


def test_hold_validation_rejects_bool_and_out_of_range_values():
    with pytest.raises(BaseException):
        module._validate_live_hold(True)
    with pytest.raises(BaseException):
        module._validate_live_hold(99)
    with pytest.raises(BaseException):
        module._validate_live_hold(1001)


def test_preflight_reads_all_fields_before_lock_and_normal_flow_is_ordered():
    probe, memory, transport, sleeps = make_probe()
    result = probe.run()
    assert result.preflight == module.ProbeSnapshot(
        138, 0, 0, PRE_TRIGGER_POINTER
    )
    assert result.locked_trigger_pointer == LEASE_TIMER_ADDRESS
    assert result.master_control_period_us == 16666
    assert result.timer_ticks == 12
    assert result.active_state == module.ActiveInterpolationState(
        16, 0, LEASE_TIMER_ADDRESS, 12, 0.0, 0
    )
    assert result.interpolation_reached_target is True
    assert result.hold_completed is True
    assert result.off_state == module.ActiveInterpolationState(
        0, 0, LEASE_TIMER_ADDRESS, 12, 0.0, 0
    )
    assert result.fade_down_completed is True
    assert result.interpolation_output_safe_zero is True
    assert result.postflight.selector == 138
    assert result.postflight.target == 0
    assert result.postflight.trigger_pointer == PRE_TRIGGER_POINTER
    assert sleeps == [0.2, 0.5, 0.2]
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
        ("READ", MASTER_CONTROL_PERIOD_ADDRESS, 4),
        ("APP", INTERP_LOCK_COMMAND),
        ("APP", INTERP_CONVERT_COMMAND),
    ]
    assert memory.operations[7] == (
        "READ", SOTA_MOUTH_TRIGGER_POINTER_ADDRESS, 2
    )
    assert (
        "READ", SOTA_MOUTH_REMAINING_TIME_ADDRESS, 2
    ) in memory.operations
    assert ("READ", LEASE_TIMER_ADDRESS, 2) in memory.operations
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
        "WRITE", result.timer_address, struct.pack("<H", 12)
    )
    assert writes(memory).count(target_on) == 1
    assert writes(memory).count(timer_on) == 2
    assert writes(memory).count(
        ("WRITE", SOTA_MOUTH_TARGET_ADDRESS, struct.pack("<h", 0))
    ) >= 2
    assert commands(transport).count(INTERP_LOCK_COMMAND) == 1
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_rise_hold_fall_write_sequence_and_hold_contains_no_write():
    probe, memory, unused_transport, unused_sleeps = make_probe()
    sleep_observations = []

    def observe_sleep(seconds):
        sleep_observations.append((seconds, len(writes(memory))))

    probe._sleep_function = observe_sleep
    result = probe.run()
    assert sleep_observations == [
        (0.2, 3),
        (0.5, 3),
        (0.2, 5),
    ]
    assert writes(memory) == [
        ("WRITE", MOUTH_LED_SELECTOR_ADDRESS, b"\x9c\x0c"),
        ("WRITE", SOTA_MOUTH_TARGET_ADDRESS, b"\x10\x00"),
        ("WRITE", LEASE_TIMER_ADDRESS, b"\x0c\x00"),
        ("WRITE", SOTA_MOUTH_TARGET_ADDRESS, b"\x00\x00"),
        ("WRITE", LEASE_TIMER_ADDRESS, b"\x0c\x00"),
        ("WRITE", SOTA_MOUTH_TARGET_ADDRESS, b"\x00\x00"),
        ("WRITE", LEASE_TIMER_ADDRESS, b"\x00\x00"),
        ("WRITE", MOUTH_LED_SELECTOR_ADDRESS, b"\x8a\x00"),
        ("WRITE", SOTA_MOUTH_TARGET_ADDRESS, b"\x00\x00"),
    ]
    assert result.hold_duration_ms == 500


def test_timer_conversion_callback_runs_before_lock_or_write():
    probe, memory, transport, unused_sleeps = make_probe()
    observations = []

    def observe_preflight(period, ticks):
        observations.append(
            (period, ticks, len(transport.requests), tuple(writes(memory)))
        )

    probe.run(preflight_callback=observe_preflight)
    assert observations == [(16666, 12, 0, tuple())]


def test_period_16667_converts_200_ms_to_11_ticks():
    probe, memory, unused_transport, unused_sleeps = make_probe(
        master_period=16667
    )
    result = probe.run()
    assert result.timer_ticks == 11
    timer_write = (
        "WRITE", LEASE_TIMER_ADDRESS, struct.pack("<H", 11)
    )
    assert writes(memory).count(timer_write) == 2
    assert result.active_state.timer_value == 11
    assert result.off_state.timer_value == 11


def test_nonzero_remaining_time_is_rechecked_with_a_finite_poll():
    probe, unused_memory, transport, sleeps = make_probe(
        active_states=[
            (1, 1, LEASE_TIMER_ADDRESS, 999),
            (16, 0, LEASE_TIMER_ADDRESS, 999),
        ]
    )
    result = probe.run()
    assert result.interpolation_reached_target is True
    assert result.active_state.timer_value == 999
    assert sleeps[:2] == [0.2, pytest.approx(0.016666)]
    assert sleeps[-2:] == [0.5, 0.2]
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_active_timer_value_is_recorded_but_not_a_success_condition():
    probe, unused_memory, unused_transport, unused_sleeps = make_probe(
        active_states=[
            (16, 0, LEASE_TIMER_ADDRESS, 0xFFFF),
        ]
    )
    result = probe.run()
    assert result.active_state.timer_value == 0xFFFF
    assert result.interpolation_reached_target is True


def test_fall_timer_value_is_recorded_but_not_a_success_condition():
    probe, unused_memory, unused_transport, unused_sleeps = make_probe(
        fall_states=[
            (0, 0, LEASE_TIMER_ADDRESS, 0xFFFF),
        ]
    )
    result = probe.run()
    assert result.off_state.timer_value == 0xFFFF
    assert result.fade_down_completed is True


def test_complete_first_snapshot_is_accepted_after_deadline_elapsed():
    times = iter([0.0, 0.0, 1.0, 1.0, 1.0, 2.0])
    probe, unused_memory, unused_transport, unused_sleeps = make_probe(
        monotonic_function=lambda: next(times)
    )
    result = probe.run()
    assert result.active_state.snapshot_read_duration_ms == 1000.0
    assert result.off_state.snapshot_read_duration_ms == 1000.0
    assert result.active_state.poll_attempt == 0
    assert result.off_state.poll_attempt == 0


def test_snapshot_read_duration_and_poll_attempt_are_recorded():
    current = [0.0]

    def monotonic():
        current[0] += 0.01
        return current[0]

    probe, unused_memory, unused_transport, unused_sleeps = make_probe(
        monotonic_function=monotonic
    )
    result = probe.run()
    assert result.active_state.snapshot_read_duration_ms == pytest.approx(
        10.0
    )
    assert result.off_state.snapshot_read_duration_ms == pytest.approx(10.0)
    assert result.active_state.poll_attempt == 0
    assert result.off_state.poll_attempt == 0


@pytest.mark.parametrize(
    "active_state,error_text",
    [
        (
            (1, 0, LEASE_TIMER_ADDRESS, 12),
            "before reaching",
        ),
        (
            (16, 0, PRE_TRIGGER_POINTER, 12),
            "TriggerPointer",
        ),
    ],
)
def test_incomplete_active_state_fails_after_cleanup_and_unlock(
    active_state, error_text
):
    probe, memory, transport, unused_sleeps = make_probe(
        active_states=[active_state]
    )
    with pytest.raises(VsmdMouthLedStateError, match=error_text):
        probe.run()
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1
    assert ("WRITE", MOUTH_LED_SELECTOR_ADDRESS, b"\x8a\x00") in writes(
        memory
    )
    assert probe.postflight is not None
    assert probe.routing_state_restored is True


def test_active_completion_deadline_is_bounded_and_cleanup_runs():
    times = iter([0.0, 0.0, 0.0, 1.0])
    probe, memory, transport, sleeps = make_probe(
        active_states=[
            (1, 1, LEASE_TIMER_ADDRESS, 12),
        ],
        monotonic_function=lambda: next(times),
    )
    with pytest.raises(VsmdMouthLedStateError, match="deadline"):
        probe.run()
    assert sleeps == [0.2]
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1
    assert ("WRITE", MOUTH_LED_SELECTOR_ADDRESS, b"\x8a\x00") in writes(
        memory
    )


def test_persistent_remaining_time_stops_after_three_rechecks():
    probe, memory, transport, sleeps = make_probe(
        active_states=[
            (1, 1, LEASE_TIMER_ADDRESS, 12),
        ],
        monotonic_function=lambda: 0.0,
    )
    with pytest.raises(VsmdMouthLedStateError, match="deadline"):
        probe.run()
    assert memory.active_state_index == 4
    assert len(sleeps) == 4
    assert sleeps[0] == 0.2
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_active_state_read_failure_still_cleans_up_and_unlocks():
    probe, memory, transport, unused_sleeps = make_probe()
    memory.fail_read_number = 9
    with pytest.raises(RuntimeError, match="read"):
        probe.run()
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1
    assert ("WRITE", MOUTH_LED_SELECTOR_ADDRESS, b"\x8a\x00") in writes(
        memory
    )


def test_active_error_and_cleanup_failure_preserve_both_errors():
    probe, memory, transport, unused_sleeps = make_probe(
        active_states=[
            (1, 0, LEASE_TIMER_ADDRESS, 12),
        ]
    )
    memory.fail_write_numbers.add(4)
    with pytest.raises(VsmdMouthLedCleanupError) as caught:
        probe.run()
    assert isinstance(caught.value.operation_error, VsmdMouthLedStateError)
    assert isinstance(caught.value.cleanup_error, RuntimeError)
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


@pytest.mark.parametrize(
    "fall_state,error_text,safe_zero",
    [
        ((1, 0, LEASE_TIMER_ADDRESS, 12), "before reaching", False),
        ((0, 0, PRE_TRIGGER_POINTER, 12), "TriggerPointer", True),
    ],
)
def test_fade_down_failure_cleans_up_and_unlocks_once(
    fall_state, error_text, safe_zero
):
    probe, memory, transport, unused_sleeps = make_probe(
        fall_states=[fall_state]
    )
    with pytest.raises(VsmdMouthLedStateError, match=error_text):
        probe.run()
    assert probe.fade_down_completed is False
    assert probe.interpolation_output_safe_zero is safe_zero
    assert probe.cleanup_completed is True
    assert probe.routing_state_restored is True
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1
    assert ("WRITE", MOUTH_LED_SELECTOR_ADDRESS, b"\x8a\x00") in writes(
        memory
    )


def test_fade_down_read_failure_cleans_up_and_unlocks_once():
    probe, memory, transport, unused_sleeps = make_probe()
    memory.fail_read_number = 13
    with pytest.raises(RuntimeError, match="read"):
        probe.run()
    assert probe.fade_down_completed is False
    assert probe.interpolation_output_safe_zero is False
    assert probe.cleanup_completed is True
    assert probe.routing_state_restored is True
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_fade_down_deadline_has_at_most_three_rechecks():
    probe, memory, transport, sleeps = make_probe(
        fall_states=[
            (1, 1, LEASE_TIMER_ADDRESS, 12),
        ],
        monotonic_function=lambda: 0.0,
    )
    with pytest.raises(VsmdMouthLedStateError, match="fade-down.*deadline"):
        probe.run()
    assert len(probe.off_snapshots) == 4
    assert [state.poll_attempt for state in probe.off_snapshots] == [
        0, 1, 2, 3
    ]
    assert sleeps == [
        0.2,
        0.5,
        0.2,
        pytest.approx(0.016666),
        pytest.approx(0.016666),
        pytest.approx(0.016666),
    ]
    assert probe.cleanup_completed is True
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1
    assert memory.timer_phase == 0


def test_fade_down_error_and_cleanup_failure_preserve_both_errors():
    probe, memory, transport, unused_sleeps = make_probe(
        fall_states=[(1, 0, LEASE_TIMER_ADDRESS, 12)]
    )
    memory.fail_write_numbers.add(6)
    with pytest.raises(VsmdMouthLedCleanupError) as caught:
        probe.run()
    assert isinstance(caught.value.operation_error, VsmdMouthLedStateError)
    assert isinstance(caught.value.cleanup_error, RuntimeError)
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


def test_control_period_read_failure_does_not_lock_or_write():
    probe, memory, transport, unused_sleeps = make_probe()
    memory.fail_read_number = 5
    with pytest.raises(RuntimeError, match="read"):
        probe.run()
    assert transport.requests == []
    assert writes(memory) == []


def test_invalid_control_period_does_not_lock_or_write():
    probe, memory, transport, unused_sleeps = make_probe(master_period=0)
    with pytest.raises(BaseException):
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
    memory.fail_read_number = 6
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
    memory.fail_write_numbers.add(6)
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
    assert memory.read_count == 16


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
    assert probe.routing_state_restored is False
    assert commands(transport).count(INTERP_UNLOCK_COMMAND) == 1


def test_postflight_read_failure_is_not_success():
    probe, memory, transport, unused_sleeps = make_probe()
    memory.fail_read_number = 17
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


def test_safe_zero_is_distinct_from_restoring_nonzero_preflight_output():
    probe, unused_memory, unused_transport, unused_sleeps = make_probe(
        initial_output=1
    )
    result = probe.run()
    assert result.interpolation_output_safe_zero is True
    assert result.postflight.output == 0
    assert result.postflight.output != result.preflight.output


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
            "--hold-ms", "500",
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
    assert "transition_duration_ms=200" in output
    assert "hold_duration_ms=500" in output
    assert "rise_output=16" in output
    assert "rise_remaining_time=0" in output
    assert "rise_trigger_pointer=0x01f6" in output
    assert "rise_timer_value=12" in output
    assert "rise_snapshot_read_duration_ms=" in output
    assert "rise_poll_attempt=0" in output
    assert "interpolation_reached_target=true" in output
    assert "hold_completed=true" in output
    assert "off_output=0" in output
    assert "off_remaining_time=0" in output
    assert "off_trigger_pointer=0x01f6" in output
    assert "fade_down_completed=true" in output
    assert "interpolation_output_safe_zero=true" in output
    assert "post_output=0" in output
    assert "master_control_period_us=16666" in output
    assert "timer_ticks=12" in output
    assert "control_sequence_completed=true" in output
    assert "physical_illumination=not_verified" in output
    assert "routing_state_restored=true" in output
    assert "interpolation_output_restored=true" in output
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
