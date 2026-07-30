"""Tests for the Fake-only mouth LED fault-recovery smoke diagnostic."""

import io
import inspect

from robot_controller.diagnostics import (
    mouth_led_fault_recovery_smoke as module,
)


def test_smoke_runs_all_fake_checks_without_live_network_or_write():
    output = io.StringIO()
    assert module.main(output=output) == 0
    assert output.getvalue().splitlines() == [
        "live_network=false",
        "live_write=false",
        "same_process_conflict=pass",
        "cross_client_conflict=pass",
        "release_reacquire=pass",
        "idempotent_release=pass",
        "convert_failure_cleanup=pass",
        "interrupt_cleanup=pass",
        "result=success",
    ]


def test_smoke_has_no_live_transport_or_socket_dependency():
    source = inspect.getsource(module)
    assert "AppManagerTcpTransport" not in source
    assert "VsmdTcpTransport" not in source
    assert "socket." not in source
