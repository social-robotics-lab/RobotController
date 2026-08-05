package org.socialrobotics.robotcontroller.core.protocol;

import java.io.IOException;

/** Indicates that a legacy length-prefixed frame is malformed or incomplete. */
public final class FrameCodecException extends IOException {
    public FrameCodecException(String message) {
        super(message);
    }
}
