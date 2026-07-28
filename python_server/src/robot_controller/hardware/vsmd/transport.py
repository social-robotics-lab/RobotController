"""Bounded, buffered TCP transport for ``vsmd_edison``."""

import math
import socket
import threading
import typing

from robot_controller.hardware.vsmd.codec import parse_server_banner
from robot_controller.hardware.vsmd.constants import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_HOST,
    DEFAULT_MAX_LINE_LENGTH,
    DEFAULT_PORT,
    DEFAULT_READ_TIMEOUT_SECONDS,
    DEFAULT_WRITE_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.errors import (
    VsmdConnectError,
    VsmdLineTooLongError,
    VsmdTransportStateError,
    VsmdTransportTimeoutError,
    VsmdUnexpectedEofError,
    VsmdValidationError,
    VsmdWriteOutcomeUnknownError,
)


def _positive_finite(value, name):
    # type: (float, str) -> float
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise VsmdValidationError(
            "{0} must be a positive finite number".format(name)
        )
    return float(value)


class VsmdTcpTransport(object):
    """Own one VSMD TCP connection and preserve coalesced line data.

    The surrounding hardware command service supplies single-worker
    serialization. A re-entrant lock additionally keeps individual transport
    operations coherent if the object is inspected or closed concurrently.
    Failed writes are never retried because their daemon-side outcome may be
    unknown.
    """

    def __init__(
        self,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        connect_timeout=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        read_timeout=DEFAULT_READ_TIMEOUT_SECONDS,
        write_timeout=DEFAULT_WRITE_TIMEOUT_SECONDS,
        max_line_length=DEFAULT_MAX_LINE_LENGTH,
        socket_factory=None,
    ):
        # type: (str, int, float, float, float, int, typing.Any) -> None
        if not isinstance(host, str) or not host:
            raise VsmdValidationError("host must be a non-empty string")
        if isinstance(port, bool) or not isinstance(port, int):
            raise VsmdValidationError("port must be an integer")
        if port < 1 or port > 65535:
            raise VsmdValidationError("port must be between 1 and 65535")
        if (
            isinstance(max_line_length, bool)
            or not isinstance(max_line_length, int)
            or max_line_length < 1
        ):
            raise VsmdValidationError(
                "max_line_length must be a positive integer"
            )
        self._host = host
        self._port = port
        self._connect_timeout = _positive_finite(
            connect_timeout, "connect_timeout"
        )
        self._read_timeout = _positive_finite(
            read_timeout, "read_timeout"
        )
        self._write_timeout = _positive_finite(
            write_timeout, "write_timeout"
        )
        self._max_line_length = max_line_length
        self._socket_factory = (
            socket.create_connection
            if socket_factory is None
            else socket_factory
        )
        self._socket = None  # type: typing.Any
        self._buffer = bytearray()
        self._banner = None
        self._lock = threading.RLock()

    @property
    def host(self):
        # type: () -> str
        return self._host

    @property
    def port(self):
        # type: () -> int
        return self._port

    @property
    def connect_timeout(self):
        # type: () -> float
        return self._connect_timeout

    @property
    def read_timeout(self):
        # type: () -> float
        return self._read_timeout

    @property
    def write_timeout(self):
        # type: () -> float
        return self._write_timeout

    @property
    def server_banner(self):
        # type: () -> typing.Any
        with self._lock:
            if self._banner is None:
                raise VsmdTransportStateError("transport is not connected")
            return self._banner

    @property
    def is_connected(self):
        # type: () -> bool
        with self._lock:
            return self._socket is not None

    def connect(self):
        # type: () -> None
        """Connect once, validate the initial banner, and retain extra bytes."""
        with self._lock:
            if self._socket is not None:
                return
            try:
                connected = self._socket_factory(
                    (self._host, self._port), self._connect_timeout
                )
            except socket.timeout as error:
                raise VsmdTransportTimeoutError("connect") from error
            except OSError as error:
                raise VsmdConnectError(
                    "could not connect to VSMD daemon"
                ) from error
            self._socket = connected
            self._buffer = bytearray()
            self._banner = None
            try:
                connected.settimeout(self._read_timeout)
                self._banner = parse_server_banner(self._read_line_locked())
            except BaseException:
                self._close_locked()
                raise

    def close(self):
        # type: () -> None
        """Close the owned socket idempotently."""
        with self._lock:
            self._close_locked()

    def send(self, data):
        # type: (bytes) -> None
        """Send bytes exactly once without automatic reconnect or retry."""
        if not isinstance(data, bytes) or not data:
            raise VsmdValidationError("transport data must be non-empty bytes")
        with self._lock:
            connected = self._require_socket_locked()
            try:
                connected.settimeout(self._write_timeout)
                connected.sendall(data)
            except socket.timeout as error:
                raise VsmdWriteOutcomeUnknownError(
                    "VSMD write timed out; outcome is unknown"
                ) from error
            except OSError as error:
                raise VsmdWriteOutcomeUnknownError(
                    "VSMD write failed; outcome is unknown"
                ) from error
            finally:
                if self._socket is connected:
                    connected.settimeout(self._read_timeout)

    def read_line(self):
        # type: () -> bytes
        """Read one bounded newline-terminated line."""
        with self._lock:
            self._require_socket_locked()
            return self._read_line_locked()

    def __enter__(self):
        # type: () -> VsmdTcpTransport
        self.connect()
        return self

    def __exit__(self, exception_type, exception, traceback):
        # type: (typing.Any, typing.Any, typing.Any) -> bool
        self.close()
        return False

    def _require_socket_locked(self):
        # type: () -> typing.Any
        if self._socket is None:
            raise VsmdTransportStateError("transport is not connected")
        return self._socket

    def _read_line_locked(self):
        # type: () -> bytes
        connected = self._require_socket_locked()
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                line_length = newline + 1
                if line_length > self._max_line_length:
                    raise VsmdLineTooLongError(
                        "VSMD line exceeds configured maximum"
                    )
                line = bytes(self._buffer[:line_length])
                del self._buffer[:line_length]
                return line
            if len(self._buffer) >= self._max_line_length:
                raise VsmdLineTooLongError(
                    "VSMD unterminated line exceeds configured maximum"
                )
            try:
                chunk = connected.recv(4096)
            except socket.timeout as error:
                raise VsmdTransportTimeoutError("read") from error
            except OSError as error:
                raise VsmdUnexpectedEofError(
                    "VSMD receive failed before a complete line"
                ) from error
            if not chunk:
                raise VsmdUnexpectedEofError(
                    "VSMD connection closed before a complete line"
                )
            self._buffer.extend(chunk)

    def _close_locked(self):
        # type: () -> None
        connected = self._socket
        self._socket = None
        self._buffer = bytearray()
        self._banner = None
        if connected is not None:
            try:
                connected.close()
            except OSError:
                pass

