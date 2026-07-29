"""Explicit read-only CSV observer for Sota mouth-LED state.

This module uses only VSMD reads on TCP 6498 when explicitly run. It does not
use SotaAppManager, acquire locks, change the selector, or issue writes.
"""

import argparse
import csv
import math
import sys
import time
import typing

from robot_controller.hardware.vsmd.constants import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_HOST,
    DEFAULT_MAX_LINE_LENGTH,
    DEFAULT_PORT,
    DEFAULT_READ_TIMEOUT_SECONDS,
    DEFAULT_WRITE_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.interpolation_timing import (
    is_control_timer_address,
)
from robot_controller.hardware.vsmd.memory import VsmdMemoryClient
from robot_controller.hardware.vsmd.sota_memory_map import (
    AUDIO_DIFF_VALUE_ADDRESS,
    MASTER_CONTROL_PERIOD_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_OUTPUT_ADDRESS,
    SOTA_MOUTH_REMAINING_TIME_ADDRESS,
    SOTA_MOUTH_TARGET_ADDRESS,
    SOTA_MOUTH_TRIGGER_POINTER_ADDRESS,
)
from robot_controller.hardware.vsmd.transport import VsmdTcpTransport
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


CSV_HEADER = (
    "sample_index",
    "monotonic_seconds",
    "elapsed_seconds",
    "requested_interval_seconds",
    "actual_interval_seconds",
    "master_control_period_us",
    "audio_diff",
    "selector",
    "target",
    "output",
    "trigger_pointer",
    "trigger_timer_value",
    "remaining_time",
)


class MouthLedReadOnlyObserver(object):
    """Collect a finite series of non-atomic, read-only mouth snapshots."""

    def __init__(
        self,
        memory,
        interval_ms,
        samples,
        monotonic=time.monotonic,
        sleep=time.sleep,
    ):
        # type: (VsmdTypedMemory, int, int, typing.Any, typing.Any) -> None
        if not isinstance(memory, VsmdTypedMemory):
            raise TypeError("memory must be VsmdTypedMemory")
        _validate_positive_integer("interval_ms", interval_ms)
        _validate_positive_integer("samples", samples)
        if not callable(monotonic):
            raise TypeError("monotonic must be callable")
        if not callable(sleep):
            raise TypeError("sleep must be callable")
        self._memory = memory
        self._interval_seconds = interval_ms / 1000.0
        self._samples = samples
        self._monotonic = monotonic
        self._sleep = sleep

    def observe(self, output):
        # type: (typing.Any) -> int
        """Write a fixed CSV header and the requested number of samples."""
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
            values = self._read_values()
            writer.writerow(
                (
                    sample_index,
                    "{0:.9f}".format(sample_time),
                    "{0:.9f}".format(sample_time - first_time),
                    "{0:.9f}".format(self._interval_seconds),
                    "{0:.9f}".format(actual_interval),
                )
                + values
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

    def _read_values(self):
        # type: () -> typing.Tuple[typing.Any, ...]
        master_period = self._memory.read_u32(
            MASTER_CONTROL_PERIOD_ADDRESS
        )
        audio_diff = self._memory.read_u16(AUDIO_DIFF_VALUE_ADDRESS)
        selector = self._memory.read_u16(MOUTH_LED_SELECTOR_ADDRESS)
        target = self._memory.read_s16(SOTA_MOUTH_TARGET_ADDRESS)
        output = self._memory.read_s16(SOTA_MOUTH_OUTPUT_ADDRESS)
        trigger_pointer = self._memory.read_u16(
            SOTA_MOUTH_TRIGGER_POINTER_ADDRESS
        )
        trigger_timer_value = ""
        if is_control_timer_address(trigger_pointer):
            trigger_timer_value = self._memory.read_u16(trigger_pointer)
        remaining_time = self._memory.read_u16(
            SOTA_MOUTH_REMAINING_TIME_ADDRESS
        )
        return (
            master_period,
            audio_diff,
            selector,
            target,
            output,
            trigger_pointer,
            trigger_timer_value,
            remaining_time,
        )


def _validate_positive_integer(name, value):
    # type: (str, int) -> None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValueError("{0} must be a positive integer".format(name))


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
    """Build the explicit read-only observer CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Observe Sota mouth state as CSV using VSMD reads only. "
            "No lock or write is performed."
        )
    )
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
    """Run the finite observer without retrying failed reads."""
    arguments = create_argument_parser().parse_args(argv)
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
            observer = MouthLedReadOnlyObserver(
                memory_factory(transport),
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
        print(
            "error_type={0}".format(type(error).__name__),
            file=sys.stderr,
        )
        print("error={0}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
