import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.util.Locale;
import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.DataLine;
import javax.sound.sampled.Line;
import javax.sound.sampled.Mixer;
import javax.sound.sampled.SourceDataLine;
import javax.sound.sampled.UnsupportedAudioFileException;

/**
 * Human-operated Java Sound feasibility probe for Intel Edison.
 *
 * <p>This standalone diagnostic intentionally has no RobotController, VSTONE,
 * external-process, servo, or LED dependencies. It must not be added to the
 * production Maven reactor.</p>
 */
public final class SourceDataLineProbe {
    private static final Charset UTF_8 = Charset.forName("UTF-8");
    private static final int PCM_SAMPLE_BITS = 16;
    private static final int MAX_DURATION_MS = 60_000;

    private SourceDataLineProbe() {
    }

    /** Runs either the non-playing mixer inventory or the guarded WAV probe. */
    public static void main(String[] args) throws Exception {
        long programStartNanos = System.nanoTime();
        if (args == null || args.length == 0) {
            throw usage("Missing mode.");
        }

        if ("list".equals(args[0])) {
            if (args.length != 1) {
                throw usage("list mode takes no additional arguments.");
            }
            listMixers();
            return;
        }

        if ("wav".equals(args[0])) {
            WavArguments wavArguments = validateWavArguments(args);
            runWav(wavArguments, programStartNanos);
            return;
        }

        throw usage("Unknown mode: " + args[0]);
    }

    private static IllegalArgumentException usage(String problem) {
        return new IllegalArgumentException(
                problem
                        + System.lineSeparator()
                        + "Usage:"
                        + System.lineSeparator()
                        + "  java SourceDataLineProbe list"
                        + System.lineSeparator()
                        + "  java SourceDataLineProbe wav <file.wav> <chunk-ms>"
                        + " <requested-buffer-ms>");
    }

    private static WavArguments validateWavArguments(String[] args) {
        if (args.length != 4) {
            throw usage("wav mode requires exactly three arguments.");
        }

        File wavFile = new File(args[1]);
        if (!wavFile.isFile()) {
            throw usage("WAV path is not a regular file: " + wavFile);
        }
        if (!wavFile.canRead()) {
            throw usage("WAV file is not readable: " + wavFile);
        }

        int chunkMs = parseDurationMillis("chunk-ms", args[2]);
        int requestedBufferMs = parseDurationMillis("requested-buffer-ms", args[3]);
        return new WavArguments(wavFile, chunkMs, requestedBufferMs);
    }

    private static int parseDurationMillis(String name, String value) {
        final int parsed;
        try {
            parsed = Integer.parseInt(value);
        } catch (NumberFormatException exception) {
            throw usage(name + " must be a base-10 integer: " + value);
        }
        if (parsed <= 0 || parsed > MAX_DURATION_MS) {
            throw usage(name + " must be in the range 1.." + MAX_DURATION_MS + ": " + value);
        }
        return parsed;
    }

    private static void listMixers() {
        System.out.println("Java version: " + System.getProperty("java.version"));
        Mixer.Info[] mixerInfos = AudioSystem.getMixerInfo();
        System.out.println("Mixer count: " + mixerInfos.length);

        for (int index = 0; index < mixerInfos.length; index++) {
            Mixer.Info mixerInfo = mixerInfos[index];
            System.out.println();
            System.out.println("Mixer " + index + ':');
            printMixerInfo(mixerInfo, "  ");

            try {
                Mixer mixer = AudioSystem.getMixer(mixerInfo);
                Line.Info[] sourceLineInfos = mixer.getSourceLineInfo();
                boolean sourceDataLineAdvertised = false;
                System.out.println("  Source line info count: " + sourceLineInfos.length);
                for (int lineIndex = 0; lineIndex < sourceLineInfos.length; lineIndex++) {
                    Line.Info lineInfo = sourceLineInfos[lineIndex];
                    boolean isSourceDataLine =
                            SourceDataLine.class.isAssignableFrom(lineInfo.getLineClass());
                    sourceDataLineAdvertised |= isSourceDataLine;
                    System.out.println(
                            "    [" + lineIndex + "] " + lineInfo
                                    + " | SourceDataLine=" + yesNo(isSourceDataLine));
                }
                System.out.println(
                        "  Advertises SourceDataLine: " + yesNo(sourceDataLineAdvertised));
            } catch (RuntimeException exception) {
                System.out.println(
                        "  Source line inventory failed without opening a line: "
                                + exception.getClass().getName() + ": " + exception.getMessage());
            }
        }

        System.out.println();
        System.out.println("list mode did not open or start an audio line.");
    }

    private static void runWav(WavArguments arguments, long programStartNanos)
            throws Exception {
        AudioInputStream sourceStream = null;
        AudioInputStream pcmStream = null;
        SourceDataLine line = null;

        try {
            sourceStream = openAudioInputStream(arguments.wavFile);
            AudioFormat sourceFormat = sourceStream.getFormat();
            AudioFormat targetFormat = canonicalTargetFormat(sourceFormat);

            if (!isCanonicalPcm(sourceFormat, targetFormat)
                    && !AudioSystem.isConversionSupported(targetFormat, sourceFormat)) {
                throw new IllegalArgumentException(
                        "Java Sound cannot convert source format " + sourceFormat
                                + " to required target format " + targetFormat);
            }

            int frameSize = targetFormat.getFrameSize();
            int chunkBytes = bytesForDuration(targetFormat, arguments.chunkMs, "chunk");
            int requestedBufferBytes = bytesForDuration(
                    targetFormat, arguments.requestedBufferMs, "requested buffer");
            if (chunkBytes % frameSize != 0 || requestedBufferBytes % frameSize != 0) {
                throw new IllegalStateException("Calculated byte counts are not frame-aligned.");
            }
            byte[] chunk = new byte[chunkBytes];

            pcmStream = isCanonicalPcm(sourceFormat, targetFormat)
                    ? sourceStream
                    : AudioSystem.getAudioInputStream(targetFormat, sourceStream);

            System.out.println("Java version: " + System.getProperty("java.version"));
            System.out.println("WAV file: " + arguments.wavFile.getAbsolutePath());
            System.out.println("Source format: " + sourceFormat);
            System.out.println("Target format: " + targetFormat);
            System.out.println("Chunk ms: " + arguments.chunkMs);
            System.out.println("Chunk bytes: " + chunkBytes);
            System.out.println("Requested buffer ms: " + arguments.requestedBufferMs);
            System.out.println("Requested buffer bytes: " + requestedBufferBytes);
            printCandidateMixers(targetFormat);

            DataLine.Info requestedLineInfo = new DataLine.Info(
                    SourceDataLine.class, targetFormat);
            if (!AudioSystem.isLineSupported(requestedLineInfo)) {
                throw new IllegalArgumentException(
                        "No Java Sound source line advertises the requested target format and buffer.");
            }

            line = AudioSystem.getSourceDataLine(targetFormat);
            System.out.println("Selected line class: " + line.getClass().getName());
            System.out.println("Selected line info: " + line.getLineInfo());

            line.open(targetFormat, requestedBufferBytes);
            long lineOpenCompletedNanos = System.nanoTime();
            int actualBufferBytes = line.getBufferSize();
            System.out.println("Actual line format: " + line.getFormat());
            System.out.println("Actual buffer bytes: " + actualBufferBytes);

            BufferedReader operatorInput = new BufferedReader(
                    new InputStreamReader(System.in, UTF_8));
            if (!confirmPlayback(operatorInput)) {
                Exception cleanupFailure = cleanupAfterFailure(null, line, pcmStream, sourceStream);
                if (cleanupFailure != null) {
                    throw cleanupFailure;
                }
                System.out.println("RESULT:");
                System.out.println("ABORTED_BEFORE_PLAYBACK");
                return;
            }

            PlaybackStatistics statistics = new PlaybackStatistics();
            line.start();
            statistics.lineStartCalledNanos = System.nanoTime();

            while (true) {
                int read = pcmStream.read(chunk, 0, chunk.length);
                statistics.readCalls++;
                if (read < 0) {
                    statistics.eofReachedNanos = System.nanoTime();
                    break;
                }
                if (read == 0) {
                    throw new IOException("AudioInputStream.read returned zero bytes unexpectedly.");
                }
                if (read % frameSize != 0) {
                    throw new IOException(
                            "AudioInputStream returned a non-frame-aligned byte count: " + read);
                }

                statistics.totalBytesRead += read;
                writeFullyFrameAligned(line, chunk, read, frameSize, statistics);
            }

            line.drain();
            statistics.drainCompletedNanos = System.nanoTime();
            statistics.lineFramePosition = line.getLongFramePosition();
            statistics.lineMicrosecondPosition = line.getMicrosecondPosition();

            line.stop();
            line.close();
            closeStreamsNormally(pcmStream, sourceStream);
            statistics.closeCompletedNanos = System.nanoTime();

            printTiming(
                    programStartNanos,
                    lineOpenCompletedNanos,
                    statistics);
            printStatistics(
                    sourceFormat,
                    targetFormat,
                    arguments,
                    chunkBytes,
                    requestedBufferBytes,
                    actualBufferBytes,
                    frameSize,
                    statistics);
            collectOperatorObservation(operatorInput);
        } catch (Exception primary) {
            throw cleanupAfterFailure(primary, line, pcmStream, sourceStream);
        }
    }

    private static AudioInputStream openAudioInputStream(File wavFile)
            throws IOException, UnsupportedAudioFileException {
        return AudioSystem.getAudioInputStream(wavFile);
    }

    private static AudioFormat canonicalTargetFormat(AudioFormat sourceFormat) {
        float sampleRate = sourceFormat.getSampleRate();
        int channels = sourceFormat.getChannels();
        if (Float.isNaN(sampleRate) || Float.isInfinite(sampleRate) || sampleRate <= 0.0f) {
            throw new IllegalArgumentException(
                    "Source WAV must declare a finite positive sample rate: " + sampleRate);
        }
        if (channels != 1 && channels != 2) {
            throw new IllegalArgumentException(
                    "Source WAV must have one or two channels: " + channels);
        }

        int frameSize = channels * (PCM_SAMPLE_BITS / 8);
        return new AudioFormat(
                AudioFormat.Encoding.PCM_SIGNED,
                sampleRate,
                PCM_SAMPLE_BITS,
                channels,
                frameSize,
                sampleRate,
                false);
    }

    private static boolean isCanonicalPcm(AudioFormat actual, AudioFormat required) {
        return AudioFormat.Encoding.PCM_SIGNED.equals(actual.getEncoding())
                && actual.getSampleRate() == required.getSampleRate()
                && actual.getSampleSizeInBits() == required.getSampleSizeInBits()
                && actual.getChannels() == required.getChannels()
                && actual.getFrameSize() == required.getFrameSize()
                && actual.getFrameRate() == required.getFrameRate()
                && actual.isBigEndian() == required.isBigEndian();
    }

    private static int bytesForDuration(AudioFormat format, int durationMs, String label) {
        double exactFrames = ((double) format.getSampleRate() * durationMs) / 1000.0d;
        long frames = Math.round(exactFrames);
        if (frames <= 0L) {
            throw new IllegalArgumentException(label + " duration rounds to zero frames.");
        }

        long bytes = frames * (long) format.getFrameSize();
        if (bytes <= 0L || bytes > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    label + " byte count is outside the SourceDataLine integer range: " + bytes);
        }
        return (int) bytes;
    }

    private static void printCandidateMixers(AudioFormat targetFormat) {
        DataLine.Info formatInfo = new DataLine.Info(SourceDataLine.class, targetFormat);
        Mixer.Info[] mixerInfos = AudioSystem.getMixerInfo();
        int candidates = 0;
        System.out.println("Candidate mixers for target format:");
        for (int index = 0; index < mixerInfos.length; index++) {
            Mixer.Info mixerInfo = mixerInfos[index];
            try {
                Mixer mixer = AudioSystem.getMixer(mixerInfo);
                if (mixer.isLineSupported(formatInfo)) {
                    candidates++;
                    System.out.println("  Mixer " + index + ':');
                    printMixerInfo(mixerInfo, "    ");
                }
            } catch (RuntimeException exception) {
                System.out.println(
                        "  Mixer " + index + " support query failed: "
                                + exception.getClass().getName() + ": " + exception.getMessage());
            }
        }
        if (candidates == 0) {
            System.out.println("  <none advertised>");
        }
    }

    private static void printMixerInfo(Mixer.Info mixerInfo, String indent) {
        System.out.println(indent + "Name: " + mixerInfo.getName());
        System.out.println(indent + "Vendor: " + mixerInfo.getVendor());
        System.out.println(indent + "Version: " + mixerInfo.getVersion());
        System.out.println(indent + "Description: " + mixerInfo.getDescription());
    }

    private static boolean confirmPlayback(BufferedReader operatorInput) throws IOException {
        System.out.println();
        System.out.println("About to start Java Sound SourceDataLine playback.");
        System.out.println();
        System.out.println("This probe:");
        System.out.println("- does NOT call " + "ap" + "lay");
        System.out.println("- does NOT call VSTONE APIs");
        System.out.println("- does NOT control mouth LED");
        System.out.println("- does NOT control servo");
        System.out.println("- does NOT write LED state");
        System.out.println();
        System.out.println("Observe:");
        System.out.println("1. speaker audio");
        System.out.println("2. mouth LED");
        System.out.println();
        System.out.println("Press ENTER to start.");
        System.out.println("q aborts.");
        System.out.print("> ");
        String answer = operatorInput.readLine();
        if (answer == null) {
            throw new IOException("Standard input closed before operator confirmation.");
        }
        return !"q".equalsIgnoreCase(answer.trim());
    }

    private static void writeFullyFrameAligned(
            SourceDataLine line,
            byte[] bytes,
            int length,
            int frameSize,
            PlaybackStatistics statistics) throws IOException {
        int offset = 0;
        while (offset < length) {
            int remaining = length - offset;
            if (offset % frameSize != 0 || remaining % frameSize != 0) {
                throw new IOException("Pending SourceDataLine write is not frame-aligned.");
            }

            if (statistics.firstWriteBeganNanos == 0L) {
                statistics.firstWriteBeganNanos = System.nanoTime();
            }
            int written = line.write(bytes, offset, remaining);
            statistics.writeCalls++;
            if (statistics.firstWriteReturnedNanos == 0L) {
                statistics.firstWriteReturnedNanos = System.nanoTime();
            }
            if (written <= 0) {
                throw new IOException(
                        "SourceDataLine.write returned an unexpected byte count: " + written);
            }
            if (written % frameSize != 0) {
                throw new IOException(
                        "SourceDataLine.write returned a non-frame-aligned byte count: " + written);
            }
            if (written > remaining) {
                throw new IOException(
                        "SourceDataLine.write returned more bytes than requested: " + written);
            }

            offset += written;
            statistics.totalBytesWritten += written;
        }
    }

    private static void closeStreamsNormally(
            AudioInputStream pcmStream,
            AudioInputStream sourceStream) throws IOException {
        IOException primary = null;
        if (pcmStream != null) {
            try {
                pcmStream.close();
            } catch (IOException exception) {
                primary = exception;
            }
        }
        if (sourceStream != null && sourceStream != pcmStream) {
            try {
                sourceStream.close();
            } catch (IOException exception) {
                if (primary == null) {
                    primary = exception;
                } else {
                    primary.addSuppressed(exception);
                }
            }
        }
        if (primary != null) {
            throw primary;
        }
    }

    private static Exception cleanupAfterFailure(
            Exception primary,
            SourceDataLine line,
            AudioInputStream pcmStream,
            AudioInputStream sourceStream) {
        Exception retained = primary;
        if (line != null) {
            try {
                line.stop();
            } catch (RuntimeException exception) {
                retained = retainCleanupFailure(retained, exception, "line.stop");
            }
            try {
                line.flush();
            } catch (RuntimeException exception) {
                retained = retainCleanupFailure(retained, exception, "line.flush");
            }
            try {
                line.close();
            } catch (RuntimeException exception) {
                retained = retainCleanupFailure(retained, exception, "line.close");
            }
        }
        if (pcmStream != null) {
            try {
                pcmStream.close();
            } catch (IOException exception) {
                retained = retainCleanupFailure(retained, exception, "PCM stream close");
            }
        }
        if (sourceStream != null && sourceStream != pcmStream) {
            try {
                sourceStream.close();
            } catch (IOException exception) {
                retained = retainCleanupFailure(retained, exception, "source stream close");
            }
        }
        return retained;
    }

    private static Exception retainCleanupFailure(
            Exception primary, Exception secondary, String action) {
        System.err.println(
                "Cleanup failure during " + action + ": "
                        + secondary.getClass().getName() + ": " + secondary.getMessage());
        if (primary == null) {
            return secondary;
        }
        primary.addSuppressed(secondary);
        return primary;
    }

    private static void printTiming(
            long programStartNanos,
            long lineOpenCompletedNanos,
            PlaybackStatistics statistics) {
        System.out.println();
        System.out.println("Timing (milliseconds since program start):");
        printRelativeTime("program start", programStartNanos, programStartNanos);
        printRelativeTime("line open completed", lineOpenCompletedNanos, programStartNanos);
        printRelativeTime("line start called", statistics.lineStartCalledNanos, programStartNanos);
        printRelativeTime("first write began", statistics.firstWriteBeganNanos, programStartNanos);
        printRelativeTime("first write returned", statistics.firstWriteReturnedNanos, programStartNanos);
        printRelativeTime("EOF reached", statistics.eofReachedNanos, programStartNanos);
        printRelativeTime("drain completed", statistics.drainCompletedNanos, programStartNanos);
        printRelativeTime("close completed", statistics.closeCompletedNanos, programStartNanos);
    }

    private static void printRelativeTime(String name, long eventNanos, long programStartNanos) {
        if (eventNanos == 0L) {
            System.out.println("  " + name + ": NOT_REACHED");
            return;
        }
        System.out.println(
                "  " + name + ": " + formatMillis(eventNanos - programStartNanos));
    }

    private static void printStatistics(
            AudioFormat sourceFormat,
            AudioFormat targetFormat,
            WavArguments arguments,
            int chunkBytes,
            int requestedBufferBytes,
            int actualBufferBytes,
            int frameSize,
            PlaybackStatistics statistics) {
        System.out.println();
        System.out.println("Playback statistics:");
        System.out.println("  Source format: " + sourceFormat);
        System.out.println("  Target format: " + targetFormat);
        System.out.println("  Chunk ms: " + arguments.chunkMs);
        System.out.println("  Chunk bytes: " + chunkBytes);
        System.out.println("  Requested buffer ms: " + arguments.requestedBufferMs);
        System.out.println("  Requested buffer bytes: " + requestedBufferBytes);
        System.out.println("  Actual buffer bytes: " + actualBufferBytes);
        System.out.println("  Read calls: " + statistics.readCalls);
        System.out.println("  Write calls: " + statistics.writeCalls);
        System.out.println("  Total bytes read: " + statistics.totalBytesRead);
        System.out.println("  Total bytes written: " + statistics.totalBytesWritten);
        System.out.println(
                "  Total frames written: " + (statistics.totalBytesWritten / frameSize));
        System.out.println("  Line frame position: " + statistics.lineFramePosition);
        System.out.println(
                "  Line microsecond position: " + statistics.lineMicrosecondPosition);
        System.out.println(
                "  Wall-clock playback elapsed ms: "
                        + formatMillis(
                                statistics.drainCompletedNanos
                                        - statistics.lineStartCalledNanos));
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
            System.out.println("SOURCE_DATA_LINE_WITH_NATIVE_MOUTH_SYNC_OBSERVED");
        } else if (audioNormal && !mouthSync) {
            System.out.println("SOURCE_DATA_LINE_AUDIO_ONLY_OBSERVED");
        } else {
            System.out.println("SOURCE_DATA_LINE_PLAYBACK_NOT_ACCEPTED");
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
        return String.format(Locale.ROOT, "%.3f", nanoseconds / 1_000_000.0d);
    }

    private static final class WavArguments {
        private final File wavFile;
        private final int chunkMs;
        private final int requestedBufferMs;

        private WavArguments(File wavFile, int chunkMs, int requestedBufferMs) {
            this.wavFile = wavFile;
            this.chunkMs = chunkMs;
            this.requestedBufferMs = requestedBufferMs;
        }
    }

    private static final class PlaybackStatistics {
        private long readCalls;
        private long writeCalls;
        private long totalBytesRead;
        private long totalBytesWritten;
        private long lineStartCalledNanos;
        private long firstWriteBeganNanos;
        private long firstWriteReturnedNanos;
        private long eofReachedNanos;
        private long drainCompletedNanos;
        private long closeCompletedNanos;
        private long lineFramePosition;
        private long lineMicrosecondPosition;
    }
}
