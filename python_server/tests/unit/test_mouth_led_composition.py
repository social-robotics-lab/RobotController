"""Hardware-free tests for mouth LED configuration and composition."""

import inspect
import io
import math
import socket

import pytest

from robot_controller import connection_handler, mock_server, router
from robot_controller.diagnostics import mouth_led_backend_smoke
from robot_controller.errors import ConfigurationError
from robot_controller.hardware.mouth_led_backend import (
    MockMouthLedBackend,
    UnavailableMouthLedBackend,
)
from robot_controller.hardware.vsmd.errors import VsmdMouthLedStateError
from robot_controller.mouth_led_composition import (
    BACKEND_MOCK,
    BACKEND_SOTA_VSMD,
    BACKEND_UNAVAILABLE,
    MouthLedBackendDiagnostics,
    MouthLedBackendResolution,
    MouthLedBackendSettings,
    load_mouth_led_backend_settings,
    resolve_mouth_led_backend,
)
from robot_controller.process_lock import (
    ProcessLockReleaseError,
    ProcessLockUnavailableError,
)


class FakeDiagnosticProcessLock(object):
    def __init__(self, acquire_error=None, close_error=None):
        self.acquire_error = acquire_error
        self.close_error = close_error
        self.acquire_calls = 0
        self.close_calls = 0

    def acquire(self):
        self.acquire_calls += 1
        if self.acquire_error is not None:
            raise self.acquire_error

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


def test_environment_defaults_to_unavailable_with_safe_endpoint_defaults():
    settings = load_mouth_led_backend_settings({})
    resolution = resolve_mouth_led_backend(settings)

    assert settings.backend_kind == BACKEND_UNAVAILABLE
    assert settings.live_hardware_write_enabled is False
    assert settings.app_manager_host == "127.0.0.1"
    assert settings.app_manager_port == 6495
    assert settings.app_manager_timeout == 2.0
    assert settings.vsmd_host == "127.0.0.1"
    assert settings.vsmd_port == 6498
    assert settings.vsmd_connect_timeout == 1.0
    assert settings.vsmd_read_timeout == 1.0
    assert settings.vsmd_write_timeout == 1.0
    assert settings.vsmd_max_line_length == 4096
    assert settings.mouth_led_id == 14
    assert isinstance(resolution.backend, UnavailableMouthLedBackend)


def test_backend_kind_resolution_and_double_opt_in():
    assert isinstance(
        resolve_mouth_led_backend(
            MouthLedBackendSettings(backend_kind=BACKEND_UNAVAILABLE)
        ).backend,
        UnavailableMouthLedBackend,
    )
    assert isinstance(
        resolve_mouth_led_backend(
            MouthLedBackendSettings(backend_kind=BACKEND_MOCK)
        ).backend,
        MockMouthLedBackend,
    )
    disabled = resolve_mouth_led_backend(
        MouthLedBackendSettings(backend_kind=BACKEND_SOTA_VSMD)
    )
    assert isinstance(disabled.backend, UnavailableMouthLedBackend)
    assert disabled.diagnostics.requested_backend_kind == BACKEND_SOTA_VSMD
    assert disabled.diagnostics.resolved_backend_kind == BACKEND_UNAVAILABLE
    assert disabled.diagnostics.mouth_led_backend_configured is False
    assert disabled.backend.reason == (
        "Sota VSMD backend requested, but live hardware write is disabled."
    )


def test_enabled_sota_passes_all_settings_without_connecting():
    constructed = []

    class SotaBackendSpy(object):
        pass

    def sota_factory(**options):
        constructed.append(options)
        return SotaBackendSpy()

    settings = MouthLedBackendSettings(
        backend_kind=BACKEND_SOTA_VSMD,
        live_hardware_write_enabled=True,
        app_manager_host="app-manager.example",
        app_manager_port=16495,
        app_manager_timeout=1.5,
        vsmd_host="vsmd.example",
        vsmd_port=16498,
        vsmd_connect_timeout=1.1,
        vsmd_read_timeout=1.2,
        vsmd_write_timeout=1.3,
        vsmd_max_line_length=2048,
        mouth_led_id=14,
    )
    resolution = resolve_mouth_led_backend(
        settings, sota_factory=sota_factory
    )

    assert isinstance(resolution.backend, SotaBackendSpy)
    assert resolution.diagnostics.resolved_backend_kind == BACKEND_SOTA_VSMD
    assert resolution.diagnostics.mouth_led_backend_configured is True
    assert constructed == [
        {
            "app_manager_host": "app-manager.example",
            "app_manager_port": 16495,
            "app_manager_timeout": 1.5,
            "vsmd_host": "vsmd.example",
            "vsmd_port": 16498,
            "vsmd_connect_timeout": 1.1,
            "vsmd_read_timeout": 1.2,
            "vsmd_write_timeout": 1.3,
            "vsmd_max_line_length": 2048,
            "mouth_led_id": 14,
        }
    ]


@pytest.mark.parametrize("value", ["1", "yes", "on", "enabled", "", "TRUE"])
def test_live_write_boolean_rejects_ambiguous_values(value):
    with pytest.raises(ConfigurationError):
        load_mouth_led_backend_settings(
            {"ROBOT_HARDWARE_LIVE_WRITE_ENABLED": value}
        )


@pytest.mark.parametrize(
    "environment",
    [
        {"ROBOT_MOUTH_LED_BACKEND": "unknown"},
        {"ROBOT_SOTA_APP_MANAGER_HOST": ""},
        {"ROBOT_SOTA_VSMD_HOST": "   "},
        {"ROBOT_SOTA_APP_MANAGER_PORT": "0"},
        {"ROBOT_SOTA_APP_MANAGER_PORT": "65536"},
        {"ROBOT_SOTA_VSMD_PORT": "1.5"},
        {"ROBOT_SOTA_APP_MANAGER_TIMEOUT": "0"},
        {"ROBOT_SOTA_VSMD_CONNECT_TIMEOUT": "-1"},
        {"ROBOT_SOTA_VSMD_READ_TIMEOUT": "nan"},
        {"ROBOT_SOTA_VSMD_WRITE_TIMEOUT": "inf"},
        {"ROBOT_SOTA_VSMD_MAX_LINE_LENGTH": "0"},
        {"ROBOT_SOTA_MOUTH_LED_ID": "13"},
    ],
)
def test_invalid_environment_values_are_configuration_errors(environment):
    with pytest.raises(ConfigurationError):
        load_mouth_led_backend_settings(environment)


def test_settings_reject_bool_as_integer_and_nonfinite_timeout():
    with pytest.raises(ConfigurationError):
        MouthLedBackendSettings(app_manager_port=True)
    with pytest.raises(ConfigurationError):
        MouthLedBackendSettings(vsmd_max_line_length=True)
    with pytest.raises(ConfigurationError):
        MouthLedBackendSettings(vsmd_read_timeout=math.nan)


def test_application_container_exposes_backend_without_protocol_wiring():
    backend = MockMouthLedBackend()
    diagnostics = MouthLedBackendDiagnostics(
        BACKEND_MOCK, BACKEND_MOCK, False, True, None
    )

    def resolver(settings):
        return MouthLedBackendResolution(backend, diagnostics)

    application = mock_server.create_mock_application(
        mock_server.MockApplicationConfig(),
        mouth_led_backend_resolver=resolver,
    )

    assert application.mouth_led_backend is backend
    assert application.mouth_led_backend_diagnostics is diagnostics
    assert "mouth_led_backend" not in inspect.getsource(router)
    assert "pulse_mouth_led" not in inspect.getsource(router)
    assert "mouth_led_backend" not in inspect.getsource(connection_handler)


def test_sota_composition_and_smoke_dry_run_open_no_socket(monkeypatch):
    calls = []

    def forbidden_connection(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("dry-run opened a socket")

    monkeypatch.setattr(socket, "create_connection", forbidden_connection)
    output = io.StringIO()
    error_output = io.StringIO()
    status = mouth_led_backend_smoke.main(
        [],
        environ={
            "ROBOT_MOUTH_LED_BACKEND": "sota_vsmd",
            "ROBOT_HARDWARE_LIVE_WRITE_ENABLED": "true",
        },
        output=output,
        error_output=error_output,
        process_lock_factory=lambda: pytest.fail(
            "dry-run must not create process lock"
        ),
    )

    assert status == 0
    assert calls == []
    assert error_output.getvalue() == ""
    assert "requested_backend_kind=sota_vsmd" in output.getvalue()
    assert "resolved_backend_kind=sota_vsmd" in output.getvalue()
    assert "live_write=false" in output.getvalue()
    assert "result=dry_run" in output.getvalue()


def test_smoke_confirm_calls_container_backend_once_with_all_arguments():
    backend = MockMouthLedBackend()
    diagnostics = MouthLedBackendDiagnostics(
        BACKEND_MOCK, BACKEND_MOCK, False, True, None
    )

    class Application(object):
        mouth_led_backend = backend
        mouth_led_backend_diagnostics = diagnostics

    output = io.StringIO()
    status = mouth_led_backend_smoke.main(
        [
            "--level", "15",
            "--rise-ms", "150",
            "--hold-ms", "400",
            "--fall-ms", "175",
            "--confirm-live-write",
        ],
        environ={"ROBOT_MOUTH_LED_BACKEND": "mock"},
        application_factory=lambda config: Application(),
        process_lock_factory=lambda: pytest.fail(
            "mock backend must not create process lock"
        ),
        output=output,
        error_output=io.StringIO(),
    )

    assert status == 0
    assert tuple(backend.calls[0]) == (15, 150, 400, 175)
    assert len(backend.calls) == 1
    assert "result=success" in output.getvalue()


def test_unavailable_smoke_confirm_preserves_typed_failure():
    output = io.StringIO()
    error_output = io.StringIO()
    status = mouth_led_backend_smoke.main(
        ["--confirm-live-write"],
        environ={},
        output=output,
        error_output=error_output,
        process_lock_factory=lambda: pytest.fail(
            "unavailable backend must not create process lock"
        ),
    )

    assert status != 0
    assert "resolved_backend_kind=unavailable" in output.getvalue()
    assert "result=failure" in error_output.getvalue()
    assert (
        "error_type=HardwareBackendUnavailableError"
        in error_output.getvalue()
    )


def test_smoke_failure_prints_backend_lock_pointer_diagnostics():
    class PointerDiagnostics(object):
        lock_pointer_poll_attempt = 2
        lock_pointer_initial_value = 0x01F4
        lock_pointer_final_value = 0x01F4
        lock_pointer_wait_duration_ms = 20.0
        lock_pointer_converged = False

    class FailingBackend(object):
        last_pulse_diagnostics = PointerDiagnostics()

        def pulse_mouth_led(self, **unused_arguments):
            raise VsmdMouthLedStateError("pointer timeout")

    diagnostics = MouthLedBackendDiagnostics(
        BACKEND_SOTA_VSMD,
        BACKEND_SOTA_VSMD,
        True,
        True,
        None,
    )

    class Application(object):
        mouth_led_backend = FailingBackend()
        mouth_led_backend_diagnostics = diagnostics

    error_output = io.StringIO()
    status = mouth_led_backend_smoke.main(
        ["--confirm-live-write"],
        environ={
            "ROBOT_MOUTH_LED_BACKEND": "sota_vsmd",
            "ROBOT_HARDWARE_LIVE_WRITE_ENABLED": "true",
        },
        application_factory=lambda config: Application(),
        output=io.StringIO(),
        error_output=error_output,
        process_lock_factory=FakeDiagnosticProcessLock,
    )

    assert status != 0
    assert "lock_pointer_poll_attempt=2" in error_output.getvalue()
    assert "lock_pointer_initial_value=0x01f4" in error_output.getvalue()
    assert "lock_pointer_final_value=0x01f4" in error_output.getvalue()
    assert "lock_pointer_converged=false" in error_output.getvalue()
    assert "error_type=VsmdMouthLedStateError" in error_output.getvalue()


def test_live_sota_smoke_contention_prevents_application_creation():
    process_lock = FakeDiagnosticProcessLock(
        acquire_error=ProcessLockUnavailableError("held")
    )
    application_calls = []
    error_output = io.StringIO()

    status = mouth_led_backend_smoke.main(
        ["--confirm-live-write"],
        environ={
            "ROBOT_MOUTH_LED_BACKEND": "sota_vsmd",
            "ROBOT_HARDWARE_LIVE_WRITE_ENABLED": "true",
        },
        application_factory=lambda config: application_calls.append(config),
        process_lock_factory=lambda: process_lock,
        output=io.StringIO(),
        error_output=error_output,
    )

    assert status == 1
    assert process_lock.acquire_calls == 1
    assert process_lock.close_calls == 0
    assert application_calls == []
    assert "error_type=ProcessLockUnavailableError" in error_output.getvalue()


def test_live_sota_smoke_combines_operation_and_lock_close_errors():
    release_error = ProcessLockReleaseError(OSError("unlock"), None)
    process_lock = FakeDiagnosticProcessLock(close_error=release_error)
    error_output = io.StringIO()

    def fail_application(config):
        raise RuntimeError("application failed")

    status = mouth_led_backend_smoke.main(
        ["--confirm-live-write"],
        environ={
            "ROBOT_MOUTH_LED_BACKEND": "sota_vsmd",
            "ROBOT_HARDWARE_LIVE_WRITE_ENABLED": "true",
        },
        application_factory=fail_application,
        process_lock_factory=lambda: process_lock,
        output=io.StringIO(),
        error_output=error_output,
    )

    assert status == 1
    assert process_lock.close_calls == 1
    assert "error_type=ProcessLockContextCleanupError" in error_output.getvalue()
    assert "operation_error_type=RuntimeError" in error_output.getvalue()
    assert "process_lock_cleanup_error_type=ProcessLockReleaseError" in error_output.getvalue()
