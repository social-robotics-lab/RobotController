"""Convert public millisecond durations to VSMD control-loop timer ticks."""

import typing

from robot_controller.hardware.vsmd.errors import VsmdValidationError
from robot_controller.hardware.vsmd.sota_memory_map import (
    INTERP_TARGET_TIME_BASE,
    INTERP_TARGET_TIME_LENGTH,
    MASTER_CONTROL_PERIOD_ADDRESS,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


MAX_CONTROL_TIMER_TICKS = 0xFFFF


def milliseconds_to_control_ticks(
    duration_ms, master_control_period_us
):
    # type: (int, int) -> int
    """Return the floor-converted VSMD timer value in control ticks.

    Positive integer arithmetic gives the exact mathematical floor of
    ``duration_ms * 1000.0 / master_control_period_us`` without avoidable
    binary floating-point error.
    """
    _validate_duration_ms(duration_ms)
    _validate_master_control_period(master_control_period_us)
    if duration_ms == 0:
        return 0
    ticks = (duration_ms * 1000) // master_control_period_us
    if ticks == 0:
        raise VsmdValidationError(
            "positive duration produced zero VSMD control ticks"
        )
    return min(ticks, MAX_CONTROL_TIMER_TICKS)


def is_control_timer_address(address):
    # type: (int) -> bool
    """Return whether an address is a verified aligned timer-list element."""
    if isinstance(address, bool) or not isinstance(address, int):
        return False
    offset = address - INTERP_TARGET_TIME_BASE
    return (
        offset >= 0
        and offset < INTERP_TARGET_TIME_LENGTH * 2
        and offset % 2 == 0
    )


class VsmdControlTickConverter(object):
    """Use an injected period or read the current runtime period per trigger."""

    def __init__(self, memory, master_control_period_us=None):
        # type: (VsmdTypedMemory, typing.Optional[int]) -> None
        if not isinstance(memory, VsmdTypedMemory):
            raise TypeError("memory must be VsmdTypedMemory")
        if master_control_period_us is not None:
            _validate_master_control_period(master_control_period_us)
        self._memory = memory
        self._master_control_period_us = master_control_period_us

    @property
    def master_control_period_us(self):
        # type: () -> typing.Optional[int]
        return self._master_control_period_us

    def convert(self, duration_ms):
        # type: (int) -> int
        """Convert one duration, reading a non-injected period when needed."""
        _validate_duration_ms(duration_ms)
        if duration_ms == 0:
            return 0
        period = self._master_control_period_us
        if period is None:
            period = self._memory.read_u32(MASTER_CONTROL_PERIOD_ADDRESS)
            _validate_master_control_period(period)
        return milliseconds_to_control_ticks(duration_ms, period)


def _validate_duration_ms(duration_ms):
    # type: (int) -> None
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
        raise VsmdValidationError("duration_ms must be an integer")
    if duration_ms < 0:
        raise VsmdValidationError("duration_ms must not be negative")


def _validate_master_control_period(master_control_period_us):
    # type: (int) -> None
    if (
        isinstance(master_control_period_us, bool)
        or not isinstance(master_control_period_us, int)
    ):
        raise VsmdValidationError(
            "master_control_period_us must be an integer"
        )
    if master_control_period_us <= 0:
        raise VsmdValidationError(
            "master_control_period_us must be positive"
        )
