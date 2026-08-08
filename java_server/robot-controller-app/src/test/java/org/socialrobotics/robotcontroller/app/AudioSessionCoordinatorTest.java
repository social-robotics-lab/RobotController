package org.socialrobotics.robotcontroller.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.Test;
import org.socialrobotics.robotcontroller.core.audio.AudioOutputException;
import org.socialrobotics.robotcontroller.core.audio.AudioPlaybackState;
import org.socialrobotics.robotcontroller.core.audio.MouthEnvelopeAnalyzer;
import org.socialrobotics.robotcontroller.core.audio.MouthEnvelopeConfig;
import org.socialrobotics.robotcontroller.core.audio.PcmAudioData;
import org.socialrobotics.robotcontroller.core.backend.RobotBackend;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;
import org.socialrobotics.robotcontroller.core.concurrent.GenerationRegistry;
import org.socialrobotics.robotcontroller.core.concurrent.GenerationToken;
import org.socialrobotics.robotcontroller.core.concurrent.HardwareCommand;
import org.socialrobotics.robotcontroller.core.concurrent.HardwareExecutionHook;
import org.socialrobotics.robotcontroller.core.concurrent.SerializedHardwareWorker;
import org.socialrobotics.robotcontroller.mock.MockAudioOutput;
import org.socialrobotics.robotcontroller.mock.MockAudioPlaybackSession;
import org.socialrobotics.robotcontroller.mock.MockRobotBackend;

public final class AudioSessionCoordinatorTest {
    @Test
    public void normalPlaybackUsesOneCanonicalPcmAndResetsMouthOnCompletion()
            throws Exception {
        Fixture fixture = new Fixture();
        try {
            PcmAudioData audio = monoWindows(0, 20000);
            fixture.coordinator.play(audio);
            MockAudioPlaybackSession session = fixture.onlySession();
            assertSame(audio, session.audio());
            assertEquals(AudioPlaybackState.PLAYING, session.state());

            session.controllableClock().setPlayedFrames(20L);
            fixture.scheduler.runLatest();
            fixture.drainHardware();
            assertTrue(fixture.backend.ledValueHistory("MOUTH").get(0).intValue() > 0);

            session.complete();
            fixture.scheduler.runLatest();
            fixture.coordinator.awaitIdleForTest();

            assertEquals(AudioPlaybackState.CLOSED, session.state());
            assertEquals(Integer.valueOf(0), fixture.lastMouthValue());
        } finally {
            fixture.close();
        }
    }

    @Test
    public void replacementDropsPendingOldBrightnessBeforeBackendExecution()
            throws Exception {
        ControllableExecutionHook hook = new ControllableExecutionHook();
        Fixture fixture = new Fixture(hook);
        ExecutorService caller = Executors.newSingleThreadExecutor();
        try {
            int oldBrightness = expectedBrightness(1000);
            PcmAudioData first = monoWindows(1000);
            PcmAudioData second = monoWindows(20000);
            fixture.coordinator.play(first);
            hook.blockNext();
            fixture.scheduler.runLatest();
            assertTrue(hook.entered.await(2, TimeUnit.SECONDS));

            Future<?> replaced = caller.submit(new Runnable() {
                @Override
                public void run() {
                    try {
                        fixture.coordinator.play(second);
                    } catch (Exception failure) {
                        throw new AssertionError(failure);
                    }
                }
            });
            awaitWorkerQueue(fixture.worker, 1);
            hook.release.countDown();
            replaced.get(2, TimeUnit.SECONDS);

            fixture.scheduler.runLatest();
            fixture.drainHardware();
            assertFalse(fixture.backend.ledValueHistory("MOUTH")
                    .contains(Integer.valueOf(oldBrightness)));
            assertEquals(Integer.valueOf(expectedBrightness(20000)), fixture.lastMouthValue());
        } finally {
            hook.release.countDown();
            caller.shutdownNow();
            fixture.close();
        }
    }

    @Test
    public void lateCompletionResetCannotZeroReplacementSession() throws Exception {
        ControllableExecutionHook hook = new ControllableExecutionHook();
        Fixture fixture = new Fixture(hook);
        ExecutorService caller = Executors.newSingleThreadExecutor();
        try {
            fixture.coordinator.play(monoWindows(1000));
            MockAudioPlaybackSession first = fixture.onlySession();
            fixture.scheduler.runLatest();
            fixture.drainHardware();

            hook.blockNext();
            first.complete();
            fixture.scheduler.runLatest();
            assertTrue(hook.entered.await(2, TimeUnit.SECONDS));

            Future<?> replacement = caller.submit(new Runnable() {
                @Override
                public void run() {
                    try {
                        fixture.coordinator.play(monoWindows(25000));
                    } catch (Exception failure) {
                        throw new AssertionError(failure);
                    }
                }
            });
            awaitCoordinatorQueue(fixture.coordinator, 1);
            hook.release.countDown();
            replacement.get(2, TimeUnit.SECONDS);
            fixture.scheduler.runLatest();
            fixture.drainHardware();

            assertEquals(Integer.valueOf(expectedBrightness(25000)), fixture.lastMouthValue());
        } finally {
            hook.release.countDown();
            caller.shutdownNow();
            fixture.close();
        }
    }

    @Test
    public void stopIsIdempotentClearsPendingAndPreventsLateUpdate() throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.coordinator.play(monoWindows(20000));
            MockAudioPlaybackSession session = fixture.onlySession();
            fixture.scheduler.runLatest();
            fixture.coordinator.stop();
            fixture.coordinator.stop();
            fixture.scheduler.runAll();
            fixture.drainHardware();

            assertEquals(AudioPlaybackState.CLOSED, session.state());
            assertEquals(Integer.valueOf(0), fixture.lastMouthValue());
            assertFalse(fixture.scheduler.hasActiveTask());
        } finally {
            fixture.close();
        }
    }

    @Test
    public void playbackClockFailureStopsSessionAndResetsMouth() throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.coordinator.play(monoWindows(20000));
            MockAudioPlaybackSession session = fixture.onlySession();
            session.controllableClock().failReads(new IllegalStateException("injected clock"));
            fixture.scheduler.runLatest();
            awaitState(session, AudioPlaybackState.CLOSED);
            fixture.coordinator.awaitIdleForTest();

            assertEquals(Integer.valueOf(0), fixture.lastMouthValue());
        } finally {
            fixture.close();
        }
    }

    @Test
    public void oneMouthBackendFailureCleansUpWithoutKillingHardwareWorker()
            throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.coordinator.play(monoWindows(20000));
            MockAudioPlaybackSession session = fixture.onlySession();
            fixture.backend.failNextOperation(
                    "setLed", new RobotBackendException("injected mouth failure"));
            fixture.scheduler.runLatest();
            awaitState(session, AudioPlaybackState.CLOSED);
            fixture.coordinator.awaitIdleForTest();
            fixture.drainHardware();

            assertEquals(Integer.valueOf(0), fixture.lastMouthValue());
            assertEquals(Integer.valueOf(7), fixture.worker.submit(
                    GenerationToken.alwaysValid(),
                    new HardwareCommand<Integer>() {
                        @Override
                        public Integer execute(RobotBackend backend) {
                            return Integer.valueOf(7);
                        }
                    }).get(2, TimeUnit.SECONDS));
        } finally {
            fixture.close();
        }
    }

    @Test
    public void openFailurePreservesPrimaryErrorAndAttemptsZeroCleanup() throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.output.failNextOpen(new AudioOutputException("injected open"));
            try {
                fixture.coordinator.play(monoWindows(1000));
                fail("expected open failure");
            } catch (ApplicationDispatchException expected) {
                assertTrue(expected.getCause().getMessage().contains("injected open"));
            }
            assertEquals(Integer.valueOf(0), fixture.lastMouthValue());
        } finally {
            fixture.close();
        }
    }

    @Test
    public void startFailureClosesOpenedSessionAndAttemptsZeroCleanup() throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.output.failNextStart(new AudioOutputException("injected start"));
            try {
                fixture.coordinator.play(monoWindows(1000));
                fail("expected start failure");
            } catch (ApplicationDispatchException expected) {
                assertTrue(expected.getCause().getMessage().contains("injected start"));
            }
            assertEquals(AudioPlaybackState.CLOSED, fixture.onlySession().state());
            assertEquals(Integer.valueOf(0), fixture.lastMouthValue());
        } finally {
            fixture.close();
        }
    }

    @Test
    public void analysisFailureDoesNotOpenOutputAndStillAttemptsZeroCleanup()
            throws Exception {
        Fixture fixture = new Fixture();
        try {
            try {
                fixture.coordinator.play(new PcmAudioData(1, 1, new byte[2]));
                fail("expected analysis failure");
            } catch (ApplicationDispatchException expected) {
                assertTrue(expected.getCause().getMessage().contains("shorter than one"));
            }
            assertTrue(fixture.output.sessions().isEmpty());
            assertEquals(Integer.valueOf(0), fixture.lastMouthValue());
        } finally {
            fixture.close();
        }
    }

    @Test
    public void cleanupFailureIsSuppressedWithoutReplacingPrimaryOpenFailure()
            throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.output.failNextOpen(new AudioOutputException("primary open"));
            fixture.backend.failNextOperation(
                    "setLed", new RobotBackendException("secondary reset"));
            try {
                fixture.coordinator.play(monoWindows(1000));
                fail("expected open failure");
            } catch (ApplicationDispatchException expected) {
                Throwable cause = expected.getCause();
                assertTrue(cause.getMessage().contains("primary open"));
                assertEquals(1, cause.getSuppressed().length);
                assertTrue(cause.getSuppressed()[0].getMessage().contains("secondary reset"));
            }
        } finally {
            fixture.close();
        }
    }

    @Test
    public void shutdownStopsSessionResetsMouthAndRejectsNewPlay() throws Exception {
        Fixture fixture = new Fixture();
        fixture.coordinator.play(monoWindows(20000));
        MockAudioPlaybackSession session = fixture.onlySession();
        fixture.scheduler.runLatest();
        fixture.drainHardware();

        fixture.coordinator.close();
        fixture.worker.close();

        assertEquals(AudioPlaybackState.CLOSED, session.state());
        assertEquals(Integer.valueOf(0), fixture.lastMouthValue());
        assertTrue(fixture.scheduler.closed);
        try {
            fixture.coordinator.play(monoWindows(1));
            fail("expected closed coordinator rejection");
        } catch (ApplicationDispatchException expected) {
            // Expected.
        }
    }

    private static PcmAudioData monoWindows(int... amplitudes) {
        byte[] bytes = new byte[amplitudes.length * 20 * 2];
        for (int window = 0; window < amplitudes.length; window++) {
            for (int frame = 0; frame < 20; frame++) {
                int index = (window * 20 + frame) * 2;
                bytes[index] = (byte) amplitudes[window];
                bytes[index + 1] = (byte) (amplitudes[window] >>> 8);
            }
        }
        return new PcmAudioData(1000, 1, bytes);
    }

    private static int expectedBrightness(int amplitude) {
        return (int) Math.round(Math.abs((double) amplitude) / 32768.0 * 255.0);
    }

    private static void awaitState(
            final MockAudioPlaybackSession session,
            AudioPlaybackState expected) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
        while (session.state() != expected) {
            if (System.nanoTime() >= deadline) {
                fail("session did not reach " + expected);
            }
            Thread.yield();
        }
    }

    private static void awaitCoordinatorQueue(
            AudioSessionCoordinator coordinator,
            int count) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
        while (coordinator.queuedOperationCountForTest() != count) {
            if (System.nanoTime() >= deadline) {
                fail("unexpected coordinator queue count");
            }
            Thread.yield();
        }
    }

    private static void awaitWorkerQueue(
            SerializedHardwareWorker worker,
            int count) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
        while (worker.queuedCommandCount() != count) {
            if (System.nanoTime() >= deadline) {
                fail("unexpected hardware queue count");
            }
            Thread.yield();
        }
    }

    private static final class Fixture implements AutoCloseable {
        private final MockRobotBackend backend;
        private final MockAudioOutput output = new MockAudioOutput();
        private final ManualMouthSyncScheduler scheduler = new ManualMouthSyncScheduler();
        private final SerializedHardwareWorker worker;
        private final AudioSessionCoordinator coordinator;

        private Fixture() {
            this(null);
        }

        private Fixture(HardwareExecutionHook hook) {
            backend = new MockRobotBackend();
            worker = hook == null
                    ? new SerializedHardwareWorker(backend, 8)
                    : new SerializedHardwareWorker(backend, 8, hook);
            coordinator = new AudioSessionCoordinator(
                    output,
                    worker,
                    new GenerationRegistry(),
                    scheduler,
                    new MouthEnvelopeAnalyzer(new MouthEnvelopeConfig(
                            20, 0.0d, 1.0d, 1.0d, 0, 0, 255)),
                    8,
                    2_000L);
        }

        private MockAudioPlaybackSession onlySession() {
            List<MockAudioPlaybackSession> sessions = output.sessions();
            return sessions.get(sessions.size() - 1);
        }

        private void drainHardware() throws Exception {
            worker.submit(
                    GenerationToken.alwaysValid(),
                    new HardwareCommand<Void>() {
                        @Override
                        public Void execute(RobotBackend target) {
                            return null;
                        }
                    }).get(2, TimeUnit.SECONDS);
        }

        private Integer lastMouthValue() {
            List<Integer> values = backend.ledValueHistory("MOUTH");
            return values.get(values.size() - 1);
        }

        @Override
        public void close() {
            coordinator.close();
            worker.close();
        }
    }

    private static final class ManualMouthSyncScheduler implements MouthSyncScheduler {
        private final List<ManualHandle> handles = new ArrayList<ManualHandle>();
        private boolean closed;

        @Override
        public synchronized MouthSyncHandle schedule(Runnable task) {
            if (closed) {
                throw new IllegalStateException("scheduler is closed");
            }
            ManualHandle handle = new ManualHandle(task);
            handles.add(handle);
            return handle;
        }

        synchronized void runLatest() {
            for (int index = handles.size() - 1; index >= 0; index--) {
                if (!handles.get(index).cancelled) {
                    handles.get(index).run();
                    return;
                }
            }
        }

        synchronized void runAll() {
            for (ManualHandle handle : new ArrayList<ManualHandle>(handles)) {
                handle.run();
            }
        }

        synchronized boolean hasActiveTask() {
            for (ManualHandle handle : handles) {
                if (!handle.cancelled) {
                    return true;
                }
            }
            return false;
        }

        @Override
        public synchronized void close() {
            closed = true;
            for (ManualHandle handle : handles) {
                handle.cancel();
            }
        }
    }

    private static final class ManualHandle implements MouthSyncHandle {
        private final Runnable task;
        private boolean cancelled;

        private ManualHandle(Runnable task) {
            this.task = task;
        }

        @Override
        public synchronized void cancel() {
            cancelled = true;
        }

        private synchronized void run() {
            if (!cancelled) {
                task.run();
            }
        }
    }

    private static final class ControllableExecutionHook implements HardwareExecutionHook {
        private volatile boolean blocking;
        private CountDownLatch entered = new CountDownLatch(1);
        private CountDownLatch release = new CountDownLatch(1);

        synchronized void blockNext() {
            blocking = true;
            entered = new CountDownLatch(1);
            release = new CountDownLatch(1);
        }

        @Override
        public void beforeExecution() throws InterruptedException {
            if (blocking) {
                blocking = false;
                entered.countDown();
                release.await();
            }
        }
    }
}
