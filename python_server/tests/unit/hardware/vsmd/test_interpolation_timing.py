"""Pure control-tick conversion and runtime-period caching tests."""

import struct

import pytest

from robot_controller.hardware.vsmd.errors import VsmdValidationError
from robot_controller.hardware.vsmd.interpolation_timing import (
    VsmdControlTickConverter,
    milliseconds_to_control_ticks,
)
from robot_controller.hardware.vsmd.memory import VsmdMemoryAccess
from robot_controller.hardware.vsmd.sota_memory_map import (
    MASTER_CONTROL_PERIOD_ADDRESS,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


@pytest.mark.parametrize(
    "duration_ms,period_us,expected",
    [
        (0, 16666, 0),
        (50, 16666, 3),
        (100, 16666, 6),
        (200, 16666, 12),
        (200, 16667, 11),
        (65535, 1, 65535),
    ],
)
def test_milliseconds_to_control_ticks_golden_vectors(
    duration_ms, period_us, expected
):
    assert (
        milliseconds_to_control_ticks(duration_ms, period_us)
        == expected
    )
    assert expected == min(
        int(duration_ms * 1000.0 / period_us), 65535
    )


@pytest.mark.parametrize(
    "duration_ms,period_us",
    [
        (True, 16666),
        (1.0, 16666),
        (-1, 16666),
        (1, True),
        (1, 1.0),
        (1, 0),
        (1, -1),
        (1, 1001),
    ],
)
def test_invalid_conversion_inputs_fail_closed(duration_ms, period_us):
    with pytest.raises(VsmdValidationError):
        milliseconds_to_control_ticks(duration_ms, period_us)


class FakeMemory(VsmdMemoryAccess):
    def __init__(self, period):
        self.period = period
        self.reads = []

    def read_bytes(self, address, size):
        self.reads.append((address, size))
        return struct.pack("<I", self.period)

    def write_bytes(self, address, payload):
        raise AssertionError("converter must not write")


def test_converter_reads_current_runtime_period_for_each_positive_trigger():
    raw_memory = FakeMemory(16666)
    converter = VsmdControlTickConverter(VsmdTypedMemory(raw_memory))
    assert converter.convert(200) == 12
    assert converter.convert(100) == 6
    assert raw_memory.reads == [
        (MASTER_CONTROL_PERIOD_ADDRESS, 4),
        (MASTER_CONTROL_PERIOD_ADDRESS, 4),
    ]


def test_converter_reuses_an_explicitly_injected_period():
    raw_memory = FakeMemory(0)
    converter = VsmdControlTickConverter(
        VsmdTypedMemory(raw_memory), master_control_period_us=16666
    )
    assert converter.convert(200) == 12
    assert converter.convert(100) == 6
    assert raw_memory.reads == []


def test_zero_duration_needs_no_runtime_period_read():
    raw_memory = FakeMemory(0)
    converter = VsmdControlTickConverter(VsmdTypedMemory(raw_memory))
    assert converter.convert(0) == 0
    assert raw_memory.reads == []
