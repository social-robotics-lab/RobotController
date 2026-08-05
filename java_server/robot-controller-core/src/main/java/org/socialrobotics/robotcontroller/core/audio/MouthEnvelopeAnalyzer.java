package org.socialrobotics.robotcontroller.core.audio;

import java.util.ArrayList;
import java.util.List;

/** Pure mean-absolute-amplitude analyzer with bounded compression and smoothing. */
public final class MouthEnvelopeAnalyzer {
    private final MouthEnvelopeConfig config;

    public MouthEnvelopeAnalyzer(MouthEnvelopeConfig config) {
        if (config == null) {
            throw new NullPointerException("config");
        }
        this.config = config;
    }

    /** Analyzes the same canonical PCM object that will be passed to audio output. */
    public MouthEnvelope analyze(PcmAudioData audio) {
        if (audio == null) {
            throw new NullPointerException("audio");
        }
        long windowFrames = audio.sampleRateHz() * (long) config.windowMilliseconds() / 1000L;
        if (windowFrames <= 0L) {
            throw new IllegalArgumentException("window duration is shorter than one audio frame");
        }
        List<MouthEnvelopeWindow> windows = new ArrayList<MouthEnvelopeWindow>();
        double smoothedBrightness = 0.0;
        for (long startFrame = 0L; startFrame < audio.frameCount(); startFrame += windowFrames) {
            long endFrame = Math.min(audio.frameCount(), startFrame + windowFrames);
            double level = meanAbsoluteLevel(audio, startFrame, endFrame);
            double targetBrightness = targetBrightness(level);
            int smoothingMilliseconds = targetBrightness > smoothedBrightness
                    ? config.attackMilliseconds()
                    : config.releaseMilliseconds();
            double alpha = smoothingMilliseconds == 0
                    ? 1.0
                    : Math.min(1.0, config.windowMilliseconds() / (double) smoothingMilliseconds);
            smoothedBrightness += alpha * (targetBrightness - smoothedBrightness);
            int brightness = clampBrightness((int) Math.round(smoothedBrightness));
            windows.add(new MouthEnvelopeWindow(
                    startFrame,
                    endFrame,
                    startFrame * 1000000L / audio.sampleRateHz(),
                    endFrame * 1000000L / audio.sampleRateHz(),
                    brightness));
        }
        return new MouthEnvelope(windows);
    }

    private double meanAbsoluteLevel(PcmAudioData audio, long startFrame, long endFrame) {
        if (endFrame == startFrame) {
            return 0.0;
        }
        double sum = 0.0;
        long sampleCount = 0L;
        for (long frame = startFrame; frame < endFrame; frame++) {
            for (int channel = 0; channel < audio.channels(); channel++) {
                int sample = audio.sampleAt(frame, channel);
                sum += Math.abs((double) sample) / 32768.0;
                sampleCount++;
            }
        }
        return sum / sampleCount;
    }

    private double targetBrightness(double level) {
        if (level <= config.noiseGate() || config.maximumBrightness() == 0) {
            return 0.0;
        }
        double gated = (level - config.noiseGate()) / (1.0 - config.noiseGate());
        double gained = Math.min(1.0, gated * config.gain());
        double compressed = Math.pow(gained, config.compressionExponent());
        return compressed * config.maximumBrightness();
    }

    private int clampBrightness(int brightness) {
        if (brightness < 0) {
            return 0;
        }
        return Math.min(config.maximumBrightness(), brightness);
    }
}
