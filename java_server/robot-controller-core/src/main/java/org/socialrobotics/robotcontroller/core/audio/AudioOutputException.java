package org.socialrobotics.robotcontroller.core.audio;

/** Failure while opening or controlling an owned audio playback session. */
public class AudioOutputException extends Exception {
    public AudioOutputException(String message) {
        super(message);
    }

    public AudioOutputException(String message, Throwable cause) {
        super(message, cause);
    }
}
