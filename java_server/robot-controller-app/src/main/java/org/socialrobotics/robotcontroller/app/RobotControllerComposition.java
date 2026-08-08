package org.socialrobotics.robotcontroller.app;

import org.socialrobotics.robotcontroller.mock.MockAudioOutput;
import org.socialrobotics.robotcontroller.mock.MockRobotBackend;

/** Explicit composition root; only the hardware-free Mock backend exists in this slice. */
public final class RobotControllerComposition {
    private RobotControllerComposition() {
    }

    /** Creates the selected composition without performing backend I/O. */
    public static RobotControllerApplication create(ApplicationConfiguration configuration)
            throws ApplicationConfigurationException {
        if (configuration.backendSelection() == BackendSelection.MOCK) {
            return new RobotControllerApplication(
                    configuration, new MockRobotBackend(), new MockAudioOutput());
        }
        throw new ApplicationConfigurationException(
                "VSTONE backend is not implemented; select --backend=mock explicitly for Mock mode");
    }
}
