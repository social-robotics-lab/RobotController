"""Immutable, hardware-free Sota axis metadata and profile creation."""

import collections
import types
import typing

from robot_controller.profiles import RobotProfile


_SotaAxisDefinitionBase = collections.namedtuple(
    "_SotaAxisDefinitionBase",
    [
        "axis_id",
        "name",
        "minimum_degrees",
        "maximum_degrees",
        "gear_ratio_numerator",
        "gear_ratio_denominator",
    ],
)


class SotaAxisDefinition(_SotaAxisDefinitionBase):
    """One immutable Sota axis definition from the Java wire contract."""

    __slots__ = ()


def _validate_axis_definitions(definitions):
    # type: (typing.Tuple[SotaAxisDefinition, ...]) -> None
    """Reject an internally inconsistent static definition table."""
    if len(definitions) != 8:
        raise ValueError("Sota must define exactly 8 axes")

    axis_ids = set()
    names = set()
    for definition in definitions:
        if (
            isinstance(definition.axis_id, bool)
            or not isinstance(definition.axis_id, int)
        ):
            raise TypeError("axis ID must be an integer")
        if definition.axis_id < 1 or definition.axis_id > 8:
            raise ValueError("Sota axis ID must be between 1 and 8")
        if definition.axis_id in axis_ids:
            raise ValueError("duplicate Sota axis ID")
        axis_ids.add(definition.axis_id)

        if not isinstance(definition.name, str):
            raise TypeError("axis name must be a string")
        if not definition.name:
            raise ValueError("axis name must not be empty")
        if definition.name in names:
            raise ValueError("duplicate Sota axis name")
        names.add(definition.name)

        if (
            isinstance(definition.minimum_degrees, bool)
            or not isinstance(definition.minimum_degrees, int)
            or isinstance(definition.maximum_degrees, bool)
            or not isinstance(definition.maximum_degrees, int)
        ):
            raise TypeError("axis angle limits must be integers")
        if definition.minimum_degrees > definition.maximum_degrees:
            raise ValueError("axis minimum exceeds maximum")

        if (
            isinstance(definition.gear_ratio_numerator, bool)
            or not isinstance(definition.gear_ratio_numerator, int)
            or definition.gear_ratio_numerator <= 0
        ):
            raise ValueError("gear ratio numerator must be a positive integer")
        if (
            isinstance(definition.gear_ratio_denominator, bool)
            or not isinstance(definition.gear_ratio_denominator, int)
            or definition.gear_ratio_denominator <= 0
        ):
            raise ValueError(
                "gear ratio denominator must be a positive integer"
            )

    if axis_ids != set(range(1, 9)):
        raise ValueError("Sota axis IDs must be exactly 1 through 8")


SOTA_AXIS_DEFINITIONS = (
    SotaAxisDefinition(1, "BODY_Y", -61, 61, 2429, 1000),
    SotaAxisDefinition(2, "L_SHOU", -180, 60, 1, 1),
    SotaAxisDefinition(3, "L_ELBO", -90, 65, 1, 1),
    SotaAxisDefinition(4, "R_SHOU", -60, 180, 1, 1),
    SotaAxisDefinition(5, "R_ELBO", -65, 90, 1, 1),
    SotaAxisDefinition(6, "HEAD_Y", -85, 85, 7, 4),
    SotaAxisDefinition(7, "HEAD_P", -27, 5, 1, 1),
    SotaAxisDefinition(8, "HEAD_R", -30, 30, 7, 4),
)

_validate_axis_definitions(SOTA_AXIS_DEFINITIONS)

SOTA_AXES_BY_NAME = types.MappingProxyType(
    dict((axis.name, axis) for axis in SOTA_AXIS_DEFINITIONS)
)
SOTA_AXES_BY_ID = types.MappingProxyType(
    dict((axis.axis_id, axis) for axis in SOTA_AXIS_DEFINITIONS)
)
SOTA_AXIS_NAMES = frozenset(SOTA_AXES_BY_NAME)
SOTA_AXIS_IDS = frozenset(SOTA_AXES_BY_ID)


def get_sota_axis_by_name(name):
    # type: (str) -> SotaAxisDefinition
    """Return a Sota definition by its exact public wire name."""
    if not isinstance(name, str):
        raise TypeError("axis name must be a string")
    return SOTA_AXES_BY_NAME[name]


def get_sota_axis_by_id(axis_id):
    # type: (int) -> SotaAxisDefinition
    """Return a Sota definition by Java-compatible ID."""
    if isinstance(axis_id, bool) or not isinstance(axis_id, int):
        raise TypeError("axis ID must be an integer")
    return SOTA_AXES_BY_ID[axis_id]


def create_sota_robot_profile():
    # type: () -> RobotProfile
    """Create a hardware-independent profile for Sota validation."""
    servo_ranges = dict(
        (
            axis.name,
            (axis.minimum_degrees, axis.maximum_degrees),
        )
        for axis in SOTA_AXIS_DEFINITIONS
    )
    return RobotProfile(servo_ranges, {"MOUTH": (0, 255)})
