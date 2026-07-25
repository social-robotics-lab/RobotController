"""Deterministic tests for staged legacy v1 socket timeouts."""

import socket

import pytest

from robot_controller.errors import (
    CommandFrameError,
    MissingPayloadError,
    PayloadFrameError,
    ResponseFrameError,
    ResponseNotAllowedError,
)
from robot_controller.protocol.frame import encode_frame
from robot_controller.protocol.legacy_v1 import (
    DEFAULT_TIMEOUTS,
    LegacyV1Timeouts,
    read_request,
    write_response,
)


class TimeoutTrackingSocket(object):
    """Socket double recording the timeout active for each I/O operation."""

    def __init__(
        self,
        incoming=b"",
        timeout=12.5,
        recv_error_at=None,
        send_error=None,
    ):
        self.incoming = incoming
        self.timeout = timeout
        self.recv_error_at = recv_error_at
        self.send_error = send_error
        self.recv_calls = []
        self.send_calls = []
        self.settimeout_calls = []

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.settimeout_calls.append(value)
        self.timeout = value

    def recv(self, size):
        self.recv_calls.append((size, self.timeout))
        if self.recv_error_at == len(self.recv_calls):
            raise socket.timeout("timed out")
        if not self.incoming:
            return b""
        chunk = self.incoming[:size]
        self.incoming = self.incoming[size:]
        return chunk

    def sendall(self, data):
        self.send_calls.append((data, self.timeout))
        if self.send_error is not None:
            raise self.send_error


def wire_request(command, payload=None):
    wire = encode_frame(command.encode("utf-8"))
    if payload is not None:
        wire += encode_frame(payload)
    return wire


def test_default_staged_timeouts_match_confirmed_values():
    assert DEFAULT_TIMEOUTS == LegacyV1Timeouts(5.0, 5.0, 30.0, 5.0)


@pytest.mark.parametrize(
    "field",
    [
        "command_timeout",
        "json_payload_timeout",
        "wav_payload_timeout",
        "response_timeout",
    ],
)
@pytest.mark.parametrize(
    "value",
    [0, -1, True, float("nan"), float("inf"), -float("inf"), "5"],
)
def test_staged_timeout_config_rejects_invalid_values(field, value):
    values = {
        "command_timeout": 5.0,
        "json_payload_timeout": 5.0,
        "wav_payload_timeout": 30.0,
        "response_timeout": 5.0,
    }
    values[field] = value

    with pytest.raises((TypeError, ValueError)):
        LegacyV1Timeouts(**values)


@pytest.mark.parametrize(
    "command,payload",
    [
        ("read_axes", None),
        ("stop_pose", None),
        ("play_pose", b"{}"),
        ("play_wav", b"wav"),
    ],
)
def test_every_command_frame_uses_command_timeout(command, payload):
    sock = TimeoutTrackingSocket(wire_request(command, payload))

    read_request(sock)

    assert sock.recv_calls[0:2] == [
        (4, 5.0),
        (len(command), 5.0),
    ]
    assert sock.settimeout_calls[0:2] == [5.0, 12.5]
    assert sock.gettimeout() == 12.5


@pytest.mark.parametrize(
    "command,payload",
    [
        ("play_pose", b"{}"),
        ("play_motion", b"[]"),
        ("play_idle_motion", b"{}"),
    ],
)
def test_json_payload_header_and_body_use_json_timeout(command, payload):
    sock = TimeoutTrackingSocket(wire_request(command, payload))

    request = read_request(sock)

    assert request.payload == payload
    assert sock.recv_calls[2:4] == [
        (4, 5.0),
        (len(payload), 5.0),
    ]
    assert sock.settimeout_calls == [5.0, 12.5, 5.0, 12.5]
    assert sock.gettimeout() == 12.5


def test_wav_payload_header_and_body_alone_use_wav_timeout():
    payload = b"opaque-wav"
    sock = TimeoutTrackingSocket(wire_request("play_wav", payload))

    request = read_request(sock)

    assert request.payload == payload
    assert sock.recv_calls == [
        (4, 5.0),
        (len("play_wav"), 5.0),
        (4, 30.0),
        (len(payload), 30.0),
    ]
    assert sock.settimeout_calls == [5.0, 12.5, 30.0, 12.5]
    assert sock.gettimeout() == 12.5


def test_wav_timeout_is_restored_after_payload_timeout():
    payload = b"wav"
    sock = TimeoutTrackingSocket(
        wire_request("play_wav", payload),
        recv_error_at=4,
    )

    with pytest.raises(PayloadFrameError) as exc_info:
        read_request(sock)

    assert isinstance(
        exc_info.value.frame_error.__cause__,
        socket.timeout,
    )
    assert sock.gettimeout() == 12.5
    assert sock.settimeout_calls[-1] == 12.5


def test_command_timeout_is_restored_after_frame_timeout():
    sock = TimeoutTrackingSocket(recv_error_at=1)

    with pytest.raises(CommandFrameError) as exc_info:
        read_request(sock)

    assert isinstance(
        exc_info.value.frame_error.__cause__,
        socket.timeout,
    )
    assert sock.gettimeout() == 12.5
    assert sock.settimeout_calls == [5.0, 12.5]


def test_wav_timeout_is_restored_after_payload_eof():
    sock = TimeoutTrackingSocket(wire_request("play_wav"))

    with pytest.raises(MissingPayloadError):
        read_request(sock)

    assert sock.gettimeout() == 12.5
    assert sock.settimeout_calls[-2:] == [30.0, 12.5]


def test_json_timeout_is_restored_after_payload_frame_error():
    declared_length = (1024 * 1024 + 1).to_bytes(
        4,
        byteorder="big",
        signed=False,
    )
    sock = TimeoutTrackingSocket(
        encode_frame(b"play_pose") + declared_length
    )

    with pytest.raises(PayloadFrameError):
        read_request(sock)

    assert sock.gettimeout() == 12.5
    assert sock.settimeout_calls[-2:] == [5.0, 12.5]


def test_read_axes_response_uses_response_timeout_and_restores():
    request_socket = TimeoutTrackingSocket(wire_request("read_axes"))
    request = read_request(request_socket)
    response_socket = TimeoutTrackingSocket()

    write_response(response_socket, request, b"{}")

    assert response_socket.send_calls == [(encode_frame(b"{}"), 5.0)]
    assert response_socket.settimeout_calls == [5.0, 12.5]
    assert response_socket.gettimeout() == 12.5


def test_response_timeout_is_restored_after_send_failure():
    request = read_request(
        TimeoutTrackingSocket(wire_request("read_axes"))
    )
    failure = socket.timeout("send timed out")
    sock = TimeoutTrackingSocket(send_error=failure)

    with pytest.raises(ResponseFrameError) as exc_info:
        write_response(sock, request, b"{}")

    assert exc_info.value.frame_error.__cause__ is failure
    assert sock.gettimeout() == 12.5
    assert sock.settimeout_calls == [5.0, 12.5]


def test_non_response_command_does_not_apply_response_timeout():
    request = read_request(
        TimeoutTrackingSocket(wire_request("stop_pose"))
    )
    sock = TimeoutTrackingSocket()

    with pytest.raises(ResponseNotAllowedError):
        write_response(sock, request, b"not-allowed")

    assert sock.send_calls == []
    assert sock.settimeout_calls == []
    assert sock.gettimeout() == 12.5
