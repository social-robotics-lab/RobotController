"""Golden vectors and strict response validation for the VSMD codec."""

import pytest

from robot_controller.hardware.vsmd.codec import (
    VsmdProtocolCodec,
    decode_read_response,
    encode_read_request,
    encode_write_request,
    parse_server_banner,
)
from robot_controller.hardware.vsmd.errors import (
    VsmdMalformedBannerError,
    VsmdMalformedResponseError,
    VsmdResponseAddressMismatchError,
    VsmdResponseSizeMismatchError,
    VsmdValidationError,
)


def test_read_request_golden_vector():
    assert encode_read_request(0x0124, 2) == b"R 0124 2\r\n"
    assert encode_read_request(0x0E80, 64) == b"R 0e80 40\r\n"
    assert encode_read_request(0x1000, 10) == b"R 1000 a\r\n"
    assert (
        VsmdProtocolCodec.encode_read_request(0x0E80, 64)
        == b"R 0e80 40\r\n"
    )


@pytest.mark.parametrize(
    "address,payload,expected",
    [
        (0x0124, b"\x9c\x0c", b"w 0124 9c 0c\r\n"),
        (0x0124, b"\x8a\x00", b"w 0124 8a 00\r\n"),
        (0x0A9C, b"\x10\x00", b"w 0a9c 10 00\r\n"),
        (0x0B9C, b"\xf6\x01", b"w 0b9c f6 01\r\n"),
        (0x01F6, b"\x00\x00", b"w 01f6 00 00\r\n"),
        (0x01F6, b"\x0b\x00", b"w 01f6 0b 00\r\n"),
        (0x0A9C, b"\x00\x00", b"w 0a9c 00 00\r\n"),
        (0x0B9C, b"\xf4\x01", b"w 0b9c f4 01\r\n"),
        (0x0000, b"\xff", b"w 0000 ff\r\n"),
        (0xFFFF, b"\x00", b"w ffff 00\r\n"),
        (0x0020, b"\x00\xff\x01", b"w 0020 00 ff 01\r\n"),
    ],
)
def test_write_request_matches_pcap_golden_vectors(
    address, payload, expected
):
    assert encode_write_request(address, payload) == expected
    assert VsmdProtocolCodec.encode_write_request(address, payload) == expected


def test_write_request_has_exact_spaces_and_crlf():
    encoded = encode_write_request(0x0124, b"\x00\xff\x01")
    assert encoded == b"w 0124 00 ff 01\r\n"
    assert not encoded.startswith(b" ")
    assert not encoded.endswith(b" \r\n")
    assert b"  " not in encoded
    assert encoded.endswith(b"\r\n")
    assert not encoded.endswith(b"\n\n")


def test_server_banner_is_validated_and_preserved():
    line = b"#vs-rc020 (Oct 31 2018 14:44:11)\r\n"
    banner = parse_server_banner(line)
    assert banner.text == "#vs-rc020 (Oct 31 2018 14:44:11)"
    assert banner.raw_line == line


@pytest.mark.parametrize(
    "line",
    [b"vs-rc020\r\n", b"#VS-rc020\r\n", b"#vs-rc020", b"#vs-\xff\r\n"],
)
def test_invalid_server_banner_is_rejected(line):
    with pytest.raises(VsmdMalformedBannerError):
        parse_server_banner(line)


@pytest.mark.parametrize(
    "line", [b"#0e80 00 a5 FF \r\n", b"#0E80 0A A5 ff "]
)
def test_lower_and_upper_case_hex_responses_are_accepted(line):
    assert decode_read_response(line, 0x0E80, 3) in (
        b"\x00\xa5\xff",
        b"\x0a\xa5\xff",
    )


@pytest.mark.parametrize(
    "line", [b"#0124 8a 00 ", b"#0124 8a 00"]
)
def test_read_response_allows_zero_or_one_trailing_ascii_space(line):
    assert decode_read_response(line, 0x0124, 2) == b"\x8a\x00"


@pytest.mark.parametrize(
    "line",
    [
        b" #0124 8a 00 ",
        b"#0124  8a 00 ",
        b"#0124\t8a\t00 ",
        b"#0124 8a 00  ",
        b"#0124 8a 000 ",
        b"#0124 8a 00\n",
        b"#0124 8a 00\r",
    ],
)
def test_read_response_rejects_invalid_whitespace_and_token_width(line):
    with pytest.raises(VsmdMalformedResponseError):
        decode_read_response(line, 0x0124, 2)


def test_sixty_four_byte_response_with_real_daemon_trailing_space():
    payload = bytes(bytearray(range(64)))
    response = (
        "#0e80 {0} \r\n".format(
            " ".join("{0:02x}".format(value) for value in payload)
        ).encode("ascii")
    )
    assert decode_read_response(response, 0x0E80, 64) == payload


@pytest.mark.parametrize("address", [-1, 0x10000, True, 1.5, "1"])
def test_invalid_address_is_rejected(address):
    with pytest.raises(VsmdValidationError):
        encode_read_request(address, 1)


@pytest.mark.parametrize("size", [0, -1, True, 1.5, 0x10001])
def test_invalid_size_is_rejected(size):
    with pytest.raises(VsmdValidationError):
        encode_read_request(0, size)


def test_read_cannot_cross_memory_boundary():
    with pytest.raises(VsmdValidationError):
        encode_read_request(0xFFFF, 2)


def test_empty_or_non_bytes_write_payload_is_rejected():
    with pytest.raises(VsmdValidationError):
        encode_write_request(0, b"")
    with pytest.raises(VsmdValidationError):
        encode_write_request(0, bytearray(b"x"))


@pytest.mark.parametrize("address", [-1, 0x10000, True, 1.5, "1"])
def test_write_rejects_invalid_address(address):
    with pytest.raises(VsmdValidationError):
        encode_write_request(address, b"\x00")


def test_write_cannot_cross_memory_boundary():
    with pytest.raises(VsmdValidationError):
        encode_write_request(0xFFFF, b"\x00\x01")


def test_response_address_mismatch_is_distinct():
    with pytest.raises(VsmdResponseAddressMismatchError):
        decode_read_response(b"#0002 00 \r\n", 1, 1)


@pytest.mark.parametrize(
    "line", [b"#0001 \r\n", b"#0001 00 01 \r\n"]
)
def test_response_byte_count_must_match_exactly(line):
    with pytest.raises(VsmdResponseSizeMismatchError):
        decode_read_response(line, 1, 1)


@pytest.mark.parametrize(
    "line",
    [
        b"",
        b"\r\n",
        b"#0001 0g \r\n",
        b"#0001 0 \r\n",
        b"#001 00 \r\n",
        b"#vs-rc020 \r\n",
    ],
)
def test_malformed_or_banner_response_is_rejected(line):
    with pytest.raises(VsmdMalformedResponseError):
        decode_read_response(line, 1, 1)


def test_size_mismatch_contains_bounded_request_diagnostics():
    response = b"#0124 8a 00 ff "
    with pytest.raises(VsmdResponseSizeMismatchError) as caught:
        decode_read_response(response, 0x0124, 2)
    error = caught.value
    assert error.expected_address == 0x0124
    assert error.requested_bytes == 2
    assert error.received_bytes == 3
    assert error.raw_response == response
    assert not error.raw_response_truncated
    assert "address=0x0124" in str(error)
    assert "requested_bytes=2" in str(error)
    assert "received_bytes=3" in str(error)
    assert "raw_response=b'#0124 8a 00 ff '" in str(error)


def test_long_size_mismatch_diagnostic_is_truncated():
    response = (
        b"#0124 " + b"00 " * 100
    )
    with pytest.raises(VsmdResponseSizeMismatchError) as caught:
        decode_read_response(response, 0x0124, 2)
    assert caught.value.raw_response_truncated
    assert len(caught.value.raw_response) == 160
    assert str(caught.value).endswith("...")
