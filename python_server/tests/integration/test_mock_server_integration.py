"""Localhost integration test for the composed Mock Server application."""

import json
import logging
import socket
import threading

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
