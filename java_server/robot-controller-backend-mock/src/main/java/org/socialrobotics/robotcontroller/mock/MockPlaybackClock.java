package org.socialrobotics.robotcontroller.mock;

import org.socialrobotics.robotcontroller.core.audio.PlaybackClock;

/** Manually advanced playback clock with no wall-clock dependency. */
public final class MockPlaybackClock implements PlaybackClock {
    private final int sampleRateHz;
    private long playedFrames;

    public MockPlaybackClock(int sampleRateHz) {
        if (sampleRateHz <= 0) {
            throw new IllegalArgumentException("sampleRateHz must be positive");
        }
        this.sampleRateHz = sampleRateHz;
    }

    @Override
    public synchronized long playedFrames() {
        return playedFrames;
    }

    @Override
    public synchronized long playedMicroseconds() {
        return playedFrames * 1000000L / sampleRateHz;
    }

    public synchronized void setPlayedFrames(long playedFrames) {
        if (playedFrames < 0L) {
            throw new IllegalArgumentException("playedFrames must be non-negative");
        }
        this.playedFrames = playedFrames;
    }

    public synchronized void advanceFrames(long frameCount) {
        if (frameCount < 0L || playedFrames > Long.MAX_VALUE - frameCount) {
            throw new IllegalArgumentException("frameCount cannot be applied safely");
        }
        playedFrames += frameCount;
    }
}
