"""Fake-only tests for the synchronous AppManager competition probe."""

import io
import json
import struct

import pytest

from robot_controller.hardware.vsmd import (
    app_manager_lock_competition_probe as module,
)
from robot_controller.hardware.vsmd.app_manager_codec import (
    INTERP_CONVERT_COMMAND,
    INTERP_LOCK_COMMAND,
    INTERP_UNLOCK_COMMAND,
    JAVA_SHORT_SERIALIZATION_PREFIX,
    SERIALIZED_NG,
    SERIALIZED_NULL,
    SERIALIZED_OK,
)
from robot_controller.hardware.vsmd.app_manager_lock import AppManagerLedLock


def _serialized_short(value):
    return JAVA_SHORT_SERIALIZATION_PREFIX + struct.pack(">h", value)


def _request_parts(request):
    outer = json.loads(request.decode("ascii"))
    return outer["cmd"], json.loads(outer["subjson"])


class FakeAppManagerArbiter(object):
    """Shared stack state for three independent Fake transports."""

    def __init__(self, results=None):
        self.results = {} if results is None else dict(results)
        self.stacks = {}
        self.timer_by_key = {}
        self.next_timer = 502
        self.events = []

    def exchange(self, client_name, request):
        command, payload = _request_parts(request)
        key = payload["key"]
        led_ids = tuple(payload.get("ids", ()))
        self.events.append((client_name, command, key, led_ids))
        configured = self.results.get((client_name, command))
        if isinstance(configured, BaseException):
            raise configured
        if configured is not None:
            if command == INTERP_LOCK_COMMAND and configured == SERIALIZED_OK:
                self._push(key, led_ids)
            elif (
                command == INTERP_UNLOCK_COMMAND
                and configured == SERIALIZED_OK
            ):
                self._remove(key, led_ids)
            return configured

        if command == INTERP_LOCK_COMMAND:
            if any(self.stacks.get(led_id) for led_id in led_ids):
                return SERIALIZED_NG
            self._push(key, led_ids)
            return SERIALIZED_OK
        if command == INTERP_CONVERT_COMMAND:
            timer_address = self.timer_by_key.get(key)
            if timer_address is None:
                return SERIALIZED_NULL
            return _serialized_short(timer_address)
        if command == INTERP_UNLOCK_COMMAND:
            if not self._owns(key, led_ids):
                return SERIALIZED_NG
            self._remove(key, led_ids)
            return SERIALIZED_OK
        raise AssertionError("unexpected command")

    def _push(self, key, led_ids):
        self.timer_by_key[key] = self.next_timer
        self.next_timer += 2
        for led_id in led_ids:
            self.stacks.setdefault(led_id, []).append(key)

    def _owns(self, key, led_ids):
        return all(
            self.stacks.get(led_id)
            and key in self.stacks[led_id]
            for led_id in led_ids
        )

    def _remove(self, key, led_ids):
        for led_id in led_ids:
            stack = self.stacks.get(led_id, [])
            if key in stack:
                stack.remove(key)
        self.timer_by_key.pop(key, None)


class FakeTransport(object):
    def __init__(self, client_name, arbiter):
        self.client_name = client_name
        self.arbiter = arbiter
        self.requests = []

    def request(self, request):
        request = bytes(request)
        self.requests.append(request)
        return self.arbiter.exchange(self.client_name, request)


class FakeTransportFactory(object):
    def __init__(self, arbiter):
        self.arbiter = arbiter
        self.call_count = 0
        self.calls = []
        self.transports = {}

    def __call__(self, **keywords):
        client_name = ("a", "b", "c")[self.call_count]
        self.call_count += 1
        self.calls.append(dict(keywords))
        transport = FakeTransport(client_name, self.arbiter)
        self.transports[client_name] = transport
        return transport


def _commands(factory, client_name):
    transport = factory.transports.get(client_name)
    if transport is None:
        return []
    return [
        _request_parts(request)[0] for request in transport.requests
    ]


def _run(factory, arguments=None):
    output = io.StringIO()
    error_output = io.StringIO()
    argv = ["--confirm-live-lock"]
    if arguments is not None:
        argv.extend(arguments)
    status = module.main(
        argv,
        transport_factory=factory,
        lock_factory=AppManagerLedLock,
        output=output,
        error_output=error_output,
    )
    return status, output.getvalue(), error_output.getvalue()


def test_confirmation_absent_creates_no_transport():
    factory = FakeTransportFactory(FakeAppManagerArbiter())
    output = io.StringIO()
    error_output = io.StringIO()

    status = module.main(
        [],
        transport_factory=factory,
        output=output,
        error_output=error_output,
    )

    assert status == 0
    assert factory.call_count == 0
    assert output.getvalue().splitlines() == [
        "live_network=false",
        "live_lock=false",
        "result=confirmation_required",
    ]
    assert error_output.getvalue() == ""


def test_successful_competition_has_exact_command_counts_and_keys():
    arbiter = FakeAppManagerArbiter()
    factory = FakeTransportFactory(arbiter)

    status, output, error_output = _run(factory)

    assert status == 0
    assert error_output == ""
    assert factory.call_count == 3
    assert factory.calls == [
        {"host": "127.0.0.1", "port": 6495, "timeout": 2.0},
        {"host": "127.0.0.1", "port": 6495, "timeout": 2.0},
        {"host": "127.0.0.1", "port": 6495, "timeout": 2.0},
    ]
    assert _commands(factory, "a") == [
        INTERP_LOCK_COMMAND,
        INTERP_CONVERT_COMMAND,
        INTERP_UNLOCK_COMMAND,
    ]
    assert _commands(factory, "b") == [INTERP_LOCK_COMMAND]
    assert _commands(factory, "c") == [
        INTERP_LOCK_COMMAND,
        INTERP_CONVERT_COMMAND,
        INTERP_UNLOCK_COMMAND,
    ]
    assert [event[2] for event in arbiter.events] == [
        "phase7-lock-a",
        "phase7-lock-a",
        "phase7-lock-b",
        "phase7-lock-a",
        "phase7-lock-c",
        "phase7-lock-c",
        "phase7-lock-c",
    ]
    assert all(
        not event[3] or event[3] == (14,) for event in arbiter.events
    )
    for expected in (
        "SotaAppManager LED lock competition probe",
        "live_network=true",
        "live_lock=true",
        "led_id=14",
        "client_a_key=phase7-lock-a",
        "client_a_lock_acquired=true",
        "client_b_key=phase7-lock-b",
        "client_b_lock_rejected=true",
        "client_b_error_type=AppManagerLockRejectedError",
        "client_b_convert_sent=false",
        "client_b_unlock_sent=false",
        "client_a_lock_released=true",
        "client_c_key=phase7-lock-c",
        "client_c_lock_acquired=true",
        "client_c_lock_released=true",
        "vsmd_transport_created=false",
        "vsmd_read_write=false",
        "automatic_retry=false",
        "result=success",
    ):
        assert expected in output


def test_cli_values_and_explicit_key_prefix_are_forwarded():
    arbiter = FakeAppManagerArbiter()
    factory = FakeTransportFactory(arbiter)

    status, output, unused_error = _run(
        factory,
        [
            "--host",
            "localhost",
            "--port",
            "16495",
            "--led-id",
            "31",
            "--timeout",
            "1.5",
            "--key-prefix",
            "operator-test",
        ],
    )

    assert status == 0
    assert all(
        call == {"host": "localhost", "port": 16495, "timeout": 1.5}
        for call in factory.calls
    )
    assert "led_id=31" in output
    assert "client_a_key=operator-test-a" in output
    assert "client_b_key=operator-test-b" in output
    assert "client_c_key=operator-test-c" in output
    assert all(
        not event[3] or event[3] == (31,) for event in arbiter.events
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--host", ""],
        ["--port", "0"],
        ["--port", "65536"],
        ["--led-id", "-1"],
        ["--led-id", "32"],
        ["--timeout", "0"],
        ["--timeout", "nan"],
        ["--timeout", "inf"],
        ["--key-prefix", ""],
        ["--key-prefix", "has space"],
        ["--key-prefix", "\N{SNOWMAN}"],
    ],
)
def test_invalid_cli_values_fail_before_transport_creation(arguments):
    factory = FakeTransportFactory(FakeAppManagerArbiter())
    with pytest.raises(SystemExit):
        module.main(
            arguments + ["--confirm-live-lock"],
            transport_factory=factory,
        )
    assert factory.call_count == 0


@pytest.mark.parametrize(
    "results,expected_commands",
    [
        (
            {("a", INTERP_LOCK_COMMAND): SERIALIZED_NG},
            {"a": [INTERP_LOCK_COMMAND], "b": [], "c": []},
        ),
        (
            {("a", INTERP_CONVERT_COMMAND): SERIALIZED_NULL},
            {
                "a": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
                "b": [],
                "c": [],
            },
        ),
        (
            {("b", INTERP_LOCK_COMMAND): SERIALIZED_OK},
            {
                "a": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
                "b": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
                "c": [],
            },
        ),
        (
            {("a", INTERP_UNLOCK_COMMAND): SERIALIZED_NG},
            {
                "a": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
                "b": [INTERP_LOCK_COMMAND],
                "c": [],
            },
        ),
        (
            {("c", INTERP_LOCK_COMMAND): SERIALIZED_NG},
            {
                "a": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
                "b": [INTERP_LOCK_COMMAND],
                "c": [INTERP_LOCK_COMMAND],
            },
        ),
        (
            {("c", INTERP_CONVERT_COMMAND): SERIALIZED_NULL},
            {
                "a": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
                "b": [INTERP_LOCK_COMMAND],
                "c": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
            },
        ),
        (
            {("c", INTERP_UNLOCK_COMMAND): SERIALIZED_NG},
            {
                "a": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
                "b": [INTERP_LOCK_COMMAND],
                "c": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
            },
        ),
        (
            {
                ("b", INTERP_LOCK_COMMAND):
                KeyboardInterrupt("fake interrupt")
            },
            {
                "a": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
                "b": [INTERP_LOCK_COMMAND],
                "c": [],
            },
        ),
        (
            {
                ("b", INTERP_LOCK_COMMAND):
                SystemExit("fake system exit")
            },
            {
                "a": [
                    INTERP_LOCK_COMMAND,
                    INTERP_CONVERT_COMMAND,
                    INTERP_UNLOCK_COMMAND,
                ],
                "b": [INTERP_LOCK_COMMAND],
                "c": [],
            },
        ),
    ],
)
def test_failures_release_only_owned_leases_once(
    results, expected_commands
):
    factory = FakeTransportFactory(FakeAppManagerArbiter(results))

    status, output, error_output = _run(factory)

    assert status == 1
    assert "result=success" not in output
    assert "result=failure" in error_output
    for client_name, commands in expected_commands.items():
        assert _commands(factory, client_name) == commands
        assert commands.count(INTERP_UNLOCK_COMMAND) <= 1


def test_primary_and_cleanup_errors_are_both_reported():
    results = {
        ("b", INTERP_LOCK_COMMAND): RuntimeError("primary failure"),
        ("a", INTERP_UNLOCK_COMMAND): SERIALIZED_NG,
    }
    factory = FakeTransportFactory(FakeAppManagerArbiter(results))

    status, unused_output, error_output = _run(factory)

    assert status == 1
    assert "error_type=AppManagerCompetitionCleanupError" in error_output
    assert "primary_error_type=RuntimeError" in error_output
    assert "primary_error=primary failure" in error_output
    assert "cleanup_error_types=AppManagerUnlockError" in error_output
    assert _commands(factory, "a").count(INTERP_UNLOCK_COMMAND) == 1


def test_source_has_no_vsmd_transport_memory_or_retry_dependency():
    source = module.__loader__.get_source(module.__name__)
    forbidden = (
        "VsmdTcpTransport",
        "VsmdMemoryClient",
        "VsmdTypedMemory",
        "SotaMouthLed",
        "6498",
        "time.sleep",
    )
    assert all(value not in source for value in forbidden)
    assert "AppManagerTcpTransport" in source
    assert "AppManagerLedLock" in source
