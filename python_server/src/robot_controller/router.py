"""Dispatch validated commands to a high-level execution target."""

import collections
import types

from robot_controller.command_target import RobotCommandTarget
from robot_controller.errors import (
    CommandExecutionError,
    InvalidDecodedCommandError,
)
from robot_controller.models import (
    DecodedCommand,
    IdleMotionSettings,
    Motion,
    Pose,
)
from robot_controller.protocol.read_axes import encode_read_axes


_CommandDispatchResultBase = collections.namedtuple(
    "_CommandDispatchResultBase", ["response_payload"]
)


class CommandDispatchResult(_CommandDispatchResultBase):
    """Immutable result containing optional unframed response bytes."""

    __slots__ = ()


_RouteSpecBase = collections.namedtuple(
    "_RouteSpecBase",
    ["method_name", "payload_type", "payload_expected", "returns_axes"],
)


class _RouteSpec(_RouteSpecBase):
    __slots__ = ()


_ROUTES = types.MappingProxyType(
    {
        "play_wav": _RouteSpec("play_wav", bytes, "bytes", False),
        "stop_wav": _RouteSpec("stop_wav", type(None), "None", False),
        "play_pose": _RouteSpec("play_pose", Pose, "Pose", False),
        "stop_pose": _RouteSpec("stop_pose", type(None), "None", False),
        "play_motion": _RouteSpec("play_motion", Motion, "Motion", False),
        "stop_motion": _RouteSpec("stop_motion", type(None), "None", False),
        "play_idle_motion": _RouteSpec(
            "play_idle_motion",
            IdleMotionSettings,
            "IdleMotionSettings",
            False,
        ),
        "stop_idle_motion": _RouteSpec(
            "stop_idle_motion", type(None), "None", False
        ),
        "read_axes": _RouteSpec("read_axes", type(None), "None", True),
    }
)


class CommandRouter(object):
    """Route each validated DecodedCommand to exactly one target method."""

    def __init__(self, target):
        # type: (RobotCommandTarget) -> None
        if not isinstance(target, RobotCommandTarget):
            raise TypeError("target must implement RobotCommandTarget")
        self._target = target

    def dispatch(self, decoded_command):
        # type: (DecodedCommand) -> CommandDispatchResult
        """Execute one validated command and return optional response bytes."""
        if not isinstance(decoded_command, DecodedCommand):
            raise InvalidDecodedCommandError(
                None, "DecodedCommand", type(decoded_command).__name__
            )

        command = decoded_command.command
        route = _ROUTES.get(command)
        if route is None:
            raise InvalidDecodedCommandError(
                command, "one of the nine legacy v1 commands", "unknown command"
            )

        payload = decoded_command.payload
        if not isinstance(payload, route.payload_type):
            raise InvalidDecodedCommandError(
                command, route.payload_expected, type(payload).__name__
            )

        method = getattr(self._target, route.method_name)
        try:
            if payload is None:
                target_result = method()
            else:
                target_result = method(payload)
            if route.returns_axes:
                return CommandDispatchResult(
                    encode_read_axes(target_result)
                )
            return CommandDispatchResult(None)
        except Exception as error:
            raise CommandExecutionError(command) from error
