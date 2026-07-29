"""Explicit AppManager lock probe behavior with no live sockets."""

import inspect
import struct

import pytest

from robot_controller.hardware.vsmd import app_manager_probe as module
from robot_controller.hardware.vsmd.app_manager_codec import (
    JAVA_SHORT_SERIALIZATION_PREFIX,
    SERIALIZED_NG,
    SERIALIZED_OK,
)
from robot_controller.hardware.vsmd.app_manager_lock import (
    AppManagerLedLock,
)


def serialized_short(value):
    return JAVA_SHORT_SERIALIZATION_PREFIX + struct.pack(">h", value)


class FakeTransport(object):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, request_json):
        self.requests.append(bytes(request_json))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class TransportFactory(object):
    def __init__(self, transport):
        self.transport = transport
        self.keywords = None
        self.call_count = 0

    def __call__(self, **keywords):
        self.call_count += 1
        self.keywords = keywords
        return self.transport


def request_commands(transport):
    result = []
    for request in transport.requests:
        if b"INTERP_LOCK" in request:
            result.append("LOCK")
        elif b"INTERP_CNV_KEY_2_ADDR" in request:
            result.append("CONVERT")
        elif b"INTERP_UNLOCK" in request:
            result.append("UNLOCK")
    return result


def test_probe_runs_one_lock_convert_hold_unlock_sequence(capsys):
    transport = FakeTransport(
        [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
    )
    factory = TransportFactory(transport)
    sleeps = []
    status = module.main(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "16495",
            "--led-id",
            "14",
            "--hold-seconds",
            "0.2",
        ],
        transport_factory=factory,
        sleep_function=sleeps.append,
    )
    assert status == 0
    assert factory.call_count == 1
    assert factory.keywords == {
        "host": "127.0.0.1",
        "port": 16495,
        "timeout": 2.0,
    }
    assert sleeps == [0.2]
    assert request_commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]
    output = capsys.readouterr().out
    assert "endpoint=127.0.0.1:16495" in output
    assert "led_ids=14" in output
    assert "lock_acquired=true" in output
    assert "lock_key=python-led-" in output
    assert "timer_address=502" in output
    assert "timer_address_hex=0x01f6" in output
    assert "lock_released=true" in output
    assert "result=success" in output


def test_cli_host_port_led_hold_and_common_timeout_are_reflected(capsys):
    transport = FakeTransport(
        [SERIALIZED_OK, serialized_short(496), SERIALIZED_OK]
    )
    factory = TransportFactory(transport)
    sleeps = []
    status = module.main(
        [
            "--host",
            "localhost",
            "--port",
            "16495",
            "--led-id",
            "31",
            "--hold-seconds",
            "0",
            "--connect-timeout",
            "1.5",
            "--read-timeout",
            "1.5",
            "--write-timeout",
            "1.5",
        ],
        transport_factory=factory,
        sleep_function=sleeps.append,
    )
    assert status == 0
    assert factory.keywords == {
        "host": "localhost",
        "port": 16495,
        "timeout": 1.5,
    }
    assert sleeps == [0.0]
    assert b'\\"ids\\":[31]' in transport.requests[0]
    assert "timeouts connect=1.5 read=1.5 write=1.5" in (
        capsys.readouterr().out
    )


@pytest.mark.parametrize("led_id", ["-1", "32"])
def test_led_id_outside_verified_range_is_rejected(led_id):
    with pytest.raises(SystemExit):
        module.main(["--led-id", led_id])


@pytest.mark.parametrize("hold_seconds", ["-0.1", "1.1", "nan", "inf"])
def test_hold_seconds_outside_bounded_range_is_rejected(hold_seconds):
    with pytest.raises(SystemExit):
        module.main(["--hold-seconds", hold_seconds])


def test_unequal_timeouts_fail_closed_without_creating_transport(capsys):
    factory = TransportFactory(FakeTransport([]))
    status = module.main(
        [
            "--connect-timeout",
            "1",
            "--read-timeout",
            "2",
            "--write-timeout",
            "2",
        ],
        transport_factory=factory,
        sleep_function=lambda unused_seconds: None,
    )
    assert status == 1
    assert factory.call_count == 0
    error = capsys.readouterr().err
    assert "result=failure" in error
    assert "requires connect, read, and write timeouts to be equal" in error


def test_lock_rejection_is_nonzero_and_does_not_unlock(capsys):
    transport = FakeTransport([SERIALIZED_NG])
    factory = TransportFactory(transport)
    status = module.main(
        [],
        transport_factory=factory,
        sleep_function=lambda unused_seconds: None,
    )
    assert status == 1
    assert request_commands(transport) == ["LOCK"]
    error = capsys.readouterr().err
    assert "result=failure" in error
    assert "AppManagerLockRejectedError" in error


def test_release_failure_is_nonzero_and_never_sends_second_unlock(capsys):
    transport = FakeTransport(
        [SERIALIZED_OK, serialized_short(502), SERIALIZED_NG]
    )
    factory = TransportFactory(transport)
    status = module.main(
        [],
        transport_factory=factory,
        sleep_function=lambda unused_seconds: None,
    )
    assert status == 1
    assert request_commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]
    captured = capsys.readouterr()
    assert "lock_released=false" in captured.out
    assert "result=failure" in captured.err
    assert "AppManagerUnlockError" in captured.err


def test_hold_exception_still_releases_once_and_returns_nonzero(capsys):
    transport = FakeTransport(
        [SERIALIZED_OK, serialized_short(502), SERIALIZED_OK]
    )
    factory = TransportFactory(transport)

    def fail_hold(unused_seconds):
        raise RuntimeError("hold failed")

    status = module.main(
        [],
        transport_factory=factory,
        sleep_function=fail_hold,
    )
    assert status == 1
    assert request_commands(transport) == ["LOCK", "CONVERT", "UNLOCK"]
    captured = capsys.readouterr()
    assert "lock_released=true" in captured.out
    assert "RuntimeError" in captured.err
    assert "hold failed" in captured.err


def test_probe_source_has_no_direct_vsmd_memory_or_port_reference():
    source = inspect.getsource(module)
    forbidden = (
        "VsmdTcpTransport",
        "VsmdMemoryClient",
        "VsmdTypedMemory",
        "encode_write_request",
        "6498",
    )
    assert all(value not in source for value in forbidden)
    assert "AppManagerTcpTransport" in source
    assert "AppManagerLedLock" in source


def test_default_lock_factory_is_the_existing_app_manager_lock():
    signature = inspect.signature(module.main)
    assert signature.parameters["lock_factory"].default is AppManagerLedLock
