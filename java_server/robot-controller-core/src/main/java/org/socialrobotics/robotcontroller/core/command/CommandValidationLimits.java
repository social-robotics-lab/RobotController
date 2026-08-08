package org.socialrobotics.robotcontroller.core.command;

/** Immutable command, collection, and audio validation limits. */
public final class CommandValidationLimits {
    private final int maximumPoseMilliseconds;
    private final int maximumMotionPoses;
    private final double maximumIdleSpeed;
    private final int maximumIdlePauseMilliseconds;
    private final int maximumJsonBytes;
    private final int maximumWavBytes;
    private final long maximumAudioDurationMilliseconds;

    /** Creates a complete validated limit set. */
    public CommandValidationLimits(
            int maximumPoseMilliseconds,
            int maximumMotionPoses,
            double maximumIdleSpeed,
            int maximumIdlePauseMilliseconds,
            int maximumJsonBytes,
            int maximumWavBytes,
            long maximumAudioDurationMilliseconds) {
        if (maximumPoseMilliseconds < 0
                || maximumMotionPoses <= 0
                || !Double.isFinite(maximumIdleSpeed)
                || maximumIdleSpeed <= 0.0d
                || maximumIdlePauseMilliseconds < 0
                || maximumJsonBytes <= 0
                || maximumWavBytes < 12
                || maximumAudioDurationMilliseconds < 0L) {
            throw new IllegalArgumentException("all validation limits must be positive or zero");
        }
        this.maximumPoseMilliseconds = maximumPoseMilliseconds;
        this.maximumMotionPoses = maximumMotionPoses;
        this.maximumIdleSpeed = maximumIdleSpeed;
        this.maximumIdlePauseMilliseconds = maximumIdlePauseMilliseconds;
        this.maximumJsonBytes = maximumJsonBytes;
        this.maximumWavBytes = maximumWavBytes;
        this.maximumAudioDurationMilliseconds = maximumAudioDurationMilliseconds;
    }

    /** Returns the inclusive Pose duration ceiling. */
    public int maximumPoseMilliseconds() {
        return maximumPoseMilliseconds;
    }

    /** Returns the maximum number of Pose elements in one Motion. */
    public int maximumMotionPoses() {
        return maximumMotionPoses;
    }

    /** Returns the inclusive idle speed ceiling. */
    public double maximumIdleSpeed() {
        return maximumIdleSpeed;
    }

    /** Returns the inclusive idle pause ceiling. */
    public int maximumIdlePauseMilliseconds() {
        return maximumIdlePauseMilliseconds;
    }

    /** Returns the maximum JSON frame payload size. */
    public int maximumJsonBytes() {
        return maximumJsonBytes;
    }

    /** Returns the maximum WAV frame payload size. */
    public int maximumWavBytes() {
        return maximumWavBytes;
    }

    /** Returns the maximum decoded audio duration. */
    public long maximumAudioDurationMilliseconds() {
        return maximumAudioDurationMilliseconds;
    }
}
