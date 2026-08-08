package org.socialrobotics.robotcontroller.app;

import java.nio.file.Path;
import java.nio.file.Paths;

/** Immutable standard-library-only application configuration. */
public final class ApplicationConfiguration {
    private final String listenHost;
    private final int listenPort;
    private final int connectionWorkerCount;
    private final int connectionQueueCapacity;
    private final int hardwareCommandQueueCapacity;
    private final int maximumCommandFrameBytes;
    private final int maximumJsonFrameBytes;
    private final int maximumWavFrameBytes;
    private final long maximumAudioDurationMilliseconds;
    private final long mouthSynchronizationIntervalMilliseconds;
    private final int socketTimeoutMilliseconds;
    private final int shutdownTimeoutMilliseconds;
    private final Path processLockPath;
    private final BackendSelection backendSelection;

    private ApplicationConfiguration(Builder builder) {
        this.listenHost = builder.listenHost;
        this.listenPort = builder.listenPort;
        this.connectionWorkerCount = builder.connectionWorkerCount;
        this.connectionQueueCapacity = builder.connectionQueueCapacity;
        this.hardwareCommandQueueCapacity = builder.hardwareCommandQueueCapacity;
        this.maximumCommandFrameBytes = builder.maximumCommandFrameBytes;
        this.maximumJsonFrameBytes = builder.maximumJsonFrameBytes;
        this.maximumWavFrameBytes = builder.maximumWavFrameBytes;
        this.maximumAudioDurationMilliseconds = builder.maximumAudioDurationMilliseconds;
        this.mouthSynchronizationIntervalMilliseconds =
                builder.mouthSynchronizationIntervalMilliseconds;
        this.socketTimeoutMilliseconds = builder.socketTimeoutMilliseconds;
        this.shutdownTimeoutMilliseconds = builder.shutdownTimeoutMilliseconds;
        this.processLockPath = builder.processLockPath.toAbsolutePath().normalize();
        this.backendSelection = builder.backendSelection;
    }

    /** Returns a builder populated with safe bounded defaults except backend selection. */
    public static Builder builder() {
        return new Builder();
    }

    /** Returns a builder initialized from this configuration. */
    public Builder toBuilder() {
        return new Builder(this);
    }

    /** Parses explicit {@code --name=value} options and requires a backend selection. */
    public static ApplicationConfiguration fromArguments(String[] arguments)
            throws ApplicationConfigurationException {
        if (arguments == null) {
            throw new NullPointerException("arguments");
        }
        Builder builder = builder();
        boolean smokeTest = false;
        for (String argument : arguments) {
            if ("--smoke-test".equals(argument)) {
                smokeTest = true;
                continue;
            }
            if (argument == null || !argument.startsWith("--") || argument.indexOf('=') < 3) {
                throw new ApplicationConfigurationException("invalid command-line option");
            }
            int separator = argument.indexOf('=');
            String name = argument.substring(2, separator);
            String value = argument.substring(separator + 1);
            try {
                if ("listen-host".equals(name)) {
                    builder.listenHost(value);
                } else if ("listen-port".equals(name)) {
                    builder.listenPort(parseInteger(value, name));
                } else if ("connection-workers".equals(name)) {
                    builder.connectionWorkerCount(parseInteger(value, name));
                } else if ("connection-queue-capacity".equals(name)) {
                    builder.connectionQueueCapacity(parseInteger(value, name));
                } else if ("hardware-queue-capacity".equals(name)) {
                    builder.hardwareCommandQueueCapacity(parseInteger(value, name));
                } else if ("command-frame-limit".equals(name)) {
                    builder.maximumCommandFrameBytes(parseInteger(value, name));
                } else if ("json-frame-limit".equals(name)) {
                    builder.maximumJsonFrameBytes(parseInteger(value, name));
                } else if ("wav-frame-limit".equals(name)) {
                    builder.maximumWavFrameBytes(parseInteger(value, name));
                } else if ("audio-duration-limit-ms".equals(name)) {
                    builder.maximumAudioDurationMilliseconds(parseLong(value, name));
                } else if ("mouth-sync-interval-ms".equals(name)) {
                    builder.mouthSynchronizationIntervalMilliseconds(parseLong(value, name));
                } else if ("socket-timeout-ms".equals(name)) {
                    builder.socketTimeoutMilliseconds(parseInteger(value, name));
                } else if ("shutdown-timeout-ms".equals(name)) {
                    builder.shutdownTimeoutMilliseconds(parseInteger(value, name));
                } else if ("process-lock-path".equals(name)) {
                    builder.processLockPath(Paths.get(value));
                } else if ("backend".equals(name)) {
                    builder.backendSelection(BackendSelection.parse(value));
                } else {
                    throw new ApplicationConfigurationException("unknown command-line option");
                }
            } catch (IllegalArgumentException failure) {
                throw new ApplicationConfigurationException(
                        "invalid value for --" + name, failure);
            }
        }
        try {
            ApplicationConfiguration configuration = builder.build();
            if (configuration.listenPort() == 0 && !smokeTest) {
                throw new ApplicationConfigurationException(
                        "--listen-port=0 is reserved for --smoke-test");
            }
            return configuration;
        } catch (IllegalArgumentException failure) {
            throw new ApplicationConfigurationException("invalid application configuration", failure);
        }
    }

    private static long parseLong(String value, String name)
            throws ApplicationConfigurationException {
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException failure) {
            throw new ApplicationConfigurationException("--" + name + " must be an integer", failure);
        }
    }

    private static int parseInteger(String value, String name)
            throws ApplicationConfigurationException {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException failure) {
            throw new ApplicationConfigurationException("--" + name + " must be an integer", failure);
        }
    }

    /** Returns the TCP bind host. */
    public String listenHost() {
        return listenHost;
    }

    /** Returns the TCP bind port; zero requests an ephemeral test port. */
    public int listenPort() {
        return listenPort;
    }

    /** Returns the fixed connection worker count. */
    public int connectionWorkerCount() {
        return connectionWorkerCount;
    }

    /** Returns the bounded connection queue capacity. */
    public int connectionQueueCapacity() {
        return connectionQueueCapacity;
    }

    /** Returns the bounded hardware command queue capacity. */
    public int hardwareCommandQueueCapacity() {
        return hardwareCommandQueueCapacity;
    }

    /** Returns the command-name frame ceiling. */
    public int maximumCommandFrameBytes() {
        return maximumCommandFrameBytes;
    }

    /** Returns the JSON frame ceiling. */
    public int maximumJsonFrameBytes() {
        return maximumJsonFrameBytes;
    }

    /** Returns the WAV frame ceiling. */
    public int maximumWavFrameBytes() {
        return maximumWavFrameBytes;
    }

    /** Returns the decoded canonical PCM duration ceiling. */
    public long maximumAudioDurationMilliseconds() {
        return maximumAudioDurationMilliseconds;
    }

    /** Returns the periodic mouth synchronization interval. */
    public long mouthSynchronizationIntervalMilliseconds() {
        return mouthSynchronizationIntervalMilliseconds;
    }

    /** Returns the per-socket inactivity timeout and command wait ceiling. */
    public int socketTimeoutMilliseconds() {
        return socketTimeoutMilliseconds;
    }

    /** Returns the controlled shutdown wait ceiling. */
    public int shutdownTimeoutMilliseconds() {
        return shutdownTimeoutMilliseconds;
    }

    /** Returns the normalized absolute OS advisory-lock file path. */
    public Path processLockPath() {
        return processLockPath;
    }

    /** Returns the explicitly selected backend. */
    public BackendSelection backendSelection() {
        return backendSelection;
    }

    public static final class Builder {
        private String listenHost = "127.0.0.1";
        private int listenPort = 22222;
        private int connectionWorkerCount = 16;
        private int connectionQueueCapacity = 16;
        private int hardwareCommandQueueCapacity = 16;
        private int maximumCommandFrameBytes = 64;
        private int maximumJsonFrameBytes = 1_048_576;
        private int maximumWavFrameBytes = 20_971_520;
        private long maximumAudioDurationMilliseconds = 600_000L;
        private long mouthSynchronizationIntervalMilliseconds = 10L;
        private int socketTimeoutMilliseconds = 5_000;
        private int shutdownTimeoutMilliseconds = 5_000;
        private Path processLockPath = Paths.get(
                System.getProperty("java.io.tmpdir"), "robot-controller.lock");
        private BackendSelection backendSelection;

        private Builder() {
        }

        private Builder(ApplicationConfiguration source) {
            this.listenHost = source.listenHost;
            this.listenPort = source.listenPort;
            this.connectionWorkerCount = source.connectionWorkerCount;
            this.connectionQueueCapacity = source.connectionQueueCapacity;
            this.hardwareCommandQueueCapacity = source.hardwareCommandQueueCapacity;
            this.maximumCommandFrameBytes = source.maximumCommandFrameBytes;
            this.maximumJsonFrameBytes = source.maximumJsonFrameBytes;
            this.maximumWavFrameBytes = source.maximumWavFrameBytes;
            this.maximumAudioDurationMilliseconds = source.maximumAudioDurationMilliseconds;
            this.mouthSynchronizationIntervalMilliseconds =
                    source.mouthSynchronizationIntervalMilliseconds;
            this.socketTimeoutMilliseconds = source.socketTimeoutMilliseconds;
            this.shutdownTimeoutMilliseconds = source.shutdownTimeoutMilliseconds;
            this.processLockPath = source.processLockPath;
            this.backendSelection = source.backendSelection;
        }

        /** Sets the TCP bind host. */
        public Builder listenHost(String value) {
            this.listenHost = value;
            return this;
        }

        /** Sets the TCP bind port. */
        public Builder listenPort(int value) {
            this.listenPort = value;
            return this;
        }

        /** Sets the fixed connection worker count. */
        public Builder connectionWorkerCount(int value) {
            this.connectionWorkerCount = value;
            return this;
        }

        /** Sets the bounded connection queue capacity. */
        public Builder connectionQueueCapacity(int value) {
            this.connectionQueueCapacity = value;
            return this;
        }

        /** Sets the bounded hardware command queue capacity. */
        public Builder hardwareCommandQueueCapacity(int value) {
            this.hardwareCommandQueueCapacity = value;
            return this;
        }

        /** Sets the command-name frame ceiling. */
        public Builder maximumCommandFrameBytes(int value) {
            this.maximumCommandFrameBytes = value;
            return this;
        }

        /** Sets the JSON frame ceiling. */
        public Builder maximumJsonFrameBytes(int value) {
            this.maximumJsonFrameBytes = value;
            return this;
        }

        /** Sets the WAV frame ceiling. */
        public Builder maximumWavFrameBytes(int value) {
            this.maximumWavFrameBytes = value;
            return this;
        }

        /** Sets the decoded canonical PCM duration ceiling. */
        public Builder maximumAudioDurationMilliseconds(long value) {
            this.maximumAudioDurationMilliseconds = value;
            return this;
        }

        /** Sets the mouth synchronization interval. */
        public Builder mouthSynchronizationIntervalMilliseconds(long value) {
            this.mouthSynchronizationIntervalMilliseconds = value;
            return this;
        }

        /** Sets the socket inactivity timeout. */
        public Builder socketTimeoutMilliseconds(int value) {
            this.socketTimeoutMilliseconds = value;
            return this;
        }

        /** Sets the controlled shutdown timeout. */
        public Builder shutdownTimeoutMilliseconds(int value) {
            this.shutdownTimeoutMilliseconds = value;
            return this;
        }

        /** Sets the OS advisory-lock file path. */
        public Builder processLockPath(Path value) {
            this.processLockPath = value;
            return this;
        }

        /** Sets the explicit backend selection. */
        public Builder backendSelection(BackendSelection value) {
            this.backendSelection = value;
            return this;
        }

        /** Validates all bounds and builds an immutable configuration. */
        public ApplicationConfiguration build() {
            if (listenHost == null || listenHost.length() == 0) {
                throw new IllegalArgumentException("listenHost is required");
            }
            if (listenPort < 0 || listenPort > 65535) {
                throw new IllegalArgumentException("listenPort is outside 0..65535");
            }
            if (connectionWorkerCount <= 0
                    || connectionQueueCapacity <= 0
                    || hardwareCommandQueueCapacity <= 0
                    || maximumCommandFrameBytes <= 0
                    || maximumJsonFrameBytes <= 0
                    || maximumWavFrameBytes < 12
                    || maximumAudioDurationMilliseconds <= 0L
                    || mouthSynchronizationIntervalMilliseconds <= 0L
                    || socketTimeoutMilliseconds <= 0
                    || shutdownTimeoutMilliseconds < 0) {
                throw new IllegalArgumentException("capacities, limits, and timeouts are invalid");
            }
            if (processLockPath == null || processLockPath.toString().length() == 0) {
                throw new IllegalArgumentException("processLockPath is required");
            }
            if (backendSelection == null) {
                throw new IllegalArgumentException("backend selection must be explicit");
            }
            return new ApplicationConfiguration(this);
        }
    }
}
