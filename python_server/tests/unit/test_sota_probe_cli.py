"""Tests for the manually invoked Sota probe CLI."""

import pytest

from robot_controller.hardware.transport import FakeSotaTransport
from tools import sota_probe


class TransportFactory(object):
    def __init__(self):
        self.calls = []

    def __call__(self, device, baud_rate):
        self.calls.append((device, baud_rate))
        return FakeSotaTransport()


def required_args():
    return [
        "--device",
        "explicit-device",
        "--baud-rate",
        "12345",
        "--servo-ids",
        "1,8",
    ]


def test_default_is_dry_run_and_does_not_create_transport(capsys):
    factory = TransportFactory()
    assert sota_probe.main(required_args(), transport_factory=factory) == 0
    assert factory.calls == []
    output = capsys.readouterr().out
    assert "DRY-RUN" in output
    assert "1,8" in output


def test_execute_is_fail_closed_before_transport_open(capsys):
    factory = TransportFactory()
    args = required_args() + ["--execute-read-only"]
    assert sota_probe.main(args, transport_factory=factory) == 1
    assert factory.calls == [("explicit-device", 12345)]
    assert "UnverifiedHardwareSpecificationError" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra",
    [
        ["--baud-rate", "0"],
        ["--baud-rate", "-1"],
        ["--servo-ids", ""],
        ["--servo-ids", "1,1"],
        ["--servo-ids", "-1"],
        ["--servo-ids", "256"],
        ["--read-timeout", "0"],
        ["--read-timeout", "-1"],
        ["--read-timeout", "nan"],
        ["--read-timeout", "inf"],
        ["--log-level", "TRACE"],
    ],
)
def test_invalid_cli_values_are_rejected(extra):
    args = required_args()
    option = extra[0]
    if option in args:
        index = args.index(option)
        args[index:index + 2] = extra
    else:
        args.extend(extra)
    with pytest.raises(SystemExit) as caught:
        sota_probe.main(args)
    assert caught.value.code != 0


@pytest.mark.parametrize(
    "missing_option",
    ["--device", "--baud-rate", "--servo-ids"],
)
def test_explicit_target_options_are_required(missing_option):
    args = required_args()
    index = args.index(missing_option)
    del args[index:index + 2]
    with pytest.raises(SystemExit):
        sota_probe.main(args)


def test_import_has_no_device_side_effect():
    assert hasattr(sota_probe, "main")
