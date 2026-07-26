"""Small, testable transport boundary for a future Sota serial driver."""

import abc
import collections
import errno
import os
import threading
import typing

from robot_controller.errors import (
    PartialResponseError,
    TransportStateError,
    TransportTimeoutError,
    UnsupportedHardwarePlatformError,
)


class SotaTransport(abc.ABC):
    """Own a byte transport used by the read-only capability probe."""

    @abc.abstractmethod
    def open(self):
        # type: () -> None
        """Open resources."""

    @abc.abstractmethod
    def write(self, data):
        # type: (bytes) -> None
        """Write exactly the supplied bytes."""

    @abc.abstractmethod
    def read_exact(self, size, timeout):
        # type: (int, float) -> bytes
        """Read exactly size bytes within the transport timeout policy."""

    @abc.abstractmethod
    def close(self):
        # type: () -> None
        """Close resources idempotently."""

    def __enter__(self):
        # type: () -> SotaTransport
        self.open()
        return self

    def __exit__(self, exception_type, exception, traceback):
        # type: (typing.Any, typing.Any, typing.Any) -> bool
        self.close()
        return False


class PosixSerialTransport(SotaTransport):
    """Fail-closed placeholder for a future verified POSIX UART transport.

    Importing this class never imports ``termios`` or opens a device.  The
    repository does not yet contain verified UART configuration, so even on
    POSIX an open request is rejected until that configuration is documented.
    """

    def __init__(self, device, baud_rate):
        # type: (str, int) -> None
        self.device = device
        self.baud_rate = baud_rate
        self._closed = True

    def open(self):
        # type: () -> None
        if os.name != "posix":
            raise UnsupportedHardwarePlatformError(
                "Real Sota transport is unavailable on this platform"
            )
        raise UnsupportedHardwarePlatformError(
            "Real Sota transport awaits verified UART configuration"
        )

    def write(self, data):
        # type: (bytes) -> None
        raise TransportStateError("Transport is not open")

    def read_exact(self, size, timeout):
        # type: (int, float) -> bytes
        raise TransportStateError("Transport is not open")

    def close(self):
        # type: () -> None
        self._closed = True


class FakeSotaTransport(SotaTransport):
    """In-memory recording transport for deterministic tests."""

    def __init__(self, read_items=None, open_error=None):
        # type: (typing.Optional[typing.Iterable[typing.Any]], typing.Optional[BaseException]) -> None
        self._lock = threading.Lock()
        self._read_items = list(read_items or ())
        self._open_error = open_error
        self._is_open = False
        self._writes = []
        self.open_count = 0
        self.close_count = 0
        self.read_timeouts = []

    @property
    def writes(self):
        # type: () -> typing.Tuple[bytes, ...]
        with self._lock:
            return tuple(self._writes)

    @property
    def is_open(self):
        # type: () -> bool
        with self._lock:
            return self._is_open

    def open(self):
        # type: () -> None
        with self._lock:
            if self._open_error is not None:
                raise self._open_error
            self.open_count += 1
            self._is_open = True

    def write(self, data):
        # type: (bytes) -> None
        if not isinstance(data, bytes):
            raise TypeError("transport data must be bytes")
        with self._lock:
            if not self._is_open:
                raise TransportStateError("Transport is not open")
            self._writes.append(bytes(data))

    def read_exact(self, size, timeout):
        # type: (int, float) -> bytes
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError("size must be a non-negative integer")
        with self._lock:
            if not self._is_open:
                raise TransportStateError("Transport is not open")
            self.read_timeouts.append(timeout)

        received = bytearray()
        while len(received) < size:
            with self._lock:
                if not self._read_items:
                    raise PartialResponseError(size, len(received))
                item = self._read_items.pop(0)
            if isinstance(item, BaseException):
                if isinstance(item, OSError) and item.errno == errno.EINTR:
                    continue
                if isinstance(item, TimeoutError):
                    raise TransportTimeoutError("read") from item
                raise item
            if not isinstance(item, bytes):
                raise TypeError("fake read items must be bytes or exceptions")
            if not item:
                raise PartialResponseError(size, len(received))
            remaining = size - len(received)
            received.extend(item[:remaining])
            if len(item) > remaining:
                with self._lock:
                    self._read_items.insert(0, item[remaining:])
        return bytes(received)

    def close(self):
        # type: () -> None
        with self._lock:
            if self._is_open:
                self.close_count += 1
                self._is_open = False
