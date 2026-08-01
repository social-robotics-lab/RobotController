"""Platform-neutral contract for a whole-Sota process lock.

Importing this module performs no file I/O and acquires no operating-system
resource. Platform implementations own the resource from ``acquire()`` until
``close()``.
"""

import abc


PROCESS_LOCK_STATE_NEW = "new"
PROCESS_LOCK_STATE_ACQUIRED = "acquired"
PROCESS_LOCK_STATE_CLOSED = "closed"


class ProcessLockError(Exception):
    """Base class for process-lock lifecycle failures."""


class ProcessLockStateError(ProcessLockError):
    """An operation was attempted outside the lock's valid lifecycle."""


class ProcessLockUnavailableError(ProcessLockError):
    """Another cooperating RobotController process holds the lock."""


class ProcessLockAcquireCleanupError(ProcessLockError):
    """Acquisition and mandatory file-descriptor cleanup both failed."""

    def __init__(self, acquisition_error, cleanup_error):
        # type: (BaseException, BaseException) -> None
        self.acquisition_error = acquisition_error
        self.cleanup_error = cleanup_error
        ProcessLockError.__init__(
            self,
            (
                "process lock acquisition failed with {0}; fd cleanup "
                "failed with {1}"
            ).format(
                type(acquisition_error).__name__,
                type(cleanup_error).__name__,
            ),
        )


class ProcessLockReleaseError(ProcessLockError):
    """Unlock or file-descriptor close failed during release."""

    def __init__(self, unlock_error, close_error):
        # type: (BaseException, BaseException) -> None
        self.unlock_error = unlock_error
        self.close_error = close_error
        failures = []
        if unlock_error is not None:
            failures.append(
                "unlock={0}".format(type(unlock_error).__name__)
            )
        if close_error is not None:
            failures.append("close={0}".format(type(close_error).__name__))
        ProcessLockError.__init__(
            self, "process lock release failed: {0}".format(", ".join(failures))
        )


class ProcessLockContextCleanupError(ProcessLockError):
    """A context body and its process-lock cleanup both failed."""

    def __init__(self, operation_error, cleanup_error):
        # type: (BaseException, BaseException) -> None
        self.operation_error = operation_error
        self.cleanup_error = cleanup_error
        ProcessLockError.__init__(
            self,
            (
                "process lock context failed with {0}; cleanup failed "
                "with {1}"
            ).format(
                type(operation_error).__name__,
                type(cleanup_error).__name__,
            ),
        )


class ProcessLock(abc.ABC):
    """Own one non-reusable process-lock lifecycle.

    A new object may make exactly one acquisition attempt. Successful
    acquisition changes the state to ``acquired``; ``close()`` and every
    failed acquisition change it to ``closed``. Closed objects cannot be
    acquired again. ``close()`` itself is idempotent.
    """

    @property
    @abc.abstractmethod
    def state(self):
        # type: () -> str
        """Return ``new``, ``acquired``, or ``closed``."""
        raise NotImplementedError

    @property
    def is_acquired(self):
        # type: () -> bool
        """Return whether this object currently owns the process lock."""
        return self.state == PROCESS_LOCK_STATE_ACQUIRED

    @abc.abstractmethod
    def acquire(self):
        # type: () -> "ProcessLock"
        """Acquire without blocking or retrying and return this object."""
        raise NotImplementedError

    @abc.abstractmethod
    def close(self):
        # type: () -> None
        """Release owned resources; repeated calls must be safe."""
        raise NotImplementedError

    def __enter__(self):
        # type: () -> "ProcessLock"
        return self.acquire()

    def __exit__(self, exception_type, exception, traceback):
        # type: (object, BaseException, object) -> bool
        try:
            self.close()
        except BaseException as cleanup_error:
            if exception is None:
                raise
            raise ProcessLockContextCleanupError(exception, cleanup_error)
        return False
