package org.socialrobotics.robotcontroller.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.net.InetAddress;
import java.net.ServerSocket;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.Test;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;
import org.socialrobotics.robotcontroller.core.backend.RobotLifecycleState;
import org.socialrobotics.robotcontroller.mock.MockAudioOutput;
import org.socialrobotics.robotcontroller.mock.MockRobotBackend;

public final class ApplicationProcessLockIntegrationTest {
    @Test
    public void secondApplicationFailsBeforeBackendInitializationAndReleaseAllowsRestart()
            throws Exception {
        Path lockPath = newLockPath();
        ApplicationConfiguration configuration = configuration(lockPath, 0);
        RobotControllerApplication first = application(new MockRobotBackend(), configuration);
        first.start();
        try {
            MockRobotBackend competingBackend = new MockRobotBackend();
            RobotControllerApplication competing = application(competingBackend, configuration);
            try {
                competing.start();
                fail("expected single-instance startup failure");
            } catch (ApplicationStartupException expected) {
                assertTrue(expected.getCause() instanceof ProcessLockException);
                assertEquals(RobotLifecycleState.FAILED, competing.lifecycleState());
                assertEquals(0, count(competingBackend, "initialize"));
                assertEquals(-1, competing.localPort());
            } finally {
                competing.close();
            }
        } finally {
            first.close();
        }

        RobotControllerApplication restarted = application(
                new MockRobotBackend(), configuration);
        try {
            restarted.start();
            assertEquals(RobotLifecycleState.READY, restarted.lifecycleState());
            assertTrue(restarted.localPort() > 0);
        } finally {
            restarted.close();
        }
    }

    @Test
    public void backendInitializationFailureReleasesProcessLock() throws Exception {
        Path lockPath = newLockPath();
        MockRobotBackend backend = new MockRobotBackend();
        backend.failOperation("initialize", new RobotBackendException("injected initialize"));
        RobotControllerApplication application = application(backend, configuration(lockPath, 0));

        try {
            application.start();
            fail("expected initialization failure");
        } catch (ApplicationStartupException expected) {
            assertEquals(RobotLifecycleState.FAILED, application.lifecycleState());
            assertEquals(1, count(backend, "close"));
        } finally {
            application.close();
        }

        SingleInstanceProcessLock reacquired = SingleInstanceProcessLock.acquire(lockPath);
        reacquired.close();
    }

    @Test
    public void tcpBindFailureClosesBackendAndReleasesProcessLock() throws Exception {
        Path lockPath = newLockPath();
        ServerSocket occupied = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"));
        MockRobotBackend backend = new MockRobotBackend();
        RobotControllerApplication application = application(
                backend, configuration(lockPath, occupied.getLocalPort()));
        try {
            try {
                application.start();
                fail("expected bind failure");
            } catch (ApplicationStartupException expected) {
                assertEquals(RobotLifecycleState.FAILED, application.lifecycleState());
                assertEquals(-1, application.localPort());
                assertEquals(1, count(backend, "initialize"));
                assertEquals(1, count(backend, "close"));
            }
        } finally {
            application.close();
            occupied.close();
        }

        SingleInstanceProcessLock reacquired = SingleInstanceProcessLock.acquire(lockPath);
        reacquired.close();
    }

    @Test
    public void closeBeforeStartIsIdempotentAndDoesNotInitializeBackend() throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        RobotControllerApplication application = application(
                backend, configuration(newLockPath(), 0));

        application.close();
        application.close();

        assertEquals(RobotLifecycleState.STOPPED, application.lifecycleState());
        assertEquals(0, count(backend, "initialize"));
        assertEquals(0, count(backend, "close"));
    }

    private static RobotControllerApplication application(
            MockRobotBackend backend,
            ApplicationConfiguration configuration) {
        return new RobotControllerApplication(configuration, backend, new MockAudioOutput());
    }

    private static ApplicationConfiguration configuration(Path lockPath, int port) {
        return ApplicationConfiguration.builder()
                .backendSelection(BackendSelection.MOCK)
                .listenHost("127.0.0.1")
                .listenPort(port)
                .connectionWorkerCount(1)
                .connectionQueueCapacity(1)
                .hardwareCommandQueueCapacity(4)
                .socketTimeoutMilliseconds(500)
                .shutdownTimeoutMilliseconds(2_000)
                .processLockPath(lockPath)
                .build();
    }

    private static Path newLockPath() throws Exception {
        return Files.createTempDirectory("robot-controller-app-lock-test-")
                .resolve("controller.lock");
    }

    private static int count(MockRobotBackend backend, String operation) {
        int count = 0;
        for (String observed : backend.operationHistory()) {
            if (operation.equals(observed)) {
                count++;
            }
        }
        return count;
    }
}
