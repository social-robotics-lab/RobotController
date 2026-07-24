"""One-command session processing for the legacy v1 protocol."""

import collections
import socket

from robot_controller.errors import (
    CommandDecodeError,
    CommandFrameError,
    ConnectionClosedError,
    EmptyCommandError,
    MissingPayloadError,
    PayloadFrameError,
    ProtocolError,
    ResponseFrameError,
    ResponseNotAllowedError,
    UnknownCommandError,
)
from robot_controller.protocol.commands import (
    COMMAND_SPECS,
    DEFAULT_LIMITS,
    LegacyV1Limits,
)
from robot_controller.protocol.frame import read_frame, write_frame


_LegacyV1RequestBase = collections.namedtuple(
    "_LegacyV1RequestBase",
    ["command", "payload", "expects_response", "payload_kind"],
)


class LegacyV1Request(_LegacyV1RequestBase):
    """Immutable validated command name with an opaque payload."""

    __slots__ = ()


def read_request(sock, limits=DEFAULT_LIMITS):
    # type: (socket.socket, LegacyV1Limits) -> LegacyV1Request
    """Read exactly one legacy v1 command and its required payload frame."""
    try:
        command_bytes = read_frame(sock, limits.command_max_length)
    except ProtocolError as error:
        raise CommandFrameError(error) from error

    try:
        command = command_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise CommandDecodeError(command_bytes) from error

    if command == "":
        raise EmptyCommandError()

    spec = COMMAND_SPECS.get(command)
    if spec is None:
        raise UnknownCommandError(command)

    payload = None
    if spec.payload_required:
        max_length = limits.payload_max_length(spec.payload_kind)
        try:
            payload = read_frame(sock, max_length)
        except ConnectionClosedError as error:
            if error.stage == "header" and error.received_bytes == 0:
                raise MissingPayloadError(command, error) from error
            raise PayloadFrameError(error) from error
        except ProtocolError as error:
            raise PayloadFrameError(error) from error

        if payload == b"":
            raise MissingPayloadError(command)

    return LegacyV1Request(
        command=spec.name,
        payload=payload,
        expects_response=spec.expects_response,
        payload_kind=spec.payload_kind,
    )


def write_response(sock, request, payload):
    # type: (socket.socket, LegacyV1Request, bytes) -> None
    """Write an explicit response frame for a response-capable request."""
    spec = COMMAND_SPECS.get(request.command)
    if (
        spec is None
        or not spec.expects_response
        or not request.expects_response
    ):
        raise ResponseNotAllowedError(request.command)

    try:
        write_frame(sock, payload)
    except ProtocolError as error:
        raise ResponseFrameError(error) from error
