"""Pure Java-compatible angle conversion for canonical Sota axes."""

from robot_controller.hardware.sota.axis_definitions import (
    SotaAxisDefinition,
    get_sota_axis_by_id,
)


_SIGNED_S16_MINIMUM = -32768
_SIGNED_S16_MAXIMUM = 32767


def _require_canonical_axis(axis_definition):
    # type: (SotaAxisDefinition) -> SotaAxisDefinition
    if not isinstance(axis_definition, SotaAxisDefinition):
        raise TypeError("axis must be a SotaAxisDefinition")
    try:
        canonical_axis = get_sota_axis_by_id(axis_definition.axis_id)
    except (KeyError, TypeError):
        raise ValueError("axis must be a canonical Sota axis")
    if canonical_axis is not axis_definition:
        raise ValueError("axis must be a canonical Sota axis")
    return canonical_axis


def _require_integer(value, description):
    # type: (int, str) -> int
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("{0} must be an integer".format(description))
    return value


def _truncate_integer_division(numerator, denominator):
    # type: (int, int) -> int
    """Divide integers with Java's truncation toward zero."""
    quotient = abs(numerator) // denominator
    if numerator < 0:
        return -quotient
    return quotient


def _clamp_degrees(axis_definition, degrees):
    # type: (SotaAxisDefinition, int) -> int
    if degrees < axis_definition.minimum_degrees:
        return axis_definition.minimum_degrees
    if degrees > axis_definition.maximum_degrees:
        return axis_definition.maximum_degrees
    return degrees


def clamp_sota_axis_degrees(axis_definition, degrees):
    # type: (SotaAxisDefinition, int) -> int
    """Clamp integer degrees to a canonical Sota axis's external range."""
    axis = _require_canonical_axis(axis_definition)
    value = _require_integer(degrees, "degrees")
    return _clamp_degrees(axis, value)


def sota_degrees_to_internal(axis_definition, degrees):
    # type: (SotaAxisDefinition, int) -> int
    """Convert external degrees using Java's clamp and short-cast order."""
    axis = _require_canonical_axis(axis_definition)
    value = _require_integer(degrees, "degrees")
    clamped = _clamp_degrees(axis, value)
    scaled = clamped * 10

    if axis.gear_ratio_numerator == axis.gear_ratio_denominator:
        internal_value = scaled
    else:
        ratio = float(axis.gear_ratio_numerator) / float(
            axis.gear_ratio_denominator
        )
        internal_value = int(scaled * ratio)

    if (
        internal_value < _SIGNED_S16_MINIMUM
        or internal_value > _SIGNED_S16_MAXIMUM
    ):
        raise OverflowError("Sota internal value exceeds signed S16")
    return internal_value


def sota_internal_to_degrees(axis_definition, internal_value):
    # type: (SotaAxisDefinition, int) -> int
    """Convert signed S16 input using Java's integer-first division order."""
    axis = _require_canonical_axis(axis_definition)
    value = _require_integer(internal_value, "internal value")
    if value < _SIGNED_S16_MINIMUM or value > _SIGNED_S16_MAXIMUM:
        raise ValueError("internal value must be within signed S16")

    divided = _truncate_integer_division(value, 10)
    if axis.gear_ratio_numerator == axis.gear_ratio_denominator:
        return divided

    ratio = float(axis.gear_ratio_numerator) / float(
        axis.gear_ratio_denominator
    )
    return int(divided / ratio)
