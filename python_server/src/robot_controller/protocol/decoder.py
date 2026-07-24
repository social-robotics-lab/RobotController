"""Decode legacy v1 payload bytes into validated internal models."""

import json

from robot_controller.errors import (
    NonStandardJsonNumberError,
    PayloadDecodeError,
    PayloadJsonError,
)
from robot_controller.models import DecodedCommand
from robot_controller.profiles import RobotProfile
from robot_controller.protocol.legacy_v1 import LegacyV1Request
from robot_controller.protocol.validation import (
    DEFAULT_VALIDATION_LIMITS,
    ValidationLimits,
    validate_idle_motion,
    validate_motion,
    validate_pose,
)


_JSON_COMMAND_VALIDATORS = {
    "play_pose": validate_pose,
    "play_motion": validate_motion,
    "play_idle_motion": validate_idle_motion,
}


class _RejectedJsonConstant(ValueError):
    """Internal marker preserving the rejected JSON number token."""

    def __init__(self, token):
        # type: (str) -> None
        self.token = token
        ValueError.__init__(self, "non-standard JSON number")


def decode_request(
    request,
    robot_profile,
    limits=DEFAULT_VALIDATION_LIMITS,
):
    # type: (LegacyV1Request, RobotProfile, ValidationLimits) -> DecodedCommand
    """Convert a legacy request into one validated internal command.

    WAV bytes remain opaque in this layer. Commands without payloads are
    normalized to ``None``.
    """
    validator = _JSON_COMMAND_VALIDATORS.get(request.command)
    if validator is not None:
        value = _decode_json(request.command, request.payload)
        payload = validator(value, robot_profile, limits, request.command)
        return DecodedCommand(request.command, payload)

    if request.command == "play_wav":
        return DecodedCommand(request.command, request.payload)

    return DecodedCommand(request.command, None)


def _decode_json(command, payload):
    # type: (str, bytes) -> object
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PayloadDecodeError(command) from error

    try:
        return json.loads(text, parse_constant=_reject_json_constant)
    except _RejectedJsonConstant as error:
        raise NonStandardJsonNumberError(command, error.token) from error
    except ValueError as error:
        raise PayloadJsonError(command) from error


def _reject_json_constant(token):
    # type: (str) -> None
    raise _RejectedJsonConstant(token)
