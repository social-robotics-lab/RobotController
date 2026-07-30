"""Explicit command-line wrapper for the reusable Sota mouth-LED pulse."""

import argparse
import math
import sys
import time
import typing

from robot_controller.hardware.sota.backend import SotaVsmdBackend
from robot_controller.hardware.vsmd.app_manager_mouth_led_pulse import (
    ActiveInterpolationState,
    DEFAULT_LIVE_HOLD_MS,
    InterpolationObservation,
    MAX_LIVE_DURATION_MS,
    MAX_LIVE_HOLD_MS,
    MAX_LIVE_LEVEL,
    MIN_LIVE_DURATION_MS,
    MIN_LIVE_HOLD_MS,
    MIN_LIVE_LEVEL,
    MouthLedPulseResult,
    MouthLedPulseSnapshot,
    validate_mouth_led_duration,
    validate_mouth_led_hold,
    validate_mouth_led_level,
)
from robot_controller.hardware.vsmd.app_manager_transport import (
    AppManagerTcpTransport,
    DEFAULT_APP_MANAGER_HOST,
    DEFAULT_APP_MANAGER_PORT,
    DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.constants import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_HOST,
    DEFAULT_MAX_LINE_LENGTH,
    DEFAULT_PORT,
    DEFAULT_READ_TIMEOUT_SECONDS,
    DEFAULT_WRITE_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    SOTA_MOUTH_GLOBAL_LED_ID,
)
from robot_controller.hardware.vsmd.transport import VsmdTcpTransport


ProbeSnapshot = MouthLedPulseSnapshot
ProbeResult = MouthLedPulseResult
_validate_live_level = validate_mouth_led_level
_validate_live_duration = validate_mouth_led_duration
_validate_live_hold = validate_mouth_led_hold


def _bounded_integer(name, minimum, maximum):
    # type: (str, int, int) -> typing.Callable[[str], int]
    def convert(text):
        # type: (str) -> int
        try:
            value = int(text, 10)
        except ValueError:
            raise argparse.ArgumentTypeError(
                "{0} must be an integer".format(name)
            )
        if value < minimum or value > maximum:
            raise argparse.ArgumentTypeError(
                "{0} must be between {1} and {2}".format(
                    name, minimum, maximum
                )
            )
        return value

    return convert


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


def create_argument_parser():
    # type: () -> argparse.ArgumentParser
    """Build the explicit opt-in live-write CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Run one bounded Sota mouth-LED control sequence. No endpoint "
            "is opened unless --confirm-live-write is present. Success does "
            "not verify physical illumination."
        )
    )
    port = _bounded_integer("port", 1, 65535)
    parser.add_argument(
        "--app-manager-host", default=DEFAULT_APP_MANAGER_HOST
    )
    parser.add_argument(
        "--app-manager-port", type=port, default=DEFAULT_APP_MANAGER_PORT
    )
    parser.add_argument(
        "--app-manager-timeout",
        type=_positive_float,
        default=DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
    )
    parser.add_argument("--vsmd-host", default=DEFAULT_HOST)
    parser.add_argument("--vsmd-port", type=port, default=DEFAULT_PORT)
    parser.add_argument(
        "--vsmd-connect-timeout",
        type=_positive_float,
        default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--vsmd-read-timeout",
        type=_positive_float,
        default=DEFAULT_READ_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--vsmd-write-timeout",
        type=_positive_float,
        default=DEFAULT_WRITE_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--vsmd-max-line-length",
        type=_bounded_integer("vsmd-max-line-length", 1, 0x7FFFFFFF),
        default=DEFAULT_MAX_LINE_LENGTH,
    )
    parser.add_argument(
        "--led-id",
        type=_bounded_integer("led-id", 14, 14),
        default=SOTA_MOUTH_GLOBAL_LED_ID,
    )
    parser.add_argument(
        "--level",
        type=_bounded_integer(
            "level", MIN_LIVE_LEVEL, MAX_LIVE_LEVEL
        ),
        default=MAX_LIVE_LEVEL,
    )
    parser.add_argument(
        "--duration-ms",
        type=_bounded_integer(
            "duration-ms",
            MIN_LIVE_DURATION_MS,
            MAX_LIVE_DURATION_MS,
        ),
        default=MAX_LIVE_DURATION_MS,
    )
    parser.add_argument(
        "--hold-ms",
        type=_bounded_integer(
            "hold-ms",
            MIN_LIVE_HOLD_MS,
            MAX_LIVE_HOLD_MS,
        ),
        default=DEFAULT_LIVE_HOLD_MS,
    )
    parser.add_argument("--confirm-live-write", action="store_true")
    return parser


def _print_snapshot(prefix, snapshot, output):
    # type: (str, typing.Optional[ProbeSnapshot], typing.Any) -> None
    if snapshot is None:
        return
    print(
        "{0}_selector=0x{1:04x}".format(prefix, snapshot.selector),
        file=output,
    )
    print("{0}_target={1}".format(prefix, snapshot.target), file=output)
    print("{0}_output={1}".format(prefix, snapshot.output), file=output)
    print(
        "{0}_trigger_pointer=0x{1:04x}".format(
            prefix, snapshot.trigger_pointer
        ),
        file=output,
    )


def _print_lease(lease, output):
    # type: (typing.Any, typing.Any) -> None
    if lease is None:
        return
    print("lease_state={0}".format(lease.state), file=output)
    print("release_result={0}".format(lease.release_result), file=output)
    print(
        "lock_released={0}".format(
            str(lease.is_released is True).lower()
        ),
        file=output,
    )


def _print_lock_pointer_diagnostics(value, output):
    # type: (typing.Any, typing.Any) -> None
    attempt = getattr(value, "lock_pointer_poll_attempt", None)
    initial = getattr(value, "lock_pointer_initial_value", None)
    final = getattr(value, "lock_pointer_final_value", None)
    duration = getattr(value, "lock_pointer_wait_duration_ms", None)
    converged = getattr(value, "lock_pointer_converged", None)
    if attempt is not None:
        print("lock_pointer_poll_attempt={0}".format(attempt), file=output)
    if initial is not None:
        print(
            "lock_pointer_initial_value=0x{0:04x}".format(initial),
            file=output,
        )
    if final is not None:
        print(
            "lock_pointer_final_value=0x{0:04x}".format(final),
            file=output,
        )
    if duration is not None:
        print(
            "lock_pointer_wait_duration_ms={0:.3f}".format(duration),
            file=output,
        )
    if converged is not None:
        print(
            "lock_pointer_converged={0}".format(
                str(converged).lower()
            ),
            file=output,
        )


def _print_interpolation_state(prefix, state, reached_target, output):
    # type: (str, typing.Optional[InterpolationObservation], bool, typing.Any) -> None
    if state is None:
        return
    print("{0}_output={1}".format(prefix, state.output), file=output)
    print(
        "{0}_remaining_before={1}".format(
            prefix, state.remaining_before
        ),
        file=output,
    )
    print(
        "{0}_remaining_after={1}".format(
            prefix, state.remaining_after
        ),
        file=output,
    )
    print(
        "{0}_remaining_time={1}".format(
            prefix, state.remaining_after
        ),
        file=output,
    )
    print(
        "{0}_trigger_pointer=0x{1:04x}".format(
            prefix, state.trigger_pointer
        ),
        file=output,
    )
    print(
        "{0}_timer_value={1}".format(prefix, state.timer_value),
        file=output,
    )
    print(
        "{0}_observation_read_duration_ms={1:.3f}".format(
            prefix, state.observation_read_duration_ms
        ),
        file=output,
    )
    print(
        "{0}_snapshot_read_duration_ms={1:.3f}".format(
            prefix, state.observation_read_duration_ms
        ),
        file=output,
    )
    print(
        "{0}_poll_attempt={1}".format(prefix, state.poll_attempt),
        file=output,
    )
    print(
        "{0}_reached_target={1}".format(
            prefix,
            str(reached_target is True).lower()
        ),
        file=output,
    )
    if prefix == "rise":
        print(
            "interpolation_reached_target={0}".format(
                str(reached_target is True).lower()
            ),
            file=output,
        )


def _print_observation_history(prefix, observations, output):
    # type: (str, typing.Sequence[InterpolationObservation], typing.Any) -> None
    for observation in observations:
        print(
            (
                "{0}_observation_{1}=pointer=0x{2:04x},"
                "remaining_before={3},output={4},remaining_after={5},"
                "timer_value={6},read_duration_ms={7:.3f}"
            ).format(
                prefix,
                observation.poll_attempt,
                observation.trigger_pointer,
                observation.remaining_before,
                observation.output,
                observation.remaining_after,
                observation.timer_value,
                observation.observation_read_duration_ms,
            ),
            file=output,
        )


def _print_timer_preflight(master_control_period_us, timer_ticks):
    # type: (int, int) -> None
    """Print the verified conversion before any lock or VSMD write."""
    print(
        "master_control_period_us={0}".format(
            master_control_period_us
        )
    )
    print("timer_ticks={0}".format(timer_ticks))
    print("rise_timer_ticks={0}".format(timer_ticks))


def main(
    argv=None,
    vsmd_transport_factory=VsmdTcpTransport,
    app_manager_transport_factory=AppManagerTcpTransport,
    memory_factory=None,
    sleep_function=time.sleep,
    backend_factory=SotaVsmdBackend,
):
    # type: (typing.Optional[typing.Sequence[str]], typing.Any, typing.Any, typing.Any, typing.Any, typing.Any) -> int
    """Run the live probe only after explicit confirmation."""
    arguments = create_argument_parser().parse_args(argv)
    print("Sota AppManager mouth LED live probe")
    if not arguments.confirm_live_write:
        print("live_write=false")
        print("result=failure")
        print("error=--confirm-live-write is required")
        return 2

    print("live_write=true")
    print("led_id={0}".format(arguments.led_id))
    print("level={0}".format(arguments.level))
    print("duration_ms={0}".format(arguments.duration_ms))
    print("transition_duration_ms={0}".format(arguments.duration_ms))
    print("hold_duration_ms={0}".format(arguments.hold_ms))
    print(
        "app_manager_endpoint={0}:{1}".format(
            arguments.app_manager_host, arguments.app_manager_port
        )
    )
    print(
        "vsmd_endpoint={0}:{1}".format(
            arguments.vsmd_host, arguments.vsmd_port
        )
    )

    backend = None  # type: typing.Any
    try:
        backend = backend_factory(
            app_manager_host=arguments.app_manager_host,
            app_manager_port=arguments.app_manager_port,
            app_manager_timeout=arguments.app_manager_timeout,
            vsmd_host=arguments.vsmd_host,
            vsmd_port=arguments.vsmd_port,
            vsmd_connect_timeout=arguments.vsmd_connect_timeout,
            vsmd_read_timeout=arguments.vsmd_read_timeout,
            vsmd_write_timeout=arguments.vsmd_write_timeout,
            vsmd_max_line_length=arguments.vsmd_max_line_length,
            mouth_led_id=arguments.led_id,
            vsmd_transport_factory=vsmd_transport_factory,
            app_manager_transport_factory=app_manager_transport_factory,
            memory_factory=memory_factory,
            sleep_function=sleep_function,
            preflight_callback=_print_timer_preflight,
        )
        result = backend.pulse_mouth_led(
            level=arguments.level,
            rise_ms=arguments.duration_ms,
            hold_ms=arguments.hold_ms,
            fall_ms=arguments.duration_ms,
        )
    except BaseException as error:
        diagnostics = (
            None
            if backend is None
            else getattr(backend, "last_pulse_diagnostics", None)
        )
        if diagnostics is not None:
            _print_snapshot("pre", diagnostics.preflight, sys.stderr)
            if diagnostics.master_control_period_us is not None:
                print(
                    "master_control_period_us={0}".format(
                        diagnostics.master_control_period_us
                    ),
                    file=sys.stderr,
                )
            if diagnostics.timer_ticks is not None:
                print(
                    "timer_ticks={0}".format(diagnostics.timer_ticks),
                    file=sys.stderr,
                )
            if diagnostics.locked_trigger_pointer is not None:
                print(
                    "locked_trigger_pointer=0x{0:04x}".format(
                        diagnostics.locked_trigger_pointer
                    ),
                    file=sys.stderr,
                )
            _print_lock_pointer_diagnostics(diagnostics, sys.stderr)
            print(
                "normalization_required={0}".format(
                    str(diagnostics.normalization_required).lower()
                ),
                file=sys.stderr,
            )
            if diagnostics.normalization_timer_ticks is not None:
                print(
                    "normalization_timer_ticks={0}".format(
                        diagnostics.normalization_timer_ticks
                    ),
                    file=sys.stderr,
                )
            _print_interpolation_state(
                "normalized",
                diagnostics.normalized_state,
                diagnostics.normalization_completed,
                sys.stderr,
            )
            _print_observation_history(
                "normalization",
                diagnostics.normalization_observations,
                sys.stderr,
            )
            print(
                "normalization_completed={0}".format(
                    str(diagnostics.normalization_completed).lower()
                ),
                file=sys.stderr,
            )
            _print_interpolation_state(
                "rise",
                diagnostics.active_state,
                diagnostics.interpolation_reached_target,
                sys.stderr,
            )
            _print_observation_history(
                "rise", diagnostics.active_snapshots, sys.stderr
            )
            _print_interpolation_state(
                "off",
                diagnostics.off_state,
                diagnostics.fade_down_completed,
                sys.stderr,
            )
            _print_observation_history(
                "fall", diagnostics.off_snapshots, sys.stderr
            )
            _print_interpolation_state(
                "emergency",
                diagnostics.emergency_state,
                diagnostics.emergency_fade_down_completed,
                sys.stderr,
            )
            _print_observation_history(
                "emergency",
                diagnostics.emergency_observations,
                sys.stderr,
            )
            print(
                "hold_completed={0}".format(
                    str(diagnostics.hold_completed).lower()
                ),
                file=sys.stderr,
            )
            print(
                "fade_down_completed={0}".format(
                    str(diagnostics.fade_down_completed).lower()
                ),
                file=sys.stderr,
            )
            print(
                "interpolation_output_safe_zero={0}".format(
                    str(
                        diagnostics.interpolation_output_safe_zero
                    ).lower()
                ),
                file=sys.stderr,
            )
            print(
                "routing_state_restored={0}".format(
                    str(diagnostics.routing_state_restored).lower()
                ),
                file=sys.stderr,
            )
            if diagnostics.primary_operation_error is not None:
                print(
                    "primary_operation_error={0}: {1}".format(
                        type(
                            diagnostics.primary_operation_error
                        ).__name__,
                        diagnostics.primary_operation_error,
                    ),
                    file=sys.stderr,
                )
            print(
                "emergency_fade_down_attempted={0}".format(
                    str(
                        diagnostics.emergency_fade_down_attempted
                    ).lower()
                ),
                file=sys.stderr,
            )
            print(
                "emergency_fade_down_completed={0}".format(
                    str(
                        diagnostics.emergency_fade_down_completed
                    ).lower()
                ),
                file=sys.stderr,
            )
            _print_lease(diagnostics.lease, sys.stderr)
        print("result=failure", file=sys.stderr)
        print(
            "error_type={0}".format(type(error).__name__),
            file=sys.stderr,
        )
        print("error={0}".format(error), file=sys.stderr)
        return 1

    _print_snapshot("pre", result.preflight, sys.stdout)
    print(
        "lock_acquired={0}".format(
            str(result.lock_acquired).lower()
        )
    )
    print("timer_address=0x{0:04x}".format(result.timer_address))
    print(
        "locked_trigger_pointer=0x{0:04x}".format(
            result.locked_trigger_pointer
        )
    )
    _print_lock_pointer_diagnostics(result, sys.stdout)
    print(
        "normalization_required={0}".format(
            str(result.normalization_required).lower()
        )
    )
    print(
        "normalization_timer_ticks={0}".format(
            result.normalization_timer_ticks
        )
    )
    _print_interpolation_state(
        "normalized",
        result.normalized_state,
        result.normalization_completed,
        sys.stdout,
    )
    _print_observation_history(
        "normalization",
        result.normalization_observations,
        sys.stdout,
    )
    print(
        "normalization_completed={0}".format(
            str(result.normalization_completed).lower()
        )
    )
    _print_interpolation_state(
        "rise",
        result.active_state,
        result.interpolation_reached_target,
        sys.stdout,
    )
    _print_observation_history(
        "rise", result.active_snapshots, sys.stdout
    )
    print("hold_duration_ms={0}".format(result.hold_duration_ms))
    print(
        "hold_completed={0}".format(
            str(result.hold_completed).lower()
        )
    )
    print("fall_timer_ticks={0}".format(result.fall_timer_ticks))
    _print_interpolation_state(
        "off",
        result.off_state,
        result.fade_down_completed,
        sys.stdout,
    )
    _print_observation_history(
        "fall", result.off_snapshots, sys.stdout
    )
    print(
        "fade_down_completed={0}".format(
            str(result.fade_down_completed).lower()
        )
    )
    print(
        "interpolation_output_safe_zero={0}".format(
            str(result.interpolation_output_safe_zero).lower()
        )
    )
    print(
        "emergency_fade_down_attempted={0}".format(
            str(result.emergency_fade_down_attempted).lower()
        )
    )
    print(
        "emergency_fade_down_completed={0}".format(
            str(result.emergency_fade_down_completed).lower()
        )
    )
    print(
        "pulse_completed={0}".format(
            str(result.pulse_completed).lower()
        )
    )
    print(
        "control_sequence_completed={0}".format(
            str(result.control_sequence_completed).lower()
        )
    )
    print("physical_illumination=not_verified")
    print(
        "cleanup_completed={0}".format(
            str(result.cleanup_completed).lower()
        )
    )
    print("lease_state={0}".format(result.lease_state))
    print("release_result={0}".format(result.release_result))
    print(
        "lock_released={0}".format(
            str(result.lock_released).lower()
        )
    )
    _print_snapshot("post", result.postflight, sys.stdout)
    print(
        "state_restored={0}".format(
            str(result.state_restored).lower()
        )
    )
    print(
        "routing_state_restored={0}".format(
            str(result.routing_state_restored).lower()
        )
    )
    print(
        "interpolation_output_restored={0}".format(
            str(result.interpolation_output_restored).lower()
        )
    )
    print("result=success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
