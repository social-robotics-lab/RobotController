"""Shared mouth LED backend contract tests with no live hardware access."""

import threading

import pytest

from robot_controller.errors import HardwareBackendUnavailableError
from robot_controller.hardware.mouth_led_backend import (
    MockMouthLedBackend,
    MouthLedPulseCall,
    UnavailableMouthLedBackend,
)
from robot_controller.hardware.sota.backend import SotaVsmdBackend


class FakeVsmdTransport(object):
    def __init__(self, calls, **options):
        self._calls = calls
        self._calls.append(("vsmd", options))

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False


class FakeAppManagerTransport(object):
    def __init__(self, calls, **options):
        self._calls = calls
        self._calls.append(("app_manager", options))

    def request(self, unused_request):
        raise AssertionError("stub operation must not issue lock requests")


class StubOperation(object):
    def __init__(
        self,
        calls,
        memory,
        led_lock,
        level,
        rise_ms,
        hold_ms,
        fall_ms,
        sleep_function,
        monotonic_function,
    ):
        self._calls = calls
        self._arguments = MouthLedPulseCall(
            level, rise_ms, hold_ms, fall_ms
        )

    def run(self):
        self._calls.append(("operation", self._arguments))
        return self._arguments


def create_sota_backend(calls):
    def operation_factory(*args, **kwargs):
        return StubOperation(calls, *args, **kwargs)

    return SotaVsmdBackend(
        vsmd_transport_factory=lambda **options: FakeVsmdTransport(
            calls, **options
        ),
        app_manager_transport_factory=(
            lambda **options: FakeAppManagerTransport(calls, **options)
        ),
        memory_factory=lambda unused_transport: object(),
        sleep_function=lambda unused_seconds: None,
        monotonic_function=lambda: 0.0,
        operation_factory=operation_factory,
    )


@pytest.mark.parametrize(
    "backend_factory",
    [
        MockMouthLedBackend,
        lambda: create_sota_backend([]),
        UnavailableMouthLedBackend,
    ],
)
@pytest.mark.parametrize(
    "arguments",
    [
        (True, 200, 500, 200),
        (0, 200, 500, 200),
        (17, 200, 500, 200),
        (16, 49, 500, 200),
        (16, 201, 500, 200),
        (16, 200, 99, 200),
        (16, 200, 1001, 200),
        (16, 200, 500, 49),
        (16, 200, 500, 201),
    ],
)
def test_backends_share_strict_argument_validation(
    backend_factory, arguments
):
    backend = backend_factory()
    with pytest.raises((TypeError, ValueError)):
        backend.pulse_mouth_led(*arguments)


def test_mock_records_valid_call_without_sleeping():
    backend = MockMouthLedBackend()
    result = backend.pulse_mouth_led(16, 200, 500, 200)
    assert backend.calls == (MouthLedPulseCall(16, 200, 500, 200),)
    assert result.pulse_completed is True
    assert result.lock_released is True
    assert result.interpolation_output_safe_zero is True
    assert not hasattr(result, "physical_illumination")


def test_mock_can_reproduce_configured_typed_failure():
    failure = HardwareBackendUnavailableError("configured failure")
    backend = MockMouthLedBackend(failure)
    with pytest.raises(HardwareBackendUnavailableError) as caught:
        backend.pulse_mouth_led(16, 200, 500, 200)
    assert caught.value is failure
    assert len(backend.calls) == 1


def test_unavailable_backend_fails_explicitly_after_validation():
    backend = UnavailableMouthLedBackend()
    with pytest.raises(HardwareBackendUnavailableError):
        backend.pulse_mouth_led(16, 200, 500, 200)


def test_sota_backend_injects_transports_and_returns_operation_result():
    calls = []
    backend = create_sota_backend(calls)
    result = backend.pulse_mouth_led(16, 200, 500, 200)
    assert result == MouthLedPulseCall(16, 200, 500, 200)
    assert [entry[0] for entry in calls] == [
        "vsmd",
        "app_manager",
        "operation",
    ]


def test_sota_backend_accepts_only_verified_mouth_led_id():
    assert SotaVsmdBackend(mouth_led_id=14).mouth_led_id == 14
    with pytest.raises(ValueError):
        SotaVsmdBackend(mouth_led_id=13)
    with pytest.raises(ValueError):
        SotaVsmdBackend(mouth_led_id=True)


def test_same_sota_backend_instance_serializes_overlapping_pulses():
    entered = threading.Event()
    release = threading.Event()
    active_lock = threading.Lock()
    active = [0]
    maximum = [0]

    class BlockingOperation(StubOperation):
        def run(self):
            with active_lock:
                active[0] += 1
                maximum[0] = max(maximum[0], active[0])
            entered.set()
            release.wait(1.0)
            try:
                return self._arguments
            finally:
                with active_lock:
                    active[0] -= 1

    calls = []

    def operation_factory(*args, **kwargs):
        return BlockingOperation(calls, *args, **kwargs)

    backend = SotaVsmdBackend(
        vsmd_transport_factory=lambda **options: FakeVsmdTransport(
            calls, **options
        ),
        app_manager_transport_factory=(
            lambda **options: FakeAppManagerTransport(calls, **options)
        ),
        memory_factory=lambda unused_transport: object(),
        operation_factory=operation_factory,
    )
    first = threading.Thread(
        target=backend.pulse_mouth_led,
        args=(16, 200, 500, 200),
    )
    second = threading.Thread(
        target=backend.pulse_mouth_led,
        args=(16, 200, 500, 200),
    )
    first.start()
    assert entered.wait(1.0)
    second.start()
    second.join(0.05)
    assert second.is_alive()
    release.set()
    first.join(1.0)
    second.join(1.0)
    assert not first.is_alive()
    assert not second.is_alive()
    assert maximum[0] == 1
