"""Command-line entry point for the fail-closed Sota capability probe."""

import argparse
import logging
import sys

from robot_controller.errors import HardwareProbeError
from robot_controller.hardware.sota_probe import (
    SotaCapabilityProbe,
    SotaProbeConfig,
    UnverifiedFutabaReadOnlyProtocol,
)
from robot_controller.hardware.transport import PosixSerialTransport


def _positive_integer(text):
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return value


def _positive_float(text):
    value = float(text)
    if value <= 0 or value == float("inf") or value != value:
        raise argparse.ArgumentTypeError(
            "value must be a positive finite number"
        )
    return value


def _servo_ids(text):
    try:
        values = tuple(int(part) for part in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(
            "servo IDs must be comma-separated integers"
        )
    if not values or any(value < 0 or value > 255 for value in values):
        raise argparse.ArgumentTypeError("servo IDs must be byte values")
    if len(set(values)) != len(values):
        raise argparse.ArgumentTypeError("servo IDs must not repeat")
    return values


def create_argument_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute a non-driving Sota capability probe. "
            "Stop Java RobotController and confirm exclusive UART ownership "
            "before any execution."
        )
    )
    parser.add_argument("--device", required=True)
    parser.add_argument("--baud-rate", required=True, type=_positive_integer)
    parser.add_argument("--servo-ids", required=True, type=_servo_ids)
    parser.add_argument(
        "--read-timeout", type=_positive_float, default=1.0
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    parser.add_argument("--show-raw", action="store_true")
    parser.add_argument("--execute-read-only", action="store_true")
    return parser


def main(argv=None, transport_factory=PosixSerialTransport,
         protocol_factory=UnverifiedFutabaReadOnlyProtocol):
    """Run a dry plan by default; never infer a device, baud, or servo ID."""
    args = create_argument_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level))
    config = SotaProbeConfig(
        args.device, args.baud_rate, args.servo_ids, args.read_timeout
    )
    print(
        "Sota read-only probe: device={0} baud_rate={1} servo_ids={2}".format(
            config.device,
            config.baud_rate,
            ",".join(str(value) for value in config.servo_ids),
        )
    )
    print(
        "SAFETY: stop Java RobotController and confirm exclusive UART "
        "ownership before execution."
    )
    if not args.execute_read_only:
        print(
            "DRY-RUN: device was not opened; only verified model reads "
            "would be permitted."
        )
        return 0

    transport = transport_factory(config.device, config.baud_rate)
    probe = SotaCapabilityProbe(transport, protocol_factory())
    try:
        results = probe.run(
            config, execute_read_only=True, show_raw=args.show_raw
        )
    except HardwareProbeError as error:
        print(
            "Probe refused or failed: {0}".format(type(error).__name__),
            file=sys.stderr,
        )
        return 1
    for result in results:
        line = "servo_id={0} responded={1}".format(
            result.servo_id, result.responded
        )
        if result.responded:
            line += " model={0} supported={1}".format(
                result.model_identifier, result.supported
            )
        elif result.error_type is not None:
            line += " error={0}".format(result.error_type)
        if args.show_raw and result.raw_response is not None:
            line += " raw={0}".format(result.raw_response.hex())
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
