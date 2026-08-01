"""Unit tests for hardware-free Sota axis definitions."""

import os
import subprocess
import sys

import pytest

from robot_controller.hardware.sota import axis_definitions
from robot_controller.hardware.sota.axis_definitions import (
    SOTA_AXES_BY_ID,
    SOTA_AXES_BY_NAME,
    SOTA_AXIS_DEFINITIONS,
    SOTA_AXIS_IDS,
    SOTA_AXIS_NAMES,
    create_sota_robot_profile,
    get_sota_axis_by_id,
    get_sota_axis_by_name,
)
from robot_controller.profiles import create_mock_robot_profile


EXPECTED_AXES = (
    (1, "BODY_Y", -61, 61, 2429, 1000),
    (2, "L_SHOU", -180, 60, 1, 1),
    (3, "L_ELBO", -90, 65, 1, 1),
    (4, "R_SHOU", -60, 180, 1, 1),
    (5, "R_ELBO", -65, 90, 1, 1),
    (6, "HEAD_Y", -85, 85, 7, 4),
    (7, "HEAD_P", -27, 5, 1, 1),
    (8, "HEAD_R", -30, 30, 7, 4),
)


def test_exact_axis_definition_table_is_in_java_id_order():
    assert tuple(SOTA_AXIS_DEFINITIONS) == EXPECTED_AXES
    assert tuple(axis.axis_id for axis in SOTA_AXIS_DEFINITIONS) == tuple(
        range(1, 9)
    )


def test_axis_ids_and_names_are_unique():
    assert len(SOTA_AXIS_IDS) == len(SOTA_AXIS_DEFINITIONS) == 8
    assert len(SOTA_AXIS_NAMES) == len(SOTA_AXIS_DEFINITIONS) == 8


def test_published_axis_metadata_is_immutable():
    with pytest.raises(AttributeError):
        SOTA_AXIS_DEFINITIONS.append(EXPECTED_AXES[0])
    with pytest.raises(TypeError):
        SOTA_AXIS_DEFINITIONS[0] = EXPECTED_AXES[0]
    with pytest.raises(TypeError):
        SOTA_AXES_BY_NAME["BODY_Y"] = SOTA_AXIS_DEFINITIONS[0]
    with pytest.raises(TypeError):
        SOTA_AXES_BY_ID[1] = SOTA_AXIS_DEFINITIONS[0]
    with pytest.raises(AttributeError):
        SOTA_AXIS_DEFINITIONS[0].axis_id = 9


def test_known_axis_lookups_return_exact_definitions():
    for axis in SOTA_AXIS_DEFINITIONS:
        assert get_sota_axis_by_name(axis.name) is axis
        assert get_sota_axis_by_id(axis.axis_id) is axis


@pytest.mark.parametrize("name", [True, None, b"BODY_Y", 1])
def test_name_lookup_rejects_non_strings(name):
    with pytest.raises(TypeError, match="axis name must be a string"):
        get_sota_axis_by_name(name)


@pytest.mark.parametrize("name", ["", "SHOULDER", "body_y"])
def test_name_lookup_preserves_key_error_for_unknown_strings(name):
    with pytest.raises(KeyError):
        get_sota_axis_by_name(name)


@pytest.mark.parametrize("axis_id", [True, False, None, 1.0, "1"])
def test_id_lookup_rejects_booleans_and_non_integers(axis_id):
    with pytest.raises(TypeError, match="axis ID must be an integer"):
        get_sota_axis_by_id(axis_id)


@pytest.mark.parametrize("axis_id", [-1, 0, 9, 100])
def test_id_lookup_preserves_key_error_for_unknown_integers(axis_id):
    with pytest.raises(KeyError):
        get_sota_axis_by_id(axis_id)


def test_sota_profile_matches_external_axis_ranges_and_mouth_contract():
    profile = create_sota_robot_profile()

    assert profile.allowed_servo_names == SOTA_AXIS_NAMES
    assert profile.allowed_led_names == frozenset(["MOUTH"])
    assert profile.led_range("MOUTH").minimum == 0
    assert profile.led_range("MOUTH").maximum == 255
    for axis in SOTA_AXIS_DEFINITIONS:
        value_range = profile.servo_range(axis.name)
        assert value_range.minimum == axis.minimum_degrees
        assert value_range.maximum == axis.maximum_degrees

    with pytest.raises(TypeError):
        profile.servo_ranges["BODY_Y"] = (-1, 1)


def test_sota_profile_factory_returns_independent_profiles():
    assert create_sota_robot_profile() is not create_sota_robot_profile()


def test_mock_profile_is_unchanged():
    profile = create_mock_robot_profile()

    assert profile.allowed_servo_names == frozenset(
        ["BODY_Y", "HEAD_P", "HEAD_Y"]
    )
    assert profile.allowed_led_names == frozenset(["MOUTH"])
    assert profile.servo_range("BODY_Y") == (-180, 180)
    assert profile.servo_range("HEAD_P") == (-180, 180)
    assert profile.servo_range("HEAD_Y") == (-180, 180)
    assert profile.led_range("MOUTH") == (0, 255)


def test_module_does_not_publish_angle_conversion_functions():
    forbidden_names = (
        "degrees_to_servo",
        "servo_to_degrees",
        "clamp_angle",
        "convert_angle",
        "encode_servo",
        "decode_servo",
    )

    assert not any(hasattr(axis_definitions, name) for name in forbidden_names)


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
            "import robot_controller.hardware.sota.axis_definitions",
            "forbidden = (",
            "    'fcntl',",
            "    'socket',",
            "    'robot_controller.hardware.sota.backend',",
            "    'robot_controller.hardware.vsmd.transport',",
            "    'robot_controller.process_lock',",
            ")",
            "assert not any(name in sys.modules for name in forbidden)",
        ]
    )

    subprocess.check_call([sys.executable, "-c", script], env=environment)
