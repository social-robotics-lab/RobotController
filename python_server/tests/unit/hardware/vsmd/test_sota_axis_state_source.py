"""Read-only VSMD Sota raw-axis source tests using Fake memory."""

import pytest

from robot_controller.hardware.vsmd.sota_axis_state_source import (
    VsmdSotaRawAxisStateSource,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    SERVO_READ_POSITION_BASE,
    SERVO_READ_POSITION_LENGTH,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


class RecordingTypedMemory(VsmdTypedMemory):
    def __init__(self, values=None, exception=None):
        self.values = (
            [0] * SERVO_READ_POSITION_LENGTH
            if values is None
            else values
        )
        self.exception = exception
        self.read_s16_array_calls = []
        self.write_calls = []

    def read_s16_array(self, address, length):
        self.read_s16_array_calls.append((address, length))
        if self.exception is not None:
            raise self.exception
        return self.values

    def write_bytes(self, address, payload):
        self.write_calls.append((address, payload))
        raise AssertionError("read-only source must not write")


def test_constructor_performs_no_read_or_write():
    memory = RecordingTypedMemory()

    VsmdSotaRawAxisStateSource(memory)

    assert memory.read_s16_array_calls == []
    assert memory.write_calls == []


def test_read_uses_one_signed_s16_array_call_at_verified_region():
    memory = RecordingTypedMemory(list(range(SERVO_READ_POSITION_LENGTH)))
    source = VsmdSotaRawAxisStateSource(memory)

    result = source.read_raw_positions()

    assert memory.read_s16_array_calls == [
        (SERVO_READ_POSITION_BASE, SERVO_READ_POSITION_LENGTH)
    ]
    assert SERVO_READ_POSITION_BASE == 3712
    assert SERVO_READ_POSITION_LENGTH == 32
    assert result == tuple(range(32))
    assert isinstance(result, tuple)
    assert memory.write_calls == []


def test_read_detaches_result_from_memory_list():
    values = [0] * SERVO_READ_POSITION_LENGTH
    values[10] = 123
    memory = RecordingTypedMemory(values)
    source = VsmdSotaRawAxisStateSource(memory)

    result = source.read_raw_positions()
    values[10] = 456

    assert result[10] == 123
    with pytest.raises(TypeError):
        result[10] = 0


@pytest.mark.parametrize("length", [31, 33])
def test_read_rejects_wrong_array_length_without_retry(length):
    memory = RecordingTypedMemory([0] * length)
    source = VsmdSotaRawAxisStateSource(memory)

    with pytest.raises(ValueError, match="exactly 32"):
        source.read_raw_positions()

    assert len(memory.read_s16_array_calls) == 1
    assert memory.write_calls == []


@pytest.mark.parametrize("value", [True, 1.0, "1", None])
def test_read_rejects_non_integer_elements(value):
    values = [0] * SERVO_READ_POSITION_LENGTH
    values[4] = value
    memory = RecordingTypedMemory(values)

    with pytest.raises(TypeError):
        VsmdSotaRawAxisStateSource(memory).read_raw_positions()

    assert len(memory.read_s16_array_calls) == 1


@pytest.mark.parametrize("value", [-32769, 32768])
def test_read_rejects_values_outside_signed_s16(value):
    values = [0] * SERVO_READ_POSITION_LENGTH
    values[4] = value
    memory = RecordingTypedMemory(values)

    with pytest.raises(ValueError, match="signed S16"):
        VsmdSotaRawAxisStateSource(memory).read_raw_positions()

    assert len(memory.read_s16_array_calls) == 1


def test_memory_exception_is_propagated_without_retry():
    failure = RuntimeError("synthetic memory read failure")
    memory = RecordingTypedMemory(exception=failure)
    source = VsmdSotaRawAxisStateSource(memory)

    with pytest.raises(RuntimeError) as exc_info:
        source.read_raw_positions()

    assert exc_info.value is failure
    assert len(memory.read_s16_array_calls) == 1
    assert memory.write_calls == []


@pytest.mark.parametrize("memory", [object(), None, [], True])
def test_constructor_rejects_non_typed_memory(memory):
    with pytest.raises(TypeError, match="memory must be VsmdTypedMemory"):
        VsmdSotaRawAxisStateSource(memory)
