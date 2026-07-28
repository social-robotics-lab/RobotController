"""SotaAppManager transport tests using only injected socket doubles."""

import socket

import pytest

from robot_controller.hardware.vsmd.app_manager_codec import (
    JAVA_STREAM_HEADER,
    SERIALIZED_OK,
)
from robot_controller.hardware.vsmd.app_manager_transport import (
    AppManagerTcpTransport,
)
from robot_controller.hardware.vsmd.errors import (
    AppManagerConnectionError,
    AppManagerOutcomeUnknownError,
    AppManagerProtocolError,
    AppManagerTimeoutError,
    VsmdValidationError,
)


REQUEST = b'{"cmd":"INTERP_CNV_KEY_2_ADDR","subjson":"{}"}'


class StubSocket(object):
    def __init__(self, receives, events=None, send_error=None):
        self.receives = list(receives)
        self.events = [] if events is None else events
        self.send_error = send_error
        self.sent = []
        self.close_count = 0
        self.timeouts = []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def recv(self, size):
        self.events.append(("recv", size))
        if not self.receives:
            return b""
        item = self.receives.pop(0)
        if isinstance(item, BaseException):
            raise item
        if len(item) > size:
            self.receives.insert(0, item[size:])
            return item[:size]
        return item

    def sendall(self, data):
        self.events.append(("send", bytes(data)))
        self.sent.append(bytes(data))
        if self.send_error is not None:
            raise self.send_error

    def close(self):
        self.events.append(("close",))
        self.close_count += 1


class SocketFactory(object):
    def __init__(self, sockets):
        self.sockets = list(sockets)
        self.calls = []

    def __call__(self, address, timeout):
        self.calls.append((address, timeout))
        item = self.sockets.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def make_transport(stubs, max_response_bytes=4096):
    factory = SocketFactory(stubs)
    return (
        AppManagerTcpTransport(
            socket_factory=factory,
            max_response_bytes=max_response_bytes,
        ),
        factory,
    )


def test_header_is_read_before_ascii_json_plus_one_lf_is_sent():
    events = []
    stub = StubSocket([JAVA_STREAM_HEADER, b"\x74\x00\x02OK", b""], events)
    transport, factory = make_transport([stub])
    assert transport.request(REQUEST) == SERIALIZED_OK
    assert factory.calls == [(("127.0.0.1", 6495), 2.0)]
    assert stub.sent == [REQUEST + b"\n"]
    assert b"\r\n" not in stub.sent[0]
    send_index = events.index(("send", REQUEST + b"\n"))
    assert all(event[0] == "recv" for event in events[:send_index])


def test_each_request_uses_one_new_connection_and_closes_it():
    first = StubSocket([JAVA_STREAM_HEADER, b"\x70", b""])
    second = StubSocket([JAVA_STREAM_HEADER, b"\x70", b""])
    transport, factory = make_transport([first, second])
    transport.request(REQUEST)
    transport.request(REQUEST)
    assert len(factory.calls) == 2
    assert first.close_count == 1
    assert second.close_count == 1


def test_partial_header_and_response_are_combined_until_server_eof():
    stub = StubSocket(
        [b"\xac", b"\xed\x00", b"\x05", b"\x74", b"\x00\x02", b"O", b"K", b""]
    )
    transport, unused_factory = make_transport([stub])
    assert transport.request(REQUEST) == SERIALIZED_OK


def test_response_size_limit_is_protocol_error_and_socket_closes():
    stub = StubSocket([JAVA_STREAM_HEADER, b"12345"])
    transport, unused_factory = make_transport([stub], max_response_bytes=8)
    with pytest.raises(AppManagerProtocolError, match="maximum"):
        transport.request(REQUEST)
    assert stub.close_count == 1


def test_connect_timeout_and_failure_are_distinct_and_do_not_retry():
    transport, factory = make_transport([socket.timeout("connect")])
    with pytest.raises(AppManagerTimeoutError):
        transport.request(REQUEST)
    assert len(factory.calls) == 1

    transport, factory = make_transport([OSError("refused")])
    with pytest.raises(AppManagerConnectionError):
        transport.request(REQUEST)
    assert len(factory.calls) == 1


def test_eof_and_timeout_before_header_are_pre_submission_failures():
    eof_stub = StubSocket([b"\xac", b""])
    transport, unused_factory = make_transport([eof_stub])
    with pytest.raises(AppManagerProtocolError, match="EOF"):
        transport.request(REQUEST)
    assert eof_stub.sent == []
    assert eof_stub.close_count == 1

    timeout_stub = StubSocket([socket.timeout("header")])
    transport, unused_factory = make_transport([timeout_stub])
    with pytest.raises(AppManagerTimeoutError):
        transport.request(REQUEST)
    assert timeout_stub.sent == []
    assert timeout_stub.close_count == 1


def test_invalid_server_header_is_rejected_before_send():
    stub = StubSocket([b"\xac\xed\x00\x04"])
    transport, unused_factory = make_transport([stub])
    with pytest.raises(AppManagerProtocolError, match="version"):
        transport.request(REQUEST)
    assert stub.sent == []


def test_send_or_receive_timeout_after_submission_is_outcome_unknown():
    send_stub = StubSocket(
        [JAVA_STREAM_HEADER], send_error=socket.timeout("send")
    )
    transport, unused_factory = make_transport([send_stub])
    with pytest.raises(AppManagerOutcomeUnknownError):
        transport.request(REQUEST)
    assert len(send_stub.sent) == 1
    assert send_stub.close_count == 1

    read_stub = StubSocket(
        [JAVA_STREAM_HEADER, socket.timeout("response")]
    )
    transport, unused_factory = make_transport([read_stub])
    with pytest.raises(AppManagerOutcomeUnknownError):
        transport.request(REQUEST)
    assert len(read_stub.sent) == 1
    assert read_stub.close_count == 1


def test_request_must_not_include_line_ending():
    transport, factory = make_transport([])
    with pytest.raises(VsmdValidationError):
        transport.request(REQUEST + b"\n")
    assert factory.calls == []
