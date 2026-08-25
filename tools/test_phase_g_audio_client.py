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


class FakeClock(object):
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class OversleepClock(FakeClock):
    def __init__(self, oversleep_seconds):
        FakeClock.__init__(self)
        self.oversleep_seconds = oversleep_seconds
        self.overslept = False

    def sleep(self, seconds):
        FakeClock.sleep(self, seconds)
        if not self.overslept:
            self.now += self.oversleep_seconds
            self.overslept = True


class SelectedOversleepClock(FakeClock):
    def __init__(self, oversleeps):
        FakeClock.__init__(self)
        self.oversleeps = oversleeps
        self.sleep_count = 0

    def sleep(self, seconds):
        FakeClock.sleep(self, seconds)
        self.sleep_count += 1
        self.now += self.oversleeps.get(self.sleep_count, 0.0)


class TimedConnection(object):
    def __init__(self, fake_clock, send_overhead=0.0,
                 stall_after_send=None, stall_seconds=0.0,
                 send_overheads=None):
        self.clock = fake_clock
        self.send_overhead = send_overhead
        self.stall_after_send = stall_after_send
        self.stall_seconds = stall_seconds
        self.send_overheads = send_overheads or {}
        self.sent_at = []
        self.frame_lengths = []

    def sendall(self, data):
        self.sent_at.append(self.clock.monotonic())
        self.frame_lengths.append(len(data))
        self.clock.now += self.send_overheads.get(
            len(self.sent_at), self.send_overhead)
        if len(self.sent_at) == self.stall_after_send:
            self.clock.now += self.stall_seconds


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
                "127.0.0.1", server.port, 3.0, pcm_a, pcm_b, 0.02, 4, 2)
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

    def test_pacing_uses_absolute_pcm_schedule(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        sent = client.send_pcm(
            connection, self.pcm("paced.pcm", 4800), clock=fake_clock.monotonic,
            sleeper=fake_clock.sleep)
        self.assertEqual(4800, sent)
        self.assertEqual([0.0, 0.02, 0.04, 0.06, 0.08], connection.sent_at)

    def test_pacing_does_not_accumulate_send_overhead(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock, send_overhead=0.001)
        sent = client.send_pcm(
            connection, self.pcm("ten-seconds.pcm", 480000),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep)
        self.assertEqual(480000, sent)
        self.assertEqual(500, len(connection.sent_at))
        self.assertAlmostEqual(9.98, connection.sent_at[-1], places=9)

    def test_pacing_rebases_after_stall_without_catch_up_burst(self):
        fake_clock = FakeClock()
        connection = TimedConnection(
            fake_clock, stall_after_send=1, stall_seconds=0.2)
        sent = client.send_pcm(
            connection, self.pcm("stalled.pcm", 3840),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep)
        self.assertEqual(3840, sent)
        self.assertEqual(4, len(connection.sent_at))
        expected = [0.0, 0.2, 0.22, 0.24]
        for expected_time, actual_time in zip(expected, connection.sent_at):
            self.assertAlmostEqual(expected_time, actual_time, places=9)

    def test_pacing_rebases_after_sleep_stall_without_catch_up_burst(self):
        fake_clock = OversleepClock(0.2)
        connection = TimedConnection(fake_clock)
        sent = client.send_pcm(
            connection, self.pcm("overslept.pcm", 3840),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep)
        self.assertEqual(3840, sent)
        self.assertEqual(4, len(connection.sent_at))
        expected = [0.0, 0.22, 0.24, 0.26]
        for expected_time, actual_time in zip(expected, connection.sent_at):
            self.assertAlmostEqual(expected_time, actual_time, places=9)

    def test_pacing_keeps_short_final_chunk_aligned(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        sent = client.send_pcm(
            connection, self.pcm("short-final.pcm", 2400),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep)
        self.assertEqual(2400, sent)
        self.assertEqual([965, 965, 485], connection.frame_lengths)
        expected = [0.0, 0.02, 0.04]
        for expected_time, actual_time in zip(expected, connection.sent_at):
            self.assertAlmostEqual(expected_time, actual_time, places=9)

    def test_diagnostics_report_zero_rebases_without_stall(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("diagnostic-no-stall.pcm", 4800),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics)
        self.assertEqual(4800, diagnostics["pcm_bytes"])
        self.assertEqual(5, diagnostics["chunks"])
        self.assertAlmostEqual(0.1, diagnostics["nominal_seconds"], places=9)
        self.assertAlmostEqual(
            0.08, diagnostics["send_span_seconds"], places=9)
        self.assertAlmostEqual(60000.0, diagnostics["effective_rate"], places=9)
        self.assertEqual(0, diagnostics["rebases"])
        self.assertAlmostEqual(
            0.0, diagnostics["max_lateness_seconds"], places=9)
        self.assertAlmostEqual(
            0.0, diagnostics["max_send_seconds"], places=9)
        self.assertAlmostEqual(
            0.0, diagnostics["max_sleep_overshoot_seconds"], places=9)

    def test_diagnostics_report_one_rebase_after_large_stall(self):
        fake_clock = FakeClock()
        connection = TimedConnection(
            fake_clock, stall_after_send=1, stall_seconds=0.2)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("diagnostic-rebase.pcm", 3840),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics)
        self.assertEqual(1, diagnostics["rebases"])

    def test_diagnostics_report_known_minor_lateness(self):
        fake_clock = FakeClock()
        connection = TimedConnection(
            fake_clock, stall_after_send=1, stall_seconds=0.03)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("diagnostic-lateness.pcm", 2880),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics)
        self.assertEqual(0, diagnostics["rebases"])
        self.assertAlmostEqual(
            0.01, diagnostics["max_lateness_seconds"], places=9)

    def test_diagnostics_report_send_duration(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock, send_overhead=0.005)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("diagnostic-send.pcm", 2880),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics)
        self.assertAlmostEqual(
            0.005, diagnostics["max_send_seconds"], places=9)

    def test_experimental_defaults_preserve_absolute_schedule(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("experimental-default.pcm", 4800),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=0,
            max_catchup_chunks=0)
        self.assertEqual([0.0, 0.02, 0.04, 0.06, 0.08], connection.sent_at)
        self.assertEqual(0, diagnostics["initial_prebuffer_chunks"])
        self.assertEqual(0, diagnostics["catchup_event_count"])

    def test_initial_prebuffer_four_preserves_lead(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        client.send_pcm(
            connection, self.pcm("prebuffer-four.pcm", 6720),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            prebuffer_chunks=4)
        self.assertEqual(
            [0.0, 0.0, 0.0, 0.0, 0.02, 0.04, 0.06],
            connection.sent_at)

    def test_initial_prebuffer_three_preserves_lead(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        client.send_pcm(
            connection, self.pcm("prebuffer-three.pcm", 5760),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            prebuffer_chunks=3)
        self.assertEqual(
            [0.0, 0.0, 0.0, 0.02, 0.04, 0.06], connection.sent_at)

    def test_prebuffer_short_stream_sends_only_available_chunks(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        sent = client.send_pcm(
            connection, self.pcm("prebuffer-short.pcm", 1920),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4)
        self.assertEqual(1920, sent)
        self.assertEqual([0.0, 0.0], connection.sent_at)
        self.assertEqual(2, diagnostics["initial_prebuffer_chunks"])

    def test_prebuffer_keeps_short_final_chunk_aligned(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        client.send_pcm(
            connection, self.pcm("prebuffer-short-final.pcm", 2400),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            prebuffer_chunks=2)
        self.assertEqual([965, 965, 485], connection.frame_lengths)
        self.assertEqual([0.0, 0.0, 0.02], connection.sent_at)

    def test_bounded_catchup_recovers_38_201_ms_stall(self):
        fake_clock = OversleepClock(0.038201)
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("catchup-38ms.pcm", 7680),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=2)
        expected = [0.0, 0.0, 0.0, 0.0, 0.058201, 0.058201, 0.06, 0.08]
        for expected_time, actual_time in zip(expected, connection.sent_at):
            self.assertAlmostEqual(expected_time, actual_time, places=9)
        self.assertEqual(1, diagnostics["catchup_event_count"])
        self.assertEqual(2, diagnostics["catchup_chunk_count"])
        self.assertEqual(2, diagnostics["maximum_catchup_burst"])
        self.assertEqual(0, diagnostics["rebases"])

    def test_large_stall_rebases_without_catchup_burst(self):
        fake_clock = OversleepClock(0.18)
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("catchup-large-stall.pcm", 6720),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=2)
        expected = [0.0, 0.0, 0.0, 0.0, 0.2, 0.22, 0.24]
        for expected_time, actual_time in zip(expected, connection.sent_at):
            self.assertAlmostEqual(expected_time, actual_time, places=9)
        self.assertEqual(0, diagnostics["catchup_event_count"])
        self.assertEqual(1, diagnostics["rebases"])
        self.assertEqual(
            1, diagnostics["rebase_after_unrecoverable_stall_count"])

    def test_catchup_recovery_boundary_is_inclusive(self):
        recoverable_clock = OversleepClock(0.04)
        recoverable_connection = TimedConnection(recoverable_clock)
        recoverable = {}
        client.send_pcm(
            recoverable_connection, self.pcm("catchup-boundary.pcm", 6720),
            clock=recoverable_clock.monotonic,
            sleeper=recoverable_clock.sleep, diagnostics=recoverable,
            prebuffer_chunks=4, max_catchup_chunks=2)
        self.assertEqual(1, recoverable["catchup_event_count"])
        self.assertEqual(0, recoverable["rebases"])

        excessive_clock = OversleepClock(0.040001)
        excessive_connection = TimedConnection(excessive_clock)
        excessive = {}
        client.send_pcm(
            excessive_connection, self.pcm("catchup-over-boundary.pcm", 6720),
            clock=excessive_clock.monotonic, sleeper=excessive_clock.sleep,
            diagnostics=excessive, prebuffer_chunks=4,
            max_catchup_chunks=2)
        self.assertEqual(0, excessive["catchup_event_count"])
        self.assertEqual(1, excessive["rebases"])

    def test_catchup_burst_never_exceeds_configured_bound(self):
        fake_clock = OversleepClock(0.038201)
        connection = TimedConnection(fake_clock)
        client.send_pcm(
            connection, self.pcm("catchup-bound.pcm", 9600),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            prebuffer_chunks=4, max_catchup_chunks=2)
        recovery_times = connection.sent_at[4:]
        longest_equal_run = 1
        current_run = 1
        for index in range(1, len(recovery_times)):
            if abs(recovery_times[index] - recovery_times[index - 1]) < 1e-12:
                current_run += 1
                longest_equal_run = max(longest_equal_run, current_run)
            else:
                current_run = 1
        self.assertLessEqual(longest_equal_run, 2)

    def test_exhausted_catchup_budget_waits_before_third_data(self):
        fake_clock = OversleepClock(0.038201)
        connection = TimedConnection(
            fake_clock, send_overheads={5: 0.015, 6: 0.015})
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("catchup-exhausted.pcm", 8640),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=2)
        self.assertAlmostEqual(0.058201, connection.sent_at[4], places=9)
        self.assertAlmostEqual(0.073201, connection.sent_at[5], places=9)
        self.assertAlmostEqual(0.108201, connection.sent_at[6], places=9)
        self.assertEqual(2, diagnostics["maximum_catchup_burst"])
        self.assertEqual(1, diagnostics["rebases"])

    def test_repeated_moderate_stalls_recover_without_lag_accumulation(self):
        fake_clock = SelectedOversleepClock({1: 0.038201, 4: 0.037})
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("catchup-repeated.pcm", 11520),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=2)
        self.assertEqual(2, diagnostics["catchup_event_count"])
        self.assertEqual(4, diagnostics["catchup_chunk_count"])
        self.assertEqual(2, diagnostics["maximum_catchup_burst"])
        self.assertEqual(0, diagnostics["rebases"])
        self.assertAlmostEqual(0.16, connection.sent_at[-1], places=9)

    def test_catchup_enabled_without_stall_reports_no_event(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("catchup-no-stall.pcm", 7680),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=2)
        self.assertEqual(0, diagnostics["catchup_event_count"])
        self.assertEqual(0, diagnostics["catchup_chunk_count"])

    def test_experimental_pacing_does_not_accumulate_send_overhead(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock, send_overhead=0.001)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("experimental-ten-seconds.pcm", 480000),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=2)
        self.assertEqual(500, len(connection.sent_at))
        self.assertAlmostEqual(9.92, connection.sent_at[-1], places=9)
        self.assertLess(diagnostics["send_span_seconds"], 10.0)
        self.assertEqual(0, diagnostics["rebases"])

    def test_prebuffer_respects_cancel_after_byte_limit(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        sent = client.send_pcm(
            connection, self.pcm("cancel-limit.pcm", 96000),
            maximum_bytes=48000, clock=fake_clock.monotonic,
            sleeper=fake_clock.sleep, prebuffer_chunks=4,
            max_catchup_chunks=2)
        self.assertEqual(48000, sent)
        self.assertEqual(50, len(connection.sent_at))

    def test_experimental_option_validation(self):
        for prebuffer_chunks, max_catchup_chunks in (
                (-1, 0), (5, 0), (0, -1), (0, 4)):
            with self.assertRaises(ValueError):
                client.validate_experiment_options(
                    prebuffer_chunks, max_catchup_chunks)
        client.validate_experiment_options(0, 0)
        client.validate_experiment_options(4, 3)

    def test_experimental_cli_defaults_and_integer_options(self):
        parser = client.build_parser()
        defaults = parser.parse_args(
            ["normal", "--host", "localhost", "--port", "22222",
             "--pcm-a", "test.pcm"])
        self.assertEqual(0, defaults.prebuffer_chunks)
        self.assertEqual(0, defaults.max_catchup_chunks)
        configured = parser.parse_args(
            ["normal", "--host", "localhost", "--port", "22222",
             "--pcm-a", "test.pcm", "--prebuffer-chunks", "4",
             "--max-catchup-chunks", "2"])
        self.assertEqual(4, configured.prebuffer_chunks)
        self.assertEqual(2, configured.max_catchup_chunks)
        with self.assertRaises(SystemExit):
            parser.parse_args(
                ["normal", "--host", "localhost", "--port", "22222",
                 "--pcm-a", "test.pcm", "--prebuffer-chunks", "3.5"])

    def test_c3_cli_validation_accepts_max_catchup_three(self):
        client.validate_experiment_options(4, 3)
        args = client.build_parser().parse_args(
            ["normal", "--host", "localhost", "--port", "22222",
             "--pcm-a", "test.pcm", "--prebuffer-chunks", "4",
             "--max-catchup-chunks", "3"])
        self.assertEqual(4, args.prebuffer_chunks)
        self.assertEqual(3, args.max_catchup_chunks)

    def test_c3_recovers_observed_43_080_ms_stall(self):
        fake_clock = OversleepClock(0.043080)
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("c3-43ms.pcm", 8640),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=3)
        self.assertEqual(1, diagnostics["catchup_event_count"])
        self.assertEqual(3, diagnostics["catchup_chunk_count"])
        self.assertEqual(3, diagnostics["maximum_catchup_burst"])
        self.assertEqual(0, diagnostics["rebases"])
        self.assertAlmostEqual(0.08, connection.sent_at[7], places=9)

    def test_c3_recovers_observed_52_060_ms_stall(self):
        fake_clock = OversleepClock(0.052060)
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("c3-52ms.pcm", 8640),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=3)
        self.assertEqual(1, diagnostics["catchup_event_count"])
        self.assertEqual(3, diagnostics["catchup_chunk_count"])
        self.assertEqual(3, diagnostics["maximum_catchup_burst"])
        self.assertEqual(0, diagnostics["rebases"])
        self.assertAlmostEqual(0.08, connection.sent_at[7], places=9)

    def test_c3_recovery_boundary_includes_59_999_and_60_ms(self):
        for suffix, oversleep in (("59_999", 0.059999), ("60", 0.06)):
            fake_clock = OversleepClock(oversleep)
            connection = TimedConnection(fake_clock)
            diagnostics = {}
            client.send_pcm(
                connection, self.pcm("c3-boundary-{0}.pcm".format(suffix), 7680),
                clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
                diagnostics=diagnostics, prebuffer_chunks=4,
                max_catchup_chunks=3)
            self.assertEqual(1, diagnostics["catchup_event_count"])
            self.assertEqual(0, diagnostics["rebases"])
            self.assertLessEqual(diagnostics["maximum_catchup_burst"], 3)

    def test_c3_recovery_boundary_rebases_at_60_001_ms(self):
        fake_clock = OversleepClock(0.060001)
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("c3-over-boundary.pcm", 7680),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=3)
        self.assertEqual(0, diagnostics["catchup_event_count"])
        self.assertEqual(1, diagnostics["rebases"])

    def test_c3_catchup_burst_never_exceeds_three(self):
        fake_clock = OversleepClock(0.052060)
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("c3-burst-bound.pcm", 11520),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=3)
        self.assertEqual(3, diagnostics["maximum_catchup_burst"])
        recovery_times = connection.sent_at[4:]
        longest_equal_run = 1
        current_run = 1
        for index in range(1, len(recovery_times)):
            if abs(recovery_times[index] - recovery_times[index - 1]) < 1e-12:
                current_run += 1
                longest_equal_run = max(longest_equal_run, current_run)
            else:
                current_run = 1
        self.assertLessEqual(longest_equal_run, 3)

    def test_c3_exhausted_budget_waits_before_fourth_data(self):
        fake_clock = OversleepClock(0.052060)
        connection = TimedConnection(
            fake_clock, send_overheads={5: 0.01, 6: 0.01, 7: 0.01})
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("c3-exhausted.pcm", 9600),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=3)
        self.assertAlmostEqual(0.072060, connection.sent_at[4], places=9)
        self.assertAlmostEqual(0.082060, connection.sent_at[5], places=9)
        self.assertAlmostEqual(0.092060, connection.sent_at[6], places=9)
        self.assertAlmostEqual(0.122060, connection.sent_at[7], places=9)
        self.assertEqual(3, diagnostics["maximum_catchup_burst"])
        self.assertEqual(1, diagnostics["rebases"])

    def test_c3_repeated_observed_stalls_recover_without_lag(self):
        fake_clock = SelectedOversleepClock({1: 0.043080, 4: 0.052060})
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("c3-repeated.pcm", 14400),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=3)
        self.assertEqual(2, diagnostics["catchup_event_count"])
        self.assertEqual(6, diagnostics["catchup_chunk_count"])
        self.assertEqual(3, diagnostics["maximum_catchup_burst"])
        self.assertEqual(0, diagnostics["rebases"])
        self.assertAlmostEqual(0.22, connection.sent_at[-1], places=9)

    def test_c3_mixed_stalls_apply_catchup_catchup_rebase_policy(self):
        fake_clock = SelectedOversleepClock(
            {1: 0.043080, 4: 0.052060, 7: 0.08})
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("c3-mixed.pcm", 19200),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=3)
        self.assertEqual(2, diagnostics["catchup_event_count"])
        self.assertEqual(6, diagnostics["catchup_chunk_count"])
        self.assertEqual(3, diagnostics["maximum_catchup_burst"])
        self.assertEqual(1, diagnostics["rebases"])

    def test_c3_large_180_ms_stall_rebases_without_recovery_burst(self):
        fake_clock = OversleepClock(0.18)
        connection = TimedConnection(fake_clock)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("c3-large-stall.pcm", 7680),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=3)
        self.assertEqual(0, diagnostics["catchup_event_count"])
        self.assertEqual(1, diagnostics["rebases"])

    def test_c3_cancel_after_byte_limit_remains_48000(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock)
        sent = client.send_pcm(
            connection, self.pcm("c3-cancel-limit.pcm", 96000),
            maximum_bytes=48000, clock=fake_clock.monotonic,
            sleeper=fake_clock.sleep, prebuffer_chunks=4,
            max_catchup_chunks=3)
        self.assertEqual(48000, sent)
        self.assertEqual(50, len(connection.sent_at))

    def test_c3_cancel_restart_sends_exactly_one_second_before_cancel(self):
        def handler(connection, events):
            self.assertEqual(client.COMMAND, receive_frame(connection))
            send_response(connection, 0x80, 0x01)
            self.assertEqual(client.START, receive_frame(connection))
            send_response(connection, 0x80, 0x02)
            pcm_bytes = 0
            for unused in range(50):
                body = receive_frame(connection)
                self.assertEqual(client.DATA, body[:1])
                pcm_bytes += len(body) - 1
            events.append("A_BYTES={0}".format(pcm_bytes))
            self.assertEqual(client.CANCEL, receive_frame(connection))
            events.append("CANCEL")
            send_response(connection, 0x80, 0x04)
            self.assertEqual(client.START, receive_frame(connection))
            send_response(connection, 0x80, 0x02)
            body = receive_frame(connection)
            self.assertEqual(client.DATA, body[:1])
            events.append("B_DATA")
            self.assertEqual(client.END, receive_frame(connection))
            send_response(connection, 0x80, 0x03)

        server = MockServer(handler)
        server.start()
        fake_clock = FakeClock()
        original_clock = client.time.monotonic
        original_sleep = client.time.sleep
        client.time.monotonic = fake_clock.monotonic
        client.time.sleep = fake_clock.sleep
        try:
            client.run_cancel_restart(
                "127.0.0.1", server.port, 3.0,
                self.pcm("c3-cancel-a.pcm", 48000),
                self.pcm("c3-cancel-b.pcm", 960), 1.0, 4, 3)
        finally:
            client.time.monotonic = original_clock
            client.time.sleep = original_sleep
            server.finish()
        self.assertEqual(["A_BYTES=48000", "CANCEL", "B_DATA"], server.events)

    def test_c3_send_overhead_does_not_accumulate(self):
        fake_clock = FakeClock()
        connection = TimedConnection(fake_clock, send_overhead=0.001)
        diagnostics = {}
        client.send_pcm(
            connection, self.pcm("c3-ten-seconds.pcm", 480000),
            clock=fake_clock.monotonic, sleeper=fake_clock.sleep,
            diagnostics=diagnostics, prebuffer_chunks=4,
            max_catchup_chunks=3)
        self.assertEqual(500, len(connection.sent_at))
        self.assertAlmostEqual(9.92, connection.sent_at[-1], places=9)
        self.assertLess(diagnostics["send_span_seconds"], 10.0)
        self.assertEqual(0, diagnostics["rebases"])

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
