package org.socialrobotics.robotcontroller.app;

import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

/** One owned periodic wakeup source; each wakeup selects from the current playhead. */
final class PeriodicMouthSyncScheduler implements MouthSyncScheduler {
    private final ScheduledThreadPoolExecutor executor;
    private final long intervalMilliseconds;
    private final Object lifecycleLock = new Object();
    private boolean closed;

    PeriodicMouthSyncScheduler(long intervalMilliseconds) {
        if (intervalMilliseconds <= 0L) {
            throw new IllegalArgumentException("intervalMilliseconds must be positive");
        }
        this.intervalMilliseconds = intervalMilliseconds;
        this.executor = new ScheduledThreadPoolExecutor(1, new ThreadFactory() {
            @Override
            public Thread newThread(Runnable runnable) {
                Thread thread = new Thread(runnable, "robot-mouth-synchronizer");
                thread.setDaemon(false);
                return thread;
            }
        });
        this.executor.setRemoveOnCancelPolicy(true);
        this.executor.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        this.executor.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
    }

    @Override
    public MouthSyncHandle schedule(Runnable task) {
        if (task == null) {
            throw new NullPointerException("task");
        }
        synchronized (lifecycleLock) {
            if (closed) {
                throw new IllegalStateException("mouth synchronizer is closed");
            }
            final ScheduledFuture<?> future = executor.scheduleWithFixedDelay(
                    task,
                    intervalMilliseconds,
                    intervalMilliseconds,
                    TimeUnit.MILLISECONDS);
            return new MouthSyncHandle() {
                @Override
                public void cancel() {
                    future.cancel(false);
                }
            };
        }
    }

    @Override
    public void close() {
        synchronized (lifecycleLock) {
            if (closed) {
                return;
            }
            closed = true;
            executor.shutdownNow();
        }
    }
}
