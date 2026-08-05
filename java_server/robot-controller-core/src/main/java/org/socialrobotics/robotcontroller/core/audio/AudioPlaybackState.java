package org.socialrobotics.robotcontroller.core.audio;

/** Observable lifecycle of an owned playback session. */
public enum AudioPlaybackState {
    CREATED,
    PLAYING,
    STOPPED,
    COMPLETED,
    CLOSED
}
