"""High-level command execution port and recording test implementation."""

import abc
import collections
import typing

from robot_controller.models import IdleMotionSettings, Motion, Pose


_RecordedCallBase = collections.namedtuple(
    "_RecordedCallBase", ["command", "payload"]
)


class RecordedCall(_RecordedCallBase):
    """One immutable high-level command invocation."""

    __slots__ = ()


class RobotCommandTarget(abc.ABC):
    """High-level execution port consumed by CommandRouter.

    Implementations receive validated internal models. Scheduling, device
    access, and audio processing belong behind this boundary.
    """

    @abc.abstractmethod
    def play_wav(self, wav_data):
        # type: (bytes) -> None
        """Accept opaque WAV bytes for later audio handling."""
        raise NotImplementedError

    @abc.abstractmethod
    def stop_wav(self):
        # type: () -> None
        """Stop the target's managed WAV operation."""
        raise NotImplementedError

    @abc.abstractmethod
    def play_pose(self, pose):
        # type: (Pose) -> None
        """Accept one validated Pose."""
        raise NotImplementedError

    @abc.abstractmethod
    def stop_pose(self):
        # type: () -> None
        """Stop the direct-pose operation."""
        raise NotImplementedError

    @abc.abstractmethod
    def play_motion(self, motion):
        # type: (Motion) -> None
        """Accept one complete validated Motion without expanding it."""
        raise NotImplementedError

    @abc.abstractmethod
    def stop_motion(self):
        # type: () -> None
        """Stop the motion operation."""
        raise NotImplementedError

    @abc.abstractmethod
    def play_idle_motion(self, settings):
        # type: (IdleMotionSettings) -> None
        """Accept validated idle-motion settings."""
        raise NotImplementedError

    @abc.abstractmethod
    def stop_idle_motion(self):
        # type: () -> None
        """Stop the idle-motion operation."""
        raise NotImplementedError

    @abc.abstractmethod
    def read_axes(self):
        # type: () -> typing.Mapping[str, int]
        """Return public axis names mapped to integer positions."""
        raise NotImplementedError


class RecordingCommandTarget(RobotCommandTarget):
    """In-memory command target for deterministic tests.

    It records calls and returns configured axis values without sleeping,
    opening files, using sockets, creating threads, or touching hardware.
    """

    def __init__(self, read_axes_result=None, exceptions=None):
        # type: (typing.Optional[typing.Mapping[str, int]], typing.Optional[typing.Mapping[str, BaseException]]) -> None
        self._calls = []  # type: typing.List[RecordedCall]
        self._read_axes_result = {}  # type: typing.Dict[str, int]
        self._exceptions = {}  # type: typing.Dict[str, BaseException]
        if read_axes_result is not None:
            self.set_read_axes_result(read_axes_result)
        if exceptions is not None:
            for command, exception in exceptions.items():
                self.set_exception(command, exception)

    @property
    def calls(self):
        # type: () -> typing.Tuple[RecordedCall, ...]
        """Return an immutable snapshot of recorded calls."""
        return tuple(self._calls)

    @property
    def commands(self):
        # type: () -> typing.Tuple[str, ...]
        """Return command names in invocation order."""
        return tuple(call.command for call in self._calls)

    def call_count(self, command):
        # type: (str) -> int
        """Return how many times a command was invoked."""
        return sum(1 for call in self._calls if call.command == command)

    def set_read_axes_result(self, axes):
        # type: (typing.Mapping[str, int]) -> None
        """Replace the configured axes with a detached mapping copy."""
        try:
            self._read_axes_result = dict(axes.items())
        except AttributeError:
            raise TypeError("read_axes_result must be a mapping")

    def set_exception(self, command, exception):
        # type: (str, typing.Optional[BaseException]) -> None
        """Configure or clear the exception raised for one command."""
        if exception is None:
            self._exceptions.pop(command, None)
            return
        if not isinstance(exception, BaseException):
            raise TypeError("configured exception must be an exception")
        self._exceptions[command] = exception

    def play_wav(self, wav_data):
        # type: (bytes) -> None
        self._record("play_wav", wav_data)

    def stop_wav(self):
        # type: () -> None
        self._record("stop_wav", None)

    def play_pose(self, pose):
        # type: (Pose) -> None
        self._record("play_pose", pose)

    def stop_pose(self):
        # type: () -> None
        self._record("stop_pose", None)

    def play_motion(self, motion):
        # type: (Motion) -> None
        self._record("play_motion", motion)

    def stop_motion(self):
        # type: () -> None
        self._record("stop_motion", None)

    def play_idle_motion(self, settings):
        # type: (IdleMotionSettings) -> None
        self._record("play_idle_motion", settings)

    def stop_idle_motion(self):
        # type: () -> None
        self._record("stop_idle_motion", None)

    def read_axes(self):
        # type: () -> typing.Mapping[str, int]
        self._record("read_axes", None)
        return dict(self._read_axes_result)

    def _record(self, command, payload):
        # type: (str, typing.Any) -> None
        self._calls.append(RecordedCall(command, payload))
        exception = self._exceptions.get(command)
        if exception is not None:
            raise exception

