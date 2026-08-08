package org.socialrobotics.robotcontroller.app;

/** Indicates that initialization or TCP binding failed before normal service. */
public final class ApplicationStartupException extends Exception {
    /** Creates a startup failure while preserving its internal cause. */
    public ApplicationStartupException(String message, Throwable cause) {
        super(message, cause);
    }
}
