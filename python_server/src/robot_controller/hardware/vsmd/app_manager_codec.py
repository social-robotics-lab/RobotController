"""Strict codec for the verified SotaAppManager lock protocol subset."""

import collections
import json
import struct
import typing

from robot_controller.hardware.vsmd.errors import (
    AppManagerProtocolError,
    AppManagerUnexpectedResponseError,
    VsmdValidationError,
)


JAVA_STREAM_HEADER = b"\xac\xed\x00\x05"
TC_NULL = 0x70
TC_OBJECT = 0x73
TC_STRING = 0x74

INTERP_LOCK_COMMAND = "INTERP_LOCK"
INTERP_CONVERT_COMMAND = "INTERP_CNV_KEY_2_ADDR"
INTERP_UNLOCK_COMMAND = "INTERP_UNLOCK"

APP_MANAGER_RESPONSE_OK = "OK"
APP_MANAGER_RESPONSE_NG = "NG"

SERIALIZED_OK = (
    JAVA_STREAM_HEADER
    + b"\x74\x00\x02"
    + APP_MANAGER_RESPONSE_OK.encode("ascii")
)
SERIALIZED_NG = (
    JAVA_STREAM_HEADER
    + b"\x74\x00\x02"
    + APP_MANAGER_RESPONSE_NG.encode("ascii")
)
SERIALIZED_NULL = JAVA_STREAM_HEADER + b"\x70"

JAVA_SHORT_SERIALIZATION_PREFIX = bytes.fromhex(
    "aced00057372000f6a6176612e6c616e672e53686f7274"
    "684d37133460da5202000153000576616c756578720010"
    "6a6176612e6c616e672e4e756d62657286ac951d0b94e0"
    "8b0200007870"
)
JAVA_SHORT_SERIALIZED_LENGTH = len(JAVA_SHORT_SERIALIZATION_PREFIX) + 2


def _validate_key(key):
    # type: (str) -> str
    if not isinstance(key, str) or not key:
        raise VsmdValidationError("AppManager lock key must be non-empty")
    try:
        key.encode("ascii")
    except UnicodeEncodeError as error:
        raise VsmdValidationError(
            "AppManager lock key must contain ASCII only"
        ) from error
    return key


def validate_led_ids(led_ids):
    # type: (typing.Sequence[int]) -> typing.Tuple[int, ...]
    """Return immutable, validated LED IDs in caller-supplied order."""
    if isinstance(led_ids, (str, bytes)):
        raise VsmdValidationError("LED IDs must be a non-empty sequence")
    try:
        result = tuple(led_ids)
    except TypeError as error:
        raise VsmdValidationError(
            "LED IDs must be a non-empty sequence"
        ) from error
    if not result:
        raise VsmdValidationError("LED IDs must not be empty")
    seen = set()
    for led_id in result:
        if isinstance(led_id, bool) or not isinstance(led_id, int):
            raise VsmdValidationError("each LED ID must be an integer")
        if led_id < 0 or led_id > 31:
            raise VsmdValidationError("each LED ID must be between 0 and 31")
        if led_id in seen:
            raise VsmdValidationError("duplicate LED IDs are not allowed")
        seen.add(led_id)
    return result


def _compact_json(value):
    # type: (typing.Any) -> str
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _encode_outer(command, inner):
    # type: (str, collections.OrderedDict) -> bytes
    outer = collections.OrderedDict()
    outer["cmd"] = command
    outer["subjson"] = _compact_json(inner)
    return _compact_json(outer).encode("ascii")


def _encode_led_request(command, key, led_ids):
    # type: (str, str, typing.Sequence[int]) -> bytes
    validated_key = _validate_key(key)
    validated_ids = validate_led_ids(led_ids)
    inner = collections.OrderedDict()
    inner["key"] = validated_key
    inner["ids"] = list(validated_ids)
    inner["isServo"] = False
    return _encode_outer(command, inner)


def encode_lock_request(key, led_ids):
    # type: (str, typing.Sequence[int]) -> bytes
    """Encode compact ``INTERP_LOCK`` JSON without the transport LF."""
    return _encode_led_request(INTERP_LOCK_COMMAND, key, led_ids)


def encode_convert_request(key):
    # type: (str) -> bytes
    """Encode compact timer-address lookup JSON without the transport LF."""
    inner = collections.OrderedDict()
    inner["key"] = _validate_key(key)
    return _encode_outer(INTERP_CONVERT_COMMAND, inner)


def encode_unlock_request(key, led_ids):
    # type: (str, typing.Sequence[int]) -> bytes
    """Encode compact ``INTERP_UNLOCK`` JSON without the transport LF."""
    return _encode_led_request(INTERP_UNLOCK_COMMAND, key, led_ids)


def decode_response(serialized):
    # type: (bytes) -> typing.Union[str, int, None]
    """Decode only ``OK``, ``NG``, ``null``, or verified ``Short`` bytes."""
    if not isinstance(serialized, bytes):
        raise AppManagerProtocolError("serialized response must be bytes")
    if len(serialized) < len(JAVA_STREAM_HEADER):
        raise AppManagerProtocolError("truncated Java stream header")
    if serialized[:2] != JAVA_STREAM_HEADER[:2]:
        raise AppManagerProtocolError("invalid Java stream magic")
    if serialized[2:4] != JAVA_STREAM_HEADER[2:4]:
        raise AppManagerProtocolError("invalid Java stream version")
    body = serialized[4:]
    if not body:
        raise AppManagerProtocolError("missing Java serialization token")

    token = body[0]
    if token == TC_NULL:
        if len(body) != 1:
            raise AppManagerProtocolError(
                "serialized null has trailing bytes"
            )
        return None

    if token == TC_STRING:
        if len(body) < 3:
            raise AppManagerProtocolError("truncated serialized String")
        string_length = struct.unpack(">H", body[1:3])[0]
        expected_length = 3 + string_length
        if len(body) < expected_length:
            raise AppManagerProtocolError("truncated serialized String")
        if len(body) > expected_length:
            raise AppManagerProtocolError(
                "serialized String has trailing bytes"
            )
        value_bytes = body[3:]
        if value_bytes == APP_MANAGER_RESPONSE_OK.encode("ascii"):
            return APP_MANAGER_RESPONSE_OK
        if value_bytes == APP_MANAGER_RESPONSE_NG.encode("ascii"):
            return APP_MANAGER_RESPONSE_NG
        raise AppManagerUnexpectedResponseError(
            "unexpected serialized String response"
        )

    if token == TC_OBJECT:
        if len(serialized) != JAVA_SHORT_SERIALIZED_LENGTH:
            raise AppManagerProtocolError(
                "serialized Short must be exactly {0} bytes".format(
                    JAVA_SHORT_SERIALIZED_LENGTH
                )
            )
        if not serialized.startswith(JAVA_SHORT_SERIALIZATION_PREFIX):
            raise AppManagerProtocolError(
                "unverified java.lang.Short class descriptor"
            )
        return struct.unpack(">h", serialized[-2:])[0]

    raise AppManagerProtocolError(
        "unsupported Java serialization token 0x{0:02x}".format(token)
    )


class AppManagerProtocolCodec(object):
    """Stateless request and response codec facade."""

    encode_lock_request = staticmethod(encode_lock_request)
    encode_convert_request = staticmethod(encode_convert_request)
    encode_unlock_request = staticmethod(encode_unlock_request)
    decode_response = staticmethod(decode_response)
