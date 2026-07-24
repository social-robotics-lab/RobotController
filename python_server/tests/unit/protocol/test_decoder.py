"""Unit tests for legacy v1 JSON decoding and validation."""

import json
import math

import pytest

from robot_controller.errors import (
    EmptyMotionError,
    InvalidFieldTypeError,
    InvalidFieldValueError,
    InvalidTopLevelTypeError,
    LedRangeError,
    MissingFieldError,
    MotionTooLargeError,
    NonStandardJsonNumberError,
    PayloadDecodeError,
    PayloadJsonError,
    ServoRangeError,
    UnknownLedError,
    UnknownServoError,
)
from robot_controller.models import (
    DecodedCommand,
    IdleMotionSettings,
    Motion,
    Pose,
)
from robot_controller.profiles import RobotProfile
from robot_controller.protocol.commands import (
    PAYLOAD_JSON,
    PAYLOAD_NONE,
    PAYLOAD_WAV,
)
from robot_controller.protocol.decoder import decode_request
from robot_controller.protocol.legacy_v1 import LegacyV1Request
from robot_controller.protocol.validation import (
    DEFAULT_VALIDATION_LIMITS,
    ValidationLimits,
    validate_idle_motion,
    validate_motion,
    validate_pose,
)


@pytest.fixture
def robot_profile():
    """Return a deliberately small hardware-independent profile."""
    return RobotProfile(
        {
            "HEAD_Y": (-20, 20),
            "HEAD_P": (-10, 10),
        },
        {
            "Mouth": (0, 255),
            "Eye": (10, 20),
        },
    )


def request(command, payload):
    """Build a request using the existing legacy v1 transport model."""
    if command == "play_wav":
        payload_kind = PAYLOAD_WAV
    elif command.startswith("play_"):
        payload_kind = PAYLOAD_JSON
    else:
        payload_kind = PAYLOAD_NONE
    return LegacyV1Request(command, payload, command == "read_axes", payload_kind)


def json_bytes(value):
    """Encode JSON without relying on ASCII escaping."""
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def decode(command, value, robot_profile, limits=DEFAULT_VALIDATION_LIMITS):
    """Decode a Python JSON value through the public byte-oriented API."""
    return decode_request(
        request(command, json_bytes(value)),
        robot_profile,
        limits,
    )


def valid_pose(duration=700, servo_value=20):
    """Return one valid mutable Pose-shaped value."""
    return {
        "Msec": duration,
        "ServoMap": {"HEAD_Y": servo_value},
    }


def test_decode_valid_utf8_pose(robot_profile):
    decoded = decode("play_pose", valid_pose(), robot_profile)
    assert decoded == DecodedCommand(
        "play_pose",
        Pose(700, {"HEAD_Y": 20}, {}),
    )


def test_decode_json_with_japanese_unknown_field(robot_profile):
    value = valid_pose()
    value["説明"] = "こんにちは"
    decoded = decode("play_pose", value, robot_profile)
    assert decoded.payload.duration_ms == 700


def test_decode_rejects_invalid_utf8_and_preserves_cause(robot_profile):
    original = request("play_pose", b'{"Msec":1,"ServoMap":{\xff:1}}')
    with pytest.raises(PayloadDecodeError) as exc_info:
        decode_request(original, robot_profile)
    assert exc_info.value.command == "play_pose"
    assert isinstance(exc_info.value.__cause__, UnicodeDecodeError)
    assert repr(original.payload) not in str(exc_info.value)


@pytest.mark.parametrize("payload", [b"", b"{", b"not json"])
def test_decode_rejects_invalid_json_and_preserves_cause(
    payload, robot_profile
):
    with pytest.raises(PayloadJsonError) as exc_info:
        decode_request(request("play_pose", payload), robot_profile)
    assert exc_info.value.command == "play_pose"
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert repr(payload) not in str(exc_info.value)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_decode_rejects_non_standard_json_numbers(constant, robot_profile):
    payload = (
        '{"Msec":1,"ServoMap":{"HEAD_Y":' + constant + "}}"
    ).encode("ascii")
    with pytest.raises(NonStandardJsonNumberError) as exc_info:
        decode_request(request("play_pose", payload), robot_profile)
    assert exc_info.value.command == "play_pose"
    assert exc_info.value.invalid_value == constant
    assert isinstance(exc_info.value.__cause__, ValueError)


@pytest.mark.parametrize("value", [[], "pose", 1, None, True])
def test_pose_rejects_wrong_top_level_type(value, robot_profile):
    with pytest.raises(InvalidTopLevelTypeError) as exc_info:
        decode("play_pose", value, robot_profile)
    assert exc_info.value.path == "$"


def test_pose_accepts_servo_map_only(robot_profile):
    pose = decode("play_pose", valid_pose(), robot_profile).payload
    assert dict(pose.servo_positions) == {"HEAD_Y": 20}
    assert dict(pose.led_values) == {}


def test_pose_accepts_led_map_only(robot_profile):
    value = {"Msec": 10, "LedMap": {"Mouth": 255}}
    pose = decode("play_pose", value, robot_profile).payload
    assert dict(pose.servo_positions) == {}
    assert dict(pose.led_values) == {"Mouth": 255}


def test_pose_accepts_both_maps(robot_profile):
    value = {
        "Msec": 10,
        "ServoMap": {"HEAD_P": -10},
        "LedMap": {"Eye": 20},
    }
    pose = decode("play_pose", value, robot_profile).payload
    assert dict(pose.servo_positions) == {"HEAD_P": -10}
    assert dict(pose.led_values) == {"Eye": 20}


def test_pose_accepts_zero_duration_and_range_boundaries(robot_profile):
    value = {
        "Msec": 0,
        "ServoMap": {"HEAD_Y": -20, "HEAD_P": 10},
        "LedMap": {"Mouth": 255, "Eye": 10},
    }
    pose = decode("play_pose", value, robot_profile).payload
    assert pose.duration_ms == 0
    assert dict(pose.servo_positions) == {"HEAD_Y": -20, "HEAD_P": 10}
    assert dict(pose.led_values) == {"Mouth": 255, "Eye": 10}


def test_pose_accepts_different_key_order(robot_profile):
    payload = (
        b'{"LedMap":{"Mouth":1},"ServoMap":{"HEAD_Y":2},"Msec":3}'
    )
    pose = decode_request(request("play_pose", payload), robot_profile).payload
    assert pose.duration_ms == 3
    assert dict(pose.servo_positions) == {"HEAD_Y": 2}


def test_pose_ignores_unknown_top_level_fields(robot_profile):
    value = valid_pose()
    value["FutureField"] = {"anything": True}
    assert decode("play_pose", value, robot_profile).payload.duration_ms == 700


def test_pose_model_is_detached_from_input_mappings(robot_profile):
    value = valid_pose()
    pose = validate_pose(value, robot_profile, DEFAULT_VALIDATION_LIMITS)
    value["Msec"] = 1
    value["ServoMap"]["HEAD_Y"] = -20
    value["LedMap"] = {"Mouth": 1}
    assert pose.duration_ms == 700
    assert dict(pose.servo_positions) == {"HEAD_Y": 20}
    assert dict(pose.led_values) == {}
    with pytest.raises(TypeError):
        pose.servo_positions["HEAD_Y"] = 0


def test_pose_requires_msec(robot_profile):
    with pytest.raises(MissingFieldError) as exc_info:
        decode("play_pose", {"ServoMap": {"HEAD_Y": 0}}, robot_profile)
    assert exc_info.value.path == "$.Msec"


@pytest.mark.parametrize("value", [True, 1.0, "1", None])
def test_pose_rejects_invalid_msec_type(value, robot_profile):
    with pytest.raises(InvalidFieldTypeError) as exc_info:
        decode(
            "play_pose",
            {"Msec": value, "ServoMap": {"HEAD_Y": 0}},
            robot_profile,
        )
    assert exc_info.value.path == "$.Msec"
    assert exc_info.value.invalid_value == value


def test_pose_rejects_negative_msec(robot_profile):
    with pytest.raises(InvalidFieldValueError) as exc_info:
        decode("play_pose", valid_pose(duration=-1), robot_profile)
    assert exc_info.value.path == "$.Msec"


def test_pose_rejects_msec_over_configured_limit(robot_profile):
    limits = ValidationLimits(max_pose_duration_ms=699)
    with pytest.raises(InvalidFieldValueError):
        decode("play_pose", valid_pose(), robot_profile, limits)


def test_pose_requires_at_least_one_map(robot_profile):
    with pytest.raises(MissingFieldError) as exc_info:
        decode("play_pose", {"Msec": 1}, robot_profile)
    assert exc_info.value.path == "$"


@pytest.mark.parametrize(
    "field,value",
    [
        ("ServoMap", []),
        ("ServoMap", None),
        ("LedMap", []),
        ("LedMap", 1),
    ],
)
def test_pose_rejects_non_object_maps(field, value, robot_profile):
    pose_value = {"Msec": 1, field: value}
    with pytest.raises(InvalidFieldTypeError) as exc_info:
        decode("play_pose", pose_value, robot_profile)
    assert exc_info.value.path == "$." + field


def test_pose_rejects_unknown_servo(robot_profile):
    with pytest.raises(UnknownServoError) as exc_info:
        decode(
            "play_pose",
            {"Msec": 1, "ServoMap": {"UNKNOWN": 0}},
            robot_profile,
        )
    assert exc_info.value.path == "$.ServoMap.UNKNOWN"


def test_pose_rejects_unknown_led(robot_profile):
    with pytest.raises(UnknownLedError) as exc_info:
        decode(
            "play_pose",
            {"Msec": 1, "LedMap": {"Unknown": 0}},
            robot_profile,
        )
    assert exc_info.value.path == "$.LedMap.Unknown"


@pytest.mark.parametrize(
    "field,name,value,path",
    [
        ("ServoMap", "HEAD_Y", True, "$.ServoMap.HEAD_Y"),
        ("LedMap", "Mouth", False, "$.LedMap.Mouth"),
        ("ServoMap", "HEAD_Y", 1.5, "$.ServoMap.HEAD_Y"),
        ("LedMap", "Mouth", 1.5, "$.LedMap.Mouth"),
    ],
)
def test_pose_rejects_invalid_map_value_types(
    field, name, value, path, robot_profile
):
    with pytest.raises(InvalidFieldTypeError) as exc_info:
        decode(
            "play_pose",
            {"Msec": 1, field: {name: value}},
            robot_profile,
        )
    assert exc_info.value.path == path


@pytest.mark.parametrize("value", [-21, 21])
def test_pose_rejects_servo_range_violations(value, robot_profile):
    with pytest.raises(ServoRangeError) as exc_info:
        decode("play_pose", valid_pose(servo_value=value), robot_profile)
    assert exc_info.value.invalid_value == value


@pytest.mark.parametrize("value", [-1, 256])
def test_pose_rejects_led_range_violations(value, robot_profile):
    with pytest.raises(LedRangeError) as exc_info:
        decode(
            "play_pose",
            {"Msec": 1, "LedMap": {"Mouth": value}},
            robot_profile,
        )
    assert exc_info.value.invalid_value == value


def test_motion_accepts_multiple_poses_and_preserves_order(robot_profile):
    value = [valid_pose(10, -20), valid_pose(20, 20)]
    motion = decode("play_motion", value, robot_profile).payload
    assert isinstance(motion, Motion)
    assert [pose.duration_ms for pose in motion.poses] == [10, 20]
    assert [
        pose.servo_positions["HEAD_Y"] for pose in motion.poses
    ] == [-20, 20]


def test_motion_rejects_empty_array(robot_profile):
    with pytest.raises(EmptyMotionError):
        decode("play_motion", [], robot_profile)


@pytest.mark.parametrize("value", [{}, "motion", None, 1, True])
def test_motion_rejects_non_array(value, robot_profile):
    with pytest.raises(InvalidTopLevelTypeError):
        decode("play_motion", value, robot_profile)


def test_motion_rejects_one_invalid_pose_with_index_path(robot_profile):
    value = [valid_pose(), {"Msec": -1, "ServoMap": {"HEAD_Y": 0}}]
    with pytest.raises(InvalidFieldValueError) as exc_info:
        decode("play_motion", value, robot_profile)
    assert exc_info.value.path == "$[1].Msec"


def test_motion_accepts_exact_configured_pose_count(robot_profile):
    limits = ValidationLimits(max_motion_poses=2)
    motion = decode(
        "play_motion",
        [valid_pose(1), valid_pose(2)],
        robot_profile,
        limits,
    ).payload
    assert len(motion.poses) == 2


def test_motion_rejects_pose_count_over_configured_limit(robot_profile):
    limits = ValidationLimits(max_motion_poses=1)
    with pytest.raises(MotionTooLargeError) as exc_info:
        decode(
            "play_motion",
            [valid_pose(1), valid_pose(2)],
            robot_profile,
            limits,
        )
    assert exc_info.value.path == "$"


def test_motion_default_maximum_is_1000():
    assert DEFAULT_VALIDATION_LIMITS.max_motion_poses == 1000


def test_motion_enforces_configured_total_duration_limit(robot_profile):
    limits = ValidationLimits(max_motion_duration_ms=29)
    with pytest.raises(MotionTooLargeError) as exc_info:
        decode(
            "play_motion",
            [valid_pose(10), valid_pose(20)],
            robot_profile,
            limits,
        )
    assert exc_info.value.path == "$"


def test_motion_model_is_detached_from_input_list_and_dicts(robot_profile):
    first = valid_pose(10, -20)
    value = [first]
    motion = validate_motion(value, robot_profile, DEFAULT_VALIDATION_LIMITS)
    first["Msec"] = 999
    first["ServoMap"]["HEAD_Y"] = 20
    value.append(valid_pose())
    assert len(motion.poses) == 1
    assert motion.poses[0].duration_ms == 10
    assert motion.poses[0].servo_positions["HEAD_Y"] == -20
    assert isinstance(motion.poses, tuple)


def test_idle_motion_accepts_all_fields(robot_profile):
    settings = decode(
        "play_idle_motion",
        {"Speed": 1.5, "Pause": 250},
        robot_profile,
    ).payload
    assert settings == IdleMotionSettings(1.5, 250)


def test_idle_motion_uses_defaults_when_all_fields_are_omitted(
    robot_profile,
):
    settings = decode("play_idle_motion", {}, robot_profile).payload
    assert settings == IdleMotionSettings(1.0, 1000)


def test_idle_motion_accepts_only_speed(robot_profile):
    settings = decode(
        "play_idle_motion", {"Speed": 2}, robot_profile
    ).payload
    assert settings.speed == 2
    assert isinstance(settings.speed, int)
    assert settings.pause_ms == 1000


def test_idle_motion_accepts_only_pause(robot_profile):
    settings = decode(
        "play_idle_motion", {"Pause": 5}, robot_profile
    ).payload
    assert settings == IdleMotionSettings(1.0, 5)


@pytest.mark.parametrize("speed", [1, 1.25])
def test_idle_motion_accepts_integer_and_float_speed(speed, robot_profile):
    settings = decode(
        "play_idle_motion", {"Speed": speed}, robot_profile
    ).payload
    assert settings.speed == speed
    assert type(settings.speed) is type(speed)


@pytest.mark.parametrize("speed", [0, -1, True, "1", None])
def test_idle_motion_rejects_invalid_speed(speed, robot_profile):
    error_type = (
        InvalidFieldValueError
        if not isinstance(speed, (bool, str)) and speed is not None
        else InvalidFieldTypeError
    )
    with pytest.raises(error_type) as exc_info:
        decode("play_idle_motion", {"Speed": speed}, robot_profile)
    assert exc_info.value.path == "$.Speed"


@pytest.mark.parametrize("speed", [float("nan"), float("inf"), -float("inf")])
def test_idle_validator_rejects_non_finite_python_speed(
    speed, robot_profile
):
    with pytest.raises(InvalidFieldValueError):
        validate_idle_motion(
            {"Speed": speed}, robot_profile, DEFAULT_VALIDATION_LIMITS
        )
    assert not math.isfinite(speed)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_idle_decoder_rejects_non_standard_speed_number(
    constant, robot_profile
):
    payload = ('{"Speed":' + constant + "}").encode("ascii")
    with pytest.raises(NonStandardJsonNumberError):
        decode_request(
            request("play_idle_motion", payload),
            robot_profile,
        )


@pytest.mark.parametrize("pause", [-1, True, 1.5, "1", None])
def test_idle_motion_rejects_invalid_pause(pause, robot_profile):
    error_type = (
        InvalidFieldValueError
        if isinstance(pause, int) and not isinstance(pause, bool)
        else InvalidFieldTypeError
    )
    with pytest.raises(error_type) as exc_info:
        decode("play_idle_motion", {"Pause": pause}, robot_profile)
    assert exc_info.value.path == "$.Pause"


def test_idle_motion_enforces_configured_upper_limits(robot_profile):
    limits = ValidationLimits(max_idle_speed=2.0, max_idle_pause_ms=2000)
    with pytest.raises(InvalidFieldValueError):
        decode("play_idle_motion", {"Speed": 2.1}, robot_profile, limits)
    with pytest.raises(InvalidFieldValueError):
        decode("play_idle_motion", {"Pause": 2001}, robot_profile, limits)


def test_idle_motion_ignores_unknown_fields(robot_profile):
    settings = decode(
        "play_idle_motion",
        {"Speed": 1.0, "Pause": 2, "Future": [1, 2]},
        robot_profile,
    ).payload
    assert settings == IdleMotionSettings(1.0, 2)


@pytest.mark.parametrize("value", [[], "idle", 1, None, True])
def test_idle_motion_rejects_wrong_top_level_type(value, robot_profile):
    with pytest.raises(InvalidTopLevelTypeError):
        decode("play_idle_motion", value, robot_profile)


@pytest.mark.parametrize(
    "command,value,model_type",
    [
        ("play_pose", valid_pose(), Pose),
        ("play_motion", [valid_pose()], Motion),
        ("play_idle_motion", {}, IdleMotionSettings),
    ],
)
def test_json_commands_return_expected_models(
    command, value, model_type, robot_profile
):
    decoded = decode(command, value, robot_profile)
    assert decoded.command == command
    assert isinstance(decoded.payload, model_type)


def test_play_wav_preserves_bytes_without_parsing(robot_profile):
    payload = b"\x00RIFFnot validated here\xff"
    original = request("play_wav", payload)
    decoded = decode_request(original, robot_profile)
    assert decoded == DecodedCommand("play_wav", payload)
    assert decoded.payload is payload


@pytest.mark.parametrize(
    "command",
    [
        "stop_wav",
        "stop_pose",
        "stop_motion",
        "stop_idle_motion",
        "read_axes",
    ],
)
def test_payload_free_commands_return_none(command, robot_profile):
    decoded = decode_request(request(command, None), robot_profile)
    assert decoded == DecodedCommand(command, None)


def test_decode_request_does_not_modify_legacy_request(robot_profile):
    original = request("play_pose", json_bytes(valid_pose()))
    snapshot = tuple(original)
    decode_request(original, robot_profile)
    assert tuple(original) == snapshot


@pytest.mark.parametrize(
    "arguments",
    [
        {"max_pose_duration_ms": True},
        {"max_pose_duration_ms": -1},
        {"max_motion_poses": 0},
        {"max_motion_duration_ms": 1.5},
        {"max_idle_speed": float("inf")},
        {"max_idle_pause_ms": 1.0},
    ],
)
def test_validation_limits_reject_invalid_configuration(arguments):
    with pytest.raises((TypeError, ValueError)):
        ValidationLimits(**arguments)
