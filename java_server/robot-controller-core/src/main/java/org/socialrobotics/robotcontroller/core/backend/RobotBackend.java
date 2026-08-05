package org.socialrobotics.robotcontroller.core.backend;

import java.util.Map;
import java.util.Set;

/** Vendor-neutral primitive robot operations, invoked later by one hardware worker. */
public interface RobotBackend extends AutoCloseable {
    /** Initializes the backend without implying any unrequested robot motion. */
    void initialize() throws RobotBackendException;

    /** Returns the current lifecycle/health state. */
    RobotLifecycleState lifecycleState();

    /** Reads logical axis values through the backend boundary. */
    Map<String, Integer> readAxes() throws RobotBackendException;

    /** Applies one already validated vendor-neutral pose. */
    void applyPose(RobotPose pose) throws RobotBackendException;

    /** Updates one logical LED value. */
    void setLed(String logicalLedName, int value) throws RobotBackendException;

    /** Attempts to acquire explicit ownership of the requested logical LEDs. */
    boolean acquireLedOwnership(String ownershipKey, Set<String> logicalLedNames)
            throws RobotBackendException;

    /** Releases LED ownership held by the same key and LED set. */
    void releaseLedOwnership(String ownershipKey, Set<String> logicalLedNames)
            throws RobotBackendException;

    /** Disables a robot-provided native mouth/audio synchronization feature. */
    void disableNativeMouthVoiceSync() throws RobotBackendException;

    /** Restores a robot-provided native mouth/audio synchronization feature. */
    void enableNativeMouthVoiceSync() throws RobotBackendException;

    /** Requests only the stop primitive actually supported by the backend. */
    void requestRobotStop() throws RobotBackendException;

    /** Releases caller-owned backend resources. */
    @Override
    void close() throws RobotBackendException;
}
