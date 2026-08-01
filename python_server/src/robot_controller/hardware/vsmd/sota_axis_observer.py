"""Opt-in finite CSV observer for raw Sota servo-position storage.

One VSMD array read produces one raw snapshot. Its physical interpretation
and control-tick consistency are unverified. No axis mapping or degree
conversion is performed.
"""

import argparse
import csv
import math
import sys
import time
import typing

from robot_controller.hardware.sota.axis_state import (
    SotaRawAxisStateSource,
    normalize_sota_raw_axis_positions,
)
from robot_controller.hardware.vsmd.constants import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_HOST,
    DEFAULT_MAX_LINE_LENGTH,
    DEFAULT_PORT,
    DEFAULT_READ_TIMEOUT_SECONDS,
    DEFAULT_WRITE_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.memory import VsmdMemoryClient
from robot_controller.hardware.vsmd.sota_axis_state_source import (
    VsmdSotaRawAxisStateSource,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    SERVO_READ_POSITION_LENGTH,
)
from robot_controller.hardware.vsmd.transport import VsmdTcpTransport
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


CONFIRMATION_FLAG = "--confirm-read-only-axis-observation"
CSV_HEADER = (
    "sample_index",
    "monotonic_seconds",
    "elapsed_seconds",
    "requested_interval_seconds",
    "actual_interval_seconds",
) + tuple(
    "raw_{0:02d}".format(index)
    for index in range(SERVO_READ_POSITION_LENGTH)
)


class SotaAxisReadOnlyObserver(object):
    """Collect finite raw snapshots without assigning physical meaning."""

    def __init__(
        self,
        source,
        interval_ms,
        samples,
        monotonic=time.monotonic,
        sleep=time.sleep,
    ):
        # type: (SotaRawAxisStateSource, int, int, typing.Any, typing.Any) -> None
        if not isinstance(source, SotaRawAxisStateSource):
            raise TypeError("source must implement SotaRawAxisStateSource")
        _validate_bounded_integer("interval_ms", interval_ms, 1, 60000)
        _validate_bounded_integer("samples", samples, 1, 1000000)
        if not callable(monotonic):
            raise TypeError("monotonic must be callable")
        if not callable(sleep):
            raise TypeError("sleep must be callable")
        self._source = source
        self._interval_seconds = interval_ms / 1000.0
        self._samples = samples
        self._monotonic = monotonic
        self._sleep = sleep

    def observe(self, output):
        # type: (typing.Any) -> int
        """Write one header and exactly the configured number of rows."""
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(CSV_HEADER)
        first_time = None  # type: typing.Optional[float]
        previous_time = None  # type: typing.Optional[float]

        for sample_index in range(self._samples):
            sample_time = self._monotonic()
            if first_time is None:
                first_time = sample_time
            actual_interval = (
                0.0
                if previous_time is None
                else sample_time - previous_time
            )
            raw_positions = normalize_sota_raw_axis_positions(
                self._source.read_raw_positions()
            )
            writer.writerow(
                (
                    sample_index,
                    "{0:.9f}".format(sample_time),
                    "{0:.9f}".format(sample_time - first_time),
                    "{0:.9f}".format(self._interval_seconds),
                    "{0:.9f}".format(actual_interval),
                )
                + raw_positions
            )
            previous_time = sample_time

            if sample_index + 1 < self._samples:
                read_finished = self._monotonic()
                remaining = self._interval_seconds - (
                    read_finished - sample_time
                )
                if remaining > 0:
                    self._sleep(remaining)
        return self._samples


def _validate_bounded_integer(name, value, minimum, maximum):
    # type: (str, int, int, int) -> None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise ValueError(
            "{0} must be an integer between {1} and {2}".format(
                name, minimum, maximum
            )
        )


def _bounded_integer(name, minimum, maximum):
    # type: (str, int, int) -> typing.Callable[[str], int]
    def convert(text):
        # type: (str) -> int
        try:
            value = int(text, 10)
        except ValueError:
            raise argparse.ArgumentTypeError(
                "{0} must be an integer".format(name)
            )
        if value < minimum or value > maximum:
            raise argparse.ArgumentTypeError(
                "{0} must be between {1} and {2}".format(
                    name, minimum, maximum
                )
            )
        return value

    return convert


def _positive_float(text):
    # type: (str) -> float
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a number")
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(
            "timeout must be a positive finite number"
        )
    return value


def create_argument_parser():
    # type: () -> argparse.ArgumentParser
    """Build the explicit finite read-only raw-axis observer CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Observe raw Sota servo-position storage as finite CSV. "
            "Physical meaning and control-tick consistency are unverified."
        )
    )
    parser.add_argument(CONFIRMATION_FLAG, action="store_true")
    parser.add_argument("--vsmd-host", default=DEFAULT_HOST)
    parser.add_argument(
        "--vsmd-port",
        type=_bounded_integer("vsmd-port", 1, 65535),
        default=DEFAULT_PORT,
    )
    parser.add_argument(
        "--interval-ms",
        type=_bounded_integer("interval-ms", 1, 60000),
        default=20,
    )
    parser.add_argument(
        "--samples",
        type=_bounded_integer("samples", 1, 1000000),
        default=250,
    )
    parser.add_argument(
        "--connect-timeout",
        type=_positive_float,
        default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--read-timeout",
        type=_positive_float,
        default=DEFAULT_READ_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--max-line-length",
        type=_bounded_integer("max-line-length", 1, 0x7FFFFFFF),
        default=DEFAULT_MAX_LINE_LENGTH,
    )
    return parser


def _default_memory_factory(transport):
    # type: (VsmdTcpTransport) -> VsmdTypedMemory
    return VsmdTypedMemory(VsmdMemoryClient(transport))


def main(
    argv=None,
    transport_factory=VsmdTcpTransport,
    memory_factory=_default_memory_factory,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    # type: (typing.Optional[typing.Sequence[str]], typing.Any, typing.Any, typing.Any, typing.Any) -> int
    """Run an explicitly confirmed finite observation without retry."""
    arguments = create_argument_parser().parse_args(argv)
    if not arguments.confirm_read_only_axis_observation:
        print(
            "error={0} is required".format(CONFIRMATION_FLAG),
            file=sys.stderr,
        )
        return 1

    try:
        transport = transport_factory(
            host=arguments.vsmd_host,
            port=arguments.vsmd_port,
            connect_timeout=arguments.connect_timeout,
            read_timeout=arguments.read_timeout,
            write_timeout=DEFAULT_WRITE_TIMEOUT_SECONDS,
            max_line_length=arguments.max_line_length,
        )
        with transport:
            memory = memory_factory(transport)
            source = VsmdSotaRawAxisStateSource(memory)
            observer = SotaAxisReadOnlyObserver(
                source,
                arguments.interval_ms,
                arguments.samples,
                monotonic=monotonic,
                sleep=sleep,
            )
            observer.observe(sys.stdout)
    except KeyboardInterrupt:
        print("observation_interrupted=true", file=sys.stderr)
        return 0
    except BaseException as error:
        print("result=failure", file=sys.stderr)
        print("error_type={0}".format(type(error).__name__), file=sys.stderr)
        print("error={0}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
