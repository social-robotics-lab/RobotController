package org.socialrobotics.robotcontroller.app;

/** Explicit backend selection; there is deliberately no implicit production default. */
public enum BackendSelection {
    MOCK,
    VSTONE;

    /** Parses a case-insensitive command-line backend name. */
    public static BackendSelection parse(String value) {
        if ("mock".equalsIgnoreCase(value)) {
            return MOCK;
        }
        if ("vstone".equalsIgnoreCase(value)) {
            return VSTONE;
        }
        throw new IllegalArgumentException("unknown backend selection");
    }
}
