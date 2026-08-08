package org.socialrobotics.robotcontroller.mock;

/** Injectable test hook invoked while a MockRobotBackend operation is active. */
public interface MockOperationHook {
    void duringOperation(String operationName) throws InterruptedException;
}
