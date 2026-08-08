package org.socialrobotics.robotcontroller.app;

/** Typed application-layer failure contained within one legacy connection. */
final class ApplicationDispatchException extends Exception {
    ApplicationDispatchException(String message) {
        super(message);
    }

    ApplicationDispatchException(String message, Throwable cause) {
        super(message, cause);
    }
}
