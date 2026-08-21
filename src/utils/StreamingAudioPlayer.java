package utils;

import java.io.Closeable;
import java.io.IOException;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

/**
 * Manages one acquired streaming connection per player and one active response
 * per connection. Each response owns a fresh bounded queue, writer thread, and
 * PCM device; only that writer opens, uses, and closes the device.
 */
public final class StreamingAudioPlayer {

    private static final int MAX_PCM_BYTES = 960;
    private static final String WRITER_THREAD_PREFIX =
            "RobotController-AudioWriter-";

    /** Result of a bounded PCM queue offer. */
    public enum OfferResult {
        ACCEPTED,
        FULL
    }

    interface PcmDeviceFactory {
        PcmDevice open() throws IOException;
    }

    interface PcmDevice extends Closeable {
        void write(byte[] data, int offset, int length) throws IOException;

        void drain() throws IOException;

        void drop() throws IOException;

        long getBufferFrames();

        long getPeriodFrames();
    }

    /* Package-private deterministic seam for write-boundary race tests. */
    interface WriterHook {
        void beforeWrite(long generation, byte[] pcm) throws InterruptedException;

        void abortRequested(long generation);
    }

    private static final WriterHook NO_WRITER_HOOK = new WriterHook() {
        @Override
        public void beforeWrite(long generation, byte[] pcm) {
        }

        @Override
        public void abortRequested(long generation) {
        }
    };

    private enum ConnectionState {
        IDLE,
        STARTING,
        STREAMING,
        TERMINATING,
        FAILED,
        POISONED,
        CLOSED
    }

    private enum ItemKind {
        PCM,
        END,
        ABORT
    }

    private static final class QueueItem {
        private static final QueueItem END = new QueueItem(ItemKind.END, null);
        private static final QueueItem ABORT = new QueueItem(ItemKind.ABORT, null);

        private final ItemKind kind;
        private final byte[] pcm;

        private QueueItem(ItemKind kind, byte[] pcm) {
            this.kind = kind;
            this.pcm = pcm;
        }

        private static QueueItem pcm(byte[] data) {
            return new QueueItem(ItemKind.PCM, data);
        }
    }

    private static final class ResponseContext {
        private final long generation;
        private final ArrayBlockingQueue<QueueItem> queue;
        private final Semaphore pcmSlots;
        private final Object writeBoundary = new Object();
        private final WriterHook writerHook;
        private final CountDownLatch started = new CountDownLatch(1);
        private final CountDownLatch completed = new CountDownLatch(1);

        private volatile boolean abortRequested;
        private volatile boolean startSucceeded;
        private volatile boolean cleanupFailed;
        private volatile IOException failure;
        private Thread writer;

        private ResponseContext(
                long generation, int queueCapacity, WriterHook writerHook) {
            this.generation = generation;
            /* One physical slot is reserved for END/ABORT terminal signaling. */
            this.queue = new ArrayBlockingQueue<QueueItem>(queueCapacity + 1);
            this.pcmSlots = new Semaphore(queueCapacity);
            this.writerHook = writerHook;
        }
    }

    private static final class Deadline {
        private final long startNanos = System.nanoTime();
        private final long timeoutNanos;

        private Deadline(long timeoutMillis) {
            timeoutNanos = TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
        }

        private long remainingNanos() {
            long elapsed = System.nanoTime() - startNanos;
            if (elapsed >= timeoutNanos) {
                return 0L;
            }
            return timeoutNanos - elapsed;
        }

        private boolean await(CountDownLatch latch) throws InterruptedException {
            long remaining = remainingNanos();
            return remaining > 0L
                    && latch.await(remaining, TimeUnit.NANOSECONDS);
        }
    }

    private final int queueCapacity;
    private final long offerTimeoutMillis;
    private final long barrierTimeoutMillis;
    private final PcmDeviceFactory deviceFactory;
    private final WriterHook writerHook;

    private long nextGeneration;
    private Connection acquiredConnection;

    /**
     * Creates a player whose response writers open production ALSA devices.
     * Queue and timeout values remain caller-selected for later integration.
     *
     * @param queueCapacity maximum queued PCM chunks per response
     * @param offerTimeoutMillis maximum time to wait for queue capacity
     * @param barrierTimeoutMillis maximum lifecycle barrier wait
     */
    public StreamingAudioPlayer(
            int queueCapacity,
            long offerTimeoutMillis,
            long barrierTimeoutMillis) {
        this(
                queueCapacity,
                offerTimeoutMillis,
                barrierTimeoutMillis,
                new AlsaPcmDeviceFactory(),
                NO_WRITER_HOOK);
    }

    StreamingAudioPlayer(
            int queueCapacity,
            long offerTimeoutMillis,
            long barrierTimeoutMillis,
            PcmDeviceFactory deviceFactory) {
        this(
                queueCapacity,
                offerTimeoutMillis,
                barrierTimeoutMillis,
                deviceFactory,
                NO_WRITER_HOOK);
    }

    StreamingAudioPlayer(
            int queueCapacity,
            long offerTimeoutMillis,
            long barrierTimeoutMillis,
            PcmDeviceFactory deviceFactory,
            WriterHook writerHook) {
        if (queueCapacity <= 0 || queueCapacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "Queue capacity must be between 1 and Integer.MAX_VALUE - 1.");
        }
        if (offerTimeoutMillis < 0L) {
            throw new IllegalArgumentException("Offer timeout must not be negative.");
        }
        if (barrierTimeoutMillis <= 0L) {
            throw new IllegalArgumentException("Barrier timeout must be positive.");
        }
        if (deviceFactory == null) {
            throw new IllegalArgumentException("PCM device factory must not be null.");
        }
        if (writerHook == null) {
            throw new IllegalArgumentException("Writer hook must not be null.");
        }
        this.queueCapacity = queueCapacity;
        this.offerTimeoutMillis = offerTimeoutMillis;
        this.barrierTimeoutMillis = barrierTimeoutMillis;
        this.deviceFactory = deviceFactory;
        this.writerHook = writerHook;
    }

    /**
     * Acquires this player's sole connection slot, or returns {@code null} if
     * another connection still owns it.
     */
    public Connection tryAcquireConnection() {
        while (true) {
            final Connection existing;
            synchronized (this) {
                if (acquiredConnection == null) {
                    acquiredConnection = new Connection();
                    return acquiredConnection;
                }
                existing = acquiredConnection;
            }
            if (!existing.isReleasableAfterLateCompletion()) {
                return null;
            }
            synchronized (this) {
                if (acquiredConnection == existing) {
                    acquiredConnection = null;
                }
            }
        }
    }

    private synchronized long newGeneration() {
        nextGeneration++;
        if (nextGeneration == 0L) {
            nextGeneration++;
        }
        return nextGeneration;
    }

    private synchronized void releaseConnection(Connection connection) {
        if (acquiredConnection == connection) {
            acquiredConnection = null;
        }
    }

    /** Owns a sequence of non-overlapping streaming responses. */
    public final class Connection implements Closeable {
        private final Object operationLock = new Object();

        private ConnectionState state = ConnectionState.IDLE;
        private ResponseContext response;
        private boolean closed;

        private Connection() {
        }

        /** Opens a fresh response device on its fresh writer thread. */
        public void start() throws IOException, InterruptedException {
            synchronized (operationLock) {
                startSerially();
            }
        }

        /**
         * Offers one validated PCM chunk to the active response.
         *
         * <p>On {@link OfferResult#ACCEPTED}, ownership of {@code pcm} transfers
         * to this streaming layer and the caller must not mutate it. On
         * {@link OfferResult#FULL}, ownership remains with the caller.</p>
         */
        public OfferResult offerPcm(byte[] pcm)
                throws IOException, InterruptedException {
            validatePcm(pcm);
            synchronized (operationLock) {
                return offerPcmSerially(pcm);
            }
        }

        /** Writes all accepted PCM, drains, closes, and waits for termination. */
        public void end() throws IOException, InterruptedException {
            synchronized (operationLock) {
                finishSerially();
            }
        }

        /** Discards queued PCM, drops, closes, and waits for termination. */
        public void cancel() throws IOException, InterruptedException {
            synchronized (operationLock) {
                cancelSerially();
            }
        }

        /**
         * Idempotently releases this connection after aborting any active
         * response. A timed-out or failed cleanup keeps the slot fail-closed.
         */
        @Override
        public void close() throws IOException {
            synchronized (operationLock) {
                closeSerially();
            }
        }

        private void startSerially() throws IOException, InterruptedException {
            final ResponseContext current;
            synchronized (this) {
                requireNotClosed();
                if (state != ConnectionState.IDLE) {
                    throw new IllegalStateException(
                            "Cannot start audio while connection state is " + state + ".");
                }
                current = new ResponseContext(
                        newGeneration(), queueCapacity, writerHook);
                response = current;
                state = ConnectionState.STARTING;
            }

            current.writer = new Thread(
                    new Runnable() {
                        @Override
                        public void run() {
                            runResponse(Connection.this, current);
                        }
                    },
                    WRITER_THREAD_PREFIX + current.generation);
            try {
                current.writer.start();
            } catch (RuntimeException exception) {
                synchronized (this) {
                    response = null;
                    state = ConnectionState.IDLE;
                }
                throw exception;
            } catch (Error error) {
                synchronized (this) {
                    response = null;
                    state = ConnectionState.IDLE;
                }
                throw error;
            }

            Deadline deadline = new Deadline(barrierTimeoutMillis);
            final boolean started;
            try {
                started = deadline.await(current.started);
            } catch (InterruptedException exception) {
                requestAbort(current);
                poison(current);
                throw exception;
            }
            if (!started) {
                requestAbort(current);
                poison(current);
                throw timeout("start", current);
            }

            if (!current.startSucceeded) {
                if (!awaitCompletionFailClosed(current, deadline)) {
                    requestAbort(current);
                    poison(current);
                    throw timeout("start cleanup", current);
                }
                IOException failure = completeResponse(current, "start");
                if (failure != null) {
                    throw failure;
                }
                throw new IOException(
                        "Audio start did not succeed for generation "
                                + current.generation + ".");
            }

            synchronized (this) {
                if (closed || response != current) {
                    requestAbort(current);
                    poison(current);
                    throw new IOException(
                            "Audio connection closed while starting generation "
                                    + current.generation + ".");
                }
                state = ConnectionState.STREAMING;
            }
        }

        private OfferResult offerPcmSerially(byte[] pcm)
                throws IOException, InterruptedException {
            ResponseContext current = requireStreamingResponse("offer PCM");
            throwObservedFailureIfComplete(current, "offer PCM");

            boolean accepted;
            try {
                accepted = current.pcmSlots.tryAcquire(
                        offerTimeoutMillis,
                        TimeUnit.MILLISECONDS);
            } catch (InterruptedException exception) {
                requestAbort(current);
                poison(current);
                throw exception;
            }

            if (accepted) {
                if (!current.queue.offer(QueueItem.pcm(pcm))) {
                    current.pcmSlots.release();
                    throw new IllegalStateException(
                            "Reserved PCM queue slot was unavailable.");
                }
                throwObservedFailureIfComplete(current, "offer PCM");
                return OfferResult.ACCEPTED;
            }

            synchronized (this) {
                if (response == current) {
                    state = ConnectionState.TERMINATING;
                }
            }
            requestAbort(current);
            Deadline deadline = new Deadline(barrierTimeoutMillis);
            if (!awaitCompletionFailClosed(current, deadline)) {
                poison(current);
                throw timeout("queue overflow cleanup", current);
            }
            IOException failure = completeResponse(current, "queue overflow cleanup");
            if (failure != null) {
                throw failure;
            }
            return OfferResult.FULL;
        }

        private void finishSerially() throws IOException, InterruptedException {
            ResponseContext current = requireStreamingOrFailedResponse("end");
            if (current.completed.getCount() == 0L) {
                IOException failure = completeResponse(current, "end");
                if (failure != null) {
                    throw failure;
                }
                return;
            }

            synchronized (this) {
                if (response == current) {
                    state = ConnectionState.TERMINATING;
                }
            }
            Deadline deadline = new Deadline(barrierTimeoutMillis);
            if (!current.queue.offer(QueueItem.END)) {
                requestAbort(current);
                poison(current);
                throw new IOException(
                        "Reserved END queue slot was unavailable for generation "
                                + current.generation + ".");
            }
            if (!awaitCompletionFailClosed(current, deadline)) {
                requestAbort(current);
                poison(current);
                throw timeout("end", current);
            }
            IOException failure = completeResponse(current, "end");
            if (failure != null) {
                throw failure;
            }
        }

        private void cancelSerially() throws IOException, InterruptedException {
            ResponseContext current = requireStreamingOrFailedResponse("cancel");
            synchronized (this) {
                if (response == current) {
                    state = ConnectionState.TERMINATING;
                }
            }
            requestAbort(current);
            Deadline deadline = new Deadline(barrierTimeoutMillis);
            if (!awaitCompletionFailClosed(current, deadline)) {
                poison(current);
                throw timeout("cancel", current);
            }
            IOException failure = completeResponse(current, "cancel");
            if (failure != null) {
                throw failure;
            }
        }

        private void closeSerially() throws IOException {
            final ResponseContext current;
            synchronized (this) {
                if (closed) {
                    return;
                }
                closed = true;
                if (state == ConnectionState.IDLE) {
                    state = ConnectionState.CLOSED;
                    current = null;
                } else {
                    state = ConnectionState.TERMINATING;
                    current = response;
                }
            }

            if (current == null) {
                releaseConnection(this);
                return;
            }

            requestAbort(current);
            Deadline deadline = new Deadline(barrierTimeoutMillis);
            try {
                if (!awaitCompletion(current, deadline)) {
                    poison(current);
                    throw timeout("close", current);
                }
            } catch (InterruptedException exception) {
                requestAbort(current);
                poison(current);
                Thread.currentThread().interrupt();
                throw new IOException(
                        "Interrupted while closing audio generation "
                                + current.generation + ".",
                        exception);
            }

            IOException failure = responseFailure(current, "close");
            if (current.cleanupFailed) {
                poison(current);
            } else {
                synchronized (this) {
                    if (response == current) {
                        response = null;
                    }
                    state = ConnectionState.CLOSED;
                }
                releaseConnection(this);
            }
            if (failure != null) {
                throw failure;
            }
        }

        private synchronized ResponseContext requireStreamingResponse(String operation) {
            requireNotClosed();
            if (state == ConnectionState.FAILED && response != null) {
                return response;
            }
            if (state != ConnectionState.STREAMING || response == null) {
                throw new IllegalStateException(
                        "Cannot " + operation + " while connection state is "
                                + state + ".");
            }
            return response;
        }

        private synchronized ResponseContext requireStreamingOrFailedResponse(
                String operation) {
            requireNotClosed();
            if ((state != ConnectionState.STREAMING
                    && state != ConnectionState.FAILED)
                    || response == null) {
                throw new IllegalStateException(
                        "Cannot " + operation + " while connection state is "
                                + state + ".");
            }
            return response;
        }

        private synchronized void requireNotClosed() {
            if (closed || state == ConnectionState.CLOSED
                    || state == ConnectionState.POISONED) {
                throw new IllegalStateException("Audio connection is closed.");
            }
        }

        private void throwObservedFailureIfComplete(
                ResponseContext current, String operation) throws IOException {
            if (current.completed.getCount() != 0L) {
                return;
            }
            IOException failure = completeResponse(current, operation);
            if (failure != null) {
                throw failure;
            }
            throw new IOException(
                    "Audio writer ended before " + operation + " for generation "
                            + current.generation + ".");
        }

        private IOException completeResponse(ResponseContext current, String operation) {
            IOException failure = responseFailure(current, operation);
            synchronized (this) {
                if (response == current) {
                    if (current.cleanupFailed) {
                        closed = true;
                        state = ConnectionState.POISONED;
                    } else {
                        response = null;
                        state = ConnectionState.IDLE;
                    }
                }
            }
            return failure;
        }

        private void poison(ResponseContext current) {
            boolean release = false;
            synchronized (this) {
                closed = true;
                if (response == current
                        && current.completed.getCount() == 0L
                        && !current.cleanupFailed
                        && !current.writer.isAlive()) {
                    response = null;
                    state = ConnectionState.CLOSED;
                    release = true;
                } else if (response == current) {
                    state = ConnectionState.POISONED;
                }
            }
            if (release) {
                releaseConnection(this);
            }
        }

        private boolean awaitCompletionFailClosed(
                ResponseContext current, Deadline deadline)
                throws InterruptedException {
            try {
                return awaitCompletion(current, deadline);
            } catch (InterruptedException exception) {
                requestAbort(current);
                poison(current);
                throw exception;
            }
        }

        private void onWriterComplete(ResponseContext current) {
            synchronized (this) {
                if (response != current) {
                    return;
                }
                if (state == ConnectionState.POISONED && closed) {
                    if (!current.cleanupFailed) {
                        state = ConnectionState.CLOSED;
                    }
                } else if (state == ConnectionState.STREAMING
                        || state == ConnectionState.STARTING) {
                    state = ConnectionState.FAILED;
                }
            }
        }

        private synchronized boolean isReleasableAfterLateCompletion() {
            if (!closed
                    || (state != ConnectionState.CLOSED
                            && state != ConnectionState.POISONED)
                    || response == null) {
                return false;
            }
            if (response.cleanupFailed || response.completed.getCount() != 0L
                    || response.writer.isAlive()) {
                return false;
            }
            response = null;
            state = ConnectionState.CLOSED;
            return true;
        }
    }

    private void runResponse(Connection owner, ResponseContext current) {
        PcmDevice device = null;
        IOException failure = null;
        boolean startSignalled = false;
        try {
            device = deviceFactory.open();
            if (device == null) {
                throw new IOException("PCM device factory returned null.");
            }
            current.startSucceeded = !current.abortRequested;
            current.started.countDown();
            startSignalled = true;

            if (current.abortRequested) {
                failure = dropAndClose(current, device, failure);
                device = null;
            } else {
                boolean finished = false;
                while (!finished) {
                    QueueItem item = current.queue.take();
                    if (item.kind == ItemKind.PCM) {
                        current.pcmSlots.release();
                        current.writerHook.beforeWrite(
                                current.generation, item.pcm);
                        boolean writeClaimed;
                        /*
                         * This short critical section is the write-start
                         * linearization point. Abort before it skips the chunk;
                         * abort after it treats the chunk as already in flight.
                         */
                        synchronized (current.writeBoundary) {
                            writeClaimed = !current.abortRequested;
                        }
                        if (writeClaimed) {
                            try {
                                device.write(item.pcm, 0, item.pcm.length);
                            } catch (IOException exception) {
                                failure = appendFailure(failure, exception);
                                markAbortRequested(current);
                                discardQueuedItems(current);
                                failure = dropAndClose(current, device, failure);
                                device = null;
                                finished = true;
                            }
                        }
                    } else if (item.kind == ItemKind.END) {
                        failure = drainAndClose(current, device, failure);
                        device = null;
                        finished = true;
                    } else {
                        failure = dropAndClose(current, device, failure);
                        device = null;
                        finished = true;
                    }
                }
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            failure = appendFailure(
                    failure,
                    new IOException(
                            "Audio writer interrupted for generation "
                                    + current.generation + ".",
                            exception));
            if (device != null) {
                failure = dropAndClose(current, device, failure);
                device = null;
            }
        } catch (IOException exception) {
            failure = appendFailure(failure, exception);
            if (device != null) {
                failure = dropAndClose(current, device, failure);
                device = null;
            }
        } catch (RuntimeException exception) {
            failure = appendFailure(
                    failure,
                    new IOException(
                            "Unexpected audio writer failure for generation "
                                    + current.generation + ".",
                            exception));
            if (device != null) {
                failure = dropAndClose(current, device, failure);
                device = null;
            }
        } finally {
            if (device != null) {
                failure = dropAndClose(current, device, failure);
            }
            current.failure = failure;
            discardQueuedItems(current);
            if (!startSignalled) {
                current.startSucceeded = false;
                current.started.countDown();
            }
            current.completed.countDown();
            owner.onWriterComplete(current);
        }
    }

    private static IOException drainAndClose(
            ResponseContext current, PcmDevice device, IOException failure) {
        try {
            device.drain();
        } catch (IOException exception) {
            current.cleanupFailed = true;
            failure = appendFailure(failure, exception);
        }
        return closeDevice(current, device, failure);
    }

    private static IOException dropAndClose(
            ResponseContext current, PcmDevice device, IOException failure) {
        try {
            device.drop();
        } catch (IOException exception) {
            current.cleanupFailed = true;
            failure = appendFailure(failure, exception);
        }
        return closeDevice(current, device, failure);
    }

    private static IOException closeDevice(
            ResponseContext current, PcmDevice device, IOException failure) {
        try {
            device.close();
        } catch (IOException exception) {
            current.cleanupFailed = true;
            failure = appendFailure(failure, exception);
        }
        return failure;
    }

    private static IOException appendFailure(
            IOException primary, IOException additional) {
        if (primary == null) {
            return additional;
        }
        if (primary != additional) {
            primary.addSuppressed(additional);
        }
        return primary;
    }

    private static void requestAbort(ResponseContext current) {
        markAbortRequested(current);
        discardQueuedItems(current);
        if (!current.queue.offer(QueueItem.ABORT)) {
            throw new IllegalStateException("Unable to enqueue audio abort marker.");
        }
    }

    private static void markAbortRequested(ResponseContext current) {
        synchronized (current.writeBoundary) {
            current.abortRequested = true;
        }
        current.writerHook.abortRequested(current.generation);
    }

    private static void discardQueuedItems(ResponseContext current) {
        QueueItem discarded;
        while ((discarded = current.queue.poll()) != null) {
            if (discarded.kind == ItemKind.PCM) {
                current.pcmSlots.release();
            }
        }
    }

    private static boolean awaitCompletion(
            ResponseContext current, Deadline deadline) throws InterruptedException {
        if (current.completed.getCount() != 0L && !deadline.await(current.completed)) {
            return false;
        }
        while (current.writer.isAlive()) {
            long remaining = deadline.remainingNanos();
            if (remaining <= 0L) {
                return false;
            }
            long millis = TimeUnit.NANOSECONDS.toMillis(remaining);
            int nanos = (int) (remaining
                    - TimeUnit.MILLISECONDS.toNanos(millis));
            current.writer.join(millis, nanos);
        }
        return true;
    }

    private static IOException timeout(String operation, ResponseContext current) {
        return new IOException(
                "Timed out during " + operation + " for audio generation "
                        + current.generation + ".");
    }

    private static IOException responseFailure(
            ResponseContext current, String operation) {
        if (current.failure == null) {
            return null;
        }
        return new IOException(
                "Audio " + operation + " failed for generation "
                        + current.generation + ".",
                current.failure);
    }

    private static void validatePcm(byte[] pcm) {
        if (pcm == null) {
            throw new IllegalArgumentException("PCM data must not be null.");
        }
        if (pcm.length <= 0 || pcm.length > MAX_PCM_BYTES
                || (pcm.length & 1) != 0) {
            throw new IllegalArgumentException(
                    "PCM data must contain 2 to 960 frame-aligned bytes.");
        }
    }

    private static final class AlsaPcmDeviceFactory implements PcmDeviceFactory {
        @Override
        public PcmDevice open() throws IOException {
            return new AlsaPcmDevice(AlsaPcm.open());
        }
    }

    private static final class AlsaPcmDevice implements PcmDevice {
        private final AlsaPcm pcm;

        private AlsaPcmDevice(AlsaPcm pcm) {
            this.pcm = pcm;
        }

        @Override
        public void write(byte[] data, int offset, int length) throws IOException {
            pcm.write(data, offset, length);
        }

        @Override
        public void drain() throws IOException {
            pcm.drain();
        }

        @Override
        public void drop() throws IOException {
            pcm.drop();
        }

        @Override
        public long getBufferFrames() {
            return pcm.getBufferFrames();
        }

        @Override
        public long getPeriodFrames() {
            return pcm.getPeriodFrames();
        }

        @Override
        public void close() throws IOException {
            pcm.close();
        }
    }
}
