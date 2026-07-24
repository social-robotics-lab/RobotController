"""Immutable internal models produced from validated protocol values."""

import collections
import types
import typing


_PoseBase = collections.namedtuple(
    "_PoseBase", ["duration_ms", "servo_positions", "led_values"]
)


class Pose(_PoseBase):
    """One validated pose detached from its input mappings."""

    __slots__ = ()

    def __new__(cls, duration_ms, servo_positions, led_values):
        # type: (int, typing.Mapping[str, int], typing.Mapping[str, int]) -> Pose
        servo_snapshot = types.MappingProxyType(dict(servo_positions))
        led_snapshot = types.MappingProxyType(dict(led_values))
        return _PoseBase.__new__(
            cls, duration_ms, servo_snapshot, led_snapshot
        )


_MotionBase = collections.namedtuple("_MotionBase", ["poses"])


class Motion(_MotionBase):
    """An ordered immutable collection of validated poses."""

    __slots__ = ()

    def __new__(cls, poses):
        # type: (typing.Sequence[Pose]) -> Motion
        return _MotionBase.__new__(cls, tuple(poses))


_IdleMotionSettingsBase = collections.namedtuple(
    "_IdleMotionSettingsBase", ["speed", "pause_ms"]
)


class IdleMotionSettings(_IdleMotionSettingsBase):
    """Validated idle-motion speed and pause settings."""

    __slots__ = ()


_DecodedCommandBase = collections.namedtuple(
    "_DecodedCommandBase", ["command", "payload"]
)


class DecodedCommand(_DecodedCommandBase):
    """A legacy command paired with its validated internal payload."""

    __slots__ = ()

