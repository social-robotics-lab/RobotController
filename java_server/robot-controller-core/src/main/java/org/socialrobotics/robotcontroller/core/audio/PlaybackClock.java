package org.socialrobotics.robotcontroller.core.audio;

/** Playback-position source used for deterministic mouth synchronization. */
public interface PlaybackClock {
    /** Returns the observed number of played PCM frames. */
    long playedFrames();

    /** Returns the observed playback position in microseconds. */
    long playedMicroseconds();
}
