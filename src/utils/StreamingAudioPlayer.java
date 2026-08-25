package utils;

import java.io.Closeable;
import java.io.IOException;
import java.util.Locale;
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
    private static final long SLOW_WRITE_THRESHOLD_NANOS =
            TimeUnit.MILLISECONDS.toNanos(40L);
    private static final long SLOW_QUEUE_WAIT_THRESHOLD_NANOS =
            TimeUnit.MILLISECONDS.toNanos(40L);
    private static final long SLOW_INTER_WRITE_GAP_THRESHOLD_NANOS =
            TimeUnit.MILLISECONDS.toNanos(40L);
    private static final String AUDIO_DIAGNOSTIC_PREFIX = "[AUDIO_DIAG]";
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

    interface NanoClock {
        long nanoTime();
    }

    private static final NanoClock SYSTEM_NANO_CLOCK = new NanoClock() {
        @Override
        public long nanoTime() {
            return System.nanoTime();
        }
    };

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
        private volatile boolean writeInProgress;
        private volatile long writeStartNanos;
        private volatile long lastCompletedWriteDurationNanos;
        private volatile long maxCompletedWriteDurationNanos;
        private volatile long completedWriteCount;
        private volatile int queueHighWaterMark;
        private long totalCompletedWriteDurationNanos;
        private long slowWriteCount;
        private long currentConsecutiveSlowWrites;
        private long maxConsecutiveSlowWrites;
        private long maxQueueWaitNanos;
        private long maxInterWriteGapNanos;
        private long previousWriteCompletionNanos;
        private boolean hasPreviousWriteCompletion;
        private volatile String terminalReason;
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
    private final NanoClock diagnosticClock;

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
        this(
                queueCapacity,
                offerTimeoutMillis,
                barrierTimeoutMillis,
                deviceFactory,
                writerHook,
                SYSTEM_NANO_CLOCK);
    }

    StreamingAudioPlayer(
            int queueCapacity,
            long offerTimeoutMillis,
            long barrierTimeoutMillis,
            PcmDeviceFactory deviceFactory,
            NanoClock diagnosticClock) {
        this(
                queueCapacity,
                offerTimeoutMillis,
                barrierTimeoutMillis,
                deviceFactory,
                NO_WRITER_HOOK,
                diagnosticClock);
    }

    private StreamingAudioPlayer(
            int queueCapacity,
            long offerTimeoutMillis,
            long barrierTimeoutMillis,
            PcmDeviceFactory deviceFactory,
            WriterHook writerHook,
            NanoClock diagnosticClock) {
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
        if (diagnosticClock == null) {
            throw new IllegalArgumentException("Diagnostic clock must not be null.");
        }
        this.queueCapacity = queueCapacity;
        this.offerTimeoutMillis = offerTimeoutMillis;
        this.barrierTimeoutMillis = barrierTimeoutMillis;
        this.deviceFactory = deviceFactory;
        this.writerHook = writerHook;
        this.diagnosticClock = diagnosticClock;
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
                updateQueueHighWater(current);
                if (!current.queue.offer(QueueItem.pcm(pcm))) {
                    current.pcmSlots.release();
                    throw new IllegalStateException(
                            "Reserved PCM queue slot was unavailable.");
                }
                throwObservedFailureIfComplete(current, "offer PCM");
                return OfferResult.ACCEPTED;
            }

            setTerminalReason(current, "QUEUE_OVERFLOW");
            logQueueOfferTimeout(current);
            ConnectionState previousState = null;
            synchronized (this) {
                if (response == current) {
                    previousState = state;
                    state = ConnectionState.TERMINATING;
                }
            }
            if (previousState != null) {
                logStateTransition(
                        current,
                        previousState,
                        ConnectionState.TERMINATING,
                        "QUEUE_OVERFLOW");
            }
            requestAbort(current);
            Deadline deadline = new Deadline(barrierTimeoutMillis);
            if (!awaitCompletionFailClosed(current, deadline)) {
                poison(current);
                throw timeout("queue overflow cleanup", current);
            }
            IOException failure = completeResponse(
                    current,
                    "queue overflow cleanup",
                    "QUEUE_OVERFLOW_CLEANUP");
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

            setTerminalReason(current, "END");
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
            setTerminalReason(current, "CANCEL");
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

            setTerminalReason(current, "DISCONNECT");
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
            return completeResponse(current, operation, null);
        }

        private IOException completeResponse(
                ResponseContext current,
                String operation,
                String transitionReason) {
            IOException failure = responseFailure(current, operation);
            ConnectionState previousState = null;
            ConnectionState nextState = null;
            synchronized (this) {
                if (response == current) {
                    previousState = state;
                    if (current.cleanupFailed) {
                        closed = true;
                        state = ConnectionState.POISONED;
                    } else {
                        response = null;
                        state = ConnectionState.IDLE;
                    }
                    nextState = state;
                }
            }
            if (previousState != null
                    && (transitionReason != null
                            || nextState == ConnectionState.POISONED)) {
                logStateTransition(
                        current,
                        previousState,
                        nextState,
                        transitionReason != null
                                ? transitionReason
                                : "CLEANUP_FAILURE");
            }
            return failure;
        }

        private void poison(ResponseContext current) {
            boolean release = false;
            ConnectionState previousState = null;
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
                    previousState = state;
                    state = ConnectionState.POISONED;
                }
            }
            if (previousState != null) {
                logStateTransition(
                        current,
                        previousState,
                        ConnectionState.POISONED,
                        "FAIL_CLOSED");
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
            ConnectionState previousState = null;
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
                    previousState = state;
                    state = ConnectionState.FAILED;
                }
            }
            if (previousState != null) {
                logStateTransition(
                        current,
                        previousState,
                        ConnectionState.FAILED,
                        "WRITER_FAILURE");
            }
        }

        private synchronized ConnectionState snapshotState() {
            return state;
        }

        private void updateQueueHighWater(ResponseContext current) {
            int occupancy = queueCapacity - current.pcmSlots.availablePermits();
            if (occupancy > current.queueHighWaterMark) {
                current.queueHighWaterMark = occupancy;
            }
        }

        private void logQueueOfferTimeout(ResponseContext current) {
            try {
                boolean writeInProgress = current.writeInProgress;
                long currentWriteAge = 0L;
                if (writeInProgress) {
                    currentWriteAge = elapsedNanos(
                            current.writeStartNanos,
                            diagnosticClock.nanoTime());
                }
                int availablePermits = current.pcmSlots.availablePermits();
                int logicalQueueOccupancy = queueCapacity - availablePermits;
                Thread writer = current.writer;
                diagnostic(AUDIO_DIAGNOSTIC_PREFIX
                        + " QUEUE_OFFER_TIMEOUT"
                        + " generation=" + current.generation
                        + " state=" + snapshotState()
                        + " logical_queue_occupancy=" + logicalQueueOccupancy
                        + " physical_queue_size=" + current.queue.size()
                        + " available_permits=" + availablePermits
                        + " queue_high_water=" + current.queueHighWaterMark
                        + " writer_alive=" + (writer != null && writer.isAlive())
                        + " write_in_progress=" + writeInProgress
                        + " current_write_age_ms=" + formatMillis(currentWriteAge)
                        + " last_completed_write_ms="
                        + formatMillis(current.lastCompletedWriteDurationNanos)
                        + " max_completed_write_ms="
                        + formatMillis(current.maxCompletedWriteDurationNanos)
                        + " completed_write_count=" + current.completedWriteCount);
            } catch (RuntimeException ignored) {
                /* Diagnostic formatting must not alter overflow cleanup. */
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
        String failurePhase = null;
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
                    long queueWaitStart = readDiagnosticClock();
                    QueueItem item = current.queue.take();
                    long queueWaitNanos = diagnosticElapsedNanos(
                            queueWaitStart, readDiagnosticClock());
                    if (item.kind == ItemKind.PCM) {
                        current.pcmSlots.release();
                        int queueSizeAfterTake = current.queue.size();
                        int availablePermits = current.pcmSlots.availablePermits();
                        if (queueWaitNanos > current.maxQueueWaitNanos) {
                            current.maxQueueWaitNanos = queueWaitNanos;
                        }
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
                                boolean writeSucceeded = false;
                                long writeStart = beginWriteDiagnostics(current);
                                long interWriteGapNanos =
                                        current.hasPreviousWriteCompletion
                                                ? diagnosticElapsedNanos(
                                                        current.previousWriteCompletionNanos,
                                                        writeStart)
                                                : 0L;
                                if (interWriteGapNanos
                                        > current.maxInterWriteGapNanos) {
                                    current.maxInterWriteGapNanos =
                                            interWriteGapNanos;
                                }
                                try {
                                    device.write(item.pcm, 0, item.pcm.length);
                                    writeSucceeded = true;
                                } finally {
                                    finishWriteDiagnostics(
                                            current,
                                            item.pcm.length,
                                            writeStart,
                                            queueWaitNanos,
                                            interWriteGapNanos,
                                            queueSizeAfterTake,
                                            availablePermits,
                                            writeSucceeded);
                                }
                            } catch (IOException exception) {
                                failurePhase = "NATIVE_WRITE";
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
                        if (failure != null && failurePhase == null) {
                            failurePhase = "DRAIN_OR_CLOSE";
                        }
                        device = null;
                        finished = true;
                    } else {
                        failure = dropAndClose(current, device, failure);
                        if (failure != null && failurePhase == null) {
                            failurePhase = "DROP_OR_CLOSE";
                        }
                        device = null;
                        finished = true;
                    }
                }
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            failurePhase = "INTERRUPTED";
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
            if (failurePhase == null) {
                failurePhase = "OPEN_OR_WRITER";
            }
            failure = appendFailure(failure, exception);
            if (device != null) {
                failure = dropAndClose(current, device, failure);
                device = null;
            }
        } catch (RuntimeException exception) {
            failurePhase = "RUNTIME";
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
                if (failure != null && failurePhase == null) {
                    failurePhase = "DROP_OR_CLOSE";
                }
            }
            if (failure != null) {
                logWriterFailure(current, failurePhase, failure);
            }
            logStreamSummary(current, failure);
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

    private long beginWriteDiagnostics(ResponseContext current) {
        current.writeInProgress = true;
        long start = readDiagnosticClock();
        current.writeStartNanos = start != Long.MIN_VALUE ? start : 0L;
        return start;
    }

    private void finishWriteDiagnostics(
            ResponseContext current,
            int bytes,
            long writeStart,
            long queueWaitNanos,
            long interWriteGapNanos,
            int queueSizeAfterTake,
            int availablePermits,
            boolean succeeded) {
        try {
            long writeCompletion = readDiagnosticClock();
            long duration = diagnosticElapsedNanos(writeStart, writeCompletion);
            if (succeeded) {
                current.lastCompletedWriteDurationNanos = duration;
                if (duration > current.maxCompletedWriteDurationNanos) {
                    current.maxCompletedWriteDurationNanos = duration;
                }
                current.completedWriteCount++;
                current.totalCompletedWriteDurationNanos += duration;
                if (duration >= SLOW_WRITE_THRESHOLD_NANOS) {
                    current.slowWriteCount++;
                    current.currentConsecutiveSlowWrites++;
                    if (current.currentConsecutiveSlowWrites
                            > current.maxConsecutiveSlowWrites) {
                        current.maxConsecutiveSlowWrites =
                                current.currentConsecutiveSlowWrites;
                    }
                } else {
                    current.currentConsecutiveSlowWrites = 0L;
                }
                if (writeCompletion != Long.MIN_VALUE) {
                    current.previousWriteCompletionNanos = writeCompletion;
                    current.hasPreviousWriteCompletion = true;
                }
            }
            int logicalQueueOccupancy = queueCapacity - availablePermits;
            if (queueWaitNanos >= SLOW_QUEUE_WAIT_THRESHOLD_NANOS) {
                diagnostic(AUDIO_DIAGNOSTIC_PREFIX
                        + " QUEUE_WAIT_SLOW"
                        + " generation=" + current.generation
                        + " wait_ms=" + formatMillis(queueWaitNanos)
                        + " queue_size_after_take=" + queueSizeAfterTake
                        + " logical_queue_occupancy=" + logicalQueueOccupancy
                        + " available_permits=" + availablePermits);
            }
            if (current.completedWriteCount > (succeeded ? 1L : 0L)
                    && interWriteGapNanos
                            >= SLOW_INTER_WRITE_GAP_THRESHOLD_NANOS) {
                diagnostic(AUDIO_DIAGNOSTIC_PREFIX
                        + " INTER_WRITE_GAP"
                        + " generation=" + current.generation
                        + " gap_ms=" + formatMillis(interWriteGapNanos)
                        + " queue_wait_ms=" + formatMillis(queueWaitNanos)
                        + " queue_size_after_take=" + queueSizeAfterTake
                        + " logical_queue_occupancy=" + logicalQueueOccupancy
                        + " available_permits=" + availablePermits);
            }
            if (succeeded && duration >= SLOW_WRITE_THRESHOLD_NANOS) {
                diagnostic(AUDIO_DIAGNOSTIC_PREFIX
                        + " SLOW_WRITE"
                        + " generation=" + current.generation
                        + " bytes=" + bytes
                        + " duration_ms=" + formatMillis(duration));
            }
        } catch (RuntimeException ignored) {
            /* Diagnostic timing must not alter native-write handling. */
        } finally {
            current.writeInProgress = false;
        }
    }

    private void logWriterFailure(
            ResponseContext current,
            String phase,
            IOException failure) {
        try {
            diagnostic(AUDIO_DIAGNOSTIC_PREFIX
                    + " WRITER_FAILURE"
                    + " generation=" + current.generation
                    + " phase=" + (phase != null ? phase : "UNKNOWN")
                    + " exception=" + failure.getClass().getName()
                    + " message=" + diagnosticText(failure.getMessage())
                    + " write_in_progress=" + current.writeInProgress
                    + " last_completed_write_ms="
                    + formatMillis(current.lastCompletedWriteDurationNanos)
                    + " max_completed_write_ms="
                    + formatMillis(current.maxCompletedWriteDurationNanos)
                    + " completed_write_count=" + current.completedWriteCount);
        } catch (RuntimeException ignored) {
            /* Diagnostic formatting must not alter writer failure handling. */
        }
    }

    private void logStreamSummary(
            ResponseContext current, IOException failure) {
        try {
            long writes = current.completedWriteCount;
            long averageWriteDuration = writes > 0L
                    ? current.totalCompletedWriteDurationNanos / writes
                    : 0L;
            String reason = current.terminalReason;
            if (reason == null) {
                reason = failure != null ? "WRITER_FAILURE" : "DISCONNECT";
            }
            diagnostic(AUDIO_DIAGNOSTIC_PREFIX
                    + " STREAM_SUMMARY"
                    + " generation=" + current.generation
                    + " writes=" + writes
                    + " slow_writes=" + current.slowWriteCount
                    + " total_write_ms="
                    + formatMillis(current.totalCompletedWriteDurationNanos)
                    + " avg_write_ms=" + formatMillis(averageWriteDuration)
                    + " max_write_ms="
                    + formatMillis(current.maxCompletedWriteDurationNanos)
                    + " max_queue_wait_ms="
                    + formatMillis(current.maxQueueWaitNanos)
                    + " max_inter_write_gap_ms="
                    + formatMillis(current.maxInterWriteGapNanos)
                    + " queue_high_water=" + current.queueHighWaterMark
                    + " max_consecutive_slow_writes="
                    + current.maxConsecutiveSlowWrites
                    + " reason=" + reason);
        } catch (RuntimeException ignored) {
            /* Summary output must not alter writer completion. */
        }
    }

    private static void logStateTransition(
            ResponseContext current,
            ConnectionState from,
            ConnectionState to,
            String reason) {
        try {
            diagnostic(AUDIO_DIAGNOSTIC_PREFIX
                    + " STATE"
                    + " generation=" + current.generation
                    + " from=" + from
                    + " to=" + to
                    + " reason=" + reason);
        } catch (RuntimeException ignored) {
            /* Diagnostic formatting must not alter state transitions. */
        }
    }

    private static long elapsedNanos(long start, long end) {
        long elapsed = end - start;
        return elapsed >= 0L ? elapsed : 0L;
    }

    private long readDiagnosticClock() {
        try {
            return diagnosticClock.nanoTime();
        } catch (RuntimeException ignored) {
            return Long.MIN_VALUE;
        }
    }

    private static long diagnosticElapsedNanos(long start, long end) {
        if (start == Long.MIN_VALUE || end == Long.MIN_VALUE) {
            return 0L;
        }
        return elapsedNanos(start, end);
    }

    private static String formatMillis(long nanos) {
        return String.format(Locale.ROOT, "%.3f", nanos / 1000000.0d);
    }

    private static String diagnosticText(String value) {
        if (value == null) {
            return "<none>";
        }
        return value.replace('\r', ' ').replace('\n', ' ');
    }

    private static void diagnostic(String message) {
        try {
            System.err.println(message);
        } catch (RuntimeException ignored) {
            /* Diagnostic output must not alter the audio lifecycle. */
        }
    }

    private static void setTerminalReason(
            ResponseContext current, String reason) {
        if (current.terminalReason == null) {
            current.terminalReason = reason;
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
