"""Pure packet encoding and decoding with an injected verified definition.

The repository currently contains no Futaba manual, RobotLib implementation,
or packet test vector.  This module therefore deliberately supplies no default
header, checksum algorithm, read address, or flags.  A caller must construct a
``FutabaPacketDefinition`` from separately verified material before bytes can
be encoded or decoded for hardware.
"""

import collections
import typing

from robot_controller.errors import (
    FutabaChecksumMismatchError,
    InvalidFutabaPacketError,
    UnexpectedServoIdError,
)


_FutabaPacketBase = collections.namedtuple(
    "_FutabaPacketBase",
    [
        "servo_id",
        "flags",
        "address",
        "element_length",
        "element_count",
        "data",
    ],
)


class FutabaPacket(_FutabaPacketBase):
    """Immutable logical packet fields, excluding header and checksum."""

    __slots__ = ()


class FutabaPacketDefinition(object):
    """A packet envelope backed by externally verified constants.

    ``checksum`` receives all bytes after the header and before the checksum,
    and must return one byte as an integer.  No checksum implementation is
    built in because none is verified by this repository.
    """

    def __init__(self, header, checksum):
        # type: (bytes, typing.Callable[[bytes], int]) -> None
        if not isinstance(header, bytes) or not header:
            raise TypeError("header must be non-empty bytes")
        if not callable(checksum):
            raise TypeError("checksum must be callable")
        self._header = bytes(header)
        self._checksum = checksum

    @property
    def header(self):
        # type: () -> bytes
        return self._header

    def calculate_checksum(self, content):
        # type: (bytes) -> int
        value = self._checksum(content)
        _validate_byte(value, "checksum")
        return value


class FutabaPacketCodec(object):
    """Encode and validate the field layout named by a verified definition."""

    def __init__(self, definition):
        # type: (FutabaPacketDefinition) -> None
        if not isinstance(definition, FutabaPacketDefinition):
            raise TypeError("definition must be FutabaPacketDefinition")
        self._definition = definition

    def encode(self, packet):
        # type: (FutabaPacket) -> bytes
        """Encode without performing I/O or applying command semantics."""
        _validate_packet(packet)
        content = bytes(
            bytearray(
                [
                    packet.servo_id,
                    packet.flags,
                    packet.address,
                    packet.element_count,
                    packet.element_length,
                ]
            )
        ) + packet.data
        checksum = self._definition.calculate_checksum(content)
        return self._definition.header + content + bytes(bytearray([checksum]))

    def decode(self, encoded, expected_servo_id=None):
        # type: (bytes, typing.Optional[int]) -> FutabaPacket
        """Decode and validate one complete packet."""
        if not isinstance(encoded, bytes):
            raise TypeError("encoded packet must be bytes")
        header = self._definition.header
        minimum = len(header) + 6
        if len(encoded) < minimum:
            raise InvalidFutabaPacketError("Packet is shorter than its fields")
        if not encoded.startswith(header):
            raise InvalidFutabaPacketError("Packet header does not match")

        content = encoded[len(header):-1]
        received_checksum = encoded[-1]
        expected_checksum = self._definition.calculate_checksum(content)
        if received_checksum != expected_checksum:
            raise FutabaChecksumMismatchError("Packet checksum mismatch")

        servo_id = content[0]
        if expected_servo_id is not None:
            _validate_byte(expected_servo_id, "expected_servo_id")
            if servo_id != expected_servo_id:
                raise UnexpectedServoIdError(expected_servo_id, servo_id)

        element_count = content[3]
        element_length = content[4]
        data = bytes(content[5:])
        expected_data_length = element_length * element_count
        if len(data) != expected_data_length:
            raise InvalidFutabaPacketError(
                "Packet data length does not match length and count"
            )
        packet = FutabaPacket(
            servo_id,
            content[1],
            content[2],
            element_length,
            element_count,
            data,
        )
        _validate_packet(packet)
        return packet


def _validate_packet(packet):
    # type: (FutabaPacket) -> None
    if not isinstance(packet, FutabaPacket):
        raise TypeError("packet must be FutabaPacket")
    _validate_byte(packet.servo_id, "servo_id")
    _validate_byte(packet.flags, "flags")
    _validate_byte(packet.address, "address")
    _validate_byte(packet.element_length, "element_length")
    _validate_byte(packet.element_count, "element_count")
    if not isinstance(packet.data, bytes):
        raise TypeError("data must be bytes")
    if len(packet.data) != packet.element_length * packet.element_count:
        raise InvalidFutabaPacketError(
            "Packet data length does not match length and count"
        )


def _validate_byte(value, field):
    # type: (int, str) -> None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("{0} must be an integer byte".format(field))
    if value < 0 or value > 255:
        raise ValueError("{0} must be between 0 and 255".format(field))
