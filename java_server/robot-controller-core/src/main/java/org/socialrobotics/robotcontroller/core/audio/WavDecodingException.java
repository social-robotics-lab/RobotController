package org.socialrobotics.robotcontroller.core.audio;

/** Indicates a malformed, unsupported, or over-limit WAV payload. */
public final class WavDecodingException extends Exception {
    public WavDecodingException(String message) {
        super(message);
    }
}
