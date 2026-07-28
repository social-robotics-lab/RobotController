"""One-request-per-connection TCP transport for SotaAppManager."""

import math
import socket
import typing

from robot_controller.hardware.vsmd.app_manager_codec import (
    JAVA_STREAM_HEADER,
)
from robot_controller.hardware.vsmd.errors import (
    AppManagerConnectionError,
    AppManagerOutcomeUnknownError,
    AppManagerProtocolError,
    AppManagerTimeoutError,
    VsmdValidationError,
)


DEFAULT_APP_MANAGER_HOST = "127.0.0.1"
DEFAULT_APP_MANAGER_PORT = 6495
DEFAULT_APP_MANAGER_TIMEOUT_SECONDS = 2.0
DEFAULT_APP_MANAGER_MAX_RESPONSE_BYTES = 4096


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


class AppManagerTcpTransport(object):
    """Exchange one ASCII JSON request on a fresh bounded TCP connection."""

    def __init__(
        self,
        host=DEFAULT_APP_MANAGER_HOST,
        port=DEFAULT_APP_MANAGER_PORT,
        timeout=DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
        max_response_bytes=DEFAULT_APP_MANAGER_MAX_RESPONSE_BYTES,
        socket_factory=None,
    ):
        # type: (str, int, float, int, typing.Any) -> None
        if not isinstance(host, str) or not host:
            raise VsmdValidationError("host must be a non-empty string")
        if (
            isinstance(port, bool)
            or not isinstance(port, int)
            or port < 1
            or port > 65535
        ):
            raise VsmdValidationError("port must be between 1 and 65535")
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or max_response_bytes < len(JAVA_STREAM_HEADER) + 1
        ):
            raise VsmdValidationError(
                "max_response_bytes must fit a Java header and token"
            )
        self._host = host
        self._port = port
        self._timeout = _positive_finite(timeout, "timeout")
        self._max_response_bytes = max_response_bytes
        self._socket_factory = (
            socket.create_connection
            if socket_factory is None
            else socket_factory
        )

    @property
    def host(self):
        # type: () -> str
        return self._host

    @property
    def port(self):
        # type: () -> int
        return self._port

    @property
    def timeout(self):
        # type: () -> float
        return self._timeout

    @property
    def max_response_bytes(self):
        # type: () -> int
        return self._max_response_bytes

    def request(self, request_json):
        # type: (bytes) -> bytes
        """Send compact JSON plus one LF and return the complete Java stream."""
        if not isinstance(request_json, bytes) or not request_json:
            raise VsmdValidationError(
                "AppManager request must be non-empty bytes"
            )
        if request_json.endswith(b"\n") or b"\r" in request_json:
            raise VsmdValidationError(
                "AppManager request must not include a line terminator"
            )
        try:
            request_json.decode("ascii")
        except UnicodeDecodeError as error:
            raise VsmdValidationError(
                "AppManager request must contain ASCII only"
            ) from error

        connected = None  # type: typing.Any
        try:
            try:
                connected = self._socket_factory(
                    (self._host, self._port), self._timeout
                )
            except socket.timeout as error:
                raise AppManagerTimeoutError(
                    "SotaAppManager connect timed out"
                ) from error
            except OSError as error:
                raise AppManagerConnectionError(
                    "could not connect to SotaAppManager"
                ) from error

            try:
                connected.settimeout(self._timeout)
            except socket.timeout as error:
                raise AppManagerTimeoutError(
                    "timed out before AppManager request submission"
                ) from error
            except OSError as error:
                raise AppManagerConnectionError(
                    "failed before AppManager request submission"
                ) from error
            header = self._read_exact_header(connected)
            if header != JAVA_STREAM_HEADER:
                if header[:2] != JAVA_STREAM_HEADER[:2]:
                    reason = "invalid Java stream magic"
                else:
                    reason = "invalid Java stream version"
                raise AppManagerProtocolError(reason)

            try:
                connected.sendall(request_json + b"\n")
            except (socket.timeout, OSError) as error:
                raise AppManagerOutcomeUnknownError(
                    "AppManager request send failed; outcome is unknown"
                ) from error

            body = self._read_response_body(connected)
            return header + body
        finally:
            if connected is not None:
                try:
                    connected.close()
                except OSError:
                    pass

    def _read_exact_header(self, connected):
        # type: (typing.Any) -> bytes
        chunks = bytearray()
        while len(chunks) < len(JAVA_STREAM_HEADER):
            try:
                chunk = connected.recv(
                    len(JAVA_STREAM_HEADER) - len(chunks)
                )
            except socket.timeout as error:
                raise AppManagerTimeoutError(
                    "timed out before AppManager request submission"
                ) from error
            except OSError as error:
                raise AppManagerConnectionError(
                    "failed before AppManager request submission"
                ) from error
            if not chunk:
                raise AppManagerProtocolError(
                    "EOF before complete Java stream header"
                )
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_response_body(self, connected):
        # type: (typing.Any) -> bytes
        body = bytearray()
        maximum_body = self._max_response_bytes - len(JAVA_STREAM_HEADER)
        while True:
            try:
                chunk = connected.recv(
                    min(4096, maximum_body - len(body) + 1)
                )
            except (socket.timeout, OSError) as error:
                raise AppManagerOutcomeUnknownError(
                    "AppManager response failed after request submission; "
                    "outcome is unknown"
                ) from error
            if not chunk:
                return bytes(body)
            body.extend(chunk)
            if len(body) > maximum_body:
                raise AppManagerProtocolError(
                    "AppManager response exceeds configured maximum"
                )
