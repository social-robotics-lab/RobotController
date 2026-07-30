"""One-command connection handler for legacy v1 plus explicit v2 commands."""

import collections
import typing

from robot_controller.current_router import CurrentCommandExecutionError
from robot_controller.errors import (
    HardwareBackendError,
    HardwareBackendUnavailableError,
    ProtocolError,
    ResponseFrameError,
)
from robot_controller.hardware.vsmd.errors import VsmdError
from robot_controller.profiles import RobotProfile
from robot_controller.protocol.commands import DEFAULT_LIMITS, LegacyV1Limits
from robot_controller.protocol.current import (
    COMMAND_PREFIX,
    CurrentProtocolError,
    decode_request as decode_current_request,
    encode_error,
    encode_success,
)
from robot_controller.protocol.decoder import decode_request
from robot_controller.protocol.frame import read_frame, write_frame
from robot_controller.protocol.legacy_v1 import (
    DEFAULT_TIMEOUTS,
    LegacyV1Timeouts,
    read_command,
    read_request_after_command,
    socket_timeout,
    write_response,
)
from robot_controller.protocol.validation import (
    DEFAULT_VALIDATION_LIMITS,
    ValidationLimits,
)


_ProductionConnectionResultBase = collections.namedtuple(
    "_ProductionConnectionResultBase",
    ["protocol_version", "command", "response_sent"],
)


class ProductionConnectionResult(_ProductionConnectionResultBase):
    """Small immutable summary of one production connection."""

    __slots__ = ()


def handle_production_connection(
    sock,
    robot_profile,
    legacy_router,
    current_router,
    session_limits=DEFAULT_LIMITS,
    decoder_limits=DEFAULT_VALIDATION_LIMITS,
    session_timeouts=DEFAULT_TIMEOUTS,
):
    # type: (typing.Any, RobotProfile, typing.Any, typing.Any, LegacyV1Limits, ValidationLimits, LegacyV1Timeouts) -> ProductionConnectionResult
    """Handle one v1 or explicitly prefixed v2 command on the same socket."""
    command = read_command(
        sock, limits=session_limits, timeouts=session_timeouts
    )
    if not command.startswith(COMMAND_PREFIX):
        request = read_request_after_command(
            sock,
            command,
            limits=session_limits,
            timeouts=session_timeouts,
        )
        decoded = decode_request(
            request, robot_profile, limits=decoder_limits
        )
        result = legacy_router.dispatch(decoded)
        response_sent = False
        if result.response_payload is not None:
            write_response(
                sock,
                request,
                result.response_payload,
                timeouts=session_timeouts,
            )
            response_sent = True
        return ProductionConnectionResult(
            1, decoded.command, response_sent
        )

    request = None
    try:
        try:
            with socket_timeout(
                sock, session_timeouts.json_payload_timeout
            ):
                payload = read_frame(
                    sock, session_limits.json_max_length
                )
        except ProtocolError:
            raise CurrentProtocolError(
                "PROTOCOL_DECODE_ERROR",
                "request payload frame is invalid",
            )
        if payload == b"":
            raise CurrentProtocolError(
                "VALIDATION_ERROR", "request payload must not be empty"
            )
        request = decode_current_request(command, payload)
        dispatch_result = current_router.dispatch(request)
        response = encode_success(
            request.request_id,
            request.command,
            dispatch_result.backend_result,
        )
    except CurrentProtocolError as error:
        response = encode_error(
            error.code, error.client_message, error.request_id
        )
    except CurrentCommandExecutionError as error:
        cause = error.__cause__
        if isinstance(cause, HardwareBackendUnavailableError):
            code = "MOUTH_LED_BACKEND_UNAVAILABLE"
            message = "mouth LED backend is unavailable"
        elif isinstance(cause, (HardwareBackendError, VsmdError)):
            code = "MOUTH_LED_OPERATION_FAILED"
            message = "mouth LED operation failed"
        else:
            code = "INTERNAL_ERROR"
            message = "internal command failure"
        response = encode_error(
            code,
            message,
            None if request is None else request.request_id,
        )
    except Exception:
        response = encode_error(
            "INTERNAL_ERROR",
            "internal command failure",
            None if request is None else request.request_id,
        )
    _write_current_response(sock, response, session_timeouts)
    return ProductionConnectionResult(
        2,
        command[len(COMMAND_PREFIX):],
        True,
    )


def _write_current_response(sock, payload, timeouts):
    # type: (typing.Any, bytes, LegacyV1Timeouts) -> None
    with socket_timeout(sock, timeouts.response_timeout):
        try:
            write_frame(sock, payload)
        except ProtocolError as error:
            raise ResponseFrameError(error) from error
