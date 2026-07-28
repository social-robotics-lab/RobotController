"""Buffered VSMD transport behavior without external sockets or hardware."""

import socket

import pytest

from robot_controller.hardware.vsmd.errors import (
    VsmdLineTooLongError,
    VsmdTransportStateError,
    VsmdTransportTimeoutError,
    VsmdUnexpectedEofError,
    VsmdWriteOutcomeUnknownError,
)
from robot_controller.hardware.vsmd.transport import VsmdTcpTransport


BANNER = b"#vs-rc020 (Oct 31 2018 14:44:11)\r\n"


class StubSocket(object):
    def __init__(self, receives, send_error=None):
        self.receives = list(receives)
        self.send_error = send_error
        self.sent = []
        self.timeouts = []
        self.close_count = 0

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def recv(self, size):
        if not self.receives:
            return b""
        item = self.receives.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def sendall(self, data):
        self.sent.append(bytes(data))
        if self.send_error is not None:
            raise self.send_error

    def close(self):
        self.close_count += 1


class SocketFactory(object):
    def __init__(self, stub):
        self.stub = stub
        self.calls = []

    def __call__(self, address, timeout):
        self.calls.append((address, timeout))
        return self.stub


def make_transport(receives, max_line_length=4096, send_error=None):
    stub = StubSocket(receives, send_error=send_error)
    factory = SocketFactory(stub)
    transport = VsmdTcpTransport(
        socket_factory=factory, max_line_length=max_line_length
    )
    return transport, stub, factory


def test_banner_arrives_in_one_packet():
    transport, unused_stub, factory = make_transport([BANNER])
    transport.connect()
    assert transport.server_banner.text.startswith("#vs-")
    assert factory.calls == [(("127.0.0.1", 6498), 1.0)]


def test_fragmented_banner_is_combined():
    transport, unused_stub, unused_factory = make_transport(
        [BANNER[:4], BANNER[4:17], BANNER[17:]]
    )
    transport.connect()
    assert transport.server_banner.raw_line == BANNER


def test_banner_and_first_response_in_same_packet_preserves_response():
    response = b"#0001 00 \r\n"
    transport, unused_stub, unused_factory = make_transport(
        [BANNER + response]
    )
    transport.connect()
    assert transport.read_line() == response


def test_fragmented_response_is_combined():
    transport, unused_stub, unused_factory = make_transport(
        [BANNER, b"#0001 ", b"00", b" ", b"\r\n"]
    )
    transport.connect()
    assert transport.read_line() == b"#0001 00 \r\n"


def test_coalesced_responses_are_returned_separately():
    transport, unused_stub, unused_factory = make_transport(
        [BANNER, b"#0001 00 \r\n#0002 ff \r\n"]
    )
    transport.connect()
    assert transport.read_line() == b"#0001 00 \r\n"
    assert transport.read_line() == b"#0002 ff \r\n"


def test_read_timeout_is_distinct_and_keeps_cause():
    transport, unused_stub, unused_factory = make_transport(
        [BANNER, socket.timeout("secret")]
    )
    transport.connect()
    with pytest.raises(VsmdTransportTimeoutError) as caught:
        transport.read_line()
    assert caught.value.operation == "read"
    assert isinstance(caught.value.__cause__, socket.timeout)


def test_eof_before_complete_line_is_rejected():
    transport, unused_stub, unused_factory = make_transport(
        [BANNER, b"#0001", b""]
    )
    transport.connect()
    with pytest.raises(VsmdUnexpectedEofError):
        transport.read_line()


def test_maximum_line_length_is_enforced_for_unterminated_and_complete_lines():
    maximum = len(BANNER)
    transport, unused_stub, unused_factory = make_transport(
        [BANNER, b"x" * maximum], max_line_length=maximum
    )
    transport.connect()
    with pytest.raises(VsmdLineTooLongError):
        transport.read_line()

    transport, unused_stub, unused_factory = make_transport(
        [BANNER, b"x" * maximum + b"\n"], max_line_length=maximum
    )
    transport.connect()
    with pytest.raises(VsmdLineTooLongError):
        transport.read_line()


def test_connect_timeout_is_bounded_and_distinct():
    def timeout_factory(address, timeout):
        raise socket.timeout("connect")

    transport = VsmdTcpTransport(socket_factory=timeout_factory)
    with pytest.raises(VsmdTransportTimeoutError) as caught:
        transport.connect()
    assert caught.value.operation == "connect"
    assert not transport.is_connected


def test_connect_and_close_are_idempotent():
    transport, stub, factory = make_transport([BANNER])
    transport.connect()
    transport.connect()
    transport.close()
    transport.close()
    assert len(factory.calls) == 1
    assert stub.close_count == 1


def test_operations_outside_connection_are_rejected():
    transport, unused_stub, unused_factory = make_transport([])
    with pytest.raises(VsmdTransportStateError):
        transport.read_line()
    with pytest.raises(VsmdTransportStateError):
        transport.send(b"x")


def test_write_is_sent_once_and_no_response_is_read():
    transport, stub, unused_factory = make_transport([BANNER])
    transport.connect()
    transport.send(b"w 0001 00\r\n")
    assert stub.sent == [b"w 0001 00\r\n"]
    assert stub.receives == []


def test_failed_write_is_not_retried_and_outcome_is_unknown():
    transport, stub, unused_factory = make_transport(
        [BANNER], send_error=socket.timeout("late")
    )
    transport.connect()
    with pytest.raises(VsmdWriteOutcomeUnknownError):
        transport.send(b"w 0001 00\r\n")
    assert stub.sent == [b"w 0001 00\r\n"]
