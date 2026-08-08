package org.socialrobotics.robotcontroller.core.concurrent;

import org.socialrobotics.robotcontroller.core.backend.RobotBackend;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;

/** One validated operation executed only on the serialized hardware worker. */
public interface HardwareCommand<T> {
    T execute(RobotBackend backend) throws RobotBackendException;
}
