"""VSMD-specific exceptions integrated with the hardware error hierarchy."""

import typing

from robot_controller.errors import HardwareProbeError


MAX_RAW_RESPONSE_DIAGNOSTIC_BYTES = 160


def _bounded_raw_response(raw_response):
    # type: (bytes) -> typing.Tuple[bytes, bool]
    """Return a bounded byte snapshot and whether it was truncated."""
    snapshot = bytes(raw_response)
    if len(snapshot) <= MAX_RAW_RESPONSE_DIAGNOSTIC_BYTES:
        return snapshot, False
    return snapshot[:MAX_RAW_RESPONSE_DIAGNOSTIC_BYTES], True


class VsmdError(HardwareProbeError):
    """Base class for failures while communicating with ``vsmd_edison``."""


class VsmdValidationError(VsmdError):
    """A caller supplied a value outside the VSMD protocol domain."""


class VsmdProtocolError(VsmdError):
    """The daemon sent data that violates the verified wire protocol."""


class VsmdMalformedBannerError(VsmdProtocolError):
    """The connection banner is missing, unterminated, or has a bad prefix."""


class VsmdMalformedResponseError(VsmdProtocolError):
    """A memory-read response is syntactically malformed."""


class VsmdResponseAddressMismatchError(VsmdMalformedResponseError):
    """A response identifies an address other than the requested address."""

    def __init__(
        self,
        expected_address,
        actual_address,
        expected_size,
        received_bytes,
        raw_response,
    ):
        # type: (int, int, int, int, bytes) -> None
        self.expected_address = expected_address
        self.actual_address = actual_address
        self.requested_bytes = expected_size
        self.received_bytes = received_bytes
        self.raw_response, self.raw_response_truncated = (
            _bounded_raw_response(raw_response)
        )
        suffix = "..." if self.raw_response_truncated else ""
        VsmdMalformedResponseError.__init__(
            self,
            (
                "VSMD read response address mismatch: address=0x{0:04x} "
                "actual_address=0x{1:04x} requested_bytes={2} "
                "received_bytes={3} raw_response={4!r}{5}"
            ).format(
                expected_address,
                actual_address,
                expected_size,
                received_bytes,
                self.raw_response,
                suffix,
            ),
        )


class VsmdResponseSizeMismatchError(VsmdMalformedResponseError):
    """A response contains more or fewer bytes than requested."""

    def __init__(
        self, expected_address, expected_size, received_bytes, raw_response
    ):
        # type: (int, int, int, bytes) -> None
        self.expected_address = expected_address
        self.requested_bytes = expected_size
        self.received_bytes = received_bytes
        self.raw_response, self.raw_response_truncated = (
            _bounded_raw_response(raw_response)
        )
        suffix = "..." if self.raw_response_truncated else ""
        VsmdMalformedResponseError.__init__(
            self,
            (
                "VSMD read response size mismatch: address=0x{0:04x} "
                "requested_bytes={1} received_bytes={2} "
                "raw_response={3!r}{4}"
            ).format(
                expected_address,
                expected_size,
                received_bytes,
                self.raw_response,
                suffix,
            ),
        )


class VsmdTransportError(VsmdError):
    """Base class for bounded TCP transport failures."""


class VsmdTransportStateError(VsmdTransportError):
    """An operation was attempted outside a connected transport lifetime."""


class VsmdConnectError(VsmdTransportError):
    """The TCP connection or initial banner exchange failed."""


class VsmdTransportTimeoutError(VsmdTransportError):
    """A bounded connect, read, or write operation timed out."""

    def __init__(self, operation):
        # type: (str) -> None
        self.operation = operation
        VsmdTransportError.__init__(
            self, "VSMD transport {0} timed out".format(operation)
        )


class VsmdUnexpectedEofError(VsmdTransportError):
    """The daemon closed a connection before a complete line arrived."""


class VsmdLineTooLongError(VsmdTransportError):
    """An unterminated or complete daemon line exceeded the configured bound."""


class VsmdWriteOutcomeUnknownError(VsmdTransportError):
    """A write failed after submission may have begun and must not be retried."""


class VsmdLedError(VsmdError):
    """Base class for fail-closed Sota mouth-LED domain failures."""


class VsmdLedLockUnavailableError(VsmdLedError):
    """The verified InterpLockerClient protocol is unavailable."""


class VsmdMouthLedStateError(VsmdLedError):
    """A mouth-LED operation is invalid for the controller state."""


class VsmdUnexpectedMouthSelectorError(VsmdLedError):
    """The mouth selector has an unrecognized value and was not modified."""


class VsmdMouthLedCleanupError(VsmdLedError):
    """A mouth-LED operation and its mandatory cleanup both failed."""

    def __init__(self, operation_error, cleanup_error):
        # type: (BaseException, BaseException) -> None
        self.operation_error = operation_error
        self.cleanup_error = cleanup_error
        VsmdLedError.__init__(
            self,
            (
                "mouth LED operation failed with {0}; cleanup failed with "
                "{1}"
            ).format(
                type(operation_error).__name__,
                type(cleanup_error).__name__,
            ),
        )


class AppManagerError(VsmdError):
    """Base class for SotaAppManager interpolation-lock failures."""


class AppManagerConnectionError(AppManagerError):
    """A request could not connect before any command bytes were sent."""


class AppManagerTimeoutError(AppManagerError):
    """A timeout occurred before request submission began."""


class AppManagerProtocolError(AppManagerError):
    """SotaAppManager sent bytes outside the verified protocol subset."""


class AppManagerUnexpectedResponseError(AppManagerError):
    """A valid serialized value was not valid for the current operation."""


class AppManagerLockRejectedError(AppManagerError):
    """SotaAppManager explicitly returned ``NG`` for a lock request."""


class AppManagerTimerAddressError(AppManagerError):
    """A converted lock key had no valid interpolation timer address."""


class AppManagerUnlockError(AppManagerError):
    """An unlock request was explicitly rejected or had the wrong value."""


class AppManagerOutcomeUnknownError(AppManagerError):
    """A submitted request may have taken effect and must not be retried."""
