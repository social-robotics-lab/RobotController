package org.socialrobotics.robotcontroller.mock;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.socialrobotics.robotcontroller.core.audio.AudioOutput;
import org.socialrobotics.robotcontroller.core.audio.AudioOutputException;
import org.socialrobotics.robotcontroller.core.audio.AudioPlaybackSession;
import org.socialrobotics.robotcontroller.core.audio.PcmAudioData;

/** Memory-only audio output that records each opened deterministic session. */
public final class MockAudioOutput implements AudioOutput {
    private final List<MockAudioPlaybackSession> sessions =
            new ArrayList<MockAudioPlaybackSession>();
    private AudioOutputException nextOpenFailure;
    private AudioOutputException nextStartFailure;

    @Override
    public synchronized AudioPlaybackSession open(PcmAudioData audio)
            throws AudioOutputException {
        if (audio == null) {
            throw new NullPointerException("audio");
        }
        if (nextOpenFailure != null) {
            AudioOutputException failure = nextOpenFailure;
            nextOpenFailure = null;
            throw failure;
        }
        MockAudioPlaybackSession session = new MockAudioPlaybackSession(
                audio, nextStartFailure);
        nextStartFailure = null;
        sessions.add(session);
        return session;
    }

    public synchronized List<MockAudioPlaybackSession> sessions() {
        return Collections.unmodifiableList(
                new ArrayList<MockAudioPlaybackSession>(sessions));
    }

    /** Fails exactly the next open attempt for deterministic cleanup tests. */
    public synchronized void failNextOpen(AudioOutputException failure) {
        if (failure == null) {
            throw new NullPointerException("failure");
        }
        nextOpenFailure = failure;
    }

    /** Fails exactly the next opened session's start attempt. */
    public synchronized void failNextStart(AudioOutputException failure) {
        if (failure == null) {
            throw new NullPointerException("failure");
        }
        nextStartFailure = failure;
    }
}
