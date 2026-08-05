package org.socialrobotics.robotcontroller.core.protocol;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/** Pure codec for the legacy four-byte big-endian signed-length frame format. */
public final class FrameCodec {
    private static final int HEADER_BYTES = 4;

    private FrameCodec() {
    }

    /** Reads one bounded frame. A zero length is returned as an empty byte array. */
    public static byte[] readFrame(InputStream input, int maxLengthBytes) throws IOException {
        if (input == null) {
            throw new NullPointerException("input");
        }
        requireValidMaximum(maxLengthBytes);
        byte[] header = new byte[HEADER_BYTES];
        readFully(input, header, "frame header");
        int lengthBytes = ((header[0] & 0xff) << 24)
                | ((header[1] & 0xff) << 16)
                | ((header[2] & 0xff) << 8)
                | (header[3] & 0xff);
        if (lengthBytes < 0) {
            throw new FrameCodecException("negative frame length: " + lengthBytes);
        }
        if (lengthBytes > maxLengthBytes) {
            throw new FrameCodecException(
                    "frame length " + lengthBytes + " exceeds maximum " + maxLengthBytes);
        }
        byte[] payload = new byte[lengthBytes];
        readFully(input, payload, "frame payload");
        return payload;
    }

    /** Writes one bounded frame without closing or flushing the caller-owned stream. */
    public static void writeFrame(OutputStream output, byte[] payload, int maxLengthBytes)
            throws IOException {
        if (output == null) {
            throw new NullPointerException("output");
        }
        if (payload == null) {
            throw new NullPointerException("payload");
        }
        requireValidMaximum(maxLengthBytes);
        if (payload.length > maxLengthBytes) {
            throw new FrameCodecException(
                    "frame length " + payload.length + " exceeds maximum " + maxLengthBytes);
        }
        int lengthBytes = payload.length;
        output.write((lengthBytes >>> 24) & 0xff);
        output.write((lengthBytes >>> 16) & 0xff);
        output.write((lengthBytes >>> 8) & 0xff);
        output.write(lengthBytes & 0xff);
        output.write(payload);
    }

    private static void readFully(InputStream input, byte[] destination, String part)
            throws IOException {
        int offset = 0;
        while (offset < destination.length) {
            int count = input.read(destination, offset, destination.length - offset);
            if (count < 0) {
                throw new FrameCodecException(
                        "unexpected EOF while reading " + part + " at byte " + offset);
            }
            if (count == 0) {
                int single = input.read();
                if (single < 0) {
                    throw new FrameCodecException(
                            "unexpected EOF while reading " + part + " at byte " + offset);
                }
                destination[offset++] = (byte) single;
            } else {
                offset += count;
            }
        }
    }

    private static void requireValidMaximum(int maxLengthBytes) {
        if (maxLengthBytes < 0) {
            throw new IllegalArgumentException("maxLengthBytes must be non-negative");
        }
    }
}
