"""Backend contract and hardware-free implementations for mouth LED pulses."""

import abc
import collections
import threading
import typing

from robot_controller.errors import HardwareBackendUnavailableError


MIN_MOUTH_LED_LEVEL = 1
MAX_MOUTH_LED_LEVEL = 16
MIN_MOUTH_LED_DURATION_MS = 50
MAX_MOUTH_LED_DURATION_MS = 200
MIN_MOUTH_LED_HOLD_MS = 100
MAX_MOUTH_LED_HOLD_MS = 1000


def validate_mouth_led_level(value):
    # type: (int) -> None
    """Validate the physically verified conservative brightness range."""
    _validate_integer(
        "level", value, MIN_MOUTH_LED_LEVEL, MAX_MOUTH_LED_LEVEL
    )


def validate_mouth_led_duration(value):
    # type: (int) -> None
    """Validate a conservative rise or fall duration."""
    _validate_integer(
        "duration_ms",
        value,
        MIN_MOUTH_LED_DURATION_MS,
        MAX_MOUTH_LED_DURATION_MS,
    )


def validate_mouth_led_hold(value):
    # type: (int) -> None
    """Validate the physically verified conservative hold range."""
    _validate_integer(
        "hold_ms", value, MIN_MOUTH_LED_HOLD_MS, MAX_MOUTH_LED_HOLD_MS
    )


def validate_mouth_led_pulse(level, rise_ms, hold_ms, fall_ms):
    # type: (int, int, int, int) -> None
    """Validate all public pulse arguments consistently across backends."""
    validate_mouth_led_level(level)
    validate_mouth_led_duration(rise_ms)
    validate_mouth_led_hold(hold_ms)
    validate_mouth_led_duration(fall_ms)


def _validate_integer(name, value, minimum, maximum):
    # type: (str, int, int, int) -> None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("{0} must be an integer".format(name))
    if value < minimum or value > maximum:
        raise ValueError(
            "{0} must be between {1} and {2}".format(
                name, minimum, maximum
            )
        )


class MouthLedBackend(abc.ABC):
    """Reusable backend boundary for one bounded mouth LED pulse."""

    @abc.abstractmethod
    def pulse_mouth_led(self, level, rise_ms, hold_ms, fall_ms):
        # type: (int, int, int, int) -> typing.Any
        """Run one validated pulse and return structured diagnostics."""
        raise NotImplementedError


_MouthLedPulseCallBase = collections.namedtuple(
    "_MouthLedPulseCallBase",
    ["level", "rise_ms", "hold_ms", "fall_ms"],
)


class MouthLedPulseCall(_MouthLedPulseCallBase):
    """Immutable record of one backend invocation."""

    __slots__ = ()


_MockMouthLedPulseResultBase = collections.namedtuple(
    "_MockMouthLedPulseResultBase",
    [
        "level",
        "rise_ms",
        "hold_ms",
        "fall_ms",
        "master_control_period_us",
        "normalization_required",
        "normalization_completed",
        "rise_timer_ticks",
        "rise_reached_target",
        "hold_completed",
        "fall_timer_ticks",
        "fade_down_completed",
        "interpolation_output_safe_zero",
        "routing_state_restored",
        "lock_released",
        "pulse_completed",
        "timer_address",
        "normalization_observations",
        "rise_observations",
        "fall_observations",
        "preflight",
        "postflight",
    ],
)


class MockMouthLedPulseResult(_MockMouthLedPulseResultBase):
    """Structured hardware-free success returned by the Mock backend."""

    __slots__ = ()


class MockMouthLedBackend(MouthLedBackend):
    """Record calls deterministically without sleeping or touching hardware."""

    def __init__(self, failure=None):
        # type: (typing.Optional[BaseException]) -> None
        self._calls = []  # type: typing.List[MouthLedPulseCall]
        self._failure = None  # type: typing.Optional[BaseException]
        self._lock = threading.Lock()
        self.set_failure(failure)

    @property
    def calls(self):
        # type: () -> typing.Tuple[MouthLedPulseCall, ...]
        with self._lock:
            return tuple(self._calls)

    def set_failure(self, failure):
        # type: (typing.Optional[BaseException]) -> None
        """Configure a typed or test-specific failure for later calls."""
        if failure is not None and not isinstance(failure, BaseException):
            raise TypeError("failure must be an exception or None")
        with self._lock:
            self._failure = failure

    def pulse_mouth_led(self, level, rise_ms, hold_ms, fall_ms):
        # type: (int, int, int, int) -> MockMouthLedPulseResult
        validate_mouth_led_pulse(level, rise_ms, hold_ms, fall_ms)
        call = MouthLedPulseCall(level, rise_ms, hold_ms, fall_ms)
        with self._lock:
            self._calls.append(call)
            failure = self._failure
        if failure is not None:
            raise failure
        return MockMouthLedPulseResult(
            level,
            rise_ms,
            hold_ms,
            fall_ms,
            None,
            False,
            True,
            None,
            True,
            True,
            None,
            True,
            True,
            True,
            True,
            True,
            None,
            (),
            (),
            (),
            None,
            None,
        )


class UnavailableMouthLedBackend(MouthLedBackend):
    """Fail closed while the production Composition Root remains unwired."""

    def pulse_mouth_led(self, level, rise_ms, hold_ms, fall_ms):
        # type: (int, int, int, int) -> typing.NoReturn
        validate_mouth_led_pulse(level, rise_ms, hold_ms, fall_ms)
        raise HardwareBackendUnavailableError(
            "mouth LED hardware backend is unavailable"
        )
