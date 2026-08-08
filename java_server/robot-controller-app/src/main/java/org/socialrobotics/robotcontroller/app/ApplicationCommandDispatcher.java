package org.socialrobotics.robotcontroller.app;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.socialrobotics.robotcontroller.core.backend.RobotBackend;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;
import org.socialrobotics.robotcontroller.core.backend.RobotPose;
import org.socialrobotics.robotcontroller.core.command.ValidatedCommand;
import org.socialrobotics.robotcontroller.core.concurrent.GenerationGroup;
import org.socialrobotics.robotcontroller.core.concurrent.GenerationRegistry;
import org.socialrobotics.robotcontroller.core.concurrent.GenerationToken;
import org.socialrobotics.robotcontroller.core.concurrent.HardwareCommand;
import org.socialrobotics.robotcontroller.core.concurrent.SerializedHardwareWorker;

/** Application-level dispatch, replacement, scheduling, and backend submission boundary. */
final class ApplicationCommandDispatcher implements AutoCloseable {
    private static final Logger LOGGER =
            Logger.getLogger(ApplicationCommandDispatcher.class.getName());

    private final SerializedHardwareWorker hardwareWorker;
    private final GenerationRegistry generations;
    private final GenerationToken systemToken;
    private final AudioSessionCoordinator audioCoordinator;
    private final ThreadPoolExecutor motionExecutor;
    private final long resultTimeoutMilliseconds;
    private final Object motionLock = new Object();
    private Future<?> activeMotion;
    private volatile boolean closed;

    ApplicationCommandDispatcher(
            SerializedHardwareWorker hardwareWorker,
            GenerationRegistry generations,
            AudioSessionCoordinator audioCoordinator,
            long resultTimeoutMilliseconds) {
        this.hardwareWorker = hardwareWorker;
        this.generations = generations;
        this.audioCoordinator = audioCoordinator;
        this.resultTimeoutMilliseconds = resultTimeoutMilliseconds;
        this.systemToken = generations.begin(GenerationGroup.SYSTEM);
        this.motionExecutor = new ThreadPoolExecutor(
                1,
                1,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(1),
                new ThreadFactory() {
                    @Override
                    public Thread newThread(Runnable runnable) {
                        Thread thread = new Thread(runnable, "robot-motion-scheduler");
                        thread.setDaemon(false);
                        return thread;
                    }
                },
                new ThreadPoolExecutor.AbortPolicy());
    }

    /** Dispatches one validated command and returns a payload only for read_axes. */
    byte[] dispatch(ValidatedCommand command) throws ApplicationDispatchException {
        if (closed) {
            throw new ApplicationDispatchException("application dispatcher is closed");
        }
        switch (command.command()) {
        case PLAY_POSE:
            playPose(command.pose());
            return null;
        case STOP_POSE:
        case STOP_MOTION:
        case STOP_IDLE_MOTION:
            stopMovement();
            return null;
        case PLAY_MOTION:
            playMotion(command.motion());
            return null;
        case PLAY_IDLE_MOTION:
            playIdleMotion(command.idlePoses(), command.idlePauseMilliseconds());
            return null;
        case PLAY_WAV:
            audioCoordinator.play(command.audio());
            return null;
        case STOP_WAV:
            audioCoordinator.stop();
            return null;
        case READ_AXES:
            return JsonObjectEncoder.encodeIntegerMap(readAxes());
        default:
            throw new ApplicationDispatchException("unsupported validated command");
        }
    }

    private void playPose(final RobotPose pose) throws ApplicationDispatchException {
        GenerationToken token = replaceMovement();
        awaitHardware(submitHardware(token, new HardwareCommand<Void>() {
            @Override
            public Void execute(RobotBackend backend) throws RobotBackendException {
                backend.applyPose(pose);
                return null;
            }
        }));
    }

    private void playMotion(final List<RobotPose> poses) throws ApplicationDispatchException {
        final GenerationToken token = replaceMovement();
        synchronized (motionLock) {
            try {
                activeMotion = motionExecutor.submit(new Runnable() {
                    @Override
                    public void run() {
                        runMotion(token, poses);
                    }
                });
            } catch (RejectedExecutionException failure) {
                throw new ApplicationDispatchException("motion scheduler queue is full", failure);
            }
        }
    }

    private void playIdleMotion(
            final List<RobotPose> poses,
            final int pauseMilliseconds) throws ApplicationDispatchException {
        final GenerationToken token = replaceMovement();
        synchronized (motionLock) {
            try {
                activeMotion = motionExecutor.submit(new Runnable() {
                    @Override
                    public void run() {
                        runIdleMotion(token, poses, pauseMilliseconds);
                    }
                });
            } catch (RejectedExecutionException failure) {
                throw new ApplicationDispatchException("motion scheduler queue is full", failure);
            }
        }
    }

    private void runIdleMotion(
            GenerationToken token,
            List<RobotPose> poses,
            int pauseMilliseconds) {
        try {
            while (token.isValid()) {
                for (final RobotPose pose : poses) {
                    if (!token.isValid()) {
                        return;
                    }
                    awaitHardware(submitHardware(token, new HardwareCommand<Void>() {
                        @Override
                        public Void execute(RobotBackend backend) throws RobotBackendException {
                            backend.applyPose(pose);
                            return null;
                        }
                    }));
                    long waitMilliseconds = (long) pose.transitionMilliseconds()
                            + pauseMilliseconds;
                    if (!token.isValid()) {
                        return;
                    }
                    new CountDownLatch(1).await(waitMilliseconds, TimeUnit.MILLISECONDS);
                }
            }
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
        } catch (ApplicationDispatchException failure) {
            if (token.isValid() && !Thread.currentThread().isInterrupted()) {
                LOGGER.log(Level.WARNING, "idle motion execution failed", failure);
            }
        }
    }

    private void runMotion(final GenerationToken token, List<RobotPose> poses) {
        try {
            for (final RobotPose pose : poses) {
                if (!token.isValid()) {
                    return;
                }
                awaitHardware(submitHardware(token, new HardwareCommand<Void>() {
                    @Override
                    public Void execute(RobotBackend backend) throws RobotBackendException {
                        backend.applyPose(pose);
                        return null;
                    }
                }));
                if (!token.isValid()) {
                    return;
                }
                if (pose.transitionMilliseconds() > 0
                        && new CountDownLatch(1).await(
                                pose.transitionMilliseconds(), TimeUnit.MILLISECONDS)) {
                    return;
                }
            }
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
        } catch (ApplicationDispatchException failure) {
            if (token.isValid() && !Thread.currentThread().isInterrupted()) {
                LOGGER.log(Level.WARNING, "motion execution failed", failure);
            }
        }
    }

    private void stopMovement() throws ApplicationDispatchException {
        generations.cancel(GenerationGroup.MOTION);
        cancelScheduledMotion();
        awaitHardware(submitHardware(systemToken, new HardwareCommand<Void>() {
            @Override
            public Void execute(RobotBackend backend) throws RobotBackendException {
                backend.requestRobotStop();
                return null;
            }
        }));
    }

    private Map<String, Integer> readAxes() throws ApplicationDispatchException {
        return awaitHardware(submitHardware(
                systemToken,
                new HardwareCommand<Map<String, Integer>>() {
                    @Override
                    public Map<String, Integer> execute(RobotBackend backend)
                            throws RobotBackendException {
                        return backend.readAxes();
                    }
                }));
    }

    private GenerationToken replaceMovement() {
        GenerationToken token = generations.begin(GenerationGroup.MOTION);
        cancelScheduledMotion();
        return token;
    }

    private void cancelScheduledMotion() {
        synchronized (motionLock) {
            if (activeMotion != null) {
                activeMotion.cancel(true);
                activeMotion = null;
            }
            motionExecutor.getQueue().clear();
            motionExecutor.purge();
        }
    }

    private <T> T awaitHardware(Future<T> result) throws ApplicationDispatchException {
        try {
            return result.get(resultTimeoutMilliseconds, TimeUnit.MILLISECONDS);
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            throw new ApplicationDispatchException("hardware command wait was interrupted", failure);
        } catch (ExecutionException failure) {
            throw new ApplicationDispatchException("hardware command failed", failure.getCause());
        } catch (TimeoutException failure) {
            result.cancel(true);
            throw new ApplicationDispatchException("hardware command timed out", failure);
        }
    }

    private <T> Future<T> submitHardware(
            GenerationToken token,
            HardwareCommand<T> command) throws ApplicationDispatchException {
        try {
            return hardwareWorker.submit(token, command);
        } catch (RuntimeException failure) {
            throw new ApplicationDispatchException("hardware command was rejected", failure);
        }
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        cancelScheduledMotion();
        motionExecutor.shutdownNow();
        audioCoordinator.close();
        generations.invalidateAll();
        try {
            motionExecutor.awaitTermination(resultTimeoutMilliseconds, TimeUnit.MILLISECONDS);
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
        }
    }
}
