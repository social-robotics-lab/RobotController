"""Tests for the explicit v2 production command envelope."""

import json
import math

import pytest

from robot_controller.protocol.current import (
    CurrentProtocolError,
    MOUTH_LED_PULSE_WIRE_COMMAND,
    decode_request,
    encode_error,
    encode_success,
)


def encoded(payload):
    return json.dumps(payload).encode("utf-8")


def valid_envelope():
    return {
        "request_id": "request-1",
        "payload": {
            "level": 16,
            "rise_ms": 200,
            "hold_ms": 500,
            "fall_ms": 200,
        },
    }


def test_decodes_all_four_validated_arguments():
    request = decode_request(
        MOUTH_LED_PULSE_WIRE_COMMAND, encoded(valid_envelope())
    )

    assert request.request_id == "request-1"
    assert request.command == "mouth_led_pulse"
    assert tuple(request.payload) == (16, 200, 500, 200)


@pytest.mark.parametrize(
    "field,value",
    [
        ("level", None),
        ("level", "16"),
        ("level", 16.0),
        ("level", True),
        ("level", -1),
        ("level", 17),
        ("rise_ms", 49),
        ("rise_ms", math.nan),
        ("hold_ms", 99),
        ("hold_ms", math.inf),
        ("fall_ms", 201),
    ],
)
def test_rejects_invalid_values(field, value):
    envelope = valid_envelope()
    envelope["payload"][field] = value

    with pytest.raises(CurrentProtocolError) as caught:
        decode_request(MOUTH_LED_PULSE_WIRE_COMMAND, encoded(envelope))

    assert caught.value.code in (
        "PROTOCOL_DECODE_ERROR",
        "VALIDATION_ERROR",
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["payload"].pop("level"),
        lambda value: value.update({"request_id": None}),
        lambda value: value.update({"payload": None}),
    ],
)
def test_rejects_missing_and_invalid_envelope_fields(mutate):
    envelope = valid_envelope()
    mutate(envelope)

    with pytest.raises(CurrentProtocolError) as caught:
        decode_request(MOUTH_LED_PULSE_WIRE_COMMAND, encoded(envelope))

    assert caught.value.code == "VALIDATION_ERROR"


def test_unknown_fields_follow_v1_policy_and_are_ignored():
    envelope = valid_envelope()
    envelope["extra"] = "ignored"
    envelope["payload"]["extra"] = "ignored"

    request = decode_request(
        MOUTH_LED_PULSE_WIRE_COMMAND, encoded(envelope)
    )

    assert tuple(request.payload) == (16, 200, 500, 200)


def test_unknown_v2_command_is_distinct():
    with pytest.raises(CurrentProtocolError) as caught:
        decode_request("v2/not_known", encoded(valid_envelope()))

    assert caught.value.code == "UNKNOWN_COMMAND"


def test_success_and_error_responses_are_structured_and_sanitized():
    class Result(object):
        pulse_completed = True
        lock_pointer_converged = True

    success = json.loads(
        encode_success("request-1", "mouth_led_pulse", Result())
    )
    failure = json.loads(
        encode_error("MOUTH_LED_OPERATION_FAILED", "operation failed")
    )

    assert success == {
        "version": 2,
        "request_id": "request-1",
        "status": "success",
        "command": "mouth_led_pulse",
        "result": {
            "pulse_completed": True,
            "lock_pointer_converged": True,
        },
    }
    assert failure["status"] == "error"
    assert failure["error"]["code"] == "MOUTH_LED_OPERATION_FAILED"
    assert "trace" not in failure
