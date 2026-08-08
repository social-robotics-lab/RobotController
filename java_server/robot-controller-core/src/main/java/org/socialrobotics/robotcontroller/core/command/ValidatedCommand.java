package org.socialrobotics.robotcontroller.core.command;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.socialrobotics.robotcontroller.core.audio.PcmAudioData;
import org.socialrobotics.robotcontroller.core.backend.RobotPose;
import org.socialrobotics.robotcontroller.core.protocol.LegacyV1Command;

/** Immutable application command produced only after complete protocol validation. */
public final class ValidatedCommand {
    private final LegacyV1Command command;
    private final RobotPose pose;
    private final List<RobotPose> motion;
    private final double idleSpeed;
    private final int idlePauseMilliseconds;
    private final PcmAudioData audio;

    private ValidatedCommand(
            LegacyV1Command command,
            RobotPose pose,
            List<RobotPose> motion,
            double idleSpeed,
            int idlePauseMilliseconds,
            PcmAudioData audio) {
        this.command = command;
        this.pose = pose;
        this.motion = motion == null
                ? Collections.<RobotPose>emptyList()
                : Collections.unmodifiableList(new ArrayList<RobotPose>(motion));
        this.idleSpeed = idleSpeed;
        this.idlePauseMilliseconds = idlePauseMilliseconds;
        this.audio = audio;
    }

    /** Creates a validated command without a payload model. */
    public static ValidatedCommand simple(LegacyV1Command command) {
        return new ValidatedCommand(command, null, null, 0.0d, 0, null);
    }

    /** Creates a validated direct Pose command. */
    public static ValidatedCommand pose(LegacyV1Command command, RobotPose pose) {
        return new ValidatedCommand(command, pose, null, 0.0d, 0, null);
    }

    /** Creates a validated Motion command. */
    public static ValidatedCommand motion(List<RobotPose> motion) {
        return new ValidatedCommand(
                LegacyV1Command.PLAY_MOTION, null, motion, 0.0d, 0, null);
    }

    /** Creates a validated Idle Motion command. */
    public static ValidatedCommand idle(
            double speed,
            int pauseMilliseconds,
            List<RobotPose> idlePoses) {
        return new ValidatedCommand(
                LegacyV1Command.PLAY_IDLE_MOTION,
                null,
                idlePoses,
                speed,
                pauseMilliseconds,
                null);
    }

    /** Creates a validated in-memory audio command. */
    public static ValidatedCommand audio(PcmAudioData audio) {
        return new ValidatedCommand(
                LegacyV1Command.PLAY_WAV, null, null, 0.0d, 0, audio);
    }

    /** Returns the legacy command identifier. */
    public LegacyV1Command command() {
        return command;
    }

    /** Returns the direct Pose payload when applicable. */
    public RobotPose pose() {
        return pose;
    }

    /** Returns the Motion Pose sequence when applicable. */
    public List<RobotPose> motion() {
        return motion;
    }

    /** Returns the verified idle Pose sequence when applicable. */
    public List<RobotPose> idlePoses() {
        return motion;
    }

    /** Returns the normalized Idle Motion speed. */
    public double idleSpeed() {
        return idleSpeed;
    }

    /** Returns the normalized Idle Motion pause. */
    public int idlePauseMilliseconds() {
        return idlePauseMilliseconds;
    }

    /** Returns canonical PCM for play_wav when applicable. */
    public PcmAudioData audio() {
        return audio;
    }
}
