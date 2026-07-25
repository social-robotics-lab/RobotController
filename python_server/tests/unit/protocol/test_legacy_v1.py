"""Unit tests for one-command legacy v1 sessions."""

import socket

import pytest

from robot_controller.errors import (
    CommandDecodeError,
    CommandFrameError,
    EmptyCommandError,
    MissingPayloadError,
    PayloadFrameError,
    ResponseFrameError,
    ResponseNotAllowedError,
    UnknownCommandError,
)
from robot_controller.protocol.commands import (
    COMMAND_SPECS,
    DEFAULT_LIMITS,
    PAYLOAD_JSON,
    PAYLOAD_NONE,
    PAYLOAD_WAV,
    LegacyV1Limits,
)
from robot_controller.protocol.frame import encode_frame
from robot_controller.protocol.legacy_v1 import (
    LegacyV1Request,
    read_request,
    write_response,
)


class FakeSocket(object):
    """Deterministic socket double for session tests."""

    def __init__(self, recv_results=None, send_error=None, timeout=12.5):
        self.recv_results = list(recv_results or [])
        self.recv_calls = []
        self.send_error = send_error
        self.sent_data = []
        self.timeout = timeout
        self.settimeout_calls = []

    def recv(self, size):
        self.recv_calls.append(size)
        if not self.recv_results:
            return b""
        result = self.recv_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        if len(result) <= size:
            return result
        self.recv_results.insert(0, result[size:])
        return result[:size]

    def sendall(self, data):
        self.sent_data.append(data)
        if self.send_error is not None:
            raise self.send_error

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.settimeout_calls.append(value)
        self.timeout = value


def framed_socket(*payloads):
    """Return a fake socket containing one encoded frame per payload."""
    encoded = b"".join([encode_frame(payload) for payload in payloads])
    return FakeSocket([encoded])


def test_command_metadata_contains_exactly_the_nine_v1_commands():
    assert set(COMMAND_SPECS) == {
        "play_wav",
        "stop_wav",
        "play_pose",
        "stop_pose",
        "play_motion",
        "stop_motion",
        "play_idle_motion",
        "stop_idle_motion",
        "read_axes",
    }


def test_command_metadata_centralizes_payload_and_response_rules():
    assert COMMAND_SPECS["play_wav"].payload_kind == PAYLOAD_WAV
    assert COMMAND_SPECS["play_pose"].payload_kind == PAYLOAD_JSON
    assert COMMAND_SPECS["stop_pose"].payload_kind == PAYLOAD_NONE
    assert COMMAND_SPECS["read_axes"].expects_response is True
    assert sum(
        1 for spec in COMMAND_SPECS.values() if spec.expects_response
    ) == 1


def test_default_frame_limits_match_v1_specification():
    assert DEFAULT_LIMITS.command_max_length == 64
    assert DEFAULT_LIMITS.json_max_length == 1024 * 1024
    assert DEFAULT_LIMITS.wav_max_length == 20 * 1024 * 1024


@pytest.mark.parametrize("command", ["read_axes", "stop_pose"])
def test_read_command_without_payload(command):
    sock = framed_socket(command.encode("utf-8"))
    request = read_request(sock)
    assert request.command == command
    assert request.payload is None
    assert sock.sent_data == []


@pytest.mark.parametrize(
    "command",
    ["play_pose", "play_motion", "play_idle_motion"],
)
def test_read_json_payload_command(command):
    payload = b'{"Msec":500}'
    request = read_request(framed_socket(command.encode("utf-8"), payload))
    assert request.command == command
    assert request.payload == payload
    assert request.payload_kind == PAYLOAD_JSON
    assert request.expects_response is False


def test_read_play_wav_with_arbitrary_binary_payload():
    payload = b"RIFF\x00\xffWAVE\x80"
    request = read_request(framed_socket(b"play_wav", payload))
    assert request.command == "play_wav"
    assert request.payload == payload
    assert request.payload_kind == PAYLOAD_WAV


def test_read_json_payload_with_japanese_utf8_bytes():
    payload = '{"message":"こんにちは"}'.encode("utf-8")
    request = read_request(framed_socket(b"play_pose", payload))
    assert request.payload == payload


def test_read_wav_payload_preserves_nul_and_binary_bytes():
    payload = b"\x00\xff\x00\x80binary"
    request = read_request(framed_socket(b"play_wav", payload))
    assert request.payload == payload


def test_write_read_axes_response_uses_existing_frame_format():
    sock = FakeSocket()
    request = read_request(framed_socket(b"read_axes"))
    write_response(sock, request, b'{"HEAD_Y":0}')
    assert sock.sent_data == [encode_frame(b'{"HEAD_Y":0}')]


def test_empty_command_is_rejected():
    with pytest.raises(EmptyCommandError):
        read_request(framed_socket(b""))


def test_invalid_utf8_command_is_rejected():
    with pytest.raises(CommandDecodeError) as exc_info:
        read_request(framed_socket(b"\xff"))
    assert isinstance(exc_info.value.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize(
    "command",
    [
        b"unknown",
        b"READ_AXES",
        b" read_axes",
        b"read_axes ",
        b"read_axes\x00",
        b"x" * 64,
    ],
)
def test_unknown_command_variants_are_rejected_without_normalization(command):
    with pytest.raises(UnknownCommandError) as exc_info:
        read_request(framed_socket(command))
    assert exc_info.value.command == command.decode("utf-8")


def test_command_frame_over_64_bytes_is_wrapped():
    sock = framed_socket(b"x" * 65)
    with pytest.raises(CommandFrameError) as exc_info:
        read_request(sock)
    assert exc_info.value.frame_error.declared_length == 65
    assert exc_info.value.__cause__ is exc_info.value.frame_error


@pytest.mark.parametrize("command", [b"play_pose", b"play_wav"])
def test_empty_required_payload_is_rejected(command):
    with pytest.raises(MissingPayloadError) as exc_info:
        read_request(framed_socket(command, b""))
    assert exc_info.value.command == command.decode("utf-8")


@pytest.mark.parametrize(
    "command,limit_name,size",
    [
        (b"play_pose", "json_max_length", 1024 * 1024),
        (b"play_wav", "wav_max_length", 20 * 1024 * 1024),
    ],
)
def test_payload_at_default_maximum_is_accepted(command, limit_name, size):
    payload = b"x" * size
    request = read_request(framed_socket(command, payload))
    assert request.payload == payload
    assert getattr(DEFAULT_LIMITS, limit_name) == size


@pytest.mark.parametrize(
    "command,declared_length,max_length",
    [
        (b"play_pose", 1024 * 1024 + 1, 1024 * 1024),
        (b"play_wav", 20 * 1024 * 1024 + 1, 20 * 1024 * 1024),
    ],
)
def test_payload_over_default_maximum_is_wrapped(
    command, declared_length, max_length
):
    header = declared_length.to_bytes(4, byteorder="big", signed=False)
    sock = FakeSocket([encode_frame(command) + header, b"never read"])
    with pytest.raises(PayloadFrameError) as exc_info:
        read_request(sock)
    assert exc_info.value.frame_error.declared_length == declared_length
    assert exc_info.value.frame_error.max_length == max_length
    assert sock.recv_calls == [4, len(command), 4]


def test_payload_eof_before_second_frame_is_missing_payload():
    with pytest.raises(MissingPayloadError) as exc_info:
        read_request(framed_socket(b"play_pose"))
    assert exc_info.value.frame_error.stage == "header"
    assert exc_info.value.frame_error.received_bytes == 0


def test_payload_eof_during_body_is_wrapped():
    sock = FakeSocket([encode_frame(b"play_pose"), b"\x00\x00\x00\x04", b"{}"])
    with pytest.raises(PayloadFrameError) as exc_info:
        read_request(sock)
    assert exc_info.value.frame_error.stage == "payload"
    assert exc_info.value.frame_error.received_bytes == 2


def test_payload_timeout_is_wrapped():
    sock = FakeSocket(
        [encode_frame(b"play_pose"), b"\x00\x00\x00\x04", socket.timeout()]
    )
    with pytest.raises(PayloadFrameError) as exc_info:
        read_request(sock)
    assert exc_info.value.frame_error.stage == "payload"


@pytest.mark.parametrize(
    "command",
    [b"stop_wav", b"stop_pose", b"stop_motion", b"stop_idle_motion", b"read_axes"],
)
def test_payload_free_command_does_not_read_second_frame(command):
    extra_frame = encode_frame(b"must remain unread")
    sock = FakeSocket([encode_frame(command), extra_frame])
    request = read_request(sock)
    assert request.payload is None
    assert sock.recv_calls == [4, len(command)]
    assert sock.recv_results == [extra_frame]


@pytest.mark.parametrize(
    "command",
    [
        b"play_wav",
        b"stop_wav",
        b"play_pose",
        b"stop_pose",
        b"play_motion",
        b"stop_motion",
        b"play_idle_motion",
        b"stop_idle_motion",
    ],
)
def test_non_response_command_never_sends_automatically(command):
    payloads = [command]
    if COMMAND_SPECS[command.decode("ascii")].payload_required:
        payloads.append(b"x")
    sock = framed_socket(*payloads)
    request = read_request(sock)
    assert request.expects_response is False
    assert sock.sent_data == []


def test_read_axes_does_not_send_automatically():
    sock = framed_socket(b"read_axes")
    request = read_request(sock)
    assert request.expects_response is True
    assert sock.sent_data == []


def test_write_response_rejects_non_response_command_without_send():
    request = read_request(framed_socket(b"stop_pose"))
    sock = FakeSocket()
    with pytest.raises(ResponseNotAllowedError):
        write_response(sock, request, b"response")
    assert sock.sent_data == []


def test_write_response_rejects_forged_response_metadata():
    request = LegacyV1Request(
        command="stop_pose",
        payload=None,
        expects_response=True,
        payload_kind=PAYLOAD_NONE,
    )
    sock = FakeSocket()
    with pytest.raises(ResponseNotAllowedError):
        write_response(sock, request, b"response")
    assert sock.sent_data == []


def test_response_frame_error_is_wrapped():
    request = read_request(framed_socket(b"read_axes"))
    sock = FakeSocket(send_error=OSError("send failed"))
    with pytest.raises(ResponseFrameError) as exc_info:
        write_response(sock, request, b"response")
    assert exc_info.value.frame_error.expected_bytes == 12
    assert exc_info.value.__cause__ is exc_info.value.frame_error


def test_robo_tutorial_play_pose_golden_bytes():
    json_payload = b'{"Msec":500,"ServoMap":{"HEAD_Y":20}}'
    wire_bytes = (
        b"\x00\x00\x00\x09play_pose"
        + len(json_payload).to_bytes(4, byteorder="big", signed=False)
        + json_payload
    )
    request = read_request(FakeSocket([wire_bytes]))
    assert request.command == "play_pose"
    assert request.payload == json_payload


def test_robo_tutorial_read_axes_golden_bytes():
    request = read_request(
        FakeSocket([b"\x00\x00\x00\x09read_axes"])
    )
    assert request.command == "read_axes"
    assert request.payload is None


def test_complete_request_survives_client_write_shutdown():
    if not hasattr(socket, "socketpair"):
        pytest.skip("socket.socketpair is unavailable")

    reader, writer = socket.socketpair()
    try:
        writer.sendall(encode_frame(b"play_pose") + encode_frame(b"{}"))
        writer.shutdown(socket.SHUT_WR)
        request = read_request(reader)
        assert request.command == "play_pose"
        assert request.payload == b"{}"
    finally:
        reader.close()
        writer.close()


def test_custom_limits_are_applied_by_payload_kind():
    limits = LegacyV1Limits(
        command_max_length=9,
        json_max_length=2,
        wav_max_length=3,
    )
    assert read_request(
        framed_socket(b"play_pose", b"{}"), limits=limits
    ).payload == b"{}"
    assert read_request(
        framed_socket(b"play_wav", b"\x00\x01\x02"), limits=limits
    ).payload == b"\x00\x01\x02"
