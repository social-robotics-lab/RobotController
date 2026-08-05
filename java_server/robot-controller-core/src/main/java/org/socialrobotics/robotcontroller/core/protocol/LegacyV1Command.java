package org.socialrobotics.robotcontroller.core.protocol;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** Immutable metadata for the legacy v1 command surface. */
public enum LegacyV1Command {
    PLAY_WAV("play_wav", true, LegacyV1ResponseContract.NO_RESPONSE),
    STOP_WAV("stop_wav", false, LegacyV1ResponseContract.NO_RESPONSE),
    PLAY_POSE("play_pose", true, LegacyV1ResponseContract.NO_RESPONSE),
    STOP_POSE("stop_pose", false, LegacyV1ResponseContract.NO_RESPONSE),
    PLAY_MOTION("play_motion", true, LegacyV1ResponseContract.NO_RESPONSE),
    STOP_MOTION("stop_motion", false, LegacyV1ResponseContract.NO_RESPONSE),
    PLAY_IDLE_MOTION("play_idle_motion", true, LegacyV1ResponseContract.NO_RESPONSE),
    STOP_IDLE_MOTION("stop_idle_motion", false, LegacyV1ResponseContract.NO_RESPONSE),
    READ_AXES("read_axes", false, LegacyV1ResponseContract.RESPONSE_FRAME);

    private static final Map<String, LegacyV1Command> BY_WIRE_NAME = createLookup();

    private final String wireName;
    private final boolean payloadRequired;
    private final LegacyV1ResponseContract responseContract;

    LegacyV1Command(
            String wireName,
            boolean payloadRequired,
            LegacyV1ResponseContract responseContract) {
        this.wireName = wireName;
        this.payloadRequired = payloadRequired;
        this.responseContract = responseContract;
    }

    public String wireName() {
        return wireName;
    }

    public boolean payloadRequired() {
        return payloadRequired;
    }

    public LegacyV1ResponseContract responseContract() {
        return responseContract;
    }

    /** Returns the command for an exact ASCII-compatible wire name, or {@code null}. */
    public static LegacyV1Command fromWireName(String wireName) {
        return BY_WIRE_NAME.get(wireName);
    }

    private static Map<String, LegacyV1Command> createLookup() {
        Map<String, LegacyV1Command> result = new LinkedHashMap<String, LegacyV1Command>();
        for (LegacyV1Command command : values()) {
            result.put(command.wireName, command);
        }
        return Collections.unmodifiableMap(result);
    }
}
