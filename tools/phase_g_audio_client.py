#!/usr/bin/env python3
"""Minimal paced client for RobotController audio_stream_v1.

This client sends raw 24 kHz, mono, signed 16-bit little-endian PCM. It does
not create audio, access hardware, or connect to any external API.
"""

from __future__ import print_function

import argparse
import datetime
import os
import socket
import struct
import sys
import time


COMMAND = b"audio_stream_v1"
START = b"\x01"
DATA = b"\x02"
END = b"\x03"
CANCEL = b"\x04"

STATUS_NAMES = {
    0x01: "CONNECTION_READY",
    0x02: "STARTED",
    0x03: "ENDED",
    0x04: "CANCELLED",
}
ERROR_NAMES = {
    0x01: "BUSY",
    0x02: "PROTOCOL_ERROR",
    0x03: "AUDIO_ERROR",
    0x04: "QUEUE_OVERFLOW",
}

BYTES_PER_SECOND = 24000 * 1 * 2
MAX_PCM_BYTES = 960
MAX_EXPERIMENT_PREBUFFER_CHUNKS = 4
MAX_EXPERIMENT_CATCHUP_CHUNKS = 3


class ProtocolError(Exception):
    """Raised when a response violates the audio_stream_v1 contract."""


class ServerError(Exception):
    """Raised when the server returns a documented ERROR response."""

    def __init__(self, name, code):
        Exception.__init__(self, "Server ERROR: {0} (0x{1:02X})".format(name, code))
        self.name = name
        self.code = code


def log(message):
    """Print one timestamped client event."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")
    print("[{0}] {1}".format(stamp, message), flush=True)


def send_frame(connection, payload):
    """Send one legacy 4-byte big-endian length-prefixed frame."""
    connection.sendall(struct.pack(">I", len(payload)) + payload)


def receive_exact(connection, length):
    """Read exactly length bytes or raise ProtocolError on EOF."""
    chunks = []
    remaining = length
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise ProtocolError("Connection closed during framed response.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def receive_response(connection):
    """Decode one STATUS or ERROR response frame."""
    header = receive_exact(connection, 4)
    length = struct.unpack(">I", header)[0]
    if length != 2:
        raise ProtocolError("Response body length is {0}, expected 2.".format(length))
    body = receive_exact(connection, length)
    response_type = body[0]
    code = body[1]
    if response_type == 0x80:
        name = STATUS_NAMES.get(code)
        if name is None:
            raise ProtocolError("Unknown STATUS code 0x{0:02X}.".format(code))
        log("received STATUS {0}".format(name))
        return "STATUS", name
    if response_type == 0x81:
        name = ERROR_NAMES.get(code, "UNKNOWN_ERROR")
        log("received ERROR {0} (0x{1:02X})".format(name, code))
        raise ServerError(name, code)
    raise ProtocolError("Unknown response type 0x{0:02X}.".format(response_type))


def expect_status(connection, expected):
    """Wait at a protocol barrier and require the expected STATUS."""
    kind, actual = receive_response(connection)
    if kind != "STATUS" or actual != expected:
        raise ProtocolError("Expected STATUS {0}, received {1} {2}.".format(
            expected, kind, actual))


def send_barrier(connection, payload, name, expected):
    """Send START/END/CANCEL and wait before allowing the next action."""
    log("sending barrier {0}".format(name))
    send_frame(connection, payload)
    expect_status(connection, expected)


def validate_pcm(path, minimum_bytes=2):
    """Validate raw PCM byte alignment and a caller-selected minimum size."""
    size = os.path.getsize(path)
    if size < minimum_bytes:
        raise ValueError("PCM file is too short: {0} bytes (need at least {1}).".format(
            size, minimum_bytes))
    if size % 2:
        raise ValueError("PCM file size must be even for mono S16_LE: {0}.".format(size))
    return size


def validate_experiment_options(prebuffer_chunks, max_catchup_chunks):
    """Validate the deliberately small client-side experiment bounds."""
    if not (0 <= prebuffer_chunks <= MAX_EXPERIMENT_PREBUFFER_CHUNKS):
        raise ValueError("--prebuffer-chunks must be between 0 and {0}.".format(
            MAX_EXPERIMENT_PREBUFFER_CHUNKS))
    if not (0 <= max_catchup_chunks <= MAX_EXPERIMENT_CATCHUP_CHUNKS):
        raise ValueError(
            "--max-catchup-chunks must be between 0 and {0}.".format(
                MAX_EXPERIMENT_CATCHUP_CHUNKS))


def scheduled_pcm_seconds(pcm_bytes, prebuffer_chunks):
    """Return the absolute schedule offset after the initial PCM burst."""
    lead_bytes = max(0, prebuffer_chunks - 1) * MAX_PCM_BYTES
    return float(max(0, pcm_bytes - lead_bytes)) / BYTES_PER_SECOND


def send_pcm(connection, path, maximum_bytes=None, clock=None, sleeper=None,
             diagnostics=None, prebuffer_chunks=0, max_catchup_chunks=0):
    """Send DATA frames no faster than 48,000 bytes/second.

    Chunk deadlines follow an absolute byte-rate schedule so normal send
    overhead does not accumulate. An optional initial burst retains its lead
    in that schedule. A bounded catch-up event counts the late current DATA as
    its first chunk; lateness beyond that configured burst is rebased.
    When supplied, diagnostics is populated with aggregate pacing measurements.
    """
    validate_experiment_options(prebuffer_chunks, max_catchup_chunks)
    if clock is None:
        clock = time.monotonic
    if sleeper is None:
        sleeper = time.sleep
    total = 0
    chunks = 0
    rebases = 0
    max_lateness = 0.0
    max_send = 0.0
    max_sleep_overshoot = 0.0
    initial_prebuffer_chunks = 0
    catchup_event_count = 0
    catchup_chunk_count = 0
    maximum_catchup_burst = 0
    rebase_after_unrecoverable_stall_count = 0
    catchup_active = False
    current_catchup_burst = 0
    first_send_start = None
    last_send_end = None
    schedule_start = clock()
    with open(path, "rb") as pcm_file:
        while maximum_bytes is None or total < maximum_bytes:
            wanted = MAX_PCM_BYTES
            if maximum_bytes is not None:
                wanted = min(wanted, maximum_bytes - total)
            chunk = pcm_file.read(wanted)
            if not chunk:
                break
            if len(chunk) % 2:
                raise ValueError("PCM DATA chunk is not 2-byte frame aligned.")
            schedule_offset = scheduled_pcm_seconds(total, prebuffer_chunks)
            target = schedule_start + schedule_offset
            now = clock()
            delay = target - now
            if delay > 0:
                catchup_active = False
                current_catchup_burst = 0
                sleeper(delay)
                now = clock()
                max_sleep_overshoot = max(
                    max_sleep_overshoot, max(0.0, now - target))
            chunk_duration = float(len(chunk)) / BYTES_PER_SECOND
            lateness = max(0.0, now - target)
            max_lateness = max(max_lateness, lateness)
            rebased = False
            wait_after_exhausted_catchup = False
            catchup_started = False
            if catchup_active and lateness > 0.0:
                if current_catchup_burst < max_catchup_chunks:
                    current_catchup_burst += 1
                    catchup_chunk_count += 1
                    maximum_catchup_burst = max(
                        maximum_catchup_burst, current_catchup_burst)
                else:
                    rebased = True
                    wait_after_exhausted_catchup = True
            elif catchup_active:
                catchup_active = False
                current_catchup_burst = 0
            elif lateness > chunk_duration:
                recoverable_lateness = max_catchup_chunks * chunk_duration
                if (max_catchup_chunks > 0
                        and lateness <= recoverable_lateness):
                    catchup_active = True
                    current_catchup_burst = 1
                    catchup_event_count += 1
                    catchup_chunk_count += 1
                    maximum_catchup_burst = max(
                        maximum_catchup_burst, current_catchup_burst)
                    catchup_started = True
                else:
                    rebased = True
            if rebased:
                rebases += 1
                rebase_after_unrecoverable_stall_count += 1
                catchup_active = False
                current_catchup_burst = 0
                schedule_start = now - schedule_offset
                target = now
                if wait_after_exhausted_catchup:
                    target = now + chunk_duration
                    schedule_start = target - schedule_offset
                    sleeper(chunk_duration)
                    now = clock()
                    max_sleep_overshoot = max(
                        max_sleep_overshoot, max(0.0, now - target))
            send_start = clock()
            if first_send_start is None:
                first_send_start = send_start
            send_frame(connection, DATA + chunk)
            send_end = clock()
            last_send_end = send_end
            max_send = max(max_send, max(0.0, send_end - send_start))
            chunks += 1
            total += len(chunk)
            if chunks <= prebuffer_chunks:
                initial_prebuffer_chunks += 1
            if catchup_started:
                log("pacing catchup chunk={0} lateness_ms={1:.3f} "
                    "burst_limit={2}".format(
                        chunks, lateness * 1000.0, max_catchup_chunks))
            if rebased:
                log("pacing rebase chunk={0} lateness_ms={1:.3f}".format(
                    chunks, lateness * 1000.0))
    send_span = 0.0
    if first_send_start is not None and last_send_end is not None:
        send_span = max(0.0, last_send_end - first_send_start)
    effective_rate = 0.0
    if send_span > 0.0:
        effective_rate = float(total) / send_span
    values = {
        "pcm_bytes": total,
        "chunks": chunks,
        "nominal_seconds": float(total) / BYTES_PER_SECOND,
        "send_span_seconds": send_span,
        "effective_rate": effective_rate,
        "rebases": rebases,
        "max_lateness_seconds": max_lateness,
        "max_send_seconds": max_send,
        "max_sleep_overshoot_seconds": max_sleep_overshoot,
        "prebuffer_chunks": prebuffer_chunks,
        "initial_prebuffer_chunks": initial_prebuffer_chunks,
        "max_catchup_chunks": max_catchup_chunks,
        "catchup_event_count": catchup_event_count,
        "catchup_chunk_count": catchup_chunk_count,
        "maximum_catchup_burst": maximum_catchup_burst,
        "rebase_after_unrecoverable_stall_count":
            rebase_after_unrecoverable_stall_count,
    }
    if diagnostics is not None:
        diagnostics.update(values)
    log("pacing pcm_bytes={0} chunks={1} nominal_seconds={2:.3f}".format(
        total, chunks, values["nominal_seconds"]))
    log("pacing send_span_seconds={0:.3f} effective_rate={1:.1f}".format(
        send_span, effective_rate))
    log("pacing prebuffer_chunks={0} initial_prebuffer_sent={1} "
        "max_catchup_chunks={2}".format(
            prebuffer_chunks, initial_prebuffer_chunks, max_catchup_chunks))
    log("pacing catchup_events={0} catchup_chunks={1} max_catchup_burst={2} "
        "unrecoverable_rebases={3}".format(
            catchup_event_count, catchup_chunk_count, maximum_catchup_burst,
            rebase_after_unrecoverable_stall_count))
    log("pacing rebases={0} max_lateness_ms={1:.3f} max_send_ms={2:.3f} "
        "max_sleep_overshoot_ms={3:.3f}".format(
            rebases, max_lateness * 1000.0, max_send * 1000.0,
            max_sleep_overshoot * 1000.0))
    return total


def open_stream(host, port, timeout):
    """Connect, select audio_stream_v1, and wait for CONNECTION_READY."""
    log("connecting to {0}:{1}".format(host, port))
    connection = socket.create_connection((host, port), timeout)
    connection.settimeout(timeout)
    try:
        log("sending command audio_stream_v1")
        send_frame(connection, COMMAND)
        expect_status(connection, "CONNECTION_READY")
        return connection
    except Exception:
        connection.close()
        raise


def run_normal(host, port, timeout, pcm_a, prebuffer_chunks=0,
               max_catchup_chunks=0):
    """Run CONNECTION_READY -> STARTED -> DATA -> ENDED."""
    validate_pcm(pcm_a)
    connection = open_stream(host, port, timeout)
    try:
        send_barrier(connection, START, "START", "STARTED")
        sent = send_pcm(
            connection, pcm_a, prebuffer_chunks=prebuffer_chunks,
            max_catchup_chunks=max_catchup_chunks)
        send_barrier(connection, END, "END", "ENDED")
        log("result NORMAL PASS pcm_bytes={0}".format(sent))
    finally:
        connection.close()


def run_probe(host, port, timeout, hold_seconds):
    """Receive CONNECTION_READY without sending START or opening ALSA."""
    if hold_seconds < 0:
        raise ValueError("--hold-seconds must not be negative.")
    connection = open_stream(host, port, timeout)
    try:
        if hold_seconds:
            log("holding connection for {0:.3f} seconds".format(hold_seconds))
            time.sleep(hold_seconds)
        log("result PROBE PASS")
    finally:
        connection.close()


def run_cancel_restart(host, port, timeout, pcm_a, pcm_b, cancel_after,
                       prebuffer_chunks=0, max_catchup_chunks=0):
    """Cancel A and complete fresh B on one persistent connection."""
    if cancel_after <= 0:
        raise ValueError("--cancel-after must be greater than zero.")
    cancel_bytes = int(cancel_after * BYTES_PER_SECOND)
    if cancel_bytes % 2:
        cancel_bytes += 1
    validate_pcm(pcm_a, cancel_bytes)
    validate_pcm(pcm_b)
    connection = open_stream(host, port, timeout)
    try:
        send_barrier(connection, START, "START A", "STARTED")
        sent_a = send_pcm(
            connection, pcm_a, cancel_bytes,
            prebuffer_chunks=prebuffer_chunks,
            max_catchup_chunks=max_catchup_chunks)
        log("sending CANCEL at stream_seconds={0:.3f}".format(
            float(sent_a) / BYTES_PER_SECOND))
        send_barrier(connection, CANCEL, "CANCEL", "CANCELLED")

        send_barrier(connection, START, "START B", "STARTED")
        sent_b = send_pcm(
            connection, pcm_b, prebuffer_chunks=prebuffer_chunks,
            max_catchup_chunks=max_catchup_chunks)
        send_barrier(connection, END, "END B", "ENDED")
        log("result CANCEL_RESTART PASS pcm_a_bytes={0} pcm_b_bytes={1}".format(
            sent_a, sent_b))
    finally:
        connection.close()


def run_invalid_state(host, port, timeout):
    """Send one END record while IDLE and require PROTOCOL_ERROR plus EOF."""
    connection = open_stream(host, port, timeout)
    try:
        log("sending invalid END while IDLE")
        send_frame(connection, END)
        try:
            receive_response(connection)
        except ServerError as error:
            if error.name != "PROTOCOL_ERROR":
                raise ProtocolError(
                    "Expected PROTOCOL_ERROR, received {0}.".format(error.name))
        else:
            raise ProtocolError("Expected PROTOCOL_ERROR, received STATUS.")
        if connection.recv(1) != b"":
            raise ProtocolError("Connection remained open after PROTOCOL_ERROR.")
        log("result INVALID_STATE PASS error=PROTOCOL_ERROR connection=CLOSED")
    finally:
        connection.close()


def run_disconnect_active(host, port, timeout, pcm_a, reconnect_delay,
                          prebuffer_chunks=0, max_catchup_chunks=0):
    """Disconnect after one DATA chunk, then require a fresh connection slot."""
    validate_pcm(pcm_a, MAX_PCM_BYTES)
    if reconnect_delay < 0:
        raise ValueError("--reconnect-delay must not be negative.")
    connection = open_stream(host, port, timeout)
    try:
        send_barrier(connection, START, "START", "STARTED")
        sent = send_pcm(
            connection, pcm_a, MAX_PCM_BYTES,
            prebuffer_chunks=prebuffer_chunks,
            max_catchup_chunks=max_catchup_chunks)
        log("closing active connection after PCM bytes={0}".format(sent))
    finally:
        connection.close()
    if reconnect_delay:
        time.sleep(reconnect_delay)
    probe = open_stream(host, port, timeout)
    try:
        log("result DISCONNECT_ACTIVE PASS fresh_connection=CONNECTION_READY")
    finally:
        probe.close()


def build_parser():
    parser = argparse.ArgumentParser(
        description="Send paced 24 kHz mono S16_LE raw PCM to audio_stream_v1.")
    parser.add_argument(
        "mode",
        choices=("probe", "normal", "cancel-restart", "invalid-state",
                 "disconnect-active"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--pcm-a")
    parser.add_argument("--pcm-b")
    parser.add_argument("--cancel-after", type=float, default=1.0,
                        help="seconds of PCM A sent before CANCEL (default: 1.0)")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="socket/barrier timeout seconds (default: 10.0)")
    parser.add_argument("--hold-seconds", type=float, default=0.0,
                        help="probe connection hold time for BUSY checks")
    parser.add_argument("--reconnect-delay", type=float, default=0.5,
                        help="seconds before reconnect after active disconnect")
    parser.add_argument(
        "--prebuffer-chunks", type=int, default=0,
        help="EXPERIMENTAL initial DATA burst chunks (default: 0; range: 0..4)")
    parser.add_argument(
        "--max-catchup-chunks", type=int, default=0,
        help="EXPERIMENTAL maximum consecutive recovery DATA chunks, including "
             "the late current chunk (default: 0; range: 0..3)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not (1 <= args.port <= 65535):
        raise ValueError("--port must be between 1 and 65535.")
    if args.timeout <= 0:
        raise ValueError("--timeout must be greater than zero.")
    validate_experiment_options(
        args.prebuffer_chunks, args.max_catchup_chunks)
    if args.mode == "probe":
        run_probe(args.host, args.port, args.timeout, args.hold_seconds)
    elif args.mode == "normal":
        if not args.pcm_a:
            raise ValueError("normal requires --pcm-a.")
        run_normal(
            args.host, args.port, args.timeout, args.pcm_a,
            args.prebuffer_chunks, args.max_catchup_chunks)
    elif args.mode == "cancel-restart":
        if not args.pcm_a or not args.pcm_b:
            raise ValueError("cancel-restart requires --pcm-a and --pcm-b.")
        run_cancel_restart(args.host, args.port, args.timeout,
                           args.pcm_a, args.pcm_b, args.cancel_after,
                           args.prebuffer_chunks, args.max_catchup_chunks)
    elif args.mode == "invalid-state":
        run_invalid_state(args.host, args.port, args.timeout)
    else:
        if not args.pcm_a:
            raise ValueError("disconnect-active requires --pcm-a.")
        run_disconnect_active(args.host, args.port, args.timeout, args.pcm_a,
                              args.reconnect_delay, args.prebuffer_chunks,
                              args.max_catchup_chunks)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (IOError, OSError, ProtocolError, ServerError, ValueError) as error:
        log("result FAIL: {0}".format(error))
        sys.exit(1)
