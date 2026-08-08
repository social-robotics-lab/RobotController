package org.socialrobotics.robotcontroller.core.concurrent;

import org.socialrobotics.robotcontroller.core.backend.RobotBackend;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;

/**
 * Bounded latest-value path for hardware updates that must not accumulate as FIFO work.
 * At most one drain task and one replaceable pending command are retained.
 */
public final class LatestHardwareCommandMailbox implements AutoCloseable {
    private final SerializedHardwareWorker worker;
    private final Object lock = new Object();
    private Pending pending;
    private boolean drainScheduled;
    private boolean closed;

    /** Creates a mailbox whose drain operations use the supplied serialized worker. */
    public LatestHardwareCommandMailbox(SerializedHardwareWorker worker) {
        if (worker == null) {
            throw new NullPointerException("worker");
        }
        this.worker = worker;
    }

    /** Replaces the pending command and ensures one serialized drain is scheduled. */
    public void publish(GenerationToken token, HardwareCommand<Void> command) {
        if (token == null || command == null) {
            throw new NullPointerException("token and command are required");
        }
        boolean schedule = false;
        synchronized (lock) {
            if (closed) {
                throw new HardwareWorkerClosedException();
            }
            pending = new Pending(token, command);
            if (!drainScheduled) {
                drainScheduled = true;
                schedule = true;
            }
        }
        if (schedule) {
            try {
                scheduleDrain();
            } catch (RuntimeException failure) {
                synchronized (lock) {
                    drainScheduled = false;
                }
                throw failure;
            }
        }
    }

    /** Discards any not-yet-selected update without interrupting the hardware worker. */
    public void clear() {
        synchronized (lock) {
            pending = null;
        }
    }

    /** Returns whether the bounded mailbox currently retains one pending update. */
    public boolean hasPendingValue() {
        synchronized (lock) {
            return pending != null;
        }
    }

    private void scheduleDrain() {
        worker.submit(
                GenerationToken.alwaysValid(),
                new HardwareCommand<Void>() {
                    @Override
                    public Void execute(RobotBackend backend) throws RobotBackendException {
                        drainOne(backend);
                        return null;
                    }
                });
    }

    private void drainOne(RobotBackend backend) throws RobotBackendException {
        Pending selected;
        synchronized (lock) {
            if (closed) {
                pending = null;
                drainScheduled = false;
                return;
            }
            selected = pending;
            pending = null;
        }
        try {
            if (selected != null && selected.token.isValid()) {
                selected.command.execute(backend);
            }
        } finally {
            rescheduleIfPending();
        }
    }

    private void rescheduleIfPending() {
        boolean schedule;
        synchronized (lock) {
            drainScheduled = false;
            schedule = !closed && pending != null;
            if (schedule) {
                drainScheduled = true;
            }
        }
        if (schedule) {
            try {
                scheduleDrain();
            } catch (RuntimeException rejected) {
                // A later publish retries. The latest pending value remains bounded and retained.
                synchronized (lock) {
                    drainScheduled = false;
                }
            }
        }
    }

    /** Stops accepting updates and discards the replaceable pending value. */
    @Override
    public void close() {
        synchronized (lock) {
            if (closed) {
                return;
            }
            closed = true;
            pending = null;
        }
    }

    private static final class Pending {
        private final GenerationToken token;
        private final HardwareCommand<Void> command;

        private Pending(GenerationToken token, HardwareCommand<Void> command) {
            this.token = token;
            this.command = command;
        }
    }
}
