package org.socialrobotics.robotcontroller.core.backend;

/** Shared lifecycle names for robot backends and the future application lifecycle. */
public enum RobotLifecycleState {
    STARTING,
    INITIALIZING,
    READY,
    DEGRADED,
    STOPPING,
    STOPPED,
    FAILED
}
