package org.socialrobotics.robotcontroller.core.audio;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.util.List;

import org.junit.Test;

public final class MouthEnvelopeAnalyzerTest {
    private static final int SAMPLE_RATE_HZ = 1000;
    private static final int WINDOW_MILLISECONDS = 20;
    private static final int FRAMES_PER_WINDOW = 20;

    @Test
    public void silenceProducesOnlyZero() {
        assertArrayEquals(new int[] {0, 0}, brightness(analyzeMono(0, 0)));
    }

    @Test
    public void noiseGateSuppressesLowConstantAmplitude() {
        MouthEnvelopeAnalyzer analyzer = new MouthEnvelopeAnalyzer(
                new MouthEnvelopeConfig(20, 0.10, 1.0, 1.0, 0, 0, 16));
        MouthEnvelope envelope = analyzer.analyze(monoWindows(1000, 1000));
        assertArrayEquals(new int[] {0, 0}, brightness(envelope));
    }

    @Test
    public void highConstantAmplitudeProducesHighBrightness() {
        assertArrayEquals(new int[] {15, 15}, brightness(analyzeMono(30000, 30000)));
    }

    @Test
    public void impulseIsAveragedWithinItsWindow() {
        int[] samples = new int[FRAMES_PER_WINDOW];
        samples[0] = 32767;
        assertArrayEquals(new int[] {1}, brightness(defaultAnalyzer().analyze(mono(samples))));
    }

    @Test
    public void clippingBoundaryIsClampedToMaximum() {
        assertArrayEquals(new int[] {16}, brightness(analyzeMono(-32768)));
    }

    @Test
    public void stereoLeftOnlyAndRightOnlyAreEquivalent() {
        PcmAudioData left = stereoWindow(8192, 0);
        PcmAudioData right = stereoWindow(0, 8192);
        assertArrayEquals(
                brightness(defaultAnalyzer().analyze(left)),
                brightness(defaultAnalyzer().analyze(right)));
        assertArrayEquals(new int[] {2}, brightness(defaultAnalyzer().analyze(left)));
    }

    @Test
    public void attackSmoothingRisesAcrossWindows() {
        MouthEnvelopeAnalyzer analyzer = new MouthEnvelopeAnalyzer(
                new MouthEnvelopeConfig(20, 0.0, 1.0, 1.0, 40, 0, 16));
        assertArrayEquals(
                new int[] {8, 12},
                brightness(analyzer.analyze(monoWindows(32767, 32767))));
    }

    @Test
    public void releaseSmoothingFallsAcrossWindows() {
        MouthEnvelopeAnalyzer analyzer = new MouthEnvelopeAnalyzer(
                new MouthEnvelopeConfig(20, 0.0, 1.0, 1.0, 0, 40, 16));
        assertArrayEquals(
                new int[] {16, 8, 4},
                brightness(analyzer.analyze(monoWindows(32767, 0, 0))));
    }

    @Test
    public void gainCannotExceedBrightnessClamp() {
        MouthEnvelopeAnalyzer analyzer = new MouthEnvelopeAnalyzer(
                new MouthEnvelopeConfig(20, 0.0, 100.0, 0.5, 0, 0, 7));
        assertArrayEquals(new int[] {7}, brightness(analyzer.analyze(monoWindows(1000))));
    }

    @Test
    public void deterministicGoldenVectorIncludesFrameAndTimeRanges() {
        MouthEnvelope envelope = analyzeMono(0, 8192, 16384, 32767);
        assertArrayEquals(new int[] {0, 4, 8, 16}, brightness(envelope));
        List<MouthEnvelopeWindow> windows = envelope.windows();
        assertEquals(0L, windows.get(0).startFrameInclusive());
        assertEquals(20L, windows.get(0).endFrameExclusive());
        assertEquals(0L, windows.get(0).startMicroseconds());
        assertEquals(20000L, windows.get(0).endMicroseconds());
        assertEquals(8, envelope.brightnessAtFrame(40L));
        assertEquals(0, envelope.brightnessAtFrame(80L));
    }

    @Test
    public void unsupportedCanonicalPcmShapeIsRejectedBeforeAnalysis() {
        try {
            new PcmAudioData(1000, 3, new byte[6]);
            fail("expected unsupported channel count to be rejected");
        } catch (IllegalArgumentException expected) {
            assertTrue(expected.getMessage().contains("mono and stereo"));
        }
    }

    private static MouthEnvelope analyzeMono(int... amplitudesByWindow) {
        return defaultAnalyzer().analyze(monoWindows(amplitudesByWindow));
    }

    private static MouthEnvelopeAnalyzer defaultAnalyzer() {
        return new MouthEnvelopeAnalyzer(
                new MouthEnvelopeConfig(WINDOW_MILLISECONDS, 0.0, 1.0, 1.0, 0, 0, 16));
    }

    private static PcmAudioData monoWindows(int... amplitudesByWindow) {
        int[] samples = new int[amplitudesByWindow.length * FRAMES_PER_WINDOW];
        for (int window = 0; window < amplitudesByWindow.length; window++) {
            for (int frame = 0; frame < FRAMES_PER_WINDOW; frame++) {
                samples[window * FRAMES_PER_WINDOW + frame] = amplitudesByWindow[window];
            }
        }
        return mono(samples);
    }

    private static PcmAudioData mono(int[] samples) {
        return new PcmAudioData(
                SAMPLE_RATE_HZ,
                1,
                WavDecoderTest.littleEndianSamples(samples));
    }

    private static PcmAudioData stereoWindow(int left, int right) {
        int[] interleaved = new int[FRAMES_PER_WINDOW * 2];
        for (int frame = 0; frame < FRAMES_PER_WINDOW; frame++) {
            interleaved[frame * 2] = left;
            interleaved[frame * 2 + 1] = right;
        }
        return new PcmAudioData(
                SAMPLE_RATE_HZ,
                2,
                WavDecoderTest.littleEndianSamples(interleaved));
    }

    private static int[] brightness(MouthEnvelope envelope) {
        int[] result = new int[envelope.windows().size()];
        for (int index = 0; index < result.length; index++) {
            result[index] = envelope.windows().get(index).brightness();
        }
        return result;
    }
}
