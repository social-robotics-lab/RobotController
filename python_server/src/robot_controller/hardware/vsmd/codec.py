"""Pure codec for the verified line-oriented ``vsmd_edison`` protocol."""

import collections
import re

from robot_controller.hardware.vsmd.constants import MAX_ADDRESS, MIN_ADDRESS
from robot_controller.hardware.vsmd.errors import (
    VsmdMalformedBannerError,
    VsmdMalformedResponseError,
    VsmdResponseAddressMismatchError,
    VsmdResponseSizeMismatchError,
    VsmdValidationError,
)


_ServerBannerBase = collections.namedtuple(
    "_ServerBannerBase", ["text", "raw_line"]
)


class ServerBanner(_ServerBannerBase):
    """Validated immutable server banner."""

    __slots__ = ()


_ADDRESS_TOKEN = re.compile(br"^[0-9A-Fa-f]{4}$")
_BYTE_TOKEN = re.compile(br"^[0-9A-Fa-f]{2}$")


def _validate_integer(value, name, minimum, maximum):
    # type: (int, str, int, int) -> int
    if isinstance(value, bool) or not isinstance(value, int):
        raise VsmdValidationError("{0} must be an integer".format(name))
    if value < minimum or value > maximum:
        raise VsmdValidationError(
            "{0} must be between {1} and {2}".format(
                name, minimum, maximum
            )
        )
    return value


def _require_terminated_line(line, error_type):
    # type: (bytes, type) -> bytes
    if not isinstance(line, bytes):
        raise error_type("line must be bytes")
    if not line.endswith(b"\n"):
        raise error_type("line must end with a newline")
    content = line[:-1]
    if content.endswith(b"\r"):
        content = content[:-1]
    return content


def encode_read_request(address, size):
    # type: (int, int) -> bytes
    """Encode byte count ``size`` as lower-case hexadecimal on the wire."""
    _validate_integer(address, "address", MIN_ADDRESS, MAX_ADDRESS)
    _validate_integer(size, "size", 1, MAX_ADDRESS + 1)
    if address + size - 1 > MAX_ADDRESS:
        raise VsmdValidationError("read range exceeds the address space")
    return "R {0:04x} {1:x}\r\n".format(address, size).encode("ascii")


def _normalize_read_response_line(data_line):
    # type: (bytes) -> tuple
    """Return raw content and token content under strict whitespace rules."""
    if not isinstance(data_line, bytes):
        raise VsmdMalformedResponseError("response line must be bytes")
    if data_line.endswith(b"\r\n"):
        raw_content = data_line[:-2]
    elif data_line.endswith(b"\n") or data_line.endswith(b"\r"):
        raise VsmdMalformedResponseError(
            "response terminator must be CRLF when present"
        )
    else:
        raw_content = data_line
    if b"\r" in raw_content or b"\n" in raw_content:
        raise VsmdMalformedResponseError(
            "response line must not contain embedded newlines"
        )
    if not raw_content:
        raise VsmdMalformedResponseError("read response must not be empty")
    if raw_content.startswith(b" "):
        raise VsmdMalformedResponseError(
            "read response must not start with a space"
        )
    if b"\t" in raw_content:
        raise VsmdMalformedResponseError(
            "read response must not contain tabs"
        )
    if raw_content.endswith(b"  "):
        raise VsmdMalformedResponseError(
            "read response permits at most one trailing space"
        )
    token_content = (
        raw_content[:-1] if raw_content.endswith(b" ") else raw_content
    )
    if b"  " in token_content:
        raise VsmdMalformedResponseError(
            "read response fields must use exactly one space"
        )
    return raw_content, token_content


def decode_read_response(data_line, expected_address, expected_size):
    # type: (bytes, int, int) -> bytes
    """Decode exact tokens with zero or one trailing ASCII space."""
    _validate_integer(
        expected_address, "expected_address", MIN_ADDRESS, MAX_ADDRESS
    )
    _validate_integer(expected_size, "expected_size", 1, MAX_ADDRESS + 1)
    raw_content, content = _normalize_read_response_line(data_line)
    tokens = content.split(b" ")
    if not tokens or not tokens[0].startswith(b"#"):
        raise VsmdMalformedResponseError(
            "read response must start with an address token"
        )
    address_token = tokens[0][1:]
    if _ADDRESS_TOKEN.match(address_token) is None:
        raise VsmdMalformedResponseError(
            "read response address must be four hexadecimal digits"
        )
    actual_address = int(address_token, 16)
    byte_tokens = tokens[1:]
    if actual_address != expected_address:
        raise VsmdResponseAddressMismatchError(
            expected_address,
            actual_address,
            expected_size,
            len(byte_tokens),
            raw_content,
        )
    if len(byte_tokens) != expected_size:
        raise VsmdResponseSizeMismatchError(
            expected_address,
            expected_size,
            len(byte_tokens),
            raw_content,
        )
    result = bytearray()
    for token in byte_tokens:
        if _BYTE_TOKEN.match(token) is None:
            raise VsmdMalformedResponseError(
                "read response byte tokens must be two hexadecimal digits"
            )
        result.append(int(token, 16))
    return bytes(result)


def encode_write_request(address, payload):
    # type: (int, bytes) -> bytes
    """Encode the PCAP-verified, space-delimited no-response write line.

    The wire format is ``w aaaa bb cc\r\n``: one ASCII space follows the
    lower-case command, the four-digit lower-case address, and every payload
    byte except the last. Payload bytes are never concatenated without
    separators.
    """
    _validate_integer(address, "address", MIN_ADDRESS, MAX_ADDRESS)
    if not isinstance(payload, bytes):
        raise VsmdValidationError("payload must be bytes")
    if not payload:
        raise VsmdValidationError("payload must not be empty")
    if address + len(payload) - 1 > MAX_ADDRESS:
        raise VsmdValidationError("payload exceeds the address space")
    payload_text = " ".join(
        "{0:02x}".format(value) for value in payload
    )
    return "w {0:04x} {1}\r\n".format(
        address, payload_text
    ).encode("ascii")


def parse_server_banner(line):
    # type: (bytes) -> ServerBanner
    """Validate a complete banner line without consuming later responses."""
    content = _require_terminated_line(line, VsmdMalformedBannerError)
    if not content.startswith(b"#vs-"):
        raise VsmdMalformedBannerError(
            "server banner must start with '#vs-'"
        )
    try:
        text = content.decode("ascii")
    except UnicodeDecodeError as error:
        raise VsmdMalformedBannerError(
            "server banner must contain ASCII"
        ) from error
    return ServerBanner(text, bytes(line))


class VsmdProtocolCodec(object):
    """Stateless facade for dependency injection and discoverable ownership."""

    encode_read_request = staticmethod(encode_read_request)
    decode_read_response = staticmethod(decode_read_response)
    encode_write_request = staticmethod(encode_write_request)
    parse_server_banner = staticmethod(parse_server_banner)
