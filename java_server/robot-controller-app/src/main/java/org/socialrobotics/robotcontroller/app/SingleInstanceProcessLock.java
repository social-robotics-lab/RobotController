package org.socialrobotics.robotcontroller.app;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

/** Owns one non-blocking OS advisory lock for the application process lifetime. */
public final class SingleInstanceProcessLock implements AutoCloseable {
    private final Path path;
    private final FileChannel channel;
    private FileLock lock;
    private boolean closed;

    private SingleInstanceProcessLock(Path path, FileChannel channel, FileLock lock) {
        this.path = path;
        this.channel = channel;
        this.lock = lock;
    }

    /**
     * Acquires the configured lock without retrying or deleting an existing lock file.
     * The parent directory must already exist.
     */
    public static SingleInstanceProcessLock acquire(Path configuredPath)
            throws ProcessLockException {
        if (configuredPath == null) {
            throw new NullPointerException("configuredPath");
        }
        Path path = configuredPath.toAbsolutePath().normalize();
        FileChannel channel = null;
        try {
            channel = FileChannel.open(
                    path,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE);
            FileLock lock;
            try {
                lock = channel.tryLock();
            } catch (OverlappingFileLockException failure) {
                closeChannel(channel);
                throw new ProcessLockException(
                        "RobotController process lock is already held: " + path, failure);
            }
            if (lock == null) {
                closeChannel(channel);
                throw new ProcessLockException(
                        "RobotController process lock is already held: " + path);
            }
            return new SingleInstanceProcessLock(path, channel, lock);
        } catch (ProcessLockException failure) {
            throw failure;
        } catch (IOException failure) {
            if (channel != null) {
                closeChannel(channel);
            }
            throw new ProcessLockException(
                    "RobotController process lock could not be opened: " + path, failure);
        } catch (SecurityException failure) {
            if (channel != null) {
                closeChannel(channel);
            }
            throw new ProcessLockException(
                    "RobotController process lock access was denied: " + path, failure);
        }
    }

    /** Returns the normalized absolute lock path without exposing the channel or lock. */
    public Path path() {
        return path;
    }

    /** Releases the lock and closes the channel; the lock file is intentionally retained. */
    @Override
    public synchronized void close() throws ProcessLockException {
        if (closed) {
            return;
        }
        closed = true;
        IOException failure = null;
        if (lock != null) {
            try {
                lock.release();
            } catch (IOException releaseFailure) {
                failure = releaseFailure;
            } finally {
                lock = null;
            }
        }
        try {
            channel.close();
        } catch (IOException closeFailure) {
            if (failure == null) {
                failure = closeFailure;
            } else {
                failure.addSuppressed(closeFailure);
            }
        }
        if (failure != null) {
            throw new ProcessLockException(
                    "RobotController process lock could not be released: " + path, failure);
        }
    }

    private static void closeChannel(FileChannel channel) {
        try {
            channel.close();
        } catch (IOException ignored) {
            // Acquisition has already failed; the primary failure remains authoritative.
        }
    }
}
