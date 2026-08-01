"""Mapping-explicit, read-only Sota raw axis state abstractions."""

import abc
import collections
import collections.abc
import types
import typing

from robot_controller.hardware.sota.axis_conversion import (
    sota_internal_to_degrees,
)
from robot_controller.hardware.sota.axis_definitions import (
    SotaAxisDefinition,
    SOTA_AXIS_NAMES,
    get_sota_axis_by_name,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    SERVO_READ_POSITION_LENGTH,
)


_SIGNED_S16_MINIMUM = -32768
_SIGNED_S16_MAXIMUM = 32767


def normalize_sota_raw_axis_positions(values):
    # type: (typing.Iterable[int]) -> typing.Tuple[int, ...]
    """Return a detached, validated raw signed-S16 position tuple."""
    if isinstance(
        values,
        (str, bytes, bytearray, collections.abc.Mapping),
    ):
        raise TypeError("raw positions must be an iterable of integers")
    try:
        normalized = tuple(values)
    except TypeError:
        raise TypeError("raw positions must be an iterable of integers")

    if len(normalized) != SERVO_READ_POSITION_LENGTH:
        raise ValueError(
            "raw positions must contain exactly {0} values".format(
                SERVO_READ_POSITION_LENGTH
            )
        )
    for value in normalized:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("raw positions must contain integers")
        if value < _SIGNED_S16_MINIMUM or value > _SIGNED_S16_MAXIMUM:
            raise ValueError("raw positions must be within signed S16")
    return normalized


_SotaRawAxisStateBase = collections.namedtuple(
    "_SotaRawAxisStateBase", ["raw_positions"]
)


class SotaRawAxisState(_SotaRawAxisStateBase):
    """Immutable raw-only snapshot with no physical interpretation."""

    __slots__ = ()

    def __new__(cls, raw_positions):
        # type: (typing.Iterable[int]) -> SotaRawAxisState
        normalized = normalize_sota_raw_axis_positions(raw_positions)
        return _SotaRawAxisStateBase.__new__(cls, normalized)


_SotaAxisReadIndexMappingBase = collections.namedtuple(
    "_SotaAxisReadIndexMappingBase", ["indices_by_name"]
)


class SotaAxisReadIndexMapping(_SotaAxisReadIndexMappingBase):
    """Immutable caller-supplied public-name to raw-index mapping."""

    __slots__ = ()

    def __new__(cls, mapping):
        # type: (typing.Mapping[str, int]) -> SotaAxisReadIndexMapping
        if not isinstance(mapping, collections.abc.Mapping):
            raise TypeError("index mapping must be a mapping")

        copied = {}  # type: typing.Dict[str, int]
        used_indices = set()
        for name, raw_index in mapping.items():
            if not isinstance(name, str):
                raise TypeError("axis names must be strings")
            get_sota_axis_by_name(name)
            if isinstance(raw_index, bool) or not isinstance(raw_index, int):
                raise TypeError("raw indices must be integers")
            if raw_index < 0 or raw_index >= SERVO_READ_POSITION_LENGTH:
                raise ValueError(
                    "raw index must be between 0 and {0}".format(
                        SERVO_READ_POSITION_LENGTH - 1
                    )
                )
            if raw_index in used_indices:
                raise ValueError("raw indices must be unique")
            used_indices.add(raw_index)
            copied[name] = raw_index

        immutable_mapping = types.MappingProxyType(copied)
        return _SotaAxisReadIndexMappingBase.__new__(
            cls, immutable_mapping
        )


def create_sota_axis_read_index_mapping(mapping):
    # type: (typing.Mapping[str, int]) -> SotaAxisReadIndexMapping
    """Validate and detach one explicit partial or complete mapping."""
    return SotaAxisReadIndexMapping(mapping)


_SotaMappedAxisPositionBase = collections.namedtuple(
    "_SotaMappedAxisPositionBase",
    ["axis", "raw_index", "internal_value", "degrees"],
)


class SotaMappedAxisPosition(_SotaMappedAxisPositionBase):
    """One mapped raw value and its Java-compatible degree conversion."""

    __slots__ = ()


_SotaAxisStateSnapshotBase = collections.namedtuple(
    "_SotaAxisStateSnapshotBase",
    [
        "raw_state",
        "positions_by_name",
        "mapped_axis_names",
        "unmapped_axis_names",
        "mapping_available",
        "mapping_complete",
    ],
)


class SotaAxisStateSnapshot(_SotaAxisStateSnapshotBase):
    """Immutable decoded state that preserves explicit mapping status."""

    __slots__ = ()


def decode_sota_axis_state(raw_positions, index_mapping=None):
    # type: (typing.Iterable[int], typing.Optional[SotaAxisReadIndexMapping]) -> SotaAxisStateSnapshot
    """Decode only axes selected by an explicit caller-supplied mapping."""
    if isinstance(raw_positions, SotaRawAxisState):
        raw_state = raw_positions
    else:
        raw_state = SotaRawAxisState(raw_positions)

    if index_mapping is None:
        mapping = None  # type: typing.Optional[SotaAxisReadIndexMapping]
    elif isinstance(index_mapping, SotaAxisReadIndexMapping):
        mapping = index_mapping
    else:
        mapping = create_sota_axis_read_index_mapping(index_mapping)

    positions = {}  # type: typing.Dict[str, SotaMappedAxisPosition]
    if mapping is not None:
        for name, raw_index in mapping.indices_by_name.items():
            axis = get_sota_axis_by_name(name)
            internal_value = raw_state.raw_positions[raw_index]
            degrees = sota_internal_to_degrees(axis, internal_value)
            positions[name] = SotaMappedAxisPosition(
                axis, raw_index, internal_value, degrees
            )

    mapped_names = frozenset(positions)
    unmapped_names = SOTA_AXIS_NAMES - mapped_names
    mapping_available = mapping is not None
    mapping_complete = mapping_available and mapped_names == SOTA_AXIS_NAMES
    return SotaAxisStateSnapshot(
        raw_state,
        types.MappingProxyType(positions),
        mapped_names,
        unmapped_names,
        mapping_available,
        mapping_complete,
    )


class SotaRawAxisStateSource(abc.ABC):
    """Hardware-independent port for one raw read-only Sota snapshot."""

    @abc.abstractmethod
    def read_raw_positions(self):
        # type: () -> typing.Iterable[int]
        """Return exactly 32 signed-S16 values without interpretation."""
        raise NotImplementedError


class FakeSotaRawAxisStateSource(SotaRawAxisStateSource):
    """Deterministic hardware-free raw source for tests."""

    def __init__(self, raw_positions, exception=None):
        # type: (typing.Iterable[int], typing.Optional[BaseException]) -> None
        self._raw_positions = normalize_sota_raw_axis_positions(raw_positions)
        if exception is not None and not isinstance(exception, BaseException):
            raise TypeError("configured exception must be an exception")
        self._exception = exception
        self._read_count = 0

    @property
    def read_count(self):
        # type: () -> int
        """Return the number of attempted source reads."""
        return self._read_count

    def read_raw_positions(self):
        # type: () -> typing.Tuple[int, ...]
        self._read_count += 1
        if self._exception is not None:
            raise self._exception
        return self._raw_positions


def read_sota_axis_state(source, index_mapping=None):
    # type: (SotaRawAxisStateSource, typing.Optional[SotaAxisReadIndexMapping]) -> SotaAxisStateSnapshot
    """Read exactly once and decode without retry or exception translation."""
    if not isinstance(source, SotaRawAxisStateSource):
        raise TypeError("source must implement SotaRawAxisStateSource")
    raw_positions = source.read_raw_positions()
    return decode_sota_axis_state(raw_positions, index_mapping)
