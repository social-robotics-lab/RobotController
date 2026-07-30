"""Synchronous high-level commands serialized through one worker thread."""

import collections
import logging
import math
import queue
import threading
import typing

from robot_controller.command_target import RobotCommandTarget
from robot_controller.errors import (
    CommandQueueFullError,
    CommandServiceAlreadyStartedError,
    CommandServiceNotStartedError,
    CommandServiceStoppedError,
    CommandWorkerStoppedError,
    ReentrantCommandError,
)
from robot_controller.models import IdleMotionSettings, Motion, Pose


logger = logging.getLogger(__name__)


DEFAULT_COMMAND_QUEUE_CAPACITY = 16
DEFAULT_COMMAND_ENQUEUE_TIMEOUT_SECONDS = 1.0
DEFAULT_COMMAND_WORKER_THREAD_NAME = "robot-command-worker"
_WORKER_QUEUE_POLL_SECONDS = 0.1

_STATE_NEW = "new"
_STATE_STARTING = "starting"
_STATE_READY = "ready"
_STATE_STOPPING = "stopping"
_STATE_STOPPED = "stopped"
_STATE_FAILED = "failed"


_SerializedRobotCommandTargetConfigBase = collections.namedtuple(
    "_SerializedRobotCommandTargetConfigBase",
    [
        "queue_capacity",
        "enqueue_timeout_seconds",
        "worker_thread_name",
    ],
)


class SerializedRobotCommandTargetConfig(
    _SerializedRobotCommandTargetConfigBase
):
    """Immutable implementation settings for the single command worker."""

    __slots__ = ()

    def __new__(
        cls,
        queue_capacity=DEFAULT_COMMAND_QUEUE_CAPACITY,
        enqueue_timeout_seconds=DEFAULT_COMMAND_ENQUEUE_TIMEOUT_SECONDS,
        worker_thread_name=DEFAULT_COMMAND_WORKER_THREAD_NAME,
    ):
        # type: (int, float, str) -> SerializedRobotCommandTargetConfig
        if isinstance(queue_capacity, bool) or not isinstance(
            queue_capacity, int
        ):
            raise TypeError("queue_capacity must be an integer")
        if queue_capacity < 1:
            raise ValueError("queue_capacity must be at least one")
        if isinstance(enqueue_timeout_seconds, bool) or not isinstance(
            enqueue_timeout_seconds, (int, float)
        ):
            raise TypeError("enqueue_timeout_seconds must be a number")
        if (
            not math.isfinite(enqueue_timeout_seconds)
            or enqueue_timeout_seconds <= 0
        ):
            raise ValueError(
                "enqueue_timeout_seconds must be finite and positive"
            )
        if not isinstance(worker_thread_name, str):
            raise TypeError("worker_thread_name must be a string")
        if not worker_thread_name:
            raise ValueError("worker_thread_name must not be empty")
        return _SerializedRobotCommandTargetConfigBase.__new__(
            cls,
            queue_capacity,
            enqueue_timeout_seconds,
            worker_thread_name,
        )


class _CommandWorkItem(object):
    """One private command invocation and its synchronous completion state."""

    __slots__ = (
        "command",
        "payload",
        "has_payload",
        "completed",
        "result",
        "error",
    )

    def __init__(self, command, payload, has_payload):
        # type: (str, typing.Any, bool) -> None
        self.command = command
        self.payload = payload
        self.has_payload = has_payload
        self.completed = threading.Event()
        self.result = None  # type: typing.Any
        self.error = None  # type: typing.Optional[BaseException]

    def __repr__(self):
        # type: () -> str
        return "_CommandWorkItem(command={0!r})".format(self.command)

    def release_references(self):
        # type: () -> None
        self.payload = None
        self.result = None
        self.error = None


class SerializedRobotCommandTarget(RobotCommandTarget):
    """Synchronously serialize a RobotCommandTarget through one worker.

    Public methods enqueue bounded FIFO work, wait for downstream completion,
    and return its result or re-raise its exception. The worker assumes each
    downstream method returns promptly; motion scheduling is not performed.
    """

    def __init__(self, downstream, config=None):
        # type: (RobotCommandTarget, typing.Optional[SerializedRobotCommandTargetConfig]) -> None
        if not isinstance(downstream, RobotCommandTarget):
            raise TypeError("downstream must implement RobotCommandTarget")
        if config is None:
            config = SerializedRobotCommandTargetConfig()
        if not isinstance(config, SerializedRobotCommandTargetConfig):
            raise TypeError(
                "config must be SerializedRobotCommandTargetConfig"
            )

        self._downstream = downstream
        self._config = config
        self._queue = queue.Queue(maxsize=config.queue_capacity)
        self._state_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._startup_complete = threading.Event()
        self._stopped = threading.Event()
        self._state = _STATE_NEW
        self._worker_thread = None  # type: typing.Optional[threading.Thread]
        self._worker_thread_id = None  # type: typing.Optional[int]

    @property
    def config(self):
        # type: () -> SerializedRobotCommandTargetConfig
        """Return immutable queue and worker settings."""
        return self._config

    @property
    def is_ready(self):
        # type: () -> bool
        """Return whether new commands are currently accepted."""
        with self._state_lock:
            return self._state == _STATE_READY

    @property
    def is_stopped(self):
        # type: () -> bool
        """Return whether the worker has fully terminated."""
        return self._stopped.is_set()

    def start(self):
        # type: () -> None
        """Create and start the service's single-use worker thread."""
        with self._state_lock:
            if self._state != _STATE_NEW:
                raise CommandServiceAlreadyStartedError()
            self._state = _STATE_STARTING
            worker = threading.Thread(
                target=self._worker_main,
                name=self._config.worker_thread_name,
            )
            worker.daemon = False
            self._worker_thread = worker
            try:
                worker.start()
            except BaseException:
                self._state = _STATE_FAILED
                self._worker_thread = None
                self._startup_complete.set()
                self._stopped.set()
                raise

    def wait_until_ready(self, timeout=None):
        # type: (typing.Optional[float]) -> bool
        """Wait for worker startup and return whether it became ready."""
        if not self._startup_complete.wait(timeout):
            return False
        return self.is_ready

    def wait_until_stopped(self, timeout=None):
        # type: (typing.Optional[float]) -> bool
        """Wait until the worker thread has fully terminated."""
        return self._stopped.wait(timeout)

    def shutdown(self):
        # type: () -> None
        """Stop new submissions, drain accepted FIFO work, and join safely."""
        current_thread_id = threading.current_thread().ident
        with self._state_lock:
            if self._state == _STATE_NEW:
                self._state = _STATE_STOPPED
                self._stop_requested.set()
                self._startup_complete.set()
                self._stopped.set()
                return
            if self._state == _STATE_STOPPED:
                return
            if self._state != _STATE_FAILED:
                self._state = _STATE_STOPPING
                self._stop_requested.set()
            worker = self._worker_thread
            called_from_worker = (
                current_thread_id == self._worker_thread_id
            )

        if worker is not None and not called_from_worker:
            worker.join()

    def play_wav(self, wav_data):
        # type: (bytes) -> None
        return self._execute("play_wav", wav_data, True)

    def stop_wav(self):
        # type: () -> None
        return self._execute("stop_wav", None, False)

    def play_pose(self, pose):
        # type: (Pose) -> None
        return self._execute("play_pose", pose, True)

    def stop_pose(self):
        # type: () -> None
        return self._execute("stop_pose", None, False)

    def play_motion(self, motion):
        # type: (Motion) -> None
        return self._execute("play_motion", motion, True)

    def stop_motion(self):
        # type: () -> None
        return self._execute("stop_motion", None, False)

    def play_idle_motion(self, settings):
        # type: (IdleMotionSettings) -> None
        return self._execute("play_idle_motion", settings, True)

    def stop_idle_motion(self):
        # type: () -> None
        return self._execute("stop_idle_motion", None, False)

    def read_axes(self):
        # type: () -> typing.Mapping[str, int]
        return self._execute("read_axes", None, False)

    def mouth_led_pulse(self, pulse):
        # type: (typing.Any) -> typing.Any
        """Serialize one mouth LED pulse through the existing worker."""
        return self._execute("mouth_led_pulse", pulse, True)

    def _execute(self, command, payload, has_payload):
        # type: (str, typing.Any, bool) -> typing.Any
        current_thread_id = threading.current_thread().ident
        if current_thread_id == self._worker_thread_id:
            raise ReentrantCommandError(command)

        item = _CommandWorkItem(command, payload, has_payload)
        with self._state_lock:
            if self._state in (_STATE_NEW, _STATE_STARTING):
                raise CommandServiceNotStartedError()
            if self._state in (_STATE_STOPPING, _STATE_STOPPED):
                raise CommandServiceStoppedError()
            if self._state == _STATE_FAILED:
                raise CommandWorkerStoppedError(command)
            try:
                self._queue.put(
                    item,
                    block=True,
                    timeout=self._config.enqueue_timeout_seconds,
                )
            except queue.Full:
                raise CommandQueueFullError(
                    command,
                    self._config.queue_capacity,
                )

        item.completed.wait()
        error = item.error
        result = item.result
        item.release_references()
        if error is not None:
            raise error
        return result

    def _worker_main(self):
        # type: () -> None
        current_item = None  # type: typing.Optional[_CommandWorkItem]
        try:
            with self._state_lock:
                self._worker_thread_id = threading.current_thread().ident
                if self._state == _STATE_STARTING:
                    self._state = _STATE_READY
            self._startup_complete.set()

            while True:
                if self._stop_requested.is_set() and self._queue.empty():
                    break
                try:
                    current_item = self._queue.get(
                        timeout=_WORKER_QUEUE_POLL_SECONDS
                    )
                except queue.Empty:
                    continue
                try:
                    self._invoke_downstream(current_item)
                finally:
                    current_item.completed.set()
                    self._queue.task_done()
                    current_item = None
        except BaseException as error:
            if current_item is not None:
                current_item.error = CommandWorkerStoppedError(
                    current_item.command
                )
                current_item.completed.set()
                self._queue.task_done()
                current_item = None
            self._fail_pending_items()
            with self._state_lock:
                self._state = _STATE_FAILED
            logger.error(
                "Serialized command worker failed error_type=%s",
                type(error).__name__,
                exc_info=True,
            )
        finally:
            self._startup_complete.set()
            with self._state_lock:
                if self._state != _STATE_FAILED:
                    self._state = _STATE_STOPPED
                self._worker_thread_id = None
            self._stopped.set()

    def _invoke_downstream(self, item):
        # type: (_CommandWorkItem) -> None
        method = getattr(self._downstream, item.command)
        try:
            if item.has_payload:
                item.result = method(item.payload)
            else:
                item.result = method()
        except BaseException as error:
            item.error = error

    def _fail_pending_items(self):
        # type: () -> None
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            item.error = CommandWorkerStoppedError(item.command)
            item.completed.set()
            self._queue.task_done()
