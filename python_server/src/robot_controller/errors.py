"""Exception hierarchy shared by RobotController modules."""

import typing


class ProtocolError(Exception):
    """Base class for protocol processing failures."""


class DecodeError(ProtocolError):
    """Base class for protocol text decoding failures."""


class ValidationError(ProtocolError):
    """Base class for rejected protocol values."""


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


class SessionFrameError(ProtocolError):
    """Base class for a frame failure at a legacy v1 session stage."""

    def __init__(self, stage, frame_error):
        # type: (str, ProtocolError) -> None
        self.stage = stage
        self.frame_error = frame_error
        ProtocolError.__init__(
            self,
            "Legacy v1 {0} frame failed: {1}".format(stage, frame_error),
        )


class CommandFrameError(SessionFrameError):
    """The command frame could not be read."""

    def __init__(self, frame_error):
        # type: (ProtocolError) -> None
        SessionFrameError.__init__(self, "command", frame_error)


class PayloadFrameError(SessionFrameError):
    """The required payload frame could not be read."""

    def __init__(self, frame_error):
        # type: (ProtocolError) -> None
        SessionFrameError.__init__(self, "payload", frame_error)


class ResponseFrameError(SessionFrameError):
    """The response frame could not be sent."""

    def __init__(self, frame_error):
        # type: (ProtocolError) -> None
        SessionFrameError.__init__(self, "response", frame_error)


class CommandDecodeError(DecodeError):
    """Command bytes are not valid strict UTF-8."""

    def __init__(self, command_bytes):
        # type: (bytes) -> None
        self.command_bytes = command_bytes
        DecodeError.__init__(self, "Command is not valid UTF-8")


class EmptyCommandError(ValidationError):
    """The decoded command name is empty."""

    def __init__(self):
        # type: () -> None
        ValidationError.__init__(self, "Command must not be empty")


class UnknownCommandError(ValidationError):
    """The decoded command name is not defined by legacy v1."""

    def __init__(self, command):
        # type: (str) -> None
        self.command = command
        ValidationError.__init__(
            self, "Unknown legacy v1 command: {0!r}".format(command)
        )


class MissingPayloadError(ValidationError):
    """A payload-required command has no payload or an empty payload."""

    def __init__(self, command, frame_error=None):
        # type: (str, typing.Optional[ProtocolError]) -> None
        self.command = command
        self.frame_error = frame_error
        ValidationError.__init__(
            self, "Command {0!r} requires a non-empty payload".format(command)
        )


class ResponseNotAllowedError(ValidationError):
    """A response was requested for a v1 command that has no response."""

    def __init__(self, command):
        # type: (str) -> None
        self.command = command
        ValidationError.__init__(
            self, "Command {0!r} does not allow a v1 response".format(command)
        )


def _summarize_invalid_value(value):
    # type: (typing.Any) -> str
    """Return a bounded description suitable for validation messages."""
    if isinstance(value, dict):
        return "<object with {0} fields>".format(len(value))
    if isinstance(value, (list, tuple)):
        return "<array with {0} elements>".format(len(value))
    rendered = repr(value)
    if len(rendered) > 80:
        return rendered[:77] + "..."
    return rendered


class PayloadDecodeError(DecodeError):
    """A JSON command payload is not valid strict UTF-8."""

    def __init__(self, command):
        # type: (str) -> None
        self.command = command
        DecodeError.__init__(
            self,
            "Payload for command {0!r} is not valid UTF-8".format(command),
        )


class PayloadJsonError(DecodeError):
    """A decoded JSON command payload has invalid JSON syntax."""

    def __init__(self, command):
        # type: (str) -> None
        self.command = command
        DecodeError.__init__(
            self,
            "Payload for command {0!r} is not valid JSON".format(command),
        )


class NonStandardJsonNumberError(PayloadJsonError):
    """A JSON payload contains NaN or an Infinity token."""

    def __init__(self, command, invalid_value):
        # type: (str, str) -> None
        self.command = command
        self.invalid_value = invalid_value
        DecodeError.__init__(
            self,
            "Payload for command {0!r} contains non-standard JSON number "
            "{1!r}".format(command, invalid_value),
        )


class PayloadValidationError(ValidationError):
    """Base class for a rejected decoded JSON payload value."""

    def __init__(self, command, path, invalid_value, expected, message=None):
        # type: (str, str, typing.Any, str, typing.Optional[str]) -> None
        self.command = command
        self.path = path
        self.field = path
        self.invalid_value = invalid_value
        self.expected = expected
        if message is None:
            message = (
                "Invalid value at {0} for command {1!r}: {2}; expected {3}"
            ).format(
                path,
                command,
                _summarize_invalid_value(invalid_value),
                expected,
            )
        ValidationError.__init__(self, message)


class InvalidTopLevelTypeError(PayloadValidationError):
    """A command's JSON top-level value has the wrong type."""


class MissingFieldError(PayloadValidationError):
    """A required JSON field or field group is missing."""


class InvalidFieldTypeError(PayloadValidationError):
    """A JSON field has the wrong type."""


class InvalidFieldValueError(PayloadValidationError):
    """A typed JSON field violates a value constraint."""


class UnknownServoError(PayloadValidationError):
    """A ServoMap key is not present in the selected robot profile."""


class UnknownLedError(PayloadValidationError):
    """A LedMap key is not present in the selected robot profile."""


class ServoRangeError(PayloadValidationError):
    """A servo value is outside its profile range."""


class LedRangeError(PayloadValidationError):
    """An LED value is outside its profile range."""


class EmptyMotionError(PayloadValidationError):
    """A Motion JSON array contains no poses."""


class MotionTooLargeError(PayloadValidationError):
    """A Motion exceeds its configured pose-count or duration limit."""
