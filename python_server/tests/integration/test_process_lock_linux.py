"""Linux subprocess integration tests for the whole-Sota process lock."""

import os
import select
import signal
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not sys.platform.startswith("linux"),
    reason="requires Linux flock and process signals",
)


CHILD_EXIT_ACQUIRED = 0
CHILD_EXIT_UNAVAILABLE = 2
CHILD_EXIT_UNEXPECTED = 3
PROCESS_TIMEOUT_SECONDS = 5.0


CHILD_SCRIPT = r"""
import sys

from robot_controller.posix_process_lock import FcntlProcessLock
from robot_controller.process_lock import ProcessLockUnavailableError


def main():
    action = sys.argv[1]
    path = sys.argv[2]
    process_lock = FcntlProcessLock(path=path)
    try:
        process_lock.acquire()
    except ProcessLockUnavailableError as error:
        sys.stderr.write("ProcessLockUnavailableError: {0}\n".format(error))
        sys.stderr.flush()
        return 2
    except BaseException as error:
        sys.stderr.write("{0}: {1}\n".format(type(error).__name__, error))
        sys.stderr.flush()
        return 3

    sys.stdout.write("lock_acquired\n")
    sys.stdout.flush()
    if action == "hold":
        command = sys.stdin.readline().strip()
        if command != "release":
            sys.stderr.write("unexpected_command={0}\n".format(command))
            sys.stderr.flush()
            process_lock.close()
            return 3
    process_lock.close()
    sys.stdout.write("lock_released\n")
    sys.stdout.flush()
    return 0


sys.exit(main())
"""


def _child_environment():
    source_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")
    )
    environment = dict(os.environ)
    previous = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_root if not previous else source_root + os.pathsep + previous
    )
    return environment


def _child_arguments(action, lock_path):
    return [sys.executable, "-c", CHILD_SCRIPT, action, lock_path]


def _close_pipe(pipe):
    if pipe is not None and not pipe.closed:
        pipe.close()


def _cleanup_process(process):
    if process is None:
        return
    _close_pipe(process.stdin)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
    _close_pipe(process.stdout)
    _close_pipe(process.stderr)


def _start_holder(lock_path):
    process = subprocess.Popen(
        _child_arguments("hold", lock_path),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=_child_environment(),
    )
    ready, unused_write, unused_error = select.select(
        [process.stdout], [], [], PROCESS_TIMEOUT_SECONDS
    )
    if not ready:
        _cleanup_process(process)
        raise AssertionError("holder did not report readiness")
    line = process.stdout.readline().strip()
    if line != "lock_acquired":
        process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
        error = process.stderr.read()
        _cleanup_process(process)
        raise AssertionError(
            "unexpected holder output={0!r} stderr={1!r}".format(line, error)
        )
    return process


def _run_once(lock_path):
    return subprocess.run(
        _child_arguments("once", lock_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=_child_environment(),
        timeout=PROCESS_TIMEOUT_SECONDS,
    )


def _release_holder(process):
    process.stdin.write("release\n")
    process.stdin.flush()
    process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
    output = process.stdout.read()
    error = process.stderr.read()
    assert process.returncode == CHILD_EXIT_ACQUIRED, error
    assert "lock_released" in output


def test_contention_is_nonblocking_and_normal_exit_allows_reacquire(tmp_path):
    lock_path = str(tmp_path / "robot-controller-sota.lock")
    holder = None
    try:
        holder = _start_holder(lock_path)

        contender = _run_once(lock_path)
        assert contender.returncode == CHILD_EXIT_UNAVAILABLE
        assert "ProcessLockUnavailableError" in contender.stderr
        assert (
            "another RobotController process holds the Sota process lock"
            in contender.stderr
        )
        assert holder.poll() is None

        _release_holder(holder)
        assert os.path.exists(lock_path)

        successor = _run_once(lock_path)
        assert successor.returncode == CHILD_EXIT_ACQUIRED, successor.stderr
        assert "lock_acquired" in successor.stdout
        assert "lock_released" in successor.stdout
    finally:
        _cleanup_process(holder)


def test_kernel_fd_cleanup_after_sigkill_allows_reacquire(tmp_path):
    if not hasattr(signal, "SIGKILL"):
        pytest.skip("SIGKILL is unavailable")
    lock_path = str(tmp_path / "robot-controller-sota.lock")
    holder = None
    try:
        holder = _start_holder(lock_path)
        os.kill(holder.pid, signal.SIGKILL)
        holder.wait(timeout=PROCESS_TIMEOUT_SECONDS)
        assert holder.returncode != CHILD_EXIT_ACQUIRED

        # No Python cleanup runs after SIGKILL; the kernel closes the lock fd.
        successor = _run_once(lock_path)
        assert successor.returncode == CHILD_EXIT_ACQUIRED, successor.stderr
        assert "lock_acquired" in successor.stdout
    finally:
        _cleanup_process(holder)


def test_normal_close_leaves_pathname_and_another_process_can_lock(tmp_path):
    lock_path = str(tmp_path / "robot-controller-sota.lock")

    first = _run_once(lock_path)
    assert first.returncode == CHILD_EXIT_ACQUIRED, first.stderr
    assert os.path.exists(lock_path)

    second = _run_once(lock_path)
    assert second.returncode == CHILD_EXIT_ACQUIRED, second.stderr
    assert os.path.exists(lock_path)
