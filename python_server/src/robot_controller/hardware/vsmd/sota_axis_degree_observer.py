"""Opt-in finite CSV observer for mapped Sota axis degrees.

The deployed ServoSettings sequence and Java read path confirm that Sota
servo IDs 1 through 8 select raw indices 1 through 8. This source mapping
does not establish runtime physical correlation or physical angle accuracy.
"""

import argparse
import collections
import csv
import sys
import time
import typing

from robot_controller.hardware.sota.axis_definitions import (
    SotaAxisDefinition,
    SOTA_AXIS_DEFINITIONS,
    get_sota_axis_by_id,
)
from robot_controller.hardware.sota.axis_state import (
    SotaRawAxisStateSource,
    create_sota_axis_read_index_mapping,
    decode_sota_axis_state,
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
from robot_controller.hardware.vsmd import sota_axis_observer as raw_observer
from robot_controller.hardware.vsmd.sota_axis_state_source import (
    VsmdSotaRawAxisStateSource,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    SERVO_READ_POSITION_LENGTH,
)
from robot_controller.hardware.vsmd.transport import VsmdTcpTransport


CONFIRMATION_FLAG = "--confirm-read-only-axis-degree-observation"


_SotaAxisDegreeReadMappingBase = collections.namedtuple(
    "_SotaAxisDegreeReadMappingBase", ["axis", "raw_index"]
)


class SotaAxisDegreeReadMapping(_SotaAxisDegreeReadMappingBase):
    """One immutable confirmed servo-axis to raw-index association."""

    __slots__ = ()


def validate_sota_axis_degree_read_mappings(mappings):
    # type: (typing.Iterable[SotaAxisDegreeReadMapping]) -> typing.Tuple[SotaAxisDegreeReadMapping, ...]
    """Return a validated complete ID-ordered immutable mapping tuple."""
    try:
        entries = tuple(mappings)
    except TypeError:
        raise TypeError("axis degree read mappings must be iterable")
    if len(entries) != len(SOTA_AXIS_DEFINITIONS):
        raise ValueError("axis degree read mappings must contain exactly 8 entries")

    axis_ids = set()
    raw_indices = set()
    for entry in entries:
        if not isinstance(entry, SotaAxisDegreeReadMapping):
            raise TypeError(
                "axis degree read mappings must contain mapping entries"
            )
        axis = entry.axis
        if not isinstance(axis, SotaAxisDefinition):
            raise TypeError("mapping axis must be a SotaAxisDefinition")
        try:
            canonical_axis = get_sota_axis_by_id(axis.axis_id)
        except (KeyError, TypeError):
            raise ValueError("mapping axis ID must be between 1 and 8")
        if canonical_axis is not axis:
            raise ValueError("mapping axis must be a canonical Sota axis")
        if axis.axis_id in axis_ids:
            raise ValueError("mapping axis IDs must be unique")
        axis_ids.add(axis.axis_id)

        raw_index = entry.raw_index
        if isinstance(raw_index, bool) or not isinstance(raw_index, int):
            raise TypeError("mapping raw indices must be integers")
        if raw_index < 0 or raw_index >= SERVO_READ_POSITION_LENGTH:
            raise ValueError(
                "mapping raw index must be between 0 and {0}".format(
                    SERVO_READ_POSITION_LENGTH - 1
                )
            )
        if raw_index in raw_indices:
            raise ValueError("mapping raw indices must be unique")
        raw_indices.add(raw_index)
        if raw_index != axis.axis_id:
            raise ValueError("mapping raw index must equal its servo axis ID")

    expected_ids = tuple(range(1, len(SOTA_AXIS_DEFINITIONS) + 1))
    actual_ids = tuple(entry.axis.axis_id for entry in entries)
    if actual_ids != expected_ids:
        raise ValueError("mapping axes must be ordered by IDs 1 through 8")
    return entries


SOTA_AXIS_DEGREE_READ_MAPPINGS = validate_sota_axis_degree_read_mappings(
    SotaAxisDegreeReadMapping(axis, axis.axis_id)
    for axis in SOTA_AXIS_DEFINITIONS
)
SOTA_AXIS_READ_INDEX_MAPPING = create_sota_axis_read_index_mapping(
    dict(
        (entry.axis.name, entry.raw_index)
        for entry in SOTA_AXIS_DEGREE_READ_MAPPINGS
    )
)

DEGREE_CSV_HEADER = tuple(
    "{0}_deg".format(entry.axis.name)
    for entry in SOTA_AXIS_DEGREE_READ_MAPPINGS
)
CSV_HEADER = raw_observer.CSV_HEADER + DEGREE_CSV_HEADER


class SotaAxisReadOnlyDegreeObserver(object):
    """Collect finite raw snapshots and confirmed-name degree conversions."""

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
        raw_observer._validate_bounded_integer(
            "interval_ms", interval_ms, 0, 60000
        )
        raw_observer._validate_bounded_integer(
            "samples", samples, 1, 1000000
        )
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
        """Write one 45-column header and exactly the configured rows."""
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
            snapshot = decode_sota_axis_state(
                raw_positions, SOTA_AXIS_READ_INDEX_MAPPING
            )
            degrees = tuple(
                snapshot.positions_by_name[entry.axis.name].degrees
                for entry in SOTA_AXIS_DEGREE_READ_MAPPINGS
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
                + degrees
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


def create_argument_parser():
    # type: () -> argparse.ArgumentParser
    """Build the explicit finite read-only mapped-degree observer CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Observe confirmed-name Sota axis degrees as finite CSV. "
            "Runtime physical correlation and angle accuracy are unverified."
        )
    )
    parser.add_argument(CONFIRMATION_FLAG, action="store_true")
    parser.add_argument("--vsmd-host", default=DEFAULT_HOST)
    parser.add_argument(
        "--vsmd-port",
        type=raw_observer._bounded_integer("vsmd-port", 1, 65535),
        default=DEFAULT_PORT,
    )
    parser.add_argument(
        "--interval-ms",
        type=raw_observer._bounded_integer("interval-ms", 0, 60000),
        default=20,
    )
    parser.add_argument(
        "--samples",
        type=raw_observer._bounded_integer("samples", 1, 1000000),
        default=250,
    )
    parser.add_argument(
        "--connect-timeout",
        type=raw_observer._positive_float,
        default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--read-timeout",
        type=raw_observer._positive_float,
        default=DEFAULT_READ_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--max-line-length",
        type=raw_observer._bounded_integer(
            "max-line-length", 1, 0x7FFFFFFF
        ),
        default=DEFAULT_MAX_LINE_LENGTH,
    )
    return parser


def main(
    argv=None,
    transport_factory=VsmdTcpTransport,
    memory_factory=raw_observer._default_memory_factory,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    # type: (typing.Optional[typing.Sequence[str]], typing.Any, typing.Any, typing.Any, typing.Any) -> int
    """Run an explicitly confirmed finite degree observation without retry."""
    arguments = create_argument_parser().parse_args(argv)
    if not arguments.confirm_read_only_axis_degree_observation:
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
            observer = SotaAxisReadOnlyDegreeObserver(
                source,
                arguments.interval_ms,
                arguments.samples,
                monotonic=monotonic,
                sleep=sleep,
            )
            observer.observe(sys.stdout)
    except BaseException as error:
        print("result=failure", file=sys.stderr)
        print("error_type={0}".format(type(error).__name__), file=sys.stderr)
        print("error={0}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
