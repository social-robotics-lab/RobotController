"""Unit and concurrency tests for MotionSchedulingCommandTarget."""

import threading

import pytest

from robot_controller.command_service import SerializedRobotCommandTarget
from robot_controller.command_target import RecordingCommandTarget
from robot_controller.errors import (
    MotionSchedulerAlreadyStartedError,
    MotionSchedulerNotStartedError,
    MotionSchedulerStoppedError,
)
from robot_controller.models import IdleMotionSettings, Motion, Pose
from robot_controller.motion_scheduler import (
    MOTION_STATE_DIRECT_POSE,
    MOTION_STATE_IDLE_MOTION,
    MOTION_STATE_MOTION,
    MOTION_STATE_NONE,
    MotionSchedulerConfig,
    MotionSchedulingCommandTarget,
)


def pose(position, duration_ms=0):
    return Pose(duration_ms, {"HEAD_Y": position}, {})


class NotifyingTarget(RecordingCommandTarget):
    """Recording target with deterministic command-count notification."""

    def __init__(self, read_axes_result=None):
        RecordingCommandTarget.__init__(
            self,
            read_axes_result=read_axes_result,
        )
        self._condition = threading.Condition()
        self.thread_ids = []

    def _record(self, command, payload):
        with self._condition:
            self.thread_ids.append(threading.current_thread().ident)
            RecordingCommandTarget._record(self, command, payload)
            self._condition.notify_all()

    def wait_for_count(self, command, count, timeout=2.0):
        with self._condition:
            return self._condition.wait_for(
                lambda: self.call_count(command) >= count,
                timeout,
            )


class ImmediateWaiter(object):
    def __init__(self):
        self.timeouts = []
        self.cancel_events = []

    def __call__(self, cancel_event, timeout_seconds):
        self.timeouts.append(timeout_seconds)
        self.cancel_events.append(cancel_event)
        return cancel_event.is_set()


class FirstCancelThenImmediateWaiter(object):
    def __init__(self):
        self.timeouts = []
        self.first_waiting = threading.Event()

    def __call__(self, cancel_event, timeout_seconds):
        self.timeouts.append(timeout_seconds)
        if len(self.timeouts) == 1:
            self.first_waiting.set()
            return cancel_event.wait(2.0)
        return cancel_event.is_set()


def start_scheduler(downstream=None, waiter=None, config=None):
    if downstream is None:
        downstream = NotifyingTarget({"HEAD_Y": 0})
    if waiter is None:
        waiter = ImmediateWaiter()
    scheduler = MotionSchedulingCommandTarget(
        downstream,
        config=config,
        wait_strategy=waiter,
    )
    scheduler.start()
    assert scheduler.wait_until_ready(2.0)
    return scheduler


def test_constructor_does_not_start_thread_and_defaults_are_stable():
    before = tuple(threading.enumerate())
    config = MotionSchedulerConfig()
    scheduler = MotionSchedulingCommandTarget(
        RecordingCommandTarget(),
        config=config,
    )

    assert tuple(threading.enumerate()) == before
    assert config.thread_name == "motion-scheduler"
    assert scheduler.state == MOTION_STATE_NONE
    assert scheduler.generation == 0
    assert scheduler.last_failure is None
    assert not scheduler.is_ready
    assert not scheduler.is_stopped


@pytest.mark.parametrize("thread_name", ["", 1, None])
def test_config_rejects_invalid_thread_name(thread_name):
    error_type = ValueError if thread_name == "" else TypeError
    with pytest.raises(error_type):
        MotionSchedulerConfig(thread_name=thread_name)


def test_requires_target_and_callable_wait_strategy():
    with pytest.raises(TypeError):
        MotionSchedulingCommandTarget(object())
    with pytest.raises(TypeError):
        MotionSchedulingCommandTarget(
            RecordingCommandTarget(),
            wait_strategy=object(),
        )


def test_start_before_after_and_multiple_start_lifecycle():
    scheduler = MotionSchedulingCommandTarget(RecordingCommandTarget())
    with pytest.raises(MotionSchedulerNotStartedError):
        scheduler.read_axes()

    scheduler.start()
    assert scheduler.wait_until_ready(2.0)
    assert scheduler.is_ready
    with pytest.raises(MotionSchedulerAlreadyStartedError):
        scheduler.start()

    scheduler.shutdown()
    scheduler.shutdown()
    assert scheduler.is_stopped
    assert not scheduler.is_ready
    with pytest.raises(MotionSchedulerStoppedError):
        scheduler.stop_motion()
    with pytest.raises(MotionSchedulerAlreadyStartedError):
        scheduler.start()


def test_scheduler_thread_start_failure_leaves_stopped_state(monkeypatch):
    import robot_controller.motion_scheduler as module

    class FailingThread(object):
        ident = None
        daemon = None

        def __init__(self, target, name):
            self.target = target
            self.name = name

        def start(self):
            raise RuntimeError("scheduler thread start failed")

    monkeypatch.setattr(module.threading, "Thread", FailingThread)
    scheduler = MotionSchedulingCommandTarget(RecordingCommandTarget())

    with pytest.raises(RuntimeError):
        scheduler.start()

    assert scheduler.is_stopped
    assert not scheduler.wait_until_ready(0)


def test_shutdown_before_start_is_idempotent_and_prevents_restart():
    scheduler = MotionSchedulingCommandTarget(RecordingCommandTarget())

    scheduler.shutdown()
    scheduler.shutdown()

    assert scheduler.is_stopped
    with pytest.raises(MotionSchedulerAlreadyStartedError):
        scheduler.start()


def test_motion_sends_poses_in_order_once_and_waits_by_duration():
    downstream = NotifyingTarget()
    waiter = ImmediateWaiter()
    scheduler = start_scheduler(downstream, waiter)
    poses = (pose(1, 0), pose(2, 250), pose(3, 1000))
    try:
        scheduler.play_motion(Motion(poses))
        assert scheduler.wait_until_state(MOTION_STATE_NONE, 2.0)
    finally:
        scheduler.shutdown()

    assert downstream.commands == (
        "play_pose",
        "play_pose",
        "play_pose",
    )
    assert tuple(call.payload for call in downstream.calls) == poses
    assert waiter.timeouts == [0.0, 0.25, 1.0]
    assert downstream.call_count("play_motion") == 0


def test_play_motion_returns_before_motion_completion():
    downstream = NotifyingTarget()
    waiter = FirstCancelThenImmediateWaiter()
    scheduler = start_scheduler(downstream, waiter)
    try:
        scheduler.play_motion(Motion([pose(1, 5000), pose(2)]))
        assert waiter.first_waiting.wait(2.0)
        assert scheduler.state == MOTION_STATE_MOTION
        assert downstream.call_count("play_pose") == 1
    finally:
        scheduler.stop_motion()
        scheduler.shutdown()


def test_stop_motion_interrupts_wait_and_prevents_remaining_pose():
    downstream = NotifyingTarget()
    waiter = FirstCancelThenImmediateWaiter()
    scheduler = start_scheduler(downstream, waiter)
    motion = Motion([pose(1, 5000), pose(2)])
    try:
        scheduler.play_motion(motion)
        assert waiter.first_waiting.wait(2.0)

        scheduler.stop_motion()

        assert scheduler.state == MOTION_STATE_NONE
        assert downstream.call_count("play_pose") == 1
        assert downstream.call_count("stop_pose") == 1
    finally:
        scheduler.shutdown()


def test_stop_motion_without_motion_is_noop():
    downstream = NotifyingTarget()
    scheduler = start_scheduler(downstream)
    try:
        generation = scheduler.generation
        scheduler.stop_motion()
        assert generation == scheduler.generation
    finally:
        scheduler.shutdown()

    assert downstream.commands == ()


def test_new_motion_replaces_old_without_old_completion_overwrite():
    downstream = NotifyingTarget()
    waiter = FirstCancelThenImmediateWaiter()
    scheduler = start_scheduler(downstream, waiter)
    motion_a = Motion([pose(1, 5000), pose(2)])
    motion_b = Motion([pose(10), pose(11)])
    try:
        scheduler.play_motion(motion_a)
        assert waiter.first_waiting.wait(2.0)
        generation_a = scheduler.generation

        scheduler.play_motion(motion_b)
        generation_b = scheduler.generation
        assert generation_b > generation_a
        assert scheduler.wait_until_state(MOTION_STATE_NONE, 2.0)
    finally:
        scheduler.shutdown()

    positions = [
        call.payload.servo_positions["HEAD_Y"]
        for call in downstream.calls
        if call.command == "play_pose"
    ]
    assert positions == [1, 10, 11]


def test_play_pose_cancels_motion_and_becomes_direct_owner():
    downstream = NotifyingTarget()
    waiter = FirstCancelThenImmediateWaiter()
    scheduler = start_scheduler(downstream, waiter)
    direct_pose = pose(99)
    try:
        scheduler.play_motion(Motion([pose(1, 5000), pose(2)]))
        assert waiter.first_waiting.wait(2.0)

        scheduler.play_pose(direct_pose)

        assert scheduler.state == MOTION_STATE_DIRECT_POSE
        assert downstream.calls[-1].payload is direct_pose
        assert downstream.call_count("play_pose") == 2
    finally:
        scheduler.shutdown()


def test_stop_pose_only_stops_direct_pose():
    downstream = NotifyingTarget()
    waiter = FirstCancelThenImmediateWaiter()
    scheduler = start_scheduler(downstream, waiter)
    try:
        scheduler.play_motion(Motion([pose(1, 5000), pose(2)]))
        assert waiter.first_waiting.wait(2.0)

        scheduler.stop_pose()

        assert scheduler.state == MOTION_STATE_MOTION
        assert downstream.call_count("stop_pose") == 0
    finally:
        scheduler.stop_motion()
        scheduler.shutdown()


def test_play_pose_stops_idle_before_direct_pose():
    downstream = NotifyingTarget()
    scheduler = start_scheduler(downstream)
    settings = IdleMotionSettings(1.0, 1000)
    direct = pose(4)
    try:
        scheduler.play_idle_motion(settings)
        scheduler.play_pose(direct)
        assert scheduler.state == MOTION_STATE_DIRECT_POSE
    finally:
        scheduler.shutdown()

    assert downstream.commands == (
        "play_idle_motion",
        "stop_idle_motion",
        "play_pose",
    )


def test_play_motion_stops_idle_and_runs_motion():
    downstream = NotifyingTarget()
    scheduler = start_scheduler(downstream)
    settings = IdleMotionSettings(1.0, 1000)
    try:
        scheduler.play_idle_motion(settings)
        scheduler.play_motion(Motion([pose(4)]))
        assert scheduler.wait_until_state(MOTION_STATE_NONE, 2.0)
    finally:
        scheduler.shutdown()

    assert downstream.commands == (
        "play_idle_motion",
        "stop_idle_motion",
        "play_pose",
    )


def test_play_idle_replaces_existing_idle_and_stop_motion_is_noop():
    downstream = NotifyingTarget()
    scheduler = start_scheduler(downstream)
    first = IdleMotionSettings(1.0, 1000)
    second = IdleMotionSettings(2.0, 500)
    try:
        scheduler.play_idle_motion(first)
        generation = scheduler.generation
        scheduler.stop_motion()
        assert scheduler.state == MOTION_STATE_IDLE_MOTION
        assert scheduler.generation == generation

        scheduler.play_idle_motion(second)
        assert scheduler.state == MOTION_STATE_IDLE_MOTION
    finally:
        scheduler.shutdown()

    assert downstream.commands == (
        "play_idle_motion",
        "stop_idle_motion",
        "play_idle_motion",
        "stop_idle_motion",
    )
    assert downstream.calls[0].payload is first
    assert downstream.calls[2].payload is second


def test_play_idle_cancels_motion_and_stops_direct_pose():
    downstream = NotifyingTarget()
    waiter = FirstCancelThenImmediateWaiter()
    scheduler = start_scheduler(downstream, waiter)
    settings = IdleMotionSettings(1.0, 1000)
    try:
        scheduler.play_motion(Motion([pose(1, 5000), pose(2)]))
        assert waiter.first_waiting.wait(2.0)
        scheduler.play_idle_motion(settings)
        assert scheduler.state == MOTION_STATE_IDLE_MOTION

        scheduler.play_pose(pose(9))
        scheduler.play_idle_motion(settings)
        assert scheduler.state == MOTION_STATE_IDLE_MOTION
    finally:
        scheduler.shutdown()

    assert downstream.call_count("play_pose") == 2
    assert downstream.call_count("stop_pose") == 1
    assert downstream.call_count("play_idle_motion") == 2


def test_stop_idle_only_stops_idle():
    downstream = NotifyingTarget()
    waiter = FirstCancelThenImmediateWaiter()
    scheduler = start_scheduler(downstream, waiter)
    try:
        scheduler.play_motion(Motion([pose(1, 5000), pose(2)]))
        assert waiter.first_waiting.wait(2.0)
        scheduler.stop_idle_motion()
        assert scheduler.state == MOTION_STATE_MOTION
        assert downstream.call_count("stop_idle_motion") == 0
    finally:
        scheduler.stop_motion()
        scheduler.shutdown()


def test_audio_and_read_axes_do_not_change_motion_state_or_values():
    axes = {"HEAD_Y": -3}

    class IdentityAxesTarget(NotifyingTarget):
        def read_axes(self):
            self._record("read_axes", None)
            return axes

    downstream = IdentityAxesTarget()
    waiter = FirstCancelThenImmediateWaiter()
    scheduler = start_scheduler(downstream, waiter)
    wav_data = b"opaque-wav"
    try:
        scheduler.play_motion(Motion([pose(1, 5000), pose(2)]))
        assert waiter.first_waiting.wait(2.0)
        generation = scheduler.generation

        scheduler.play_wav(wav_data)
        scheduler.stop_wav()
        result = scheduler.read_axes()

        assert result is axes
        assert scheduler.state == MOTION_STATE_MOTION
        assert scheduler.generation == generation
        assert downstream.calls[-3].payload is wav_data
    finally:
        scheduler.stop_motion()
        scheduler.shutdown()


def test_async_pose_failure_stops_motion_records_failure_and_recovers(
    caplog,
):
    failed = threading.Event()

    class FailingSecondPoseTarget(NotifyingTarget):
        def __init__(self):
            NotifyingTarget.__init__(self)
            self.pose_number = 0

        def play_pose(self, value):
            self.pose_number += 1
            self._record("play_pose", value)
            if self.pose_number == 2:
                failed.set()
                raise ValueError("secret-pose-detail")

    downstream = FailingSecondPoseTarget()
    scheduler = start_scheduler(downstream)
    try:
        with caplog.at_level(
            "ERROR",
            logger="robot_controller.motion_scheduler",
        ):
            scheduler.play_motion(
                Motion([pose(1), pose(2), pose(3)])
            )
            assert failed.wait(2.0)
            assert scheduler.wait_until_state(MOTION_STATE_NONE, 2.0)
            failure = scheduler.last_failure

            scheduler.play_motion(Motion([pose(9)]))
            assert scheduler.wait_until_state(MOTION_STATE_NONE, 2.0)
            assert scheduler.is_ready
    finally:
        scheduler.shutdown()

    assert failure.command == "play_motion"
    assert failure.error_type == "ValueError"
    assert "secret-pose-detail" not in repr(failure)
    assert "secret-pose-detail" not in caplog.text
    assert "generation=" in caplog.text
    assert "error_type=ValueError" in caplog.text
    positions = [
        call.payload.servo_positions["HEAD_Y"]
        for call in downstream.calls
    ]
    assert positions == [1, 2, 9]


def test_motion_internal_calls_still_use_serialized_single_worker():
    target = NotifyingTarget()
    service = SerializedRobotCommandTarget(target)
    service.start()
    assert service.wait_until_ready(2.0)
    scheduler = start_scheduler(service)
    try:
        scheduler.play_motion(Motion([pose(1), pose(2)]))
        assert scheduler.wait_until_state(MOTION_STATE_NONE, 2.0)
    finally:
        scheduler.shutdown()
        service.shutdown()

    assert len(set(target.thread_ids)) == 1
    assert target.thread_ids[0] != threading.current_thread().ident
    assert target.commands == ("play_pose", "play_pose")


def test_state_lock_is_available_while_downstream_call_is_blocked():
    entered = threading.Event()
    release = threading.Event()

    class BlockingTarget(NotifyingTarget):
        def play_pose(self, value):
            entered.set()
            assert release.wait(2.0)
            NotifyingTarget.play_pose(self, value)

    scheduler = start_scheduler(BlockingTarget())
    caller = threading.Thread(target=scheduler.play_pose, args=(pose(1),))
    caller.start()
    assert entered.wait(2.0)
    try:
        assert scheduler.state == MOTION_STATE_NONE
        assert scheduler.generation > 0
    finally:
        release.set()
        caller.join(2.0)
        scheduler.shutdown()


def test_shutdown_cancels_motion_stops_pose_and_leaves_no_thread():
    downstream = NotifyingTarget()
    waiter = FirstCancelThenImmediateWaiter()
    config = MotionSchedulerConfig(thread_name="test-motion-scheduler")
    scheduler = start_scheduler(downstream, waiter, config)
    scheduler.play_motion(Motion([pose(1, 5000), pose(2)]))
    assert waiter.first_waiting.wait(2.0)

    scheduler.shutdown()
    scheduler.shutdown()

    assert scheduler.is_stopped
    assert downstream.call_count("stop_pose") == 1
    assert not any(
        thread.name == "test-motion-scheduler"
        for thread in threading.enumerate()
    )


def test_shutdown_stops_active_idle_without_stopping_downstream_service():
    downstream = NotifyingTarget()
    scheduler = start_scheduler(downstream)
    scheduler.play_idle_motion(IdleMotionSettings(1.0, 1000))

    scheduler.shutdown()

    assert downstream.commands == (
        "play_idle_motion",
        "stop_idle_motion",
    )
    assert scheduler.is_stopped


def test_scheduler_thread_can_request_shutdown_without_self_join():
    scheduler_holder = []
    called = threading.Event()

    def shutdown_waiter(cancel_event, timeout_seconds):
        scheduler_holder[0].shutdown()
        called.set()
        return True

    downstream = NotifyingTarget()
    scheduler = start_scheduler(downstream, shutdown_waiter)
    scheduler_holder.append(scheduler)

    scheduler.play_motion(Motion([pose(1, 1000)]))

    assert called.wait(2.0)
    assert scheduler.wait_until_stopped(2.0)
    assert scheduler.is_stopped
