"""Generation-safe ownership and time progression for robot motion modes."""

import collections
import logging
import threading
import time
import typing

from robot_controller.command_target import RobotCommandTarget
from robot_controller.errors import (
    MotionSchedulerAlreadyStartedError,
    MotionSchedulerNotStartedError,
    MotionSchedulerStoppedError,
    MotionSchedulerWorkerStoppedError,
)
from robot_controller.models import IdleMotionSettings, Motion, Pose


logger = logging.getLogger(__name__)


MOTION_STATE_NONE = "NONE"
MOTION_STATE_DIRECT_POSE = "DIRECT_POSE"
MOTION_STATE_MOTION = "MOTION"
MOTION_STATE_IDLE_MOTION = "IDLE_MOTION"

DEFAULT_MOTION_SCHEDULER_THREAD_NAME = "motion-scheduler"

_LIFECYCLE_NEW = "new"
_LIFECYCLE_STARTING = "starting"
_LIFECYCLE_READY = "ready"
_LIFECYCLE_STOPPING = "stopping"
_LIFECYCLE_STOPPED = "stopped"
_LIFECYCLE_FAILED = "failed"


_MotionSchedulerConfigBase = collections.namedtuple(
    "_MotionSchedulerConfigBase",
    ["thread_name"],
)


class MotionSchedulerConfig(_MotionSchedulerConfigBase):
    """Immutable implementation settings for the Scheduler thread."""

    __slots__ = ()

    def __new__(
        cls,
        thread_name=DEFAULT_MOTION_SCHEDULER_THREAD_NAME,
    ):
        # type: (str) -> MotionSchedulerConfig
        if not isinstance(thread_name, str):
            raise TypeError("thread_name must be a string")
        if not thread_name:
            raise ValueError("thread_name must not be empty")
        return _MotionSchedulerConfigBase.__new__(cls, thread_name)


_MotionFailureBase = collections.namedtuple(
    "_MotionFailureBase",
    [
        "generation",
        "command",
        "error_type",
        "sequence",
        "monotonic_time",
    ],
)


class MotionFailure(_MotionFailureBase):
    """Payload-free diagnostic snapshot for one asynchronous failure."""

    __slots__ = ()


def _default_wait_strategy(cancel_event, timeout_seconds):
    # type: (threading.Event, float) -> bool
    """Wait interruptibly and return whether cancellation was requested."""
    return cancel_event.wait(timeout_seconds)


class MotionSchedulingCommandTarget(RobotCommandTarget):
    """Coordinate Pose, Motion, and Idle Motion above a serialized Target.

    Motion poses are sent asynchronously in input order. Every downstream
    call still goes through the supplied Target; the Mock composition supplies
    SerializedRobotCommandTarget so hardware-facing calls remain single-threaded.
    """

    def __init__(self, downstream, config=None, wait_strategy=None):
        # type: (RobotCommandTarget, typing.Optional[MotionSchedulerConfig], typing.Optional[typing.Callable[[threading.Event, float], bool]]) -> None
        if not isinstance(downstream, RobotCommandTarget):
            raise TypeError("downstream must implement RobotCommandTarget")
        if config is None:
            config = MotionSchedulerConfig()
        if not isinstance(config, MotionSchedulerConfig):
            raise TypeError("config must be MotionSchedulerConfig")
        if wait_strategy is None:
            wait_strategy = _default_wait_strategy
        if not callable(wait_strategy):
            raise TypeError("wait_strategy must be callable")

        self._downstream = downstream
        self._config = config
        self._wait_strategy = wait_strategy

        self._condition = threading.Condition()
        self._control_lock = threading.Lock()
        self._startup_complete = threading.Event()
        self._stopped = threading.Event()

        self._lifecycle = _LIFECYCLE_NEW
        self._state = MOTION_STATE_NONE
        self._generation = 0
        self._active_motion = None  # type: typing.Optional[Motion]
        self._active_cancel = None  # type: typing.Optional[threading.Event]
        self._motion_dispatches = 0
        self._last_failure = None  # type: typing.Optional[MotionFailure]
        self._failure_sequence = 0
        self._thread = None  # type: typing.Optional[threading.Thread]
        self._thread_id = None  # type: typing.Optional[int]

    @property
    def config(self):
        # type: () -> MotionSchedulerConfig
        return self._config

    @property
    def state(self):
        # type: () -> str
        with self._condition:
            return self._state

    @property
    def generation(self):
        # type: () -> int
        with self._condition:
            return self._generation

    @property
    def last_failure(self):
        # type: () -> typing.Optional[MotionFailure]
        with self._condition:
            return self._last_failure

    @property
    def is_ready(self):
        # type: () -> bool
        with self._condition:
            return self._lifecycle == _LIFECYCLE_READY

    @property
    def is_stopped(self):
        # type: () -> bool
        return self._stopped.is_set()

    def start(self):
        # type: () -> None
        """Create and start the single-use Scheduler thread."""
        with self._condition:
            if self._lifecycle != _LIFECYCLE_NEW:
                raise MotionSchedulerAlreadyStartedError()
            self._lifecycle = _LIFECYCLE_STARTING
            worker = threading.Thread(
                target=self._worker_main,
                name=self._config.thread_name,
            )
            worker.daemon = False
            self._thread = worker
            try:
                worker.start()
            except BaseException:
                self._lifecycle = _LIFECYCLE_FAILED
                self._thread = None
                self._startup_complete.set()
                self._stopped.set()
                raise

    def wait_until_ready(self, timeout=None):
        # type: (typing.Optional[float]) -> bool
        if not self._startup_complete.wait(timeout):
            return False
        return self.is_ready

    def wait_until_stopped(self, timeout=None):
        # type: (typing.Optional[float]) -> bool
        return self._stopped.wait(timeout)

    def wait_until_state(self, expected_state, timeout=None):
        # type: (str, typing.Optional[float]) -> bool
        """Wait until the diagnostic motion state matches a value."""
        with self._condition:
            return self._condition.wait_for(
                lambda: self._state == expected_state,
                timeout,
            )

    def play_wav(self, wav_data):
        # type: (bytes) -> None
        with self._control_lock:
            self._require_ready()
            return self._downstream.play_wav(wav_data)

    def stop_wav(self):
        # type: () -> None
        with self._control_lock:
            self._require_ready()
            return self._downstream.stop_wav()

    def read_axes(self):
        # type: () -> typing.Mapping[str, int]
        with self._control_lock:
            self._require_ready()
            return self._downstream.read_axes()

    def play_pose(self, pose):
        # type: (Pose) -> None
        with self._control_lock:
            self._require_ready()
            with self._condition:
                previous_state = self._invalidate_active_locked()
                self._wait_for_motion_dispatches_locked()
            if previous_state == MOTION_STATE_IDLE_MOTION:
                self._downstream.stop_idle_motion()
            self._downstream.play_pose(pose)
            with self._condition:
                self._state = MOTION_STATE_DIRECT_POSE
                self._condition.notify_all()

    def stop_pose(self):
        # type: () -> None
        with self._control_lock:
            self._require_ready()
            with self._condition:
                if self._state != MOTION_STATE_DIRECT_POSE:
                    return
            self._downstream.stop_pose()
            with self._condition:
                if self._state == MOTION_STATE_DIRECT_POSE:
                    self._generation += 1
                    self._state = MOTION_STATE_NONE
                    self._condition.notify_all()

    def play_motion(self, motion):
        # type: (Motion) -> None
        with self._control_lock:
            self._require_ready()
            with self._condition:
                previous_state = self._invalidate_active_locked()
                self._wait_for_motion_dispatches_locked()
            if previous_state == MOTION_STATE_IDLE_MOTION:
                self._downstream.stop_idle_motion()
            with self._condition:
                self._require_ready_locked()
                cancel_event = threading.Event()
                self._active_motion = motion
                self._active_cancel = cancel_event
                self._state = MOTION_STATE_MOTION
                self._condition.notify_all()

    def stop_motion(self):
        # type: () -> None
        with self._control_lock:
            self._require_ready()
            with self._condition:
                if self._state != MOTION_STATE_MOTION:
                    return
                self._invalidate_active_locked()
                self._wait_for_motion_dispatches_locked()
            self._downstream.stop_pose()

    def play_idle_motion(self, settings):
        # type: (IdleMotionSettings) -> None
        with self._control_lock:
            self._require_ready()
            with self._condition:
                previous_state = self._invalidate_active_locked()
                self._wait_for_motion_dispatches_locked()
            if previous_state == MOTION_STATE_DIRECT_POSE:
                self._downstream.stop_pose()
            elif previous_state == MOTION_STATE_IDLE_MOTION:
                self._downstream.stop_idle_motion()
            self._downstream.play_idle_motion(settings)
            with self._condition:
                self._state = MOTION_STATE_IDLE_MOTION
                self._condition.notify_all()

    def stop_idle_motion(self):
        # type: () -> None
        with self._control_lock:
            self._require_ready()
            with self._condition:
                if self._state != MOTION_STATE_IDLE_MOTION:
                    return
            self._downstream.stop_idle_motion()
            with self._condition:
                if self._state == MOTION_STATE_IDLE_MOTION:
                    self._generation += 1
                    self._state = MOTION_STATE_NONE
                    self._condition.notify_all()

    def shutdown(self):
        # type: () -> None
        """Cancel active ownership without shutting down the downstream."""
        current_thread_id = threading.current_thread().ident
        with self._control_lock:
            with self._condition:
                if self._lifecycle == _LIFECYCLE_NEW:
                    self._lifecycle = _LIFECYCLE_STOPPED
                    self._state = MOTION_STATE_NONE
                    self._startup_complete.set()
                    self._stopped.set()
                    self._condition.notify_all()
                    return
                if self._lifecycle == _LIFECYCLE_STOPPED:
                    return
                if self._lifecycle != _LIFECYCLE_FAILED:
                    self._lifecycle = _LIFECYCLE_STOPPING
                    previous_state = self._invalidate_active_locked()
                    self._wait_for_motion_dispatches_locked()
                else:
                    previous_state = MOTION_STATE_NONE
                worker = self._thread
                called_from_worker = current_thread_id == self._thread_id

            if previous_state == MOTION_STATE_MOTION:
                self._downstream.stop_pose()
            elif previous_state == MOTION_STATE_IDLE_MOTION:
                self._downstream.stop_idle_motion()

        if worker is not None and not called_from_worker:
            worker.join()

    def _require_ready(self):
        # type: () -> None
        with self._condition:
            self._require_ready_locked()

    def _require_ready_locked(self):
        # type: () -> None
        if self._lifecycle in (_LIFECYCLE_NEW, _LIFECYCLE_STARTING):
            raise MotionSchedulerNotStartedError()
        if self._lifecycle in (
            _LIFECYCLE_STOPPING,
            _LIFECYCLE_STOPPED,
        ):
            raise MotionSchedulerStoppedError()
        if self._lifecycle == _LIFECYCLE_FAILED:
            raise MotionSchedulerWorkerStoppedError()

    def _invalidate_active_locked(self):
        # type: () -> str
        previous_state = self._state
        self._generation += 1
        if self._active_cancel is not None:
            self._active_cancel.set()
        self._active_motion = None
        self._active_cancel = None
        self._state = MOTION_STATE_NONE
        self._condition.notify_all()
        return previous_state

    def _wait_for_motion_dispatches_locked(self):
        # type: () -> None
        while self._motion_dispatches:
            self._condition.wait()

    def _motion_is_current_locked(self, generation, cancel_event):
        # type: (int, threading.Event) -> bool
        return (
            self._lifecycle == _LIFECYCLE_READY
            and self._state == MOTION_STATE_MOTION
            and self._generation == generation
            and self._active_cancel is cancel_event
            and not cancel_event.is_set()
        )

    def _worker_main(self):
        # type: () -> None
        try:
            with self._condition:
                self._thread_id = threading.current_thread().ident
                if self._lifecycle == _LIFECYCLE_STARTING:
                    self._lifecycle = _LIFECYCLE_READY
                self._startup_complete.set()
                self._condition.notify_all()

            while True:
                with self._condition:
                    self._condition.wait_for(
                        lambda: (
                            self._lifecycle != _LIFECYCLE_READY
                            or (
                                self._state == MOTION_STATE_MOTION
                                and self._active_motion is not None
                                and self._active_cancel is not None
                            )
                        )
                    )
                    if self._lifecycle != _LIFECYCLE_READY:
                        break
                    generation = self._generation
                    motion = self._active_motion
                    cancel_event = self._active_cancel

                self._run_motion(generation, motion, cancel_event)
        except BaseException as error:
            with self._condition:
                self._record_failure_locked(
                    self._generation,
                    "motion_scheduler",
                    error,
                )
                self._invalidate_active_locked()
                self._lifecycle = _LIFECYCLE_FAILED
            logger.error(
                "Motion Scheduler failed error_type=%s",
                type(error).__name__,
                exc_info=True,
            )
        finally:
            self._startup_complete.set()
            with self._condition:
                if self._lifecycle != _LIFECYCLE_FAILED:
                    self._lifecycle = _LIFECYCLE_STOPPED
                self._state = MOTION_STATE_NONE
                self._thread_id = None
                self._condition.notify_all()
            self._stopped.set()

    def _run_motion(self, generation, motion, cancel_event):
        # type: (int, Motion, threading.Event) -> None
        for pose in motion.poses:
            with self._condition:
                if not self._motion_is_current_locked(
                    generation, cancel_event
                ):
                    return
                self._motion_dispatches += 1

            error = None  # type: typing.Optional[BaseException]
            try:
                self._downstream.play_pose(pose)
            except BaseException as caught:
                error = caught
            finally:
                with self._condition:
                    self._motion_dispatches -= 1
                    self._condition.notify_all()

            if error is not None:
                self._finish_failed_motion(
                    generation,
                    cancel_event,
                    error,
                )
                return

            with self._condition:
                if not self._motion_is_current_locked(
                    generation, cancel_event
                ):
                    return

            try:
                cancelled = self._wait_strategy(
                    cancel_event,
                    pose.duration_ms / 1000.0,
                )
            except BaseException as error:
                self._finish_failed_motion(
                    generation,
                    cancel_event,
                    error,
                )
                return
            if cancelled:
                return

            with self._condition:
                if not self._motion_is_current_locked(
                    generation, cancel_event
                ):
                    return

        with self._condition:
            if self._motion_is_current_locked(
                generation, cancel_event
            ):
                self._active_motion = None
                self._active_cancel = None
                self._state = MOTION_STATE_NONE
                self._condition.notify_all()

    def _finish_failed_motion(self, generation, cancel_event, error):
        # type: (int, threading.Event, BaseException) -> None
        recorded = False
        with self._condition:
            if self._motion_is_current_locked(
                generation, cancel_event
            ):
                self._record_failure_locked(
                    generation,
                    "play_motion",
                    error,
                )
                cancel_event.set()
                self._active_motion = None
                self._active_cancel = None
                self._state = MOTION_STATE_NONE
                self._condition.notify_all()
                recorded = True
        if recorded:
            logger.error(
                (
                    "Asynchronous motion failed command=play_motion "
                    "generation=%d error_type=%s"
                ),
                generation,
                type(error).__name__,
            )

    def _record_failure_locked(self, generation, command, error):
        # type: (int, str, BaseException) -> None
        self._failure_sequence += 1
        self._last_failure = MotionFailure(
            generation,
            command,
            type(error).__name__,
            self._failure_sequence,
            time.monotonic(),
        )
