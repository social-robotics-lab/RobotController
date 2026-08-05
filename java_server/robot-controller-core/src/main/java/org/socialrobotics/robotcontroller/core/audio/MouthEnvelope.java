package org.socialrobotics.robotcontroller.core.audio;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Immutable sequence of analyzed mouth-brightness windows. */
public final class MouthEnvelope {
    private final List<MouthEnvelopeWindow> windows;

    public MouthEnvelope(List<MouthEnvelopeWindow> windows) {
        if (windows == null) {
            throw new NullPointerException("windows");
        }
        this.windows = Collections.unmodifiableList(
                new ArrayList<MouthEnvelopeWindow>(windows));
    }

    public List<MouthEnvelopeWindow> windows() {
        return windows;
    }

    /** Finds brightness by played frame, returning zero outside the audio range. */
    public int brightnessAtFrame(long playedFrame) {
        if (playedFrame < 0 || windows.isEmpty()) {
            return 0;
        }
        int low = 0;
        int high = windows.size() - 1;
        while (low <= high) {
            int middle = low + (high - low) / 2;
            MouthEnvelopeWindow window = windows.get(middle);
            if (playedFrame < window.startFrameInclusive()) {
                high = middle - 1;
            } else if (playedFrame >= window.endFrameExclusive()) {
                low = middle + 1;
            } else {
                return window.brightness();
            }
        }
        return 0;
    }
}
