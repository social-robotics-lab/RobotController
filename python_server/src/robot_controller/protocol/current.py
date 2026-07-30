"""Explicit v2 command envelope for production-only extensions."""

import collections
import json
import typing

from robot_controller.hardware.mouth_led_backend import (
    validate_mouth_led_pulse,
)
from robot_controller.models import MouthLedPulse


PROTOCOL_VERSION = 2
COMMAND_PREFIX = "v2/"
MOUTH_LED_PULSE_COMMAND = "mouth_led_pulse"
MOUTH_LED_PULSE_WIRE_COMMAND = COMMAND_PREFIX + MOUTH_LED_PULSE_COMMAND
MAX_REQUEST_ID_LENGTH = 128


class CurrentProtocolError(Exception):
    """Safe structured failure that may be returned to a v2 client."""

    def __init__(self, code, message, request_id=None):
        # type: (str, str, typing.Optional[str]) -> None
        self.code = code
        self.client_message = message
        self.request_id = request_id
        Exception.__init__(self, message)


class _RejectedJsonConstant(ValueError):
    """Internal marker for a non-standard JSON numeric token."""


_CurrentRequestBase = collections.namedtuple(
    "_CurrentRequestBase", ["request_id", "command", "payload"]
)


class CurrentRequest(_CurrentRequestBase):
    """One decoded v2 request."""

    __slots__ = ()


def decode_request(command, payload_bytes):
    # type: (str, bytes) -> CurrentRequest
    """Decode and strictly validate one v2 command payload."""
    if command != MOUTH_LED_PULSE_WIRE_COMMAND:
        raise CurrentProtocolError(
            "UNKNOWN_COMMAND", "unsupported v2 command"
        )
    try:
        text = payload_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise CurrentProtocolError(
            "PROTOCOL_DECODE_ERROR", "request payload is not valid UTF-8"
        )
    try:
        envelope = json.loads(text, parse_constant=_reject_constant)
    except _RejectedJsonConstant:
        raise CurrentProtocolError(
            "VALIDATION_ERROR",
            "request payload contains a non-standard number",
        )
    except (TypeError, ValueError):
        raise CurrentProtocolError(
            "PROTOCOL_DECODE_ERROR", "request payload is not valid JSON"
        )
    if not isinstance(envelope, dict):
        raise CurrentProtocolError(
            "VALIDATION_ERROR", "request envelope must be an object"
        )

    request_id = envelope.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise CurrentProtocolError(
            "VALIDATION_ERROR", "request_id must be a non-empty string"
        )
    if len(request_id) > MAX_REQUEST_ID_LENGTH:
        raise CurrentProtocolError(
            "VALIDATION_ERROR",
            "request_id is too long",
            request_id=None,
        )
    if "payload" not in envelope:
        raise CurrentProtocolError(
            "VALIDATION_ERROR",
            "request payload field is missing",
            request_id=request_id,
        )

    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise CurrentProtocolError(
            "VALIDATION_ERROR",
            "payload must be an object",
            request_id=request_id,
        )
    required = {"level", "rise_ms", "hold_ms", "fall_ms"}
    if not required.issubset(payload):
        raise CurrentProtocolError(
            "VALIDATION_ERROR",
            "mouth_led_pulse fields are missing",
            request_id=request_id,
        )
    values = (
        payload["level"],
        payload["rise_ms"],
        payload["hold_ms"],
        payload["fall_ms"],
    )
    try:
        validate_mouth_led_pulse(*values)
    except (TypeError, ValueError):
        raise CurrentProtocolError(
            "VALIDATION_ERROR",
            "mouth_led_pulse values are invalid",
            request_id=request_id,
        )
    return CurrentRequest(
        request_id,
        MOUTH_LED_PULSE_COMMAND,
        MouthLedPulse(*values)
    )


def encode_success(request_id, command, backend_result):
    # type: (str, str, typing.Any) -> bytes
    """Encode a minimal non-secret v2 success response."""
    result = {
        "pulse_completed": bool(
            getattr(backend_result, "pulse_completed", False)
        )
    }
    if hasattr(backend_result, "lock_pointer_converged"):
        result["lock_pointer_converged"] = bool(
            backend_result.lock_pointer_converged
        )
    return _encode(
        {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "status": "success",
            "command": command,
            "result": result,
        }
    )


def encode_error(code, message, request_id=None):
    # type: (str, str, typing.Optional[str]) -> bytes
    """Encode a sanitized v2 error response."""
    value = {
        "version": PROTOCOL_VERSION,
        "request_id": request_id,
        "status": "error",
        "error": {"code": code, "message": message},
    }
    return _encode(value)


def _encode(value):
    # type: (typing.Mapping[str, typing.Any]) -> bytes
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _reject_constant(token):
    # type: (str) -> None
    raise _RejectedJsonConstant("non-standard JSON number")
