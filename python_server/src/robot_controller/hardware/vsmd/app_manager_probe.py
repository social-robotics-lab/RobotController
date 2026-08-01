"""Explicit SotaAppManager LED-lock diagnostic probe.

This command talks only to the configured SotaAppManager endpoint. It does
not construct the VSMD memory transport or perform direct memory I/O.
"""

import argparse
import math
import sys
import time
import typing

from robot_controller.diagnostic_process_lock import (
    acquire_live_process_lock,
    combine_process_lock_close,
)
from robot_controller.hardware.vsmd.app_manager_lock import (
    AppManagerLedLock,
)
from robot_controller.hardware.vsmd.app_manager_transport import (
    AppManagerTcpTransport,
    DEFAULT_APP_MANAGER_HOST,
    DEFAULT_APP_MANAGER_PORT,
    DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
)
from robot_controller.process_lock import ProcessLockContextCleanupError


DEFAULT_LED_ID = 14
DEFAULT_HOLD_SECONDS = 0.2
MAX_HOLD_SECONDS = 1.0


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


def _hold_seconds(text):
    # type: (str) -> float
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("hold-seconds must be a number")
    if (
        not math.isfinite(value)
        or value < 0
        or value > MAX_HOLD_SECONDS
    ):
        raise argparse.ArgumentTypeError(
            "hold-seconds must be between 0 and 1.0"
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


def create_argument_parser():
    # type: () -> argparse.ArgumentParser
    """Build the explicit, bounded diagnostic CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Acquire one SotaAppManager LED interpolation lock briefly, "
            "then release it exactly once."
        )
    )
    parser.add_argument("--host", default=DEFAULT_APP_MANAGER_HOST)
    parser.add_argument("--port", type=_port, default=DEFAULT_APP_MANAGER_PORT)
    parser.add_argument("--led-id", type=_led_id, default=DEFAULT_LED_ID)
    parser.add_argument(
        "--hold-seconds",
        type=_hold_seconds,
        default=DEFAULT_HOLD_SECONDS,
    )
    parser.add_argument(
        "--connect-timeout",
        type=_positive_timeout,
        default=DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--read-timeout",
        type=_positive_timeout,
        default=DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--write-timeout",
        type=_positive_timeout,
        default=DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
    )
    parser.add_argument("--confirm-live-lock", action="store_true")
    return parser


def _common_timeout(arguments):
    # type: (argparse.Namespace) -> float
    """Map the CLI to the existing transport without hiding differences."""
    values = (
        arguments.connect_timeout,
        arguments.read_timeout,
        arguments.write_timeout,
    )
    if values[0] != values[1] or values[0] != values[2]:
        raise ValueError(
            "existing AppManagerTcpTransport requires connect, read, and "
            "write timeouts to be equal"
        )
    return values[0]


def main(
    argv=None,
    transport_factory=AppManagerTcpTransport,
    lock_factory=AppManagerLedLock,
    sleep_function=time.sleep,
    process_lock_factory=None,
):
    # type: (typing.Optional[typing.Sequence[str]], typing.Any, typing.Any, typing.Any, typing.Any) -> int
    """Run one bounded LOCK, hold, and UNLOCK sequence without retry."""
    arguments = create_argument_parser().parse_args(argv)
    if not arguments.confirm_live_lock:
        print("live_lock=false")
        print("result=confirmation_required")
        return 0
    print("SotaAppManager LED lock probe")
    print("endpoint={0}:{1}".format(arguments.host, arguments.port))
    print("led_ids={0}".format(arguments.led_id))
    print(
        "warning=lock operation changes TriggerPointer through "
        "SotaAppManager"
    )
    print(
        (
            "timeouts connect={0} read={1} write={2}"
        ).format(
            arguments.connect_timeout,
            arguments.read_timeout,
            arguments.write_timeout,
        )
    )

    process_lock = None
    try:
        process_lock = acquire_live_process_lock(process_lock_factory)
        timeout = _common_timeout(arguments)
        transport = transport_factory(
            host=arguments.host,
            port=arguments.port,
            timeout=timeout,
        )
        led_lock = lock_factory(transport=transport)
        lease = led_lock.acquire_leds((arguments.led_id,))
        try:
            print("lock_acquired=true")
            print("lock_key={0}".format(lease.key))
            print("timer_address={0}".format(lease.timer_address))
            print(
                "timer_address_hex=0x{0:04x}".format(
                    lease.timer_address
                )
            )
            print("hold_seconds={0}".format(arguments.hold_seconds))
            sleep_function(arguments.hold_seconds)
        finally:
            try:
                lease.release()
            except BaseException:
                print("lock_released=false")
                raise
            else:
                print("lock_released=true")
    except BaseException as error:
        if process_lock is not None:
            error = combine_process_lock_close(process_lock, error)
        print("result=failure", file=sys.stderr)
        print(
            "error_type={0}".format(type(error).__name__),
            file=sys.stderr,
        )
        if isinstance(error, ProcessLockContextCleanupError):
            print(
                "operation_error_type={0}".format(
                    type(error.operation_error).__name__
                ),
                file=sys.stderr,
            )
            print(
                "process_lock_cleanup_error_type={0}".format(
                    type(error.cleanup_error).__name__
                ),
                file=sys.stderr,
            )
        print("error={0}".format(error), file=sys.stderr)
        return 1

    close_error = combine_process_lock_close(process_lock, None)
    if close_error is not None:
        print("result=failure", file=sys.stderr)
        print(
            "error_type={0}".format(type(close_error).__name__),
            file=sys.stderr,
        )
        print("error={0}".format(close_error), file=sys.stderr)
        return 1
    print("result=success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
