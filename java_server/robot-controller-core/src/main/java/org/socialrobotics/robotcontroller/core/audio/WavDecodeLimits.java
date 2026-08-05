package org.socialrobotics.robotcontroller.core.audio;

/** Immutable memory and duration limits applied before canonical PCM is created. */
public final class WavDecodeLimits {
    private final int maximumPayloadBytes;
    private final long maximumDurationMilliseconds;

    public WavDecodeLimits(int maximumPayloadBytes, long maximumDurationMilliseconds) {
        if (maximumPayloadBytes < 12) {
            throw new IllegalArgumentException("maximumPayloadBytes must fit a RIFF/WAVE header");
        }
        if (maximumDurationMilliseconds < 0) {
            throw new IllegalArgumentException("maximumDurationMilliseconds must be non-negative");
        }
        this.maximumPayloadBytes = maximumPayloadBytes;
        this.maximumDurationMilliseconds = maximumDurationMilliseconds;
    }

    public int maximumPayloadBytes() {
        return maximumPayloadBytes;
    }

    public long maximumDurationMilliseconds() {
        return maximumDurationMilliseconds;
    }
}
