"""Binary frame codec for the legacy v1 TCP protocol."""

import socket
import struct

from robot_controller.errors import (
    ConnectionClosedError,
    FrameReadError,
    FrameTimeoutError,
    FrameTooLargeError,
    FrameWriteError,
    InvalidFrameLengthError,
)


_HEADER_LENGTH = 4
_MAX_V1_PAYLOAD_LENGTH = 0x7FFFFFFF


def encode_frame(payload):
    # type: (bytes) -> bytes
    """Return one complete legacy v1 frame for a bytes payload."""
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")

    payload_length = len(payload)
    if payload_length > _MAX_V1_PAYLOAD_LENGTH:
        raise InvalidFrameLengthError(payload_length)

    return struct.pack(">I", payload_length) + payload


def read_frame(sock, max_length):
    # type: (socket.socket, int) -> bytes
    """Read and return one complete legacy v1 payload from a socket.

    ``max_length`` is supplied for each call so command, JSON, and WAV frames
    can use different configured limits.
    """
    _validate_max_length(max_length)

    header = _recv_exact(sock, _HEADER_LENGTH, "header")
    declared_length = struct.unpack(">I", header)[0]

    if declared_length > _MAX_V1_PAYLOAD_LENGTH:
        raise InvalidFrameLengthError(declared_length)
    if declared_length > max_length:
        raise FrameTooLargeError(declared_length, max_length)
    if declared_length == 0:
        return b""

    return _recv_exact(sock, declared_length, "payload")


def write_frame(sock, payload):
    # type: (socket.socket, bytes) -> None
    """Encode and completely send one legacy v1 frame to a socket."""
    encoded = encode_frame(payload)
    try:
        sock.sendall(encoded)
    except OSError as error:
        raise FrameWriteError(len(encoded)) from error


def _validate_max_length(max_length):
    # type: (int) -> None
    if isinstance(max_length, bool) or not isinstance(max_length, int):
        raise TypeError("max_length must be an integer")
    if max_length < 0:
        raise ValueError("max_length must not be negative")


def _recv_exact(sock, expected_bytes, stage):
    # type: (socket.socket, int, str) -> bytes
    chunks = []
    received_bytes = 0

    while received_bytes < expected_bytes:
        try:
            chunk = sock.recv(expected_bytes - received_bytes)
        except socket.timeout as error:
            raise FrameTimeoutError(
                stage, expected_bytes, received_bytes
            ) from error
        except OSError as error:
            raise FrameReadError(
                stage, expected_bytes, received_bytes
            ) from error

        if not chunk:
            raise ConnectionClosedError(
                stage, expected_bytes, received_bytes
            )

        chunks.append(chunk)
        received_bytes += len(chunk)

    return b"".join(chunks)
