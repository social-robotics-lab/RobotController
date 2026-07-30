"""One-command session processing for the legacy v1 protocol."""

import collections
import contextlib
import math
import socket
import typing

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
    PAYLOAD_JSON,
    PAYLOAD_WAV,
    LegacyV1Limits,
)
from robot_controller.protocol.frame import read_frame, write_frame


_LegacyV1TimeoutsBase = collections.namedtuple(
    "_LegacyV1TimeoutsBase",
    [
        "command_timeout",
        "json_payload_timeout",
        "wav_payload_timeout",
        "response_timeout",
    ],
)


class LegacyV1Timeouts(_LegacyV1TimeoutsBase):
    """Immutable inactivity timeouts for legacy v1 socket operations."""

    __slots__ = ()

    def __new__(
        cls,
        command_timeout=5.0,
        json_payload_timeout=5.0,
        wav_payload_timeout=30.0,
        response_timeout=5.0,
    ):
        # type: (float, float, float, float) -> LegacyV1Timeouts
        values = (
            command_timeout,
            json_payload_timeout,
            wav_payload_timeout,
            response_timeout,
        )
        for value in values:
            if isinstance(value, bool) or not isinstance(
                value, (int, float)
            ):
                raise TypeError(
                    "legacy v1 timeouts must be numbers"
                )
            if not math.isfinite(value) or value <= 0:
                raise ValueError(
                    "legacy v1 timeouts must be finite and positive"
                )
        return _LegacyV1TimeoutsBase.__new__(cls, *values)

    def payload_timeout(self, payload_kind):
        # type: (str) -> float
        """Return the inactivity timeout for one payload metadata kind."""
        if payload_kind == PAYLOAD_JSON:
            return self.json_payload_timeout
        if payload_kind == PAYLOAD_WAV:
            return self.wav_payload_timeout
        raise ValueError(
            "Payload kind {0!r} has no payload timeout".format(
                payload_kind
            )
        )


DEFAULT_TIMEOUTS = LegacyV1Timeouts()


_LegacyV1RequestBase = collections.namedtuple(
    "_LegacyV1RequestBase",
    ["command", "payload", "expects_response", "payload_kind"],
)


class LegacyV1Request(_LegacyV1RequestBase):
    """Immutable validated command name with an opaque payload."""

    __slots__ = ()


@contextlib.contextmanager
def socket_timeout(sock, timeout):
    # type: (socket.socket, float) -> typing.Iterator[None]
    """Temporarily apply a per-blocking-operation inactivity timeout."""
    original_timeout = sock.gettimeout()
    sock.settimeout(timeout)
    try:
        yield
    finally:
        sock.settimeout(original_timeout)


def read_request(
    sock,
    limits=DEFAULT_LIMITS,
    timeouts=DEFAULT_TIMEOUTS,
):
    # type: (socket.socket, LegacyV1Limits, LegacyV1Timeouts) -> LegacyV1Request
    """Read one request using command- and payload-stage timeouts."""
    if not isinstance(timeouts, LegacyV1Timeouts):
        raise TypeError("timeouts must be LegacyV1Timeouts")
    command = read_command(sock, limits=limits, timeouts=timeouts)
    return read_request_after_command(
        sock, command, limits=limits, timeouts=timeouts
    )


def read_command(sock, limits=DEFAULT_LIMITS, timeouts=DEFAULT_TIMEOUTS):
    # type: (socket.socket, LegacyV1Limits, LegacyV1Timeouts) -> str
    """Read and decode the first command frame without classifying it."""
    with socket_timeout(sock, timeouts.command_timeout):
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
    return command


def read_request_after_command(
    sock,
    command,
    limits=DEFAULT_LIMITS,
    timeouts=DEFAULT_TIMEOUTS,
):
    # type: (socket.socket, str, LegacyV1Limits, LegacyV1Timeouts) -> LegacyV1Request
    """Finish a legacy request after a shared handler read its command."""

    spec = COMMAND_SPECS.get(command)
    if spec is None:
        raise UnknownCommandError(command)

    payload = None
    if spec.payload_required:
        max_length = limits.payload_max_length(spec.payload_kind)
        payload_timeout = timeouts.payload_timeout(spec.payload_kind)
        with socket_timeout(sock, payload_timeout):
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


def write_response(
    sock,
    request,
    payload,
    timeouts=DEFAULT_TIMEOUTS,
):
    # type: (socket.socket, LegacyV1Request, bytes, LegacyV1Timeouts) -> None
    """Write an explicit response frame for a response-capable request."""
    if not isinstance(timeouts, LegacyV1Timeouts):
        raise TypeError("timeouts must be LegacyV1Timeouts")
    spec = COMMAND_SPECS.get(request.command)
    if (
        spec is None
        or not spec.expects_response
        or not request.expects_response
    ):
        raise ResponseNotAllowedError(request.command)

    with socket_timeout(sock, timeouts.response_timeout):
        try:
            write_frame(sock, payload)
        except ProtocolError as error:
            raise ResponseFrameError(error) from error
