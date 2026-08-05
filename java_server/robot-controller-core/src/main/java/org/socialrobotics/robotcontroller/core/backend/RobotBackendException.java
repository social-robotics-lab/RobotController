package org.socialrobotics.robotcontroller.core.backend;

/** Typed boundary exception that prevents vendor-specific exceptions leaking into core. */
public class RobotBackendException extends Exception {
    public RobotBackendException(String message) {
        super(message);
    }

    public RobotBackendException(String message, Throwable cause) {
        super(message, cause);
    }
}
