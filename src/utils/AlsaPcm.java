package utils;

import java.io.Closeable;
import java.io.IOException;

/**
 * Owns one native ALSA PCM playback handle configured for RobotController's
 * fixed 24 kHz, mono, signed 16-bit little-endian streaming format.
 *
 * <p>The object is intended to be owned by one audio writer thread. Public
 * lifecycle methods are synchronized so that close cannot race another Java
 * operation on the same object.</p>
 */
public final class AlsaPcm implements Closeable {

    private static final String NATIVE_LIBRARY_NAME = "robotcontroller_alsa";
    private static final Object LOAD_LOCK = new Object();
    private static final Object NATIVE_OPEN_LOCK = new Object();

    private static boolean nativeLibraryLoaded;
    private static Throwable nativeLibraryLoadFailure;

    private long handle;
    private final long bufferFrames;
    private final long periodFrames;

    private AlsaPcm(long handle, long bufferFrames, long periodFrames) {
        this.handle = handle;
        this.bufferFrames = bufferFrames;
        this.periodFrames = periodFrames;
    }

    /**
     * Opens ALSA PCM {@code default} with the fixed production streaming
     * configuration.
     *
     * @return a new, open PCM owner
     * @throws IOException if the JNI library cannot be loaded or ALSA setup
     *         fails
     */
    public static AlsaPcm open() throws IOException {
        ensureNativeLibraryLoaded();

        /*
         * nativeOpen is private and all calls pass through this lock. This
         * also serializes the process-wide RTLD_GLOBAL bootstrap.
         */
        synchronized (NATIVE_OPEN_LOCK) {
            long openedHandle = 0L;
            try {
                openedHandle = nativeOpen();
                if (openedHandle == 0L) {
                    throw new IOException("Native ALSA open returned a null handle.");
                }

                long actualBufferFrames = nativeGetBufferFrames(openedHandle);
                long actualPeriodFrames = nativeGetPeriodFrames(openedHandle);
                if (actualBufferFrames <= 0L || actualPeriodFrames <= 0L) {
                    throw new IOException(
                            "ALSA returned non-positive buffer or period frames.");
                }
                return new AlsaPcm(
                        openedHandle, actualBufferFrames, actualPeriodFrames);
            } catch (IOException exception) {
                closeAfterFailedOpen(openedHandle, exception);
                throw exception;
            } catch (UnsatisfiedLinkError error) {
                closeAfterFailedOpen(openedHandle, error);
                throw new IOException(
                        "Native ALSA JNI entry point is unavailable or incompatible.",
                        error);
            } catch (RuntimeException exception) {
                closeAfterFailedOpen(openedHandle, exception);
                throw exception;
            } catch (Error error) {
                closeAfterFailedOpen(openedHandle, error);
                throw error;
            }
        }
    }

    /**
     * Writes the complete frame-aligned byte range to ALSA.
     *
     * @param data PCM bytes; the native layer does not modify this array
     * @param offset first byte to write
     * @param length positive, even number of bytes to write
     * @throws IllegalArgumentException if the range is invalid or not aligned
     * @throws IllegalStateException if this object has been closed
     * @throws IOException if ALSA cannot accept the complete range
     */
    public synchronized void write(byte[] data, int offset, int length)
            throws IOException {
        validateWriteRange(data, offset, length);
        long openHandle = requireOpenHandle();
        nativeWrite(openHandle, data, offset, length);
    }

    /**
     * Drains all accepted PCM frames for normal stream completion.
     *
     * @throws IllegalStateException if this object has been closed
     * @throws IOException if ALSA drain fails
     */
    public synchronized void drain() throws IOException {
        long openHandle = requireOpenHandle();
        nativeDrain(openHandle);
    }

    /**
     * Discards pending PCM frames for cancellation or abort.
     *
     * @throws IllegalStateException if this object has been closed
     * @throws IOException if ALSA drop fails
     */
    public synchronized void drop() throws IOException {
        long openHandle = requireOpenHandle();
        nativeDrop(openHandle);
    }

    /** Returns the actual ALSA buffer size observed when this PCM was opened. */
    public long getBufferFrames() {
        return bufferFrames;
    }

    /** Returns the actual ALSA period size observed when this PCM was opened. */
    public long getPeriodFrames() {
        return periodFrames;
    }

    /**
     * Invalidates the Java handle before attempting native close.
     *
     * @throws IOException if {@code snd_pcm_close} reports an error
     */
    @Override
    public synchronized void close() throws IOException {
        long handleToClose = handle;
        handle = 0L;
        if (handleToClose != 0L) {
            nativeClose(handleToClose);
        }
    }

    private static void ensureNativeLibraryLoaded() throws IOException {
        synchronized (LOAD_LOCK) {
            if (nativeLibraryLoaded) {
                return;
            }
            if (nativeLibraryLoadFailure != null) {
                throw loadFailure(nativeLibraryLoadFailure);
            }
            try {
                System.loadLibrary(NATIVE_LIBRARY_NAME);
                nativeLibraryLoaded = true;
            } catch (UnsatisfiedLinkError error) {
                nativeLibraryLoadFailure = error;
                throw loadFailure(error);
            } catch (SecurityException exception) {
                nativeLibraryLoadFailure = exception;
                throw loadFailure(exception);
            }
        }
    }

    private static IOException loadFailure(Throwable cause) {
        return new IOException(
                "Unable to load native library '" + NATIVE_LIBRARY_NAME
                        + "' from java.library.path.",
                cause);
    }

    private static void closeAfterFailedOpen(long openedHandle, Throwable failure) {
        if (openedHandle == 0L) {
            return;
        }
        try {
            nativeClose(openedHandle);
        } catch (Throwable closeFailure) {
            if (closeFailure != failure) {
                failure.addSuppressed(closeFailure);
            }
        }
    }

    private static void validateWriteRange(byte[] data, int offset, int length) {
        if (data == null) {
            throw new IllegalArgumentException("PCM data must not be null.");
        }
        if (offset < 0 || length <= 0 || length > data.length
                || offset > data.length - length) {
            throw new IllegalArgumentException(
                    "PCM write range is outside the byte array or empty.");
        }
        if ((length & 1) != 0) {
            throw new IllegalArgumentException(
                    "PCM write length must be aligned to a 2-byte mono frame.");
        }
    }

    private long requireOpenHandle() {
        if (handle == 0L) {
            throw new IllegalStateException("ALSA PCM is closed.");
        }
        return handle;
    }

    private static native long nativeOpen() throws IOException;

    private static native void nativeWrite(
            long handle, byte[] data, int offset, int length) throws IOException;

    private static native long nativeGetBufferFrames(long handle) throws IOException;

    private static native long nativeGetPeriodFrames(long handle) throws IOException;

    private static native void nativeDrain(long handle) throws IOException;

    private static native void nativeDrop(long handle) throws IOException;

    private static native void nativeClose(long handle) throws IOException;
}
