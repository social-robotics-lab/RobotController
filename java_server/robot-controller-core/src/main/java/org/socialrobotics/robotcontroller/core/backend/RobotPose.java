package org.socialrobotics.robotcontroller.core.backend;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** Immutable vendor-neutral pose containing logical axis and LED values. */
public final class RobotPose {
    private final Map<String, Integer> axisDegrees;
    private final Map<String, Integer> ledValues;
    private final int transitionMilliseconds;

    public RobotPose(
            Map<String, Integer> axisDegrees,
            Map<String, Integer> ledValues,
            int transitionMilliseconds) {
        if (axisDegrees == null) {
            throw new NullPointerException("axisDegrees");
        }
        if (ledValues == null) {
            throw new NullPointerException("ledValues");
        }
        if (transitionMilliseconds < 0) {
            throw new IllegalArgumentException("transitionMilliseconds must be non-negative");
        }
        this.axisDegrees = immutableCopy(axisDegrees, "axisDegrees");
        this.ledValues = immutableCopy(ledValues, "ledValues");
        this.transitionMilliseconds = transitionMilliseconds;
    }

    public Map<String, Integer> axisDegrees() {
        return axisDegrees;
    }

    public Map<String, Integer> ledValues() {
        return ledValues;
    }

    public int transitionMilliseconds() {
        return transitionMilliseconds;
    }

    private static Map<String, Integer> immutableCopy(
            Map<String, Integer> source,
            String fieldName) {
        Map<String, Integer> copy = new LinkedHashMap<String, Integer>();
        for (Map.Entry<String, Integer> entry : source.entrySet()) {
            if (entry.getKey() == null || entry.getValue() == null) {
                throw new IllegalArgumentException(fieldName + " must not contain nulls");
            }
            copy.put(entry.getKey(), entry.getValue());
        }
        return Collections.unmodifiableMap(copy);
    }
}
