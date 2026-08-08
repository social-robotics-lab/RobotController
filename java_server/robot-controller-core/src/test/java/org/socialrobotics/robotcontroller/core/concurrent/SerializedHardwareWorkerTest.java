package org.socialrobotics.robotcontroller.core.concurrent;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.util.Collections;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.Test;
import org.socialrobotics.robotcontroller.core.backend.RobotBackend;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;
import org.socialrobotics.robotcontroller.core.backend.RobotLifecycleState;
import org.socialrobotics.robotcontroller.core.backend.RobotPose;

public final class SerializedHardwareWorkerTest {
    @Test
    public void staleGenerationIsCheckedAfterPreExecutionHook() throws Exception {
        final CountDownLatch hookEntered = new CountDownLatch(1);
        final CountDownLatch releaseHook = new CountDownLatch(1);
        RecordingBackend backend = new RecordingBackend();
        GenerationRegistry registry = new GenerationRegistry();
        GenerationToken token = registry.begin(GenerationGroup.MOTION);
        SerializedHardwareWorker worker = new SerializedHardwareWorker(
                backend,
                2,
                new HardwareExecutionHook() {
                    @Override
                    public void beforeExecution() throws InterruptedException {
                        hookEntered.countDown();
                        releaseHook.await();
                    }
                });
        try {
            Future<Void> result = worker.submit(token, new HardwareCommand<Void>() {
                @Override
                public Void execute(RobotBackend target) throws RobotBackendException {
                    target.applyPose(new RobotPose(
                            Collections.singletonMap("HEAD_Y", Integer.valueOf(1)),
                            Collections.<String, Integer>emptyMap(),
                            0));
                    return null;
                }
            });
            assertTrue(hookEntered.await(2, TimeUnit.SECONDS));
            registry.cancel(GenerationGroup.MOTION);
            releaseHook.countDown();

            assertNull(result.get(2, TimeUnit.SECONDS));
            assertEquals(0, backend.applyCount.get());
        } finally {
            releaseHook.countDown();
            worker.close();
        }
    }

    @Test
    public void backendFailureDoesNotKillWorker() throws Exception {
        final AtomicInteger attempts = new AtomicInteger();
        RecordingBackend backend = new RecordingBackend();
        SerializedHardwareWorker worker = new SerializedHardwareWorker(backend, 2);
        try {
            Future<Integer> failed = worker.submit(
                    GenerationToken.alwaysValid(),
                    new HardwareCommand<Integer>() {
                        @Override
                        public Integer execute(RobotBackend target)
                                throws RobotBackendException {
                            attempts.incrementAndGet();
                            throw new RobotBackendException("injected");
                        }
                    });
            try {
                failed.get(2, TimeUnit.SECONDS);
                fail("expected failure");
            } catch (ExecutionException expected) {
                assertTrue(expected.getCause() instanceof RobotBackendException);
            }

            Future<Integer> succeeded = worker.submit(
                    GenerationToken.alwaysValid(),
                    new HardwareCommand<Integer>() {
                        @Override
                        public Integer execute(RobotBackend target) {
                            return Integer.valueOf(attempts.incrementAndGet());
                        }
                    });
            assertEquals(Integer.valueOf(2), succeeded.get(2, TimeUnit.SECONDS));
        } finally {
            worker.close();
        }
    }

    @Test
    public void boundedQueueRejectsOverflowAndShutdownRejectsNewWork() throws Exception {
        final CountDownLatch firstEntered = new CountDownLatch(1);
        final CountDownLatch releaseFirst = new CountDownLatch(1);
        SerializedHardwareWorker worker = new SerializedHardwareWorker(
                new RecordingBackend(),
                1,
                new HardwareExecutionHook() {
                    @Override
                    public void beforeExecution() throws InterruptedException {
                        firstEntered.countDown();
                        releaseFirst.await();
                    }
                });
        try {
            worker.submit(GenerationToken.alwaysValid(), noOp());
            assertTrue(firstEntered.await(2, TimeUnit.SECONDS));
            worker.submit(GenerationToken.alwaysValid(), noOp());
            try {
                worker.submit(GenerationToken.alwaysValid(), noOp());
                fail("expected bounded queue rejection");
            } catch (HardwareQueueFullException expected) {
                // Expected.
            }
        } finally {
            releaseFirst.countDown();
            worker.close();
        }

        try {
            worker.submit(GenerationToken.alwaysValid(), noOp());
            fail("expected shutdown rejection");
        } catch (HardwareWorkerClosedException expected) {
            // Expected.
        }
    }

    private static HardwareCommand<Void> noOp() {
        return new HardwareCommand<Void>() {
            @Override
            public Void execute(RobotBackend target) {
                return null;
            }
        };
    }

    private static final class RecordingBackend implements RobotBackend {
        private final AtomicInteger applyCount = new AtomicInteger();

        @Override
        public void initialize() {
        }

        @Override
        public RobotLifecycleState lifecycleState() {
            return RobotLifecycleState.READY;
        }

        @Override
        public java.util.Map<String, Integer> readAxes() {
            return Collections.emptyMap();
        }

        @Override
        public void applyPose(RobotPose pose) {
            applyCount.incrementAndGet();
        }

        @Override
        public void setLed(String logicalLedName, int value) {
        }

        @Override
        public boolean acquireLedOwnership(
                String ownershipKey,
                java.util.Set<String> logicalLedNames) {
            return true;
        }

        @Override
        public void releaseLedOwnership(
                String ownershipKey,
                java.util.Set<String> logicalLedNames) {
        }

        @Override
        public void disableNativeMouthVoiceSync() {
        }

        @Override
        public void enableNativeMouthVoiceSync() {
        }

        @Override
        public void requestRobotStop() {
        }

        @Override
        public void close() {
        }
    }
}
