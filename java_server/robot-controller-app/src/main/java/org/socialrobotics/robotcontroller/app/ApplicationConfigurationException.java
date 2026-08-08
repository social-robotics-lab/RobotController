package org.socialrobotics.robotcontroller.app;

/** Indicates invalid or incomplete process configuration before startup. */
public final class ApplicationConfigurationException extends Exception {
    /** Creates a configuration failure. */
    public ApplicationConfigurationException(String message) {
        super(message);
    }

    /** Creates a configuration failure with its parsing cause. */
    public ApplicationConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}
