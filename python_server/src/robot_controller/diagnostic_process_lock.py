"""Small lazy process-lock helpers for explicitly live diagnostics."""

import typing

from robot_controller.process_lock import ProcessLockContextCleanupError


def acquire_live_process_lock(process_lock_factory=None):
    # type: (typing.Any) -> typing.Any
    """Create and acquire the whole-Sota lock without retrying."""
    if process_lock_factory is None:
        from robot_controller.posix_process_lock import FcntlProcessLock

        process_lock_factory = FcntlProcessLock
    process_lock = process_lock_factory()
    process_lock.acquire()
    return process_lock


def combine_process_lock_close(process_lock, operation_error):
    # type: (typing.Any, typing.Optional[BaseException]) -> typing.Optional[BaseException]
    """Close once and preserve both operation and close failures."""
    try:
        process_lock.close()
    except BaseException as cleanup_error:
        if operation_error is None:
            return cleanup_error
        return ProcessLockContextCleanupError(
            operation_error, cleanup_error
        )
    return operation_error
