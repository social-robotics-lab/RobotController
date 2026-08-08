package org.socialrobotics.robotcontroller.mock;

import org.socialrobotics.robotcontroller.core.audio.AudioOutputException;
import org.socialrobotics.robotcontroller.core.audio.AudioPlaybackSession;
import org.socialrobotics.robotcontroller.core.audio.AudioPlaybackState;
import org.socialrobotics.robotcontroller.core.audio.PcmAudioData;
import org.socialrobotics.robotcontroller.core.audio.PlaybackClock;

/** Deterministic owned audio session whose stop and close operations are idempotent. */
public final class MockAudioPlaybackSession implements AudioPlaybackSession {
    private final PcmAudioData audio;
    private final MockPlaybackClock clock;
    private AudioOutputException startFailure;
    private AudioPlaybackState state = AudioPlaybackState.CREATED;

    MockAudioPlaybackSession(PcmAudioData audio) {
        this(audio, null);
    }

    MockAudioPlaybackSession(PcmAudioData audio, AudioOutputException startFailure) {
        this.audio = audio;
        this.clock = new MockPlaybackClock(audio.sampleRateHz());
        this.startFailure = startFailure;
    }

    @Override
    public synchronized void start() throws AudioOutputException {
        if (state == AudioPlaybackState.CLOSED) {
            throw new AudioOutputException("cannot start a closed session");
        }
        if (state == AudioPlaybackState.CREATED) {
            if (startFailure != null) {
                AudioOutputException failure = startFailure;
                startFailure = null;
                throw failure;
            }
            state = AudioPlaybackState.PLAYING;
        }
    }

    @Override
    public synchronized void stop() {
        if (state != AudioPlaybackState.CLOSED) {
            state = AudioPlaybackState.STOPPED;
        }
    }

    @Override
    public PlaybackClock clock() {
        return clock;
    }

    public MockPlaybackClock controllableClock() {
        return clock;
    }

    @Override
    public synchronized AudioPlaybackState state() {
        return state;
    }

    @Override
    public synchronized void close() {
        state = AudioPlaybackState.CLOSED;
    }

    public synchronized void complete() {
        if (state == AudioPlaybackState.PLAYING) {
            clock.setPlayedFrames(audio.frameCount());
            state = AudioPlaybackState.COMPLETED;
        }
    }

    public PcmAudioData audio() {
        return audio;
    }
}
