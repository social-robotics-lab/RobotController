"""Fake-only tests for the production mouth LED command path."""

import json

import pytest

from robot_controller.command_service import SerializedRobotCommandTarget
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
from robot_controller.models import MouthLedPulse
from robot_controller.protocol.current import (
    MOUTH_LED_PULSE_WIRE_COMMAND,
    decode_request,
)


def request():
    value = {
        "request_id": "fake-1",
        "payload": {
            "level": 16,
            "rise_ms": 200,
            "hold_ms": 500,
            "fall_ms": 200,
        },
    }
    return decode_request(
        MOUTH_LED_PULSE_WIRE_COMMAND,
        json.dumps(value).encode("utf-8"),
    )


def test_router_service_calls_composed_backend_once():
    backend = MockMouthLedBackend()
    target = MouthLedBackendCommandTarget(
        RecordingCommandTarget(), backend
    )
    service = SerializedRobotCommandTarget(target)
    service.start()
    assert service.wait_until_ready(2.0)
    try:
        result = CurrentCommandRouter(service).dispatch(request())
    finally:
        service.shutdown()

    assert len(backend.calls) == 1
    assert tuple(backend.calls[0]) == (16, 200, 500, 200)
    assert result.backend_result.pulse_completed is True


def test_unavailable_backend_preserves_typed_failure_without_retry():
    target = MouthLedBackendCommandTarget(
        RecordingCommandTarget(), UnavailableMouthLedBackend()
    )
    service = SerializedRobotCommandTarget(target)
    service.start()
    assert service.wait_until_ready(2.0)
    try:
        with pytest.raises(Exception) as caught:
            CurrentCommandRouter(service).dispatch(request())
    finally:
        service.shutdown()

    assert isinstance(caught.value.__cause__, HardwareBackendUnavailableError)


def test_backend_target_forwards_values_unchanged():
    backend = MockMouthLedBackend()
    target = MouthLedBackendCommandTarget(
        RecordingCommandTarget(), backend
    )

    target.mouth_led_pulse(MouthLedPulse(1, 50, 100, 50))

    assert tuple(backend.calls[0]) == (1, 50, 100, 50)
