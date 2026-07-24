"""Unit tests for the legacy v1 frame codec."""

import socket

import pytest

from robot_controller.errors import (
    ConnectionClosedError,
    FrameReadError,
    FrameTimeoutError,
    FrameTooLargeError,
    FrameWriteError,
    InvalidFrameLengthError,
)
from robot_controller.protocol.frame import encode_frame, read_frame, write_frame


class FakeSocket(object):
    """Deterministic socket double supporting recv() and sendall()."""

    def __init__(self, recv_results=None, send_error=None):
        self.recv_results = list(recv_results or [])
        self.recv_calls = []
        self.send_error = send_error
        self.sent_data = []

    def recv(self, size):
        self.recv_calls.append(size)
        if not self.recv_results:
            return b""
        result = self.recv_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def sendall(self, data):
        self.sent_data.append(data)
        if self.send_error is not None:
            raise self.send_error


def test_encode_read_axes_golden_bytes():
    assert encode_frame(b"read_axes") == b"\x00\x00\x00\x09read_axes"


def test_encode_empty_payload():
    assert encode_frame(b"") == b"\x00\x00\x00\x00"


def test_encode_arbitrary_binary_payload():
    payload = b"\x00\xffRIFF\x80"
    assert encode_frame(payload) == b"\x00\x00\x00\x07" + payload


def test_encode_rejects_non_bytes_payload():
    with pytest.raises(TypeError):
        encode_frame(bytearray(b"data"))


def test_encode_rejects_payload_larger_than_v1_limit():
    class OversizedBytes(bytes):
        def __len__(self):
            return 0x80000000

    with pytest.raises(InvalidFrameLengthError) as exc_info:
        encode_frame(OversizedBytes(b""))

    assert exc_info.value.declared_length == 0x80000000


def test_read_empty_payload():
    sock = FakeSocket([b"\x00\x00\x00\x00"])
    assert read_frame(sock, max_length=0) == b""
    assert sock.recv_calls == [4]


def test_read_arbitrary_binary_payload():
    payload = b"\x00\xff\x10\x80"
    sock = FakeSocket([b"\x00\x00\x00\x04", payload])
    assert read_frame(sock, max_length=4) == payload


def test_read_utf8_json_with_japanese_text_as_opaque_bytes():
    payload = '{"message":"こんにちは"}'.encode("utf-8")
    sock = FakeSocket([encode_frame(payload)[:4], payload])
    assert read_frame(sock, max_length=len(payload)) == payload


def test_read_length_exactly_at_configured_maximum():
    sock = FakeSocket([b"\x00\x00\x00\x04", b"data"])
    assert read_frame(sock, max_length=4) == b"data"


def test_read_rejects_length_over_configured_maximum():
    sock = FakeSocket([b"\x00\x00\x00\x05", b"never read"])

    with pytest.raises(FrameTooLargeError) as exc_info:
        read_frame(sock, max_length=4)

    error = exc_info.value
    assert error.stage == "header"
    assert error.declared_length == 5
    assert error.max_length == 4
    assert sock.recv_calls == [4]


def test_read_accepts_0x7fffffff_header_without_allocating_in_advance():
    sock = FakeSocket([b"\x7f\xff\xff\xff", b""])

    with pytest.raises(ConnectionClosedError) as exc_info:
        read_frame(sock, max_length=0x7FFFFFFF)

    error = exc_info.value
    assert error.stage == "payload"
    assert error.expected_bytes == 0x7FFFFFFF
    assert error.received_bytes == 0


def test_read_rejects_0x80000000_header_before_payload_read():
    sock = FakeSocket([b"\x80\x00\x00\x00", b"never read"])

    with pytest.raises(InvalidFrameLengthError) as exc_info:
        read_frame(sock, max_length=0xFFFFFFFF)

    error = exc_info.value
    assert error.stage == "header"
    assert error.declared_length == 0x80000000
    assert sock.recv_calls == [4]


def test_read_frame_received_in_one_chunk_per_part():
    sock = FakeSocket([b"\x00\x00\x00\x04", b"data"])
    assert read_frame(sock, max_length=4) == b"data"
    assert sock.recv_calls == [4, 4]


def test_read_frame_with_split_header():
    sock = FakeSocket([b"\x00", b"\x00\x00", b"\x04", b"data"])
    assert read_frame(sock, max_length=4) == b"data"
    assert sock.recv_calls == [4, 3, 1, 4]


def test_read_frame_with_split_payload():
    sock = FakeSocket([b"\x00\x00\x00\x04", b"d", b"at", b"a"])
    assert read_frame(sock, max_length=4) == b"data"
    assert sock.recv_calls == [4, 4, 3, 1]


def test_read_frame_one_byte_at_a_time():
    encoded = b"\x00\x00\x00\x04data"
    sock = FakeSocket([bytes(bytearray([value])) for value in bytearray(encoded)])
    assert read_frame(sock, max_length=4) == b"data"


def test_read_eof_before_header():
    sock = FakeSocket([b""])

    with pytest.raises(ConnectionClosedError) as exc_info:
        read_frame(sock, max_length=64)

    error = exc_info.value
    assert error.stage == "header"
    assert error.expected_bytes == 4
    assert error.received_bytes == 0


def test_read_eof_during_header():
    sock = FakeSocket([b"\x00\x00", b""])

    with pytest.raises(ConnectionClosedError) as exc_info:
        read_frame(sock, max_length=64)

    error = exc_info.value
    assert error.stage == "header"
    assert error.expected_bytes == 4
    assert error.received_bytes == 2


def test_read_eof_during_payload():
    sock = FakeSocket([b"\x00\x00\x00\x04", b"da", b""])

    with pytest.raises(ConnectionClosedError) as exc_info:
        read_frame(sock, max_length=4)

    error = exc_info.value
    assert error.stage == "payload"
    assert error.expected_bytes == 4
    assert error.received_bytes == 2


def test_read_timeout_during_header():
    sock = FakeSocket([b"\x00", socket.timeout("timed out")])

    with pytest.raises(FrameTimeoutError) as exc_info:
        read_frame(sock, max_length=64)

    error = exc_info.value
    assert error.stage == "header"
    assert error.expected_bytes == 4
    assert error.received_bytes == 1
    assert isinstance(error.__cause__, socket.timeout)


def test_read_timeout_during_payload():
    sock = FakeSocket(
        [b"\x00\x00\x00\x04", b"d", socket.timeout("timed out")]
    )

    with pytest.raises(FrameTimeoutError) as exc_info:
        read_frame(sock, max_length=4)

    error = exc_info.value
    assert error.stage == "payload"
    assert error.expected_bytes == 4
    assert error.received_bytes == 1


def test_read_socket_error_preserves_progress():
    sock = FakeSocket([b"\x00", OSError("read failed")])

    with pytest.raises(FrameReadError) as exc_info:
        read_frame(sock, max_length=64)

    error = exc_info.value
    assert error.stage == "header"
    assert error.expected_bytes == 4
    assert error.received_bytes == 1
    assert isinstance(error.__cause__, OSError)


@pytest.mark.parametrize("max_length", [-1, True, 1.5])
def test_read_rejects_invalid_max_length(max_length):
    sock = FakeSocket([b"\x00\x00\x00\x00"])
    with pytest.raises((TypeError, ValueError)):
        read_frame(sock, max_length=max_length)
    assert sock.recv_calls == []


def test_write_frame_uses_complete_send():
    sock = FakeSocket()
    write_frame(sock, b"data")
    assert sock.sent_data == [b"\x00\x00\x00\x04data"]


def test_write_frame_wraps_socket_error():
    sock = FakeSocket(send_error=OSError("send failed"))

    with pytest.raises(FrameWriteError) as exc_info:
        write_frame(sock, b"data")

    assert exc_info.value.expected_bytes == 8
    assert isinstance(exc_info.value.__cause__, OSError)


def test_socketpair_round_trip_when_available():
    if not hasattr(socket, "socketpair"):
        pytest.skip("socket.socketpair is unavailable")

    reader, writer = socket.socketpair()
    try:
        write_frame(writer, b"round trip")
        assert read_frame(reader, max_length=10) == b"round trip"
    finally:
        reader.close()
        writer.close()
