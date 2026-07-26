"""Tests for the read-only probe transport boundary and fake."""

import errno

import pytest

from robot_controller.errors import (
    PartialResponseError,
    TransportStateError,
    TransportTimeoutError,
    UnsupportedHardwarePlatformError,
)
from robot_controller.hardware import transport as module
from robot_controller.hardware.transport import (
    FakeSotaTransport,
    PosixSerialTransport,
)


def test_partial_reads_are_combined_and_remainder_is_preserved():
    transport = FakeSotaTransport([b"a", b"bc", b"def"])
    transport.open()
    assert transport.read_exact(4, 0.5) == b"abcd"
    assert transport.read_exact(2, 0.5) == b"ef"
    assert transport.read_timeouts == [0.5, 0.5]


def test_eof_reports_bounded_counts():
    transport = FakeSotaTransport([b"a", b""])
    transport.open()
    with pytest.raises(PartialResponseError) as caught:
        transport.read_exact(2, 1.0)
    assert caught.value.expected_bytes == 2
    assert caught.value.received_bytes == 1


def test_empty_input_reports_partial_response():
    transport = FakeSotaTransport()
    transport.open()
    with pytest.raises(PartialResponseError):
        transport.read_exact(1, 1.0)


def test_timeout_keeps_original_cause():
    original = TimeoutError("secret payload must not leak")
    transport = FakeSotaTransport([original])
    transport.open()
    with pytest.raises(TransportTimeoutError) as caught:
        transport.read_exact(1, 1.0)
    assert caught.value.__cause__ is original
    assert "secret payload" not in str(caught.value)


def test_eintr_is_retried():
    interrupted = OSError(errno.EINTR, "interrupted")
    transport = FakeSotaTransport([interrupted, b"x"])
    transport.open()
    assert transport.read_exact(1, 1.0) == b"x"


def test_close_is_idempotent():
    transport = FakeSotaTransport()
    transport.open()
    transport.close()
    transport.close()
    assert transport.open_count == 1
    assert transport.close_count == 1


def test_context_manager_closes_after_error():
    transport = FakeSotaTransport()
    with pytest.raises(RuntimeError):
        with transport:
            raise RuntimeError("failed")
    assert not transport.is_open
    assert transport.close_count == 1


def test_write_before_open_and_after_close_is_rejected():
    transport = FakeSotaTransport()
    with pytest.raises(TransportStateError):
        transport.write(b"x")
    transport.open()
    transport.close()
    with pytest.raises(TransportStateError):
        transport.write(b"x")


def test_record_snapshot_cannot_mutate_internal_state():
    transport = FakeSotaTransport()
    transport.open()
    source = bytearray(b"x")
    transport.write(bytes(source))
    snapshot = transport.writes
    source[0] = ord("y")
    assert snapshot == (b"x",)
    assert transport.writes == (b"x",)


def test_open_error_does_not_mark_transport_open():
    error = RuntimeError("open failed")
    transport = FakeSotaTransport(open_error=error)
    with pytest.raises(RuntimeError):
        transport.open()
    assert not transport.is_open


def test_windows_real_transport_is_import_safe_and_rejected(monkeypatch):
    monkeypatch.setattr(module.os, "name", "nt")
    transport = PosixSerialTransport("explicit-device", 12345)
    with pytest.raises(UnsupportedHardwarePlatformError):
        transport.open()
    transport.close()


def test_posix_transport_also_fails_closed_without_verified_uart(monkeypatch):
    monkeypatch.setattr(module.os, "name", "posix")
    transport = PosixSerialTransport("explicit-device", 12345)
    with pytest.raises(UnsupportedHardwarePlatformError):
        transport.open()
