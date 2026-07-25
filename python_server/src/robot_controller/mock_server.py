"""Composition root and command-line entry point for the safe Mock Server."""

import argparse
import collections
import logging
import math
import signal
import sys
import threading
import typing

from robot_controller.command_target import RecordingCommandTarget
from robot_controller.profiles import (
    RobotProfile,
    create_mock_robot_profile,
)
from robot_controller.protocol.legacy_v1 import (
    DEFAULT_TIMEOUTS,
    LegacyV1Timeouts,
)
from robot_controller.router import CommandRouter
from robot_controller.tcp_server import (
    DEFAULT_BACKLOG,
    DEFAULT_CLIENT_TIMEOUT_SECONDS,
    DEFAULT_MAX_WORKERS,
    DEFAULT_PORT,
    LegacyV1TcpServer,
    LegacyV1TcpServerConfig,
)


logger = logging.getLogger(__name__)


DEFAULT_MOCK_HOST = "127.0.0.1"
DEFAULT_MOCK_PROFILE = "mock"
SUPPORTED_MOCK_PROFILES = (DEFAULT_MOCK_PROFILE,)
SUPPORTED_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


class _SignalShutdown(BaseException):
    """Interrupt a blocking server call after a console stop request."""


_MockApplicationConfigBase = collections.namedtuple(
    "_MockApplicationConfigBase",
    [
        "host",
        "port",
        "backlog",
        "max_workers",
        "client_timeout_seconds",
        "profile",
        "wav_timeout_seconds",
    ],
)


class MockApplicationConfig(_MockApplicationConfigBase):
    """Immutable validated configuration for the Mock composition root."""

    __slots__ = ()

    def __new__(
        cls,
        host=DEFAULT_MOCK_HOST,
        port=DEFAULT_PORT,
        backlog=DEFAULT_BACKLOG,
        max_workers=DEFAULT_MAX_WORKERS,
        client_timeout_seconds=DEFAULT_CLIENT_TIMEOUT_SECONDS,
        profile=DEFAULT_MOCK_PROFILE,
        wav_timeout_seconds=DEFAULT_TIMEOUTS.wav_payload_timeout,
    ):
        # type: (str, int, int, int, float, str, float) -> MockApplicationConfig
        if profile not in SUPPORTED_MOCK_PROFILES:
            raise ValueError(
                "unsupported Mock profile: {0}".format(profile)
            )
        session_timeouts = LegacyV1Timeouts(
            command_timeout=client_timeout_seconds,
            json_payload_timeout=client_timeout_seconds,
            wav_payload_timeout=wav_timeout_seconds,
            response_timeout=client_timeout_seconds,
        )
        validated_server_config = LegacyV1TcpServerConfig(
            host=host,
            port=port,
            backlog=backlog,
            max_workers=max_workers,
            client_timeout_seconds=client_timeout_seconds,
            session_timeouts=session_timeouts,
        )
        return _MockApplicationConfigBase.__new__(
            cls,
            validated_server_config.host,
            validated_server_config.port,
            validated_server_config.backlog,
            validated_server_config.max_workers,
            validated_server_config.client_timeout_seconds,
            profile,
            session_timeouts.wav_payload_timeout,
        )


class LoggingRecordingCommandTarget(RecordingCommandTarget):
    """Recording target that logs command identity without payload content."""

    def __init__(self, read_axes_result=None, exceptions=None):
        # type: (typing.Optional[typing.Mapping[str, int]], typing.Optional[typing.Mapping[str, BaseException]]) -> None
        RecordingCommandTarget.__init__(
            self,
            read_axes_result=read_axes_result,
            exceptions=exceptions,
        )
        self._command_log_lock = threading.Lock()
        self._command_sequence = 0

    def _record(self, command, payload):
        # type: (str, typing.Any) -> None
        with self._command_log_lock:
            self._command_sequence += 1
            sequence = self._command_sequence
            try:
                RecordingCommandTarget._record(self, command, payload)
            finally:
                logger.info(
                    "Mock command command=%s sequence=%d",
                    command,
                    sequence,
                )


class MockApplication(object):
    """Composed hardware-free Mock Server application."""

    def __init__(self, config, profile, target, router, server):
        # type: (MockApplicationConfig, RobotProfile, LoggingRecordingCommandTarget, CommandRouter, LegacyV1TcpServer) -> None
        self._config = config
        self._profile = profile
        self._target = target
        self._router = router
        self._server = server

    @property
    def config(self):
        # type: () -> MockApplicationConfig
        return self._config

    @property
    def profile(self):
        # type: () -> RobotProfile
        return self._profile

    @property
    def target(self):
        # type: () -> LoggingRecordingCommandTarget
        return self._target

    @property
    def router(self):
        # type: () -> CommandRouter
        return self._router

    @property
    def server(self):
        # type: () -> LegacyV1TcpServer
        return self._server

    def run(self):
        # type: () -> None
        """Run the TCP server in the calling thread."""
        self._server.serve_forever()

    def shutdown(self):
        # type: () -> None
        """Request idempotent graceful TCP server shutdown."""
        self._server.shutdown()


def create_mock_application(config):
    # type: (MockApplicationConfig) -> MockApplication
    """Build Profile, Recording Target, Router, then TCP Server."""
    if not isinstance(config, MockApplicationConfig):
        raise TypeError("config must be MockApplicationConfig")

    profile = create_mock_robot_profile()
    initial_axes = dict(
        (name, 0) for name in sorted(profile.allowed_servo_names)
    )
    target = LoggingRecordingCommandTarget(initial_axes)
    router = CommandRouter(target)

    def log_listening(server):
        # type: (LegacyV1TcpServer) -> None
        bound_host, bound_port = server.bound_address
        logger.info(
            (
                "Mock server listening host=%s port=%d profile=%s "
                "max_workers=%d client_timeout=%s wav_timeout=%s"
            ),
            bound_host,
            bound_port,
            config.profile,
            config.max_workers,
            config.client_timeout_seconds,
            config.wav_timeout_seconds,
        )

    session_timeouts = LegacyV1Timeouts(
        command_timeout=config.client_timeout_seconds,
        json_payload_timeout=config.client_timeout_seconds,
        wav_payload_timeout=config.wav_timeout_seconds,
        response_timeout=config.client_timeout_seconds,
    )
    server_config = LegacyV1TcpServerConfig(
        host=config.host,
        port=config.port,
        backlog=config.backlog,
        max_workers=config.max_workers,
        client_timeout_seconds=config.client_timeout_seconds,
        session_timeouts=session_timeouts,
    )
    server = LegacyV1TcpServer(
        robot_profile=profile,
        router=router,
        config=server_config,
        on_listening=log_listening,
    )
    return MockApplication(config, profile, target, router, server)


def _port_argument(value):
    # type: (str) -> int
    return _bounded_integer_argument("port", value, 0, 65535)


def _positive_integer_argument(value):
    # type: (str) -> int
    return _bounded_integer_argument("value", value, 1, None)


def _bounded_integer_argument(name, value, minimum, maximum):
    # type: (str, str, int, typing.Optional[int]) -> int
    try:
        parsed = int(value, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "{0} must be an integer".format(name)
        )
    if str(parsed) != value and not (
        value.startswith("+") and str(parsed) == value[1:]
    ):
        raise argparse.ArgumentTypeError(
            "{0} must be an integer".format(name)
        )
    if parsed < minimum:
        raise argparse.ArgumentTypeError(
            "{0} must be at least {1}".format(name, minimum)
        )
    if maximum is not None and parsed > maximum:
        raise argparse.ArgumentTypeError(
            "{0} must not exceed {1}".format(name, maximum)
        )
    return parsed


def _positive_float_argument(value):
    # type: (str) -> float
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "client timeout must be a number"
        )
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError(
            "client timeout must be finite and greater than zero"
        )
    return parsed


def _wav_timeout_argument(value):
    # type: (str) -> float
    try:
        return _positive_float_argument(value)
    except argparse.ArgumentTypeError:
        raise argparse.ArgumentTypeError(
            "wav timeout must be finite and greater than zero"
        )


def build_argument_parser():
    # type: () -> argparse.ArgumentParser
    """Build the injectable Python 3.6-compatible CLI parser."""
    parser = argparse.ArgumentParser(
        description="Run the hardware-free legacy v1 Mock Server."
    )
    parser.add_argument("--host", default=DEFAULT_MOCK_HOST)
    parser.add_argument("--port", type=_port_argument, default=DEFAULT_PORT)
    parser.add_argument(
        "--max-workers",
        type=_positive_integer_argument,
        default=DEFAULT_MAX_WORKERS,
    )
    parser.add_argument(
        "--client-timeout",
        type=_positive_float_argument,
        default=DEFAULT_CLIENT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--wav-timeout",
        type=_wav_timeout_argument,
        default=DEFAULT_TIMEOUTS.wav_payload_timeout,
    )
    parser.add_argument(
        "--log-level",
        choices=SUPPORTED_LOG_LEVELS,
        default="INFO",
    )
    parser.add_argument(
        "--profile",
        choices=SUPPORTED_MOCK_PROFILES,
        default=DEFAULT_MOCK_PROFILE,
    )
    return parser


def parse_arguments(argv=None):
    # type: (typing.Optional[typing.Sequence[str]]) -> argparse.Namespace
    """Parse explicit arguments without starting or composing the server."""
    return build_argument_parser().parse_args(argv)


def _install_signal_handlers(stop_requested):
    # type: (threading.Event) -> typing.Dict[int, typing.Any]
    previous_handlers = {}

    def request_stop(signum, frame):
        # type: (int, typing.Any) -> None
        stop_requested.set()
        raise _SignalShutdown()

    signal_numbers = [signal.SIGINT]
    sigterm = getattr(signal, "SIGTERM", None)
    if sigterm is not None:
        signal_numbers.append(sigterm)
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        signal_numbers.append(sigbreak)

    for signal_number in signal_numbers:
        if signal_number in previous_handlers:
            continue
        previous_handlers[signal_number] = signal.getsignal(signal_number)
        signal.signal(signal_number, request_stop)
    return previous_handlers


def _restore_signal_handlers(previous_handlers):
    # type: (typing.Mapping[int, typing.Any]) -> None
    for signal_number, handler in previous_handlers.items():
        signal.signal(signal_number, handler)


def main(argv=None):
    # type: (typing.Optional[typing.Sequence[str]]) -> int
    """Run the Mock CLI and return a process exit status."""
    arguments = parse_arguments(argv)
    logging.basicConfig(
        level=getattr(logging, arguments.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    application = None
    stop_requested = threading.Event()
    previous_handlers = {}
    try:
        config = MockApplicationConfig(
            host=arguments.host,
            port=arguments.port,
            max_workers=arguments.max_workers,
            client_timeout_seconds=arguments.client_timeout,
            profile=arguments.profile,
            wav_timeout_seconds=arguments.wav_timeout,
        )
        application = create_mock_application(config)
        previous_handlers = _install_signal_handlers(stop_requested)
        application.run()
        return 0
    except (KeyboardInterrupt, _SignalShutdown):
        return 0
    except Exception as error:
        if stop_requested.is_set():
            return 0
        logger.error(
            "Mock server failed error_type=%s",
            type(error).__name__,
        )
        return 1
    finally:
        stop_requested.set()
        if application is not None:
            application.shutdown()
        if previous_handlers:
            _restore_signal_handlers(previous_handlers)


if __name__ == "__main__":
    sys.exit(main())
