package org.socialrobotics.robotcontroller.mock;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.socialrobotics.robotcontroller.core.audio.AudioOutput;
import org.socialrobotics.robotcontroller.core.audio.AudioPlaybackSession;
import org.socialrobotics.robotcontroller.core.audio.PcmAudioData;

/** Memory-only audio output that records each opened deterministic session. */
public final class MockAudioOutput implements AudioOutput {
    private final List<MockAudioPlaybackSession> sessions =
            new ArrayList<MockAudioPlaybackSession>();

    @Override
    public synchronized AudioPlaybackSession open(PcmAudioData audio) {
        if (audio == null) {
            throw new NullPointerException("audio");
        }
        MockAudioPlaybackSession session = new MockAudioPlaybackSession(audio);
        sessions.add(session);
        return session;
    }

    public synchronized List<MockAudioPlaybackSession> sessions() {
        return Collections.unmodifiableList(
                new ArrayList<MockAudioPlaybackSession>(sessions));
    }
}
