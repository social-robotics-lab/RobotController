"""One-command connection integration for the legacy v1 protocol."""

import collections
import typing

from robot_controller.profiles import RobotProfile
from robot_controller.protocol.commands import (
    DEFAULT_LIMITS,
    LegacyV1Limits,
)
from robot_controller.protocol.decoder import decode_request
from robot_controller.protocol.legacy_v1 import read_request, write_response
from robot_controller.protocol.validation import (
    DEFAULT_VALIDATION_LIMITS,
    ValidationLimits,
)
from robot_controller.router import CommandRouter


_ConnectionHandleResultBase = collections.namedtuple(
    "_ConnectionHandleResultBase", ["command", "response_sent"]
)


class ConnectionHandleResult(_ConnectionHandleResultBase):
    """Immutable summary of one handled legacy v1 command."""

    __slots__ = ()


def handle_connection(
    sock,
    robot_profile,
    router,
    session_limits=DEFAULT_LIMITS,
    decoder_limits=DEFAULT_VALIDATION_LIMITS,
):
    # type: (typing.Any, RobotProfile, CommandRouter, LegacyV1Limits, ValidationLimits) -> ConnectionHandleResult
    """Read, decode, dispatch, and optionally respond to one v1 request.

    The caller owns ``sock``. This function does not close or shut down it,
    change its timeout, accept another connection, or read a second command.
    Existing layer-specific exceptions propagate unchanged to the caller.
    """
    request = read_request(sock, limits=session_limits)
    decoded_command = decode_request(
        request,
        robot_profile,
        limits=decoder_limits,
    )
    dispatch_result = router.dispatch(decoded_command)

    response_sent = False
    if dispatch_result.response_payload is not None:
        write_response(sock, request, dispatch_result.response_payload)
        response_sent = True

    return ConnectionHandleResult(
        command=decoded_command.command,
        response_sent=response_sent,
    )
