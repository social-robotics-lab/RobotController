package org.socialrobotics.robotcontroller.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.nio.file.Paths;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.Test;

public final class ApplicationConfigurationTest {
    @Test
    public void parsesAllExplicitRuntimeBoundaries() throws Exception {
        ApplicationConfiguration configuration = ApplicationConfiguration.fromArguments(
                new String[] {
                    "--backend=mock",
                    "--listen-host=127.0.0.1",
                    "--listen-port=12345",
                    "--connection-workers=3",
                    "--connection-queue-capacity=4",
                    "--hardware-queue-capacity=5",
                    "--command-frame-limit=63",
                    "--json-frame-limit=1000",
                    "--wav-frame-limit=2000",
                    "--audio-duration-limit-ms=3000",
                    "--mouth-sync-interval-ms=20",
                    "--socket-timeout-ms=600",
                    "--shutdown-timeout-ms=700",
                    "--process-lock-path=target/test-explicit.lock"
                });

        assertEquals(BackendSelection.MOCK, configuration.backendSelection());
        assertEquals(12345, configuration.listenPort());
        assertEquals(3, configuration.connectionWorkerCount());
        assertEquals(4, configuration.connectionQueueCapacity());
        assertEquals(5, configuration.hardwareCommandQueueCapacity());
        assertEquals(63, configuration.maximumCommandFrameBytes());
        assertEquals(1000, configuration.maximumJsonFrameBytes());
        assertEquals(2000, configuration.maximumWavFrameBytes());
        assertEquals(3000L, configuration.maximumAudioDurationMilliseconds());
        assertEquals(20L, configuration.mouthSynchronizationIntervalMilliseconds());
        assertEquals(600, configuration.socketTimeoutMilliseconds());
        assertEquals(700, configuration.shutdownTimeoutMilliseconds());
        assertEquals(
                Paths.get("target/test-explicit.lock").toAbsolutePath().normalize(),
                configuration.processLockPath());
        assertTrue(configuration.processLockPath().isAbsolute());
    }

    @Test
    public void backendSelectionMustBeExplicit() throws Exception {
        try {
            ApplicationConfiguration.fromArguments(new String[0]);
            fail("expected missing backend rejection");
        } catch (ApplicationConfigurationException expected) {
            // Expected.
        }
    }

    @Test
    public void defaultsAreBoundedAndUseAnAbsolutePlatformNeutralLockPath() throws Exception {
        ApplicationConfiguration configuration = ApplicationConfiguration.fromArguments(
                new String[] {"--backend=mock"});

        assertEquals("127.0.0.1", configuration.listenHost());
        assertEquals(22222, configuration.listenPort());
        assertEquals(16, configuration.connectionWorkerCount());
        assertEquals(16, configuration.connectionQueueCapacity());
        assertEquals(16, configuration.hardwareCommandQueueCapacity());
        assertEquals(64, configuration.maximumCommandFrameBytes());
        assertEquals(1_048_576, configuration.maximumJsonFrameBytes());
        assertEquals(20_971_520, configuration.maximumWavFrameBytes());
        assertEquals(600_000L, configuration.maximumAudioDurationMilliseconds());
        assertEquals(10L, configuration.mouthSynchronizationIntervalMilliseconds());
        assertEquals(5_000, configuration.socketTimeoutMilliseconds());
        assertEquals(5_000, configuration.shutdownTimeoutMilliseconds());
        assertTrue(configuration.processLockPath().isAbsolute());
    }

    @Test
    public void rejectsInvalidAndUnknownRuntimeOptionsBeforeComposition() throws Exception {
        String[][] invalidArguments = new String[][] {
            {"--backend=mock", "--listen-host="},
            {"--backend=mock", "--listen-port=-1"},
            {"--backend=mock", "--listen-port=65536"},
            {"--backend=mock", "--listen-port=0"},
            {"--backend=mock", "--connection-workers=0"},
            {"--backend=mock", "--connection-queue-capacity=0"},
            {"--backend=mock", "--hardware-queue-capacity=-1"},
            {"--backend=mock", "--command-frame-limit=0"},
            {"--backend=mock", "--json-frame-limit=0"},
            {"--backend=mock", "--wav-frame-limit=11"},
            {"--backend=mock", "--audio-duration-limit-ms=0"},
            {"--backend=mock", "--mouth-sync-interval-ms=0"},
            {"--backend=mock", "--socket-timeout-ms=0"},
            {"--backend=mock", "--shutdown-timeout-ms=-1"},
            {"--backend=mock", "--process-lock-path="},
            {"--backend=mock", "--unknown-option=1"},
            {"--backend=unknown"},
            {"--backend=mock", "--listen-port=not-an-integer"}
        };

        for (String[] arguments : invalidArguments) {
            try {
                ApplicationConfiguration.fromArguments(arguments);
                fail("expected configuration rejection");
            } catch (ApplicationConfigurationException expected) {
                // Each malformed configuration must fail before application composition.
            }
        }
    }

    @Test
    public void ephemeralPortIsAcceptedOnlyByExplicitSmokeTestMode() throws Exception {
        ApplicationConfiguration configuration = ApplicationConfiguration.fromArguments(
                new String[] {"--backend=mock", "--listen-port=0", "--smoke-test"});

        assertEquals(0, configuration.listenPort());
    }

    @Test
    public void mainRejectsInvalidConfigurationBeforeCreatingTheProcessLock()
            throws Exception {
        Path lockPath = Files.createTempDirectory("robot-controller-invalid-config-test-")
                .resolve("controller.lock");
        try {
            Main.main(new String[] {
                "--backend=mock",
                "--listen-port=-1",
                "--process-lock-path=" + lockPath
            });
            fail("expected configuration failure");
        } catch (ApplicationConfigurationException expected) {
            // Configuration is validated before application resources are constructed.
        }
        assertFalse(Files.exists(lockPath));
    }

    @Test
    public void vstoneSelectionFailsBeforeAnyVendorAdapterIsConstructed() throws Exception {
        ApplicationConfiguration configuration = ApplicationConfiguration.fromArguments(
                new String[] {"--backend=vstone"});
        try {
            RobotControllerComposition.create(configuration);
            fail("expected unavailable VSTONE backend rejection");
        } catch (ApplicationConfigurationException expected) {
            // Expected.
        }
    }
}
