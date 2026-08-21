package utils;

import java.io.IOException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Java 8-only deterministic test runner for {@link StreamingAudioPlayer}. */
public final class StreamingAudioPlayerTest {

    private static final long TEST_TIMEOUT_MILLIS = 3000L;
    private static int testsRun;

    private StreamingAudioPlayerTest() {
    }

    public static void main(String[] args) throws Exception {
        run("configuration and connection exclusivity", new CheckedRunnable() {
            @Override public void run() throws Exception { testConfigurationAndConnectionExclusivity(); }
        });
        run("START barrier, underflow, and writer ownership", new CheckedRunnable() {
            @Override public void run() throws Exception { testStartBarrierUnderflowAndOwnership(); }
        });
        run("START failure and timeout", new CheckedRunnable() {
            @Override public void run() throws Exception { testStartFailureAndTimeout(); }
        });
        run("FIFO END barrier", new CheckedRunnable() {
            @Override public void run() throws Exception { testFifoAndEndBarrier(); }
        });
        run("CANCEL discard and generation isolation", new CheckedRunnable() {
            @Override public void run() throws Exception { testCancelDiscardAndGenerationIsolation(); }
        });
        run("CANCEL after dequeue before write", new CheckedRunnable() {
            @Override public void run() throws Exception { testCancelAfterDequeueBeforeWrite(); }
        });
        run("END while PCM queue is full", new CheckedRunnable() {
            @Override public void run() throws Exception { testEndWhileQueueFull(); }
        });
        run("queue overflow cleanup", new CheckedRunnable() {
            @Override public void run() throws Exception { testQueueOverflowCleanup(); }
        });
        run("asynchronous write failure observers", new CheckedRunnable() {
            @Override public void run() throws Exception { testAsyncWriteFailureObservers(); }
        });
        run("drain, drop, and close failures", new CheckedRunnable() {
            @Override public void run() throws Exception { testCleanupFailures(); }
        });
        run("active close abort and idempotency", new CheckedRunnable() {
            @Override public void run() throws Exception { testActiveCloseAndIdempotency(); }
        });
        run("fail-closed timeout and late release", new CheckedRunnable() {
            @Override public void run() throws Exception { testFailClosedTimeoutAndLateRelease(); }
        });
        run("interrupted barrier remains fail-closed", new CheckedRunnable() {
            @Override public void run() throws Exception { testInterruptedBarrierFailClosed(); }
        });
        run("invalid lifecycle and PCM validation", new CheckedRunnable() {
            @Override public void run() throws Exception { testInvalidLifecycleAndPcmValidation(); }
        });
        assertNoLiveAudioWriters();
        System.out.println("ALL TESTS PASSED (" + testsRun + ")");
    }

    private static void testConfigurationAndConnectionExclusivity() throws Exception {
        final FakeFactory factory = new FakeFactory();
        expectThrows(IllegalArgumentException.class, new CheckedRunnable() {
            @Override public void run() { new StreamingAudioPlayer(0, 0L, 1L, factory); }
        });
        expectThrows(IllegalArgumentException.class, new CheckedRunnable() {
            @Override public void run() { new StreamingAudioPlayer(1, -1L, 1L, factory); }
        });
        expectThrows(IllegalArgumentException.class, new CheckedRunnable() {
            @Override public void run() { new StreamingAudioPlayer(1, 0L, 0L, factory); }
        });
        expectThrows(IllegalArgumentException.class, new CheckedRunnable() {
            @Override public void run() { new StreamingAudioPlayer(1, 0L, 1L, null); }
        });

        StreamingAudioPlayer player = player(factory, 2, 20L, 500L);
        StreamingAudioPlayer.Connection first = player.tryAcquireConnection();
        assertNotNull(first, "first connection");
        assertNull(player.tryAcquireConnection(), "second concurrent connection");
        first.close();
        first.close();
        StreamingAudioPlayer.Connection replacement = player.tryAcquireConnection();
        assertNotNull(replacement, "replacement connection");
        replacement.close();
    }

    private static void testStartBarrierUnderflowAndOwnership() throws Exception {
        FakeFactory factory = new FakeFactory();
        FakeDevice device = new FakeDevice("start", factory.events);
        factory.add(device);
        factory.blockOpen();
        StreamingAudioPlayer player = player(factory, 3, 20L, 1000L);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);

        AsyncCall start = async("test-start-barrier", new CheckedRunnable() {
            @Override public void run() throws Exception { connection.start(); }
        });
        await(factory.openEntered, "factory open entry");
        assertNotDone(start, "start returned before open completed");
        factory.releaseOpen();
        start.awaitSuccess();
        assertEquals(1, factory.openCount.get(), "open count");
        assertEquals(0, device.drainCount.get(), "underflow drain count");
        assertEquals(0, device.dropCount.get(), "underflow drop count");
        assertEquals(0, device.closeCount.get(), "underflow close count");

        assertEquals(StreamingAudioPlayer.OfferResult.ACCEPTED,
                connection.offerPcm(pcm(7, 2)), "underflow follow-up offer");
        await(device.writeEntered, "underflow follow-up write");
        connection.end();
        assertOperations(device, "write:7", "drain", "close");
        assertWriterOwnership(factory, device);
        connection.close();
    }

    private static void testStartFailureAndTimeout() throws Exception {
        FakeFactory failingFactory = new FakeFactory();
        failingFactory.openFailure = new IOException("injected open failure");
        StreamingAudioPlayer failingPlayer = player(failingFactory, 1, 10L, 500L);
        final StreamingAudioPlayer.Connection failingConnection = requireConnection(failingPlayer);
        expectThrows(IOException.class, new CheckedRunnable() {
            @Override public void run() throws Exception { failingConnection.start(); }
        });
        joinFactoryWriters(failingFactory);
        FakeDevice retryDevice = new FakeDevice("open-retry", failingFactory.events);
        failingFactory.openFailure = null;
        failingFactory.add(retryDevice);
        failingConnection.start();
        failingConnection.end();
        assertOperations(retryDevice, "drain", "close");
        failingConnection.close();
        assertNotNull(failingPlayer.tryAcquireConnection(), "slot after prompt open failure");

        FakeFactory timeoutFactory = new FakeFactory();
        FakeDevice lateDevice = new FakeDevice("late-open", timeoutFactory.events);
        timeoutFactory.add(lateDevice);
        timeoutFactory.blockOpen();
        StreamingAudioPlayer timeoutPlayer = player(timeoutFactory, 1, 10L, 40L);
        final StreamingAudioPlayer.Connection timeoutConnection = requireConnection(timeoutPlayer);
        expectThrows(IOException.class, new CheckedRunnable() {
            @Override public void run() throws Exception { timeoutConnection.start(); }
        });
        assertNull(timeoutPlayer.tryAcquireConnection(), "slot while timed-out open remains blocked");
        timeoutFactory.releaseOpen();
        await(lateDevice.closed, "late-open device close");
        joinFactoryWriters(timeoutFactory);
        assertOperations(lateDevice, "drop", "close");
        StreamingAudioPlayer.Connection afterLateClose = timeoutPlayer.tryAcquireConnection();
        assertNotNull(afterLateClose, "slot after late open cleanup");
        afterLateClose.close();
    }

    private static void testFifoAndEndBarrier() throws Exception {
        FakeFactory factory = new FakeFactory();
        final FakeDevice device = new FakeDevice("end", factory.events);
        device.blockClose();
        factory.add(device);
        StreamingAudioPlayer player = player(factory, 3, 20L, 1000L);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);
        connection.start();
        assertAccepted(connection.offerPcm(pcm(1, 2)));
        assertAccepted(connection.offerPcm(pcm(2, 4)));
        assertAccepted(connection.offerPcm(pcm(3, 6)));
        AsyncCall end = async("test-end-barrier", new CheckedRunnable() {
            @Override public void run() throws Exception { connection.end(); }
        });
        await(device.closeEntered, "END close entry");
        assertNotDone(end, "end returned before close completed");
        device.releaseClose();
        end.awaitSuccess();
        assertOperations(device, "write:1", "write:2", "write:3", "drain", "close");
        assertFalse(factory.writerThreads.get(0).isAlive(),
                "END returned before writer termination");
        connection.close();
    }

    private static void testCancelDiscardAndGenerationIsolation() throws Exception {
        FakeFactory factory = new FakeFactory();
        final FakeDevice first = new FakeDevice("generation-a", factory.events);
        FakeDevice second = new FakeDevice("generation-b", factory.events);
        first.blockWrite();
        factory.add(first);
        factory.add(second);
        StreamingAudioPlayer player = player(factory, 3, 20L, 1000L);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);
        connection.start();
        assertAccepted(connection.offerPcm(pcm(10, 2)));
        await(first.writeEntered, "generation A first write");
        assertAccepted(connection.offerPcm(pcm(11, 2)));
        assertAccepted(connection.offerPcm(pcm(12, 2)));
        AsyncCall cancel = async("test-cancel-barrier", new CheckedRunnable() {
            @Override public void run() throws Exception { connection.cancel(); }
        });
        assertNotDone(cancel, "cancel returned during blocked write");
        assertEquals(1, first.writeCount.get(), "writes before release");
        first.releaseWrite();
        cancel.awaitSuccess();
        assertOperations(first, "write:10", "drop", "close");

        connection.start();
        assertEquals(2, factory.openCount.get(), "fresh device open count");
        assertAccepted(connection.offerPcm(pcm(20, 2)));
        connection.end();
        assertOperations(second, "write:20", "drain", "close");
        assertBefore(factory.events.snapshot(), "generation-a:close", "open:generation-b",
                "old device closes before fresh open");
        connection.close();
    }

    private static void testCancelAfterDequeueBeforeWrite() throws Exception {
        FakeFactory factory = new FakeFactory();
        FakeDevice device = new FakeDevice("dequeued-cancel", factory.events);
        DequeueHook hook = new DequeueHook(21);
        factory.add(device);
        StreamingAudioPlayer player = new StreamingAudioPlayer(
                2, 20L, 1000L, factory, hook);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);
        connection.start();
        assertAccepted(connection.offerPcm(pcm(21, 2)));
        await(hook.beforeWrite, "dequeued PCM before-write hook");
        assertAccepted(connection.offerPcm(pcm(22, 2)));

        AsyncCall cancel = async("test-dequeued-cancel", new CheckedRunnable() {
            @Override public void run() throws Exception { connection.cancel(); }
        });
        await(hook.abortSeen, "dequeued PCM abort request");
        assertNotDone(cancel, "cancel returned while before-write hook was blocked");
        hook.release.countDown();
        cancel.awaitSuccess();
        assertOperations(device, "drop", "close");
        connection.close();
    }

    private static void testEndWhileQueueFull() throws Exception {
        FakeFactory factory = new FakeFactory();
        final FakeDevice device = new FakeDevice("full-end", factory.events);
        device.blockWrite();
        factory.add(device);
        StreamingAudioPlayer player = player(factory, 1, 20L, 1000L);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);
        connection.start();
        assertAccepted(connection.offerPcm(pcm(31, 2)));
        await(device.writeEntered, "full END active write");
        assertAccepted(connection.offerPcm(pcm(32, 2)));

        AsyncCall end = async("test-full-end", new CheckedRunnable() {
            @Override public void run() throws Exception { connection.end(); }
        });
        assertNotDone(end, "END returned while full queue was blocked");
        device.releaseWrite();
        end.awaitSuccess();
        assertOperations(device, "write:31", "write:32", "drain", "close");
        connection.close();
    }

    private static void testQueueOverflowCleanup() throws Exception {
        FakeFactory factory = new FakeFactory();
        final FakeDevice first = new FakeDevice("overflow-a", factory.events);
        FakeDevice second = new FakeDevice("overflow-b", factory.events);
        first.blockWrite();
        factory.add(first);
        factory.add(second);
        StreamingAudioPlayer player = player(factory, 1, 25L, 1000L);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);
        connection.start();
        assertAccepted(connection.offerPcm(pcm(1, 2)));
        await(first.writeEntered, "overflow first write");
        assertAccepted(connection.offerPcm(pcm(2, 2)));
        final ValueBox<StreamingAudioPlayer.OfferResult> result =
                new ValueBox<StreamingAudioPlayer.OfferResult>();
        AsyncCall overflow = async("test-overflow", new CheckedRunnable() {
            @Override public void run() throws Exception {
                result.value = connection.offerPcm(pcm(3, 2));
            }
        });
        assertNotDoneAfter(overflow, 80L, "FULL returned before blocked writer cleanup");
        first.releaseWrite();
        overflow.awaitSuccess();
        assertEquals(StreamingAudioPlayer.OfferResult.FULL, result.value, "overflow result");
        assertOperations(first, "write:1", "drop", "close");
        connection.start();
        assertEquals(2, factory.openCount.get(), "open after safe FULL cleanup");
        connection.end();
        assertOperations(second, "drain", "close");
        connection.close();

        FakeFactory failedCleanupFactory = new FakeFactory();
        final FakeDevice failedCleanup =
                new FakeDevice("overflow-cleanup-failure", failedCleanupFactory.events);
        failedCleanup.blockWrite();
        failedCleanup.dropFailure = new IOException("injected overflow drop failure");
        failedCleanupFactory.add(failedCleanup);
        StreamingAudioPlayer failedCleanupPlayer =
                player(failedCleanupFactory, 1, 20L, 1000L);
        final StreamingAudioPlayer.Connection failedCleanupConnection =
                requireConnection(failedCleanupPlayer);
        failedCleanupConnection.start();
        assertAccepted(failedCleanupConnection.offerPcm(pcm(4, 2)));
        await(failedCleanup.writeEntered, "failed overflow first write");
        assertAccepted(failedCleanupConnection.offerPcm(pcm(5, 2)));
        AsyncCall failedOverflow = async("test-overflow-cleanup-failure", new CheckedRunnable() {
            @Override public void run() throws Exception {
                failedCleanupConnection.offerPcm(pcm(6, 2));
            }
        });
        assertNotDoneAfter(failedOverflow, 60L,
                "overflow cleanup failure returned before write release");
        failedCleanup.releaseWrite();
        failedOverflow.awaitFailure(IOException.class);
        assertOperations(failedCleanup, "write:4", "drop", "close");
        assertNull(failedCleanupPlayer.tryAcquireConnection(),
                "slot after overflow cleanup failure");
        joinFactoryWriters(failedCleanupFactory);
    }

    private static void testAsyncWriteFailureObservers() throws Exception {
        FakeFactory factory = new FakeFactory();
        FakeDevice offerFailure = failingWriteDevice("failure-offer", factory.events);
        FakeDevice endFailure = failingWriteDevice("failure-end", factory.events);
        FakeDevice cancelFailure = failingWriteDevice("failure-cancel", factory.events);
        factory.add(offerFailure);
        factory.add(endFailure);
        factory.add(cancelFailure);
        StreamingAudioPlayer player = player(factory, 2, 20L, 1000L);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);

        connection.start();
        assertAccepted(connection.offerPcm(pcm(1, 2)));
        await(offerFailure.closed, "offer-observed failure cleanup");
        joinFactoryWriters(factory);
        expectThrows(IOException.class, new CheckedRunnable() {
            @Override public void run() throws Exception { connection.offerPcm(pcm(2, 2)); }
        });
        connection.start();
        assertAccepted(connection.offerPcm(pcm(3, 2)));
        await(endFailure.closed, "end-observed failure cleanup");
        joinFactoryWriters(factory);
        expectThrows(IOException.class, new CheckedRunnable() {
            @Override public void run() throws Exception { connection.end(); }
        });
        connection.start();
        assertAccepted(connection.offerPcm(pcm(4, 2)));
        await(cancelFailure.closed, "cancel-observed failure cleanup");
        joinFactoryWriters(factory);
        expectThrows(IOException.class, new CheckedRunnable() {
            @Override public void run() throws Exception { connection.cancel(); }
        });
        assertOperations(offerFailure, "write:1", "drop", "close");
        assertOperations(endFailure, "write:3", "drop", "close");
        assertOperations(cancelFailure, "write:4", "drop", "close");
        connection.close();
    }

    private static void testCleanupFailures() throws Exception {
        FakeFactory drainFactory = new FakeFactory();
        FakeDevice drainFailure = new FakeDevice("drain-failure", drainFactory.events);
        drainFailure.drainFailure = new IOException("injected drain failure");
        drainFactory.add(drainFailure);
        StreamingAudioPlayer drainPlayer = player(drainFactory, 1, 10L, 500L);
        final StreamingAudioPlayer.Connection drainConnection = requireConnection(drainPlayer);
        drainConnection.start();
        expectThrows(IOException.class, new CheckedRunnable() {
            @Override public void run() throws Exception { drainConnection.end(); }
        });
        assertOperations(drainFailure, "drain", "close");
        assertEquals(1, drainFailure.closeCount.get(), "drain failure close count");

        FakeFactory dropFactory = new FakeFactory();
        FakeDevice dropFailure = new FakeDevice("drop-failure", dropFactory.events);
        dropFailure.dropFailure = new IOException("injected drop failure");
        dropFactory.add(dropFailure);
        StreamingAudioPlayer dropPlayer = player(dropFactory, 1, 10L, 500L);
        final StreamingAudioPlayer.Connection dropConnection = requireConnection(dropPlayer);
        dropConnection.start();
        expectThrows(IOException.class, new CheckedRunnable() {
            @Override public void run() throws Exception { dropConnection.cancel(); }
        });
        assertOperations(dropFailure, "drop", "close");
        assertEquals(1, dropFailure.closeCount.get(), "drop failure close count");

        FakeFactory closeFactory = new FakeFactory();
        FakeDevice closeFailure = new FakeDevice("close-failure", closeFactory.events);
        closeFailure.closeFailure = new IOException("injected close failure");
        closeFactory.add(closeFailure);
        StreamingAudioPlayer closePlayer = player(closeFactory, 1, 10L, 500L);
        final StreamingAudioPlayer.Connection closeConnection = requireConnection(closePlayer);
        closeConnection.start();
        expectThrows(IOException.class, new CheckedRunnable() {
            @Override public void run() throws Exception { closeConnection.end(); }
        });
        assertOperations(closeFailure, "drain", "close");
        assertEquals(1, closeFailure.closeCount.get(), "close failure count");
        joinFactoryWriters(drainFactory);
        joinFactoryWriters(dropFactory);
        joinFactoryWriters(closeFactory);
    }

    private static void testActiveCloseAndIdempotency() throws Exception {
        FakeFactory factory = new FakeFactory();
        final FakeDevice device = new FakeDevice("active-close", factory.events);
        device.blockWrite();
        factory.add(device);
        StreamingAudioPlayer player = player(factory, 2, 20L, 1000L);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);
        connection.start();
        assertAccepted(connection.offerPcm(pcm(1, 2)));
        await(device.writeEntered, "active close first write");
        assertAccepted(connection.offerPcm(pcm(2, 2)));
        AsyncCall close = async("test-active-close", new CheckedRunnable() {
            @Override public void run() throws Exception { connection.close(); }
        });
        assertNotDone(close, "active close returned during blocked write");
        device.releaseWrite();
        close.awaitSuccess();
        assertOperations(device, "write:1", "drop", "close");
        connection.close();
        assertEquals(1, device.dropCount.get(), "idempotent active close drop count");
        assertEquals(1, device.closeCount.get(), "idempotent active close close count");
        StreamingAudioPlayer.Connection replacement = player.tryAcquireConnection();
        assertNotNull(replacement, "slot after active close");
        replacement.close();
    }

    private static void testFailClosedTimeoutAndLateRelease() throws Exception {
        FakeFactory factory = new FakeFactory();
        FakeDevice device = new FakeDevice("timeout-write", factory.events);
        device.blockWrite();
        factory.add(device);
        StreamingAudioPlayer player = player(factory, 1, 10L, 40L);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);
        connection.start();
        assertAccepted(connection.offerPcm(pcm(1, 2)));
        await(device.writeEntered, "timeout write entry");
        expectThrows(IOException.class, new CheckedRunnable() {
            @Override public void run() throws Exception { connection.cancel(); }
        });
        assertTrue(factory.writerThreads.get(0).isAlive(), "old writer must remain active at timeout");
        assertNull(player.tryAcquireConnection(), "slot after cancel timeout");
        assertEquals(1, factory.openCount.get(), "open count at timeout");
        device.releaseWrite();
        await(device.closed, "timeout late close");
        joinFactoryWriters(factory);
        assertOperations(device, "write:1", "drop", "close");
        StreamingAudioPlayer.Connection replacement = player.tryAcquireConnection();
        assertNotNull(replacement, "slot after late writer completion");
        connection.close();
        assertNull(player.tryAcquireConnection(),
                "old connection must not release replacement owner");
        replacement.close();
    }

    private static void testInterruptedBarrierFailClosed() throws Exception {
        FakeFactory factory = new FakeFactory();
        FakeDevice device = new FakeDevice("interrupted-end", factory.events);
        device.blockClose();
        factory.add(device);
        StreamingAudioPlayer player = player(factory, 1, 10L, 1000L);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);
        connection.start();
        AsyncCall end = async("test-interrupted-end", new CheckedRunnable() {
            @Override public void run() throws Exception { connection.end(); }
        });
        await(device.closeEntered, "interrupted END close entry");
        end.thread.interrupt();
        end.awaitFailure(InterruptedException.class);
        assertNull(player.tryAcquireConnection(),
                "slot before interrupted END writer completion");
        device.releaseClose();
        await(device.closed, "interrupted END close completion");
        joinFactoryWriters(factory);
        StreamingAudioPlayer.Connection replacement = player.tryAcquireConnection();
        assertNotNull(replacement, "slot after interrupted END late completion");
        replacement.close();
    }

    private static void testInvalidLifecycleAndPcmValidation() throws Exception {
        FakeFactory factory = new FakeFactory();
        final FakeDevice device = new FakeDevice("validation", factory.events);
        device.blockWrite();
        factory.add(device);
        StreamingAudioPlayer player = player(factory, 3, 20L, 1000L);
        final StreamingAudioPlayer.Connection connection = requireConnection(player);
        expectIllegalState(new CheckedRunnable() {
            @Override public void run() throws Exception { connection.offerPcm(pcm(1, 2)); }
        });
        expectIllegalState(new CheckedRunnable() {
            @Override public void run() throws Exception { connection.end(); }
        });
        expectIllegalState(new CheckedRunnable() {
            @Override public void run() throws Exception { connection.cancel(); }
        });
        connection.start();
        expectIllegalState(new CheckedRunnable() {
            @Override public void run() throws Exception { connection.start(); }
        });
        expectIllegalArgument(new CheckedRunnable() {
            @Override public void run() throws Exception { connection.offerPcm(null); }
        });
        expectIllegalArgument(new CheckedRunnable() {
            @Override public void run() throws Exception { connection.offerPcm(new byte[0]); }
        });
        expectIllegalArgument(new CheckedRunnable() {
            @Override public void run() throws Exception { connection.offerPcm(new byte[3]); }
        });
        expectIllegalArgument(new CheckedRunnable() {
            @Override public void run() throws Exception { connection.offerPcm(new byte[962]); }
        });
        assertAccepted(connection.offerPcm(new byte[2]));
        await(device.writeEntered, "validation first valid write");
        assertAccepted(connection.offerPcm(new byte[960]));
        assertAccepted(connection.offerPcm(new byte[4]));
        AsyncCall cancel = async("test-validation-cancel", new CheckedRunnable() {
            @Override public void run() throws Exception { connection.cancel(); }
        });
        device.releaseWrite();
        cancel.awaitSuccess();
        connection.close();
        expectIllegalState(new CheckedRunnable() {
            @Override public void run() throws Exception { connection.start(); }
        });
        expectIllegalState(new CheckedRunnable() {
            @Override public void run() throws Exception { connection.offerPcm(pcm(1, 2)); }
        });
    }

    private static StreamingAudioPlayer player(FakeFactory factory, int capacity,
            long offerTimeoutMillis, long barrierTimeoutMillis) {
        return new StreamingAudioPlayer(capacity, offerTimeoutMillis, barrierTimeoutMillis, factory);
    }

    private static StreamingAudioPlayer.Connection requireConnection(StreamingAudioPlayer player) {
        StreamingAudioPlayer.Connection connection = player.tryAcquireConnection();
        assertNotNull(connection, "connection acquisition");
        return connection;
    }

    private static FakeDevice failingWriteDevice(String name, EventLog events) {
        FakeDevice device = new FakeDevice(name, events);
        device.writeFailure = new IOException("injected write failure for " + name);
        return device;
    }

    private static byte[] pcm(int value, int length) {
        byte[] data = new byte[length];
        Arrays.fill(data, (byte) value);
        return data;
    }

    private static void assertAccepted(StreamingAudioPlayer.OfferResult result) {
        assertEquals(StreamingAudioPlayer.OfferResult.ACCEPTED, result, "offer result");
    }

    private static void assertWriterOwnership(FakeFactory factory, FakeDevice device) {
        assertEquals(1, factory.writerThreads.size(), "factory writer count");
        Thread writer = factory.writerThreads.get(0);
        assertTrue(writer.getName().startsWith("RobotController-AudioWriter-"), "writer thread name");
        for (Thread operationThread : device.operationThreads) {
            assertSame(writer, operationThread, "device operation owner");
        }
        assertTrue(writer != Thread.currentThread(), "writer differs from caller");
    }

    private static void assertOperations(FakeDevice device, String... expected) {
        assertEquals(Arrays.asList(expected), device.operationsSnapshot(), "operations for " + device.name);
    }

    private static void assertBefore(List<String> values, String first, String second, String message) {
        int firstIndex = values.indexOf(first);
        int secondIndex = values.indexOf(second);
        assertTrue(firstIndex >= 0 && secondIndex >= 0 && firstIndex < secondIndex,
                message + ": " + values);
    }

    private static void joinFactoryWriters(FakeFactory factory) throws Exception {
        List<Thread> snapshot;
        synchronized (factory.writerThreads) {
            snapshot = new ArrayList<Thread>(factory.writerThreads);
        }
        for (Thread writer : snapshot) {
            writer.join(TEST_TIMEOUT_MILLIS);
            assertFalse(writer.isAlive(), "writer thread leak: " + writer.getName());
        }
    }

    private static void assertNoLiveAudioWriters() {
        for (Thread thread : Thread.getAllStackTraces().keySet()) {
            if (thread.getName().startsWith("RobotController-AudioWriter-") && thread.isAlive()) {
                throw new AssertionError("live audio writer after tests: " + thread.getName());
            }
        }
    }

    private static AsyncCall async(String name, CheckedRunnable runnable) {
        AsyncCall call = new AsyncCall(name, runnable);
        call.start();
        return call;
    }

    private static void assertNotDone(AsyncCall call, String message) throws InterruptedException {
        assertNotDoneAfter(call, 50L, message);
    }

    private static void assertNotDoneAfter(AsyncCall call, long timeoutMillis, String message)
            throws InterruptedException {
        if (call.done.await(timeoutMillis, TimeUnit.MILLISECONDS)) {
            throw new AssertionError(message + "; failure=" + call.failure);
        }
    }

    private static void await(CountDownLatch latch, String description) throws InterruptedException {
        if (!latch.await(TEST_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)) {
            throw new AssertionError("Timed out waiting for " + description + ".");
        }
    }

    private static void run(String name, CheckedRunnable runnable) throws Exception {
        runnable.run();
        testsRun++;
        System.out.println("PASS: " + name);
    }

    private static void expectIllegalState(CheckedRunnable runnable) throws Exception {
        expectThrows(IllegalStateException.class, runnable);
    }

    private static void expectIllegalArgument(CheckedRunnable runnable) throws Exception {
        expectThrows(IllegalArgumentException.class, runnable);
    }

    private static <T extends Throwable> T expectThrows(Class<T> expected, CheckedRunnable runnable)
            throws Exception {
        try {
            runnable.run();
        } catch (Throwable failure) {
            if (expected.isInstance(failure)) {
                return expected.cast(failure);
            }
            throw new AssertionError("Expected " + expected.getName() + " but received " + failure,
                    failure);
        }
        throw new AssertionError("Expected " + expected.getName() + ".");
    }

    private static void assertTrue(boolean condition, String message) {
        if (!condition) { throw new AssertionError(message); }
    }

    private static void assertFalse(boolean condition, String message) { assertTrue(!condition, message); }
    private static void assertNull(Object value, String message) {
        if (value != null) { throw new AssertionError(message + ": expected null but was " + value); }
    }
    private static void assertNotNull(Object value, String message) {
        if (value == null) { throw new AssertionError(message + ": expected non-null value"); }
    }
    private static void assertSame(Object expected, Object actual, String message) {
        if (expected != actual) { throw new AssertionError(message + ": objects differ"); }
    }
    private static void assertEquals(Object expected, Object actual, String message) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(message + ": expected=" + expected + ", actual=" + actual);
        }
    }

    private interface CheckedRunnable { void run() throws Exception; }
    private static final class ValueBox<T> { private volatile T value; }

    private static final class AsyncCall {
        private final CountDownLatch done = new CountDownLatch(1);
        private final Thread thread;
        private volatile Throwable failure;

        private AsyncCall(String name, final CheckedRunnable runnable) {
            thread = new Thread(new Runnable() {
                @Override public void run() {
                    try { runnable.run(); }
                    catch (Throwable exception) { failure = exception; }
                    finally { done.countDown(); }
                }
            }, name);
        }

        private void start() { thread.start(); }
        private void awaitSuccess() throws Exception {
            await(done, thread.getName());
            thread.join(TEST_TIMEOUT_MILLIS);
            if (failure instanceof Exception) { throw (Exception) failure; }
            if (failure instanceof Error) { throw (Error) failure; }
            if (failure != null) { throw new AssertionError(failure); }
        }

        private <T extends Throwable> T awaitFailure(Class<T> expected)
                throws Exception {
            await(done, thread.getName());
            thread.join(TEST_TIMEOUT_MILLIS);
            if (!expected.isInstance(failure)) {
                throw new AssertionError(
                        "Expected async " + expected.getName() + " but received "
                                + failure,
                        failure);
            }
            return expected.cast(failure);
        }
    }

    private static final class EventLog {
        private final List<String> events =
                Collections.synchronizedList(new ArrayList<String>());
        private void add(String event) { events.add(event); }
        private List<String> snapshot() {
            synchronized (events) { return new ArrayList<String>(events); }
        }
    }

    private static final class DequeueHook
            implements StreamingAudioPlayer.WriterHook {
        private final int targetValue;
        private final CountDownLatch beforeWrite = new CountDownLatch(1);
        private final CountDownLatch abortSeen = new CountDownLatch(1);
        private final CountDownLatch release = new CountDownLatch(1);

        private DequeueHook(int targetValue) {
            this.targetValue = targetValue;
        }

        @Override
        public void beforeWrite(long generation, byte[] pcm)
                throws InterruptedException {
            if ((pcm[0] & 0xff) != targetValue) {
                return;
            }
            beforeWrite.countDown();
            if (!release.await(TEST_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)) {
                throw new AssertionError("Timed out in before-write hook.");
            }
        }

        @Override
        public void abortRequested(long generation) {
            abortSeen.countDown();
        }
    }

    private static final class FakeFactory implements StreamingAudioPlayer.PcmDeviceFactory {
        private final EventLog events = new EventLog();
        private final Deque<FakeDevice> devices = new ArrayDeque<FakeDevice>();
        private final AtomicInteger openCount = new AtomicInteger();
        private final List<Thread> writerThreads =
                Collections.synchronizedList(new ArrayList<Thread>());
        private final CountDownLatch openEntered = new CountDownLatch(1);
        private volatile IOException openFailure;
        private volatile CountDownLatch openRelease;

        private synchronized void add(FakeDevice device) { devices.addLast(device); }
        private void blockOpen() { openRelease = new CountDownLatch(1); }
        private void releaseOpen() {
            CountDownLatch release = openRelease;
            if (release != null) { release.countDown(); }
        }

        @Override public StreamingAudioPlayer.PcmDevice open() throws IOException {
            openCount.incrementAndGet();
            writerThreads.add(Thread.currentThread());
            openEntered.countDown();
            CountDownLatch release = openRelease;
            if (release != null) {
                try {
                    if (!release.await(
                            TEST_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)) {
                        throw new IOException("Timed out waiting for fake open release.");
                    }
                }
                catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    throw new IOException("fake open interrupted", exception);
                }
            }
            if (openFailure != null) { throw openFailure; }
            FakeDevice device;
            synchronized (this) { device = devices.pollFirst(); }
            if (device == null) { throw new IOException("No fake PCM device configured."); }
            events.add("open:" + device.name);
            return device;
        }
    }

    private static final class FakeDevice implements StreamingAudioPlayer.PcmDevice {
        private final String name;
        private final EventLog events;
        private final List<String> operations =
                Collections.synchronizedList(new ArrayList<String>());
        private final List<Thread> operationThreads =
                Collections.synchronizedList(new ArrayList<Thread>());
        private final AtomicInteger writeCount = new AtomicInteger();
        private final AtomicInteger drainCount = new AtomicInteger();
        private final AtomicInteger dropCount = new AtomicInteger();
        private final AtomicInteger closeCount = new AtomicInteger();
        private final CountDownLatch writeEntered = new CountDownLatch(1);
        private final CountDownLatch closeEntered = new CountDownLatch(1);
        private final CountDownLatch closed = new CountDownLatch(1);
        private volatile CountDownLatch writeRelease;
        private volatile CountDownLatch closeRelease;
        private volatile IOException writeFailure;
        private volatile IOException drainFailure;
        private volatile IOException dropFailure;
        private volatile IOException closeFailure;

        private FakeDevice(String name, EventLog events) { this.name = name; this.events = events; }
        private void blockWrite() { writeRelease = new CountDownLatch(1); }
        private void releaseWrite() {
            CountDownLatch release = writeRelease;
            if (release != null) { release.countDown(); }
        }
        private void blockClose() { closeRelease = new CountDownLatch(1); }
        private void releaseClose() {
            CountDownLatch release = closeRelease;
            if (release != null) { release.countDown(); }
        }
        private List<String> operationsSnapshot() {
            synchronized (operations) { return new ArrayList<String>(operations); }
        }

        @Override public void write(byte[] data, int offset, int length) throws IOException {
            record("write:" + (data[offset] & 0xff));
            writeCount.incrementAndGet();
            writeEntered.countDown();
            CountDownLatch release = writeRelease;
            if (release != null) { awaitRelease(release, "fake write release"); }
            if (writeFailure != null) { throw writeFailure; }
        }
        @Override public void drain() throws IOException {
            record("drain");
            drainCount.incrementAndGet();
            if (drainFailure != null) { throw drainFailure; }
        }
        @Override public void drop() throws IOException {
            record("drop");
            dropCount.incrementAndGet();
            if (dropFailure != null) { throw dropFailure; }
        }
        @Override public long getBufferFrames() { return 2400L; }
        @Override public long getPeriodFrames() { return 480L; }
        @Override public void close() throws IOException {
            record("close");
            closeCount.incrementAndGet();
            closeEntered.countDown();
            CountDownLatch release = closeRelease;
            if (release != null) { awaitRelease(release, "fake close release"); }
            closed.countDown();
            if (closeFailure != null) { throw closeFailure; }
        }
        private void record(String operation) {
            operations.add(operation);
            operationThreads.add(Thread.currentThread());
            events.add(name + ":" + operation);
        }
        private static void awaitRelease(CountDownLatch latch, String description)
                throws IOException {
            try {
                if (!latch.await(TEST_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)) {
                    throw new IOException("Timed out waiting for " + description + ".");
                }
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IOException(description + " was interrupted.", exception);
            }
        }
    }
}
