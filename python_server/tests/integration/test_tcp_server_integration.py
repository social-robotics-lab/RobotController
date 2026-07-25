"""Localhost integration tests for the bounded legacy v1 TCP server."""

import json
import socket
import threading

from robot_controller.command_target import RecordingCommandTarget
from robot_controller.profiles import RobotProfile
from robot_controller.protocol.frame import encode_frame
from robot_controller.router import CommandRouter
from robot_controller.tcp_server import (
    LegacyV1TcpServer,
    LegacyV1TcpServerConfig,
)


class EventRecordingTarget(RecordingCommandTarget):
    """Recording target exposing deterministic command completion Events."""

    def __init__(self, axes):
        RecordingCommandTarget.__init__(self, axes)
        self.stop_pose_event = threading.Event()
        self.read_axes_event = threading.Event()

    def stop_pose(self):
        RecordingCommandTarget.stop_pose(self)
        self.stop_pose_event.set()

    def read_axes(self):
        axes = RecordingCommandTarget.read_axes(self)
        self.read_axes_event.set()
        return axes


def recv_exact(sock, size):
    """Receive exactly size bytes from a localhost test connection."""
    chunks = []
    received = 0
    while received < size:
        chunk = sock.recv(size - received)
        if not chunk:
            raise AssertionError("connection closed before response completed")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def run_server(server, errors):
    """Run serve_forever and capture unexpected thread exceptions."""
    try:
        server.serve_forever()
    except BaseException as error:
        errors.append(error)


def test_localhost_stop_pose_read_axes_and_graceful_shutdown():
    profile = RobotProfile({"HEAD_Y": (-20, 20)}, {})
    target = EventRecordingTarget({"HEAD_Y": -4})
    router = CommandRouter(target)
    server = LegacyV1TcpServer(
        robot_profile=profile,
        router=router,
        config=LegacyV1TcpServerConfig(
            host="127.0.0.1",
            port=0,
            backlog=4,
            max_workers=2,
            client_timeout_seconds=2.0,
        ),
    )
    errors = []
    server_thread = threading.Thread(
        target=run_server, args=(server, errors)
    )
    server_thread.start()

    try:
        assert server.wait_until_listening(5.0)
        address = server.bound_address
        assert address[0] == "127.0.0.1"
        assert address[1] != 0
        assert server.is_listening is True

        stop_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        stop_client.settimeout(3.0)
        try:
            stop_client.connect(address)
            stop_client.sendall(encode_frame(b"stop_pose"))
            assert stop_client.recv(1) == b""
        finally:
            stop_client.close()

        assert target.stop_pose_event.wait(3.0)
        assert target.call_count("stop_pose") == 1

        axes_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        axes_client.settimeout(3.0)
        try:
            axes_client.connect(address)
            axes_client.sendall(encode_frame(b"read_axes"))
            header = recv_exact(axes_client, 4)
            length = int.from_bytes(
                header, byteorder="big", signed=False
            )
            payload = recv_exact(axes_client, length)
            assert json.loads(payload.decode("utf-8")) == {"HEAD_Y": -4}
            assert axes_client.recv(1) == b""
        finally:
            axes_client.close()

        assert target.read_axes_event.wait(3.0)
        assert target.call_count("read_axes") == 1
    finally:
        server.shutdown()
        server_thread.join(5.0)

    assert not server_thread.is_alive()
    assert errors == []
    assert server.is_listening is False
    assert server.is_stopped is True
    assert server.active_connection_count == 0
