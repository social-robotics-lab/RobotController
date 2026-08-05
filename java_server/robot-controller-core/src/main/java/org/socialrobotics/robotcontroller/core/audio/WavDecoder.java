package org.socialrobotics.robotcontroller.core.audio;

import java.util.Arrays;

/** Strict memory-only decoder for the initial signed 16-bit PCM WAV subset. */
public final class WavDecoder {
    private static final int RIFF_HEADER_BYTES = 12;
    private static final int CHUNK_HEADER_BYTES = 8;
    private static final int PCM_FORMAT_TAG = 1;

    private WavDecoder() {
    }

    /** Validates and decodes one bounded WAV payload into canonical PCM. */
    public static PcmAudioData decode(byte[] wavPayload, WavDecodeLimits limits)
            throws WavDecodingException {
        if (wavPayload == null) {
            throw new NullPointerException("wavPayload");
        }
        if (limits == null) {
            throw new NullPointerException("limits");
        }
        if (wavPayload.length > limits.maximumPayloadBytes()) {
            throw new WavDecodingException("WAV payload exceeds maximum size");
        }
        if (wavPayload.length < RIFF_HEADER_BYTES) {
            throw new WavDecodingException("truncated RIFF/WAVE header");
        }
        requireAscii(wavPayload, 0, "RIFF", "missing RIFF signature");
        requireAscii(wavPayload, 8, "WAVE", "missing WAVE signature");
        long declaredRiffBytes = littleUnsignedInt(wavPayload, 4);
        if (declaredRiffBytes + 8L != wavPayload.length) {
            throw new WavDecodingException("RIFF size does not match payload length");
        }

        Format format = null;
        int dataOffset = -1;
        int dataLengthBytes = -1;
        int offset = RIFF_HEADER_BYTES;
        while (offset < wavPayload.length) {
            if (wavPayload.length - offset < CHUNK_HEADER_BYTES) {
                throw new WavDecodingException("truncated WAV chunk header");
            }
            String chunkId = ascii(wavPayload, offset, 4);
            long chunkLength = littleUnsignedInt(wavPayload, offset + 4);
            long chunkDataOffset = offset + (long) CHUNK_HEADER_BYTES;
            long chunkEnd = chunkDataOffset + chunkLength;
            if (chunkEnd > wavPayload.length) {
                throw new WavDecodingException("WAV chunk exceeds payload boundary: " + chunkId);
            }
            if ("fmt ".equals(chunkId)) {
                if (format != null) {
                    throw new WavDecodingException("duplicate fmt chunk");
                }
                format = parseFormat(wavPayload, (int) chunkDataOffset, chunkLength);
            } else if ("data".equals(chunkId)) {
                if (dataOffset >= 0) {
                    throw new WavDecodingException("duplicate data chunk");
                }
                if (chunkLength > Integer.MAX_VALUE) {
                    throw new WavDecodingException("data chunk is too large");
                }
                dataOffset = (int) chunkDataOffset;
                dataLengthBytes = (int) chunkLength;
            }
            long paddedEnd = chunkEnd + (chunkLength & 1L);
            if (paddedEnd > wavPayload.length) {
                throw new WavDecodingException("missing WAV chunk padding byte");
            }
            offset = (int) paddedEnd;
        }
        if (format == null) {
            throw new WavDecodingException("missing fmt chunk");
        }
        if (dataOffset < 0) {
            throw new WavDecodingException("missing data chunk");
        }
        if (dataLengthBytes % format.frameSizeBytes != 0) {
            throw new WavDecodingException("data chunk is not frame aligned");
        }
        long frameCount = dataLengthBytes / format.frameSizeBytes;
        long durationMilliseconds = frameCount == 0L
                ? 0L
                : (frameCount * 1000L + format.sampleRateHz - 1L) / format.sampleRateHz;
        if (durationMilliseconds > limits.maximumDurationMilliseconds()) {
            throw new WavDecodingException("decoded audio duration exceeds maximum");
        }
        byte[] pcmBytes = Arrays.copyOfRange(
                wavPayload,
                dataOffset,
                dataOffset + dataLengthBytes);
        return new PcmAudioData(format.sampleRateHz, format.channels, pcmBytes);
    }

    private static Format parseFormat(byte[] bytes, int offset, long chunkLength)
            throws WavDecodingException {
        if (chunkLength < 16L) {
            throw new WavDecodingException("fmt chunk is shorter than PCM format data");
        }
        int formatTag = littleUnsignedShort(bytes, offset);
        int channels = littleUnsignedShort(bytes, offset + 2);
        long sampleRate = littleUnsignedInt(bytes, offset + 4);
        long byteRate = littleUnsignedInt(bytes, offset + 8);
        int frameSizeBytes = littleUnsignedShort(bytes, offset + 12);
        int bitsPerSample = littleUnsignedShort(bytes, offset + 14);
        if (formatTag != PCM_FORMAT_TAG) {
            throw new WavDecodingException("unsupported WAV encoding: " + formatTag);
        }
        if (channels < 1 || channels > 2) {
            throw new WavDecodingException("only mono and stereo WAV are supported");
        }
        if (bitsPerSample != PcmAudioData.BITS_PER_SAMPLE) {
            throw new WavDecodingException("only signed 16-bit PCM WAV is supported");
        }
        if (sampleRate <= 0L || sampleRate > Integer.MAX_VALUE) {
            throw new WavDecodingException("invalid sample rate");
        }
        int expectedFrameSizeBytes = channels * (bitsPerSample / 8);
        if (frameSizeBytes != expectedFrameSizeBytes) {
            throw new WavDecodingException("inconsistent PCM frame size");
        }
        if (byteRate != sampleRate * frameSizeBytes) {
            throw new WavDecodingException("inconsistent PCM byte rate");
        }
        return new Format((int) sampleRate, channels, frameSizeBytes);
    }

    private static int littleUnsignedShort(byte[] bytes, int offset) {
        return (bytes[offset] & 0xff) | ((bytes[offset + 1] & 0xff) << 8);
    }

    private static long littleUnsignedInt(byte[] bytes, int offset) {
        return ((long) bytes[offset] & 0xffL)
                | (((long) bytes[offset + 1] & 0xffL) << 8)
                | (((long) bytes[offset + 2] & 0xffL) << 16)
                | (((long) bytes[offset + 3] & 0xffL) << 24);
    }

    private static void requireAscii(
            byte[] bytes,
            int offset,
            String expected,
            String message) throws WavDecodingException {
        if (!expected.equals(ascii(bytes, offset, expected.length()))) {
            throw new WavDecodingException(message);
        }
    }

    private static String ascii(byte[] bytes, int offset, int length) {
        StringBuilder result = new StringBuilder(length);
        for (int index = 0; index < length; index++) {
            result.append((char) (bytes[offset + index] & 0xff));
        }
        return result.toString();
    }

    private static final class Format {
        private final int sampleRateHz;
        private final int channels;
        private final int frameSizeBytes;

        private Format(int sampleRateHz, int channels, int frameSizeBytes) {
            this.sampleRateHz = sampleRateHz;
            this.channels = channels;
            this.frameSizeBytes = frameSizeBytes;
        }
    }
}
