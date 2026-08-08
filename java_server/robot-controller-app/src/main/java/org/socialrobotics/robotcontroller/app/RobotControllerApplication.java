package org.socialrobotics.robotcontroller.app;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.socialrobotics.robotcontroller.core.audio.AudioOutput;
import org.socialrobotics.robotcontroller.core.audio.MouthEnvelopeAnalyzer;
import org.socialrobotics.robotcontroller.core.audio.MouthEnvelopeConfig;
import org.socialrobotics.robotcontroller.core.backend.RobotBackend;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;
import org.socialrobotics.robotcontroller.core.backend.RobotLifecycleState;
import org.socialrobotics.robotcontroller.core.command.CommandValidationLimits;
import org.socialrobotics.robotcontroller.core.command.LegacyCommandValidator;
import org.socialrobotics.robotcontroller.core.command.RobotProfile;
import org.socialrobotics.robotcontroller.core.concurrent.GenerationRegistry;
import org.socialrobotics.robotcontroller.core.concurrent.GenerationToken;
import org.socialrobotics.robotcontroller.core.concurrent.HardwareCommand;
import org.socialrobotics.robotcontroller.core.concurrent.SerializedHardwareWorker;

/** Composition lifecycle owner: initialize, become ready, then bind TCP, and close in reverse. */
public final class RobotControllerApplication implements AutoCloseable {
    private static final Logger LOGGER =
            Logger.getLogger(RobotControllerApplication.class.getName());

    private final ApplicationConfiguration configuration;
    private final RobotBackend backend;
    private final SerializedHardwareWorker hardwareWorker;
    private final GenerationRegistry generations;
    private final ApplicationCommandDispatcher dispatcher;
    private final BoundedTcpServer tcpServer;
    private final AtomicReference<RobotLifecycleState> lifecycle =
            new AtomicReference<RobotLifecycleState>(RobotLifecycleState.STARTING);
    private final Object lifecycleLock = new Object();
    private SingleInstanceProcessLock processLock;
    private boolean backendInitializationAttempted;

    /** Creates an unstarted application without opening a listen or device socket. */
    public RobotControllerApplication(
            ApplicationConfiguration configuration,
            RobotBackend backend,
            AudioOutput audioOutput) {
        this(
                configuration,
                backend,
                audioOutput,
                new PeriodicMouthSyncScheduler(
                        configuration.mouthSynchronizationIntervalMilliseconds()),
                new MouthEnvelopeAnalyzer(defaultMouthEnvelopeConfig()));
    }

    RobotControllerApplication(
            ApplicationConfiguration configuration,
            RobotBackend backend,
            AudioOutput audioOutput,
            MouthSyncScheduler mouthSyncScheduler,
            MouthEnvelopeAnalyzer mouthEnvelopeAnalyzer) {
        if (configuration == null || backend == null || audioOutput == null) {
            throw new NullPointerException("configuration, backend, and audioOutput are required");
        }
        if (mouthSyncScheduler == null || mouthEnvelopeAnalyzer == null) {
            throw new NullPointerException("mouth synchronization dependencies are required");
        }
        this.configuration = configuration;
        this.backend = backend;
        this.hardwareWorker = new SerializedHardwareWorker(
                backend, configuration.hardwareCommandQueueCapacity());
        this.generations = new GenerationRegistry();
        AudioSessionCoordinator audioCoordinator = new AudioSessionCoordinator(
                audioOutput,
                hardwareWorker,
                generations,
                mouthSyncScheduler,
                mouthEnvelopeAnalyzer,
                configuration.hardwareCommandQueueCapacity(),
                configuration.socketTimeoutMilliseconds());
        this.dispatcher = new ApplicationCommandDispatcher(
                hardwareWorker,
                generations,
                audioCoordinator,
                configuration.socketTimeoutMilliseconds());
        CommandValidationLimits limits = new CommandValidationLimits(
                60_000,
                1_000,
                10.0d,
                60_000,
                configuration.maximumJsonFrameBytes(),
                configuration.maximumWavFrameBytes(),
                configuration.maximumAudioDurationMilliseconds());
        LegacyCommandValidator validator = new LegacyCommandValidator(
                RobotProfile.sotaCompatibilityProfile(), limits);
        this.tcpServer = new BoundedTcpServer(
                configuration,
                new LegacyConnectionHandler(configuration, validator, dispatcher));
    }

    /** Returns the conservative hardware-independent mouth-envelope defaults. */
    private static MouthEnvelopeConfig defaultMouthEnvelopeConfig() {
        return new MouthEnvelopeConfig(
                20,
                0.02d,
                2.0d,
                0.5d,
                40,
                100,
                16);
    }

    /** Acquires the process lock, initializes the backend, enters READY, then binds TCP. */
    public void start() throws ApplicationStartupException {
        synchronized (lifecycleLock) {
            if (lifecycle.get() != RobotLifecycleState.STARTING) {
                throw new IllegalStateException("application can only be started once");
            }
            logEffectiveConfiguration();
            try {
                processLock = SingleInstanceProcessLock.acquire(
                        configuration.processLockPath());
                LOGGER.log(Level.INFO, "lifecycle starting -> initializing");
                lifecycle.set(RobotLifecycleState.INITIALIZING);
                backendInitializationAttempted = true;
                await(hardwareWorker.submit(
                        GenerationToken.alwaysValid(),
                        new HardwareCommand<Void>() {
                            @Override
                            public Void execute(RobotBackend target)
                                    throws RobotBackendException {
                                target.initialize();
                                return null;
                            }
                        }));
                if (backend.lifecycleState() != RobotLifecycleState.READY) {
                    throw new IllegalStateException("backend did not enter READY");
                }
                lifecycle.set(RobotLifecycleState.READY);
                tcpServer.start();
                LOGGER.log(
                        Level.INFO,
                        "lifecycle initializing -> ready; listening on {0}:{1}",
                        new Object[] {
                            configuration.listenHost(), Integer.valueOf(tcpServer.localPort())
                        });
            } catch (Exception failure) {
                lifecycle.set(RobotLifecycleState.FAILED);
                cleanupAfterFailure();
                throw new ApplicationStartupException("RobotController startup failed", failure);
            }
        }
    }

    /** Returns the current application lifecycle state. */
    public RobotLifecycleState lifecycleState() {
        return lifecycle.get();
    }

    /** Returns the bound local port, or {@code -1} before listen. */
    public int localPort() {
        return tcpServer.localPort();
    }

    int queuedHardwareCommandCount() {
        return hardwareWorker.queuedCommandCount();
    }

    int activeConnectionHandlerCount() {
        return tcpServer.activeConnectionHandlerCount();
    }

    int queuedConnectionCount() {
        return tcpServer.queuedConnectionCount();
    }

    @Override
    public void close() {
        synchronized (lifecycleLock) {
            RobotLifecycleState state = lifecycle.get();
            if (state == RobotLifecycleState.STOPPED
                    || state == RobotLifecycleState.STOPPING) {
                return;
            }
            if (state == RobotLifecycleState.FAILED) {
                return;
            }
            lifecycle.set(RobotLifecycleState.STOPPING);
            LOGGER.log(Level.INFO, "lifecycle {0} -> stopping", state);
            tcpServer.close();
            dispatcher.close();
            if (backendInitializationAttempted) {
                closeBackendBestEffort();
            }
            hardwareWorker.shutdown(configuration.shutdownTimeoutMilliseconds());
            releaseProcessLockBestEffort();
            lifecycle.set(RobotLifecycleState.STOPPED);
            LOGGER.log(Level.INFO, "lifecycle stopping -> stopped");
        }
    }

    private <T> T await(Future<T> result) throws Exception {
        try {
            return result.get(
                    configuration.shutdownTimeoutMilliseconds(), TimeUnit.MILLISECONDS);
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

    private void cleanupAfterFailure() {
        tcpServer.close();
        dispatcher.close();
        if (backendInitializationAttempted) {
            closeBackendBestEffort();
        }
        hardwareWorker.shutdown(configuration.shutdownTimeoutMilliseconds());
        releaseProcessLockBestEffort();
    }

    private void closeBackendBestEffort() {
        try {
            await(hardwareWorker.submit(
                    GenerationToken.alwaysValid(),
                    new HardwareCommand<Void>() {
                        @Override
                        public Void execute(RobotBackend target) throws RobotBackendException {
                            target.close();
                            return null;
                        }
                    }));
        } catch (Exception failure) {
            LOGGER.log(Level.WARNING, "backend close failed", failure);
        }
    }

    private void releaseProcessLockBestEffort() {
        SingleInstanceProcessLock owned = processLock;
        processLock = null;
        if (owned == null) {
            return;
        }
        try {
            owned.close();
        } catch (ProcessLockException failure) {
            LOGGER.log(Level.WARNING, "process lock release failed", failure);
        }
    }

    private void logEffectiveConfiguration() {
        Package applicationPackage = RobotControllerApplication.class.getPackage();
        String version = applicationPackage == null
                ? null
                : applicationPackage.getImplementationVersion();
        if (version == null) {
            version = "development";
        }
        LOGGER.log(
                Level.INFO,
                "RobotController {0}; backend={1}; listen={2}:{3}; "
                        + "workers={4}; connectionQueue={5}; hardwareQueue={6}; "
                        + "frameLimits(command/json/wav)={7}/{8}/{9}; "
                        + "timeouts(socket/shutdown)={10}/{11}ms; "
                        + "audioDurationLimit={12}ms; mouthSyncInterval={13}ms; lock={14}",
                new Object[] {
                    version,
                    configuration.backendSelection(),
                    configuration.listenHost(),
                    Integer.valueOf(configuration.listenPort()),
                    Integer.valueOf(configuration.connectionWorkerCount()),
                    Integer.valueOf(configuration.connectionQueueCapacity()),
                    Integer.valueOf(configuration.hardwareCommandQueueCapacity()),
                    Integer.valueOf(configuration.maximumCommandFrameBytes()),
                    Integer.valueOf(configuration.maximumJsonFrameBytes()),
                    Integer.valueOf(configuration.maximumWavFrameBytes()),
                    Integer.valueOf(configuration.socketTimeoutMilliseconds()),
                    Integer.valueOf(configuration.shutdownTimeoutMilliseconds()),
                    Long.valueOf(configuration.maximumAudioDurationMilliseconds()),
                    Long.valueOf(configuration.mouthSynchronizationIntervalMilliseconds()),
                    configuration.processLockPath()
                });
    }
}
