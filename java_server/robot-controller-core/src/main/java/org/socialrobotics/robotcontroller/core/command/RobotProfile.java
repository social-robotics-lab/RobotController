package org.socialrobotics.robotcontroller.core.command;

import java.util.Collections;
import java.util.ArrayList;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;

import org.socialrobotics.robotcontroller.core.backend.RobotPose;

/** Immutable logical name and strict external-value policy for one robot profile. */
public final class RobotProfile {
    private final Map<String, ValueRange> axes;
    private final Map<String, ValueRange> leds;
    private final List<Map<String, Integer>> idleAxisMaps;

    /** Creates a profile without an idle sequence. */
    public RobotProfile(Map<String, ValueRange> axes, Map<String, ValueRange> leds) {
        this(axes, leds, Collections.<Map<String, Integer>>emptyList());
    }

    /** Creates a profile with strict ranges and an optional verified idle sequence. */
    public RobotProfile(
            Map<String, ValueRange> axes,
            Map<String, ValueRange> leds,
            List<Map<String, Integer>> idleAxisMaps) {
        if (axes == null || leds == null) {
            throw new NullPointerException("axes and leds are required");
        }
        this.axes = immutableRanges(axes);
        this.leds = immutableRanges(leds);
        this.idleAxisMaps = immutableIdleMaps(idleAxisMaps);
    }

    /** Returns the documented legacy Sota names with strict rejection instead of clamping. */
    public static RobotProfile sotaCompatibilityProfile() {
        Map<String, ValueRange> axes = new LinkedHashMap<String, ValueRange>();
        axes.put("BODY_Y", new ValueRange(-61, 61));
        axes.put("L_SHOU", new ValueRange(-180, 60));
        axes.put("L_ELBO", new ValueRange(-90, 65));
        axes.put("R_SHOU", new ValueRange(-60, 180));
        axes.put("R_ELBO", new ValueRange(-65, 90));
        axes.put("HEAD_Y", new ValueRange(-85, 85));
        axes.put("HEAD_P", new ValueRange(-27, 5));
        axes.put("HEAD_R", new ValueRange(-30, 30));

        Map<String, ValueRange> leds = new LinkedHashMap<String, ValueRange>();
        String[] ledNames = {
            "PWR_BTN_R", "PWR_BTN_G", "PWR_BTN_B",
            "R_EYE_R", "R_EYE_G", "R_EYE_B",
            "L_EYE_R", "L_EYE_G", "L_EYE_B", "MOUTH"
        };
        for (String ledName : ledNames) {
            leds.put(ledName, new ValueRange(0, 255));
        }
        List<Map<String, Integer>> idle = new ArrayList<Map<String, Integer>>();
        Map<String, Integer> first = new LinkedHashMap<String, Integer>();
        first.put("R_SHOU", Integer.valueOf(80));
        first.put("R_ELBO", Integer.valueOf(15));
        first.put("L_ELBO", Integer.valueOf(-15));
        first.put("L_SHOU", Integer.valueOf(-80));
        idle.add(first);
        Map<String, Integer> second = new LinkedHashMap<String, Integer>();
        second.put("R_SHOU", Integer.valueOf(100));
        second.put("R_ELBO", Integer.valueOf(5));
        second.put("L_ELBO", Integer.valueOf(-5));
        second.put("L_SHOU", Integer.valueOf(-100));
        idle.add(second);
        return new RobotProfile(axes, leds, idle);
    }

    /** Returns the public range for an axis, or {@code null} when unknown. */
    public ValueRange axisRange(String name) {
        return axes.get(name);
    }

    /** Returns the public range for an LED, or {@code null} when unknown. */
    public ValueRange ledRange(String name) {
        return leds.get(name);
    }

    /** Expands the verified legacy idle maps into immutable vendor-neutral poses. */
    public List<RobotPose> idlePoses(double speed) {
        if (!Double.isFinite(speed) || speed <= 0.0d) {
            throw new IllegalArgumentException("speed must be finite and positive");
        }
        int transitionMilliseconds = (int) (1000.0d / speed);
        List<RobotPose> result = new ArrayList<RobotPose>(idleAxisMaps.size());
        for (Map<String, Integer> axesForPose : idleAxisMaps) {
            result.add(new RobotPose(
                    axesForPose,
                    Collections.<String, Integer>emptyMap(),
                    transitionMilliseconds));
        }
        return Collections.unmodifiableList(result);
    }

    private static Map<String, ValueRange> immutableRanges(Map<String, ValueRange> source) {
        Map<String, ValueRange> copy = new LinkedHashMap<String, ValueRange>();
        for (Map.Entry<String, ValueRange> entry : source.entrySet()) {
            if (entry.getKey() == null || entry.getValue() == null) {
                throw new IllegalArgumentException("profile ranges must not contain nulls");
            }
            copy.put(entry.getKey(), entry.getValue());
        }
        return Collections.unmodifiableMap(copy);
    }

    private static List<Map<String, Integer>> immutableIdleMaps(
            List<Map<String, Integer>> source) {
        if (source == null) {
            throw new NullPointerException("idleAxisMaps");
        }
        List<Map<String, Integer>> copy = new ArrayList<Map<String, Integer>>();
        for (Map<String, Integer> pose : source) {
            if (pose == null || pose.containsKey(null) || pose.containsValue(null)) {
                throw new IllegalArgumentException("idleAxisMaps must not contain nulls");
            }
            copy.add(Collections.unmodifiableMap(
                    new LinkedHashMap<String, Integer>(pose)));
        }
        return Collections.unmodifiableList(copy);
    }

    /** Inclusive integer range for one public protocol value. */
    public static final class ValueRange {
        private final int minimum;
        private final int maximum;

        /** Creates an inclusive integer range. */
        public ValueRange(int minimum, int maximum) {
            if (minimum > maximum) {
                throw new IllegalArgumentException("minimum exceeds maximum");
            }
            this.minimum = minimum;
            this.maximum = maximum;
        }

        /** Returns whether the value is inside this inclusive range. */
        public boolean contains(int value) {
            return value >= minimum && value <= maximum;
        }
    }
}
