"""Connection tests for v2 production commands and v1 fallback."""

import json

from robot_controller.command_target import (
    MouthLedBackendCommandTarget,
    RecordingCommandTarget,
)
from robot_controller.current_router import CurrentCommandRouter
from robot_controller.errors import HardwareBackendUnavailableError
from robot_controller.hardware.mouth_led_backend import (
    MockMouthLedBackend,
    UnavailableMouthLedBackend,
)
from robot_controller.hardware.vsmd.errors import (
    AppManagerAcquireCleanupError,
    AppManagerTimerAddressError,
    AppManagerUnlockError,
    VsmdMouthLedCleanupError,
    VsmdTransportError,
)
from robot_controller.production_connection_handler import (
    handle_production_connection,
)
from robot_controller.profiles import RobotProfile
from robot_controller.protocol.current import MOUTH_LED_PULSE_WIRE_COMMAND
from robot_controller.protocol.frame import encode_frame
from robot_controller.router import CommandRouter


class FakeSocket(object):
    def __init__(self, incoming):
        self.incoming = incoming
        self.sent_data = []
        self.timeout = 12.5

    def recv(self, size):
        value = self.incoming[:size]
        self.incoming = self.incoming[size:]
        return value

    def sendall(self, value):
        self.sent_data.append(value)

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value


def frame_body(frame):
    size = int.from_bytes(frame[:4], "big")
    return json.loads(frame[4:4 + size].decode("utf-8"))


def wire(payload=None, command=MOUTH_LED_PULSE_WIRE_COMMAND):
    if payload is None:
        payload = {
            "request_id": "wire-1",
            "payload": {
                "level": 16,
                "rise_ms": 200,
                "hold_ms": 500,
                "fall_ms": 200,
            },
        }
    return (
        encode_frame(command.encode("utf-8"))
        + encode_frame(json.dumps(payload).encode("utf-8"))
    )


def parts(backend):
    legacy_target = RecordingCommandTarget({"HEAD_Y": 0})
    combined = MouthLedBackendCommandTarget(legacy_target, backend)
    return (
        legacy_target,
        CommandRouter(combined),
        CurrentCommandRouter(combined),
    )


def profile():
    return RobotProfile({"HEAD_Y": (-20, 20)}, {"Mouth": (0, 255)})


def test_complete_v2_frame_calls_backend_once_and_returns_success():
    backend = MockMouthLedBackend()
    legacy_target, legacy_router, current_router = parts(backend)
    sock = FakeSocket(wire())

    result = handle_production_connection(
        sock, profile(), legacy_router, current_router
    )

    assert tuple(result) == (2, "mouth_led_pulse", True)
    assert len(backend.calls) == 1
    assert legacy_target.calls == ()
    assert frame_body(sock.sent_data[0])["status"] == "success"
    assert sock.timeout == 12.5


def test_invalid_payload_returns_validation_error_without_backend_call():
    backend = MockMouthLedBackend()
    _, legacy_router, current_router = parts(backend)
    payload = {
        "request_id": "wire-2",
        "payload": {
            "level": True,
            "rise_ms": 200,
            "hold_ms": 500,
            "fall_ms": 200,
        },
    }
    sock = FakeSocket(wire(payload))

    handle_production_connection(
        sock, profile(), legacy_router, current_router
    )

    response = frame_body(sock.sent_data[0])
    assert response["error"]["code"] == "VALIDATION_ERROR"
    assert backend.calls == ()


def test_unavailable_backend_returns_typed_safe_error():
    _, legacy_router, current_router = parts(
        UnavailableMouthLedBackend()
    )
    sock = FakeSocket(wire())

    handle_production_connection(
        sock, profile(), legacy_router, current_router
    )

    response = frame_body(sock.sent_data[0])
    assert response["error"]["code"] == "MOUTH_LED_BACKEND_UNAVAILABLE"
    assert "unavailable" in response["error"]["message"]


def test_typed_hardware_failure_is_sanitized_without_retry():
    failure = VsmdTransportError("secret endpoint")
    backend = MockMouthLedBackend(failure)
    _, legacy_router, current_router = parts(backend)
    sock = FakeSocket(wire())

    handle_production_connection(
        sock, profile(), legacy_router, current_router
    )

    response = frame_body(sock.sent_data[0])
    assert response["error"]["code"] == "MOUTH_LED_OPERATION_FAILED"
    assert "secret endpoint" not in json.dumps(response)
    assert len(backend.calls) == 1


def test_cleanup_failure_is_sanitized_and_preserves_primary_chain():
    primary = VsmdTransportError("primary secret")
    cleanup = VsmdTransportError("cleanup secret")
    failure = VsmdMouthLedCleanupError(primary, cleanup)
    backend = MockMouthLedBackend(failure)
    _, legacy_router, current_router = parts(backend)
    sock = FakeSocket(wire())

    handle_production_connection(
        sock, profile(), legacy_router, current_router
    )

    response = frame_body(sock.sent_data[0])
    assert response["error"]["code"] == "MOUTH_LED_OPERATION_FAILED"
    assert len(backend.calls) == 1


def test_app_manager_acquire_cleanup_failure_is_sanitized():
    primary = AppManagerTimerAddressError("secret key and address")
    cleanup = AppManagerUnlockError("secret endpoint")
    failure = AppManagerAcquireCleanupError(primary, cleanup)
    backend = MockMouthLedBackend(failure)
    _, legacy_router, current_router = parts(backend)
    sock = FakeSocket(wire())

    handle_production_connection(
        sock, profile(), legacy_router, current_router
    )

    response = frame_body(sock.sent_data[0])
    serialized = json.dumps(response)
    assert response["error"]["code"] == "MOUTH_LED_OPERATION_FAILED"
    assert "secret key" not in serialized
    assert "secret endpoint" not in serialized
    assert failure.acquisition_error is primary
    assert failure.cleanup_error is cleanup
    assert len(backend.calls) == 1


def test_unexpected_backend_failure_returns_internal_error():
    backend = MockMouthLedBackend(RuntimeError("internal secret"))
    _, legacy_router, current_router = parts(backend)
    sock = FakeSocket(wire())

    handle_production_connection(
        sock, profile(), legacy_router, current_router
    )

    response = frame_body(sock.sent_data[0])
    assert response["error"]["code"] == "INTERNAL_ERROR"
    assert "internal secret" not in json.dumps(response)
    assert len(backend.calls) == 1


def test_legacy_v1_fallback_remains_response_free():
    backend = MockMouthLedBackend()
    legacy_target, legacy_router, current_router = parts(backend)
    sock = FakeSocket(encode_frame(b"stop_pose"))

    result = handle_production_connection(
        sock, profile(), legacy_router, current_router
    )

    assert tuple(result) == (1, "stop_pose", False)
    assert legacy_target.commands == ("stop_pose",)
    assert backend.calls == ()
    assert sock.sent_data == []


def test_bare_mouth_led_name_remains_unknown_legacy_command():
    backend = MockMouthLedBackend()
    _, legacy_router, current_router = parts(backend)
    sock = FakeSocket(encode_frame(b"mouth_led_pulse"))

    try:
        handle_production_connection(
            sock, profile(), legacy_router, current_router
        )
    except Exception as error:
        assert type(error).__name__ == "UnknownCommandError"
    else:
        raise AssertionError("legacy command must remain unknown")
    assert backend.calls == ()
