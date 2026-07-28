"""Byte client and strict little-endian typed memory tests."""

import pytest

from robot_controller.hardware.vsmd.errors import VsmdValidationError
from robot_controller.hardware.vsmd.memory import (
    VsmdMemoryAccess,
    VsmdMemoryClient,
)
from robot_controller.hardware.vsmd.typed_memory import (
    VsmdTypedMemory,
    calculate_indexed_address,
)


class StubTransport(object):
    def __init__(self, lines):
        self.lines = list(lines)
        self.sent = []

    def send(self, data):
        self.sent.append(data)

    def read_line(self):
        return self.lines.pop(0)


class FakeMemory(VsmdMemoryAccess):
    def __init__(self, data=None):
        self.data = bytearray(b"\x00" * 65536)
        self.reads = []
        self.writes = []
        if data is not None:
            for address, payload in data.items():
                self.data[address:address + len(payload)] = payload

    def read_bytes(self, address, size):
        self.reads.append((address, size))
        return bytes(self.data[address:address + size])

    def write_bytes(self, address, payload):
        self.writes.append((address, bytes(payload)))
        self.data[address:address + len(payload)] = payload


def test_memory_client_composes_codec_and_transport():
    transport = StubTransport([b"#0e80 00 FF \r\n"])
    memory = VsmdMemoryClient(transport)
    assert memory.read_bytes(0x0E80, 2) == b"\x00\xff"
    memory.write_bytes(0x012C, b"\x9c\x0c")
    assert transport.sent == [
        b"R 0e80 2\r\n",
        b"w 012c 9c 0c\r\n",
    ]


@pytest.mark.parametrize(
    "method,payload,expected",
    [
        ("read_u8", b"\xff", 255),
        ("read_s8", b"\x80", -128),
        ("read_u16", b"\xff\xff", 65535),
        ("read_s16", b"\x00\x80", -32768),
        ("read_u32", b"\xff\xff\xff\xff", 4294967295),
        ("read_s32", b"\x00\x00\x00\x80", -2147483648),
    ],
)
def test_scalar_reads_are_little_endian(method, payload, expected):
    typed = VsmdTypedMemory(FakeMemory({100: payload}))
    assert getattr(typed, method)(100) == expected


@pytest.mark.parametrize(
    "method,minimum,maximum,minimum_bytes,maximum_bytes",
    [
        ("write_u8", 0, 255, b"\x00", b"\xff"),
        ("write_s8", -128, 127, b"\x80", b"\x7f"),
        ("write_u16", 0, 65535, b"\x00\x00", b"\xff\xff"),
        ("write_s16", -32768, 32767, b"\x00\x80", b"\xff\x7f"),
        (
            "write_u32",
            0,
            4294967295,
            b"\x00\x00\x00\x00",
            b"\xff\xff\xff\xff",
        ),
        (
            "write_s32",
            -2147483648,
            2147483647,
            b"\x00\x00\x00\x80",
            b"\xff\xff\xff\x7f",
        ),
    ],
)
def test_scalar_write_boundaries(
    method, minimum, maximum, minimum_bytes, maximum_bytes
):
    memory = FakeMemory()
    typed = VsmdTypedMemory(memory)
    getattr(typed, method)(10, minimum)
    getattr(typed, method)(20, maximum)
    assert memory.writes == [(10, minimum_bytes), (20, maximum_bytes)]
    with pytest.raises(VsmdValidationError):
        getattr(typed, method)(30, minimum - 1)
    with pytest.raises(VsmdValidationError):
        getattr(typed, method)(30, maximum + 1)
    with pytest.raises(VsmdValidationError):
        getattr(typed, method)(30, True)


def test_arrays_read_write_and_index_calculation():
    memory = FakeMemory(
        {
            100: b"\x00\x01\xff",
            200: b"\x00\x00\xff\xff\x34\x12",
            300: b"\x00\x80\xff\x7f",
        }
    )
    typed = VsmdTypedMemory(memory)
    assert typed.read_u8_array(100, 3) == (0, 1, 255)
    assert typed.read_u16_array(200, 3) == (0, 65535, 0x1234)
    assert typed.read_s16_array(300, 2) == (-32768, 32767)
    typed.write_u8_array(400, [0, 255])
    typed.write_u16_array(500, [0, 65535])
    typed.write_s16_array(600, [-32768, 32767])
    typed.write_u16_at(700, 3, 0x1234)
    typed.write_s16_at(800, 2, -2)
    assert memory.writes == [
        (400, b"\x00\xff"),
        (500, b"\x00\x00\xff\xff"),
        (600, b"\x00\x80\xff\x7f"),
        (706, b"\x34\x12"),
        (804, b"\xfe\xff"),
    ]
    assert calculate_indexed_address(700, 3, 2) == 706


@pytest.mark.parametrize(
    "base,index,size",
    [
        (-1, 0, 1),
        (0, -1, 1),
        (0, 0, 0),
        (65535, 0, 2),
        (65534, 1, 2),
        (True, 0, 1),
    ],
)
def test_invalid_indexed_addresses_are_rejected(base, index, size):
    with pytest.raises(VsmdValidationError):
        calculate_indexed_address(base, index, size)


def test_empty_array_read_is_safe_but_empty_write_is_rejected():
    typed = VsmdTypedMemory(FakeMemory())
    assert typed.read_u16_array(0, 0) == ()
    with pytest.raises(VsmdValidationError):
        typed.write_u16_array(0, [])
