"""Tests for the safe production-command diagnostic client."""

import io
import json

from robot_controller.diagnostics import mouth_led_command_client as module


def test_without_confirmation_builds_request_but_never_connects(monkeypatch):
    def forbidden_connection(*args, **kwargs):
        raise AssertionError("dry-run must not connect")

    monkeypatch.setattr(
        module.socket, "create_connection", forbidden_connection
    )
    output = io.StringIO()

    exit_code = module.main(
        [
            "--request-id",
            "dry-run-1",
            "--level",
            "16",
            "--rise-ms",
            "200",
            "--hold-ms",
            "500",
            "--fall-ms",
            "200",
        ],
        output=output,
    )

    lines = dict(
        line.split("=", 1)
        for line in output.getvalue().strip().splitlines()
    )
    assert exit_code == 2
    assert lines["command"] == "v2/mouth_led_pulse"
    assert json.loads(lines["request"])["request_id"] == "dry-run-1"
    assert lines["sent"] == "false"
