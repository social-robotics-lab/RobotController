"""Read-only VSMD probe behavior and CLI surface."""

import struct

import pytest

from robot_controller.hardware.vsmd.codec import ServerBanner
from robot_controller.hardware.vsmd import probe as module
from robot_controller.hardware.vsmd.probe import VsmdReadOnlyProbe


class ProbeTransport(object):
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.server_banner = ServerBanner("#vs-test", b"#vs-test\r\n")
        self.connect_count = 0
        self.close_count = 0

    def __enter__(self):
        self.connect_count += 1
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.close_count += 1
        return False

    def send(self, data):
        self.sent.append(bytes(data))

    def read_line(self):
        return self.responses.pop(0)


def response(address, payload):
    return (
        "#{0:04x} {1} \r\n".format(
            address,
            " ".join("{0:02x}".format(value) for value in payload),
        ).encode("ascii")
    )


def probe_responses():
    positions = tuple(range(-16, 16))
    return [
        response(292, struct.pack("<H", 138)),
        response(138, struct.pack("<h", -5)),
        response(2716, struct.pack("<h", 16)),
        response(3228, struct.pack("<h", 16)),
        response(3712, struct.pack("<32h", *positions)),
    ]


def test_probe_reads_only_confirmed_ranges_and_never_memory_writes():
    transport = ProbeTransport(probe_responses())
    result = VsmdReadOnlyProbe().run(transport)
    assert result.banner == "#vs-test"
    assert result.mouth_selector == 138
    assert result.audio_diff == -5
    assert result.mouth_target == 16
    assert result.mouth_output == 16
    assert result.servo_read_positions == tuple(range(-16, 16))
    assert transport.sent == [
        b"R 0124 2\r\n",
        b"R 008a 2\r\n",
        b"R 0a9c 2\r\n",
        b"R 0c9c 2\r\n",
        b"R 0e80 40\r\n",
    ]
    assert all(not request.startswith(b"w") for request in transport.sent)
    assert transport.connect_count == 1
    assert transport.close_count == 1


class TransportFactory(object):
    def __init__(self, transport):
        self.transport = transport
        self.keywords = None

    def __call__(self, **keywords):
        self.keywords = keywords
        return self.transport


def test_cli_reports_endpoint_timeouts_banner_and_values(capsys):
    transport = ProbeTransport(probe_responses())
    factory = TransportFactory(transport)
    status = module.main(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "6498",
            "--connect-timeout",
            "2",
            "--read-timeout",
            "3",
            "--write-timeout",
            "4",
        ],
        transport_factory=factory,
    )
    assert status == 0
    output = capsys.readouterr().out
    assert "READ-ONLY" in output
    assert "endpoint=127.0.0.1:6498" in output
    assert "server_banner=#vs-test" in output
    assert "mouth_selector address=292 value=138" in output
    assert "AudioDiff address=138 value=-5" in output
    assert "InterpLEDTarget[14] address=2716 value=16" in output
    assert "InterpLEDOutput[14] address=3228 value=16" in output
    assert "ServoReadPos base=3712 length=32" in output
    assert factory.keywords["connect_timeout"] == 2.0


def test_cli_has_no_write_or_execution_switches():
    parser = module.create_argument_parser()
    option_strings = set(
        option
        for action in parser._actions
        for option in action.option_strings
    )
    assert "--write" not in option_strings
    assert "--execute" not in option_strings
    assert "--disable-voice-sync" not in option_strings
    assert "--dry-run" not in option_strings


def test_cli_size_error_includes_bounded_request_diagnostics(capsys):
    transport = ProbeTransport([b"#0124 8a 00 ff \r\n"])
    factory = TransportFactory(transport)
    assert module.main([], transport_factory=factory) == 1
    error_output = capsys.readouterr().err
    assert "VsmdResponseSizeMismatchError" in error_output
    assert "address=0x0124" in error_output
    assert "requested_bytes=2" in error_output
    assert "received_bytes=3" in error_output
    assert "raw_response=b'#0124 8a 00 ff '" in error_output


@pytest.mark.parametrize(
    "arguments",
    [
        ["--port", "0"],
        ["--port", "65536"],
        ["--connect-timeout", "0"],
        ["--read-timeout", "nan"],
        ["--write-timeout", "inf"],
        ["--max-line-length", "0"],
    ],
)
def test_invalid_cli_values_are_rejected(arguments):
    with pytest.raises(SystemExit):
        module.main(arguments)
