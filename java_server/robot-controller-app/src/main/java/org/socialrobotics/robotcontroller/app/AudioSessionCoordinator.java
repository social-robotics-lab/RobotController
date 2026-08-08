package org.socialrobotics.robotcontroller.app;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.socialrobotics.robotcontroller.core.audio.AudioOutput;
import org.socialrobotics.robotcontroller.core.audio.AudioPlaybackSession;
import org.socialrobotics.robotcontroller.core.audio.AudioPlaybackState;
import org.socialrobotics.robotcontroller.core.audio.MouthEnvelope;
import org.socialrobotics.robotcontroller.core.audio.MouthEnvelopeAnalyzer;
import org.socialrobotics.robotcontroller.core.audio.PcmAudioData;
import org.socialrobotics.robotcontroller.core.backend.RobotBackend;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;
import org.socialrobotics.robotcontroller.core.concurrent.GenerationGroup;
import org.socialrobotics.robotcontroller.core.concurrent.GenerationRegistry;
import org.socialrobotics.robotcontroller.core.concurrent.GenerationToken;
import org.socialrobotics.robotcontroller.core.concurrent.HardwareCommand;
import org.socialrobotics.robotcontroller.core.concurrent.LatestHardwareCommandMailbox;
import org.socialrobotics.robotcontroller.core.concurrent.SerializedHardwareWorker;

/**
 * Owns canonical PCM playback, playhead-driven mouth synchronization, replacement,
 * stop, failure recovery, and shutdown for exactly one current audio generation.
 */
final class AudioSessionCoordinator implements AutoCloseable {
    private static final Logger LOGGER =
            Logger.getLogger(AudioSessionCoordinator.class.getName());
    private static final String MOUTH_LED_NAME = "MOUTH";

    private final AudioOutput output;
    private final SerializedHardwareWorker hardwareWorker;
    private final GenerationRegistry generations;
    private final MouthSyncScheduler scheduler;
    private final MouthEnvelopeAnalyzer analyzer;
    private final LatestHardwareCommandMailbox mouthMailbox;
    private final ThreadPoolExecutor executor;
    private final long timeoutMilliseconds;
    private final Object lifecycleLock = new Object();
    private Session currentSession;
    private boolean mouthCleanupRequired;
    private boolean activityStarted;
    private boolean closing;
    private boolean closed;

    AudioSessionCoordinator(
            AudioOutput output,
            SerializedHardwareWorker hardwareWorker,
            GenerationRegistry generations,
            MouthSyncScheduler scheduler,
            MouthEnvelopeAnalyzer analyzer,
            int queueCapacity,
            long timeoutMilliseconds) {
        if (output == null
                || hardwareWorker == null
                || generations == null
                || scheduler == null
                || analyzer == null) {
            throw new NullPointerException("audio coordinator dependencies are required");
        }
        if (queueCapacity <= 0 || timeoutMilliseconds < 0L) {
            throw new IllegalArgumentException("queue capacity and timeout are invalid");
        }
        this.output = output;
        this.hardwareWorker = hardwareWorker;
        this.generations = generations;
        this.scheduler = scheduler;
        this.analyzer = analyzer;
        this.timeoutMilliseconds = timeoutMilliseconds;
        this.mouthMailbox = new LatestHardwareCommandMailbox(hardwareWorker);
        this.executor = new ThreadPoolExecutor(
                1,
                1,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(queueCapacity),
                new ThreadFactory() {
                    @Override
                    public Thread newThread(Runnable runnable) {
                        Thread thread = new Thread(runnable, "robot-audio-coordinator");
                        thread.setDaemon(false);
                        return thread;
                    }
                },
                new ThreadPoolExecutor.AbortPolicy());
    }

    /** Replaces the current session using one already validated canonical PCM object. */
    void play(final PcmAudioData audio) throws ApplicationDispatchException {
        if (audio == null) {
            throw new NullPointerException("audio");
        }
        final GenerationToken token;
        final Future<Void> task;
        synchronized (lifecycleLock) {
            requireOpen();
            activityStarted = true;
            token = generations.begin(GenerationGroup.AUDIO);
            task = submitLocked(new Callable<Void>() {
                @Override
                public Void call() throws Exception {
                    replaceSession(token, audio);
                    return null;
                }
            });
        }
        await(task);
    }

    /** Invalidates playback and performs idempotent owned-session cleanup. */
    void stop() throws ApplicationDispatchException {
        final GenerationToken cleanupToken;
        final Future<Void> task;
        synchronized (lifecycleLock) {
            requireOpen();
            activityStarted = true;
            cleanupToken = generations.begin(GenerationGroup.AUDIO);
            task = submitLocked(new Callable<Void>() {
                @Override
                public Void call() throws Exception {
                    stopCurrent(cleanupToken);
                    return null;
                }
            });
        }
        await(task);
    }

    private void replaceSession(GenerationToken token, PcmAudioData audio) throws Exception {
        if (!token.isValid()) {
            return;
        }
        Session replaced = currentSession;
        currentSession = null;
        Exception failure = cleanupSession(replaced, token, true, null);
        if (failure != null) {
            throw failure;
        }
        if (!token.isValid()) {
            return;
        }
        mouthCleanupRequired = true;

        AudioPlaybackSession playback = null;
        try {
            MouthEnvelope envelope = analyzer.analyze(audio);
            playback = output.open(audio);
            if (!token.isValid()) {
                closeUnstarted(playback);
                return;
            }
            playback.start();
            if (!token.isValid()) {
                stopAndClose(playback);
                return;
            }
            final Session created = new Session(token, audio, envelope, playback);
            created.syncHandle = scheduler.schedule(new Runnable() {
                @Override
                public void run() {
                    synchronize(created);
                }
            });
            currentSession = created;
        } catch (Exception primary) {
            if (playback != null) {
                primary = cleanupPlayback(playback, true, primary);
            }
            primary = resetMouth(token, primary);
            throw primary;
        }
    }

    private void stopCurrent(GenerationToken cleanupToken) throws Exception {
        Session owned = currentSession;
        currentSession = null;
        Exception failure = cleanupSession(owned, cleanupToken, true, null);
        if (owned == null && mouthCleanupRequired) {
            mouthMailbox.clear();
            failure = resetMouth(cleanupToken, failure);
        }
        if (failure != null) {
            throw failure;
        }
    }

    private void synchronize(final Session session) {
        if (!session.token.isValid()) {
            return;
        }
        try {
            AudioPlaybackState state = session.playback.state();
            if (state == AudioPlaybackState.COMPLETED
                    || state == AudioPlaybackState.STOPPED
                    || state == AudioPlaybackState.CLOSED) {
                enqueueTerminalCleanup(session, null);
                return;
            }
            if (state != AudioPlaybackState.PLAYING) {
                return;
            }
            long playedFrames = session.playback.clock().playedFrames();
            final int brightness = session.envelope.brightnessAtFrame(playedFrames);
            if (!session.markBrightnessIfChanged(brightness)
                    && !mouthMailbox.hasPendingValue()) {
                return;
            }
            mouthMailbox.publish(session.token, new HardwareCommand<Void>() {
                @Override
                public Void execute(RobotBackend backend) throws RobotBackendException {
                    try {
                        backend.setLed(MOUTH_LED_NAME, brightness);
                    } catch (RobotBackendException failure) {
                        enqueueTerminalCleanup(session, failure);
                        throw failure;
                    }
                    return null;
                }
            });
        } catch (RuntimeException failure) {
            enqueueTerminalCleanup(session, failure);
        }
    }

    private void enqueueTerminalCleanup(final Session session, final Throwable primary) {
        if (!session.cleanupQueued.compareAndSet(false, true)) {
            return;
        }
        synchronized (lifecycleLock) {
            if (closing || closed) {
                return;
            }
            try {
                executor.execute(new Runnable() {
                    @Override
                    public void run() {
                        if (currentSession != session || !session.token.isValid()) {
                            return;
                        }
                        currentSession = null;
                        Exception failure = asException(primary);
                        failure = cleanupSession(
                                session,
                                session.token,
                                primary != null,
                                failure);
                        if (failure != null) {
                            LOGGER.log(
                                    Level.WARNING,
                                    "audio session failed; owned resources were cleaned: {0}",
                                    failure.getMessage());
                        }
                    }
                });
            } catch (RejectedExecutionException rejected) {
                LOGGER.log(Level.FINE, "audio cleanup was rejected during shutdown");
            }
        }
    }

    private Exception cleanupSession(
            Session session,
            GenerationToken resetToken,
            boolean stopPlayback,
            Exception primary) {
        if (session == null) {
            return primary;
        }
        MouthSyncHandle handle = session.syncHandle;
        if (handle != null) {
            try {
                handle.cancel();
            } catch (RuntimeException failure) {
                primary = append(primary, failure);
            }
        }
        mouthMailbox.clear();
        if (stopPlayback) {
            try {
                session.playback.stop();
            } catch (Exception failure) {
                primary = append(primary, failure);
            }
        }
        if (resetToken != null) {
            primary = resetMouth(resetToken, primary);
        }
        try {
            session.playback.close();
        } catch (Exception failure) {
            primary = append(primary, failure);
        }
        return primary;
    }

    private Exception cleanupPlayback(
            AudioPlaybackSession playback,
            boolean stop,
            Exception primary) {
        if (stop) {
            try {
                playback.stop();
            } catch (Exception failure) {
                primary = append(primary, failure);
            }
        }
        try {
            playback.close();
        } catch (Exception failure) {
            primary = append(primary, failure);
        }
        return primary;
    }

    private void closeUnstarted(AudioPlaybackSession playback) throws Exception {
        playback.close();
    }

    private void stopAndClose(AudioPlaybackSession playback) throws Exception {
        Exception failure = cleanupPlayback(playback, true, null);
        if (failure != null) {
            throw failure;
        }
    }

    private Exception resetMouth(
            GenerationToken token,
            Exception primary) {
        try {
            awaitHardware(hardwareWorker.submit(token, new HardwareCommand<Void>() {
                @Override
                public Void execute(RobotBackend backend) throws RobotBackendException {
                    backend.setLed(MOUTH_LED_NAME, 0);
                    return null;
                }
            }));
            mouthCleanupRequired = false;
        } catch (Exception failure) {
            primary = append(primary, failure);
        }
        return primary;
    }

    private <T> T awaitHardware(Future<T> result) throws Exception {
        try {
            return result.get(timeoutMilliseconds, TimeUnit.MILLISECONDS);
        } catch (ExecutionException failure) {
            Throwable cause = failure.getCause();
            if (cause instanceof Exception) {
                throw (Exception) cause;
            }
            throw failure;
        } catch (TimeoutException failure) {
            result.cancel(true);
            throw failure;
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            throw failure;
        }
    }

    private Future<Void> submitLocked(Callable<Void> operation)
            throws ApplicationDispatchException {
        FutureTask<Void> task = new FutureTask<Void>(operation);
        try {
            executor.execute(task);
            return task;
        } catch (RejectedExecutionException failure) {
            throw new ApplicationDispatchException("audio command queue is full", failure);
        }
    }

    private void await(Future<Void> result) throws ApplicationDispatchException {
        try {
            result.get(timeoutMilliseconds, TimeUnit.MILLISECONDS);
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            throw new ApplicationDispatchException("audio command wait was interrupted", failure);
        } catch (ExecutionException failure) {
            throw new ApplicationDispatchException("audio command failed", failure.getCause());
        } catch (TimeoutException failure) {
            result.cancel(true);
            throw new ApplicationDispatchException("audio command timed out", failure);
        }
    }

    private void requireOpen() throws ApplicationDispatchException {
        if (closing || closed) {
            throw new ApplicationDispatchException("audio coordinator is closed");
        }
    }

    int queuedOperationCountForTest() {
        return executor.getQueue().size();
    }

    void awaitIdleForTest() throws ApplicationDispatchException {
        final Future<Void> task;
        synchronized (lifecycleLock) {
            if (closed) {
                return;
            }
            task = submitLocked(new Callable<Void>() {
                @Override
                public Void call() {
                    return null;
                }
            });
        }
        await(task);
    }

    @Override
    public void close() {
        final Future<Void> cleanup;
        synchronized (lifecycleLock) {
            if (closing || closed) {
                return;
            }
            closing = true;
            if (!activityStarted) {
                cleanup = null;
            } else {
                final GenerationToken cleanupToken = generations.begin(GenerationGroup.AUDIO);
                Future<Void> submitted;
                try {
                    submitted = submitLocked(new Callable<Void>() {
                        @Override
                        public Void call() throws Exception {
                            stopCurrent(cleanupToken);
                            return null;
                        }
                    });
                } catch (ApplicationDispatchException failure) {
                    submitted = null;
                    LOGGER.log(Level.WARNING, "audio shutdown cleanup was rejected", failure);
                }
                cleanup = submitted;
            }
        }
        if (cleanup != null) {
            try {
                await(cleanup);
            } catch (ApplicationDispatchException failure) {
                LOGGER.log(Level.WARNING, "audio shutdown cleanup failed", failure);
            }
        }
        scheduler.close();
        mouthMailbox.close();
        executor.shutdownNow();
        try {
            executor.awaitTermination(timeoutMilliseconds, TimeUnit.MILLISECONDS);
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
        }
        synchronized (lifecycleLock) {
            closed = true;
        }
    }

    private static Exception append(Exception primary, Throwable secondary) {
        Exception converted = asException(secondary);
        if (primary == null) {
            return converted;
        }
        if (converted != primary) {
            primary.addSuppressed(converted);
        }
        return primary;
    }

    private static Exception asException(Throwable failure) {
        if (failure == null) {
            return null;
        }
        if (failure instanceof Exception) {
            return (Exception) failure;
        }
        return new Exception("audio session failure", failure);
    }

    private static final class Session {
        private final GenerationToken token;
        private final PcmAudioData audio;
        private final MouthEnvelope envelope;
        private final AudioPlaybackSession playback;
        private final AtomicBoolean cleanupQueued = new AtomicBoolean();
        private MouthSyncHandle syncHandle;
        private int lastBrightness = -1;

        private Session(
                GenerationToken token,
                PcmAudioData audio,
                MouthEnvelope envelope,
                AudioPlaybackSession playback) {
            this.token = token;
            this.audio = audio;
            this.envelope = envelope;
            this.playback = playback;
        }

        private synchronized boolean markBrightnessIfChanged(int brightness) {
            if (brightness == lastBrightness) {
                return false;
            }
            lastBrightness = brightness;
            return true;
        }
    }
}
