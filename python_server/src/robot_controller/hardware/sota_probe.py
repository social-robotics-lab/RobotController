"""Fail-closed, read-only Sota capability-probe orchestration."""

import abc
import collections
import math
import typing

from robot_controller.errors import (
    HardwareProbeError,
    UnverifiedHardwareSpecificationError,
    UnsafeProbeOperationError,
)
from robot_controller.hardware.transport import SotaTransport


_ProbeConfigBase = collections.namedtuple(
    "_ProbeConfigBase", ["device", "baud_rate", "servo_ids", "read_timeout"]
)


class SotaProbeConfig(_ProbeConfigBase):
    """Immutable explicit probe selection."""

    __slots__ = ()

    def __new__(cls, device, baud_rate, servo_ids, read_timeout):
        # type: (str, int, typing.Iterable[int], float) -> SotaProbeConfig
        if not isinstance(device, str) or not device.strip():
            raise ValueError("device must be a non-empty string")
        if (
            isinstance(baud_rate, bool)
            or not isinstance(baud_rate, int)
            or baud_rate <= 0
        ):
            raise ValueError("baud_rate must be a positive integer")
        ids = tuple(servo_ids)
        if not ids:
            raise ValueError("servo_ids must not be empty")
        seen = set()
        for servo_id in ids:
            if isinstance(servo_id, bool) or not isinstance(servo_id, int):
                raise ValueError("servo IDs must be integers")
            if servo_id < 0 or servo_id > 255:
                raise ValueError("servo IDs must be byte values")
            if servo_id in seen:
                raise ValueError("servo IDs must not contain duplicates")
            seen.add(servo_id)
        if (
            isinstance(read_timeout, bool)
            or not isinstance(read_timeout, (int, float))
            or not math.isfinite(read_timeout)
            or read_timeout <= 0
        ):
            raise ValueError("read_timeout must be a positive finite number")
        return _ProbeConfigBase.__new__(
            cls, device, baud_rate, ids, read_timeout
        )


_ReadOnlyRequestBase = collections.namedtuple(
    "_ReadOnlyRequestBase", ["operation", "packet", "response_size"]
)


class ReadOnlyRequest(_ReadOnlyRequestBase):
    """One verified read request and its exact expected response size."""

    __slots__ = ()

    def __new__(cls, operation, packet, response_size):
        # type: (str, bytes, int) -> ReadOnlyRequest
        if operation not in ("read_model",):
            raise UnsafeProbeOperationError(
                "Probe operation is not an approved read-only operation"
            )
        if not isinstance(packet, bytes) or not packet:
            raise ValueError("read request packet must be non-empty bytes")
        if (
            isinstance(response_size, bool)
            or not isinstance(response_size, int)
            or response_size <= 0
        ):
            raise ValueError("response_size must be a positive integer")
        return _ReadOnlyRequestBase.__new__(
            cls, operation, bytes(packet), response_size
        )


_ProbeResultBase = collections.namedtuple(
    "_ProbeResultBase",
    [
        "servo_id",
        "responded",
        "model_identifier",
        "supported",
        "error_type",
        "raw_response",
    ],
)


class ProbeResult(_ProbeResultBase):
    """Bounded immutable result for one explicitly selected servo."""

    __slots__ = ()


class ReadOnlyProbeProtocol(abc.ABC):
    """Verified model-query packet policy injected into the probe."""

    @abc.abstractmethod
    def ensure_verified(self):
        # type: () -> None
        """Reject use if the protocol values lack a verified source."""

    @abc.abstractmethod
    def build_model_query(self, servo_id):
        # type: (int) -> ReadOnlyRequest
        """Build only a read-model request."""

    @abc.abstractmethod
    def decode_model_response(self, response, expected_servo_id):
        # type: (bytes, int) -> int
        """Validate a response and return its model identifier."""

    @abc.abstractmethod
    def is_supported_model(self, model_identifier):
        # type: (int) -> bool
        """Return whether a model is in the verified allowlist."""


class UnverifiedFutabaReadOnlyProtocol(ReadOnlyProbeProtocol):
    """Repository default: no hardware bytes until a manual is verified."""

    def ensure_verified(self):
        # type: () -> None
        raise UnverifiedHardwareSpecificationError(
            "No verified Futaba read packet specification is available"
        )

    def build_model_query(self, servo_id):
        # type: (int) -> ReadOnlyRequest
        self.ensure_verified()
        raise AssertionError("unreachable")

    def decode_model_response(self, response, expected_servo_id):
        # type: (bytes, int) -> int
        self.ensure_verified()
        raise AssertionError("unreachable")

    def is_supported_model(self, model_identifier):
        # type: (int) -> bool
        return False


class SotaCapabilityProbe(object):
    """Execute an explicitly selected sequence of verified model reads."""

    def __init__(self, transport, protocol):
        # type: (SotaTransport, ReadOnlyProbeProtocol) -> None
        if not isinstance(transport, SotaTransport):
            raise TypeError("transport must implement SotaTransport")
        if not isinstance(protocol, ReadOnlyProbeProtocol):
            raise TypeError("protocol must implement ReadOnlyProbeProtocol")
        self._transport = transport
        self._protocol = protocol

    def run(self, config, execute_read_only=False, show_raw=False):
        # type: (SotaProbeConfig, bool, bool) -> typing.Tuple[ProbeResult, ...]
        """Return a dry-run plan, or execute only verified model reads."""
        if not isinstance(config, SotaProbeConfig):
            raise TypeError("config must be SotaProbeConfig")
        if not execute_read_only:
            return tuple(
                ProbeResult(servo_id, False, None, None, None, None)
                for servo_id in config.servo_ids
            )

        # This check intentionally occurs before opening the device.
        self._protocol.ensure_verified()
        results = []
        with self._transport:
            for servo_id in config.servo_ids:
                raw_response = None
                try:
                    request = self._protocol.build_model_query(servo_id)
                    if request.operation != "read_model":
                        raise UnsafeProbeOperationError(
                            "Only model reads are permitted"
                        )
                    self._transport.write(request.packet)
                    response = self._transport.read_exact(
                        request.response_size, config.read_timeout
                    )
                    model_identifier = self._protocol.decode_model_response(
                        response, servo_id
                    )
                    if show_raw:
                        raw_response = bytes(response)
                    results.append(
                        ProbeResult(
                            servo_id,
                            True,
                            model_identifier,
                            self._protocol.is_supported_model(
                                model_identifier
                            ),
                            None,
                            raw_response,
                        )
                    )
                except HardwareProbeError as error:
                    results.append(
                        ProbeResult(
                            servo_id,
                            False,
                            None,
                            False,
                            type(error).__name__,
                            raw_response,
                        )
                    )
        return tuple(results)
