package org.socialrobotics.robotcontroller.core.concurrent;

/** Indicates that the bounded hardware command queue cannot accept more work. */
public final class HardwareQueueFullException extends RuntimeException {
    public HardwareQueueFullException() {
        super("hardware command queue is full");
    }
}
