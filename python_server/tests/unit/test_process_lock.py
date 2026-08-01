"""Unit tests for the kernel-backed whole-Sota process lock."""

import errno
import importlib
import os

import pytest

from robot_controller.posix_process_lock import (
    DEFAULT_SOTA_PROCESS_LOCK_PATH,
    FcntlProcessLock,
)
from robot_controller.process_lock import (
    ProcessLockAcquireCleanupError,
    ProcessLockContextCleanupError,
    ProcessLockReleaseError,
    ProcessLockStateError,
    ProcessLockUnavailableError,
)


class FakePosixOperations(object):
    """Record injected POSIX calls without importing or using ``fcntl``."""

    lock_ex = 1
    lock_nb = 2
    lock_un = 8

    def __init__(self):
        self.fd = 41
        self.calls = []
        self.open_error = None
        self.set_inheritable_error = None
        self.lock_error = None
        self.unlock_error = None
        self.close_error = None

    def open(self, path, flags, mode):
        self.calls.append(("open", path, flags, mode))
        if self.open_error is not None:
            raise self.open_error
        return self.fd

    def set_inheritable(self, fd, inheritable):
        self.calls.append(("set_inheritable", fd, inheritable))
        if self.set_inheritable_error is not None:
            raise self.set_inheritable_error

    def flock(self, fd, operation):
        self.calls.append(("flock", fd, operation))
        if operation == self.lock_un:
            if self.unlock_error is not None:
                raise self.unlock_error
        elif self.lock_error is not None:
            raise self.lock_error

    def close(self, fd):
        self.calls.append(("close", fd))
        if self.close_error is not None:
            raise self.close_error


def _lock(operations=None, path=DEFAULT_SOTA_PROCESS_LOCK_PATH):
    if operations is None:
        operations = FakePosixOperations()
    return FcntlProcessLock(path=path, operations=operations), operations


def _call_count(operations, name):
    return len([call for call in operations.calls if call[0] == name])


def test_modules_import_without_opening_a_file(monkeypatch):
    def fail_open(*unused_arguments, **unused_keywords):
        raise AssertionError("import attempted file I/O")

    monkeypatch.setattr(os, "open", fail_open)
    import robot_controller.process_lock as contract_module
    import robot_controller.posix_process_lock as posix_module

    assert contract_module.ProcessLock is not None
    importlib.reload(posix_module)


def test_acquire_uses_expected_path_flags_mode_lock_and_inheritance():
    lock, operations = _lock(path="/run/lock/custom.lock")

    assert lock.state == "new"
    assert lock.is_acquired is False
    lock.acquire()

    assert lock.state == "acquired"
    assert lock.is_acquired is True
    assert lock._fd == operations.fd
    assert operations.calls == [
        (
            "open",
            "/run/lock/custom.lock",
            os.O_RDWR | os.O_CREAT,
            0o640,
        ),
        ("set_inheritable", operations.fd, False),
        (
            "flock",
            operations.fd,
            operations.lock_ex | operations.lock_nb,
        ),
    ]


def test_close_unlocks_then_closes_once_without_unlink(monkeypatch):
    lock, operations = _lock()
    unlink_calls = []
    monkeypatch.setattr(
        os, "unlink", lambda path: unlink_calls.append(path)
    )
    lock.acquire()

    lock.close()
    lock.close()

    assert lock.state == "closed"
    assert lock.is_acquired is False
    assert lock._fd is None
    assert operations.calls[-2:] == [
        ("flock", operations.fd, operations.lock_un),
        ("close", operations.fd),
    ]
    assert _call_count(operations, "flock") == 2
    assert _call_count(operations, "close") == 1
    assert unlink_calls == []


def test_close_before_acquire_is_idempotent_and_consumes_object():
    lock, operations = _lock()

    lock.close()
    lock.close()

    assert lock.state == "closed"
    assert operations.calls == []
    with pytest.raises(ProcessLockStateError):
        lock.acquire()


def test_context_manager_acquires_and_releases():
    lock, operations = _lock()

    with lock as entered:
        assert entered is lock
        assert lock.is_acquired is True

    assert lock.state == "closed"
    assert _call_count(operations, "close") == 1


def test_context_manager_releases_when_body_raises():
    lock, operations = _lock()

    with pytest.raises(RuntimeError, match="body failed"):
        with lock:
            raise RuntimeError("body failed")

    assert lock.state == "closed"
    assert _call_count(operations, "close") == 1


def test_context_manager_preserves_body_and_cleanup_errors():
    lock, operations = _lock()
    operations.unlock_error = OSError(errno.EIO, "unlock failed")

    with pytest.raises(ProcessLockContextCleanupError) as captured:
        with lock:
            raise RuntimeError("body failed")

    assert isinstance(captured.value.operation_error, RuntimeError)
    assert isinstance(captured.value.cleanup_error, ProcessLockReleaseError)
    assert _call_count(operations, "close") == 1


def test_double_acquire_and_reused_context_are_rejected():
    lock, unused_operations = _lock()
    lock.acquire()

    with pytest.raises(ProcessLockStateError):
        lock.acquire()
    lock.close()
    with pytest.raises(ProcessLockStateError):
        with lock:
            pass


@pytest.mark.parametrize("error_number", [errno.EACCES, errno.EAGAIN])
def test_contention_is_typed_nonblocking_and_closes_fd(error_number):
    lock, operations = _lock()
    operations.lock_error = OSError(error_number, "busy")

    with pytest.raises(ProcessLockUnavailableError) as captured:
        lock.acquire()

    assert (
        "another RobotController process holds the Sota process lock"
        in str(captured.value)
    )
    assert lock.state == "closed"
    assert lock.is_acquired is False
    assert lock._fd is None
    assert _call_count(operations, "open") == 1
    assert _call_count(operations, "flock") == 1
    assert _call_count(operations, "close") == 1


def test_open_error_is_preserved_without_fd_operations():
    lock, operations = _lock()
    expected = OSError(errno.ENOENT, "parent missing")
    operations.open_error = expected

    with pytest.raises(OSError) as captured:
        lock.acquire()

    assert captured.value is expected
    assert lock.state == "closed"
    assert operations.calls == [
        (
            "open",
            DEFAULT_SOTA_PROCESS_LOCK_PATH,
            os.O_RDWR | os.O_CREAT,
            0o640,
        )
    ]


def test_unexpected_flock_error_is_preserved_and_fd_is_closed():
    lock, operations = _lock()
    expected = OSError(errno.EIO, "flock failed")
    operations.lock_error = expected

    with pytest.raises(OSError) as captured:
        lock.acquire()

    assert captured.value is expected
    assert _call_count(operations, "flock") == 1
    assert _call_count(operations, "close") == 1
    assert lock.state == "closed"


def test_set_inheritable_error_is_preserved_and_fd_is_closed():
    lock, operations = _lock()
    expected = OSError(errno.EPERM, "inheritance failed")
    operations.set_inheritable_error = expected

    with pytest.raises(OSError) as captured:
        lock.acquire()

    assert captured.value is expected
    assert _call_count(operations, "flock") == 0
    assert _call_count(operations, "close") == 1
    assert lock.state == "closed"


def test_acquisition_and_fd_cleanup_errors_are_both_preserved():
    lock, operations = _lock()
    operations.lock_error = OSError(errno.EIO, "flock failed")
    operations.close_error = OSError(errno.EBADF, "close failed")

    with pytest.raises(ProcessLockAcquireCleanupError) as captured:
        lock.acquire()

    assert captured.value.acquisition_error is operations.lock_error
    assert captured.value.cleanup_error is operations.close_error
    assert _call_count(operations, "close") == 1
    assert lock.state == "closed"


def test_unlock_error_still_closes_fd_and_is_reported():
    lock, operations = _lock()
    operations.unlock_error = OSError(errno.EIO, "unlock failed")
    lock.acquire()

    with pytest.raises(ProcessLockReleaseError) as captured:
        lock.close()

    assert captured.value.unlock_error is operations.unlock_error
    assert captured.value.close_error is None
    assert _call_count(operations, "close") == 1
    assert lock.state == "closed"
    lock.close()
    assert _call_count(operations, "close") == 1


def test_unlock_and_close_errors_are_both_preserved():
    lock, operations = _lock()
    operations.unlock_error = OSError(errno.EIO, "unlock failed")
    operations.close_error = OSError(errno.EBADF, "close failed")
    lock.acquire()

    with pytest.raises(ProcessLockReleaseError) as captured:
        lock.close()

    assert captured.value.unlock_error is operations.unlock_error
    assert captured.value.close_error is operations.close_error
    assert _call_count(operations, "flock") == 2
    assert _call_count(operations, "close") == 1


def test_close_error_without_unlock_error_is_reported():
    lock, operations = _lock()
    operations.close_error = OSError(errno.EBADF, "close failed")
    lock.acquire()

    with pytest.raises(ProcessLockReleaseError) as captured:
        lock.close()

    assert captured.value.unlock_error is None
    assert captured.value.close_error is operations.close_error
    assert _call_count(operations, "close") == 1
