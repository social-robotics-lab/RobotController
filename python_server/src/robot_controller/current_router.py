"""Route validated current-protocol commands to the command service."""

import collections
import typing

from robot_controller.models import MouthLedPulse
from robot_controller.protocol.current import MOUTH_LED_PULSE_COMMAND


class CurrentCommandExecutionError(Exception):
    """Preserve a command failure and its typed cause."""

    def __init__(self, command):
        # type: (str) -> None
        self.command = command
        Exception.__init__(self, "current command execution failed")


_CurrentDispatchResultBase = collections.namedtuple(
    "_CurrentDispatchResultBase", ["backend_result"]
)


class CurrentDispatchResult(_CurrentDispatchResultBase):
    """Internal result from one current command dispatch."""

    __slots__ = ()


class CurrentCommandRouter(object):
    """Dispatch validated current commands without exposing hardware details."""

    def __init__(self, target):
        # type: (typing.Any) -> None
        if not callable(getattr(target, "mouth_led_pulse", None)):
            raise TypeError("target must provide mouth_led_pulse")
        self._target = target

    def dispatch(self, request):
        # type: (typing.Any) -> CurrentDispatchResult
        if (
            request.command != MOUTH_LED_PULSE_COMMAND
            or not isinstance(request.payload, MouthLedPulse)
        ):
            raise TypeError("invalid current command request")
        try:
            return CurrentDispatchResult(
                self._target.mouth_led_pulse(request.payload)
            )
        except Exception as error:
            raise CurrentCommandExecutionError(request.command) from error
