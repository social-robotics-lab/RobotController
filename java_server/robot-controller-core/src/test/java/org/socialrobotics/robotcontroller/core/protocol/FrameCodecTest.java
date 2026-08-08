package org.socialrobotics.robotcontroller.core.protocol;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

import org.junit.Test;

public final class FrameCodecTest {
    @Test
    public void writesAndReadsBigEndianFrame() throws Exception {
        byte[] payload = new byte[] {0x01, 0x23, (byte) 0xfe};
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        FrameCodec.writeFrame(output, payload, 16);

        assertArrayEquals(
                new byte[] {0x00, 0x00, 0x00, 0x03, 0x01, 0x23, (byte) 0xfe},
                output.toByteArray());
        assertArrayEquals(
                payload,
                FrameCodec.readFrame(new ByteArrayInputStream(output.toByteArray()), 16));
    }

    @Test
    public void readsPartialHeaderAndPayload() throws Exception {
        byte[] framed = new byte[] {0, 0, 0, 4, 9, 8, 7, 6};

        byte[] decoded = FrameCodec.readFrame(new ChunkedInputStream(framed, 1), 4);

        assertArrayEquals(new byte[] {9, 8, 7, 6}, decoded);
    }

    @Test
    public void readsZeroLengthAsEmptyPayload() throws Exception {
        assertEquals(
                0,
                FrameCodec.readFrame(
                        new ByteArrayInputStream(new byte[] {0, 0, 0, 0}),
                        0).length);
    }

    @Test
    public void rejectsEofInHeader() throws Exception {
        for (int received = 0; received < 4; received++) {
            assertCodecFailure(new byte[received], 16, "frame header");
        }
    }

    @Test
    public void rejectsEofInPayload() throws Exception {
        assertCodecFailure(new byte[] {0, 0, 0, 2, 1}, 16, "frame payload");
    }

    @Test
    public void rejectsNegativeSignedLength() throws Exception {
        assertCodecFailure(
                new byte[] {(byte) 0x80, 0, 0, 0},
                Integer.MAX_VALUE,
                "negative frame length");
        assertCodecFailure(
                new byte[] {(byte) 0xff, (byte) 0xff, (byte) 0xff, (byte) 0xff},
                Integer.MAX_VALUE,
                "negative frame length");
    }

    @Test
    public void rejectsLengthAboveCallerMaximumBeforeAllocation() throws Exception {
        assertCodecFailure(new byte[] {0, 0, 1, 0}, 255, "exceeds maximum");
        assertCodecFailure(
                new byte[] {0x7f, (byte) 0xff, (byte) 0xff, (byte) 0xff},
                1_024,
                "exceeds maximum");
    }

    @Test
    public void acceptsExactCallerMaximumAndRejectsMaximumPlusOne() throws Exception {
        assertArrayEquals(
                new byte[] {1, 2, 3, 4},
                FrameCodec.readFrame(
                        new ByteArrayInputStream(new byte[] {0, 0, 0, 4, 1, 2, 3, 4}),
                        4));
        assertCodecFailure(new byte[] {0, 0, 0, 5}, 4, "exceeds maximum");

        try {
            FrameCodec.writeFrame(new ByteArrayOutputStream(), new byte[5], 4);
            fail("expected output maximum rejection");
        } catch (FrameCodecException expected) {
            // The outbound path applies the same caller-owned bound.
        }
    }

    private static void assertCodecFailure(byte[] bytes, int maximum, String messagePart)
            throws Exception {
        try {
            FrameCodec.readFrame(new ByteArrayInputStream(bytes), maximum);
            fail("expected FrameCodecException");
        } catch (FrameCodecException expected) {
            if (!expected.getMessage().contains(messagePart)) {
                fail("message did not contain '" + messagePart + "': " + expected.getMessage());
            }
        }
    }

    private static final class ChunkedInputStream extends InputStream {
        private final ByteArrayInputStream delegate;
        private final int maximumChunkBytes;

        private ChunkedInputStream(byte[] bytes, int maximumChunkBytes) {
            this.delegate = new ByteArrayInputStream(bytes);
            this.maximumChunkBytes = maximumChunkBytes;
        }

        @Override
        public int read() {
            return delegate.read();
        }

        @Override
        public int read(byte[] buffer, int offset, int length) throws IOException {
            return delegate.read(buffer, offset, Math.min(length, maximumChunkBytes));
        }
    }
}
