"""Byte-oriented memory client layered on the VSMD transport and codec."""

import abc

from robot_controller.hardware.vsmd.codec import (
    decode_read_response,
    encode_read_request,
    encode_write_request,
)


class VsmdMemoryAccess(abc.ABC):
    """Byte-level memory port used by typed and domain layers."""

    @abc.abstractmethod
    def read_bytes(self, address, size):
        # type: (int, int) -> bytes
        """Read an exact byte range."""
        raise NotImplementedError

    @abc.abstractmethod
    def write_bytes(self, address, payload):
        # type: (int, bytes) -> None
        """Write one non-empty byte range without waiting for an ACK."""
        raise NotImplementedError


class VsmdMemoryClient(VsmdMemoryAccess):
    """Issue validated memory operations over a connected transport."""

    def __init__(self, transport):
        # type: (object) -> None
        self._transport = transport

    def read_bytes(self, address, size):
        # type: (int, int) -> bytes
        request = encode_read_request(address, size)
        self._transport.send(request)
        response_line = self._transport.read_line()
        return decode_read_response(response_line, address, size)

    def write_bytes(self, address, payload):
        # type: (int, bytes) -> None
        self._transport.send(encode_write_request(address, payload))

