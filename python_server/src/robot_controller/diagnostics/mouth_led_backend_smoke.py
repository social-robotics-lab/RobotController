"""Smoke-test the normal mouth LED configuration and composition path."""

import argparse
import sys
import typing

from robot_controller.hardware.mouth_led_backend import (
    validate_mouth_led_duration,
    validate_mouth_led_hold,
    validate_mouth_led_level,
)
from robot_controller.mock_server import (
    MockApplicationConfig,
    create_mock_application,
)
from robot_controller.mouth_led_composition import (
    load_mouth_led_backend_settings,
)


DEFAULT_LEVEL = 16
DEFAULT_RISE_MS = 200
DEFAULT_HOLD_MS = 500
DEFAULT_FALL_MS = 200


def _validated_argument(validator, name, value):
    # type: (typing.Any, str, str) -> int
    try:
        parsed = int(value, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "{0} must be an integer".format(name)
        )
    if str(parsed) != value:
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
        description=(
            "Inspect the normal mouth LED Composition Root; pulse only "
            "with --confirm-live-write."
        )
    )
    parser.add_argument(
        "--level",
        type=lambda value: _validated_argument(
            validate_mouth_led_level, "level", value
        ),
        default=DEFAULT_LEVEL,
    )
    parser.add_argument(
        "--rise-ms",
        type=lambda value: _validated_argument(
            validate_mouth_led_duration, "rise-ms", value
        ),
        default=DEFAULT_RISE_MS,
    )
    parser.add_argument(
        "--hold-ms",
        type=lambda value: _validated_argument(
            validate_mouth_led_hold, "hold-ms", value
        ),
        default=DEFAULT_HOLD_MS,
    )
    parser.add_argument(
        "--fall-ms",
        type=lambda value: _validated_argument(
            validate_mouth_led_duration, "fall-ms", value
        ),
        default=DEFAULT_FALL_MS,
    )
    parser.add_argument("--confirm-live-write", action="store_true")
    return parser


def _print_diagnostics(diagnostics, output):
    # type: (typing.Any, typing.Any) -> None
    print("mouth_led_backend_smoke", file=output)
    print(
        "requested_backend_kind={0}".format(
            diagnostics.requested_backend_kind
        ),
        file=output,
    )
    print(
        "resolved_backend_kind={0}".format(
            diagnostics.resolved_backend_kind
        ),
        file=output,
    )
    print(
        "live_hardware_write_enabled={0}".format(
            str(diagnostics.live_hardware_write_enabled).lower()
        ),
        file=output,
    )
    print(
        "mouth_led_backend_configured={0}".format(
            str(diagnostics.mouth_led_backend_configured).lower()
        ),
        file=output,
    )
    if diagnostics.unavailable_reason is not None:
        print(
            "unavailable_reason={0}".format(
                diagnostics.unavailable_reason
            ),
            file=output,
        )


def main(
    argv=None,
    environ=None,
    application_factory=create_mock_application,
    output=None,
    error_output=None,
):
    # type: (typing.Optional[typing.Sequence[str]], typing.Any, typing.Any, typing.Any, typing.Any) -> int
    """Compose normally and optionally invoke exactly one backend pulse."""
    if output is None:
        output = sys.stdout
    if error_output is None:
        error_output = sys.stderr
    arguments = build_argument_parser().parse_args(argv)
    try:
        settings = load_mouth_led_backend_settings(environ)
        application = application_factory(
            MockApplicationConfig(mouth_led_settings=settings)
        )
        _print_diagnostics(
            application.mouth_led_backend_diagnostics, output
        )
        print(
            "live_write={0}".format(
                str(arguments.confirm_live_write).lower()
            ),
            file=output,
        )
        if not arguments.confirm_live_write:
            print("result=dry_run", file=output)
            return 0
        result = application.mouth_led_backend.pulse_mouth_led(
            level=arguments.level,
            rise_ms=arguments.rise_ms,
            hold_ms=arguments.hold_ms,
            fall_ms=arguments.fall_ms,
        )
        print(
            "pulse_completed={0}".format(
                str(result.pulse_completed).lower()
            ),
            file=output,
        )
        print("result=success", file=output)
        return 0
    except Exception as error:
        print("result=failure", file=error_output)
        print(
            "error_type={0}".format(type(error).__name__),
            file=error_output,
        )
        print("error={0}".format(error), file=error_output)
        return 1


if __name__ == "__main__":
    sys.exit(main())
