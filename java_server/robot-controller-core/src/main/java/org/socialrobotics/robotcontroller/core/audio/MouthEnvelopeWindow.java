package org.socialrobotics.robotcontroller.core.audio;

/** One immutable frame/time interval and its target mouth brightness. */
public final class MouthEnvelopeWindow {
    private final long startFrameInclusive;
    private final long endFrameExclusive;
    private final long startMicroseconds;
    private final long endMicroseconds;
    private final int brightness;

    public MouthEnvelopeWindow(
            long startFrameInclusive,
            long endFrameExclusive,
            long startMicroseconds,
            long endMicroseconds,
            int brightness) {
        if (startFrameInclusive < 0 || endFrameExclusive < startFrameInclusive) {
            throw new IllegalArgumentException("invalid frame range");
        }
        if (startMicroseconds < 0 || endMicroseconds < startMicroseconds) {
            throw new IllegalArgumentException("invalid time range");
        }
        if (brightness < 0 || brightness > 255) {
            throw new IllegalArgumentException("brightness must be between 0 and 255");
        }
        this.startFrameInclusive = startFrameInclusive;
        this.endFrameExclusive = endFrameExclusive;
        this.startMicroseconds = startMicroseconds;
        this.endMicroseconds = endMicroseconds;
        this.brightness = brightness;
    }

    public long startFrameInclusive() {
        return startFrameInclusive;
    }

    public long endFrameExclusive() {
        return endFrameExclusive;
    }

    public long startMicroseconds() {
        return startMicroseconds;
    }

    public long endMicroseconds() {
        return endMicroseconds;
    }

    public int brightness() {
        return brightness;
    }
}
