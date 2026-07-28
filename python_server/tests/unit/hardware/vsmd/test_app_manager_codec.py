"""Golden vectors for the strict SotaAppManager protocol codec."""

import json
import struct

import pytest

from robot_controller.hardware.vsmd.app_manager_codec import (
    JAVA_SHORT_SERIALIZATION_PREFIX,
    JAVA_STREAM_HEADER,
    SERIALIZED_NG,
    SERIALIZED_NULL,
    SERIALIZED_OK,
    decode_response,
    encode_convert_request,
    encode_lock_request,
    encode_unlock_request,
)
from robot_controller.hardware.vsmd.errors import (
    AppManagerProtocolError,
    AppManagerUnexpectedResponseError,
    VsmdValidationError,
)


LOCK_GOLDEN = (
    b'{"cmd":"INTERP_LOCK","subjson":"{\\"key\\":\\"fixture-key\\",'
    b'\\"ids\\":[14],\\"isServo\\":false}"}'
)
CONVERT_GOLDEN = (
    b'{"cmd":"INTERP_CNV_KEY_2_ADDR",'
    b'"subjson":"{\\"key\\":\\"fixture-key\\"}"}'
)
UNLOCK_GOLDEN = (
    b'{"cmd":"INTERP_UNLOCK","subjson":"{\\"key\\":\\"fixture-key\\",'
    b'\\"ids\\":[14],\\"isServo\\":false}"}'
)


def serialized_short(value):
    return JAVA_SHORT_SERIALIZATION_PREFIX + struct.pack(">h", value)


def test_serialized_short_golden_shape_is_exactly_77_bytes():
    assert len(JAVA_SHORT_SERIALIZATION_PREFIX) == 75
    assert len(serialized_short(502)) == 77
    assert serialized_short(502).hex().endswith("01f6")


def test_request_json_golden_vectors_are_exact_and_have_no_line_ending():
    assert encode_lock_request("fixture-key", [14]) == LOCK_GOLDEN
    assert encode_convert_request("fixture-key") == CONVERT_GOLDEN
    assert encode_unlock_request("fixture-key", [14]) == UNLOCK_GOLDEN
    assert not LOCK_GOLDEN.endswith(b"\n")
    assert b"\r" not in LOCK_GOLDEN
    assert b" " not in LOCK_GOLDEN


def test_subjson_is_a_compact_json_string_not_an_object():
    outer = json.loads(encode_lock_request("fixture-key", [14]).decode("ascii"))
    assert list(outer.keys()) == ["cmd", "subjson"]
    assert isinstance(outer["subjson"], str)
    assert json.loads(outer["subjson"]) == {
        "key": "fixture-key",
        "ids": [14],
        "isServo": False,
    }


@pytest.mark.parametrize("key", ["", "\N{SNOWMAN}"])
def test_empty_or_non_ascii_key_is_rejected(key):
    with pytest.raises(VsmdValidationError):
        encode_lock_request(key, [14])
    with pytest.raises(VsmdValidationError):
        encode_convert_request(key)


@pytest.mark.parametrize(
    "ids",
    [
        [],
        [True],
        ["14"],
        [-1],
        [32],
        [14, 14],
    ],
)
def test_invalid_led_ids_are_rejected(ids):
    with pytest.raises(VsmdValidationError):
        encode_lock_request("fixture-key", ids)
    with pytest.raises(VsmdValidationError):
        encode_unlock_request("fixture-key", ids)


def test_valid_led_id_boundaries_and_order_are_preserved():
    encoded = encode_lock_request("fixture-key", [0, 31])
    outer = json.loads(encoded.decode("ascii"))
    assert json.loads(outer["subjson"])["ids"] == [0, 31]


@pytest.mark.parametrize(
    "serialized,expected",
    [
        (SERIALIZED_OK, "OK"),
        (SERIALIZED_NG, "NG"),
        (SERIALIZED_NULL, None),
        (serialized_short(0), 0),
        (serialized_short(496), 496),
        (serialized_short(502), 502),
        (serialized_short(558), 558),
    ],
)
def test_verified_java_serialization_values_decode(serialized, expected):
    assert decode_response(serialized) == expected


def test_invalid_stream_magic_and_version_are_rejected():
    with pytest.raises(AppManagerProtocolError, match="magic"):
        decode_response(b"\x00\xed\x00\x05\x70")
    with pytest.raises(AppManagerProtocolError, match="version"):
        decode_response(b"\xac\xed\x00\x04\x70")


@pytest.mark.parametrize(
    "serialized",
    [
        JAVA_STREAM_HEADER + b"\x74",
        JAVA_STREAM_HEADER + b"\x74\x00",
        JAVA_STREAM_HEADER + b"\x74\x00\x02O",
    ],
)
def test_truncated_string_is_rejected(serialized):
    with pytest.raises(AppManagerProtocolError):
        decode_response(serialized)


def test_unknown_string_is_a_distinct_unexpected_response():
    with pytest.raises(AppManagerUnexpectedResponseError):
        decode_response(JAVA_STREAM_HEADER + b"\x74\x00\x03BAD")


def test_invalid_string_length_and_extra_bytes_are_rejected():
    with pytest.raises(AppManagerProtocolError):
        decode_response(JAVA_STREAM_HEADER + b"\x74\x00\x03OK")
    with pytest.raises(AppManagerProtocolError):
        decode_response(SERIALIZED_OK + b"\x00")


def test_invalid_short_descriptor_truncation_and_extra_bytes_are_rejected():
    invalid = bytearray(serialized_short(496))
    invalid[10] ^= 0x01
    with pytest.raises(AppManagerProtocolError, match="descriptor"):
        decode_response(bytes(invalid))
    with pytest.raises(AppManagerProtocolError):
        decode_response(serialized_short(496)[:-1])
    with pytest.raises(AppManagerProtocolError):
        decode_response(serialized_short(496) + b"\x00")


def test_null_trailing_bytes_and_unknown_token_are_rejected():
    with pytest.raises(AppManagerProtocolError):
        decode_response(SERIALIZED_NULL + b"\x00")
    with pytest.raises(AppManagerProtocolError, match="unsupported"):
        decode_response(JAVA_STREAM_HEADER + b"\x71")
