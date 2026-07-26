"""Tests for the specification-injected pure packet codec."""

import pytest

from robot_controller.errors import (
    FutabaChecksumMismatchError,
    InvalidFutabaPacketError,
    UnexpectedServoIdError,
)
from robot_controller.hardware.futaba_codec import (
    FutabaPacket,
    FutabaPacketCodec,
    FutabaPacketDefinition,
)


def sample_checksum(content):
    """Test-only checksum, not a verified hardware checksum."""
    value = 0
    for item in content:
        value ^= item
    return value


@pytest.fixture
def codec():
    # This header and checksum exist only as a structural test definition.
    return FutabaPacketCodec(
        FutabaPacketDefinition(b"\xaa\x55", sample_checksum)
    )


def test_encode_matches_explicit_expected_bytes(codec):
    packet = FutabaPacket(1, 2, 3, 2, 1, b"\x10\x20")
    assert codec.encode(packet) == b"\xaa\x55\x01\x02\x03\x01\x02\x10\x20\x33"


def test_decode_matches_explicit_packet_fields(codec):
    encoded = b"\xaa\x55\x01\x02\x03\x01\x02\x10\x20\x33"
    assert codec.decode(encoded, expected_servo_id=1) == FutabaPacket(
        1, 2, 3, 2, 1, b"\x10\x20"
    )


def test_empty_data_is_supported_when_declared_empty(codec):
    encoded = codec.encode(FutabaPacket(1, 2, 3, 0, 4, b""))
    assert codec.decode(encoded).data == b""


def test_maximum_declared_data_dimensions(codec):
    data = b"x" * (255 * 255)
    encoded = codec.encode(FutabaPacket(255, 255, 255, 255, 255, data))
    assert codec.decode(encoded).data == data


@pytest.mark.parametrize(
    "encoded",
    [
        b"",
        b"\xaa\x55",
        b"\xaa\x55\x01\x02\x03\x01",
    ],
)
def test_partial_packet_is_rejected(codec, encoded):
    with pytest.raises(InvalidFutabaPacketError):
        codec.decode(encoded)


def test_bad_header_is_rejected(codec):
    with pytest.raises(InvalidFutabaPacketError):
        codec.decode(b"\x00\x55\x01\x02\x03\x00\x00\x00")


def test_bad_checksum_is_rejected(codec):
    packet = bytearray(codec.encode(FutabaPacket(1, 2, 3, 1, 1, b"x")))
    packet[-1] ^= 1
    with pytest.raises(FutabaChecksumMismatchError):
        codec.decode(bytes(packet))


def test_bad_data_length_is_rejected_on_encode(codec):
    with pytest.raises(InvalidFutabaPacketError):
        codec.encode(FutabaPacket(1, 2, 3, 2, 1, b"x"))


def test_bad_data_length_is_rejected_on_decode(codec):
    content = b"\x01\x02\x03\x01\x02x"
    encoded = b"\xaa\x55" + content + bytes(bytearray([sample_checksum(content)]))
    with pytest.raises(InvalidFutabaPacketError):
        codec.decode(encoded)


def test_unexpected_servo_id_is_rejected(codec):
    encoded = codec.encode(FutabaPacket(2, 0, 0, 0, 0, b""))
    with pytest.raises(UnexpectedServoIdError) as caught:
        codec.decode(encoded, expected_servo_id=1)
    assert caught.value.expected_id == 1
    assert caught.value.actual_id == 2


@pytest.mark.parametrize("value", [True, False, 1.0, "1"])
def test_non_integer_byte_fields_are_rejected(codec, value):
    with pytest.raises(TypeError):
        codec.encode(FutabaPacket(value, 0, 0, 0, 0, b""))


@pytest.mark.parametrize("value", [-1, 256])
def test_out_of_range_byte_fields_are_rejected(codec, value):
    with pytest.raises(ValueError):
        codec.encode(FutabaPacket(value, 0, 0, 0, 0, b""))


def test_data_must_be_bytes(codec):
    with pytest.raises(TypeError):
        codec.encode(FutabaPacket(1, 0, 0, 1, 1, bytearray(b"x")))


def test_definition_has_no_implicit_hardware_defaults():
    with pytest.raises(TypeError):
        FutabaPacketDefinition(b"", sample_checksum)
    with pytest.raises(TypeError):
        FutabaPacketDefinition(b"\xaa", None)


def test_invalid_checksum_result_is_rejected():
    codec = FutabaPacketCodec(
        FutabaPacketDefinition(b"x", lambda content: True)
    )
    with pytest.raises(TypeError):
        codec.encode(FutabaPacket(1, 0, 0, 0, 0, b""))
