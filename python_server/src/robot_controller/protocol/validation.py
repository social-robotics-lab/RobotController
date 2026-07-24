"""Validation of decoded legacy v1 JSON values into internal models."""

import collections
import math
import typing

from robot_controller.errors import (
    EmptyMotionError,
    InvalidFieldTypeError,
    InvalidFieldValueError,
    InvalidTopLevelTypeError,
    LedRangeError,
    MissingFieldError,
    MotionTooLargeError,
    ServoRangeError,
    UnknownLedError,
    UnknownServoError,
)
from robot_controller.models import IdleMotionSettings, Motion, Pose
from robot_controller.profiles import RobotProfile


DEFAULT_MAX_POSE_DURATION_MS = 60000
DEFAULT_MAX_MOTION_POSES = 1000
DEFAULT_IDLE_SPEED = 1.0
DEFAULT_IDLE_PAUSE_MS = 1000


def _require_configured_integer(name, value, minimum):
    # type: (str, typing.Any, int) -> None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("{0} must be an integer".format(name))
    if value < minimum:
        raise ValueError(
            "{0} must be at least {1}".format(name, minimum)
        )


_ValidationLimitsBase = collections.namedtuple(
    "_ValidationLimitsBase",
    [
        "max_pose_duration_ms",
        "max_motion_poses",
        "max_motion_duration_ms",
        "max_idle_speed",
        "max_idle_pause_ms",
    ],
)


class ValidationLimits(_ValidationLimitsBase):
    """Immutable configurable upper bounds for JSON value validation.

    Motion total duration and idle-motion upper limits have no confirmed
    compatibility defaults, so they remain disabled unless configured.
    """

    __slots__ = ()

    def __new__(
        cls,
        max_pose_duration_ms=DEFAULT_MAX_POSE_DURATION_MS,
        max_motion_poses=DEFAULT_MAX_MOTION_POSES,
        max_motion_duration_ms=None,
        max_idle_speed=None,
        max_idle_pause_ms=None,
    ):
        # type: (int, int, typing.Optional[int], typing.Optional[float], typing.Optional[int]) -> ValidationLimits
        _require_configured_integer(
            "max_pose_duration_ms", max_pose_duration_ms, 0
        )
        _require_configured_integer(
            "max_motion_poses", max_motion_poses, 1
        )
        if max_motion_duration_ms is not None:
            _require_configured_integer(
                "max_motion_duration_ms", max_motion_duration_ms, 0
            )
        if max_idle_speed is not None:
            if (
                isinstance(max_idle_speed, bool)
                or not isinstance(max_idle_speed, (int, float))
            ):
                raise TypeError("max_idle_speed must be a number")
            if not math.isfinite(max_idle_speed) or max_idle_speed <= 0:
                raise ValueError(
                    "max_idle_speed must be finite and greater than zero"
                )
        if max_idle_pause_ms is not None:
            _require_configured_integer(
                "max_idle_pause_ms", max_idle_pause_ms, 0
            )
        return _ValidationLimitsBase.__new__(
            cls,
            max_pose_duration_ms,
            max_motion_poses,
            max_motion_duration_ms,
            max_idle_speed,
            max_idle_pause_ms,
        )


DEFAULT_VALIDATION_LIMITS = ValidationLimits()


def validate_pose(
    value,
    robot_profile,
    limits=DEFAULT_VALIDATION_LIMITS,
    command="play_pose",
    path="$",
):
    # type: (typing.Any, RobotProfile, ValidationLimits, str, str) -> Pose
    """Validate one Pose JSON value and return an immutable Pose."""
    if not isinstance(value, dict):
        raise InvalidTopLevelTypeError(
            command, path, value, "a JSON object"
        )

    msec_path = path + ".Msec"
    if "Msec" not in value:
        raise MissingFieldError(
            command, msec_path, None, "required integer field Msec"
        )
    duration_ms = value["Msec"]
    _require_integer(command, msec_path, duration_ms)
    if duration_ms < 0 or duration_ms > limits.max_pose_duration_ms:
        raise InvalidFieldValueError(
            command,
            msec_path,
            duration_ms,
            "an integer from 0 through {0}".format(
                limits.max_pose_duration_ms
            ),
        )

    has_servo_map = "ServoMap" in value
    has_led_map = "LedMap" in value
    if not has_servo_map and not has_led_map:
        raise MissingFieldError(
            command,
            path,
            None,
            "at least one of ServoMap or LedMap",
        )

    servo_positions = {}
    if has_servo_map:
        servo_positions = _validate_servo_map(
            value["ServoMap"],
            robot_profile,
            command,
            path + ".ServoMap",
        )

    led_values = {}
    if has_led_map:
        led_values = _validate_led_map(
            value["LedMap"],
            robot_profile,
            command,
            path + ".LedMap",
        )

    return Pose(duration_ms, servo_positions, led_values)


def validate_motion(
    value,
    robot_profile,
    limits=DEFAULT_VALIDATION_LIMITS,
    command="play_motion",
):
    # type: (typing.Any, RobotProfile, ValidationLimits, str) -> Motion
    """Validate a Motion JSON array and return an immutable Motion."""
    if not isinstance(value, list):
        raise InvalidTopLevelTypeError(
            command, "$", value, "a JSON array"
        )
    if not value:
        raise EmptyMotionError(
            command, "$", value, "a non-empty JSON array of poses"
        )
    if len(value) > limits.max_motion_poses:
        raise MotionTooLargeError(
            command,
            "$",
            len(value),
            "at most {0} poses".format(limits.max_motion_poses),
        )

    poses = []
    total_duration_ms = 0
    for index, pose_value in enumerate(value):
        pose = validate_pose(
            pose_value,
            robot_profile,
            limits,
            command,
            "$[{0}]".format(index),
        )
        poses.append(pose)
        total_duration_ms += pose.duration_ms
        if (
            limits.max_motion_duration_ms is not None
            and total_duration_ms > limits.max_motion_duration_ms
        ):
            raise MotionTooLargeError(
                command,
                "$",
                total_duration_ms,
                "total duration at most {0} ms".format(
                    limits.max_motion_duration_ms
                ),
            )

    return Motion(poses)


def validate_idle_motion(
    value,
    robot_profile,
    limits=DEFAULT_VALIDATION_LIMITS,
    command="play_idle_motion",
):
    # type: (typing.Any, RobotProfile, ValidationLimits, str) -> IdleMotionSettings
    """Validate Idle Motion JSON and return immutable settings."""
    del robot_profile
    if not isinstance(value, dict):
        raise InvalidTopLevelTypeError(
            command, "$", value, "a JSON object"
        )

    speed = value.get("Speed", DEFAULT_IDLE_SPEED)
    speed_path = "$.Speed"
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        raise InvalidFieldTypeError(
            command,
            speed_path,
            speed,
            "an integer or floating-point number, excluding bool",
        )
    if not math.isfinite(speed) or speed <= 0:
        raise InvalidFieldValueError(
            command,
            speed_path,
            speed,
            "a finite number greater than zero",
        )
    if limits.max_idle_speed is not None and speed > limits.max_idle_speed:
        raise InvalidFieldValueError(
            command,
            speed_path,
            speed,
            "a number no greater than {0}".format(limits.max_idle_speed),
        )

    pause_ms = value.get("Pause", DEFAULT_IDLE_PAUSE_MS)
    pause_path = "$.Pause"
    _require_integer(command, pause_path, pause_ms)
    if pause_ms < 0:
        raise InvalidFieldValueError(
            command,
            pause_path,
            pause_ms,
            "an integer greater than or equal to zero",
        )
    if (
        limits.max_idle_pause_ms is not None
        and pause_ms > limits.max_idle_pause_ms
    ):
        raise InvalidFieldValueError(
            command,
            pause_path,
            pause_ms,
            "an integer no greater than {0}".format(
                limits.max_idle_pause_ms
            ),
        )

    return IdleMotionSettings(speed, pause_ms)


def _validate_servo_map(value, robot_profile, command, path):
    # type: (typing.Any, RobotProfile, str, str) -> typing.Dict[str, int]
    if not isinstance(value, dict):
        raise InvalidFieldTypeError(
            command, path, value, "a JSON object"
        )
    validated = {}
    for name, position in value.items():
        item_path = path + "." + name
        if name not in robot_profile.allowed_servo_names:
            raise UnknownServoError(
                command, item_path, name, "a servo name in RobotProfile"
            )
        _require_integer(command, item_path, position)
        allowed_range = robot_profile.servo_range(name)
        if (
            position < allowed_range.minimum
            or position > allowed_range.maximum
        ):
            raise ServoRangeError(
                command,
                item_path,
                position,
                "an integer from {0} through {1}".format(
                    allowed_range.minimum, allowed_range.maximum
                ),
            )
        validated[name] = position
    return validated


def _validate_led_map(value, robot_profile, command, path):
    # type: (typing.Any, RobotProfile, str, str) -> typing.Dict[str, int]
    if not isinstance(value, dict):
        raise InvalidFieldTypeError(
            command, path, value, "a JSON object"
        )
    validated = {}
    for name, led_value in value.items():
        item_path = path + "." + name
        if name not in robot_profile.allowed_led_names:
            raise UnknownLedError(
                command, item_path, name, "an LED name in RobotProfile"
            )
        _require_integer(command, item_path, led_value)
        allowed_range = robot_profile.led_range(name)
        if (
            led_value < allowed_range.minimum
            or led_value > allowed_range.maximum
        ):
            raise LedRangeError(
                command,
                item_path,
                led_value,
                "an integer from {0} through {1}".format(
                    allowed_range.minimum, allowed_range.maximum
                ),
            )
        validated[name] = led_value
    return validated


def _require_integer(command, path, value):
    # type: (str, str, typing.Any) -> None
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidFieldTypeError(
            command, path, value, "an integer, excluding bool"
        )
