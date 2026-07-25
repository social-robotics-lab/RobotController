"""Bounded synchronous TCP server for one-command legacy v1 connections."""

import collections
import concurrent.futures
import logging
import math
import socket
import threading
import typing

from robot_controller.connection_handler import handle_connection
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


logger = logging.getLogger(__name__)


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 22222
DEFAULT_BACKLOG = 16
DEFAULT_MAX_WORKERS = 16
DEFAULT_CLIENT_TIMEOUT_SECONDS = 5.0


_LegacyV1TcpServerConfigBase = collections.namedtuple(
    "_LegacyV1TcpServerConfigBase",
    [
        "host",
        "port",
        "backlog",
        "max_workers",
        "client_timeout_seconds",
        "session_limits",
        "decoder_limits",
    ],
)


class LegacyV1TcpServerConfig(_LegacyV1TcpServerConfigBase):
    """Immutable validated configuration for LegacyV1TcpServer."""

    __slots__ = ()

    def __new__(
        cls,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        backlog=DEFAULT_BACKLOG,
        max_workers=DEFAULT_MAX_WORKERS,
        client_timeout_seconds=DEFAULT_CLIENT_TIMEOUT_SECONDS,
        session_limits=DEFAULT_LIMITS,
        decoder_limits=DEFAULT_VALIDATION_LIMITS,
    ):
        # type: (str, int, int, int, float, LegacyV1Limits, ValidationLimits) -> LegacyV1TcpServerConfig
        if not isinstance(host, str):
            raise TypeError("host must be a string")
        _validate_integer("port", port, 0, 65535)
        _validate_integer("backlog", backlog, 1)
        _validate_integer("max_workers", max_workers, 1)
        if (
            isinstance(client_timeout_seconds, bool)
            or not isinstance(client_timeout_seconds, (int, float))
        ):
            raise TypeError("client_timeout_seconds must be a number")
        if (
            not math.isfinite(client_timeout_seconds)
            or client_timeout_seconds <= 0
        ):
            raise ValueError(
                "client_timeout_seconds must be finite and greater than zero"
            )
        if not isinstance(session_limits, LegacyV1Limits):
            raise TypeError("session_limits must be LegacyV1Limits")
        if not isinstance(decoder_limits, ValidationLimits):
            raise TypeError("decoder_limits must be ValidationLimits")
        return _LegacyV1TcpServerConfigBase.__new__(
            cls,
            host,
            port,
            backlog,
            max_workers,
            client_timeout_seconds,
            session_limits,
            decoder_limits,
        )


class LegacyV1TcpServer(object):
    """Serve bounded legacy v1 connections in the calling thread.

    Construction does not create sockets, executors, or background threads.
    A stopped instance cannot be restarted.
    """

    def __init__(
        self,
        robot_profile,
        router,
        config=None,
        socket_factory=None,
        executor_factory=None,
        connection_handler=None,
    ):
        # type: (RobotProfile, CommandRouter, typing.Optional[LegacyV1TcpServerConfig], typing.Optional[typing.Callable[..., typing.Any]], typing.Optional[typing.Callable[..., typing.Any]], typing.Optional[typing.Callable[..., typing.Any]]) -> None
        if not isinstance(robot_profile, RobotProfile):
            raise TypeError("robot_profile must be RobotProfile")
        if not isinstance(router, CommandRouter):
            raise TypeError("router must be CommandRouter")
        if config is None:
            config = LegacyV1TcpServerConfig()
        if not isinstance(config, LegacyV1TcpServerConfig):
            raise TypeError("config must be LegacyV1TcpServerConfig")

        self._robot_profile = robot_profile
        self._router = router
        self._config = config
        self._socket_factory = socket_factory or socket.socket
        self._executor_factory = (
            executor_factory or concurrent.futures.ThreadPoolExecutor
        )
        self._connection_handler = connection_handler or handle_connection

        self._capacity = threading.BoundedSemaphore(config.max_workers)
        self._shutdown_event = threading.Event()
        self._listening_event = threading.Event()
        self._stopped_event = threading.Event()
        self._state_lock = threading.Lock()
        self._submission_lock = threading.RLock()

        self._started = False
        self._listening = False
        self._listen_socket = None  # type: typing.Optional[typing.Any]
        self._executor = None  # type: typing.Optional[typing.Any]
        self._bound_address = None  # type: typing.Optional[typing.Tuple[str, int]]
        self._serve_thread_id = None  # type: typing.Optional[int]
        self._worker_thread_ids = set()  # type: typing.Set[int]
        self._active_connection_count = 0

    @property
    def config(self):
        # type: () -> LegacyV1TcpServerConfig
        """Return the immutable server configuration."""
        return self._config

    @property
    def bound_address(self):
        # type: () -> typing.Optional[typing.Tuple[str, int]]
        """Return the actual bound address after successful listen."""
        with self._state_lock:
            return self._bound_address

    @property
    def is_listening(self):
        # type: () -> bool
        """Return whether the listening socket currently accepts clients."""
        with self._state_lock:
            return self._listening

    @property
    def is_stopped(self):
        # type: () -> bool
        """Return whether shutdown or serve termination is complete."""
        return self._stopped_event.is_set()

    @property
    def active_connection_count(self):
        # type: () -> int
        """Return accepted connections holding capacity permits."""
        with self._state_lock:
            return self._active_connection_count

    def wait_until_listening(self, timeout=None):
        # type: (typing.Optional[float]) -> bool
        """Wait until bind and listen have completed successfully."""
        return self._listening_event.wait(timeout)

    def wait_until_stopped(self, timeout=None):
        # type: (typing.Optional[float]) -> bool
        """Wait until the accept loop and all submitted workers finish."""
        return self._stopped_event.wait(timeout)

    def serve_forever(self):
        # type: () -> None
        """Bind, listen, and synchronously run the bounded accept loop."""
        current_thread_id = threading.current_thread().ident
        with self._state_lock:
            if self._started or self._shutdown_event.is_set():
                raise RuntimeError(
                    "LegacyV1TcpServer cannot be restarted"
                )
            self._started = True
            self._serve_thread_id = current_thread_id

        listen_socket = None
        executor = None
        try:
            if self._shutdown_event.is_set():
                return
            listen_socket = self._socket_factory(
                socket.AF_INET, socket.SOCK_STREAM
            )
            with self._state_lock:
                self._listen_socket = listen_socket

            listen_socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
            )
            listen_socket.bind((self._config.host, self._config.port))
            listen_socket.listen(self._config.backlog)
            bound_address = listen_socket.getsockname()

            with self._state_lock:
                if self._shutdown_event.is_set():
                    return
                self._bound_address = bound_address
                self._listening = True
            self._listening_event.set()

            with self._state_lock:
                if self._shutdown_event.is_set():
                    return
                executor = self._executor_factory(
                    max_workers=self._config.max_workers
                )
                self._executor = executor

            self._accept_loop(listen_socket, executor)
        finally:
            with self._state_lock:
                self._listening = False
            self._close_listening_socket()
            try:
                if executor is not None:
                    executor.shutdown(wait=True)
            finally:
                with self._state_lock:
                    self._executor = None
                    self._serve_thread_id = None
                self._stopped_event.set()

    def shutdown(self):
        # type: () -> None
        """Stop accepting and wait for graceful completion when safe.

        Calls from the serve thread or one of this server's workers do not
        wait, preventing self-deadlock. External callers wait until submitted
        work and executor shutdown are complete.
        """
        current_thread_id = threading.current_thread().ident
        with self._submission_lock:
            with self._state_lock:
                self._shutdown_event.set()
                self._listening = False
                listen_socket = self._listen_socket
                self._listen_socket = None
                started = self._started
                called_from_server = (
                    current_thread_id == self._serve_thread_id
                    or current_thread_id in self._worker_thread_ids
                )
                already_stopped = self._stopped_event.is_set()
                if not started:
                    self._stopped_event.set()

        if listen_socket is not None:
            self._close_server_socket(listen_socket)

        if started and not called_from_server and not already_stopped:
            self._stopped_event.wait()

    def _accept_loop(self, listen_socket, executor):
        # type: (typing.Any, typing.Any) -> None
        while not self._shutdown_event.is_set():
            try:
                client_socket, peer_address = listen_socket.accept()
            except OSError:
                if self._shutdown_event.is_set():
                    break
                raise

            if self._shutdown_event.is_set():
                self._close_socket(client_socket, "client socket")
                break

            if not self._acquire_capacity():
                logger.warning(
                    "Rejecting legacy v1 connection from %r: capacity full",
                    peer_address,
                )
                self._close_socket(client_socket, "rejected client socket")
                continue

            try:
                client_socket.settimeout(
                    self._config.client_timeout_seconds
                )
            except Exception as error:
                logger.warning(
                    "Failed to configure legacy v1 client %r: %s",
                    peer_address,
                    type(error).__name__,
                )
                self._close_unsubmitted_client(client_socket)
                continue

            submit_error = None
            with self._submission_lock:
                if self._shutdown_event.is_set():
                    should_submit = False
                else:
                    should_submit = True
                    try:
                        executor.submit(
                            self._run_client,
                            client_socket,
                            peer_address,
                        )
                    except Exception as error:
                        should_submit = False
                        submit_error = error

            if not should_submit:
                self._close_unsubmitted_client(client_socket)
                if submit_error is not None:
                    raise submit_error
                break

    def _run_client(self, client_socket, peer_address):
        # type: (typing.Any, typing.Any) -> None
        thread_id = threading.current_thread().ident
        with self._state_lock:
            self._worker_thread_ids.add(thread_id)
        try:
            self._connection_handler(
                client_socket,
                self._robot_profile,
                self._router,
                session_limits=self._config.session_limits,
                decoder_limits=self._config.decoder_limits,
            )
        except Exception as error:
            logger.warning(
                "Legacy v1 connection from %r failed: %s",
                peer_address,
                type(error).__name__,
            )
        finally:
            self._close_socket(client_socket, "client socket")
            try:
                self._release_capacity()
            finally:
                with self._state_lock:
                    self._worker_thread_ids.discard(thread_id)

    def _acquire_capacity(self):
        # type: () -> bool
        acquired = self._capacity.acquire(False)
        if acquired:
            with self._state_lock:
                self._active_connection_count += 1
        return acquired

    def _release_capacity(self):
        # type: () -> None
        self._capacity.release()
        with self._state_lock:
            self._active_connection_count -= 1

    def _close_unsubmitted_client(self, client_socket):
        # type: (typing.Any) -> None
        self._close_socket(client_socket, "unsubmitted client socket")
        self._release_capacity()

    def _close_listening_socket(self):
        # type: () -> None
        with self._state_lock:
            listen_socket = self._listen_socket
            self._listen_socket = None
        if listen_socket is not None:
            self._close_server_socket(listen_socket)

    @staticmethod
    def _close_server_socket(sock):
        # type: (typing.Any) -> None
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except (AttributeError, OSError):
            pass
        LegacyV1TcpServer._close_socket(sock, "listening socket")

    @staticmethod
    def _close_socket(sock, description):
        # type: (typing.Any, str) -> None
        try:
            sock.close()
        except Exception as error:
            logger.warning(
                "Failed to close %s: %s",
                description,
                type(error).__name__,
            )


def _validate_integer(name, value, minimum, maximum=None):
    # type: (str, typing.Any, int, typing.Optional[int]) -> None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("{0} must be an integer".format(name))
    if value < minimum:
        raise ValueError(
            "{0} must be at least {1}".format(name, minimum)
        )
    if maximum is not None and value > maximum:
        raise ValueError(
            "{0} must not exceed {1}".format(name, maximum)
        )
