package org.socialrobotics.robotcontroller.core.concurrent;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.Test;
import org.socialrobotics.robotcontroller.core.backend.RobotBackend;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;
import org.socialrobotics.robotcontroller.core.backend.RobotLifecycleState;
import org.socialrobotics.robotcontroller.core.backend.RobotPose;

public final class LatestHardwareCommandMailboxTest {
    @Test
    public void blockedConsumerCoalescesAllPendingValuesToLatest() throws Exception {
        BlockingHook hook = new BlockingHook();
        RecordingBackend backend = new RecordingBackend();
        SerializedHardwareWorker worker = new SerializedHardwareWorker(backend, 4, hook);
        LatestHardwareCommandMailbox mailbox = new LatestHardwareCommandMailbox(worker);
        try {
            GenerationToken token = GenerationToken.alwaysValid();
            mailbox.publish(token, setLed(10));
            assertTrue(hook.entered.await(2, TimeUnit.SECONDS));
            mailbox.publish(token, setLed(20));
            mailbox.publish(token, setLed(40));
            mailbox.publish(token, setLed(180));

            hook.release.countDown();
            awaitWrites(backend, 1);

            assertEquals(Collections.singletonList(Integer.valueOf(180)), backend.writes());
        } finally {
            hook.release.countDown();
            mailbox.close();
            worker.close();
        }
    }

    @Test
    public void replacementBeforeHardwareExecutionDropsStaleGeneration() throws Exception {
        BlockingHook hook = new BlockingHook();
        RecordingBackend backend = new RecordingBackend();
        SerializedHardwareWorker worker = new SerializedHardwareWorker(backend, 4, hook);
        LatestHardwareCommandMailbox mailbox = new LatestHardwareCommandMailbox(worker);
        GenerationRegistry generations = new GenerationRegistry();
        try {
            GenerationToken first = generations.begin(GenerationGroup.AUDIO);
            mailbox.publish(first, setLed(10));
            assertTrue(hook.entered.await(2, TimeUnit.SECONDS));

            GenerationToken second = generations.begin(GenerationGroup.AUDIO);
            mailbox.publish(second, setLed(90));
            hook.release.countDown();
            awaitWrites(backend, 1);

            assertEquals(Collections.singletonList(Integer.valueOf(90)), backend.writes());
        } finally {
            hook.release.countDown();
            mailbox.close();
            worker.close();
        }
    }

    private static HardwareCommand<Void> setLed(final int brightness) {
        return new HardwareCommand<Void>() {
            @Override
            public Void execute(RobotBackend backend) throws RobotBackendException {
                backend.setLed("MOUTH", brightness);
                return null;
            }
        };
    }

    private static void awaitWrites(final RecordingBackend backend, int expected)
            throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
        while (backend.writes().size() < expected) {
            if (System.nanoTime() >= deadline) {
                throw new AssertionError("mailbox did not execute before timeout");
            }
            Thread.yield();
        }
    }

    private static final class BlockingHook implements HardwareExecutionHook {
        private final CountDownLatch entered = new CountDownLatch(1);
        private final CountDownLatch release = new CountDownLatch(1);

        @Override
        public void beforeExecution() throws InterruptedException {
            entered.countDown();
            release.await();
        }
    }

    private static final class RecordingBackend implements RobotBackend {
        private final List<Integer> writes = new ArrayList<Integer>();

        synchronized List<Integer> writes() {
            return new ArrayList<Integer>(writes);
        }

        @Override
        public void initialize() {
        }

        @Override
        public RobotLifecycleState lifecycleState() {
            return RobotLifecycleState.READY;
        }

        @Override
        public Map<String, Integer> readAxes() {
            return Collections.emptyMap();
        }

        @Override
        public void applyPose(RobotPose pose) {
        }

        @Override
        public synchronized void setLed(String logicalLedName, int value) {
            writes.add(Integer.valueOf(value));
        }

        @Override
        public boolean acquireLedOwnership(String ownershipKey, Set<String> logicalLedNames) {
            return true;
        }

        @Override
        public void releaseLedOwnership(String ownershipKey, Set<String> logicalLedNames) {
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
