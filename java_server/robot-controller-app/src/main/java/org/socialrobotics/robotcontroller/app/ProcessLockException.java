package org.socialrobotics.robotcontroller.app;

/** Indicates that the configured single-instance advisory lock could not be acquired. */
public final class ProcessLockException extends Exception {
    private static final long serialVersionUID = 1L;

    ProcessLockException(String message) {
        super(message);
    }

    ProcessLockException(String message, Throwable cause) {
        super(message, cause);
    }
}
