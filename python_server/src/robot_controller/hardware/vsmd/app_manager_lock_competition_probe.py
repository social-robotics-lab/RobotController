"""Explicit two-client SotaAppManager timer-slot observation probe.

This operator diagnostic creates only AppManager transports. It performs no
direct robot-memory operation and has no timing-based hold interval.
"""

import argparse
import math
import sys
import typing

from robot_controller.hardware.vsmd.app_manager_lock import (
    AppManagerLedLock,
)
from robot_controller.hardware.vsmd.app_manager_transport import (
    AppManagerTcpTransport,
    DEFAULT_APP_MANAGER_HOST,
    DEFAULT_APP_MANAGER_PORT,
    DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
)
DEFAULT_LED_ID = 14
DEFAULT_KEY_PREFIX = "phase7-lock"


class AppManagerCompetitionTimerAliasError(Exception):
    """Both observed clients received the same interpolation timer slot."""


class AppManagerCompetitionCleanupError(Exception):
    """Preserve a probe failure and every failed known-lease cleanup."""

    def __init__(self, primary_error, cleanup_errors):
        # type: (BaseException, typing.Sequence[BaseException]) -> None
        self.primary_error = primary_error
        self.cleanup_errors = tuple(cleanup_errors)
        Exception.__init__(
            self,
            (
                "competition probe failed with {0}; cleanup failed with "
                "{1}"
            ).format(
                type(primary_error).__name__,
                ",".join(
                    type(error).__name__
                    for error in self.cleanup_errors
                ),
            ),
        )


def _host(text):
    # type: (str) -> str
    if not text:
        raise argparse.ArgumentTypeError("host must be non-empty")
    return text


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


def _led_id(text):
    # type: (str) -> int
    try:
        value = int(text, 10)
    except ValueError:
        raise argparse.ArgumentTypeError("led-id must be an integer")
    if value < 0 or value > 31:
        raise argparse.ArgumentTypeError(
            "led-id must be between 0 and 31"
        )
    return value


def _positive_timeout(text):
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


def _key_prefix(text):
    # type: (str) -> str
    if not text:
        raise argparse.ArgumentTypeError("key-prefix must be non-empty")
    try:
        encoded = text.encode("ascii")
    except UnicodeEncodeError:
        raise argparse.ArgumentTypeError(
            "key-prefix must contain ASCII only"
        )
    if any(value < 0x21 or value > 0x7E for value in encoded):
        raise argparse.ArgumentTypeError(
            "key-prefix must contain printable non-space ASCII only"
        )
    return text


def create_argument_parser():
    # type: () -> argparse.ArgumentParser
    """Build the explicit opt-in competition diagnostic CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Observe independent AppManager timer slots for two keys that "
            "request the same LED ID."
        )
    )
    parser.add_argument(
        "--host", type=_host, default=DEFAULT_APP_MANAGER_HOST
    )
    parser.add_argument(
        "--port", type=_port, default=DEFAULT_APP_MANAGER_PORT
    )
    parser.add_argument(
        "--led-id", type=_led_id, default=DEFAULT_LED_ID
    )
    parser.add_argument(
        "--timeout",
        type=_positive_timeout,
        default=DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--key-prefix",
        type=_key_prefix,
        default=DEFAULT_KEY_PREFIX,
    )
    parser.add_argument("--confirm-live-lock", action="store_true")
    return parser


def _fixed_key_factory(key):
    # type: (str) -> typing.Callable[[], str]
    def create_key():
        # type: () -> str
        return key

    return create_key


def _new_clients(arguments, transport_factory, lock_factory):
    # type: (argparse.Namespace, typing.Any, typing.Any) -> typing.Tuple[typing.Tuple[typing.Any, ...], typing.Tuple[str, ...]]
    keys = tuple(
        "{0}-{1}".format(arguments.key_prefix, suffix)
        for suffix in ("a", "b")
    )
    locks = []
    for key in keys:
        transport = transport_factory(
            host=arguments.host,
            port=arguments.port,
            timeout=arguments.timeout,
        )
        locks.append(
            lock_factory(
                transport=transport,
                key_factory=_fixed_key_factory(key),
            )
        )
    return tuple(locks), keys


def _release_once(states, name):
    # type: (typing.Dict[str, typing.Any], str) -> None
    state = states[name]
    lease = state["lease"]
    if lease is None or state["release_attempted"]:
        return
    state["release_attempted"] = True
    lease.release()


def _cleanup_known_leases(states):
    # type: (typing.Dict[str, typing.Any]) -> typing.Tuple[BaseException, ...]
    errors = []
    for name in ("b", "a"):
        try:
            _release_once(states, name)
        except BaseException as error:
            errors.append(error)
    return tuple(errors)


def _run_competition(arguments, locks, keys, output):
    # type: (argparse.Namespace, typing.Tuple[typing.Any, ...], typing.Tuple[str, ...], typing.Any) -> None
    states = {
        "a": {"lease": None, "release_attempted": False},
        "b": {"lease": None, "release_attempted": False},
    }  # type: typing.Dict[str, typing.Any]
    try:
        print("client_a_key={0}".format(keys[0]), file=output)
        states["a"]["lease"] = locks[0].acquire_leds(
            (arguments.led_id,)
        )
        print("client_a_lock_acquired=true", file=output)
        print(
            "client_a_timer_address={0}".format(
                states["a"]["lease"].timer_address
            ),
            file=output,
        )

        print("", file=output)
        print("client_b_key={0}".format(keys[1]), file=output)
        states["b"]["lease"] = locks[1].acquire_leds(
            (arguments.led_id,)
        )
        print("client_b_lock_acquired=true", file=output)
        print(
            "client_b_timer_address={0}".format(
                states["b"]["lease"].timer_address
            ),
            file=output,
        )
        if (
            states["a"]["lease"].timer_address
            == states["b"]["lease"].timer_address
        ):
            raise AppManagerCompetitionTimerAliasError(
                "clients A and B received the same interpolation timer slot"
            )
        print("timer_addresses_distinct=true", file=output)
        print("cross_process_exclusion=false", file=output)

        print("", file=output)
        _release_once(states, "b")
        print("client_b_lock_released=true", file=output)
        _release_once(states, "a")
        print("client_a_lock_released=true", file=output)
    except BaseException as primary_error:
        cleanup_errors = _cleanup_known_leases(states)
        if cleanup_errors:
            raise AppManagerCompetitionCleanupError(
                primary_error, cleanup_errors
            ) from cleanup_errors[0]
        raise


def _print_failure(error, error_output):
    # type: (BaseException, typing.Any) -> None
    print("result=failure", file=error_output)
    print(
        "error_type={0}".format(type(error).__name__),
        file=error_output,
    )
    if isinstance(error, AppManagerCompetitionCleanupError):
        print(
            "primary_error_type={0}".format(
                type(error.primary_error).__name__
            ),
            file=error_output,
        )
        print(
            "primary_error={0}".format(error.primary_error),
            file=error_output,
        )
        print(
            "cleanup_error_types={0}".format(
                ",".join(
                    type(cleanup_error).__name__
                    for cleanup_error in error.cleanup_errors
                )
            ),
            file=error_output,
        )
        for index, cleanup_error in enumerate(
            error.cleanup_errors, start=1
        ):
            print(
                "cleanup_error_{0}={1}".format(
                    index, cleanup_error
                ),
                file=error_output,
            )
    print("error={0}".format(error), file=error_output)


def main(
    argv=None,
    transport_factory=AppManagerTcpTransport,
    lock_factory=AppManagerLedLock,
    output=None,
    error_output=None,
):
    # type: (typing.Optional[typing.Sequence[str]], typing.Any, typing.Any, typing.Any, typing.Any) -> int
    """Run the explicit A/B allocation and B/A release without retry."""
    if output is None:
        output = sys.stdout
    if error_output is None:
        error_output = sys.stderr
    arguments = create_argument_parser().parse_args(argv)
    if not arguments.confirm_live_lock:
        print("live_network=false", file=output)
        print("live_lock=false", file=output)
        print("result=confirmation_required", file=output)
        return 0

    print("SotaAppManager LED timer-slot observation probe", file=output)
    print("live_network=true", file=output)
    print("live_lock=true", file=output)
    print("led_id={0}".format(arguments.led_id), file=output)
    print("", file=output)
    try:
        locks, keys = _new_clients(
            arguments, transport_factory, lock_factory
        )
        _run_competition(arguments, locks, keys, output)
    except BaseException as error:
        _print_failure(error, error_output)
        return 1

    print("", file=output)
    print("vsmd_transport_created=false", file=output)
    print("vsmd_read_write=false", file=output)
    print("automatic_retry=false", file=output)
    print("result=observed_semantics", file=output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
