"""Unit tests for the bounded legacy v1 TCP server."""

import socket
import threading

import pytest

from robot_controller.command_target import RecordingCommandTarget
from robot_controller.errors import (
    CommandExecutionError,
    CommandFrameError,
    FrameTooLargeError,
    FrameWriteError,
    InvalidFieldValueError,
    ResponseFrameError,
)
from robot_controller.profiles import RobotProfile
from robot_controller.protocol.commands import (
    DEFAULT_LIMITS,
    LegacyV1Limits,
)
from robot_controller.protocol.validation import (
    DEFAULT_VALIDATION_LIMITS,
    ValidationLimits,
)
from robot_controller.router import CommandRouter
from robot_controller.tcp_server import (
    DEFAULT_BACKLOG,
    DEFAULT_CLIENT_TIMEOUT_SECONDS,
    DEFAULT_HOST,
    DEFAULT_MAX_WORKERS,
    DEFAULT_PORT,
    LegacyV1TcpServer,
    LegacyV1TcpServerConfig,
)


class FakeClientSocket(object):
    """Accepted socket double with deterministic ownership tracking."""

    def __init__(self, name, events=None, settimeout_error=None, close_error=None):
        self.name = name
        self.events = events if events is not None else []
        self.settimeout_error = settimeout_error
        self.close_error = close_error
        self.timeout_values = []
        self.close_calls = 0
        self.shutdown_calls = []
        self.sent_data = []

    def settimeout(self, value):
        self.events.append(("settimeout", self.name, value))
        self.timeout_values.append(value)
        if self.settimeout_error is not None:
            raise self.settimeout_error

    def close(self):
        self.events.append(("client_close", self.name))
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error

    def shutdown(self, how):
        self.shutdown_calls.append(how)

    def sendall(self, data):
        self.sent_data.append(data)


class FakeListeningSocket(object):
    """Listening socket double with scripted accept results."""

    def __init__(self, accept_results=None, bound_address=("127.0.0.1", 41000)):
        self.accept_results = list(accept_results or [])
        self.bound_address = bound_address
        self.events = []
        self.close_calls = 0
        self.shutdown_calls = []
        self.on_empty = None

    def setsockopt(self, level, option, value):
        self.events.append(("setsockopt", level, option, value))

    def bind(self, address):
        self.events.append(("bind", address))

    def listen(self, backlog):
        self.events.append(("listen", backlog))

    def getsockname(self):
        self.events.append(("getsockname",))
        return self.bound_address

    def accept(self):
        self.events.append(("accept",))
        if self.accept_results:
            result = self.accept_results.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result
        if self.on_empty is not None:
            self.on_empty()
        raise OSError("listening socket closed")

    def close(self):
        self.events.append(("listen_close",))
        self.close_calls += 1

    def shutdown(self, how):
        self.events.append(("listen_shutdown", how))
        self.shutdown_calls.append(how)


class BlockingListeningSocket(FakeListeningSocket):
    """Listening socket that blocks its second accept until close."""

    def __init__(self, first_result):
        FakeListeningSocket.__init__(self, [first_result])
        self.accept_waiting = threading.Event()
        self.closed_event = threading.Event()

    def accept(self):
        if self.accept_results:
            return FakeListeningSocket.accept(self)
        self.events.append(("accept",))
        self.accept_waiting.set()
        if not self.closed_event.wait(5.0):
            raise AssertionError("listening socket was not closed")
        raise OSError("listening socket closed")

    def close(self):
        FakeListeningSocket.close(self)
        self.closed_event.set()


class FakeSocketFactory(object):
    """Callable socket factory returning one scripted listening socket."""

    def __init__(self, listening_socket):
        self.listening_socket = listening_socket
        self.calls = []

    def __call__(self, family, socket_type):
        self.calls.append((family, socket_type))
        return self.listening_socket


class FakeFuture(object):
    """Minimal executor Future stand-in."""


class ImmediateExecutor(object):
    """Executor double that runs submitted work synchronously."""

    def __init__(self):
        self.submit_calls = []
        self.shutdown_calls = []

    def submit(self, function, *args):
        self.submit_calls.append((function, args))
        function(*args)
        return FakeFuture()

    def shutdown(self, wait=True):
        self.shutdown_calls.append(wait)


class HoldingExecutor(object):
    """Executor double retaining work until graceful shutdown."""

    def __init__(self):
        self.submit_calls = []
        self.pending = []
        self.shutdown_calls = []

    def submit(self, function, *args):
        self.submit_calls.append((function, args))
        self.pending.append((function, args))
        return FakeFuture()

    def shutdown(self, wait=True):
        self.shutdown_calls.append(wait)
        while self.pending:
            function, args = self.pending.pop(0)
            function(*args)


class FailingSubmitExecutor(ImmediateExecutor):
    """Executor double that rejects every submission."""

    def submit(self, function, *args):
        self.submit_calls.append((function, args))
        raise RuntimeError("submit failed")


class FakeExecutorFactory(object):
    """Callable factory recording construction timing and max_workers."""

    def __init__(self, executor):
        self.executor = executor
        self.calls = []

    def __call__(self, max_workers):
        self.calls.append(max_workers)
        return self.executor


@pytest.fixture
def robot_profile():
    """Return a small hardware-independent profile."""
    return RobotProfile({"HEAD_Y": (-20, 20)}, {"Mouth": (0, 255)})


@pytest.fixture
def router():
    """Return a Router backed by the recording command target."""
    return CommandRouter(RecordingCommandTarget())


def make_server(
    robot_profile,
    router,
    listening_socket,
    executor,
    config=None,
    handler=None,
):
    """Construct a server with deterministic socket and executor factories."""
    socket_factory = FakeSocketFactory(listening_socket)
    executor_factory = FakeExecutorFactory(executor)
    kwargs = {}
    if handler is not None:
        kwargs["connection_handler"] = handler
    server = LegacyV1TcpServer(
        robot_profile=robot_profile,
        router=router,
        config=config or LegacyV1TcpServerConfig(),
        socket_factory=socket_factory,
        executor_factory=executor_factory,
        **kwargs
    )
    return server, socket_factory, executor_factory


def stop_when_accept_queue_is_empty(server, listening_socket):
    """Arrange deterministic shutdown after scripted accepts are exhausted."""
    listening_socket.on_empty = server.shutdown


def test_config_defaults_match_confirmed_server_values():
    config = LegacyV1TcpServerConfig()
    assert config.host == DEFAULT_HOST == "0.0.0.0"
    assert config.port == DEFAULT_PORT == 22222
    assert config.backlog == DEFAULT_BACKLOG == 16
    assert config.max_workers == DEFAULT_MAX_WORKERS == 16
    assert (
        config.client_timeout_seconds
        == DEFAULT_CLIENT_TIMEOUT_SECONDS
        == 5.0
    )
    assert config.session_limits is DEFAULT_LIMITS
    assert config.decoder_limits is DEFAULT_VALIDATION_LIMITS


@pytest.mark.parametrize("port", [-1, 65536, True, 1.5, "22222"])
def test_config_rejects_invalid_port(port):
    with pytest.raises((TypeError, ValueError)):
        LegacyV1TcpServerConfig(port=port)


@pytest.mark.parametrize("backlog", [0, -1, True, 1.5, "16"])
def test_config_rejects_invalid_backlog(backlog):
    with pytest.raises((TypeError, ValueError)):
        LegacyV1TcpServerConfig(backlog=backlog)


@pytest.mark.parametrize("max_workers", [0, -1, True, 1.5, "16"])
def test_config_rejects_invalid_max_workers(max_workers):
    with pytest.raises((TypeError, ValueError)):
        LegacyV1TcpServerConfig(max_workers=max_workers)


@pytest.mark.parametrize(
    "timeout",
    [0, -1, True, float("inf"), -float("inf"), float("nan"), "5"],
)
def test_config_rejects_invalid_timeout(timeout):
    with pytest.raises((TypeError, ValueError)):
        LegacyV1TcpServerConfig(client_timeout_seconds=timeout)


def test_config_rejects_invalid_host_and_limit_objects():
    with pytest.raises(TypeError):
        LegacyV1TcpServerConfig(host=123)
    with pytest.raises(TypeError):
        LegacyV1TcpServerConfig(session_limits=object())
    with pytest.raises(TypeError):
        LegacyV1TcpServerConfig(decoder_limits=object())


def test_config_accepts_port_zero_and_custom_immutable_limits():
    session_limits = LegacyV1Limits(9, 100, 200)
    decoder_limits = ValidationLimits(max_motion_poses=2)
    config = LegacyV1TcpServerConfig(
        host="127.0.0.1",
        port=0,
        backlog=3,
        max_workers=2,
        client_timeout_seconds=1,
        session_limits=session_limits,
        decoder_limits=decoder_limits,
    )
    assert config.port == 0
    assert config.session_limits is session_limits
    assert config.decoder_limits is decoder_limits


def test_constructor_does_not_create_socket_executor_or_thread(
    robot_profile, router
):
    listening = FakeListeningSocket()
    socket_factory = FakeSocketFactory(listening)
    executor_factory = FakeExecutorFactory(ImmediateExecutor())
    before_threads = tuple(threading.enumerate())

    server = LegacyV1TcpServer(
        robot_profile,
        router,
        LegacyV1TcpServerConfig(),
        socket_factory=socket_factory,
        executor_factory=executor_factory,
    )

    assert socket_factory.calls == []
    assert executor_factory.calls == []
    assert tuple(threading.enumerate()) == before_threads
    assert server.bound_address is None
    assert server.is_listening is False
    assert server.is_stopped is False


def test_serve_creates_binds_and_listens_once_in_order(
    robot_profile, router
):
    listening = FakeListeningSocket(bound_address=("127.0.0.1", 42000))
    executor = ImmediateExecutor()
    config = LegacyV1TcpServerConfig(
        host="127.0.0.1", port=0, backlog=7, max_workers=2
    )
    server, socket_factory, executor_factory = make_server(
        robot_profile, router, listening, executor, config
    )
    stop_when_accept_queue_is_empty(server, listening)

    server.serve_forever()

    assert socket_factory.calls == [(socket.AF_INET, socket.SOCK_STREAM)]
    assert listening.events[:4] == [
        ("setsockopt", socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
        ("bind", ("127.0.0.1", 0)),
        ("listen", 7),
        ("getsockname",),
    ]
    assert sum(1 for event in listening.events if event[0] == "listen") == 1
    assert executor_factory.calls == [2]
    assert server.bound_address == ("127.0.0.1", 42000)
    assert server.wait_until_listening(0) is True
    assert server.is_listening is False
    assert server.is_stopped is True
    assert listening.close_calls == 1
    assert executor.shutdown_calls == [True]


def test_listening_callback_runs_only_after_bound_address_is_available(
    robot_profile, router
):
    listening = FakeListeningSocket(bound_address=("127.0.0.1", 42001))
    executor = ImmediateExecutor()
    callback_observations = []

    def on_listening(server):
        callback_observations.append(
            (server.bound_address, server.is_listening)
        )
        server.shutdown()

    server = LegacyV1TcpServer(
        robot_profile=robot_profile,
        router=router,
        socket_factory=FakeSocketFactory(listening),
        executor_factory=FakeExecutorFactory(executor),
        on_listening=on_listening,
    )

    assert callback_observations == []
    server.serve_forever()

    assert callback_observations == [
        (("127.0.0.1", 42001), True)
    ]
    assert not any(event[0] == "accept" for event in listening.events)


def test_accepted_socket_timeout_precedes_single_handler_call_and_close(
    robot_profile, router
):
    events = []
    client = FakeClientSocket("first", events)
    listening = FakeListeningSocket([(client, ("127.0.0.1", 51000))])
    executor = ImmediateExecutor()
    calls = []

    def handler(sock, profile, actual_router, session_limits, decoder_limits):
        events.append(("handler", sock.name))
        calls.append(
            (sock, profile, actual_router, session_limits, decoder_limits)
        )

    config = LegacyV1TcpServerConfig(client_timeout_seconds=2.5)
    server, _, _ = make_server(
        robot_profile,
        router,
        listening,
        executor,
        config,
        handler,
    )
    stop_when_accept_queue_is_empty(server, listening)

    server.serve_forever()

    assert events == [
        ("settimeout", "first", 2.5),
        ("handler", "first"),
        ("client_close", "first"),
    ]
    assert len(calls) == 1
    assert calls[0][0] is client
    assert calls[0][1] is robot_profile
    assert calls[0][2] is router
    assert calls[0][3] is config.session_limits
    assert calls[0][4] is config.decoder_limits
    assert client.close_calls == 1
    assert client.shutdown_calls == []
    assert server.active_connection_count == 0


def test_capacity_rejects_connection_before_executor_submission(
    robot_profile, router
):
    first = FakeClientSocket("first")
    rejected = FakeClientSocket("rejected")
    listening = FakeListeningSocket(
        [
            (first, ("127.0.0.1", 1)),
            (rejected, ("127.0.0.1", 2)),
        ]
    )
    executor = HoldingExecutor()
    handled = []

    def handler(sock, *args, **kwargs):
        handled.append(sock.name)

    config = LegacyV1TcpServerConfig(max_workers=1)
    server, _, _ = make_server(
        robot_profile,
        router,
        listening,
        executor,
        config,
        handler,
    )
    stop_when_accept_queue_is_empty(server, listening)

    server.serve_forever()

    assert len(executor.submit_calls) == 1
    assert handled == ["first"]
    assert first.close_calls == 1
    assert rejected.timeout_values == []
    assert rejected.close_calls == 1
    assert rejected.shutdown_calls == []
    assert rejected.sent_data == []
    assert server.active_connection_count == 0


def test_capacity_is_reusable_after_normal_completion(
    robot_profile, router
):
    first = FakeClientSocket("first")
    second = FakeClientSocket("second")
    listening = FakeListeningSocket(
        [(first, ("peer", 1)), (second, ("peer", 2))]
    )
    executor = ImmediateExecutor()
    handled = []

    def handler(sock, *args, **kwargs):
        handled.append(sock.name)

    server, _, _ = make_server(
        robot_profile,
        router,
        listening,
        executor,
        LegacyV1TcpServerConfig(max_workers=1),
        handler,
    )
    stop_when_accept_queue_is_empty(server, listening)

    server.serve_forever()

    assert handled == ["first", "second"]
    assert len(executor.submit_calls) == 2
    assert first.close_calls == second.close_calls == 1
    assert server.active_connection_count == 0


@pytest.mark.parametrize(
    "failure",
    [
        CommandFrameError(FrameTooLargeError(65, 64)),
        InvalidFieldValueError("play_pose", "$.Msec", -1, "non-negative"),
        CommandExecutionError("stop_pose"),
        ResponseFrameError(FrameWriteError(8)),
        socket.timeout("timed out"),
        OSError("client failed"),
    ],
)
def test_connection_failure_does_not_stop_next_connection(
    failure, robot_profile, router
):
    first = FakeClientSocket("first")
    second = FakeClientSocket("second")
    listening = FakeListeningSocket(
        [(first, ("peer", 1)), (second, ("peer", 2))]
    )
    executor = ImmediateExecutor()
    handled = []

    def handler(sock, *args, **kwargs):
        handled.append(sock.name)
        if sock is first:
            raise failure

    server, _, _ = make_server(
        robot_profile,
        router,
        listening,
        executor,
        handler=handler,
    )
    stop_when_accept_queue_is_empty(server, listening)

    server.serve_forever()

    assert handled == ["first", "second"]
    assert first.close_calls == second.close_calls == 1
    assert first.sent_data == []
    assert server.active_connection_count == 0


def test_settimeout_failure_closes_releases_and_continues(
    robot_profile, router
):
    failed = FakeClientSocket(
        "failed", settimeout_error=OSError("settimeout failed")
    )
    second = FakeClientSocket("second")
    listening = FakeListeningSocket(
        [(failed, ("peer", 1)), (second, ("peer", 2))]
    )
    executor = ImmediateExecutor()
    handled = []

    def handler(sock, *args, **kwargs):
        handled.append(sock.name)

    server, _, _ = make_server(
        robot_profile, router, listening, executor, handler=handler
    )
    stop_when_accept_queue_is_empty(server, listening)

    server.serve_forever()

    assert handled == ["second"]
    assert failed.close_calls == 1
    assert second.close_calls == 1
    assert server.active_connection_count == 0


def test_client_close_failure_still_releases_capacity(
    robot_profile, router
):
    client = FakeClientSocket(
        "client", close_error=OSError("close failed")
    )
    listening = FakeListeningSocket([(client, ("peer", 1))])
    executor = ImmediateExecutor()
    server, _, _ = make_server(
        robot_profile,
        router,
        listening,
        executor,
        handler=lambda *args: None,
    )
    stop_when_accept_queue_is_empty(server, listening)

    server.serve_forever()

    assert client.close_calls == 1
    assert server.active_connection_count == 0


def test_submit_failure_closes_client_releases_permit_and_fails_server(
    robot_profile, router
):
    client = FakeClientSocket("client")
    listening = FakeListeningSocket([(client, ("peer", 1))])
    executor = FailingSubmitExecutor()
    server, _, _ = make_server(
        robot_profile, router, listening, executor
    )

    with pytest.raises(RuntimeError, match="submit failed"):
        server.serve_forever()

    assert client.close_calls == 1
    assert server.active_connection_count == 0
    assert listening.close_calls == 1
    assert executor.shutdown_calls == [True]


def test_unexpected_accept_error_propagates_without_loop(
    robot_profile, router
):
    failure = OSError("unexpected accept failure")
    listening = FakeListeningSocket([failure])
    executor = ImmediateExecutor()
    server, _, _ = make_server(
        robot_profile, router, listening, executor
    )

    with pytest.raises(OSError) as exc_info:
        server.serve_forever()

    assert exc_info.value is failure
    assert sum(1 for item in listening.events if item[0] == "accept") == 1
    assert listening.close_calls == 1
    assert executor.shutdown_calls == [True]
    assert server.is_stopped is True


def test_shutdown_close_accept_error_is_normal_and_idempotent(
    robot_profile, router
):
    listening = FakeListeningSocket()
    executor = ImmediateExecutor()
    server, _, _ = make_server(
        robot_profile, router, listening, executor
    )
    stop_when_accept_queue_is_empty(server, listening)

    server.serve_forever()
    server.shutdown()
    server.shutdown()

    assert listening.close_calls == 1
    assert executor.shutdown_calls == [True]
    assert server.is_stopped is True


def test_stopped_server_cannot_be_restarted(robot_profile, router):
    listening = FakeListeningSocket()
    executor = ImmediateExecutor()
    server, socket_factory, executor_factory = make_server(
        robot_profile, router, listening, executor
    )
    stop_when_accept_queue_is_empty(server, listening)
    server.serve_forever()

    with pytest.raises(RuntimeError, match="cannot be restarted"):
        server.serve_forever()

    assert len(socket_factory.calls) == 1
    assert len(executor_factory.calls) == 1


def test_shutdown_before_serve_prevents_later_start(robot_profile, router):
    listening = FakeListeningSocket()
    executor = ImmediateExecutor()
    server, socket_factory, executor_factory = make_server(
        robot_profile, router, listening, executor
    )

    server.shutdown()

    assert server.is_stopped is True
    with pytest.raises(RuntimeError, match="cannot be restarted"):
        server.serve_forever()
    assert socket_factory.calls == []
    assert executor_factory.calls == []


def test_worker_can_request_shutdown_without_deadlock(
    robot_profile, router
):
    client = FakeClientSocket("client")
    unaccepted = FakeClientSocket("unaccepted")
    listening = FakeListeningSocket(
        [(client, ("peer", 1)), (unaccepted, ("peer", 2))]
    )
    executor = ImmediateExecutor()
    holder = {}

    def handler(*args, **kwargs):
        holder["server"].shutdown()

    server, _, _ = make_server(
        robot_profile,
        router,
        listening,
        executor,
        handler=handler,
    )
    holder["server"] = server

    server.serve_forever()

    assert server.is_stopped is True
    assert client.close_calls == 1
    assert unaccepted.close_calls == 0
    assert len(executor.submit_calls) == 1
    assert sum(1 for event in listening.events if event[0] == "accept") == 1
    assert server.active_connection_count == 0


def test_external_shutdown_waits_for_active_worker_and_executor(
    robot_profile, router
):
    client = FakeClientSocket("client")
    listening = BlockingListeningSocket((client, ("peer", 1)))
    socket_factory = FakeSocketFactory(listening)
    handler_started = threading.Event()
    release_handler = threading.Event()
    handler_finished = threading.Event()
    shutdown_returned = threading.Event()
    serve_errors = []

    def handler(*args, **kwargs):
        handler_started.set()
        release_handler.wait()
        handler_finished.set()

    server = LegacyV1TcpServer(
        robot_profile,
        router,
        LegacyV1TcpServerConfig(max_workers=1),
        socket_factory=socket_factory,
        connection_handler=handler,
    )

    def run_server():
        try:
            server.serve_forever()
        except BaseException as error:
            serve_errors.append(error)

    serve_thread = threading.Thread(target=run_server)
    serve_thread.start()
    assert server.wait_until_listening(2.0)
    assert handler_started.wait(2.0)
    assert listening.accept_waiting.wait(2.0)

    def stop_server():
        server.shutdown()
        shutdown_returned.set()

    shutdown_thread = threading.Thread(target=stop_server)
    shutdown_thread.start()
    assert listening.closed_event.wait(2.0)
    assert shutdown_returned.is_set() is False
    assert handler_finished.is_set() is False

    release_handler.set()
    shutdown_thread.join(3.0)
    serve_thread.join(3.0)

    assert not shutdown_thread.is_alive()
    assert not serve_thread.is_alive()
    assert shutdown_returned.is_set()
    assert handler_finished.is_set()
    assert serve_errors == []
    assert client.close_calls == 1
    assert listening.close_calls == 1
    assert listening.shutdown_calls == [socket.SHUT_RDWR]
    assert server.active_connection_count == 0
    assert server.is_stopped is True
