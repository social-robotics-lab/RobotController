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
from robot_controller.mouth_led_composition import (
    BACKEND_MOCK,
    MouthLedBackendSettings,
)
from robot_controller.protocol.current import MOUTH_LED_PULSE_WIRE_COMMAND
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


def _send_current_request(address, command, payload):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(3.0)
    try:
        client.connect(address)
        client.sendall(
            encode_frame(command.encode("utf-8"))
            + encode_frame(json.dumps(payload).encode("utf-8"))
        )
        header = _recv_exact(client, 4)
        length = int.from_bytes(header, "big", signed=False)
        return json.loads(_recv_exact(client, length).decode("utf-8"))
    finally:
        client.close()


def test_composed_server_routes_v2_mouth_led_to_mock_backend_once():
    application = create_mock_application(
        MockApplicationConfig(
            host="127.0.0.1",
            port=0,
            mouth_led_settings=MouthLedBackendSettings(
                backend_kind=BACKEND_MOCK
            ),
        )
    )
    errors = []
    server_thread = threading.Thread(
        target=_run_application, args=(application, errors)
    )
    server_thread.start()
    try:
        assert application.server.wait_until_listening(5.0)
        response = _send_current_request(
            application.server.bound_address,
            MOUTH_LED_PULSE_WIRE_COMMAND,
            {
                "request_id": "integration-1",
                "payload": {
                    "level": 16,
                    "rise_ms": 200,
                    "hold_ms": 500,
                    "fall_ms": 200,
                },
            },
        )
    finally:
        application.shutdown()
        server_thread.join(5.0)

    assert errors == []
    assert response["status"] == "success"
    assert response["request_id"] == "integration-1"
    assert len(application.mouth_led_backend.calls) == 1


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
            assert "wav_timeout=30.0" in caplog.text
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

        assert application.target.call_count("stop_pose") == 0

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
    assert application.scheduler.is_stopped is True
    assert application.service.is_stopped is True
    assert len(set(application.target.command_thread_ids)) == 1


def test_multiple_tcp_clients_reach_target_only_on_single_worker():
    application = create_mock_application(
        MockApplicationConfig(
            host="127.0.0.1",
            port=0,
            max_workers=4,
            client_timeout_seconds=2.0,
        )
    )
    errors = []
    server_thread = threading.Thread(
        target=_run_application,
        args=(application, errors),
    )
    server_thread.start()
    try:
        assert application.server.wait_until_listening(5.0)
        address = application.server.bound_address
        start = threading.Barrier(5)
        clients = []

        def send_stop(command):
            start.wait()
            _send_legacy_request(address, command)

        for command in (
            "stop_wav",
            "stop_pose",
            "stop_motion",
            "stop_idle_motion",
        ):
            client = threading.Thread(target=send_stop, args=(command,))
            clients.append(client)
            client.start()
        start.wait()
        for client in clients:
            client.join(5.0)
            assert not client.is_alive()

        pose = b'{"Msec":0,"ServoMap":{"HEAD_Y":0}}'
        motion = b'[{"Msec":0,"ServoMap":{"HEAD_Y":0}}]'
        _send_legacy_request(address, "play_pose", pose)
        _send_legacy_request(address, "play_motion", motion)
        axes = _send_legacy_request(
            address,
            "read_axes",
            response=True,
        )
        assert json.loads(axes.decode("utf-8"))["HEAD_Y"] == 0
    finally:
        application.shutdown()
        server_thread.join(5.0)

    assert errors == []
    assert not server_thread.is_alive()
    assert application.target.call_count("play_pose") == 2
    assert application.target.call_count("play_motion") == 0
    assert application.target.call_count("read_axes") == 1
    assert len(application.target.command_thread_ids) == 4
    assert len(set(application.target.command_thread_ids)) == 1
    assert application.scheduler.is_stopped
    assert application.service.is_stopped


def test_tcp_motion_stop_replacement_modes_and_independent_commands():
    application = create_mock_application(
        MockApplicationConfig(
            host="127.0.0.1",
            port=0,
            max_workers=4,
            client_timeout_seconds=2.0,
        )
    )
    errors = []
    server_thread = threading.Thread(
        target=_run_application,
        args=(application, errors),
    )
    server_thread.start()
    try:
        assert application.server.wait_until_listening(5.0)
        address = application.server.bound_address

        motion_a = (
            b'[{"Msec":60000,"ServoMap":{"HEAD_Y":1}},'
            b'{"Msec":0,"ServoMap":{"HEAD_Y":2}}]'
        )
        _send_legacy_request(address, "play_motion", motion_a)
        assert application.target.wait_for_call_count(
            "play_pose", 1, 2.0
        )
        _send_legacy_request(address, "stop_motion")
        assert application.target.call_count("play_pose") == 1
        assert application.target.call_count("stop_pose") == 1

        _send_legacy_request(address, "play_motion", motion_a)
        assert application.target.wait_for_call_count(
            "play_pose", 2, 2.0
        )
        motion_b = (
            b'[{"Msec":0,"ServoMap":{"HEAD_Y":10}}]'
        )
        _send_legacy_request(address, "play_motion", motion_b)
        assert application.target.wait_for_call_count(
            "play_pose", 3, 2.0
        )

        _send_legacy_request(address, "play_motion", motion_a)
        assert application.target.wait_for_call_count(
            "play_pose", 4, 2.0
        )
        direct = b'{"Msec":0,"ServoMap":{"HEAD_Y":99}}'
        _send_legacy_request(address, "play_pose", direct)
        assert application.target.wait_for_call_count(
            "play_pose", 5, 2.0
        )

        _send_legacy_request(
            address,
            "play_idle_motion",
            b'{"Speed":1.0,"Pause":1000}',
        )
        _send_legacy_request(address, "stop_idle_motion")
        _send_legacy_request(address, "play_wav", b"opaque-wav")
        _send_legacy_request(address, "stop_wav")
        axes = _send_legacy_request(
            address,
            "read_axes",
            response=True,
        )

        positions = [
            call.payload.servo_positions["HEAD_Y"]
            for call in application.target.calls
            if call.command == "play_pose"
        ]
        assert positions == [1, 1, 10, 1, 99]
        assert application.target.call_count("play_idle_motion") == 1
        assert application.target.call_count("stop_idle_motion") == 1
        assert application.target.call_count("play_wav") == 1
        assert application.target.call_count("stop_wav") == 1
        assert json.loads(axes.decode("utf-8"))["HEAD_Y"] == 0
    finally:
        application.shutdown()
        server_thread.join(5.0)

    assert errors == []
    assert not server_thread.is_alive()
    assert application.scheduler.is_stopped
    assert application.service.is_stopped


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
