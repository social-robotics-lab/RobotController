"""Unit tests for the single-worker serialized command target."""

import math
import queue
import threading

import pytest

from robot_controller.command_service import (
    DEFAULT_COMMAND_ENQUEUE_TIMEOUT_SECONDS,
    DEFAULT_COMMAND_QUEUE_CAPACITY,
    DEFAULT_COMMAND_WORKER_THREAD_NAME,
    SerializedRobotCommandTarget,
    SerializedRobotCommandTargetConfig,
)
from robot_controller.command_target import (
    RecordingCommandTarget,
    RobotCommandTarget,
)
from robot_controller.errors import (
    CommandQueueFullError,
    CommandServiceAlreadyStartedError,
    CommandServiceNotStartedError,
    CommandServiceStoppedError,
    CommandWorkerStoppedError,
    ReentrantCommandError,
)
from robot_controller.models import IdleMotionSettings, Motion, Pose


def sample_values():
    pose = Pose(50, {"HEAD_Y": 1}, {})
    return (
        b"opaque-wav",
        pose,
        Motion([pose]),
        IdleMotionSettings(1.0, 1000),
    )


def start_service(downstream=None, config=None):
    if downstream is None:
        downstream = RecordingCommandTarget({"HEAD_Y": -4})
    service = SerializedRobotCommandTarget(downstream, config=config)
    service.start()
    assert service.wait_until_ready(2.0)
    return service


class ThreadRecordingTarget(RecordingCommandTarget):
    def __init__(self, read_axes_result=None):
        RecordingCommandTarget.__init__(
            self,
            read_axes_result=read_axes_result,
        )
        self.thread_ids = []
        self.thread_names = []

    def _record(self, command, payload):
        self.thread_ids.append(threading.current_thread().ident)
        self.thread_names.append(threading.current_thread().name)
        RecordingCommandTarget._record(self, command, payload)


@pytest.mark.parametrize(
    "field,value,error_type",
    [
        ("queue_capacity", 0, ValueError),
        ("queue_capacity", -1, ValueError),
        ("queue_capacity", True, TypeError),
        ("queue_capacity", 1.5, TypeError),
        ("queue_capacity", "1", TypeError),
        ("enqueue_timeout_seconds", 0, ValueError),
        ("enqueue_timeout_seconds", -1, ValueError),
        ("enqueue_timeout_seconds", True, TypeError),
        ("enqueue_timeout_seconds", "1", TypeError),
        ("enqueue_timeout_seconds", math.nan, ValueError),
        ("enqueue_timeout_seconds", math.inf, ValueError),
        ("enqueue_timeout_seconds", -math.inf, ValueError),
        ("worker_thread_name", "", ValueError),
        ("worker_thread_name", 1, TypeError),
    ],
)
def test_config_rejects_invalid_values(field, value, error_type):
    values = {
        "queue_capacity": DEFAULT_COMMAND_QUEUE_CAPACITY,
        "enqueue_timeout_seconds": (
            DEFAULT_COMMAND_ENQUEUE_TIMEOUT_SECONDS
        ),
        "worker_thread_name": DEFAULT_COMMAND_WORKER_THREAD_NAME,
    }
    values[field] = value

    with pytest.raises(error_type):
        SerializedRobotCommandTargetConfig(**values)


def test_config_defaults_are_bounded_and_deterministic():
    config = SerializedRobotCommandTargetConfig()

    assert config.queue_capacity == 16
    assert config.enqueue_timeout_seconds == 1.0
    assert config.worker_thread_name == "robot-command-worker"


def test_constructor_does_not_create_or_start_thread():
    before = tuple(threading.enumerate())
    service = SerializedRobotCommandTarget(RecordingCommandTarget())

    assert tuple(threading.enumerate()) == before
    assert service.is_ready is False
    assert service.is_stopped is False


def test_requires_robot_command_target_downstream():
    with pytest.raises(TypeError):
        SerializedRobotCommandTarget(object())


def test_call_before_start_is_rejected():
    service = SerializedRobotCommandTarget(RecordingCommandTarget())

    with pytest.raises(CommandServiceNotStartedError):
        service.stop_pose()


def test_worker_start_failure_is_reported_without_leaving_thread(monkeypatch):
    import robot_controller.command_service as module

    class FailingThread(object):
        ident = None
        daemon = None

        def __init__(self, target, name):
            self.target = target
            self.name = name

        def start(self):
            raise RuntimeError("thread start failed")

    monkeypatch.setattr(module.threading, "Thread", FailingThread)
    service = SerializedRobotCommandTarget(RecordingCommandTarget())

    with pytest.raises(RuntimeError):
        service.start()

    assert service.is_stopped
    assert service.wait_until_ready(0) is False
    with pytest.raises(CommandWorkerStoppedError):
        service.stop_pose()


def test_start_is_single_use_and_restart_after_shutdown_is_rejected():
    service = start_service()

    with pytest.raises(CommandServiceAlreadyStartedError):
        service.start()

    service.shutdown()
    assert service.is_stopped
    with pytest.raises(CommandServiceAlreadyStartedError):
        service.start()
    with pytest.raises(CommandServiceStoppedError):
        service.stop_pose()


def test_shutdown_before_start_is_safe_and_idempotent():
    service = SerializedRobotCommandTarget(RecordingCommandTarget())

    service.shutdown()
    service.shutdown()

    assert service.is_stopped
    assert not service.is_ready


def test_all_nine_methods_run_once_on_the_same_worker_thread():
    downstream = ThreadRecordingTarget({"HEAD_Y": -4})
    service = start_service(downstream)
    wav_data, pose, motion, settings = sample_values()
    caller_id = threading.current_thread().ident
    try:
        assert service.play_wav(wav_data) is None
        assert service.stop_wav() is None
        assert service.play_pose(pose) is None
        assert service.stop_pose() is None
        assert service.play_motion(motion) is None
        assert service.stop_motion() is None
        assert service.play_idle_motion(settings) is None
        assert service.stop_idle_motion() is None
        assert service.read_axes() == {"HEAD_Y": -4}
    finally:
        service.shutdown()

    assert downstream.commands == (
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
    assert len(set(downstream.thread_ids)) == 1
    assert downstream.thread_ids[0] != caller_id
    assert set(downstream.thread_names) == {
        DEFAULT_COMMAND_WORKER_THREAD_NAME
    }
    assert downstream.calls[0].payload is wav_data
    assert downstream.calls[2].payload is pose
    assert downstream.calls[4].payload is motion
    assert downstream.calls[6].payload is settings


def test_read_axes_returns_exact_downstream_mapping_object():
    axes = {"HEAD_Y": 3}

    class IdentityAxesTarget(RecordingCommandTarget):
        def read_axes(self):
            self._record("read_axes", None)
            return axes

    service = start_service(IdentityAxesTarget())
    try:
        assert service.read_axes() is axes
    finally:
        service.shutdown()


def test_downstream_exception_reaches_caller_and_worker_continues():
    failure = ValueError("downstream failure")
    downstream = RecordingCommandTarget(
        exceptions={"stop_pose": failure}
    )
    service = start_service(downstream)
    try:
        with pytest.raises(ValueError) as exc_info:
            service.stop_pose()
        assert exc_info.value is failure

        service.stop_motion()
    finally:
        service.shutdown()

    assert downstream.commands == ("stop_pose", "stop_motion")


def test_large_payload_is_absent_from_queue_error_text():
    secret_payload = b"secret" * 10000
    config = SerializedRobotCommandTargetConfig(
        queue_capacity=1,
        enqueue_timeout_seconds=0.01,
    )
    started = threading.Event()
    release = threading.Event()
    second_put = threading.Event()

    class BlockingTarget(RecordingCommandTarget):
        def play_wav(self, wav_data):
            started.set()
            assert release.wait(2.0)
            RecordingCommandTarget.play_wav(self, wav_data)

    downstream = BlockingTarget()
    service = start_service(downstream, config)
    first = threading.Thread(
        target=service.play_wav,
        args=(b"first",),
    )
    first.start()
    assert started.wait(2.0)

    original_put = service._queue.put

    def observed_put(item, block=True, timeout=None):
        original_put(item, block=block, timeout=timeout)
        second_put.set()

    service._queue.put = observed_put
    second = threading.Thread(target=service.stop_pose)
    second.start()
    assert second_put.wait(2.0)
    try:
        with pytest.raises(CommandQueueFullError) as exc_info:
            service.play_wav(secret_payload)
        assert "secret" not in str(exc_info.value)
    finally:
        release.set()
        first.join(2.0)
        second.join(2.0)
        service.shutdown()

    assert downstream.call_count("play_wav") == 1
    assert downstream.call_count("stop_pose") == 1


def test_queue_is_bounded_and_uses_configured_enqueue_timeout():
    config = SerializedRobotCommandTargetConfig(
        queue_capacity=3,
        enqueue_timeout_seconds=0.25,
    )
    service = SerializedRobotCommandTarget(
        RecordingCommandTarget(),
        config=config,
    )
    observed = []

    def fake_put(item, block=True, timeout=None):
        observed.append((block, timeout))
        raise queue.Full

    service._queue.put = fake_put
    service.start()
    assert service.wait_until_ready(2.0)
    try:
        with pytest.raises(CommandQueueFullError):
            service.stop_pose()
    finally:
        service.shutdown()

    assert service._queue.maxsize == 3
    assert observed == [(True, 0.25)]


def test_concurrent_calls_are_fifo_and_never_overlap():
    first_started = threading.Event()
    release_first = threading.Event()
    second_enqueued = threading.Event()

    class ExclusiveTarget(RecordingCommandTarget):
        def __init__(self):
            RecordingCommandTarget.__init__(self)
            self.active = 0
            self.maximum_active = 0
            self.lock = threading.Lock()

        def _record(self, command, payload):
            with self.lock:
                self.active += 1
                self.maximum_active = max(
                    self.maximum_active,
                    self.active,
                )
            try:
                if command == "stop_pose":
                    first_started.set()
                    assert release_first.wait(2.0)
                RecordingCommandTarget._record(self, command, payload)
            finally:
                with self.lock:
                    self.active -= 1

    downstream = ExclusiveTarget()
    service = start_service(downstream)
    first = threading.Thread(target=service.stop_pose)
    first.start()
    assert first_started.wait(2.0)

    original_put = service._queue.put

    def observed_put(item, block=True, timeout=None):
        original_put(item, block=block, timeout=timeout)
        if item.command == "stop_motion":
            second_enqueued.set()

    service._queue.put = observed_put
    second = threading.Thread(target=service.stop_motion)
    second.start()
    assert second_enqueued.wait(2.0)
    release_first.set()
    first.join(2.0)
    second.join(2.0)
    service.shutdown()

    assert not first.is_alive()
    assert not second.is_alive()
    assert downstream.commands == ("stop_pose", "stop_motion")
    assert downstream.maximum_active == 1


def test_shutdown_drains_accepted_work_and_leaves_no_worker_thread():
    started = threading.Event()
    release = threading.Event()

    class BlockingTarget(RecordingCommandTarget):
        def stop_pose(self):
            started.set()
            assert release.wait(2.0)
            RecordingCommandTarget.stop_pose(self)

    service = start_service(BlockingTarget())
    caller = threading.Thread(target=service.stop_pose)
    caller.start()
    assert started.wait(2.0)

    shutdown_finished = threading.Event()

    def shutdown():
        service.shutdown()
        shutdown_finished.set()

    shutdown_thread = threading.Thread(target=shutdown)
    shutdown_thread.start()
    with pytest.raises(CommandServiceStoppedError):
        service.stop_motion()
    assert not shutdown_finished.is_set()

    release.set()
    caller.join(2.0)
    shutdown_thread.join(2.0)

    assert shutdown_finished.is_set()
    assert service.is_stopped
    assert not service.is_ready
    assert not any(
        thread.name == DEFAULT_COMMAND_WORKER_THREAD_NAME
        for thread in threading.enumerate()
    )


def test_reentrant_command_is_rejected_without_deadlock():
    captured = []
    service_holder = []

    class ReentrantTarget(RecordingCommandTarget):
        def stop_pose(self):
            try:
                service_holder[0].stop_motion()
            except BaseException as error:
                captured.append(error)
            RecordingCommandTarget.stop_pose(self)

    service = start_service(ReentrantTarget())
    service_holder.append(service)
    try:
        service.stop_pose()
    finally:
        service.shutdown()

    assert len(captured) == 1
    assert isinstance(captured[0], ReentrantCommandError)


def test_worker_thread_can_request_shutdown_without_self_join():
    service_holder = []

    class ShutdownTarget(RecordingCommandTarget):
        def stop_pose(self):
            service_holder[0].shutdown()
            RecordingCommandTarget.stop_pose(self)

    downstream = ShutdownTarget()
    service = start_service(downstream)
    service_holder.append(service)

    service.stop_pose()
    assert service.wait_until_stopped(2.0)
    assert downstream.commands == ("stop_pose",)
    assert service.is_stopped


def test_unexpected_worker_stop_is_distinguishable():
    service = SerializedRobotCommandTarget(RecordingCommandTarget())
    original_get = service._queue.get

    def fail_get(block=True, timeout=None):
        if block:
            raise RuntimeError("unexpected worker failure")
        return original_get(block=block, timeout=timeout)

    service._queue.get = fail_get
    service.start()
    assert service.wait_until_stopped(2.0)

    with pytest.raises(CommandWorkerStoppedError):
        service.stop_pose()


def test_shutdown_waits_for_unexpected_worker_cleanup(monkeypatch):
    import robot_controller.command_service as module

    service = SerializedRobotCommandTarget(RecordingCommandTarget())
    original_get = service._queue.get
    failure_reached = threading.Event()
    release_failure = threading.Event()

    def fail_get(block=True, timeout=None):
        if block:
            raise RuntimeError("unexpected worker failure")
        return original_get(block=block, timeout=timeout)

    def hold_failure_log(*args, **kwargs):
        failure_reached.set()
        assert release_failure.wait(2.0)

    service._queue.get = fail_get
    monkeypatch.setattr(module.logger, "error", hold_failure_log)
    service.start()
    assert failure_reached.wait(2.0)

    shutdown_finished = threading.Event()

    def shutdown():
        service.shutdown()
        shutdown_finished.set()

    shutdown_thread = threading.Thread(target=shutdown)
    shutdown_thread.start()
    assert not shutdown_finished.wait(0.05)
    release_failure.set()
    shutdown_thread.join(2.0)

    assert shutdown_finished.is_set()
    assert service.is_stopped
