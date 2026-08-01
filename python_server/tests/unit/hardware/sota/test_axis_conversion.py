"""Golden tests for Java-compatible, hardware-free Sota conversion."""

import os
import subprocess
import sys

import pytest

from robot_controller.hardware.sota.axis_conversion import (
    clamp_sota_axis_degrees,
    sota_degrees_to_internal,
    sota_internal_to_degrees,
)
from robot_controller.hardware.sota.axis_definitions import (
    SotaAxisDefinition,
    SOTA_AXIS_DEFINITIONS,
    get_sota_axis_by_name,
)


BODY_Y_FORWARD = (
    (-62, -1481),
    (-61, -1481),
    (-10, -242),
    (-1, -24),
    (0, 0),
    (1, 24),
    (10, 242),
    (61, 1481),
    (62, 1481),
)

BODY_Y_REVERSE = (
    (-1481, -60),
    (-242, -9),
    (-24, 0),
    (0, 0),
    (24, 0),
    (242, 9),
    (1481, 60),
)

HEAD_Y_FORWARD = (
    (-86, -1487),
    (-85, -1487),
    (-10, -175),
    (-1, -17),
    (0, 0),
    (1, 17),
    (2, 35),
    (10, 175),
    (85, 1487),
    (86, 1487),
)

HEAD_Y_REVERSE = (
    (-1487, -84),
    (-175, -9),
    (-17, 0),
    (0, 0),
    (17, 0),
    (35, 1),
    (175, 9),
    (1487, 84),
)

AXIS_BOUNDARIES = (
    ("BODY_Y", -61, 61, -1481, 1481),
    ("L_SHOU", -180, 60, -1800, 600),
    ("L_ELBO", -90, 65, -900, 650),
    ("R_SHOU", -60, 180, -600, 1800),
    ("R_ELBO", -65, 90, -650, 900),
    ("HEAD_Y", -85, 85, -1487, 1487),
    ("HEAD_P", -27, 5, -270, 50),
    ("HEAD_R", -30, 30, -525, 525),
)


@pytest.mark.parametrize("degrees,expected", BODY_Y_FORWARD)
def test_body_y_forward_golden_vectors(degrees, expected):
    axis = get_sota_axis_by_name("BODY_Y")

    assert sota_degrees_to_internal(axis, degrees) == expected


@pytest.mark.parametrize("internal_value,expected", BODY_Y_REVERSE)
def test_body_y_reverse_golden_vectors(internal_value, expected):
    axis = get_sota_axis_by_name("BODY_Y")

    assert sota_internal_to_degrees(axis, internal_value) == expected


@pytest.mark.parametrize("degrees,expected", HEAD_Y_FORWARD)
def test_head_y_forward_golden_vectors(degrees, expected):
    axis = get_sota_axis_by_name("HEAD_Y")

    assert sota_degrees_to_internal(axis, degrees) == expected


@pytest.mark.parametrize("internal_value,expected", HEAD_Y_REVERSE)
def test_head_y_reverse_golden_vectors(internal_value, expected):
    axis = get_sota_axis_by_name("HEAD_Y")

    assert sota_internal_to_degrees(axis, internal_value) == expected


@pytest.mark.parametrize(
    "degrees,expected",
    [(30, 525), (-30, -525)],
)
def test_head_r_forward_golden_vectors(degrees, expected):
    axis = get_sota_axis_by_name("HEAD_R")

    assert sota_degrees_to_internal(axis, degrees) == expected


@pytest.mark.parametrize(
    "internal_value,expected",
    [(525, 29), (-525, -29)],
)
def test_head_r_reverse_golden_vectors(internal_value, expected):
    axis = get_sota_axis_by_name("HEAD_R")

    assert sota_internal_to_degrees(axis, internal_value) == expected


@pytest.mark.parametrize(
    "degrees,expected",
    [(-11, -110), (-1, -10), (0, 0), (1, 10), (11, 110)],
)
def test_unit_ratio_forward_golden_vectors(degrees, expected):
    axis = get_sota_axis_by_name("L_ELBO")

    assert sota_degrees_to_internal(axis, degrees) == expected


@pytest.mark.parametrize(
    "internal_value,expected",
    [(-19, -1), (-10, -1), (-9, 0), (9, 0), (10, 1), (19, 1)],
)
def test_unit_ratio_reverse_uses_java_integer_division(
    internal_value, expected
):
    axis = get_sota_axis_by_name("L_ELBO")

    assert sota_internal_to_degrees(axis, internal_value) == expected


@pytest.mark.parametrize(
    "name,minimum,maximum,expected_minimum,expected_maximum",
    AXIS_BOUNDARIES,
)
def test_all_axis_forward_boundaries_and_clamp(
    name, minimum, maximum, expected_minimum, expected_maximum
):
    axis = get_sota_axis_by_name(name)

    assert clamp_sota_axis_degrees(axis, minimum - 1) == minimum
    assert clamp_sota_axis_degrees(axis, minimum) == minimum
    assert clamp_sota_axis_degrees(axis, maximum) == maximum
    assert clamp_sota_axis_degrees(axis, maximum + 1) == maximum
    assert sota_degrees_to_internal(axis, minimum - 1) == expected_minimum
    assert sota_degrees_to_internal(axis, minimum) == expected_minimum
    assert sota_degrees_to_internal(axis, maximum) == expected_maximum
    assert sota_degrees_to_internal(axis, maximum + 1) == expected_maximum
    assert sota_degrees_to_internal(axis, 0) == 0


@pytest.mark.parametrize("axis", SOTA_AXIS_DEFINITIONS)
def test_all_in_range_forward_values_are_monotonic_signed_s16(axis):
    results = tuple(
        sota_degrees_to_internal(axis, degrees)
        for degrees in range(
            axis.minimum_degrees, axis.maximum_degrees + 1
        )
    )

    assert results == tuple(sorted(results))
    assert all(-32768 <= result <= 32767 for result in results)


def test_reverse_does_not_clamp_to_external_axis_range():
    axis = get_sota_axis_by_name("L_SHOU")

    assert sota_internal_to_degrees(axis, -32768) == -3276
    assert sota_internal_to_degrees(axis, 32767) == 3276


@pytest.mark.parametrize(
    "converter,value",
    [
        (clamp_sota_axis_degrees, 0),
        (sota_degrees_to_internal, 0),
        (sota_internal_to_degrees, 0),
    ],
)
def test_converters_reject_non_axis_definitions(converter, value):
    with pytest.raises(TypeError, match="axis must be a SotaAxisDefinition"):
        converter(object(), value)


@pytest.mark.parametrize(
    "converter,value",
    [
        (clamp_sota_axis_degrees, 0),
        (sota_degrees_to_internal, 0),
        (sota_internal_to_degrees, 0),
    ],
)
def test_converters_reject_noncanonical_axis_definitions(converter, value):
    axis = get_sota_axis_by_name("BODY_Y")
    duplicate = SotaAxisDefinition(*axis)
    mismatched = SotaAxisDefinition(
        axis.axis_id,
        axis.name,
        axis.minimum_degrees,
        axis.maximum_degrees + 1,
        axis.gear_ratio_numerator,
        axis.gear_ratio_denominator,
    )

    for noncanonical in (duplicate, mismatched):
        with pytest.raises(ValueError, match="canonical Sota axis"):
            converter(noncanonical, value)


@pytest.mark.parametrize("degrees", [True, False, 1.0, "10", None])
@pytest.mark.parametrize(
    "converter", [clamp_sota_axis_degrees, sota_degrees_to_internal]
)
def test_forward_inputs_require_non_boolean_integers(converter, degrees):
    axis = get_sota_axis_by_name("BODY_Y")

    with pytest.raises(TypeError, match="degrees must be an integer"):
        converter(axis, degrees)


@pytest.mark.parametrize("internal_value", [True, False, 1.0, "10", None])
def test_reverse_input_requires_non_boolean_integer(internal_value):
    axis = get_sota_axis_by_name("BODY_Y")

    with pytest.raises(TypeError, match="internal value must be an integer"):
        sota_internal_to_degrees(axis, internal_value)


@pytest.mark.parametrize("internal_value", [-32769, 32768])
def test_reverse_input_rejects_values_outside_signed_s16(internal_value):
    axis = get_sota_axis_by_name("BODY_Y")

    with pytest.raises(ValueError, match="signed S16"):
        sota_internal_to_degrees(axis, internal_value)


def test_module_import_does_not_load_hardware_access_modules():
    source_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            os.pardir,
            os.pardir,
            os.pardir,
            "src",
        )
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = source_root
    script = "\n".join(
        [
            "import sys",
            "import robot_controller.hardware.sota.axis_conversion",
            "forbidden = (",
            "    'fcntl',",
            "    'socket',",
            "    'robot_controller.hardware.sota.backend',",
            "    'robot_controller.hardware.vsmd.transport',",
            "    'robot_controller.process_lock',",
            "    'robot_controller.command_service',",
            "    'robot_controller.motion_scheduler',",
            ")",
            "assert not any(name in sys.modules for name in forbidden)",
        ]
    )

    subprocess.check_call([sys.executable, "-c", script], env=environment)
