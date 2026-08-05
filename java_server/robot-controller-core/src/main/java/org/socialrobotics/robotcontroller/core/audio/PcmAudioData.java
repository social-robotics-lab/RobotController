package org.socialrobotics.robotcontroller.core.audio;

import java.util.Arrays;

/** Immutable interleaved signed 16-bit little-endian canonical PCM. */
public final class PcmAudioData {
    public static final int BITS_PER_SAMPLE = 16;
    private static final int BYTES_PER_SAMPLE = BITS_PER_SAMPLE / 8;

    private final int sampleRateHz;
    private final int channels;
    private final long frameCount;
    private final byte[] pcmBytes;

    public PcmAudioData(int sampleRateHz, int channels, byte[] pcmBytes) {
        if (sampleRateHz <= 0) {
            throw new IllegalArgumentException("sampleRateHz must be positive");
        }
        if (channels < 1 || channels > 2) {
            throw new IllegalArgumentException("only mono and stereo PCM are supported");
        }
        if (pcmBytes == null) {
            throw new NullPointerException("pcmBytes");
        }
        int frameSizeBytes = channels * BYTES_PER_SAMPLE;
        if (pcmBytes.length % frameSizeBytes != 0) {
            throw new IllegalArgumentException("PCM byte length is not frame aligned");
        }
        this.sampleRateHz = sampleRateHz;
        this.channels = channels;
        this.frameCount = pcmBytes.length / frameSizeBytes;
        this.pcmBytes = Arrays.copyOf(pcmBytes, pcmBytes.length);
    }

    public int sampleRateHz() {
        return sampleRateHz;
    }

    public int channels() {
        return channels;
    }

    public int bitsPerSample() {
        return BITS_PER_SAMPLE;
    }

    public int frameSizeBytes() {
        return channels * BYTES_PER_SAMPLE;
    }

    public long frameCount() {
        return frameCount;
    }

    public long durationMicroseconds() {
        return frameCount * 1000000L / sampleRateHz;
    }

    /** Returns a defensive copy for transfer to an owned audio output. */
    public byte[] copyPcmBytes() {
        return Arrays.copyOf(pcmBytes, pcmBytes.length);
    }

    /** Returns one signed sample without copying the backing audio buffer. */
    public short sampleAt(long frameIndex, int channelIndex) {
        if (frameIndex < 0 || frameIndex >= frameCount) {
            throw new IndexOutOfBoundsException("frameIndex: " + frameIndex);
        }
        if (channelIndex < 0 || channelIndex >= channels) {
            throw new IndexOutOfBoundsException("channelIndex: " + channelIndex);
        }
        int byteIndex = (int) (frameIndex * frameSizeBytes() + channelIndex * BYTES_PER_SAMPLE);
        int low = pcmBytes[byteIndex] & 0xff;
        int high = pcmBytes[byteIndex + 1];
        return (short) ((high << 8) | low);
    }
}
