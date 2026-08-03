"""Finite read-only mapped Sota degree observer and CLI tests."""

import csv
import inspect
import io

import pytest

from robot_controller.hardware.sota import axis_state
from robot_controller.hardware.sota.axis_definitions import (
    SOTA_AXIS_DEFINITIONS,
)
from robot_controller.hardware.sota.axis_state import SotaRawAxisStateSource
from robot_controller.hardware.vsmd import sota_axis_degree_observer as module
from robot_controller.hardware.vsmd.sota_memory_map import (
    SERVO_READ_POSITION_LENGTH,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


class FakeClock(object):
    def __init__(self):
        self.now = 10.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class TimedSource(SotaRawAxisStateSource):
    def __init__(self, values, clock, read_seconds=0.0, exception=None):
        self.values = tuple(values)
        self.clock = clock
        self.read_seconds = read_seconds
        self.exception = exception
        self.read_count = 0

    def read_raw_positions(self):
        self.read_count += 1
        self.clock.now += self.read_seconds
        if self.exception is not None:
            raise self.exception
        return self.values


class CliTypedMemory(VsmdTypedMemory):
    def __init__(self, values=None, exception=None):
        self.values = (
            tuple(range(SERVO_READ_POSITION_LENGTH))
            if values is None
            else tuple(values)
        )
        self.exception = exception
        self.read_calls = []
        self.write_calls = []

    def read_s16_array(self, address, length):
        self.read_calls.append((address, length))
        if self.exception is not None:
            raise self.exception
        return self.values

    def write_bytes(self, address, payload):
        self.write_calls.append((address, payload))
        raise AssertionError("degree observer must not write")


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


def sample_raw_values():
    values = [index * 113 - 1700 for index in range(32)]
    values[1:9] = [5, -899, 3, 904, 3, -2, -8, 4]
    return values


def parse_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


def expected_header():
    return (
        "sample_index",
        "monotonic_seconds",
        "elapsed_seconds",
        "requested_interval_seconds",
        "actual_interval_seconds",
    ) + tuple(
        "raw_{0:02d}".format(index) for index in range(32)
    ) + tuple(
        "{0}_deg".format(axis.name) for axis in SOTA_AXIS_DEFINITIONS
    )


def test_mapping_is_immutable_complete_and_uses_raw_indices_one_to_eight():
    mappings = module.SOTA_AXIS_DEGREE_READ_MAPPINGS

    assert isinstance(mappings, tuple)
    assert [entry.axis.axis_id for entry in mappings] == list(range(1, 9))
    assert [entry.axis.name for entry in mappings] == [
        axis.name for axis in SOTA_AXIS_DEFINITIONS
    ]
    assert [entry.raw_index for entry in mappings] == list(range(1, 9))
    assert module.SOTA_AXIS_READ_INDEX_MAPPING.indices_by_name == {
        axis.name: axis.axis_id for axis in SOTA_AXIS_DEFINITIONS
    }
    with pytest.raises(TypeError):
        mappings[0] = mappings[1]


@pytest.mark.parametrize(
    "entries,error",
    [
        ((), "exactly 8"),
        (
            tuple(
                module.SotaAxisDegreeReadMapping(axis, 1)
                for axis in SOTA_AXIS_DEFINITIONS
            ),
            "raw indices must be unique",
        ),
        (
            tuple(
                module.SotaAxisDegreeReadMapping(
                    axis, 32 if index == 0 else axis.axis_id
                )
                for index, axis in enumerate(SOTA_AXIS_DEFINITIONS)
            ),
            "raw index must be between",
        ),
        (
            tuple(
                module.SotaAxisDegreeReadMapping(
                    SOTA_AXIS_DEFINITIONS[0]
                    if index == 1
                    else axis,
                    axis.axis_id,
                )
                for index, axis in enumerate(SOTA_AXIS_DEFINITIONS)
            ),
            "axis IDs must be unique",
        ),
    ],
)
def test_mapping_validation_fails_fast(entries, error):
    with pytest.raises(ValueError, match=error):
        module.validate_sota_axis_degree_read_mappings(entries)


def test_observer_writes_exact_45_column_header_and_expected_sample():
    clock = FakeClock()
    source = TimedSource(sample_raw_values(), clock)
    output = io.StringIO()
    observer = module.SotaAxisReadOnlyDegreeObserver(
        source,
        interval_ms=0,
        samples=1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert observer.observe(output) == 1

    rows = parse_csv(output.getvalue())
    assert module.CSV_HEADER == expected_header()
    assert len(module.CSV_HEADER) == 45
    assert tuple(rows[0]) == expected_header()
    assert source.read_count == 1
    assert clock.sleeps == []
    assert [rows[0]["raw_{0:02d}".format(index)] for index in range(32)] == [
        str(value) for value in sample_raw_values()
    ]
    assert [rows[0]["{0}_deg".format(axis.name)] for axis in SOTA_AXIS_DEFINITIONS] == [
        "0", "-89", "0", "90", "0", "0", "0", "0"
    ]


def test_mapping_ignores_raw_zero_and_raw_nine_through_thirty_one():
    baseline = sample_raw_values()
    changed = list(baseline)
    changed[0] = 32767
    for index in range(9, 32):
        changed[index] = -32768 + index

    baseline_output = io.StringIO()
    changed_output = io.StringIO()
    module.SotaAxisReadOnlyDegreeObserver(
        TimedSource(baseline, FakeClock()), 0, 1
    ).observe(baseline_output)
    module.SotaAxisReadOnlyDegreeObserver(
        TimedSource(changed, FakeClock()), 0, 1
    ).observe(changed_output)

    baseline_row = parse_csv(baseline_output.getvalue())[0]
    changed_row = parse_csv(changed_output.getvalue())[0]
    for axis in SOTA_AXIS_DEFINITIONS:
        column = "{0}_deg".format(axis.name)
        assert changed_row[column] == baseline_row[column]
    assert changed_row["raw_00"] == "32767"
    assert changed_row["raw_31"] == str(-32768 + 31)


@pytest.mark.parametrize("raw", [-1, -9, -10, -11, -899])
def test_negative_values_use_existing_java_compatible_converter(raw):
    values = [0] * 32
    values[2] = raw
    output = io.StringIO()

    module.SotaAxisReadOnlyDegreeObserver(
        TimedSource(values, FakeClock()), 0, 1
    ).observe(output)

    expected = "0" if raw in (-1, -9) else str(int(raw / 10))
    assert parse_csv(output.getvalue())[0]["L_SHOU_deg"] == expected


def test_observer_calls_existing_axis_state_converter_once_per_axis(monkeypatch):
    calls = []
    original = axis_state.sota_internal_to_degrees

    def recording_converter(axis, internal_value):
        calls.append((axis.axis_id, internal_value))
        return original(axis, internal_value)

    monkeypatch.setattr(
        axis_state, "sota_internal_to_degrees", recording_converter
    )
    module.SotaAxisReadOnlyDegreeObserver(
        TimedSource(sample_raw_values(), FakeClock()), 0, 1
    ).observe(io.StringIO())

    assert calls == [
        (axis.axis_id, sample_raw_values()[axis.axis_id])
        for axis in SOTA_AXIS_DEFINITIONS
    ]


@pytest.mark.parametrize("samples", [1, 10])
def test_observer_reads_exact_requested_sample_count(samples):
    clock = FakeClock()
    source = TimedSource(sample_raw_values(), clock)
    output = io.StringIO()

    observed = module.SotaAxisReadOnlyDegreeObserver(
        source, 0, samples, monotonic=clock.monotonic, sleep=clock.sleep
    ).observe(output)

    rows = parse_csv(output.getvalue())
    assert observed == samples
    assert source.read_count == samples
    assert len(rows) == samples
    assert [row["sample_index"] for row in rows] == [
        str(index) for index in range(samples)
    ]


def test_observer_propagates_read_failure_without_retry():
    failure = RuntimeError("synthetic degree read failure")
    source = TimedSource(sample_raw_values(), FakeClock(), exception=failure)

    with pytest.raises(RuntimeError) as exc_info:
        module.SotaAxisReadOnlyDegreeObserver(source, 0, 10).observe(
            io.StringIO()
        )

    assert exc_info.value is failure
    assert source.read_count == 1


def test_confirmation_is_required_before_any_factory_source_or_csv(
    capsys, monkeypatch
):
    transport_calls = []
    memory_calls = []
    source_calls = []

    monkeypatch.setattr(
        module,
        "VsmdSotaRawAxisStateSource",
        lambda memory: source_calls.append(memory),
    )

    status = module.main(
        [],
        transport_factory=lambda **kwargs: transport_calls.append(kwargs),
        memory_factory=lambda transport: memory_calls.append(transport),
    )

    captured = capsys.readouterr()
    assert status == 1
    assert transport_calls == []
    assert memory_calls == []
    assert source_calls == []
    assert captured.out == ""
    assert captured.err == (
        "error=--confirm-read-only-axis-degree-observation is required\n"
    )


def test_confirmed_cli_uses_read_only_finite_path(capsys):
    transport_arguments = []
    transports = []
    memory = CliTypedMemory(sample_raw_values())
    clock = FakeClock()

    def transport_factory(**kwargs):
        transport = FakeTransport(transport_arguments, **kwargs)
        transports.append(transport)
        return transport

    status = module.main(
        [
            "--confirm-read-only-axis-degree-observation",
            "--interval-ms", "0",
            "--samples", "10",
        ],
        transport_factory=transport_factory,
        memory_factory=lambda unused_transport: memory,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    captured = capsys.readouterr()
    assert status == 0
    assert captured.err == ""
    assert len(parse_csv(captured.out)) == 10
    assert len(memory.read_calls) == 10
    assert memory.write_calls == []
    assert transports[0].entered == 1
    assert transports[0].closed == 1


def test_confirmed_cli_reports_failure_without_retry(capsys):
    memory = CliTypedMemory(exception=RuntimeError("synthetic CLI failure"))
    transport_arguments = []

    status = module.main(
        [
            "--confirm-read-only-axis-degree-observation",
            "--samples", "10",
        ],
        transport_factory=lambda **kwargs: FakeTransport(
            transport_arguments, **kwargs
        ),
        memory_factory=lambda unused_transport: memory,
    )

    captured = capsys.readouterr()
    assert status == 1
    assert len(memory.read_calls) == 1
    assert memory.write_calls == []
    assert "result=failure" in captured.err
    assert "error_type=RuntimeError" in captured.err
    assert "error=synthetic CLI failure" in captured.err


@pytest.mark.parametrize(
    "arguments",
    [
        ["--interval-ms", "-1"],
        ["--interval-ms", "60001"],
        ["--samples", "0"],
        ["--samples", "1000001"],
    ],
)
def test_cli_rejects_invalid_finite_arguments(arguments):
    with pytest.raises(SystemExit) as exc_info:
        module.create_argument_parser().parse_args(arguments)

    assert exc_info.value.code != 0


def test_module_execution_path_contains_no_write_or_control_api():
    source = inspect.getsource(module)
    assert ".write_bytes(" not in source
    assert ".write_s16(" not in source
    assert ".write_s16_array(" not in source
    assert "AppManager" not in source
    assert "ProcessLock" not in source
    assert "torque" not in source.lower()
    assert "motion" not in source.lower()
    assert "led" not in source.lower()
