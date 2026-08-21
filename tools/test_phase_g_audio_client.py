#!/usr/bin/env python3
"""Localhost-only tests for phase_g_audio_client.py."""

from __future__ import print_function

import os
import socket
import struct
import tempfile
import threading
import unittest

import phase_g_audio_client as client


def receive_exact(connection, length):
    data = b""
    while len(data) < length:
        chunk = connection.recv(length - len(data))
        if not chunk:
            raise AssertionError("unexpected EOF")
        data += chunk
    return data


def receive_frame(connection):
    length = struct.unpack(">I", receive_exact(connection, 4))[0]
    return receive_exact(connection, length)


def send_response(connection, response_type, code):
    client.send_frame(connection, bytes(bytearray((response_type, code))))


def expect_no_frame(connection, timeout=0.1):
    previous = connection.gettimeout()
    connection.settimeout(timeout)
    try:
        try:
            data = connection.recv(1)
        except socket.timeout:
            return
        if data == b"":
            raise AssertionError("connection closed while barrier was gated")
        raise AssertionError("client sent data before barrier response")
    finally:
        connection.settimeout(previous)


class MockServer(object):
    def __init__(self, handler):
        self.events = []
        self.failure = None
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(3.0)
        self.port = self.listener.getsockname()[1]
        self.connection = None
        self.thread = threading.Thread(target=self._run, args=(handler,))

    def _run(self, handler):
        try:
            connection, _ = self.listener.accept()
            self.connection = connection
            connection.settimeout(3.0)
            try:
                handler(connection, self.events)
            finally:
                connection.close()
                self.connection = None
        except BaseException as error:
            self.failure = error
        finally:
            self.listener.close()

    def start(self):
        self.thread.start()

    def finish(self):
        self.thread.join(5.0)
        if self.thread.is_alive():
            self.close()
            self.thread.join(3.0)
        if self.thread.is_alive():
            raise AssertionError("mock server did not terminate after cleanup")
        if self.failure is not None:
            raise self.failure

    def close(self):
        connection = self.connection
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except socket.error:
                pass
            connection.close()
        self.listener.close()


class AudioClientTest(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.mkdtemp(prefix="phase-g-client-")

    def tearDown(self):
        for name in os.listdir(self.temp_directory):
            os.remove(os.path.join(self.temp_directory, name))
        os.rmdir(self.temp_directory)

    def pcm(self, name, length):
        path = os.path.join(self.temp_directory, name)
        with open(path, "wb") as output:
            output.write(b"\x01\x00" * (length // 2))
        return path

    def test_normal_barriers_and_framing(self):
        def handler(connection, events):
            self.assertEqual(client.COMMAND, receive_frame(connection))
            events.append("COMMAND")
            send_response(connection, 0x80, 0x01)
            self.assertEqual(client.START, receive_frame(connection))
            events.append("START")
            expect_no_frame(connection)
            send_response(connection, 0x80, 0x02)
            body = receive_frame(connection)
            self.assertEqual(client.DATA, body[:1])
            self.assertEqual(960, len(body) - 1)
            events.append("DATA")
            self.assertEqual(client.END, receive_frame(connection))
            events.append("END")
            send_response(connection, 0x80, 0x03)

        server = MockServer(handler)
        server.start()
        try:
            client.run_normal(
                "127.0.0.1", server.port, 3.0, self.pcm("a.pcm", 960))
        finally:
            server.finish()
        self.assertEqual(["COMMAND", "START", "DATA", "END"], server.events)

    def test_probe_stops_after_connection_ready(self):
        def handler(connection, events):
            self.assertEqual(client.COMMAND, receive_frame(connection))
            events.append("COMMAND")
            send_response(connection, 0x80, 0x01)
            self.assertEqual(b"", connection.recv(1))
            events.append("EOF")

        server = MockServer(handler)
        server.start()
        try:
            client.run_probe("127.0.0.1", server.port, 3.0, 0.0)
        finally:
            server.finish()
        self.assertEqual(["COMMAND", "EOF"], server.events)

    def test_cancel_restart_on_one_connection(self):
        def handler(connection, events):
            self.assertEqual(client.COMMAND, receive_frame(connection))
            events.append("COMMAND")
            send_response(connection, 0x80, 0x01)
            self.assertEqual(client.START, receive_frame(connection))
            events.append("START_A")
            expect_no_frame(connection)
            send_response(connection, 0x80, 0x02)
            body = receive_frame(connection)
            self.assertEqual(client.DATA, body[:1])
            events.append("DATA_A")
            self.assertEqual(client.CANCEL, receive_frame(connection))
            events.append("CANCEL")
            expect_no_frame(connection)
            send_response(connection, 0x80, 0x04)
            self.assertEqual(client.START, receive_frame(connection))
            events.append("START_B")
            send_response(connection, 0x80, 0x02)
            body = receive_frame(connection)
            self.assertEqual(client.DATA, body[:1])
            events.append("DATA_B")
            self.assertEqual(client.END, receive_frame(connection))
            events.append("END_B")
            send_response(connection, 0x80, 0x03)

        server = MockServer(handler)
        server.start()
        pcm_a = self.pcm("a.pcm", 960)
        pcm_b = self.pcm("b.pcm", 960)
        try:
            client.run_cancel_restart(
                "127.0.0.1", server.port, 3.0, pcm_a, pcm_b, 0.02)
        finally:
            server.finish()
        self.assertEqual(
            ["COMMAND", "START_A", "DATA_A", "CANCEL", "START_B", "DATA_B", "END_B"],
            server.events)

    def test_documented_error_decode(self):
        pairs = ((0x01, "BUSY"), (0x02, "PROTOCOL_ERROR"),
                 (0x03, "AUDIO_ERROR"), (0x04, "QUEUE_OVERFLOW"))
        for code, name in pairs:
            left, right = socket.socketpair()
            try:
                send_response(left, 0x81, code)
                with self.assertRaises(client.ServerError) as raised:
                    client.receive_response(right)
                self.assertEqual(name, raised.exception.name)
            finally:
                left.close()
                right.close()

    def test_pacing_does_not_catch_up_after_delay(self):
        class FakeClock(object):
            def __init__(self):
                self.now = 0.0

            def monotonic(self):
                return self.now

            def sleep(self, seconds):
                self.now += seconds

        class DelayedConnection(object):
            def __init__(self, fake_clock):
                self.clock = fake_clock
                self.sent_at = []

            def sendall(self, data):
                self.sent_at.append(self.clock.monotonic())
                if len(self.sent_at) == 1:
                    self.clock.now += 0.2

        fake_clock = FakeClock()
        connection = DelayedConnection(fake_clock)
        sent = client.send_pcm(
            connection, self.pcm("paced.pcm", 2880), clock=fake_clock.monotonic,
            sleeper=fake_clock.sleep)
        self.assertEqual(2880, sent)
        self.assertEqual(3, len(connection.sent_at))
        minimum_interval = 960.0 / client.BYTES_PER_SECOND
        intervals = [connection.sent_at[index] - connection.sent_at[index - 1]
                     for index in range(1, len(connection.sent_at))]
        for interval in intervals:
            self.assertGreaterEqual(interval + 1e-12, minimum_interval)

    def test_invalid_state_requires_protocol_error_and_close(self):
        def handler(connection, events):
            self.assertEqual(client.COMMAND, receive_frame(connection))
            send_response(connection, 0x80, 0x01)
            self.assertEqual(client.END, receive_frame(connection))
            events.append("END_IDLE")
            send_response(connection, 0x81, 0x02)

        server = MockServer(handler)
        server.start()
        try:
            client.run_invalid_state("127.0.0.1", server.port, 3.0)
        finally:
            server.finish()
        self.assertEqual(["END_IDLE"], server.events)

    def test_active_disconnect_releases_slot_for_probe(self):
        server = None

        def handler(connection, events):
            self.assertEqual(client.COMMAND, receive_frame(connection))
            send_response(connection, 0x80, 0x01)
            self.assertEqual(client.START, receive_frame(connection))
            send_response(connection, 0x80, 0x02)
            body = receive_frame(connection)
            self.assertEqual(client.DATA, body[:1])
            self.assertEqual(960, len(body) - 1)
            self.assertEqual(b"", connection.recv(1))
            events.append("ACTIVE_EOF")

            second, _ = server.listener.accept()
            second.settimeout(3.0)
            try:
                self.assertEqual(client.COMMAND, receive_frame(second))
                send_response(second, 0x80, 0x01)
                self.assertEqual(b"", second.recv(1))
                events.append("FRESH_READY")
            finally:
                second.close()

        server = MockServer(handler)
        server.start()
        try:
            client.run_disconnect_active(
                "127.0.0.1", server.port, 3.0,
                self.pcm("disconnect.pcm", 960), 0.0)
        finally:
            server.finish()
        self.assertEqual(["ACTIVE_EOF", "FRESH_READY"], server.events)


if __name__ == "__main__":
    unittest.main(verbosity=2)
