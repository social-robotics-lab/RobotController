"""Read-only Sota mouth observer tests using only Fake memory/transport."""

import csv
import inspect
import io
import struct

from robot_controller import mock_server
from robot_controller.hardware.vsmd import mouth_led_observer as module
from robot_controller.hardware.vsmd.memory import VsmdMemoryAccess
from robot_controller.hardware.vsmd.sota_memory_map import (
    AUDIO_DIFF_VALUE_ADDRESS,
    MASTER_CONTROL_PERIOD_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_OUTPUT_ADDRESS,
    SOTA_MOUTH_REMAINING_TIME_ADDRESS,
    SOTA_MOUTH_TARGET_ADDRESS,
    SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


VALID_TIMER_ADDRESS = 0x01F4


class FakeMemory(VsmdMemoryAccess):
    def __init__(self, pointer=VALID_TIMER_ADDRESS):
        self.data = bytearray(b"\x00" * 65536)
        self.reads = []
        self.write_calls = 0
        self.fail_read_number = None
        self.set_u32(MASTER_CONTROL_PERIOD_ADDRESS, 16666)
        self.set_u16(AUDIO_DIFF_VALUE_ADDRESS, 7)
        self.set_u16(MOUTH_LED_SELECTOR_ADDRESS, 138)
        self.set_s16(SOTA_MOUTH_TARGET_ADDRESS, 2)
        self.set_s16(SOTA_MOUTH_OUTPUT_ADDRESS, 1)
        self.set_u16(SOTA_MOUTH_TRIGGER_POINTER_ADDRESS, pointer)
        self.set_u16(SOTA_MOUTH_REMAINING_TIME_ADDRESS, 5)
        if 0 <= pointer <= 0xFFFD:
            self.set_u16(pointer, 0xFFFF)

    def read_bytes(self, address, size):
        self.reads.append((address, size))
        if self.fail_read_number == len(self.reads):
            raise RuntimeError("fake observer read failed")
        return bytes(self.data[address:address + size])

    def write_bytes(self, address, payload):
        self.write_calls += 1
        raise AssertionError("observer must not write")

    def set_u16(self, address, value):
        self.data[address:address + 2] = struct.pack("<H", value)

    def set_s16(self, address, value):
        self.data[address:address + 2] = struct.pack("<h", value)

    def set_u32(self, address, value):
        self.data[address:address + 4] = struct.pack("<I", value)


class FakeClock(object):
    def __init__(self):
        self.now = 10.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeTransport(object):
    def __init__(self, calls, **kwargs):
        self.calls = calls
        self.calls.append(kwargs)
        self.entered = 0
        self.closed = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, error_type, error, traceback):
        self.closed += 1
        return False


def parse_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_observer_reads_fixed_columns_and_requested_number_of_samples():
    raw_memory = FakeMemory()
    clock = FakeClock()
    output = io.StringIO()
    observer = module.MouthLedReadOnlyObserver(
        VsmdTypedMemory(raw_memory),
        interval_ms=20,
        samples=3,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    assert observer.observe(output) == 3
    rows = parse_csv(output.getvalue())
    assert tuple(rows[0].keys()) == module.CSV_HEADER
    assert [row["sample_index"] for row in rows] == ["0", "1", "2"]
    assert rows[0]["requested_interval_seconds"] == "0.020000000"
    assert rows[0]["actual_interval_seconds"] == "0.000000000"
    assert rows[1]["actual_interval_seconds"] == "0.020000000"
    assert rows[0]["master_control_period_us"] == "16666"
    assert rows[0]["trigger_timer_value"] == "65535"
    assert raw_memory.write_calls == 0
    assert clock.sleeps == [0.02, 0.02]


def test_valid_pointer_is_read_but_invalid_pointer_is_left_blank():
    valid_memory = FakeMemory(pointer=VALID_TIMER_ADDRESS)
    valid_output = io.StringIO()
    module.MouthLedReadOnlyObserver(
        VsmdTypedMemory(valid_memory), 20, 1
    ).observe(valid_output)
    assert (VALID_TIMER_ADDRESS, 2) in valid_memory.reads
    assert parse_csv(valid_output.getvalue())[0][
        "trigger_timer_value"
    ] == "65535"

    invalid_memory = FakeMemory(pointer=0x1234)
    invalid_output = io.StringIO()
    module.MouthLedReadOnlyObserver(
        VsmdTypedMemory(invalid_memory), 20, 1
    ).observe(invalid_output)
    assert (0x1234, 2) not in invalid_memory.reads
    assert parse_csv(invalid_output.getvalue())[0][
        "trigger_timer_value"
    ] == ""
    assert invalid_memory.write_calls == 0


def test_main_applies_cli_endpoint_and_is_read_only(capsys):
    raw_memory = FakeMemory()
    calls = []
    clock = FakeClock()

    status = module.main(
        [
            "--vsmd-host", "127.0.0.2",
            "--vsmd-port", "16498",
            "--interval-ms", "25",
            "--samples", "2",
        ],
        transport_factory=lambda **kwargs: FakeTransport(calls, **kwargs),
        memory_factory=lambda unused_transport: VsmdTypedMemory(raw_memory),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    assert status == 0
    assert len(parse_csv(capsys.readouterr().out)) == 2
    assert calls[0]["host"] == "127.0.0.2"
    assert calls[0]["port"] == 16498
    assert raw_memory.write_calls == 0


def test_read_failure_is_not_retried_and_returns_nonzero(capsys):
    raw_memory = FakeMemory()
    raw_memory.fail_read_number = 2
    calls = []
    status = module.main(
        ["--samples", "2"],
        transport_factory=lambda **kwargs: FakeTransport(calls, **kwargs),
        memory_factory=lambda unused_transport: VsmdTypedMemory(raw_memory),
    )
    assert status != 0
    assert len(raw_memory.reads) == 2
    assert "result=failure" in capsys.readouterr().err


def test_ctrl_c_is_a_normal_bounded_exit(capsys):
    calls = []

    def interrupted_memory(unused_transport):
        raise KeyboardInterrupt()

    status = module.main(
        [],
        transport_factory=lambda **kwargs: FakeTransport(calls, **kwargs),
        memory_factory=interrupted_memory,
    )
    assert status == 0
    assert "observation_interrupted=true" in capsys.readouterr().err


def test_observer_has_no_app_manager_lock_or_composition_registration():
    source = inspect.getsource(module)
    assert "AppManagerTcpTransport" not in source
    assert "AppManagerLedLock" not in source
    assert "app_manager_" not in source
    assert "6495" not in source
    assert ".write_" not in source
    assert "mouth_led_observer" not in inspect.getsource(mock_server)
