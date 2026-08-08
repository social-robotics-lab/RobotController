package org.socialrobotics.robotcontroller.core.concurrent;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.socialrobotics.robotcontroller.core.backend.RobotBackend;

/** Bounded single-thread dispatcher that owns every {@link RobotBackend} invocation. */
public final class SerializedHardwareWorker implements AutoCloseable {
    private static final HardwareExecutionHook NO_HOOK = new HardwareExecutionHook() {
        @Override
        public void beforeExecution() {
        }
    };

    private final RobotBackend backend;
    private final HardwareExecutionHook hook;
    private final ThreadPoolExecutor executor;
    private final Object lifecycleLock = new Object();
    private boolean closed;

    /** Creates a worker with the default no-op pre-execution hook. */
    public SerializedHardwareWorker(RobotBackend backend, int queueCapacity) {
        this(backend, queueCapacity, NO_HOOK);
    }

    /** Creates a worker with an injectable deterministic pre-execution hook. */
    public SerializedHardwareWorker(
            RobotBackend backend,
            int queueCapacity,
            HardwareExecutionHook hook) {
        if (backend == null) {
            throw new NullPointerException("backend");
        }
        if (queueCapacity <= 0) {
            throw new IllegalArgumentException("queueCapacity must be positive");
        }
        if (hook == null) {
            throw new NullPointerException("hook");
        }
        this.backend = backend;
        this.hook = hook;
        this.executor = new ThreadPoolExecutor(
                1,
                1,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(queueCapacity),
                new ThreadFactory() {
                    @Override
                    public Thread newThread(Runnable runnable) {
                        Thread thread = new Thread(runnable, "robot-hardware-worker");
                        thread.setDaemon(false);
                        return thread;
                    }
                },
                new ThreadPoolExecutor.AbortPolicy());
    }

    /** Submits one bounded command; a stale token completes with {@code null}. */
    public <T> Future<T> submit(
            final GenerationToken token,
            final HardwareCommand<T> command) {
        if (token == null || command == null) {
            throw new NullPointerException("token and command are required");
        }
        final FutureTask<T> task = new FutureTask<T>(new Callable<T>() {
            @Override
            public T call() throws Exception {
                try {
                    hook.beforeExecution();
                } catch (InterruptedException failure) {
                    Thread.currentThread().interrupt();
                    throw failure;
                }
                if (!token.isValid()) {
                    return null;
                }
                return command.execute(backend);
            }
        });
        synchronized (lifecycleLock) {
            if (closed) {
                throw new HardwareWorkerClosedException();
            }
            try {
                executor.execute(task);
            } catch (RejectedExecutionException rejected) {
                if (closed || executor.isShutdown()) {
                    throw new HardwareWorkerClosedException();
                }
                throw new HardwareQueueFullException();
            }
        }
        return task;
    }

    /** Returns the current bounded queue depth for observation and tests. */
    public int queuedCommandCount() {
        return executor.getQueue().size();
    }

    /** Stops accepting work and interrupts queued/running commands after the timeout. */
    public void shutdown(long timeoutMilliseconds) {
        if (timeoutMilliseconds < 0L) {
            throw new IllegalArgumentException("timeoutMilliseconds must be non-negative");
        }
        synchronized (lifecycleLock) {
            if (closed) {
                return;
            }
            closed = true;
            executor.shutdown();
        }
        boolean interrupted = false;
        try {
            if (!executor.awaitTermination(timeoutMilliseconds, TimeUnit.MILLISECONDS)) {
                executor.shutdownNow();
                executor.awaitTermination(timeoutMilliseconds, TimeUnit.MILLISECONDS);
            }
        } catch (InterruptedException failure) {
            interrupted = true;
            executor.shutdownNow();
        } finally {
            if (interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }

    @Override
    public void close() {
        shutdown(5_000L);
    }
}
