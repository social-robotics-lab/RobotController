"""Smoke-test the normal mouth LED configuration and composition path."""

import argparse
import sys
import typing

from robot_controller.diagnostic_process_lock import (
    acquire_live_process_lock,
    combine_process_lock_close,
)
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
    BACKEND_SOTA_VSMD,
    load_mouth_led_backend_settings,
)
from robot_controller.process_lock import ProcessLockContextCleanupError


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


def _print_lock_pointer_diagnostics(value, output):
    # type: (typing.Any, typing.Any) -> None
    for name in (
        "lock_pointer_poll_attempt",
        "lock_pointer_wait_duration_ms",
        "lock_pointer_converged",
    ):
        field_value = getattr(value, name, None)
        if field_value is not None:
            if isinstance(field_value, bool):
                field_value = str(field_value).lower()
            print("{0}={1}".format(name, field_value), file=output)
    for name in (
        "lock_pointer_initial_value",
        "lock_pointer_final_value",
    ):
        field_value = getattr(value, name, None)
        if field_value is not None:
            print(
                "{0}=0x{1:04x}".format(name, field_value),
                file=output,
            )


def main(
    argv=None,
    environ=None,
    application_factory=create_mock_application,
    process_lock_factory=None,
    output=None,
    error_output=None,
):
    # type: (typing.Optional[typing.Sequence[str]], typing.Any, typing.Any, typing.Any, typing.Any, typing.Any) -> int
    """Compose normally and optionally invoke exactly one backend pulse."""
    if output is None:
        output = sys.stdout
    if error_output is None:
        error_output = sys.stderr
    arguments = build_argument_parser().parse_args(argv)
    application = None
    process_lock = None
    operation_error = None  # type: typing.Optional[BaseException]
    try:
        settings = load_mouth_led_backend_settings(environ)
        if (
            arguments.confirm_live_write
            and settings.backend_kind == BACKEND_SOTA_VSMD
            and settings.live_hardware_write_enabled is True
        ):
            process_lock = acquire_live_process_lock(
                process_lock_factory
            )
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
        _print_lock_pointer_diagnostics(result, output)
        print(
            "pulse_completed={0}".format(
                str(result.pulse_completed).lower()
            ),
            file=output,
        )
    except BaseException as error:
        operation_error = error
    if process_lock is not None:
        operation_error = combine_process_lock_close(
            process_lock, operation_error
        )
    if operation_error is not None:
        if not isinstance(operation_error, Exception):
            raise operation_error
        if application is not None:
            diagnostics = getattr(
                application.mouth_led_backend,
                "last_pulse_diagnostics",
                None,
            )
            if diagnostics is not None:
                _print_lock_pointer_diagnostics(
                    diagnostics, error_output
                )
        print("result=failure", file=error_output)
        print(
            "error_type={0}".format(type(operation_error).__name__),
            file=error_output,
        )
        if isinstance(
            operation_error, ProcessLockContextCleanupError
        ):
            print(
                "operation_error_type={0}".format(
                    type(operation_error.operation_error).__name__
                ),
                file=error_output,
            )
            print(
                "process_lock_cleanup_error_type={0}".format(
                    type(operation_error.cleanup_error).__name__
                ),
                file=error_output,
            )
        print("error={0}".format(operation_error), file=error_output)
        return 1
    print("result=success", file=output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
