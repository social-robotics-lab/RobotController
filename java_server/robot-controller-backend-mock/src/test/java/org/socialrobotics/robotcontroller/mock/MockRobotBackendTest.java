package org.socialrobotics.robotcontroller.mock;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.Test;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;
import org.socialrobotics.robotcontroller.core.backend.RobotLifecycleState;

public final class MockRobotBackendTest {
    @Test
    public void mouthOwnershipVoiceSyncAndBrightnessAreObservable() throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        Set<String> mouth = Collections.singleton("MOUTH");
        backend.initialize();

        assertTrue(backend.acquireLedOwnership("audio-1", mouth));
        backend.disableNativeMouthVoiceSync();
        backend.setLed("MOUTH", 7);

        assertEquals(RobotLifecycleState.READY, backend.lifecycleState());
        assertEquals("audio-1", backend.ledOwnershipKey());
        assertEquals(mouth, backend.ownedLedNames());
        assertFalse(backend.nativeMouthVoiceSyncEnabled());
        assertEquals(Integer.valueOf(7), backend.currentLedValues().get("MOUTH"));

        backend.enableNativeMouthVoiceSync();
        backend.releaseLedOwnership("audio-1", mouth);
        assertTrue(backend.nativeMouthVoiceSyncEnabled());
        assertEquals(null, backend.ledOwnershipKey());
        assertEquals(
                Arrays.asList(
                        "initialize",
                        "acquireLedOwnership",
                        "disableNativeMouthVoiceSync",
                        "setLed",
                        "enableNativeMouthVoiceSync",
                        "releaseLedOwnership"),
                backend.operationHistory());
    }

    @Test
    public void conflictingLedOwnershipIsRejected() throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        Set<String> mouth = new HashSet<String>(Collections.singleton("MOUTH"));
        assertTrue(backend.acquireLedOwnership("first", mouth));
        assertFalse(backend.acquireLedOwnership("second", mouth));
    }

    @Test
    public void namedFaultInjectionIsObservableAndClearable() throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        backend.failOperation("setLed", new RobotBackendException("injected LED failure"));
        try {
            backend.setLed("MOUTH", 4);
            throw new AssertionError("expected injected failure");
        } catch (RobotBackendException expected) {
            assertEquals("injected LED failure", expected.getMessage());
        }
        backend.clearFailure("setLed");
        backend.setLed("MOUTH", 4);
        assertEquals(Integer.valueOf(4), backend.currentLedValues().get("MOUTH"));
    }

    @Test
    public void maximumConcurrentBackendCallsIsObservableWithoutSleeping() throws Exception {
        final CountDownLatch entered = new CountDownLatch(2);
        final CountDownLatch release = new CountDownLatch(1);
        MockRobotBackend backend = new MockRobotBackend(new MockOperationHook() {
            @Override
            public void duringOperation(String operationName) {
                entered.countDown();
                try {
                    if (!release.await(2, TimeUnit.SECONDS)) {
                        throw new AssertionError("operation release timed out");
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new AssertionError(interrupted);
                }
            }
        });
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = executor.submit(new SetLedCall(backend, "A"));
            Future<?> second = executor.submit(new SetLedCall(backend, "B"));
            assertTrue("both calls should overlap", entered.await(2, TimeUnit.SECONDS));
            release.countDown();
            first.get(2, TimeUnit.SECONDS);
            second.get(2, TimeUnit.SECONDS);
            assertEquals(2, backend.maximumConcurrentBackendCalls());
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }

    private static final class SetLedCall implements Runnable {
        private final MockRobotBackend backend;
        private final String name;

        private SetLedCall(MockRobotBackend backend, String name) {
            this.backend = backend;
            this.name = name;
        }

        @Override
        public void run() {
            try {
                backend.setLed(name, 1);
            } catch (Exception failure) {
                throw new AssertionError(failure);
            }
        }
    }
}
