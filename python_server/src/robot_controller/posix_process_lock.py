"""POSIX ``flock`` implementation of the whole-Sota process lock.

The module is importable on Windows: ``fcntl`` is loaded only when default
POSIX operations are constructed. Tests inject an operations object instead.
"""

import errno
import os

from robot_controller.process_lock import (
    PROCESS_LOCK_STATE_ACQUIRED,
    PROCESS_LOCK_STATE_CLOSED,
    PROCESS_LOCK_STATE_NEW,
    ProcessLock,
    ProcessLockAcquireCleanupError,
    ProcessLockReleaseError,
    ProcessLockStateError,
    ProcessLockUnavailableError,
)


DEFAULT_SOTA_PROCESS_LOCK_PATH = "/run/lock/robot-controller-sota.lock"
PROCESS_LOCK_FILE_MODE = 0o640


class _FcntlOperations(object):
    """Small adapter around POSIX calls, constructed only on POSIX hosts."""

    def __init__(self):
        import fcntl

        self._fcntl = fcntl
        self.lock_ex = fcntl.LOCK_EX
        self.lock_nb = fcntl.LOCK_NB
        self.lock_un = fcntl.LOCK_UN

    @staticmethod
    def open(path, flags, mode):
        # type: (str, int, int) -> int
        return os.open(path, flags, mode)

    @staticmethod
    def set_inheritable(fd, inheritable):
        # type: (int, bool) -> None
        os.set_inheritable(fd, inheritable)

    def flock(self, fd, operation):
        # type: (int, int) -> None
        self._fcntl.flock(fd, operation)

    @staticmethod
    def close(fd):
        # type: (int) -> None
        os.close(fd)


class FcntlProcessLock(ProcessLock):
    """Own a nonblocking kernel lock for one whole Sota robot.

    The lock file is deliberately never unlinked. Removing it while locked
    would allow another process to create a different inode at the same path
    and acquire an independent lock. This object is single-use: after an
    acquisition attempt or ``close()``, callers must create a new instance.
    """

    def __init__(self, path=DEFAULT_SOTA_PROCESS_LOCK_PATH, operations=None):
        # type: (str, object) -> None
        self._path = path
        self._operations = (
            _FcntlOperations() if operations is None else operations
        )
        self._state = PROCESS_LOCK_STATE_NEW
        self._fd = None

    @property
    def state(self):
        # type: () -> str
        return self._state

    def acquire(self):
        # type: () -> "FcntlProcessLock"
        """Acquire ``LOCK_EX | LOCK_NB`` without retry or waiting."""
        if self._state != PROCESS_LOCK_STATE_NEW:
            raise ProcessLockStateError(
                "process lock acquire requires state=new; state={0}".format(
                    self._state
                )
            )

        try:
            fd = self._operations.open(
                self._path,
                os.O_RDWR | os.O_CREAT,
                PROCESS_LOCK_FILE_MODE,
            )
        except BaseException:
            self._state = PROCESS_LOCK_STATE_CLOSED
            raise

        try:
            self._operations.set_inheritable(fd, False)
            self._operations.flock(
                fd,
                self._operations.lock_ex | self._operations.lock_nb,
            )
        except BaseException as acquisition_error:
            if (
                isinstance(acquisition_error, OSError)
                and acquisition_error.errno in (errno.EACCES, errno.EAGAIN)
            ):
                acquisition_error = ProcessLockUnavailableError(
                    (
                        "another RobotController process holds the Sota "
                        "process lock: {0}"
                    ).format(self._path)
                )
            self._state = PROCESS_LOCK_STATE_CLOSED
            self._close_failed_acquisition(fd, acquisition_error)

        self._fd = fd
        self._state = PROCESS_LOCK_STATE_ACQUIRED
        return self

    def _close_failed_acquisition(self, fd, acquisition_error):
        # type: (int, BaseException) -> None
        try:
            self._operations.close(fd)
        except BaseException as cleanup_error:
            raise ProcessLockAcquireCleanupError(
                acquisition_error, cleanup_error
            )
        raise acquisition_error

    def close(self):
        # type: () -> None
        """Unlock, close the fd, and leave the pathname in place."""
        if self._state == PROCESS_LOCK_STATE_CLOSED:
            return
        if self._state == PROCESS_LOCK_STATE_NEW:
            self._state = PROCESS_LOCK_STATE_CLOSED
            return

        fd = self._fd
        self._fd = None
        self._state = PROCESS_LOCK_STATE_CLOSED
        unlock_error = None
        close_error = None
        try:
            self._operations.flock(fd, self._operations.lock_un)
        except BaseException as error:
            unlock_error = error
        try:
            self._operations.close(fd)
        except BaseException as error:
            close_error = error
        if unlock_error is not None or close_error is not None:
            raise ProcessLockReleaseError(unlock_error, close_error)
