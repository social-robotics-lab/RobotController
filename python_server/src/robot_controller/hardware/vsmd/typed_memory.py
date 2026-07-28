"""Strict little-endian typed access over byte-oriented VSMD memory."""

import struct
import typing

from robot_controller.hardware.vsmd.constants import MAX_ADDRESS
from robot_controller.hardware.vsmd.errors import VsmdValidationError
from robot_controller.hardware.vsmd.memory import VsmdMemoryAccess


_FORMATS = {
    "u8": ("<B", 1, 0, 0xFF),
    "s8": ("<b", 1, -0x80, 0x7F),
    "u16": ("<H", 2, 0, 0xFFFF),
    "s16": ("<h", 2, -0x8000, 0x7FFF),
    "u32": ("<I", 4, 0, 0xFFFFFFFF),
    "s32": ("<i", 4, -0x80000000, 0x7FFFFFFF),
}


def calculate_indexed_address(base_address, index, item_size):
    # type: (int, int, int) -> int
    """Return a checked array element address."""
    for value, name in (
        (base_address, "base_address"),
        (index, "index"),
        (item_size, "item_size"),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise VsmdValidationError("{0} must be an integer".format(name))
    if base_address < 0 or base_address > MAX_ADDRESS:
        raise VsmdValidationError("base_address is outside memory")
    if index < 0:
        raise VsmdValidationError("index must not be negative")
    if item_size < 1:
        raise VsmdValidationError("item_size must be positive")
    address = base_address + index * item_size
    if address > MAX_ADDRESS or address + item_size - 1 > MAX_ADDRESS:
        raise VsmdValidationError("indexed address is outside memory")
    return address


class VsmdTypedMemory(object):
    """Read and write strict scalar and array types."""

    def __init__(self, memory):
        # type: (VsmdMemoryAccess) -> None
        if not isinstance(memory, VsmdMemoryAccess):
            raise TypeError("memory must implement VsmdMemoryAccess")
        self._memory = memory

    def read_u8(self, address):
        # type: (int) -> int
        return self._read_scalar(address, "u8")

    def read_s8(self, address):
        # type: (int) -> int
        return self._read_scalar(address, "s8")

    def read_u16(self, address):
        # type: (int) -> int
        return self._read_scalar(address, "u16")

    def read_s16(self, address):
        # type: (int) -> int
        return self._read_scalar(address, "s16")

    def read_u32(self, address):
        # type: (int) -> int
        return self._read_scalar(address, "u32")

    def read_s32(self, address):
        # type: (int) -> int
        return self._read_scalar(address, "s32")

    def write_u8(self, address, value):
        # type: (int, int) -> None
        self._write_scalar(address, value, "u8")

    def write_s8(self, address, value):
        # type: (int, int) -> None
        self._write_scalar(address, value, "s8")

    def write_u16(self, address, value):
        # type: (int, int) -> None
        self._write_scalar(address, value, "u16")

    def write_s16(self, address, value):
        # type: (int, int) -> None
        self._write_scalar(address, value, "s16")

    def write_u32(self, address, value):
        # type: (int, int) -> None
        self._write_scalar(address, value, "u32")

    def write_s32(self, address, value):
        # type: (int, int) -> None
        self._write_scalar(address, value, "s32")

    def read_u8_array(self, address, length):
        # type: (int, int) -> typing.Sequence[int]
        return self._read_array(address, length, "u8")

    def read_u16_array(self, address, length):
        # type: (int, int) -> typing.Sequence[int]
        return self._read_array(address, length, "u16")

    def read_s16_array(self, address, length):
        # type: (int, int) -> typing.Sequence[int]
        return self._read_array(address, length, "s16")

    def write_u8_array(self, address, values):
        # type: (int, typing.Iterable[int]) -> None
        self._write_array(address, values, "u8")

    def write_u16_array(self, address, values):
        # type: (int, typing.Iterable[int]) -> None
        self._write_array(address, values, "u16")

    def write_s16_array(self, address, values):
        # type: (int, typing.Iterable[int]) -> None
        self._write_array(address, values, "s16")

    def write_u16_at(self, base_address, index, value):
        # type: (int, int, int) -> None
        self.write_u16(
            calculate_indexed_address(base_address, index, 2), value
        )

    def write_s16_at(self, base_address, index, value):
        # type: (int, int, int) -> None
        self.write_s16(
            calculate_indexed_address(base_address, index, 2), value
        )

    def read_u16_at(self, base_address, index):
        # type: (int, int) -> int
        return self.read_u16(
            calculate_indexed_address(base_address, index, 2)
        )

    def read_s16_at(self, base_address, index):
        # type: (int, int) -> int
        return self.read_s16(
            calculate_indexed_address(base_address, index, 2)
        )

    def _read_scalar(self, address, type_name):
        # type: (int, str) -> int
        format_string, size, unused_minimum, unused_maximum = _FORMATS[
            type_name
        ]
        calculate_indexed_address(address, 0, size)
        return struct.unpack(
            format_string, self._memory.read_bytes(address, size)
        )[0]

    def _write_scalar(self, address, value, type_name):
        # type: (int, int, str) -> None
        format_string, size, minimum, maximum = _FORMATS[type_name]
        calculate_indexed_address(address, 0, size)
        self._validate_value(value, minimum, maximum, type_name)
        self._memory.write_bytes(address, struct.pack(format_string, value))

    def _read_array(self, address, length, type_name):
        # type: (int, int, str) -> typing.Sequence[int]
        self._validate_length(length)
        format_string, item_size, unused_minimum, unused_maximum = _FORMATS[
            type_name
        ]
        if length == 0:
            calculate_indexed_address(address, 0, 1)
            return tuple()
        calculate_indexed_address(address, length - 1, item_size)
        data = self._memory.read_bytes(address, length * item_size)
        item_format = format_string[1:]
        return tuple(
            item[0]
            for item in struct.iter_unpack("<" + item_format, data)
        )

    def _write_array(self, address, values, type_name):
        # type: (int, typing.Iterable[int], str) -> None
        values_tuple = tuple(values)
        if not values_tuple:
            raise VsmdValidationError("array values must not be empty")
        format_string, item_size, minimum, maximum = _FORMATS[type_name]
        calculate_indexed_address(
            address, len(values_tuple) - 1, item_size
        )
        for value in values_tuple:
            self._validate_value(value, minimum, maximum, type_name)
        item_format = format_string[1:]
        payload = struct.pack(
            "<{0}{1}".format(len(values_tuple), item_format), *values_tuple
        )
        self._memory.write_bytes(address, payload)

    @staticmethod
    def _validate_length(length):
        # type: (int) -> None
        if isinstance(length, bool) or not isinstance(length, int):
            raise VsmdValidationError("length must be an integer")
        if length < 0:
            raise VsmdValidationError("length must not be negative")

    @staticmethod
    def _validate_value(value, minimum, maximum, type_name):
        # type: (int, int, int, str) -> None
        if isinstance(value, bool) or not isinstance(value, int):
            raise VsmdValidationError(
                "{0} value must be an integer".format(type_name)
            )
        if value < minimum or value > maximum:
            raise VsmdValidationError(
                "{0} value must be between {1} and {2}".format(
                    type_name, minimum, maximum
                )
            )
