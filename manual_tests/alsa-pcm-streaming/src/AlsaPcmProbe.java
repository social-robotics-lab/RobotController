import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Human-operated JNI/libasound feasibility probe for Intel Edison.
 *
 * <p>This standalone diagnostic streams raw signed 16-bit little-endian PCM to
 * an explicitly named ALSA PCM. It has no RobotController, VSTONE, Java Sound,
 * external-process, servo, or LED dependencies and must not be added to the
 * production Maven reactor.</p>
 */
public final class AlsaPcmProbe {
    private static final Charset UTF_8 = Charset.forName("UTF-8");
    private static final String NATIVE_LIBRARY = "robotcontroller_alsa_probe";
    private static final String DEFAULT_PCM_NAME = "default";
    private static final int BYTES_PER_SAMPLE = 2;
    private static final int MAX_SAMPLE_RATE = 384_000;
    private static final int MAX_CHANNELS = 32;
    private static final int MAX_DURATION_MS = 60_000;
    private static final int MAX_INPUT_DURATION_SECONDS = 60;
    private static final int MAX_PCM_NAME_LENGTH = 256;
    private static final long FIRST_WRITE_TIMEOUT_MS = 5_000L;
    private static final long WRITER_JOIN_TIMEOUT_MS = 5_000L;

    private AlsaPcmProbe() {
    }

    /** Validates arguments and runs the selected guarded raw-PCM probe. */
    public static void main(String[] args) throws Exception {
        long programStartNanos = System.nanoTime();
        if (args == null || args.length == 0) {
            throw usage("Missing mode.");
        }
        if ("raw".equals(args[0])) {
            runRawProbe(validateRawArguments(args), programStartNanos);
            return;
        }
        if ("cancel-restart".equals(args[0])) {
            runCancelRestartProbe(validateCancelRestartArguments(args), programStartNanos);
            return;
        }
        throw usage("Unknown mode: " + args[0]);
    }

    private static ProbeArguments validateRawArguments(String[] args) {
        if (args.length != 6 && args.length != 7) {
            throw usage("raw mode requires five arguments and an optional PCM name.");
        }
        int sampleRate = parseBoundedInteger(
                "sample-rate", args[2], 1, MAX_SAMPLE_RATE);
        int channels = parseBoundedInteger(
                "channels", args[3], 1, MAX_CHANNELS);
        int chunkMs = parseBoundedInteger(
                "chunk-ms", args[4], 1, MAX_DURATION_MS);
        int latencyMs = parseBoundedInteger(
                "latency-ms", args[5], 1, MAX_DURATION_MS);
        String pcmName = args.length == 7 ? args[6] : DEFAULT_PCM_NAME;
        return createProbeArguments(
                new File(args[1]), sampleRate, channels, chunkMs, latencyMs, pcmName);
    }

    private static CancelRestartArguments validateCancelRestartArguments(String[] args) {
        if (args.length != 7 && args.length != 8) {
            throw usage(
                    "cancel-restart mode requires six arguments and an optional PCM name.");
        }
        int sampleRate = parseBoundedInteger(
                "sample-rate", args[3], 1, MAX_SAMPLE_RATE);
        int channels = parseBoundedInteger(
                "channels", args[4], 1, MAX_CHANNELS);
        int chunkMs = parseBoundedInteger(
                "chunk-ms", args[5], 1, MAX_DURATION_MS);
        int latencyMs = parseBoundedInteger(
                "latency-ms", args[6], 1, MAX_DURATION_MS);
        String pcmName = args.length == 8 ? args[7] : DEFAULT_PCM_NAME;
        File streamA = new File(args[1]);
        File streamB = new File(args[2]);
        if (streamA.getAbsoluteFile().equals(streamB.getAbsoluteFile())) {
            throw usage("stream A and stream B must be different files.");
        }
        return new CancelRestartArguments(
                createProbeArguments(
                        streamA, sampleRate, channels, chunkMs, latencyMs, pcmName),
                createProbeArguments(
                        streamB, sampleRate, channels, chunkMs, latencyMs, pcmName));
    }

    private static ProbeArguments createProbeArguments(
            File pcmFile,
            int sampleRate,
            int channels,
            int chunkMs,
            int latencyMs,
            String pcmName) {
        if (!pcmFile.isFile()) {
            throw usage("Raw PCM path is not a regular file: " + pcmFile);
        }
        if (!pcmFile.canRead()) {
            throw usage("Raw PCM file is not readable: " + pcmFile);
        }
        if (pcmName == null || pcmName.trim().isEmpty()) {
            throw usage("pcm-name must not be empty.");
        }
        if (pcmName.length() > MAX_PCM_NAME_LENGTH) {
            throw usage(
                    "pcm-name must contain at most " + MAX_PCM_NAME_LENGTH + " characters.");
        }
        for (int index = 0; index < pcmName.length(); index++) {
            if (Character.isISOControl(pcmName.charAt(index))) {
                throw usage("pcm-name must not contain control characters.");
            }
        }

        int frameSize = checkedFrameSize(channels);
        if (pcmFile.length() <= 0L) {
            throw usage("Raw PCM file must not be empty: " + pcmFile);
        }
        if (pcmFile.length() % frameSize != 0L) {
            throw usage(
                    "Raw PCM file length is not frame-aligned: "
                            + pcmFile.length() + " bytes, frame size " + frameSize);
        }
        long maximumInputBytes = (long) sampleRate
                * frameSize
                * MAX_INPUT_DURATION_SECONDS;
        if (pcmFile.length() > maximumInputBytes) {
            throw usage(
                    "Raw PCM duration exceeds the "
                            + MAX_INPUT_DURATION_SECONDS + " second manual-probe limit.");
        }

        int chunkFrames = framesForDuration(sampleRate, chunkMs, "chunk");
        int chunkBytes = checkedByteCount(chunkFrames, frameSize, "chunk");
        int latencyMicros = checkedLatencyMicros(latencyMs);
        return new ProbeArguments(
                pcmFile,
                sampleRate,
                channels,
                chunkMs,
                latencyMs,
                latencyMicros,
                pcmName,
                frameSize,
                chunkFrames,
                chunkBytes);
    }

    private static IllegalArgumentException usage(String problem) {
        return new IllegalArgumentException(
                problem
                        + System.lineSeparator()
                        + "Usage:"
                        + System.lineSeparator()
                        + "  java AlsaPcmProbe raw <file.pcm> <sample-rate> <channels>"
                        + " <chunk-ms> <latency-ms> [pcm-name]"
                        + System.lineSeparator()
                        + "  java AlsaPcmProbe cancel-restart <stream-a.pcm> <stream-b.pcm>"
                        + " <sample-rate> <channels> <chunk-ms> <latency-ms> [pcm-name]");
    }

    private static int parseBoundedInteger(
            String name, String value, int minimum, int maximum) {
        final int parsed;
        try {
            parsed = Integer.parseInt(value);
        } catch (NumberFormatException exception) {
            throw usage(name + " must be a base-10 integer: " + value);
        }
        if (parsed < minimum || parsed > maximum) {
            throw usage(
                    name + " must be in the range " + minimum + ".." + maximum + ": " + value);
        }
        return parsed;
    }

    private static int checkedFrameSize(int channels) {
        long frameSize = (long) channels * BYTES_PER_SAMPLE;
        if (frameSize <= 0L || frameSize > Integer.MAX_VALUE) {
            throw usage("Calculated PCM frame size is outside the Java integer range.");
        }
        return (int) frameSize;
    }

    private static int framesForDuration(int sampleRate, int durationMs, String label) {
        long scaled = (long) sampleRate * durationMs;
        long frames = (scaled + 500L) / 1000L;
        if (frames <= 0L || frames > Integer.MAX_VALUE) {
            throw usage(label + " duration produces an invalid frame count: " + frames);
        }
        return (int) frames;
    }

    private static int checkedByteCount(int frames, int frameSize, String label) {
        long bytes = (long) frames * frameSize;
        if (bytes <= 0L || bytes > Integer.MAX_VALUE) {
            throw usage(label + " byte count is outside the Java integer range: " + bytes);
        }
        return (int) bytes;
    }

    private static int checkedLatencyMicros(int latencyMs) {
        long latencyMicros = (long) latencyMs * 1000L;
        if (latencyMicros <= 0L || latencyMicros > Integer.MAX_VALUE) {
            throw usage("latency-ms cannot be represented as microseconds: " + latencyMs);
        }
        return (int) latencyMicros;
    }

    private static void runRawProbe(ProbeArguments arguments, long programStartNanos)
            throws Exception {
        NativePcm pcm = null;
        FileInputStream input = null;
        PlaybackStatistics statistics = new PlaybackStatistics();
        BufferedReader operatorInput = new BufferedReader(
                new InputStreamReader(System.in, UTF_8));

        try {
            System.loadLibrary(NATIVE_LIBRARY);
            pcm = NativePcm.open(arguments);
            statistics.openCompletedNanos = System.nanoTime();
            printGate(arguments, pcm);

            if (!confirmPlayback(operatorInput)) {
                Exception cleanupFailure = cleanupAfterFailure(null, pcm, input);
                pcm = null;
                input = null;
                statistics.closeCompletedNanos = System.nanoTime();
                if (cleanupFailure != null) {
                    throw cleanupFailure;
                }
                printTiming(programStartNanos, statistics);
                System.out.println("RESULT:");
                System.out.println("ABORTED_BEFORE_PLAYBACK");
                return;
            }

            input = new FileInputStream(arguments.pcmFile);
            byte[] chunk = new byte[arguments.chunkBytes];
            streamRawPcm(input, pcm, chunk, arguments.frameSize, statistics);

            pcm.drain();
            statistics.drainCompletedNanos = System.nanoTime();
            input.close();
            input = null;
            pcm.close();
            pcm = null;
            statistics.closeCompletedNanos = System.nanoTime();

            printTiming(programStartNanos, statistics);
            printStatistics(arguments, statistics);
            collectOperatorObservation(operatorInput);
        } catch (Exception primary) {
            throw cleanupAfterFailure(primary, pcm, input);
        }
    }

    private static void runCancelRestartProbe(
            CancelRestartArguments arguments, long programStartNanos) throws Exception {
        BufferedReader operatorInput = new BufferedReader(
                new InputStreamReader(System.in, UTF_8));
        CancelRestartStatistics statistics = new CancelRestartStatistics();
        boolean diagnosticsPrinted = false;

        try {
            System.loadLibrary(NATIVE_LIBRARY);
            if (!runStreamAUntilCancellation(arguments, operatorInput, statistics)) {
                return;
            }

            System.out.println();
            System.out.println("STREAM A CANCELLED");
            System.out.println("STREAM B STARTING");
            runStreamB(arguments.streamB, statistics.streamB);

            printCancelRestartTiming(programStartNanos, statistics);
            printCancelRestartStatistics(arguments, statistics);
            diagnosticsPrinted = true;
            collectCancelRestartObservation(operatorInput);
        } catch (Exception primary) {
            if (!diagnosticsPrinted) {
                printCancelRestartTiming(programStartNanos, statistics);
                printCancelRestartStatistics(arguments, statistics);
            }
            throw primary;
        }
    }

    private static boolean runStreamAUntilCancellation(
            CancelRestartArguments arguments,
            BufferedReader operatorInput,
            CancelRestartStatistics statistics) throws Exception {
        NativePcm pcm = null;
        CancelSignal cancelSignal = new CancelSignal();
        StreamAWriter writerTask = null;
        Thread writerThread = null;

        try {
            statistics.streamA.openBeginNanos = System.nanoTime();
            pcm = NativePcm.open(arguments.streamA);
            statistics.streamA.openEndNanos = System.nanoTime();
            printCancelRestartGate(arguments, pcm);
            if (!confirmCancelRestartGate(operatorInput)) {
                Exception cleanupFailure = cleanupAfterFailure(null, pcm, null);
                pcm = null;
                if (cleanupFailure != null) {
                    throw cleanupFailure;
                }
                statistics.streamA.closeNanos = System.nanoTime();
                System.out.println("RESULT:");
                System.out.println("ABORTED_BEFORE_PLAYBACK");
                return false;
            }

            writerTask = new StreamAWriter(arguments.streamA, pcm, cancelSignal, statistics.streamA);
            writerThread = new Thread(writerTask, "alsa-cancel-gate-stream-a");
            writerThread.setDaemon(true);
            writerThread.start();
            pcm = null;

            if (!writerTask.firstWriteReady.await(FIRST_WRITE_TIMEOUT_MS, TimeUnit.MILLISECONDS)) {
                throw new IOException(
                        "Stream A did not complete its first native write within "
                                + FIRST_WRITE_TIMEOUT_MS + " ms.");
            }
            if (writerTask.failure != null) {
                throw writerTask.failure;
            }
            if (statistics.streamA.firstWriteEndNanos == 0L) {
                throw new IOException("Stream A ended before its first native write completed.");
            }

            System.out.println();
            System.out.println("STREAM A PLAYING");
            boolean continueWithStreamB = awaitCancelCommand(operatorInput);
            requestCancellation(cancelSignal, statistics);
            awaitWriterTermination(writerThread);
            if (writerTask.failure != null) {
                throw writerTask.failure;
            }
            if (!statistics.streamA.cancelledBeforeEof) {
                throw new IOException(
                        "Stream A reached EOF before the cancellation boundary; use a longer stream A.");
            }

            if (!continueWithStreamB) {
                System.out.println("RESULT:");
                System.out.println("ABORTED_DURING_STREAM_A");
                return false;
            }
            return true;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw cleanupStreamAFailure(
                    new IOException("Interrupted while waiting for stream A.", exception),
                    pcm,
                    cancelSignal,
                    writerTask,
                    writerThread,
                    statistics);
        } catch (Exception primary) {
            throw cleanupStreamAFailure(
                    primary,
                    pcm,
                    cancelSignal,
                    writerTask,
                    writerThread,
                    statistics);
        }
    }

    private static Exception cleanupStreamAFailure(
            Exception primary,
            NativePcm unownedPcm,
            CancelSignal cancelSignal,
            StreamAWriter writerTask,
            Thread writerThread,
            CancelRestartStatistics statistics) {
        Exception retained = primary;
        if (unownedPcm != null) {
            retained = cleanupAfterFailure(retained, unownedPcm, null);
            statistics.streamA.closeNanos = System.nanoTime();
        }
        if (writerThread != null && writerThread.isAlive()) {
            requestCancellation(cancelSignal, statistics);
            try {
                awaitWriterTermination(writerThread);
            } catch (IOException exception) {
                retained = retainCleanupFailure(
                        retained, exception, "stream A writer termination");
            }
        }
        if (writerTask != null
                && writerThread != null
                && !writerThread.isAlive()
                && writerTask.failure != null
                && writerTask.failure != primary) {
            retained = retainCleanupFailure(
                    retained, writerTask.failure, "stream A writer cleanup");
        }
        return retained;
    }

    private static void requestCancellation(
            CancelSignal cancelSignal, CancelRestartStatistics statistics) {
        if (!cancelSignal.isRequested()) {
            statistics.cancelRequestedNanos = System.nanoTime();
            cancelSignal.request();
        }
    }

    private static void awaitWriterTermination(Thread writerThread) throws IOException {
        try {
            writerThread.join(WRITER_JOIN_TIMEOUT_MS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IOException("Interrupted while joining stream A writer.", exception);
        }
        if (writerThread.isAlive()) {
            throw new IOException(
                    "Stream A writer did not stop within " + WRITER_JOIN_TIMEOUT_MS
                            + " ms; stream B will not be opened.");
        }
    }

    private static void runStreamB(
            ProbeArguments arguments, CancelStreamStatistics statistics) throws Exception {
        NativePcm pcm = null;
        FileInputStream input = null;
        try {
            statistics.openBeginNanos = System.nanoTime();
            pcm = NativePcm.open(arguments);
            statistics.openEndNanos = System.nanoTime();
            input = new FileInputStream(arguments.pcmFile);
            byte[] chunk = new byte[arguments.chunkBytes];
            streamBToNormalEof(input, pcm, chunk, arguments.frameSize, statistics);

            pcm.drain();
            statistics.drainNanos = System.nanoTime();
            input.close();
            input = null;
            pcm.close();
            pcm = null;
            statistics.closeNanos = System.nanoTime();
            statistics.normalEof = true;
        } catch (Exception primary) {
            Exception retained = cleanupAfterFailure(primary, pcm, input);
            statistics.closeNanos = System.nanoTime();
            throw retained;
        }
    }

    private static void streamBToNormalEof(
            FileInputStream input,
            NativePcm pcm,
            byte[] chunk,
            int frameSize,
            CancelStreamStatistics statistics) throws IOException {
        boolean eof = false;
        while (!eof) {
            int filled = 0;
            while (filled < chunk.length) {
                int read = input.read(chunk, filled, chunk.length - filled);
                statistics.readCalls++;
                if (read < 0) {
                    eof = true;
                    break;
                }
                if (read == 0) {
                    throw new IOException("Stream B read returned zero bytes unexpectedly.");
                }
                filled += read;
                statistics.bytesRead += read;
            }
            if (filled == 0) {
                statistics.eofNanos = System.nanoTime();
                break;
            }
            requireFrameAligned(filled, frameSize, "Stream B read");
            if (statistics.firstWriteBeginNanos == 0L) {
                statistics.firstWriteBeginNanos = System.nanoTime();
            }
            int written = pcm.write(chunk, 0, filled);
            statistics.writeCalls++;
            requireCompleteWrite(written, filled, frameSize, "Stream B");
            statistics.lastSuccessfulWriteNanos = System.nanoTime();
            if (statistics.firstWriteEndNanos == 0L) {
                statistics.firstWriteEndNanos = statistics.lastSuccessfulWriteNanos;
                System.out.println("STREAM B PLAYING");
            }
            statistics.bytesWritten += written;
            if (eof) {
                statistics.eofNanos = System.nanoTime();
            }
        }
    }

    private static void requireFrameAligned(int length, int frameSize, String operation)
            throws IOException {
        if (length % frameSize != 0) {
            throw new IOException(operation + " ended on a partial frame: " + length + " bytes.");
        }
    }

    private static void requireCompleteWrite(
            int written, int requested, int frameSize, String streamName) throws IOException {
        if (written != requested || written % frameSize != 0) {
            throw new IOException(
                    streamName + " native write returned " + written
                            + " bytes for " + requested + " requested bytes.");
        }
    }

    private static void printCancelRestartGate(
            CancelRestartArguments arguments, NativePcm streamAPcm) throws IOException {
        ProbeArguments common = arguments.streamA;
        System.out.println("ALSA CANCEL / RESTART FEASIBILITY GATE");
        System.out.println();
        System.out.println("PCM name:");
        System.out.println(common.pcmName);
        System.out.println();
        System.out.println("Format:");
        System.out.println(common.sampleRate + " Hz");
        System.out.println(common.channels == 1 ? "mono" : common.channels + " channels");
        System.out.println("S16_LE");
        System.out.println();
        System.out.println(
                "Chunk: " + common.chunkMs + " ms / " + common.chunkBytes + " bytes");
        System.out.println("Chunk frames: " + common.chunkFrames);
        System.out.println("Requested latency: " + common.latencyMs + " ms");
        System.out.println("Actual buffer frames: " + streamAPcm.getBufferFrames());
        System.out.println("Actual period frames: " + streamAPcm.getPeriodFrames());
        System.out.println();
        System.out.println("Stream A:");
        System.out.println(arguments.streamA.pcmFile.getAbsolutePath());
        System.out.println("Stream B:");
        System.out.println(arguments.streamB.pcmFile.getAbsolutePath());
        System.out.println();
        System.out.println("This probe:");
        System.out.println("- does NOT call " + "ap" + "lay");
        System.out.println("- does NOT use Java Sound");
        System.out.println("- does NOT control mouth LED");
        System.out.println("- does NOT control servo");
        System.out.println("- does NOT call VSTONE APIs");
        System.out.println();
        System.out.println("Observe:");
        System.out.println("1. stream A starts normally");
        System.out.println("2. press ENTER while A is speaking");
        System.out.println("3. A should stop promptly");
        System.out.println("4. no remainder of A should leak afterward");
        System.out.println("5. stream B should start");
        System.out.println("6. B should play normally");
        System.out.println("7. mouth LED should follow both A and B");
        System.out.println("8. listen for problematic clicks/pops/dropouts");
    }

    private static boolean confirmCancelRestartGate(BufferedReader operatorInput)
            throws IOException {
        System.out.println();
        System.out.println("Press ENTER to begin Gate.");
        System.out.println("q aborts.");
        System.out.print("> ");
        while (true) {
            String answer = operatorInput.readLine();
            if (answer == null) {
                throw new IOException("Standard input closed before Gate confirmation.");
            }
            if (answer.isEmpty()) {
                return true;
            }
            if ("q".equalsIgnoreCase(answer.trim())) {
                return false;
            }
            System.out.println("Press ENTER to begin or enter q to abort.");
            System.out.print("> ");
        }
    }

    private static boolean awaitCancelCommand(BufferedReader operatorInput) throws IOException {
        System.out.println();
        System.out.println("Press ENTER to CANCEL A and START B.");
        System.out.println("q aborts whole Gate.");
        System.out.print("> ");
        while (true) {
            String answer = operatorInput.readLine();
            if (answer == null) {
                throw new IOException("Standard input closed while stream A was playing.");
            }
            if (answer.isEmpty()) {
                return true;
            }
            if ("q".equalsIgnoreCase(answer.trim())) {
                return false;
            }
            System.out.println("Press ENTER to cancel A or enter q to abort.");
            System.out.print("> ");
        }
    }

    private static void printCancelRestartTiming(
            long programStartNanos, CancelRestartStatistics statistics) {
        System.out.println();
        System.out.println("Cancel/restart timing (milliseconds since program start):");
        printRelativeTime("A open begin", statistics.streamA.openBeginNanos, programStartNanos);
        printRelativeTime("A open end", statistics.streamA.openEndNanos, programStartNanos);
        printRelativeTime(
                "A first write begin", statistics.streamA.firstWriteBeginNanos, programStartNanos);
        printRelativeTime(
                "A first write end", statistics.streamA.firstWriteEndNanos, programStartNanos);
        printRelativeTime("cancel requested", statistics.cancelRequestedNanos, programStartNanos);
        printRelativeTime(
                "A last successful write",
                statistics.streamA.lastSuccessfulWriteNanos,
                programStartNanos);
        printRelativeTime("A drop begin", statistics.streamA.dropBeginNanos, programStartNanos);
        printRelativeTime("A drop end", statistics.streamA.dropEndNanos, programStartNanos);
        printRelativeTime("A close complete", statistics.streamA.closeNanos, programStartNanos);
        printRelativeTime("B open begin", statistics.streamB.openBeginNanos, programStartNanos);
        printRelativeTime("B open end", statistics.streamB.openEndNanos, programStartNanos);
        printRelativeTime(
                "B first write begin", statistics.streamB.firstWriteBeginNanos, programStartNanos);
        printRelativeTime(
                "B first write end", statistics.streamB.firstWriteEndNanos, programStartNanos);
        printRelativeTime("B EOF", statistics.streamB.eofNanos, programStartNanos);
        printRelativeTime("B drain complete", statistics.streamB.drainNanos, programStartNanos);
        printRelativeTime("B close complete", statistics.streamB.closeNanos, programStartNanos);
        printElapsed(
                "cancel request -> A drop complete",
                statistics.cancelRequestedNanos,
                statistics.streamA.dropEndNanos);
        printElapsed(
                "cancel request -> B first write",
                statistics.cancelRequestedNanos,
                statistics.streamB.firstWriteBeginNanos);
        System.out.println(
                "These software timestamps do not measure acoustic stop/start latency.");
    }

    private static void printElapsed(String label, long beginNanos, long endNanos) {
        if (beginNanos == 0L || endNanos == 0L || endNanos < beginNanos) {
            System.out.println("  " + label + ": NOT_REACHED");
            return;
        }
        System.out.println("  " + label + ": " + formatMillis(endNanos - beginNanos));
    }

    private static void printCancelRestartStatistics(
            CancelRestartArguments arguments, CancelRestartStatistics statistics) {
        System.out.println();
        printCancelStreamStatistics(
                "Stream A", arguments.streamA, statistics.streamA, "Cancelled before EOF",
                statistics.streamA.cancelledBeforeEof);
        printCancelStreamStatistics(
                "Stream B", arguments.streamB, statistics.streamB, "Normal EOF",
                statistics.streamB.normalEof);
    }

    private static void printCancelStreamStatistics(
            String label,
            ProbeArguments arguments,
            CancelStreamStatistics statistics,
            String completionLabel,
            boolean completionValue) {
        System.out.println(label + " statistics:");
        System.out.println("  Read calls: " + statistics.readCalls);
        System.out.println("  Write calls: " + statistics.writeCalls);
        System.out.println("  Bytes read: " + statistics.bytesRead);
        System.out.println("  Bytes written: " + statistics.bytesWritten);
        System.out.println("  Frames written: " + statistics.bytesWritten / arguments.frameSize);
        System.out.println("  " + completionLabel + ": " + yesNo(completionValue));
    }

    private static void collectCancelRestartObservation(BufferedReader operatorInput)
            throws IOException {
        boolean aNormal = promptYesNo(
                operatorInput,
                "Operator: did stream A play normally before cancel? [yes/no]: ");
        boolean aStoppedPromptly = promptYesNo(
                operatorInput,
                "Operator: did stream A stop promptly after cancel? [yes/no]: ");
        boolean oldALeak = promptYesNo(
                operatorInput,
                "Operator: was any old stream A audio heard after stream B began? [yes/no]: ");
        boolean bNormal = promptYesNo(
                operatorInput,
                "Operator: did stream B start and play normally? [yes/no]: ");
        boolean mouthA = promptYesNo(
                operatorInput,
                "Operator: did the mouth LED follow stream A before cancel? [yes/no]: ");
        boolean mouthB = promptYesNo(
                operatorInput,
                "Operator: did the mouth LED follow stream B? [yes/no]: ");
        boolean problematicAudio = promptYesNo(
                operatorInput,
                "Operator: were problematic clicks/pops/dropouts heard? [yes/no]: ");
        System.out.print("Operator note: ");
        String note = operatorInput.readLine();
        if (note == null) {
            throw new IOException("Standard input closed before operator note was recorded.");
        }

        System.out.println();
        System.out.println("Cancel/restart operator observation:");
        System.out.println("  A normal before cancel: " + yesNo(aNormal));
        System.out.println("  A stopped promptly: " + yesNo(aStoppedPromptly));
        System.out.println("  Old A audio after B began: " + yesNo(oldALeak));
        System.out.println("  B normal: " + yesNo(bNormal));
        System.out.println("  Mouth followed A: " + yesNo(mouthA));
        System.out.println("  Mouth followed B: " + yesNo(mouthB));
        System.out.println("  Problematic clicks/pops/dropouts: " + yesNo(problematicAudio));
        System.out.println("  Note: " + (note.trim().isEmpty() ? "<none>" : note));
        System.out.println();
        System.out.println("RESULT:");
        if (!aStoppedPromptly || oldALeak) {
            System.out.println("ALSA_CANCEL_NOT_ACCEPTED");
        } else if (!aNormal || !bNormal || problematicAudio) {
            System.out.println("ALSA_CANCEL_OBSERVED_RESTART_NOT_ACCEPTED");
        } else if (!mouthA || !mouthB) {
            System.out.println("ALSA_CANCEL_RESTART_AUDIO_ONLY_OBSERVED");
        } else {
            System.out.println("ALSA_CANCEL_RESTART_WITH_NATIVE_MOUTH_SYNC_OBSERVED");
        }
        System.out.println("This result is one operator observation, not a general guarantee.");
    }

    private static void streamRawPcm(
            FileInputStream input,
            NativePcm pcm,
            byte[] chunk,
            int frameSize,
            PlaybackStatistics statistics) throws IOException {
        boolean eof = false;
        while (!eof) {
            int filled = 0;
            while (filled < chunk.length) {
                int read = input.read(chunk, filled, chunk.length - filled);
                statistics.readCalls++;
                if (read < 0) {
                    eof = true;
                    break;
                }
                if (read == 0) {
                    throw new IOException("FileInputStream.read returned zero bytes unexpectedly.");
                }
                filled += read;
                statistics.bytesRead += read;
            }

            if (filled == 0) {
                statistics.eofNanos = System.nanoTime();
                break;
            }
            if (filled % frameSize != 0) {
                throw new IOException(
                        "Raw PCM read ended on a partial frame: " + filled + " bytes.");
            }

            if (statistics.firstWriteBeginNanos == 0L) {
                statistics.firstWriteBeginNanos = System.nanoTime();
            }
            int written = pcm.write(chunk, 0, filled);
            statistics.nativeWriteCalls++;
            if (statistics.firstWriteEndNanos == 0L) {
                statistics.firstWriteEndNanos = System.nanoTime();
            }
            if (written != filled || written % frameSize != 0) {
                throw new IOException(
                        "Native write returned an unexpected byte count: "
                                + written + " for " + filled + " requested bytes.");
            }
            statistics.bytesWritten += written;

            if (eof) {
                statistics.eofNanos = System.nanoTime();
            }
        }
    }

    private static void printGate(ProbeArguments arguments, NativePcm pcm) throws IOException {
        System.out.println("ALSA PCM STREAMING FEASIBILITY GATE");
        System.out.println();
        System.out.println("PCM name:");
        System.out.println(arguments.pcmName);
        System.out.println("Raw PCM file: " + arguments.pcmFile.getAbsolutePath());
        System.out.println("Raw PCM bytes: " + arguments.pcmFile.length());
        System.out.println();
        System.out.println("Input:");
        System.out.println(arguments.sampleRate + " Hz");
        System.out.println(arguments.channels == 1 ? "mono" : arguments.channels + " channels");
        System.out.println("S16_LE");
        System.out.println();
        System.out.println(
                "Chunk: " + arguments.chunkMs + " ms / " + arguments.chunkBytes + " bytes");
        System.out.println("Chunk frames: " + arguments.chunkFrames);
        System.out.println("Requested latency: " + arguments.latencyMs + " ms");
        System.out.println("Actual buffer frames: " + pcm.getBufferFrames());
        System.out.println("Actual period frames: " + pcm.getPeriodFrames());
    }

    private static boolean confirmPlayback(BufferedReader operatorInput) throws IOException {
        System.out.println();
        System.out.println("This probe:");
        System.out.println("- does NOT call " + "ap" + "lay");
        System.out.println("- does NOT create WAV files");
        System.out.println("- does NOT use Java Sound SourceDataLine");
        System.out.println("- does NOT call VSTONE Java APIs");
        System.out.println("- does NOT control mouth LED");
        System.out.println("- does NOT control servo");
        System.out.println("- does NOT write LED state");
        System.out.println();
        System.out.println("Observe:");
        System.out.println("1. speaker audio");
        System.out.println("2. mouth LED");
        System.out.println("3. clicks/dropouts");
        System.out.println();
        System.out.println("Press ENTER to start.");
        System.out.println("q aborts.");
        System.out.print("> ");
        while (true) {
            String answer = operatorInput.readLine();
            if (answer == null) {
                throw new IOException("Standard input closed before operator confirmation.");
            }
            if (answer.isEmpty()) {
                return true;
            }
            if ("q".equalsIgnoreCase(answer.trim())) {
                return false;
            }
            System.out.println("Press ENTER to start or enter q to abort.");
            System.out.print("> ");
        }
    }

    private static Exception cleanupAfterFailure(
            Exception primary, NativePcm pcm, FileInputStream input) {
        Exception retained = primary;
        if (pcm != null) {
            try {
                pcm.drop();
            } catch (IOException exception) {
                retained = retainCleanupFailure(retained, exception, "snd_pcm_drop");
            }
        }
        if (input != null) {
            try {
                input.close();
            } catch (IOException exception) {
                retained = retainCleanupFailure(retained, exception, "raw PCM stream close");
            }
        }
        if (pcm != null) {
            try {
                pcm.close();
            } catch (IOException exception) {
                retained = retainCleanupFailure(retained, exception, "snd_pcm_close");
            }
        }
        return retained;
    }

    private static Exception retainCleanupFailure(
            Exception primary, Exception cleanupFailure, String operation) {
        System.err.println(
                "Cleanup failure during " + operation + ": " + cleanupFailure.getMessage());
        if (primary == null) {
            return cleanupFailure;
        }
        primary.addSuppressed(cleanupFailure);
        return primary;
    }

    private static void printTiming(
            long programStartNanos, PlaybackStatistics statistics) {
        System.out.println();
        System.out.println("Timing (milliseconds since program start):");
        printRelativeTime("open complete", statistics.openCompletedNanos, programStartNanos);
        printRelativeTime(
                "first native write begin", statistics.firstWriteBeginNanos, programStartNanos);
        printRelativeTime(
                "first native write end", statistics.firstWriteEndNanos, programStartNanos);
        printRelativeTime("EOF", statistics.eofNanos, programStartNanos);
        printRelativeTime("drain complete", statistics.drainCompletedNanos, programStartNanos);
        printRelativeTime("close complete", statistics.closeCompletedNanos, programStartNanos);
    }

    private static void printRelativeTime(
            String label, long eventNanos, long programStartNanos) {
        if (eventNanos == 0L) {
            System.out.println("  " + label + ": NOT_REACHED");
            return;
        }
        System.out.println(
                "  " + label + ": " + formatMillis(eventNanos - programStartNanos));
    }

    private static void printStatistics(
            ProbeArguments arguments, PlaybackStatistics statistics) {
        System.out.println();
        System.out.println("Streaming statistics:");
        System.out.println("  Read calls: " + statistics.readCalls);
        System.out.println("  Native write calls: " + statistics.nativeWriteCalls);
        System.out.println("  Bytes read: " + statistics.bytesRead);
        System.out.println("  Bytes written: " + statistics.bytesWritten);
        System.out.println(
                "  Frames written: " + (statistics.bytesWritten / arguments.frameSize));
    }

    private static void collectOperatorObservation(BufferedReader operatorInput)
            throws IOException {
        boolean audioNormal = promptYesNo(
                operatorInput, "Operator: was audio playback normal? [yes/no]: ");
        boolean mouthSync = promptYesNo(
                operatorInput,
                "Operator: did the mouth LED visibly follow the audio? [yes/no]: ");
        boolean clicksOrDropouts = promptYesNo(
                operatorInput, "Operator: were clicks/dropouts heard? [yes/no]: ");
        System.out.print("Operator note: ");
        String note = operatorInput.readLine();
        if (note == null) {
            throw new IOException("Standard input closed before operator note was recorded.");
        }

        System.out.println();
        System.out.println("Operator observation:");
        System.out.println("  Audio playback normal: " + yesNo(audioNormal));
        System.out.println("  Mouth LED followed audio: " + yesNo(mouthSync));
        System.out.println("  Clicks/dropouts heard: " + yesNo(clicksOrDropouts));
        System.out.println("  Note: " + (note.trim().isEmpty() ? "<none>" : note));
        System.out.println();
        System.out.println("RESULT:");
        if (audioNormal && mouthSync && !clicksOrDropouts) {
            System.out.println("ALSA_DEFAULT_STREAMING_WITH_NATIVE_MOUTH_SYNC_OBSERVED");
        } else if (audioNormal && !mouthSync) {
            System.out.println("ALSA_DEFAULT_STREAMING_AUDIO_ONLY_OBSERVED");
        } else {
            System.out.println("ALSA_DEFAULT_STREAMING_PLAYBACK_NOT_ACCEPTED");
        }
        System.out.println("This result is one operator observation, not a general guarantee.");
    }

    private static boolean promptYesNo(BufferedReader operatorInput, String prompt)
            throws IOException {
        while (true) {
            System.out.print(prompt);
            String answer = operatorInput.readLine();
            if (answer == null) {
                throw new IOException("Standard input closed while awaiting operator observation.");
            }
            String normalized = answer.trim().toLowerCase(Locale.ROOT);
            if ("yes".equals(normalized)) {
                return true;
            }
            if ("no".equals(normalized)) {
                return false;
            }
            System.out.println("Please enter yes or no.");
        }
    }

    private static String yesNo(boolean value) {
        return value ? "YES" : "NO";
    }

    private static String formatMillis(long nanoseconds) {
        return String.format(Locale.ROOT, "%.3f ms", nanoseconds / 1_000_000.0d);
    }

    private static native long openPcm(
            String pcmName, int sampleRate, int channels, int latencyMicros)
            throws IOException;

    private static native int writePcm(
            long handle, byte[] data, int offset, int length) throws IOException;

    private static native long getBufferFrames(long handle) throws IOException;

    private static native long getPeriodFrames(long handle) throws IOException;

    private static native void drainPcm(long handle) throws IOException;

    private static native void dropPcm(long handle) throws IOException;

    private static native void closePcm(long handle) throws IOException;

    private static final class NativePcm {
        private long handle;
        private final int frameSize;

        private NativePcm(long handle, int frameSize) {
            this.handle = handle;
            this.frameSize = frameSize;
        }

        private static NativePcm open(ProbeArguments arguments) throws IOException {
            long handle = openPcm(
                    arguments.pcmName,
                    arguments.sampleRate,
                    arguments.channels,
                    arguments.latencyMicros);
            if (handle == 0L) {
                throw new IOException("openPcm returned a null native handle.");
            }
            return new NativePcm(handle, arguments.frameSize);
        }

        private synchronized int write(byte[] data, int offset, int length) throws IOException {
            requireOpen();
            if (data == null
                    || offset < 0
                    || length < 0
                    || offset > data.length - length
                    || offset % frameSize != 0
                    || length % frameSize != 0) {
                throw new IllegalArgumentException("Native PCM write must be in-bounds and frame-aligned.");
            }
            return writePcm(handle, data, offset, length);
        }

        private synchronized long getBufferFrames() throws IOException {
            requireOpen();
            return AlsaPcmProbe.getBufferFrames(handle);
        }

        private synchronized long getPeriodFrames() throws IOException {
            requireOpen();
            return AlsaPcmProbe.getPeriodFrames(handle);
        }

        private synchronized void drain() throws IOException {
            requireOpen();
            drainPcm(handle);
        }

        private synchronized void drop() throws IOException {
            if (handle != 0L) {
                dropPcm(handle);
            }
        }

        private synchronized void close() throws IOException {
            if (handle == 0L) {
                return;
            }
            long ownedHandle = handle;
            handle = 0L;
            closePcm(ownedHandle);
        }

        private void requireOpen() throws IOException {
            if (handle == 0L) {
                throw new IOException("Native PCM handle is closed.");
            }
        }
    }

    private static final class ProbeArguments {
        private final File pcmFile;
        private final int sampleRate;
        private final int channels;
        private final int chunkMs;
        private final int latencyMs;
        private final int latencyMicros;
        private final String pcmName;
        private final int frameSize;
        private final int chunkFrames;
        private final int chunkBytes;

        private ProbeArguments(
                File pcmFile,
                int sampleRate,
                int channels,
                int chunkMs,
                int latencyMs,
                int latencyMicros,
                String pcmName,
                int frameSize,
                int chunkFrames,
                int chunkBytes) {
            this.pcmFile = pcmFile;
            this.sampleRate = sampleRate;
            this.channels = channels;
            this.chunkMs = chunkMs;
            this.latencyMs = latencyMs;
            this.latencyMicros = latencyMicros;
            this.pcmName = pcmName;
            this.frameSize = frameSize;
            this.chunkFrames = chunkFrames;
            this.chunkBytes = chunkBytes;
        }
    }

    private static final class CancelRestartArguments {
        private final ProbeArguments streamA;
        private final ProbeArguments streamB;

        private CancelRestartArguments(ProbeArguments streamA, ProbeArguments streamB) {
            this.streamA = streamA;
            this.streamB = streamB;
        }
    }

    private static final class CancelSignal {
        private volatile boolean requested;

        private void request() {
            requested = true;
        }

        private boolean isRequested() {
            return requested;
        }
    }

    private static final class CancelRestartStatistics {
        private final CancelStreamStatistics streamA = new CancelStreamStatistics();
        private final CancelStreamStatistics streamB = new CancelStreamStatistics();
        private long cancelRequestedNanos;
    }

    private static final class CancelStreamStatistics {
        private long readCalls;
        private long writeCalls;
        private long bytesRead;
        private long bytesWritten;
        private long openBeginNanos;
        private long openEndNanos;
        private long firstWriteBeginNanos;
        private long firstWriteEndNanos;
        private long lastSuccessfulWriteNanos;
        private long eofNanos;
        private long dropBeginNanos;
        private long dropEndNanos;
        private long drainNanos;
        private long closeNanos;
        private boolean cancelledBeforeEof;
        private boolean normalEof;
    }

    private static final class StreamAWriter implements Runnable {
        private final ProbeArguments arguments;
        private final NativePcm pcm;
        private final CancelSignal cancelSignal;
        private final CancelStreamStatistics statistics;
        private final CountDownLatch firstWriteReady = new CountDownLatch(1);
        private volatile Exception failure;

        private StreamAWriter(
                ProbeArguments arguments,
                NativePcm pcm,
                CancelSignal cancelSignal,
                CancelStreamStatistics statistics) {
            this.arguments = arguments;
            this.pcm = pcm;
            this.cancelSignal = cancelSignal;
            this.statistics = statistics;
        }

        @Override
        public void run() {
            FileInputStream input = null;
            Exception retained = null;
            try {
                input = new FileInputStream(arguments.pcmFile);
                byte[] chunk = new byte[arguments.chunkBytes];
                boolean eof = false;
                while (!eof && !cancelSignal.isRequested()) {
                    int filled = 0;
                    while (filled < chunk.length && !cancelSignal.isRequested()) {
                        int read = input.read(chunk, filled, chunk.length - filled);
                        statistics.readCalls++;
                        if (read < 0) {
                            eof = true;
                            break;
                        }
                        if (read == 0) {
                            throw new IOException(
                                    "Stream A read returned zero bytes unexpectedly.");
                        }
                        filled += read;
                        statistics.bytesRead += read;
                    }

                    if (cancelSignal.isRequested()) {
                        statistics.cancelledBeforeEof = hasUnwrittenInput();
                        break;
                    }
                    if (filled == 0) {
                        statistics.eofNanos = System.nanoTime();
                        break;
                    }
                    requireFrameAligned(filled, arguments.frameSize, "Stream A read");
                    if (statistics.firstWriteBeginNanos == 0L) {
                        statistics.firstWriteBeginNanos = System.nanoTime();
                    }
                    int written = pcm.write(chunk, 0, filled);
                    statistics.writeCalls++;
                    requireCompleteWrite(written, filled, arguments.frameSize, "Stream A");
                    statistics.lastSuccessfulWriteNanos = System.nanoTime();
                    if (statistics.firstWriteEndNanos == 0L) {
                        statistics.firstWriteEndNanos = statistics.lastSuccessfulWriteNanos;
                        firstWriteReady.countDown();
                    }
                    statistics.bytesWritten += written;
                    if (eof) {
                        statistics.eofNanos = System.nanoTime();
                    }
                }
                if (cancelSignal.isRequested()) {
                    statistics.cancelledBeforeEof = hasUnwrittenInput();
                }
            } catch (Exception exception) {
                retained = exception;
            } finally {
                statistics.dropBeginNanos = System.nanoTime();
                try {
                    pcm.drop();
                } catch (IOException exception) {
                    retained = retainCleanupFailure(retained, exception, "stream A snd_pcm_drop");
                } finally {
                    statistics.dropEndNanos = System.nanoTime();
                }
                if (input != null) {
                    try {
                        input.close();
                    } catch (IOException exception) {
                        retained = retainCleanupFailure(
                                retained, exception, "stream A input close");
                    }
                }
                try {
                    pcm.close();
                } catch (IOException exception) {
                    retained = retainCleanupFailure(
                            retained, exception, "stream A snd_pcm_close");
                } finally {
                    statistics.closeNanos = System.nanoTime();
                }
                failure = retained;
                firstWriteReady.countDown();
            }
        }

        private boolean hasUnwrittenInput() {
            return statistics.bytesWritten < arguments.pcmFile.length();
        }
    }

    private static final class PlaybackStatistics {
        private long readCalls;
        private long nativeWriteCalls;
        private long bytesRead;
        private long bytesWritten;
        private long openCompletedNanos;
        private long firstWriteBeginNanos;
        private long firstWriteEndNanos;
        private long eofNanos;
        private long drainCompletedNanos;
        private long closeCompletedNanos;
    }
}
