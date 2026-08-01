"""Read-only VSMD adapter for unverified-meaning Sota raw positions."""

import typing

from robot_controller.hardware.sota.axis_state import (
    SotaRawAxisStateSource,
    normalize_sota_raw_axis_positions,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    SERVO_READ_POSITION_BASE,
    SERVO_READ_POSITION_LENGTH,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


class VsmdSotaRawAxisStateSource(SotaRawAxisStateSource):
    """Read one raw array without assigning axes or physical meaning.

    One VSMD array read produces one raw snapshot. Its physical
    interpretation and control-tick consistency are unverified.
    """

    def __init__(self, memory):
        # type: (VsmdTypedMemory) -> None
        if not isinstance(memory, VsmdTypedMemory):
            raise TypeError("memory must be VsmdTypedMemory")
        self._memory = memory

    def read_raw_positions(self):
        # type: () -> typing.Tuple[int, ...]
        values = self._memory.read_s16_array(
            SERVO_READ_POSITION_BASE,
            SERVO_READ_POSITION_LENGTH,
        )
        return normalize_sota_raw_axis_positions(values)
