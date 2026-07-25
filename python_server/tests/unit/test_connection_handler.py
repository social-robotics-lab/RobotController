"""Unit tests for one-command legacy v1 connection integration."""

import json
import socket

import pytest

import robot_controller.connection_handler as connection_handler
from robot_controller.command_target import RecordingCommandTarget
from robot_controller.errors import (
    CommandDecodeError,
    CommandExecutionError,
    CommandFrameError,
    InvalidAxesError,
    InvalidFieldTypeError,
    InvalidFieldValueError,
    MissingPayloadError,
    PayloadJsonError,
    ResponseFrameError,
    ServoRangeError,
    UnknownCommandError,
)
from robot_controller.models import (
    DecodedCommand,
    IdleMotionSettings,
    Motion,
    Pose,
)
from robot_controller.profiles import RobotProfile
from robot_controller.protocol.commands import (
    DEFAULT_LIMITS,
    PAYLOAD_NONE,
    LegacyV1Limits,
)
from robot_controller.protocol.frame import encode_frame
from robot_controller.protocol.legacy_v1 import (
    LegacyV1Request,
    LegacyV1Timeouts,
)
from robot_controller.protocol.validation import ValidationLimits
from robot_controller.router import (
    CommandDispatchResult,
    CommandRouter,
)


class TrackingSocket(object):
    """Socket double that records ownership and I/O operations."""

    def __init__(self, incoming=b"", send_error=None, timeout=12.5):
        self.incoming = incoming
        self.send_error = send_error
        self.timeout = timeout
        self.recv_calls = []
        self.sent_data = []
        self.close_calls = 0
        self.shutdown_calls = []
        self.settimeout_calls = []

    def recv(self, size):
        self.recv_calls.append(size)
        if not self.incoming:
            return b""
        chunk = self.incoming[:size]
        self.incoming = self.incoming[size:]
        return chunk

    def sendall(self, data):
        self.sent_data.append(data)
        if self.send_error is not None:
            raise self.send_error

    def close(self):
        self.close_calls += 1

    def shutdown(self, how):
        self.shutdown_calls.append(how)

    def settimeout(self, value):
        self.settimeout_calls.append(value)
        self.timeout = value

    def gettimeout(self):
        return self.timeout


@pytest.fixture
def robot_profile():
    """Return a small test-only validation profile."""
    return RobotProfile(
        {"HEAD_Y": (-20, 20), "HEAD_P": (-10, 10)},
        {"Mouth": (0, 255)},
    )


def wire_request(command, payload=None):
    """Encode one complete legacy v1 request."""
    wire = encode_frame(command.encode("utf-8"))
    if payload is not None:
        wire += encode_frame(payload)
    return wire


def make_handler_parts(axes=None, exceptions=None):
    """Return a recording target and its router."""
    target = RecordingCommandTarget(
        read_axes_result=axes,
        exceptions=exceptions,
    )
    return target, CommandRouter(target)


def assert_socket_ownership_unchanged(sock, expected_timeout=12.5):
    """Assert that the handler did not take ownership of the socket."""
    assert sock.close_calls == 0
    assert sock.shutdown_calls == []
    assert sock.gettimeout() == expected_timeout


def test_handler_applies_custom_timeouts_and_restores_socket(robot_profile):
    payload = b'{"Msec":1,"ServoMap":{"HEAD_Y":0}}'
    sock = TrackingSocket(wire_request("play_pose", payload))
    target, router = make_handler_parts()
    timeouts = LegacyV1Timeouts(1.0, 2.0, 3.0, 4.0)

    result = connection_handler.handle_connection(
        sock,
        robot_profile,
        router,
        session_timeouts=timeouts,
    )

    assert result.command == "play_pose"
    assert target.call_count("play_pose") == 1
    assert sock.settimeout_calls == [1.0, 12.5, 2.0, 12.5]
    assert_socket_ownership_unchanged(sock)


def test_json_validation_failure_leaves_original_timeout(robot_profile):
    sock = TrackingSocket(wire_request("play_pose", b"{"))
    target, router = make_handler_parts()

    with pytest.raises(PayloadJsonError):
        connection_handler.handle_connection(sock, robot_profile, router)

    assert target.calls == ()
    assert sock.gettimeout() == 12.5
    assert sock.settimeout_calls == [5.0, 12.5, 5.0, 12.5]


def test_read_axes_response_failure_restores_original_timeout(robot_profile):
    failure = socket.timeout("send timed out")
    sock = TrackingSocket(
        wire_request("read_axes"),
        send_error=failure,
    )
    target, router = make_handler_parts({"HEAD_Y": 0})

    with pytest.raises(ResponseFrameError):
        connection_handler.handle_connection(sock, robot_profile, router)

    assert target.call_count("read_axes") == 1
    assert sock.gettimeout() == 12.5
    assert sock.settimeout_calls == [5.0, 12.5, 5.0, 12.5]


@pytest.mark.parametrize(
    "command",
    ["stop_wav", "stop_pose", "stop_motion", "stop_idle_motion"],
)
def test_stop_command_executes_once_without_response(
    command, robot_profile
):
    sock = TrackingSocket(wire_request(command))
    target, router = make_handler_parts()

    result = connection_handler.handle_connection(
        sock, robot_profile, router
    )

    assert result.command == command
    assert result.response_sent is False
    assert target.commands == (command,)
    assert target.call_count(command) == 1
    assert sock.sent_data == []
    assert_socket_ownership_unchanged(sock)


def test_play_wav_passes_opaque_bytes_once_without_response(robot_profile):
    wav_data = b"\x00RIFFopaque\xffWAVE"
    sock = TrackingSocket(wire_request("play_wav", wav_data))
    target, router = make_handler_parts()

    result = connection_handler.handle_connection(
        sock, robot_profile, router
    )

    assert result.command == "play_wav"
    assert result.response_sent is False
    assert target.commands == ("play_wav",)
    assert target.calls[0].payload == wav_data
    assert isinstance(target.calls[0].payload, bytes)
    assert sock.sent_data == []


def test_play_pose_passes_validated_pose_once(robot_profile):
    payload = b'{"Msec":50,"ServoMap":{"HEAD_Y":2}}'
    sock = TrackingSocket(wire_request("play_pose", payload))
    target, router = make_handler_parts()

    result = connection_handler.handle_connection(
        sock, robot_profile, router
    )

    pose = target.calls[0].payload
    assert result.command == "play_pose"
    assert result.response_sent is False
    assert target.commands == ("play_pose",)
    assert isinstance(pose, Pose)
    assert pose.duration_ms == 50
    assert dict(pose.servo_positions) == {"HEAD_Y": 2}
    assert sock.sent_data == []


def test_play_motion_passes_complete_motion_once(robot_profile):
    payload = (
        b'[{"Msec":10,"ServoMap":{"HEAD_Y":-2}},'
        b'{"Msec":20,"ServoMap":{"HEAD_Y":2}}]'
    )
    sock = TrackingSocket(wire_request("play_motion", payload))
    target, router = make_handler_parts()

    result = connection_handler.handle_connection(
        sock, robot_profile, router
    )

    motion = target.calls[0].payload
    assert result.command == "play_motion"
    assert target.commands == ("play_motion",)
    assert target.call_count("play_motion") == 1
    assert isinstance(motion, Motion)
    assert [pose.duration_ms for pose in motion.poses] == [10, 20]
    assert result.response_sent is False
    assert sock.sent_data == []


def test_play_idle_motion_passes_validated_settings_once(robot_profile):
    payload = b'{"Speed":1.5,"Pause":250}'
    sock = TrackingSocket(wire_request("play_idle_motion", payload))
    target, router = make_handler_parts()

    result = connection_handler.handle_connection(
        sock, robot_profile, router
    )

    settings = target.calls[0].payload
    assert result.command == "play_idle_motion"
    assert target.commands == ("play_idle_motion",)
    assert isinstance(settings, IdleMotionSettings)
    assert settings == IdleMotionSettings(1.5, 250)
    assert result.response_sent is False
    assert sock.sent_data == []


def test_read_axes_sends_one_existing_v1_response_frame(robot_profile):
    sock = TrackingSocket(wire_request("read_axes"))
    target, router = make_handler_parts({"HEAD_Y": -2, "HEAD_P": 3})

    result = connection_handler.handle_connection(
        sock, robot_profile, router
    )

    expected_body = b'{"HEAD_P":3,"HEAD_Y":-2}'
    assert result.command == "read_axes"
    assert result.response_sent is True
    assert target.commands == ("read_axes",)
    assert target.call_count("read_axes") == 1
    assert sock.sent_data == [encode_frame(expected_body)]
    assert sock.sent_data[0][:4] == len(expected_body).to_bytes(
        4, byteorder="big", signed=False
    )
    assert json.loads(sock.sent_data[0][4:].decode("utf-8")) == {
        "HEAD_P": 3,
        "HEAD_Y": -2,
    }
    assert_socket_ownership_unchanged(sock)


def test_result_is_small_immutable_and_does_not_retain_large_payload(
    robot_profile,
):
    wav_data = b"x" * (1024 * 1024)
    sock = TrackingSocket(wire_request("play_wav", wav_data))
    target, router = make_handler_parts()

    result = connection_handler.handle_connection(
        sock, robot_profile, router
    )

    assert tuple(result) == ("play_wav", False)
    assert result._fields == ("command", "response_sent")
    assert not hasattr(result, "payload")
    assert not hasattr(result, "socket")
    with pytest.raises(AttributeError):
        result.command = "forged"


def test_handler_processes_only_first_payload_free_command(robot_profile):
    second_frame = wire_request("stop_motion")
    sock = TrackingSocket(wire_request("stop_pose") + second_frame)
    target, router = make_handler_parts()

    result = connection_handler.handle_connection(
        sock, robot_profile, router
    )

    assert result.command == "stop_pose"
    assert target.commands == ("stop_pose",)
    assert sock.recv_calls == [4, len("stop_pose")]
    assert sock.incoming == second_frame


def test_handler_processes_only_first_payload_command(robot_profile):
    first = wire_request(
        "play_pose", b'{"Msec":10,"ServoMap":{"HEAD_Y":1}}'
    )
    second = wire_request("stop_pose")
    sock = TrackingSocket(first + second)
    target, router = make_handler_parts()

    connection_handler.handle_connection(sock, robot_profile, router)

    assert target.commands == ("play_pose",)
    assert sock.incoming == second


def test_layers_run_in_required_order_for_read_axes(
    monkeypatch, robot_profile
):
    events = []
    sock = TrackingSocket()
    request = LegacyV1Request(
        "read_axes", None, True, PAYLOAD_NONE
    )
    decoded = DecodedCommand("read_axes", None)

    class OrderedRouter(object):
        def dispatch(self, value):
            events.append(("dispatch", value))
            return CommandDispatchResult(b'{"HEAD_Y":0}')

    def fake_read_request(value, limits, timeouts):
        events.append(("read_request", value, limits, timeouts))
        return request

    def fake_decode_request(value, profile, limits):
        events.append(("decode_request", value, profile, limits))
        return decoded

    def fake_write_response(
        value,
        original_request,
        payload,
        timeouts,
    ):
        events.append(
            (
                "write_response",
                value,
                original_request,
                payload,
                timeouts,
            )
        )

    monkeypatch.setattr(
        connection_handler, "read_request", fake_read_request
    )
    monkeypatch.setattr(
        connection_handler, "decode_request", fake_decode_request
    )
    monkeypatch.setattr(
        connection_handler, "write_response", fake_write_response
    )
    router = OrderedRouter()

    result = connection_handler.handle_connection(
        sock,
        robot_profile,
        router,
        session_limits=DEFAULT_LIMITS,
        decoder_limits=ValidationLimits(),
    )

    assert [event[0] for event in events] == [
        "read_request",
        "decode_request",
        "dispatch",
        "write_response",
    ]
    assert events[1][1] is request
    assert events[2][1] is decoded
    assert events[3][2] is request
    assert events[3][3] == b'{"HEAD_Y":0}'
    assert result.command == "read_axes"
    assert result.response_sent is True


def test_no_response_payload_skips_write_response(
    monkeypatch, robot_profile
):
    events = []
    request = LegacyV1Request("stop_pose", None, False, PAYLOAD_NONE)
    decoded = DecodedCommand("stop_pose", None)

    class OrderedRouter(object):
        def dispatch(self, value):
            events.append("dispatch")
            return CommandDispatchResult(None)

    monkeypatch.setattr(
        connection_handler,
        "read_request",
        lambda sock, limits, timeouts: events.append("read") or request,
    )
    monkeypatch.setattr(
        connection_handler,
        "decode_request",
        lambda value, profile, limits: events.append("decode") or decoded,
    )

    def fail_if_written(*args):
        raise AssertionError("write_response must not be called")

    monkeypatch.setattr(
        connection_handler, "write_response", fail_if_written
    )

    result = connection_handler.handle_connection(
        TrackingSocket(), robot_profile, OrderedRouter()
    )

    assert events == ["read", "decode", "dispatch"]
    assert result.response_sent is False


def test_decode_failure_prevents_dispatch_and_response(
    monkeypatch, robot_profile
):
    failure = PayloadJsonError("play_pose")
    request = LegacyV1Request("play_pose", b"{", False, "json")
    events = []

    class ForbiddenRouter(object):
        def dispatch(self, value):
            raise AssertionError("dispatch must not be called")

    monkeypatch.setattr(
        connection_handler,
        "read_request",
        lambda sock, limits, timeouts: events.append("read") or request,
    )

    def fail_decode(value, profile, limits):
        events.append("decode")
        raise failure

    monkeypatch.setattr(
        connection_handler, "decode_request", fail_decode
    )
    monkeypatch.setattr(
        connection_handler,
        "write_response",
        lambda *args: pytest.fail("write_response must not be called"),
    )

    with pytest.raises(PayloadJsonError) as exc_info:
        connection_handler.handle_connection(
            TrackingSocket(), robot_profile, ForbiddenRouter()
        )

    assert exc_info.value is failure
    assert events == ["read", "decode"]


def test_dispatch_failure_prevents_response(
    monkeypatch, robot_profile
):
    request = LegacyV1Request("stop_pose", None, False, PAYLOAD_NONE)
    decoded = DecodedCommand("stop_pose", None)
    failure = CommandExecutionError("stop_pose")
    events = []

    class FailingRouter(object):
        def dispatch(self, value):
            events.append("dispatch")
            raise failure

    monkeypatch.setattr(
        connection_handler,
        "read_request",
        lambda sock, limits, timeouts: events.append("read") or request,
    )
    monkeypatch.setattr(
        connection_handler,
        "decode_request",
        lambda value, profile, limits: events.append("decode") or decoded,
    )
    monkeypatch.setattr(
        connection_handler,
        "write_response",
        lambda *args: pytest.fail("write_response must not be called"),
    )

    with pytest.raises(CommandExecutionError) as exc_info:
        connection_handler.handle_connection(
            TrackingSocket(), robot_profile, FailingRouter()
        )

    assert exc_info.value is failure
    assert events == ["read", "decode", "dispatch"]


@pytest.mark.parametrize(
    "incoming,error_type",
    [
        (b"\x00\x00\x00\x41", CommandFrameError),
        (encode_frame(b"\xff"), CommandDecodeError),
        (wire_request("unknown"), UnknownCommandError),
        (wire_request("play_pose"), MissingPayloadError),
        (wire_request("play_pose", b"{"), PayloadJsonError),
        (
            wire_request(
                "play_pose",
                b'{"Msec":true,"ServoMap":{"HEAD_Y":1}}',
            ),
            InvalidFieldTypeError,
        ),
        (
            wire_request(
                "play_pose",
                b'{"Msec":1,"ServoMap":{"HEAD_Y":21}}',
            ),
            ServoRangeError,
        ),
    ],
)
def test_read_decode_validation_errors_propagate_without_error_response(
    incoming, error_type, robot_profile
):
    sock = TrackingSocket(incoming)
    target, router = make_handler_parts()

    with pytest.raises(error_type):
        connection_handler.handle_connection(sock, robot_profile, router)

    assert target.calls == ()
    assert sock.sent_data == []
    assert_socket_ownership_unchanged(sock)


def test_target_exception_preserves_command_and_cause_without_response(
    robot_profile,
):
    failure = RuntimeError("target failed")
    sock = TrackingSocket(wire_request("stop_motion"))
    target, router = make_handler_parts(
        exceptions={"stop_motion": failure}
    )

    with pytest.raises(CommandExecutionError) as exc_info:
        connection_handler.handle_connection(sock, robot_profile, router)

    assert exc_info.value.command == "stop_motion"
    assert exc_info.value.__cause__ is failure
    assert sock.sent_data == []
    assert_socket_ownership_unchanged(sock)


def test_invalid_read_axes_result_propagates_without_error_frame(
    robot_profile,
):
    sock = TrackingSocket(wire_request("read_axes"))
    target, router = make_handler_parts({"HEAD_Y": True})

    with pytest.raises(CommandExecutionError) as exc_info:
        connection_handler.handle_connection(sock, robot_profile, router)

    assert exc_info.value.command == "read_axes"
    assert isinstance(exc_info.value.__cause__, InvalidAxesError)
    assert sock.sent_data == []
    assert_socket_ownership_unchanged(sock)


def test_response_socket_error_is_not_success_and_socket_is_not_closed(
    robot_profile,
):
    socket_error = OSError("send failed")
    sock = TrackingSocket(
        wire_request("read_axes"), send_error=socket_error
    )
    target, router = make_handler_parts({"HEAD_Y": 0})

    with pytest.raises(ResponseFrameError) as exc_info:
        connection_handler.handle_connection(sock, robot_profile, router)

    assert target.commands == ("read_axes",)
    assert exc_info.value.__cause__ is exc_info.value.frame_error
    assert exc_info.value.frame_error.__cause__ is socket_error
    assert len(sock.sent_data) == 1
    assert sock.sent_data[0] == encode_frame(b'{"HEAD_Y":0}')
    assert_socket_ownership_unchanged(sock)


def test_custom_session_limits_are_passed_to_read_request(robot_profile):
    limits = LegacyV1Limits(
        command_max_length=8,
        json_max_length=1024,
        wav_max_length=1024,
    )
    sock = TrackingSocket(wire_request("play_pose", b"{}"))
    target, router = make_handler_parts()

    with pytest.raises(CommandFrameError) as exc_info:
        connection_handler.handle_connection(
            sock,
            robot_profile,
            router,
            session_limits=limits,
        )

    assert exc_info.value.frame_error.max_length == 8
    assert target.calls == ()


def test_custom_decoder_limits_are_passed_to_decoder(robot_profile):
    limits = ValidationLimits(max_pose_duration_ms=9)
    payload = b'{"Msec":10,"ServoMap":{"HEAD_Y":1}}'
    sock = TrackingSocket(wire_request("play_pose", payload))
    target, router = make_handler_parts()

    with pytest.raises(InvalidFieldValueError):
        connection_handler.handle_connection(
            sock,
            robot_profile,
            router,
            decoder_limits=limits,
        )

    assert target.calls == ()


def test_handler_does_not_create_or_accept_additional_connections(
    monkeypatch, robot_profile
):
    def forbidden_socket(*args, **kwargs):
        raise AssertionError("new socket must not be created")

    monkeypatch.setattr(socket, "socket", forbidden_socket)
    sock = TrackingSocket(wire_request("stop_wav"))
    target, router = make_handler_parts()

    result = connection_handler.handle_connection(
        sock, robot_profile, router
    )

    assert result.command == "stop_wav"
    assert target.commands == ("stop_wav",)
