package org.socialrobotics.robotcontroller.core.audio;

/** One caller-owned audio playback resource. Stop and close must be idempotent. */
public interface AudioPlaybackSession extends AutoCloseable {
    /** Starts this session once; repeated calls must not create new playback. */
    void start() throws AudioOutputException;

    /** Stops only this owned session and is safe to call repeatedly. */
    void stop() throws AudioOutputException;

    /** Returns the playback-position source associated with this session. */
    PlaybackClock clock();

    /** Returns the current observable playback state. */
    AudioPlaybackState state();

    /** Releases owned playback resources and is safe to call repeatedly. */
    @Override
    void close() throws AudioOutputException;
}
