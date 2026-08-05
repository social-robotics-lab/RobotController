package org.socialrobotics.robotcontroller.core.audio;

/** Immutable tuning parameters for deterministic PCM-to-brightness analysis. */
public final class MouthEnvelopeConfig {
    private final int windowMilliseconds;
    private final double noiseGate;
    private final double gain;
    private final double compressionExponent;
    private final int attackMilliseconds;
    private final int releaseMilliseconds;
    private final int maximumBrightness;

    public MouthEnvelopeConfig(
            int windowMilliseconds,
            double noiseGate,
            double gain,
            double compressionExponent,
            int attackMilliseconds,
            int releaseMilliseconds,
            int maximumBrightness) {
        if (windowMilliseconds < 20 || windowMilliseconds > 50) {
            throw new IllegalArgumentException("windowMilliseconds must be between 20 and 50");
        }
        requireFiniteInRange(noiseGate, 0.0, 1.0, "noiseGate");
        if (noiseGate >= 1.0) {
            throw new IllegalArgumentException("noiseGate must be less than one");
        }
        if (!isFinite(gain) || gain <= 0.0) {
            throw new IllegalArgumentException("gain must be finite and positive");
        }
        if (!isFinite(compressionExponent)
                || compressionExponent <= 0.0
                || compressionExponent > 1.0) {
            throw new IllegalArgumentException(
                    "compressionExponent must be finite and in (0, 1]");
        }
        if (attackMilliseconds < 0 || releaseMilliseconds < 0) {
            throw new IllegalArgumentException("attack and release must be non-negative");
        }
        if (maximumBrightness < 0 || maximumBrightness > 255) {
            throw new IllegalArgumentException("maximumBrightness must be between 0 and 255");
        }
        this.windowMilliseconds = windowMilliseconds;
        this.noiseGate = noiseGate;
        this.gain = gain;
        this.compressionExponent = compressionExponent;
        this.attackMilliseconds = attackMilliseconds;
        this.releaseMilliseconds = releaseMilliseconds;
        this.maximumBrightness = maximumBrightness;
    }

    public int windowMilliseconds() {
        return windowMilliseconds;
    }

    public double noiseGate() {
        return noiseGate;
    }

    public double gain() {
        return gain;
    }

    public double compressionExponent() {
        return compressionExponent;
    }

    public int attackMilliseconds() {
        return attackMilliseconds;
    }

    public int releaseMilliseconds() {
        return releaseMilliseconds;
    }

    public int maximumBrightness() {
        return maximumBrightness;
    }

    private static void requireFiniteInRange(
            double value,
            double minimum,
            double maximum,
            String name) {
        if (!isFinite(value) || value < minimum || value > maximum) {
            throw new IllegalArgumentException(name + " is outside its supported range");
        }
    }

    private static boolean isFinite(double value) {
        return !Double.isNaN(value) && !Double.isInfinite(value);
    }
}
