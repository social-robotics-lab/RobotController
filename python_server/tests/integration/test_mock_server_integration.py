"""Localhost integration test for the composed Mock Server application."""

import json
import logging
import os
import queue
import signal
import socket
import subprocess
import sys
import threading

import pytest

from robot_controller.mock_server import (
    MockApplicationConfig,
    create_mock_application,
)
from robot_controller.protocol.frame import encode_frame


def _recv_exact(sock, size):
    chunks = []
    received = 0
    while received < size:
        chunk = sock.recv(size - received)
        if not chunk:
            raise AssertionError("connection closed before response completed")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def _run_application(application, errors):
    try:
        application.run()
    except BaseException as error:
        errors.append(error)


def _send_legacy_request(address, command, payload=None, response=False):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(3.0)
    try:
        client.connect(address)
        request = encode_frame(command.encode("utf-8"))
        if payload is not None:
            request += encode_frame(payload)
        client.sendall(request)
        if response:
            header = _recv_exact(client, 4)
            length = int.from_bytes(
                header,
                byteorder="big",
                signed=False,
            )
            return _recv_exact(client, length)
        assert client.recv(1) == b""
        return None
    finally:
        client.close()


def _send_all_legacy_commands(address):
    pose = b'{"Msec":0,"ServoMap":{"HEAD_Y":0}}'
    motion = b'[{"Msec":0,"ServoMap":{"HEAD_Y":0}}]'
    commands = [
        ("play_wav", b"opaque-wav", False),
        ("stop_wav", None, False),
        ("play_pose", pose, False),
        ("stop_pose", None, False),
        ("play_motion", motion, False),
        ("stop_motion", None, False),
        ("play_idle_motion", b"{}", False),
        ("stop_idle_motion", None, False),
        ("read_axes", None, True),
    ]
    response = None
    for command, payload, expects_response in commands:
        response = _send_legacy_request(
            address,
            command,
            payload=payload,
            response=expects_response,
        )
    assert json.loads(response.decode("utf-8")) == {
        "BODY_Y": 0,
        "HEAD_P": 0,
        "HEAD_Y": 0,
    }


def test_composed_mock_application_serves_stop_pose_and_read_axes(caplog):
    application = create_mock_application(
        MockApplicationConfig(
            host="127.0.0.1",
            port=0,
            max_workers=2,
            client_timeout_seconds=2.0,
        )
    )
    errors = []
    server_thread = threading.Thread(
        target=_run_application,
        args=(application, errors),
    )
    with caplog.at_level(logging.INFO, logger="robot_controller.mock_server"):
        assert "Mock server listening" not in caplog.text
        server_thread.start()
        try:
            assert application.server.wait_until_listening(5.0)
            assert "Mock server listening" in caplog.text
            assert "host=127.0.0.1" in caplog.text
            assert "profile=mock" in caplog.text
            assert "max_workers=2" in caplog.text
            assert "client_timeout=2.0" in caplog.text
        except BaseException:
            application.shutdown()
            server_thread.join(5.0)
            raise

    try:
        address = application.server.bound_address
        assert address[0] == "127.0.0.1"
        assert address[1] != 0

        stop_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        stop_client.settimeout(3.0)
        try:
            stop_client.connect(address)
            stop_client.sendall(encode_frame(b"stop_pose"))
            assert stop_client.recv(1) == b""
        finally:
            stop_client.close()

        assert application.target.call_count("stop_pose") == 1

        axes_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        axes_client.settimeout(3.0)
        try:
            axes_client.connect(address)
            axes_client.sendall(encode_frame(b"read_axes"))
            header = _recv_exact(axes_client, 4)
            length = int.from_bytes(
                header,
                byteorder="big",
                signed=False,
            )
            payload = _recv_exact(axes_client, length)
            assert json.loads(payload.decode("utf-8")) == {
                "BODY_Y": 0,
                "HEAD_P": 0,
                "HEAD_Y": 0,
            }
            assert axes_client.recv(1) == b""
        finally:
            axes_client.close()
    finally:
        application.shutdown()
        server_thread.join(5.0)

    assert not server_thread.is_alive()
    assert errors == []
    assert application.target.call_count("read_axes") == 1
    assert application.server.is_stopped is True


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows console control event regression",
)
@pytest.mark.parametrize("send_all_commands", [False, True])
def test_windows_mock_process_stops_after_one_console_control_event(
    send_all_commands,
):
    executable = getattr(sys, "_base_executable", sys.executable)
    source_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")
    )
    environment = dict(os.environ)
    previous_python_path = environment.get("PYTHONPATH")
    if previous_python_path:
        environment["PYTHONPATH"] = (
            source_root + os.pathsep + previous_python_path
        )
    else:
        environment["PYTHONPATH"] = source_root

    process = subprocess.Popen(
        [
            executable,
            "-m",
            "robot_controller.mock_server",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--log-level",
            "INFO",
        ],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=environment,
    )
    ready_lines = queue.Queue()

    def read_ready_line():
        ready_lines.put(process.stderr.readline())

    reader = threading.Thread(target=read_ready_line)
    reader.daemon = True
    reader.start()
    try:
        ready_line = ready_lines.get(timeout=10.0)
        assert "Mock server listening" in ready_line
        bound_port = int(
            ready_line.split("port=", 1)[1].split(" ", 1)[0]
        )
        if send_all_commands:
            _send_all_legacy_commands(("127.0.0.1", bound_port))

        process.send_signal(signal.CTRL_BREAK_EVENT)
        exit_code = process.wait(timeout=10.0)
        remaining_stdout, remaining_stderr = process.communicate(timeout=2.0)

        output = ready_line + remaining_stdout + remaining_stderr
        assert exit_code == 0
        assert "Traceback" not in output

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", bound_port))
        finally:
            probe.close()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)
