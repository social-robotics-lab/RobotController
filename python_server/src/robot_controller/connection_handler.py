"""One-command connection integration for the legacy v1 protocol."""

import collections
import typing

from robot_controller.profiles import RobotProfile
from robot_controller.protocol.commands import (
    DEFAULT_LIMITS,
    LegacyV1Limits,
)
from robot_controller.protocol.decoder import decode_request
from robot_controller.protocol.legacy_v1 import (
    DEFAULT_TIMEOUTS,
    LegacyV1Timeouts,
    read_request,
    write_response,
)
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
    session_timeouts=DEFAULT_TIMEOUTS,
):
    # type: (typing.Any, RobotProfile, CommandRouter, LegacyV1Limits, ValidationLimits, LegacyV1Timeouts) -> ConnectionHandleResult
    """Read, decode, dispatch, and optionally respond to one v1 request.

    The caller owns ``sock``. This function does not close or shut it down,
    accept another connection, or read a second command. Stage-specific
    inactivity timeouts are always restored to the caller's original value.
    Existing layer-specific exceptions propagate unchanged to the caller.
    """
    request = read_request(
        sock,
        limits=session_limits,
        timeouts=session_timeouts,
    )
    decoded_command = decode_request(
        request,
        robot_profile,
        limits=decoder_limits,
    )
    dispatch_result = router.dispatch(decoded_command)

    response_sent = False
    if dispatch_result.response_payload is not None:
        write_response(
            sock,
            request,
            dispatch_result.response_payload,
            timeouts=session_timeouts,
        )
        response_sent = True

    return ConnectionHandleResult(
        command=decoded_command.command,
        response_sent=response_sent,
    )
