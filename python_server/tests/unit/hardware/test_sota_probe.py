"""Tests for fail-closed read-only capability-probe orchestration."""

import pytest

from robot_controller.errors import (
    InvalidFutabaPacketError,
    UnverifiedHardwareSpecificationError,
    UnsafeProbeOperationError,
)
from robot_controller.hardware.sota_probe import (
    ProbeResult,
    ReadOnlyProbeProtocol,
    ReadOnlyRequest,
    SotaCapabilityProbe,
    SotaProbeConfig,
    UnverifiedFutabaReadOnlyProtocol,
)
from robot_controller.hardware.transport import FakeSotaTransport


class SampleReadOnlyProtocol(ReadOnlyProbeProtocol):
    """Test-only protocol; none of these bytes are hardware test vectors."""

    def __init__(self, supported_models=(42,), failures=None):
        self.supported_models = tuple(supported_models)
        self.failures = dict(failures or {})
        self.queried_ids = []

    def ensure_verified(self):
        return None

    def build_model_query(self, servo_id):
        self.queried_ids.append(servo_id)
        return ReadOnlyRequest(
            "read_model", bytes(bytearray([0x70, servo_id])), 2
        )

    def decode_model_response(self, response, expected_servo_id):
        if expected_servo_id in self.failures:
            raise self.failures[expected_servo_id]
        if response[0] != expected_servo_id:
            raise InvalidFutabaPacketError("unexpected test ID")
        return response[1]

    def is_supported_model(self, model_identifier):
        return model_identifier in self.supported_models


def config(ids=(1, 2), timeout=0.25):
    return SotaProbeConfig("explicit-device", 12345, ids, timeout)


def test_config_snapshots_ids_and_has_explicit_values():
    ids = [1, 2]
    result = SotaProbeConfig("device", 115200, ids, 0.5)
    ids.append(3)
    assert result.servo_ids == (1, 2)


@pytest.mark.parametrize("device", ["", "  ", None, 1])
def test_invalid_device_is_rejected(device):
    with pytest.raises((TypeError, ValueError)):
        SotaProbeConfig(device, 1, (1,), 1.0)


@pytest.mark.parametrize("baud", [0, -1, True, False, 1.0, "9600"])
def test_invalid_baud_is_rejected(baud):
    with pytest.raises(ValueError):
        SotaProbeConfig("device", baud, (1,), 1.0)


@pytest.mark.parametrize(
    "ids", [(), (True,), (1.0,), ("1",), (-1,), (256,), (1, 1)]
)
def test_invalid_or_duplicate_ids_are_rejected(ids):
    with pytest.raises(ValueError):
        SotaProbeConfig("device", 1, ids, 1.0)


@pytest.mark.parametrize(
    "timeout", [0, -1, True, False, float("nan"), float("inf"), "1"]
)
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(ValueError):
        SotaProbeConfig("device", 1, (1,), timeout)


def test_dry_run_never_opens_or_writes():
    transport = FakeSotaTransport()
    protocol = SampleReadOnlyProtocol()
    results = SotaCapabilityProbe(transport, protocol).run(config())
    assert [result.servo_id for result in results] == [1, 2]
    assert transport.open_count == 0
    assert transport.writes == ()
    assert protocol.queried_ids == []


def test_unverified_protocol_rejects_before_device_open():
    transport = FakeSotaTransport()
    probe = SotaCapabilityProbe(
        transport, UnverifiedFutabaReadOnlyProtocol()
    )
    with pytest.raises(UnverifiedHardwareSpecificationError):
        probe.run(config(), execute_read_only=True)
    assert transport.open_count == 0


def test_queries_only_explicit_ids_in_order():
    transport = FakeSotaTransport([b"\x05\x2a", b"\x09\x2b"])
    protocol = SampleReadOnlyProtocol()
    results = SotaCapabilityProbe(transport, protocol).run(
        config((5, 9)), execute_read_only=True
    )
    assert protocol.queried_ids == [5, 9]
    assert transport.writes == (b"\x70\x05", b"\x70\x09")
    assert [result.model_identifier for result in results] == [42, 43]
    assert [result.supported for result in results] == [True, False]
    assert transport.close_count == 1


def test_one_timeout_does_not_lose_later_servo_result():
    transport = FakeSotaTransport(
        [TimeoutError("first"), b"\x02\x2a"]
    )
    protocol = SampleReadOnlyProtocol()
    results = SotaCapabilityProbe(transport, protocol).run(
        config(), execute_read_only=True
    )
    assert results[0].error_type == "TransportTimeoutError"
    assert results[1].responded
    assert protocol.queried_ids == [1, 2]


def test_invalid_response_does_not_stop_later_query():
    transport = FakeSotaTransport([b"\x09\x2a", b"\x02\x2a"])
    protocol = SampleReadOnlyProtocol()
    results = SotaCapabilityProbe(transport, protocol).run(
        config(), execute_read_only=True
    )
    assert results[0].error_type == "InvalidFutabaPacketError"
    assert results[1].responded


def test_raw_response_is_hidden_unless_requested():
    hidden_transport = FakeSotaTransport([b"\x01\x2a"])
    hidden = SotaCapabilityProbe(
        hidden_transport, SampleReadOnlyProtocol()
    ).run(config((1,)), execute_read_only=True)
    shown_transport = FakeSotaTransport([b"\x01\x2a"])
    shown = SotaCapabilityProbe(
        shown_transport, SampleReadOnlyProtocol()
    ).run(config((1,)), execute_read_only=True, show_raw=True)
    assert hidden[0].raw_response is None
    assert shown[0].raw_response == b"\x01\x2a"


def test_only_read_model_operation_can_be_constructed():
    with pytest.raises(UnsafeProbeOperationError):
        ReadOnlyRequest("write_goal_position", b"x", 1)
    with pytest.raises(UnsafeProbeOperationError):
        ReadOnlyRequest("write_goal_time", b"x", 1)
    with pytest.raises(UnsafeProbeOperationError):
        ReadOnlyRequest("write_torque", b"x", 1)
    with pytest.raises(UnsafeProbeOperationError):
        ReadOnlyRequest("broadcast_write", b"x", 1)


def test_results_are_immutable():
    result = ProbeResult(1, True, 42, True, None, None)
    with pytest.raises(AttributeError):
        result.servo_id = 2
