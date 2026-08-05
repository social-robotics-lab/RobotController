package org.socialrobotics.robotcontroller.core.audio;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;

import java.io.ByteArrayOutputStream;
import java.util.Arrays;

import org.junit.Test;

public final class WavDecoderTest {
    @Test
    public void decodesBoundedPcmWavInMemory() throws Exception {
        byte[] pcm = littleEndianSamples(new int[] {0, 1000, -1000, 32767});
        byte[] wav = wav(1, 8000, 16, pcm);

        PcmAudioData decoded = WavDecoder.decode(wav, new WavDecodeLimits(1024, 1000));

        assertEquals(8000, decoded.sampleRateHz());
        assertEquals(1, decoded.channels());
        assertEquals(4L, decoded.frameCount());
        assertArrayEquals(pcm, decoded.copyPcmBytes());
    }

    @Test
    public void rejectsMalformedRiffAndWaveSignatures() throws Exception {
        byte[] riff = wav(1, 8000, 16, littleEndianSamples(new int[] {1}));
        riff[0] = 'X';
        assertDecodeFailure(riff, 1024, 1000, "RIFF");

        byte[] wave = wav(1, 8000, 16, littleEndianSamples(new int[] {1}));
        wave[8] = 'X';
        assertDecodeFailure(wave, 1024, 1000, "WAVE");
    }

    @Test
    public void rejectsTruncatedChunkPayload() throws Exception {
        byte[] complete = wav(1, 8000, 16, littleEndianSamples(new int[] {1, 2}));
        byte[] truncated = Arrays.copyOf(complete, complete.length - 1);
        writeLittleInt(truncated, 4, truncated.length - 8);

        assertDecodeFailure(truncated, 1024, 1000, "boundary");
    }

    @Test
    public void rejectsOversizedPayloadBeforeDecode() throws Exception {
        byte[] wav = wav(1, 8000, 16, littleEndianSamples(new int[] {1, 2}));
        assertDecodeFailure(wav, wav.length - 1, 1000, "maximum size");
    }

    @Test
    public void rejectsUnsupportedSampleSize() throws Exception {
        byte[] wav = wav(1, 8000, 8, new byte[] {0, 1, 2, 3});
        assertDecodeFailure(wav, 1024, 1000, "16-bit");
    }

    @Test
    public void rejectsDecodedDurationOverLimit() throws Exception {
        byte[] pcm = new byte[8000 * 2];
        byte[] wav = wav(1, 8000, 16, pcm);
        assertDecodeFailure(wav, wav.length, 999, "duration");
    }

    @Test
    public void durationLimitRoundsUpAnyPartialMillisecond() throws Exception {
        byte[] wav = wav(1, 8000, 16, littleEndianSamples(new int[] {1}));
        assertDecodeFailure(wav, wav.length, 0, "duration");
    }

    @Test
    public void canonicalPcmDefensivelyCopiesInputAndOutput() {
        byte[] bytes = littleEndianSamples(new int[] {100});
        PcmAudioData audio = new PcmAudioData(8000, 1, bytes);
        bytes[0] = 0;
        byte[] copy = audio.copyPcmBytes();
        copy[0] = 0;

        assertEquals(100, audio.sampleAt(0, 0));
    }

    private static void assertDecodeFailure(
            byte[] wav,
            int maximumPayloadBytes,
            long maximumDurationMilliseconds,
            String messagePart) throws Exception {
        try {
            WavDecoder.decode(
                    wav,
                    new WavDecodeLimits(maximumPayloadBytes, maximumDurationMilliseconds));
            fail("expected WavDecodingException");
        } catch (WavDecodingException expected) {
            if (!expected.getMessage().contains(messagePart)) {
                fail("message did not contain '" + messagePart + "': " + expected.getMessage());
            }
        }
    }

    static byte[] littleEndianSamples(int[] samples) {
        byte[] result = new byte[samples.length * 2];
        for (int index = 0; index < samples.length; index++) {
            result[index * 2] = (byte) (samples[index] & 0xff);
            result[index * 2 + 1] = (byte) ((samples[index] >>> 8) & 0xff);
        }
        return result;
    }

    static byte[] wav(int channels, int sampleRateHz, int bitsPerSample, byte[] pcm) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        writeAscii(output, "RIFF");
        writeLittleInt(output, 36 + pcm.length);
        writeAscii(output, "WAVE");
        writeAscii(output, "fmt ");
        writeLittleInt(output, 16);
        writeLittleShort(output, 1);
        writeLittleShort(output, channels);
        int frameSize = channels * bitsPerSample / 8;
        writeLittleInt(output, sampleRateHz);
        writeLittleInt(output, sampleRateHz * frameSize);
        writeLittleShort(output, frameSize);
        writeLittleShort(output, bitsPerSample);
        writeAscii(output, "data");
        writeLittleInt(output, pcm.length);
        output.write(pcm, 0, pcm.length);
        return output.toByteArray();
    }

    private static void writeAscii(ByteArrayOutputStream output, String value) {
        for (int index = 0; index < value.length(); index++) {
            output.write(value.charAt(index));
        }
    }

    private static void writeLittleShort(ByteArrayOutputStream output, int value) {
        output.write(value & 0xff);
        output.write((value >>> 8) & 0xff);
    }

    private static void writeLittleInt(ByteArrayOutputStream output, int value) {
        output.write(value & 0xff);
        output.write((value >>> 8) & 0xff);
        output.write((value >>> 16) & 0xff);
        output.write((value >>> 24) & 0xff);
    }

    private static void writeLittleInt(byte[] bytes, int offset, int value) {
        bytes[offset] = (byte) (value & 0xff);
        bytes[offset + 1] = (byte) ((value >>> 8) & 0xff);
        bytes[offset + 2] = (byte) ((value >>> 16) & 0xff);
        bytes[offset + 3] = (byte) ((value >>> 24) & 0xff);
    }
}
