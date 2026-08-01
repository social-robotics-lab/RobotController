"""Finite read-only Sota raw-axis observer and CLI tests."""

import csv
import inspect
import io
import os
import subprocess
import sys

import pytest

from robot_controller.hardware.sota.axis_state import SotaRawAxisStateSource
from robot_controller.hardware.vsmd import sota_axis_observer as module
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
    def __init__(self, clock, read_seconds=0.0, exception=None):
        self.clock = clock
        self.read_seconds = read_seconds
        self.exception = exception
        self.read_count = 0
        self.values = tuple(range(SERVO_READ_POSITION_LENGTH))

    def read_raw_positions(self):
        self.read_count += 1
        self.clock.now += self.read_seconds
        if self.exception is not None:
            raise self.exception
        return self.values


class CliTypedMemory(VsmdTypedMemory):
    def __init__(self, exception=None):
        self.exception = exception
        self.read_calls = []
        self.write_calls = []

    def read_s16_array(self, address, length):
        self.read_calls.append((address, length))
        if self.exception is not None:
            raise self.exception
        return tuple(range(length))

    def write_bytes(self, address, payload):
        self.write_calls.append((address, payload))
        raise AssertionError("axis observer must not write")


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


def expected_header():
    return (
        "sample_index",
        "monotonic_seconds",
        "elapsed_seconds",
        "requested_interval_seconds",
        "actual_interval_seconds",
    ) + tuple("raw_{0:02d}".format(index) for index in range(32))


def test_observer_writes_exact_wide_header_and_finite_rows():
    clock = FakeClock()
    source = TimedSource(clock)
    output = io.StringIO()
    observer = module.SotaAxisReadOnlyObserver(
        source,
        interval_ms=20,
        samples=3,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert observer.observe(output) == 3

    rows = parse_csv(output.getvalue())
    assert module.CSV_HEADER == expected_header()
    assert tuple(rows[0].keys()) == expected_header()
    assert len(rows) == 3
    assert source.read_count == 3
    assert [row["sample_index"] for row in rows] == ["0", "1", "2"]
    assert rows[0]["elapsed_seconds"] == "0.000000000"
    assert rows[0]["actual_interval_seconds"] == "0.000000000"
    assert rows[0]["requested_interval_seconds"] == "0.020000000"
    assert [rows[0]["raw_{0:02d}".format(index)] for index in range(32)] == [
        str(index) for index in range(32)
    ]
    assert clock.sleeps == [0.02, 0.02]


def test_observer_subtracts_read_time_and_does_not_sleep_after_last_sample():
    clock = FakeClock()
    source = TimedSource(clock, read_seconds=0.005)
    output = io.StringIO()

    module.SotaAxisReadOnlyObserver(
        source, 20, 2, monotonic=clock.monotonic, sleep=clock.sleep
    ).observe(output)

    rows = parse_csv(output.getvalue())
    assert clock.sleeps == [pytest.approx(0.015)]
    assert rows[1]["actual_interval_seconds"] == "0.020000000"


def test_observer_does_not_sleep_when_read_exceeds_interval():
    clock = FakeClock()
    source = TimedSource(clock, read_seconds=0.030)

    module.SotaAxisReadOnlyObserver(
        source, 20, 2, monotonic=clock.monotonic, sleep=clock.sleep
    ).observe(io.StringIO())

    assert source.read_count == 2
    assert clock.sleeps == []


def test_observer_propagates_source_exception_without_retry():
    clock = FakeClock()
    failure = RuntimeError("synthetic observer read failure")
    source = TimedSource(clock, exception=failure)

    with pytest.raises(RuntimeError) as exc_info:
        module.SotaAxisReadOnlyObserver(
            source, 20, 3, monotonic=clock.monotonic, sleep=clock.sleep
        ).observe(io.StringIO())

    assert exc_info.value is failure
    assert source.read_count == 1
    assert clock.sleeps == []


@pytest.mark.parametrize("interval_ms", [True, False, 0, -1, 1.0])
def test_observer_rejects_invalid_interval(interval_ms):
    with pytest.raises(ValueError):
        module.SotaAxisReadOnlyObserver(
            TimedSource(FakeClock()), interval_ms, 1
        )


@pytest.mark.parametrize("samples", [True, False, 0, -1, 1.0])
def test_observer_rejects_invalid_samples(samples):
    with pytest.raises(ValueError):
        module.SotaAxisReadOnlyObserver(
            TimedSource(FakeClock()), 20, samples
        )


def test_observer_rejects_non_source():
    with pytest.raises(TypeError, match="source must implement"):
        module.SotaAxisReadOnlyObserver(object(), 20, 1)


def test_confirmation_is_required_before_any_factory_or_csv(capsys):
    transport_calls = []
    memory_calls = []

    status = module.main(
        [],
        transport_factory=lambda **kwargs: transport_calls.append(kwargs),
        memory_factory=lambda transport: memory_calls.append(transport),
    )

    captured = capsys.readouterr()
    assert status != 0
    assert transport_calls == []
    assert memory_calls == []
    assert captured.out == ""
    assert "--confirm-read-only-axis-observation" in captured.err


def test_confirmed_cli_uses_one_transport_context_and_finite_reads(capsys):
    transport_arguments = []
    transports = []
    memory = CliTypedMemory()
    clock = FakeClock()

    def transport_factory(**kwargs):
        transport = FakeTransport(transport_arguments, **kwargs)
        transports.append(transport)
        return transport

    status = module.main(
        [
            "--confirm-read-only-axis-observation",
            "--vsmd-host", "127.0.0.2",
            "--vsmd-port", "16498",
            "--interval-ms", "25",
            "--samples", "2",
            "--connect-timeout", "1.25",
            "--read-timeout", "2.5",
            "--max-line-length", "4096",
        ],
        transport_factory=transport_factory,
        memory_factory=lambda unused_transport: memory,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    captured = capsys.readouterr()
    rows = parse_csv(captured.out)
    assert status == 0
    assert captured.err == ""
    assert len(rows) == 2
    assert len(memory.read_calls) == 2
    assert memory.write_calls == []
    assert transports[0].entered == 1
    assert transports[0].closed == 1
    assert transport_arguments == [
        {
            "host": "127.0.0.2",
            "port": 16498,
            "connect_timeout": 1.25,
            "read_timeout": 2.5,
            "write_timeout": module.DEFAULT_WRITE_TIMEOUT_SECONDS,
            "max_line_length": 4096,
        }
    ]


def test_confirmed_cli_reports_observer_failure_without_retry(capsys):
    failure = RuntimeError("synthetic CLI read failure")
    memory = CliTypedMemory(exception=failure)
    transport_arguments = []

    status = module.main(
        ["--confirm-read-only-axis-observation", "--samples", "3"],
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
    assert "error=synthetic CLI read failure" in captured.err


def test_confirmed_cli_treats_keyboard_interrupt_as_bounded_exit(capsys):
    memory = CliTypedMemory(exception=KeyboardInterrupt())
    transport_arguments = []

    status = module.main(
        ["--confirm-read-only-axis-observation"],
        transport_factory=lambda **kwargs: FakeTransport(
            transport_arguments, **kwargs
        ),
        memory_factory=lambda unused_transport: memory,
    )

    assert status == 0
    assert len(memory.read_calls) == 1
    assert memory.write_calls == []
    assert "observation_interrupted=true" in capsys.readouterr().err


def test_module_has_no_mapping_degree_write_app_manager_or_lock_path():
    source = inspect.getsource(module)
    assert "decode_sota_axis_state" not in source
    assert "sota_internal_to_degrees" not in source
    assert "axis_id" not in source
    assert "--axis-map" not in source
    assert "--head-y-index" not in source
    assert "--assume-java-order" not in source
    assert "--decode-degrees" not in source
    assert "AppManager" not in source
    assert "ProcessLock" not in source
    assert ".write_bytes(" not in source
    assert ".write_s16(" not in source
    assert ".write_s16_array(" not in source


def test_main_exposes_no_app_manager_or_process_lock_factory():
    parameter_names = tuple(inspect.signature(module.main).parameters)

    assert "app_manager_factory" not in parameter_names
    assert "process_lock_factory" not in parameter_names


@pytest.mark.parametrize(
    "arguments",
    [
        ["--vsmd-port", "0"],
        ["--vsmd-port", "65536"],
        ["--interval-ms", "0"],
        ["--interval-ms", "60001"],
        ["--samples", "0"],
        ["--samples", "1000001"],
        ["--connect-timeout", "0"],
        ["--read-timeout", "nan"],
        ["--max-line-length", "0"],
    ],
)
def test_cli_rejects_invalid_bounded_arguments(arguments):
    with pytest.raises(SystemExit) as exc_info:
        module.create_argument_parser().parse_args(arguments)

    assert exc_info.value.code != 0


def test_module_import_has_no_factory_read_or_thread_side_effects():
    source_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            os.pardir,
            os.pardir,
            os.pardir,
            "src",
        )
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = source_root
    script = "\n".join(
        [
            "import threading",
            "from robot_controller.hardware.vsmd import memory",
            "from robot_controller.hardware.vsmd import transport",
            "from robot_controller.hardware.vsmd import typed_memory",
            "before = tuple(threading.enumerate())",
            "calls = []",
            "def forbidden(*args, **kwargs):",
            "    calls.append((args, kwargs))",
            "    raise AssertionError('import-time construction')",
            "transport.VsmdTcpTransport.__init__ = forbidden",
            "memory.VsmdMemoryClient.__init__ = forbidden",
            "typed_memory.VsmdTypedMemory.__init__ = forbidden",
            "import robot_controller.hardware.vsmd.sota_axis_observer",
            "assert calls == []",
            "assert tuple(threading.enumerate()) == before",
        ]
    )

    subprocess.check_call([sys.executable, "-c", script], env=environment)
