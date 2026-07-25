"""Unit tests for validated command routing."""

import json

import pytest

from robot_controller.command_target import RecordingCommandTarget
from robot_controller.errors import (
    CommandExecutionError,
    InvalidAxesError,
    InvalidDecodedCommandError,
)
from robot_controller.models import (
    DecodedCommand,
    IdleMotionSettings,
    Motion,
    Pose,
)
from robot_controller.router import CommandDispatchResult, CommandRouter


def sample_pose():
    """Return a small immutable validated Pose."""
    return Pose(50, {"HEAD_Y": 2}, {"Mouth": 3})


def sample_motion():
    """Return a small immutable validated Motion."""
    return Motion([sample_pose(), Pose(10, {"HEAD_Y": -2}, {})])


def sample_idle_settings():
    """Return immutable validated idle-motion settings."""
    return IdleMotionSettings(1.5, 250)


@pytest.mark.parametrize(
    "command,payload",
    [
        ("play_wav", b"RIFFopaque bytes"),
        ("stop_wav", None),
        ("play_pose", sample_pose()),
        ("stop_pose", None),
        ("play_motion", sample_motion()),
        ("stop_motion", None),
        ("play_idle_motion", sample_idle_settings()),
        ("stop_idle_motion", None),
    ],
)
def test_non_response_command_calls_only_matching_target_method_once(
    command, payload
):
    target = RecordingCommandTarget()
    router = CommandRouter(target)
    decoded = DecodedCommand(command, payload)

    result = router.dispatch(decoded)

    assert result == CommandDispatchResult(None)
    assert result.response_payload is None
    assert target.commands == (command,)
    assert target.calls[0].payload is payload
    assert target.call_count(command) == 1


def test_read_axes_calls_only_read_axes_once_and_returns_json_bytes():
    target = RecordingCommandTarget({"HEAD_Y": -2})
    result = CommandRouter(target).dispatch(DecodedCommand("read_axes", None))

    assert target.commands == ("read_axes",)
    assert target.call_count("read_axes") == 1
    assert result.response_payload == b'{"HEAD_Y":-2}'
    assert json.loads(result.response_payload.decode("utf-8")) == {
        "HEAD_Y": -2
    }


@pytest.mark.parametrize(
    "command,payload",
    [
        ("play_wav", b"data"),
        ("play_pose", sample_pose()),
        ("play_motion", sample_motion()),
        ("play_idle_motion", sample_idle_settings()),
    ],
)
def test_play_commands_do_not_add_ack_or_empty_response(command, payload):
    result = CommandRouter(RecordingCommandTarget()).dispatch(
        DecodedCommand(command, payload)
    )
    assert result.response_payload is None


@pytest.mark.parametrize(
    "command",
    ["stop_wav", "stop_pose", "stop_motion", "stop_idle_motion"],
)
def test_stop_commands_do_not_add_ack_or_empty_response(command):
    result = CommandRouter(RecordingCommandTarget()).dispatch(
        DecodedCommand(command, None)
    )
    assert result.response_payload is None


def test_router_does_not_modify_decoded_command_or_internal_model():
    pose = sample_pose()
    decoded = DecodedCommand("play_pose", pose)
    snapshot = tuple(decoded)

    CommandRouter(RecordingCommandTarget()).dispatch(decoded)

    assert tuple(decoded) == snapshot
    assert decoded.payload is pose
    assert dict(pose.servo_positions) == {"HEAD_Y": 2}
    assert dict(pose.led_values) == {"Mouth": 3}


@pytest.mark.parametrize(
    "command,payload,expected",
    [
        ("play_pose", {}, "Pose"),
        ("play_motion", [sample_pose()], "Motion"),
        (
            "play_idle_motion",
            {"Speed": 1.0, "Pause": 1000},
            "IdleMotionSettings",
        ),
        ("play_wav", bytearray(b"wav"), "bytes"),
    ],
)
def test_router_rejects_wrong_play_payload_type(
    command, payload, expected
):
    target = RecordingCommandTarget()
    with pytest.raises(InvalidDecodedCommandError) as exc_info:
        CommandRouter(target).dispatch(DecodedCommand(command, payload))
    assert exc_info.value.command == command
    assert expected in exc_info.value.expected
    assert target.calls == ()


@pytest.mark.parametrize(
    "command",
    ["stop_wav", "stop_pose", "stop_motion", "stop_idle_motion"],
)
def test_router_rejects_extra_stop_payload(command):
    target = RecordingCommandTarget()
    with pytest.raises(InvalidDecodedCommandError):
        CommandRouter(target).dispatch(DecodedCommand(command, b"extra"))
    assert target.calls == ()


def test_router_rejects_extra_read_axes_payload():
    target = RecordingCommandTarget()
    with pytest.raises(InvalidDecodedCommandError):
        CommandRouter(target).dispatch(
            DecodedCommand("read_axes", {"unexpected": True})
        )
    assert target.calls == ()


def test_router_rejects_unknown_command_without_target_call():
    target = RecordingCommandTarget()
    with pytest.raises(InvalidDecodedCommandError) as exc_info:
        CommandRouter(target).dispatch(DecodedCommand("unknown", None))
    assert exc_info.value.command == "unknown"
    assert target.calls == ()


def test_router_rejects_non_decoded_command():
    target = RecordingCommandTarget()
    with pytest.raises(InvalidDecodedCommandError):
        CommandRouter(target).dispatch(("play_pose", sample_pose()))
    assert target.calls == ()


def test_target_exception_is_wrapped_with_command_and_cause():
    failure = RuntimeError("target failed")
    target = RecordingCommandTarget(exceptions={"play_pose": failure})

    with pytest.raises(CommandExecutionError) as exc_info:
        CommandRouter(target).dispatch(
            DecodedCommand("play_pose", sample_pose())
        )

    assert exc_info.value.command == "play_pose"
    assert exc_info.value.__cause__ is failure
    assert target.commands == ("play_pose",)


def test_huge_payload_is_not_in_execution_error_message():
    wav_data = b"x" * (1024 * 1024)
    failure = RuntimeError("audio target failed")
    target = RecordingCommandTarget(exceptions={"play_wav": failure})

    with pytest.raises(CommandExecutionError) as exc_info:
        CommandRouter(target).dispatch(DecodedCommand("play_wav", wav_data))

    assert exc_info.value.command == "play_wav"
    assert repr(wav_data) not in str(exc_info.value)
    assert len(str(exc_info.value)) < 200


def test_large_motion_is_not_in_execution_error_message():
    pose = sample_pose()
    motion = Motion([pose] * 1000)
    failure = RuntimeError("motion target failed")
    target = RecordingCommandTarget(exceptions={"play_motion": failure})

    with pytest.raises(CommandExecutionError) as exc_info:
        CommandRouter(target).dispatch(
            DecodedCommand("play_motion", motion)
        )

    assert exc_info.value.command == "play_motion"
    assert repr(motion) not in str(exc_info.value)
    assert len(str(exc_info.value)) < 200


def test_invalid_read_axes_result_is_execution_failure():
    target = RecordingCommandTarget({"HEAD_Y": True})

    with pytest.raises(CommandExecutionError) as exc_info:
        CommandRouter(target).dispatch(DecodedCommand("read_axes", None))

    assert exc_info.value.command == "read_axes"
    assert isinstance(exc_info.value.__cause__, InvalidAxesError)
