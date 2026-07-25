"""Unit tests for the recording high-level command target."""

import pytest

from robot_controller.command_target import (
    RecordingCommandTarget,
    RobotCommandTarget,
)
from robot_controller.models import IdleMotionSettings, Motion, Pose


def sample_pose():
    """Return one immutable Pose for recording tests."""
    return Pose(50, {"HEAD_Y": 1}, {})


def test_abstract_command_target_cannot_be_instantiated():
    with pytest.raises(TypeError):
        RobotCommandTarget()


def test_recording_target_preserves_call_order_and_payloads():
    target = RecordingCommandTarget()
    pose = sample_pose()
    motion = Motion([pose])
    settings = IdleMotionSettings(1.0, 1000)
    wav_data = b"wav"

    target.play_wav(wav_data)
    target.stop_wav()
    target.play_pose(pose)
    target.stop_pose()
    target.play_motion(motion)
    target.stop_motion()
    target.play_idle_motion(settings)
    target.stop_idle_motion()
    target.read_axes()

    assert target.commands == (
        "play_wav",
        "stop_wav",
        "play_pose",
        "stop_pose",
        "play_motion",
        "stop_motion",
        "play_idle_motion",
        "stop_idle_motion",
        "read_axes",
    )
    assert [call.payload for call in target.calls] == [
        wav_data,
        None,
        pose,
        None,
        motion,
        None,
        settings,
        None,
        None,
    ]


def test_recording_target_records_repeated_calls_and_counts():
    target = RecordingCommandTarget()
    pose = sample_pose()

    target.play_pose(pose)
    target.play_pose(pose)
    target.stop_pose()

    assert target.commands == ("play_pose", "play_pose", "stop_pose")
    assert target.call_count("play_pose") == 2
    assert target.call_count("stop_pose") == 1
    assert target.call_count("read_axes") == 0


def test_read_axes_setting_is_detached_from_original_mapping():
    axes = {"HEAD_Y": -3}
    target = RecordingCommandTarget(axes)
    axes["HEAD_Y"] = 99
    axes["EXTRA"] = 1

    assert target.read_axes() == {"HEAD_Y": -3}


def test_returned_axes_mapping_cannot_mutate_internal_setting():
    target = RecordingCommandTarget({"HEAD_Y": -3})
    returned = target.read_axes()
    returned["HEAD_Y"] = 99

    assert target.read_axes() == {"HEAD_Y": -3}


def test_set_read_axes_result_copies_new_mapping():
    target = RecordingCommandTarget()
    axes = {"HEAD_Y": 4}
    target.set_read_axes_result(axes)
    axes.clear()

    assert target.read_axes() == {"HEAD_Y": 4}


def test_exposed_call_records_cannot_mutate_internal_history():
    target = RecordingCommandTarget()
    target.stop_pose()
    exposed = target.calls

    assert isinstance(exposed, tuple)
    with pytest.raises(AttributeError):
        exposed.append("forged")
    copied = list(exposed)
    copied.append("forged")

    assert target.commands == ("stop_pose",)
    assert target.call_count("stop_pose") == 1


def test_configured_exception_is_raised_after_call_is_recorded():
    failure = RuntimeError("configured")
    target = RecordingCommandTarget(exceptions={"stop_motion": failure})

    with pytest.raises(RuntimeError) as exc_info:
        target.stop_motion()

    assert exc_info.value is failure
    assert target.commands == ("stop_motion",)


def test_set_exception_can_add_and_clear_failure():
    target = RecordingCommandTarget()
    failure = ValueError("configured")
    target.set_exception("read_axes", failure)

    with pytest.raises(ValueError):
        target.read_axes()

    target.set_exception("read_axes", None)
    assert target.read_axes() == {}

