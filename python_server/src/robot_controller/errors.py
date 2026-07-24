"""Exception hierarchy shared by RobotController modules."""

import typing


class ProtocolError(Exception):
    """Base class for protocol processing failures."""


class FrameReadError(ProtocolError):
    """A socket error occurred while receiving part of a frame."""

    def __init__(self, stage, expected_bytes, received_bytes, message=None):
        # type: (str, int, int, typing.Optional[str]) -> None
        self.stage = stage
        self.expected_bytes = expected_bytes
        self.received_bytes = received_bytes
        if message is None:
            message = (
                "Failed to read frame {0}: expected {1} bytes, "
                "received {2}"
            ).format(stage, expected_bytes, received_bytes)
        ProtocolError.__init__(self, message)


class ConnectionClosedError(FrameReadError):
    """The peer closed the connection before a frame part was complete."""

    def __init__(self, stage, expected_bytes, received_bytes):
        # type: (str, int, int) -> None
        message = (
            "Connection closed while reading frame {0}: expected {1} bytes, "
            "received {2}"
        ).format(stage, expected_bytes, received_bytes)
        FrameReadError.__init__(
            self, stage, expected_bytes, received_bytes, message
        )


class FrameTimeoutError(FrameReadError):
    """A socket timeout occurred while receiving part of a frame."""

    def __init__(self, stage, expected_bytes, received_bytes):
        # type: (str, int, int) -> None
        message = (
            "Timed out while reading frame {0}: expected {1} bytes, "
            "received {2}"
        ).format(stage, expected_bytes, received_bytes)
        FrameReadError.__init__(
            self, stage, expected_bytes, received_bytes, message
        )


class FrameLengthError(ProtocolError):
    """Base class for a rejected declared or encoded frame length."""

    def __init__(self, declared_length, message):
        # type: (int, str) -> None
        self.stage = "header"
        self.expected_bytes = 4
        self.received_bytes = 4
        self.declared_length = declared_length
        ProtocolError.__init__(self, message)


class FrameTooLargeError(FrameLengthError):
    """The declared frame length exceeds the caller's configured limit."""

    def __init__(self, declared_length, max_length):
        # type: (int, int) -> None
        self.max_length = max_length
        message = "Frame length {0} exceeds configured maximum {1}".format(
            declared_length, max_length
        )
        FrameLengthError.__init__(self, declared_length, message)


class InvalidFrameLengthError(FrameLengthError):
    """The frame length cannot be represented by legacy v1."""

    def __init__(self, declared_length):
        # type: (int) -> None
        message = "Frame length {0} is invalid for legacy v1".format(
            declared_length
        )
        FrameLengthError.__init__(self, declared_length, message)


class FrameWriteError(ProtocolError):
    """A socket error occurred while sending an encoded frame."""

    def __init__(self, expected_bytes):
        # type: (int) -> None
        self.expected_bytes = expected_bytes
        ProtocolError.__init__(
            self,
            "Failed to send encoded frame of {0} bytes".format(expected_bytes),
        )
