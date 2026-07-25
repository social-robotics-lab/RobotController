"""Hardware-independent robot names and external validation ranges."""

import collections
import types
import typing


_ValueRangeBase = collections.namedtuple(
    "_ValueRangeBase", ["minimum", "maximum"]
)


class ValueRange(_ValueRangeBase):
    """Inclusive integer range for one public servo or LED name."""

    __slots__ = ()


class RobotProfile(object):
    """Immutable public servo and LED validation metadata.

    This profile contains no device identifiers, conversion code, or hardware
    access. Concrete robot profiles can be supplied by later backend work.
    """

    def __init__(self, servo_ranges, led_ranges):
        # type: (typing.Mapping[str, typing.Tuple[int, int]], typing.Mapping[str, typing.Tuple[int, int]]) -> None
        servo_snapshot = self._copy_ranges(servo_ranges, "servo")
        led_snapshot = self._copy_ranges(led_ranges, "LED")
        self._servo_ranges = types.MappingProxyType(servo_snapshot)
        self._led_ranges = types.MappingProxyType(led_snapshot)
        self._allowed_servo_names = frozenset(servo_snapshot)
        self._allowed_led_names = frozenset(led_snapshot)

    @staticmethod
    def _copy_ranges(ranges, kind):
        # type: (typing.Mapping[str, typing.Tuple[int, int]], str) -> typing.Dict[str, ValueRange]
        copied = {}
        try:
            items = ranges.items()
        except AttributeError:
            raise TypeError("{0} ranges must be a mapping".format(kind))

        for name, bounds in items:
            if not isinstance(name, str):
                raise TypeError("{0} names must be strings".format(kind))
            if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
                raise TypeError(
                    "{0} range for {1!r} must contain two integers".format(
                        kind, name
                    )
                )
            minimum, maximum = bounds
            if (
                isinstance(minimum, bool)
                or not isinstance(minimum, int)
                or isinstance(maximum, bool)
                or not isinstance(maximum, int)
            ):
                raise TypeError(
                    "{0} range for {1!r} must contain integers".format(
                        kind, name
                    )
                )
            if minimum > maximum:
                raise ValueError(
                    "{0} range minimum exceeds maximum for {1!r}".format(
                        kind, name
                    )
                )
            copied[name] = ValueRange(minimum, maximum)
        return copied

    @property
    def servo_ranges(self):
        # type: () -> typing.Mapping[str, ValueRange]
        """Return the immutable mapping of servo names to ranges."""
        return self._servo_ranges

    @property
    def led_ranges(self):
        # type: () -> typing.Mapping[str, ValueRange]
        """Return the immutable mapping of LED names to ranges."""
        return self._led_ranges

    @property
    def allowed_servo_names(self):
        # type: () -> typing.AbstractSet[str]
        """Return the allowed public servo names."""
        return self._allowed_servo_names

    @property
    def allowed_led_names(self):
        # type: () -> typing.AbstractSet[str]
        """Return the allowed public LED names."""
        return self._allowed_led_names

    def servo_range(self, name):
        # type: (str) -> ValueRange
        """Return the inclusive range for a known servo name."""
        return self._servo_ranges[name]

    def led_range(self, name):
        # type: (str) -> ValueRange
        """Return the inclusive range for a known LED name."""
        return self._led_ranges[name]


def create_mock_robot_profile():
    # type: () -> RobotProfile
    """Return a small hardware-free profile for protocol testing.

    These ranges are a permissive Mock validation envelope. They are not
    verified hardware limits and must not be used as real robot safety data.
    Public names follow the legacy Sota spelling where it is unambiguous.
    """
    return RobotProfile(
        {
            "BODY_Y": (-180, 180),
            "HEAD_P": (-180, 180),
            "HEAD_Y": (-180, 180),
        },
        {
            "MOUTH": (0, 255),
        },
    )
