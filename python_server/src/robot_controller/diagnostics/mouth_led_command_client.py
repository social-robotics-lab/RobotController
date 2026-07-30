"""Explicit-confirmation client for the production mouth LED command."""

import argparse
import json
import socket
import sys
import uuid

from robot_controller.hardware.mouth_led_backend import (
    validate_mouth_led_duration,
    validate_mouth_led_hold,
    validate_mouth_led_level,
)
from robot_controller.protocol.current import MOUTH_LED_PULSE_WIRE_COMMAND
from robot_controller.protocol.frame import read_frame, write_frame


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 22222
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_LENGTH = 1024 * 1024


def _validated_integer(validator, name, value):
    try:
        parsed = int(value, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "{0} must be an integer".format(name)
        )
    try:
        validator(parsed)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError(str(error))
    return parsed


def build_argument_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser(
        description="Send one explicitly confirmed v2 mouth LED command."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--level",
        type=lambda value: _validated_integer(
            validate_mouth_led_level, "level", value
        ),
        default=16,
    )
    parser.add_argument(
        "--rise-ms",
        type=lambda value: _validated_integer(
            validate_mouth_led_duration, "rise-ms", value
        ),
        default=200,
    )
    parser.add_argument(
        "--hold-ms",
        type=lambda value: _validated_integer(
            validate_mouth_led_hold, "hold-ms", value
        ),
        default=500,
    )
    parser.add_argument(
        "--fall-ms",
        type=lambda value: _validated_integer(
            validate_mouth_led_duration, "fall-ms", value
        ),
        default=200,
    )
    parser.add_argument(
        "--request-id",
        default=None,
        help="Optional correlation ID; a random UUID is used by default.",
    )
    parser.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="Actually connect and send the command.",
    )
    return parser


def build_request(arguments):
    # type: (argparse.Namespace) -> bytes
    request_id = arguments.request_id or uuid.uuid4().hex
    value = {
        "request_id": request_id,
        "payload": {
            "level": arguments.level,
            "rise_ms": arguments.rise_ms,
            "hold_ms": arguments.hold_ms,
            "fall_ms": arguments.fall_ms,
        },
    }
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def main(argv=None, output=None):
    # type: (object, object) -> int
    arguments = build_argument_parser().parse_args(argv)
    output = sys.stdout if output is None else output
    payload = build_request(arguments)
    print("command={0}".format(MOUTH_LED_PULSE_WIRE_COMMAND), file=output)
    print("request={0}".format(payload.decode("utf-8")), file=output)
    if not arguments.confirm_live_write:
        print("sent=false", file=output)
        print("reason=confirmation_required", file=output)
        return 2

    connection = socket.create_connection(
        (arguments.host, arguments.port), DEFAULT_TIMEOUT_SECONDS
    )
    try:
        connection.settimeout(DEFAULT_TIMEOUT_SECONDS)
        write_frame(
            connection, MOUTH_LED_PULSE_WIRE_COMMAND.encode("utf-8")
        )
        write_frame(connection, payload)
        response = read_frame(connection, MAX_RESPONSE_LENGTH)
    finally:
        connection.close()
    print("sent=true", file=output)
    print("response={0}".format(response.decode("utf-8")), file=output)
    parsed = json.loads(response.decode("utf-8"))
    return 0 if parsed.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
