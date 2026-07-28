"""Read-only command-line probe for the verified VSMD memory map."""

import argparse
import collections
import math
import sys
import typing

from robot_controller.hardware.vsmd.constants import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_HOST,
    DEFAULT_MAX_LINE_LENGTH,
    DEFAULT_PORT,
    DEFAULT_READ_TIMEOUT_SECONDS,
    DEFAULT_WRITE_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.errors import VsmdError
from robot_controller.hardware.vsmd.memory import VsmdMemoryClient
from robot_controller.hardware.vsmd.sota_memory_map import (
    AUDIO_DIFF_VALUE_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SERVO_READ_POSITION_BASE,
    SERVO_READ_POSITION_LENGTH,
    SOTA_MOUTH_GLOBAL_LED_ID,
    SOTA_MOUTH_OUTPUT_ADDRESS,
    SOTA_MOUTH_TARGET_ADDRESS,
)
from robot_controller.hardware.vsmd.transport import VsmdTcpTransport
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


_VsmdProbeResultBase = collections.namedtuple(
    "_VsmdProbeResultBase",
    [
        "banner",
        "mouth_selector",
        "audio_diff",
        "mouth_target",
        "mouth_output",
        "servo_read_positions",
    ],
)


class VsmdProbeResult(_VsmdProbeResultBase):
    """Immutable snapshot returned by one read-only probe."""

    __slots__ = ()


class VsmdReadOnlyProbe(object):
    """Read only confirmed addresses; this class exposes no write operation."""

    def run(self, transport):
        # type: (VsmdTcpTransport) -> VsmdProbeResult
        with transport:
            memory = VsmdTypedMemory(VsmdMemoryClient(transport))
            selector = memory.read_u16(MOUTH_LED_SELECTOR_ADDRESS)
            audio_diff = memory.read_s16(AUDIO_DIFF_VALUE_ADDRESS)
            target = memory.read_s16(SOTA_MOUTH_TARGET_ADDRESS)
            output = memory.read_s16(SOTA_MOUTH_OUTPUT_ADDRESS)
            positions = memory.read_s16_array(
                SERVO_READ_POSITION_BASE,
                SERVO_READ_POSITION_LENGTH,
            )
            return VsmdProbeResult(
                transport.server_banner.text,
                selector,
                audio_diff,
                target,
                output,
                tuple(positions),
            )


def _port(text):
    # type: (str) -> int
    try:
        value = int(text, 10)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer")
    if value < 1 or value > 65535:
        raise argparse.ArgumentTypeError(
            "port must be between 1 and 65535"
        )
    return value


def _positive_float(text):
    # type: (str) -> float
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a number")
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(
            "timeout must be a positive finite number"
        )
    return value


def _positive_integer(text):
    # type: (str) -> int
    try:
        value = int(text, 10)
    except ValueError:
        raise argparse.ArgumentTypeError("value must be an integer")
    if value < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def create_argument_parser():
    # type: () -> argparse.ArgumentParser
    """Build a parser containing connectivity and timeout options only."""
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Sota vsmd_edison probe. This command connects and "
            "reads confirmed memory addresses; it never writes."
        )
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=_port, default=DEFAULT_PORT)
    parser.add_argument(
        "--connect-timeout",
        type=_positive_float,
        default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--read-timeout",
        type=_positive_float,
        default=DEFAULT_READ_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--write-timeout",
        type=_positive_float,
        default=DEFAULT_WRITE_TIMEOUT_SECONDS,
        help=(
            "Transport send bound used for read requests; the probe has no "
            "memory-write operation."
        ),
    )
    parser.add_argument(
        "--max-line-length",
        type=_positive_integer,
        default=DEFAULT_MAX_LINE_LENGTH,
    )
    return parser


def main(argv=None, transport_factory=VsmdTcpTransport, probe=None):
    # type: (typing.Optional[typing.Sequence[str]], typing.Any, typing.Optional[VsmdReadOnlyProbe]) -> int
    """Connect to VSMD, perform confirmed reads, and print a bounded snapshot."""
    arguments = create_argument_parser().parse_args(argv)
    if probe is None:
        probe = VsmdReadOnlyProbe()
    transport = transport_factory(
        host=arguments.host,
        port=arguments.port,
        connect_timeout=arguments.connect_timeout,
        read_timeout=arguments.read_timeout,
        write_timeout=arguments.write_timeout,
        max_line_length=arguments.max_line_length,
    )
    print(
        (
            "READ-ONLY VSMD probe: endpoint={0}:{1} "
            "connect_timeout={2} read_timeout={3} write_timeout={4}"
        ).format(
            arguments.host,
            arguments.port,
            arguments.connect_timeout,
            arguments.read_timeout,
            arguments.write_timeout,
        )
    )
    try:
        result = probe.run(transport)
    except (VsmdError, OSError) as error:
        print(
            "VSMD read-only probe failed: {0}: {1}".format(
                type(error).__name__, error
            ),
            file=sys.stderr,
        )
        return 1
    print("server_banner={0}".format(result.banner))
    print(
        "mouth_selector address={0} value={1}".format(
            MOUTH_LED_SELECTOR_ADDRESS, result.mouth_selector
        )
    )
    print(
        "AudioDiff address={0} value={1}".format(
            AUDIO_DIFF_VALUE_ADDRESS, result.audio_diff
        )
    )
    print(
        "InterpLEDTarget[{0}] address={1} value={2}".format(
            SOTA_MOUTH_GLOBAL_LED_ID,
            SOTA_MOUTH_TARGET_ADDRESS,
            result.mouth_target,
        )
    )
    print(
        "InterpLEDOutput[{0}] address={1} value={2}".format(
            SOTA_MOUTH_GLOBAL_LED_ID,
            SOTA_MOUTH_OUTPUT_ADDRESS,
            result.mouth_output,
        )
    )
    print(
        "ServoReadPos base={0} length={1} values={2}".format(
            SERVO_READ_POSITION_BASE,
            SERVO_READ_POSITION_LENGTH,
            ",".join(str(value) for value in result.servo_read_positions),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
