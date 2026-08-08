package org.socialrobotics.robotcontroller.core.concurrent;

/** Indicates that hardware work was submitted after controlled shutdown began. */
public final class HardwareWorkerClosedException extends IllegalStateException {
    public HardwareWorkerClosedException() {
        super("hardware worker is closed");
    }
}
