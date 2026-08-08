package org.socialrobotics.robotcontroller.core.command;

/** Sanitized failure raised while decoding or validating one legacy command. */
public final class CommandValidationException extends Exception {
    /** Creates a validation failure without exposing payload content. */
    public CommandValidationException(String message) {
        super(message);
    }

    /** Creates a validation failure with an internal cause. */
    public CommandValidationException(String message, Throwable cause) {
        super(message, cause);
    }
}
