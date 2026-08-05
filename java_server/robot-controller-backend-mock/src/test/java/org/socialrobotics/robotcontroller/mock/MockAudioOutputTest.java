package org.socialrobotics.robotcontroller.mock;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertSame;

import org.junit.Test;
import org.socialrobotics.robotcontroller.core.audio.AudioPlaybackState;
import org.socialrobotics.robotcontroller.core.audio.PcmAudioData;

public final class MockAudioOutputTest {
    @Test
    public void startStopAndCloseAreIdempotent() throws Exception {
        MockAudioOutput output = new MockAudioOutput();
        PcmAudioData audio = new PcmAudioData(1000, 1, new byte[40]);
        MockAudioPlaybackSession session =
                (MockAudioPlaybackSession) output.open(audio);

        session.start();
        session.start();
        assertEquals(AudioPlaybackState.PLAYING, session.state());
        session.stop();
        session.stop();
        assertEquals(AudioPlaybackState.STOPPED, session.state());
        session.close();
        session.close();
        assertEquals(AudioPlaybackState.CLOSED, session.state());
        assertEquals(1, output.sessions().size());
        assertSame(session, output.sessions().get(0));
    }

    @Test
    public void stopBeforeStartIsSafeAndIdempotent() throws Exception {
        MockAudioPlaybackSession session = (MockAudioPlaybackSession) new MockAudioOutput()
                .open(new PcmAudioData(1000, 1, new byte[0]));
        session.stop();
        session.stop();
        assertEquals(AudioPlaybackState.STOPPED, session.state());
    }

    @Test
    public void playbackClockIsControllableWithoutSleeping() throws Exception {
        MockAudioPlaybackSession session = (MockAudioPlaybackSession) new MockAudioOutput()
                .open(new PcmAudioData(1000, 1, new byte[400]));
        session.controllableClock().advanceFrames(25L);
        assertEquals(25L, session.clock().playedFrames());
        assertEquals(25000L, session.clock().playedMicroseconds());
        session.controllableClock().setPlayedFrames(100L);
        assertEquals(100000L, session.clock().playedMicroseconds());
    }
}
