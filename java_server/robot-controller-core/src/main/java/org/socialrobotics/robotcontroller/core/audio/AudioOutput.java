package org.socialrobotics.robotcontroller.core.audio;

/** Opens playback directly from immutable canonical PCM data. */
public interface AudioOutput {
    /** Opens, but does not implicitly start, one session for the supplied PCM. */
    AudioPlaybackSession open(PcmAudioData audio) throws AudioOutputException;
}
