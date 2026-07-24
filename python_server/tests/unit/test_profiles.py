"""Unit tests for hardware-independent robot validation profiles."""

import pytest

from robot_controller.profiles import RobotProfile


def test_profile_exposes_immutable_names_and_ranges():
    servo_ranges = {"HEAD_Y": (-20, 20)}
    led_ranges = {"Mouth": (0, 255)}

    profile = RobotProfile(servo_ranges, led_ranges)
    servo_ranges["HEAD_Y"] = (-90, 90)
    led_ranges["Extra"] = (0, 1)

    assert profile.allowed_servo_names == frozenset(["HEAD_Y"])
    assert profile.allowed_led_names == frozenset(["Mouth"])
    assert profile.servo_range("HEAD_Y").minimum == -20
    assert profile.servo_range("HEAD_Y").maximum == 20
    assert profile.led_range("Mouth").minimum == 0
    assert profile.led_range("Mouth").maximum == 255


def test_profile_does_not_expose_mutable_range_mappings():
    profile = RobotProfile({"HEAD_Y": (-20, 20)}, {"Mouth": (0, 255)})

    with pytest.raises(TypeError):
        profile.servo_ranges["HEAD_Y"] = (-90, 90)
    with pytest.raises(TypeError):
        profile.led_ranges["Mouth"] = (0, 1)


@pytest.mark.parametrize(
    "servo_ranges,led_ranges",
    [
        ({"HEAD_Y": (True, 20)}, {}),
        ({"HEAD_Y": (-20, 20.0)}, {}),
        ({}, {"Mouth": (False, 255)}),
        ({}, {"Mouth": (0, 255.0)}),
        ({"HEAD_Y": (20, -20)}, {}),
        ({"HEAD_Y": (-20,)}, {}),
    ],
)
def test_profile_rejects_invalid_ranges(servo_ranges, led_ranges):
    with pytest.raises((TypeError, ValueError)):
        RobotProfile(servo_ranges, led_ranges)


def test_profile_rejects_non_string_names():
    with pytest.raises(TypeError):
        RobotProfile({1: (-20, 20)}, {})

