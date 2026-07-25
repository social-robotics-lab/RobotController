"""Unit tests for the Mock Server composition root and CLI."""

import logging
import os
import signal
import subprocess
import sys
import threading

import pytest

from robot_controller.command_service import SerializedRobotCommandTarget
from robot_controller.command_target import RecordingCommandTarget
from robot_controller.mock_server import (
    DEFAULT_MOCK_HOST,
    DEFAULT_MOCK_PROFILE,
    LoggingRecordingCommandTarget,
    MockApplication,
    MockApplicationConfig,
    create_mock_application,
    main,
    parse_arguments,
)
from robot_controller.models import IdleMotionSettings, Motion, Pose
from robot_controller.profiles import create_mock_robot_profile
from robot_controller.protocol.legacy_v1 import LegacyV1Timeouts
from robot_controller.router import CommandRouter
from robot_controller.tcp_server import LegacyV1TcpServer


def test_module_import_has_no_socket_signal_or_thread_side_effects():
    source_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")
    )
    environment = dict(os.environ)
    previous_python_path = environment.get("PYTHONPATH")
    if previous_python_path:
        environment["PYTHONPATH"] = (
            source_root + os.pathsep + previous_python_path
        )
    else:
        environment["PYTHONPATH"] = source_root
    script = "\n".join(
        [
            "import signal",
            "import socket",
            "import threading",
            "before = tuple(threading.enumerate())",
            "def forbidden(*args, **kwargs):",
            "    raise AssertionError('import-time side effect')",
            "socket.socket = forbidden",
            "signal.signal = forbidden",
            "import robot_controller.mock_server",
            "assert tuple(threading.enumerate()) == before",
        ]
    )

    subprocess.check_call(
        [sys.executable, "-c", script],
        env=environment,
    )


def test_mock_profile_has_deterministic_protocol_names_and_mock_ranges():
    profile = create_mock_robot_profile()

    assert profile.allowed_servo_names == frozenset(
        ["BODY_Y", "HEAD_P", "HEAD_Y"]
    )
    assert profile.allowed_led_names == frozenset(["MOUTH"])
    assert profile.servo_range("HEAD_Y").minimum == -180
    assert profile.servo_range("HEAD_Y").maximum == 180
    assert profile.led_range("MOUTH").minimum == 0
    assert profile.led_range("MOUTH").maximum == 255


def test_composition_builds_existing_layers_without_listening():
    config = MockApplicationConfig(port=0)
    before_threads = tuple(threading.enumerate())

    application = create_mock_application(config)

    assert isinstance(application.profile, type(create_mock_robot_profile()))
    assert isinstance(application.target, RecordingCommandTarget)
    assert isinstance(application.service, SerializedRobotCommandTarget)
    assert isinstance(application.router, CommandRouter)
    assert isinstance(application.server, LegacyV1TcpServer)
    assert application.server.bound_address is None
    assert application.server.is_listening is False
    assert application.service.is_ready is False
    assert application.server.config.session_timeouts == LegacyV1Timeouts(
        5.0,
        5.0,
        30.0,
        5.0,
    )
    assert tuple(threading.enumerate()) == before_threads
    assert application.target.read_axes() == {
        "BODY_Y": 0,
        "HEAD_P": 0,
        "HEAD_Y": 0,
    }


def test_composition_constructs_dependencies_in_documented_order(monkeypatch):
    import robot_controller.mock_server as module

    order = []
    class EmptyProfile(object):
        allowed_servo_names = ()

    profile = EmptyProfile()
    target = object()
    service = object()
    router = object()
    server = object()

    def profile_factory():
        order.append("profile")
        return profile

    class TargetFactory(object):
        def __init__(self, axes):
            order.append(("target", axes))

    class RouterFactory(object):
        def __new__(cls, actual_target):
            order.append(("router", actual_target))
            return router

    class ServiceFactory(object):
        def __new__(cls, downstream, config=None):
            order.append(("service", downstream))
            return service

    class ServerFactory(object):
        def __new__(cls, **kwargs):
            order.append(
                (
                    "server",
                    kwargs["robot_profile"],
                    kwargs["router"],
                )
            )
            return server

    monkeypatch.setattr(module, "create_mock_robot_profile", profile_factory)
    monkeypatch.setattr(module, "LoggingRecordingCommandTarget", TargetFactory)
    monkeypatch.setattr(module, "SerializedRobotCommandTarget", ServiceFactory)
    monkeypatch.setattr(module, "CommandRouter", RouterFactory)
    monkeypatch.setattr(module, "LegacyV1TcpServer", ServerFactory)

    application = module.create_mock_application(MockApplicationConfig())

    assert order == [
        "profile",
        ("target", {}),
        ("service", application.target),
        ("router", application.service),
        ("server", profile, router),
    ]
    assert application.server is server


class LifecycleService(object):
    def __init__(self, events, start_error=None, ready=True):
        self.events = events
        self.start_error = start_error
        self.ready = ready
        self.shutdown_calls = 0

    def start(self):
        self.events.append("service.start")
        if self.start_error is not None:
            raise self.start_error

    def wait_until_ready(self, timeout=None):
        self.events.append("service.ready")
        return self.ready

    def shutdown(self):
        self.events.append("service.shutdown")
        self.shutdown_calls += 1


class LifecycleServer(object):
    def __init__(self, events, serve_error=None):
        self.events = events
        self.serve_error = serve_error
        self.shutdown_calls = 0

    def serve_forever(self):
        self.events.append("server.serve")
        if self.serve_error is not None:
            raise self.serve_error

    def shutdown(self):
        self.events.append("server.shutdown")
        self.shutdown_calls += 1


def make_lifecycle_application(service, server):
    return MockApplication(
        MockApplicationConfig(),
        object(),
        object(),
        service,
        object(),
        server,
    )


def test_application_starts_service_and_waits_ready_before_server():
    events = []
    service = LifecycleService(events)
    server = LifecycleServer(events)
    application = make_lifecycle_application(service, server)

    application.run()

    assert events == [
        "service.start",
        "service.ready",
        "server.serve",
        "service.shutdown",
    ]


def test_service_start_failure_prevents_listen_and_stops_service():
    events = []
    service = LifecycleService(
        events,
        start_error=RuntimeError("start failed"),
    )
    server = LifecycleServer(events)
    application = make_lifecycle_application(service, server)

    with pytest.raises(RuntimeError):
        application.run()

    assert "server.serve" not in events
    assert events == ["service.start", "service.shutdown"]


def test_server_failure_stops_service():
    events = []
    service = LifecycleService(events)
    server = LifecycleServer(events, OSError("bind failed"))
    application = make_lifecycle_application(service, server)

    with pytest.raises(OSError):
        application.run()

    assert events == [
        "service.start",
        "service.ready",
        "server.serve",
        "service.shutdown",
    ]


def test_application_shutdown_orders_server_before_service():
    events = []
    service = LifecycleService(events)
    server = LifecycleServer(events)
    application = make_lifecycle_application(service, server)

    application.shutdown()
    application.shutdown()

    assert events == [
        "server.shutdown",
        "service.shutdown",
        "server.shutdown",
        "service.shutdown",
    ]


def test_cli_defaults_are_local_only_and_deterministic():
    arguments = parse_arguments([])

    assert arguments.host == DEFAULT_MOCK_HOST == "127.0.0.1"
    assert arguments.port == 22222
    assert arguments.max_workers == 16
    assert arguments.client_timeout == 5.0
    assert arguments.wav_timeout == 30.0
    assert arguments.log_level == "INFO"
    assert arguments.profile == DEFAULT_MOCK_PROFILE == "mock"


def test_cli_accepts_all_supported_overrides():
    arguments = parse_arguments(
        [
            "--host",
            "localhost",
            "--port",
            "0",
            "--max-workers",
            "2",
            "--client-timeout",
            "1.25",
            "--wav-timeout",
            "45",
            "--log-level",
            "DEBUG",
            "--profile",
            "mock",
        ]
    )

    assert arguments.host == "localhost"
    assert arguments.port == 0
    assert arguments.max_workers == 2
    assert arguments.client_timeout == 1.25
    assert arguments.wav_timeout == 45.0
    assert arguments.log_level == "DEBUG"
    assert arguments.profile == "mock"


def test_mock_config_maps_client_and_wav_timeouts_to_server_stages():
    application = create_mock_application(
        MockApplicationConfig(
            client_timeout_seconds=2.0,
            wav_timeout_seconds=40.0,
        )
    )

    assert application.server.config.client_timeout_seconds == 2.0
    assert application.server.config.session_timeouts == LegacyV1Timeouts(
        2.0,
        2.0,
        40.0,
        2.0,
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--port", "-1"],
        ["--port", "65536"],
        ["--port", "1.5"],
        ["--max-workers", "0"],
        ["--max-workers", "1.5"],
        ["--client-timeout", "0"],
        ["--client-timeout", "-1"],
        ["--client-timeout", "nan"],
        ["--client-timeout", "inf"],
        ["--wav-timeout", "0"],
        ["--wav-timeout", "-1"],
        ["--wav-timeout", "nan"],
        ["--wav-timeout", "inf"],
        ["--wav-timeout", "true"],
        ["--log-level", "TRACE"],
        ["--profile", "sota"],
    ],
)
def test_cli_rejects_invalid_values(arguments):
    with pytest.raises(SystemExit) as exc_info:
        parse_arguments(arguments)

    assert exc_info.value.code != 0


def test_logging_target_records_models_and_logs_only_command_and_sequence(
    caplog,
):
    target = LoggingRecordingCommandTarget({"HEAD_Y": 0})
    pose = Pose(50, {"HEAD_Y": 1}, {})
    motion = Motion([pose])
    settings = IdleMotionSettings(1.0, 1000)
    secret_wav = b"secret-wave-payload"

    with caplog.at_level(logging.INFO, logger="robot_controller.mock_server"):
        target.play_wav(secret_wav)
        target.stop_wav()
        target.play_pose(pose)
        target.stop_pose()
        target.play_motion(motion)
        target.stop_motion()
        target.play_idle_motion(settings)
        target.stop_idle_motion()
        assert target.read_axes() == {"HEAD_Y": 0}

    assert target.commands == (
        "play_wav",
        "stop_wav",
        "play_pose",
        "stop_pose",
        "play_motion",
        "stop_motion",
        "play_idle_motion",
        "stop_idle_motion",
        "read_axes",
    )
    assert target.calls[0].payload is secret_wav
    assert target.calls[4].payload is motion
    assert len(caplog.records) == 9
    assert [record.args[0] for record in caplog.records] == list(
        target.commands
    )
    assert [record.args[1] for record in caplog.records] == list(
        range(1, 10)
    )
    assert "secret-wave-payload" not in caplog.text
    assert "servo_positions" not in caplog.text


class FakeApplication(object):
    """CLI application double with configurable run behavior."""

    def __init__(self, run_error=None):
        self.run_error = run_error
        self.run_calls = 0
        self.shutdown_calls = 0

    def run(self):
        self.run_calls += 1
        if self.run_error is not None:
            raise self.run_error

    def shutdown(self):
        self.shutdown_calls += 1


def test_main_runs_and_shuts_down_application(monkeypatch):
    import robot_controller.mock_server as module

    application = FakeApplication()
    monkeypatch.setattr(
        module, "create_mock_application", lambda config: application
    )

    result = main([])

    assert result == 0
    assert application.run_calls == 1
    assert application.shutdown_calls >= 1


def test_main_does_not_create_shutdown_coordinator_thread(monkeypatch):
    import robot_controller.mock_server as module

    application = FakeApplication()

    def forbidden_thread(*args, **kwargs):
        raise AssertionError("shutdown coordinator thread was created")

    monkeypatch.setattr(
        module, "create_mock_application", lambda config: application
    )
    monkeypatch.setattr(module.threading, "Thread", forbidden_thread)

    assert main([]) == 0
    assert application.shutdown_calls >= 1


def test_main_treats_keyboard_interrupt_as_clean_shutdown(monkeypatch):
    import robot_controller.mock_server as module

    application = FakeApplication(KeyboardInterrupt())
    monkeypatch.setattr(
        module, "create_mock_application", lambda config: application
    )

    result = main([])

    assert result == 0
    assert application.shutdown_calls >= 1


def test_main_treats_signal_requested_startup_stop_as_clean(monkeypatch):
    import robot_controller.mock_server as module

    application = FakeApplication(RuntimeError("stopped before serve"))

    def request_stop_immediately(stop_requested):
        stop_requested.set()
        return {}

    monkeypatch.setattr(
        module, "create_mock_application", lambda config: application
    )
    monkeypatch.setattr(
        module,
        "_install_signal_handlers",
        request_stop_immediately,
    )

    assert main([]) == 0
    assert application.shutdown_calls >= 1


def test_main_reports_server_failure_and_still_shuts_down(
    monkeypatch, caplog
):
    import robot_controller.mock_server as module

    application = FakeApplication(OSError("bind detail must not be logged"))
    monkeypatch.setattr(
        module, "create_mock_application", lambda config: application
    )

    with caplog.at_level(logging.ERROR, logger="robot_controller.mock_server"):
        result = main([])

    assert result == 1
    assert application.shutdown_calls >= 1
    assert "OSError" in caplog.text
    assert "bind detail must not be logged" not in caplog.text


def test_main_reports_composition_failure_without_success(monkeypatch):
    import robot_controller.mock_server as module

    def fail_creation(config):
        raise RuntimeError("creation detail")

    monkeypatch.setattr(module, "create_mock_application", fail_creation)

    assert main([]) == 1


def test_signal_handlers_are_installed_only_by_main_and_restored(monkeypatch):
    import robot_controller.mock_server as module

    application = FakeApplication()
    signal_calls = []
    old_handlers = {}

    def fake_getsignal(signum):
        old_handler = object()
        old_handlers[signum] = old_handler
        return old_handler

    def fake_signal(signum, handler):
        signal_calls.append((signum, handler))

    monkeypatch.setattr(module, "create_mock_application", lambda config: application)
    monkeypatch.setattr(module.signal, "getsignal", fake_getsignal)
    monkeypatch.setattr(module.signal, "signal", fake_signal)

    assert signal_calls == []
    assert main([]) == 0

    installed = [
        item for item in signal_calls if callable(item[1])
    ]
    restored = [
        item for item in signal_calls if item[1] is old_handlers[item[0]]
    ]
    signal_numbers = [signal.SIGINT]
    if hasattr(signal, "SIGTERM"):
        signal_numbers.append(signal.SIGTERM)
    if hasattr(signal, "SIGBREAK"):
        signal_numbers.append(signal.SIGBREAK)
    expected_count = len(set(signal_numbers))
    assert len(installed) == expected_count
    assert len(restored) == expected_count


def test_signal_handler_sets_stop_request_and_interrupts_blocking_run(
    monkeypatch,
):
    import robot_controller.mock_server as module

    installed = {}
    stop_requested = threading.Event()

    monkeypatch.setattr(
        module.signal,
        "getsignal",
        lambda signum: signal.SIG_DFL,
    )
    monkeypatch.setattr(
        module.signal,
        "signal",
        lambda signum, handler: installed.update({signum: handler}),
    )

    previous = module._install_signal_handlers(stop_requested)

    assert signal.SIGINT in installed
    if hasattr(signal, "SIGTERM"):
        assert signal.SIGTERM in installed
    if hasattr(signal, "SIGBREAK"):
        assert signal.SIGBREAK in installed
    assert not stop_requested.is_set()
    with pytest.raises(module._SignalShutdown):
        installed[signal.SIGINT](signal.SIGINT, None)
    assert stop_requested.is_set()
    assert all(handler == signal.SIG_DFL for handler in previous.values())


def test_signal_handler_does_not_call_application_shutdown_or_join(
    monkeypatch,
):
    import robot_controller.mock_server as module

    installed = {}
    stop_requested = threading.Event()

    monkeypatch.setattr(
        module.signal,
        "getsignal",
        lambda signum: signal.SIG_DFL,
    )
    monkeypatch.setattr(
        module.signal,
        "signal",
        lambda signum, handler: installed.update({signum: handler}),
    )

    module._install_signal_handlers(stop_requested)

    with pytest.raises(module._SignalShutdown):
        installed[signal.SIGINT](signal.SIGINT, None)
    assert stop_requested.is_set()
