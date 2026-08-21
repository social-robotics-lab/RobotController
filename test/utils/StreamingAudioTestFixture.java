package utils;

import java.io.IOException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Fake-backed StreamingAudioPlayer construction seam for TCP integration tests. */
public final class StreamingAudioTestFixture {
    private static final long WAIT_MILLIS = 3000L;

    private final EventLog events = new EventLog();
    private final FakeFactory factory = new FakeFactory(events);
    private final StreamingAudioPlayer player;

    public StreamingAudioTestFixture(
            int queueCapacity,
            long offerTimeoutMillis,
            long barrierTimeoutMillis) {
        player = new StreamingAudioPlayer(
                queueCapacity,
                offerTimeoutMillis,
                barrierTimeoutMillis,
                factory);
    }

    public StreamingAudioPlayer player() {
        return player;
    }

    public FakeDevice addDevice(String name) {
        FakeDevice device = new FakeDevice(name, events);
        factory.add(device);
        return device;
    }

    public void failOpen(IOException failure) {
        factory.openFailure = failure;
    }

    public void blockOpen() {
        factory.openRelease = new CountDownLatch(1);
    }

    public void awaitOpenEntered() throws InterruptedException {
        await(factory.openEntered, "fake PCM open");
    }

    public void releaseOpen() {
        CountDownLatch release = factory.openRelease;
        if (release != null) {
            release.countDown();
        }
    }

    public List<String> events() {
        return events.snapshot();
    }

    public void awaitWritersTerminated() throws InterruptedException {
        List<Thread> writers;
        synchronized (factory.writerThreads) {
            writers = new ArrayList<Thread>(factory.writerThreads);
        }
        for (Thread writer : writers) {
            writer.join(WAIT_MILLIS);
            if (writer.isAlive()) {
                throw new AssertionError("Fake audio writer did not terminate: "
                        + writer.getName());
            }
        }
    }

    private static void await(CountDownLatch latch, String description)
            throws InterruptedException {
        if (!latch.await(WAIT_MILLIS, TimeUnit.MILLISECONDS)) {
            throw new AssertionError("Timed out waiting for " + description + ".");
        }
    }

    private static final class EventLog {
        private final List<String> values =
                Collections.synchronizedList(new ArrayList<String>());

        private void add(String value) {
            values.add(value);
        }

        private List<String> snapshot() {
            synchronized (values) {
                return new ArrayList<String>(values);
            }
        }
    }

    private static final class FakeFactory
            implements StreamingAudioPlayer.PcmDeviceFactory {
        private final EventLog events;
        private final Deque<FakeDevice> devices = new ArrayDeque<FakeDevice>();
        private final List<Thread> writerThreads =
                Collections.synchronizedList(new ArrayList<Thread>());
        private final CountDownLatch openEntered = new CountDownLatch(1);
        private volatile CountDownLatch openRelease;
        private volatile IOException openFailure;

        private FakeFactory(EventLog events) {
            this.events = events;
        }

        private synchronized void add(FakeDevice device) {
            devices.addLast(device);
        }

        @Override
        public StreamingAudioPlayer.PcmDevice open() throws IOException {
            writerThreads.add(Thread.currentThread());
            openEntered.countDown();
            CountDownLatch release = openRelease;
            if (release != null) {
                try {
                    if (!release.await(WAIT_MILLIS, TimeUnit.MILLISECONDS)) {
                        throw new IOException("Timed out waiting for fake open release.");
                    }
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Fake open interrupted.", exception);
                }
            }
            if (openFailure != null) {
                throw openFailure;
            }
            FakeDevice device;
            synchronized (this) {
                device = devices.pollFirst();
            }
            if (device == null) {
                throw new IOException("No fake PCM device configured.");
            }
            events.add("open:" + device.name);
            return device;
        }
    }

    /** Deterministic fake PCM device controlled by bounded test latches. */
    public static final class FakeDevice
            implements StreamingAudioPlayer.PcmDevice {
        private final String name;
        private final EventLog events;
        private final List<String> operations =
                Collections.synchronizedList(new ArrayList<String>());
        private final CountDownLatch writeEntered = new CountDownLatch(1);
        private final CountDownLatch closeEntered = new CountDownLatch(1);
        private final CountDownLatch closed = new CountDownLatch(1);
        private volatile CountDownLatch writeRelease;
        private volatile CountDownLatch closeRelease;
        private volatile IOException writeFailure;

        private FakeDevice(String name, EventLog events) {
            this.name = name;
            this.events = events;
        }

        public void blockWrite() {
            writeRelease = new CountDownLatch(1);
        }

        public void releaseWrite() {
            CountDownLatch release = writeRelease;
            if (release != null) {
                release.countDown();
            }
        }

        public void blockClose() {
            closeRelease = new CountDownLatch(1);
        }

        public void releaseClose() {
            CountDownLatch release = closeRelease;
            if (release != null) {
                release.countDown();
            }
        }

        public void failWrite(IOException failure) {
            writeFailure = failure;
        }

        public void awaitWriteEntered() throws InterruptedException {
            await(writeEntered, name + " write");
        }

        public void awaitCloseEntered() throws InterruptedException {
            await(closeEntered, name + " close");
        }

        public void awaitClosed() throws InterruptedException {
            await(closed, name + " closed");
        }

        public List<String> operations() {
            synchronized (operations) {
                return new ArrayList<String>(operations);
            }
        }

        @Override
        public void write(byte[] data, int offset, int length) throws IOException {
            record("write:" + (data[offset] & 0xff));
            writeEntered.countDown();
            CountDownLatch release = writeRelease;
            if (release != null) {
                awaitRelease(release, "fake write release");
            }
            if (writeFailure != null) {
                throw writeFailure;
            }
        }

        @Override
        public void drain() {
            record("drain");
        }

        @Override
        public void drop() {
            record("drop");
        }

        @Override
        public long getBufferFrames() {
            return 2400L;
        }

        @Override
        public long getPeriodFrames() {
            return 480L;
        }

        @Override
        public void close() throws IOException {
            record("close");
            closeEntered.countDown();
            CountDownLatch release = closeRelease;
            if (release != null) {
                awaitRelease(release, "fake close release");
            }
            closed.countDown();
        }

        private void record(String operation) {
            operations.add(operation);
            events.add(name + ":" + operation);
        }

        private static void awaitRelease(CountDownLatch latch, String description)
                throws IOException {
            try {
                if (!latch.await(WAIT_MILLIS, TimeUnit.MILLISECONDS)) {
                    throw new IOException("Timed out waiting for " + description + ".");
                }
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IOException(description + " interrupted.", exception);
            }
        }
    }
}
