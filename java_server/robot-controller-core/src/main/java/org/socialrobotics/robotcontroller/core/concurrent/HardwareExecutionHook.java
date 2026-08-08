package org.socialrobotics.robotcontroller.core.concurrent;

/** Test seam invoked before the final generation check and backend call. */
public interface HardwareExecutionHook {
    void beforeExecution() throws InterruptedException;
}
