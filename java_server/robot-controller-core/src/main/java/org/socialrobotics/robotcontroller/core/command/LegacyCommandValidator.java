package org.socialrobotics.robotcontroller.core.command;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.socialrobotics.robotcontroller.core.audio.PcmAudioData;
import org.socialrobotics.robotcontroller.core.audio.WavDecodeLimits;
import org.socialrobotics.robotcontroller.core.audio.WavDecoder;
import org.socialrobotics.robotcontroller.core.audio.WavDecodingException;
import org.socialrobotics.robotcontroller.core.backend.RobotPose;
import org.socialrobotics.robotcontroller.core.protocol.LegacyV1Command;

/** Converts a complete legacy request into a strictly validated immutable command. */
public final class LegacyCommandValidator {
    private static final Set<String> POSE_FIELDS = fields("Msec", "ServoMap", "LedMap");
    private static final Set<String> IDLE_FIELDS = fields("Speed", "Pause");

    private final RobotProfile profile;
    private final CommandValidationLimits limits;

    /** Creates a validator for one explicit robot profile and limit set. */
    public LegacyCommandValidator(RobotProfile profile, CommandValidationLimits limits) {
        if (profile == null || limits == null) {
            throw new NullPointerException("profile and limits are required");
        }
        this.profile = profile;
        this.limits = limits;
    }

    /** Validates payload presence, syntax, types, ranges, profile names, and WAV format. */
    public ValidatedCommand validate(LegacyV1Command command, byte[] payload)
            throws CommandValidationException {
        if (command == null) {
            throw new NullPointerException("command");
        }
        if (command.payloadRequired() && payload == null) {
            throw new CommandValidationException("required payload frame is missing");
        }
        if (!command.payloadRequired() && payload != null) {
            throw new CommandValidationException("command does not accept a payload frame");
        }
        switch (command) {
        case PLAY_POSE:
            return ValidatedCommand.pose(command, parsePose(parseJson(payload)));
        case PLAY_MOTION:
            return parseMotion(parseJson(payload));
        case PLAY_IDLE_MOTION:
            return parseIdle(parseJson(payload));
        case PLAY_WAV:
            return parseAudio(payload);
        default:
            return ValidatedCommand.simple(command);
        }
    }

    private ValidatedCommand parseMotion(Object root) throws CommandValidationException {
        List<Object> values = requireArray(root, "motion");
        if (values.isEmpty()) {
            throw new CommandValidationException("motion must not be empty");
        }
        if (values.size() > limits.maximumMotionPoses()) {
            throw new CommandValidationException("motion element count exceeds maximum");
        }
        List<RobotPose> poses = new ArrayList<RobotPose>(values.size());
        for (Object value : values) {
            poses.add(parsePose(value));
        }
        return ValidatedCommand.motion(poses);
    }

    private RobotPose parsePose(Object root) throws CommandValidationException {
        Map<String, Object> object = requireObject(root, "pose");
        requireOnlyFields(object, POSE_FIELDS, "pose");
        int milliseconds = requireInteger(object.get("Msec"), "Msec");
        if (!object.containsKey("Msec")
                || milliseconds < 0
                || milliseconds > limits.maximumPoseMilliseconds()) {
            throw new CommandValidationException("Msec is missing or outside its range");
        }
        boolean servoPresent = object.containsKey("ServoMap");
        boolean ledPresent = object.containsKey("LedMap");
        if (!servoPresent && !ledPresent) {
            throw new CommandValidationException("ServoMap or LedMap is required");
        }
        Map<String, Integer> axes = servoPresent
                ? parseValueMap(object.get("ServoMap"), true)
                : Collections.<String, Integer>emptyMap();
        Map<String, Integer> leds = ledPresent
                ? parseValueMap(object.get("LedMap"), false)
                : Collections.<String, Integer>emptyMap();
        return new RobotPose(axes, leds, milliseconds);
    }

    private Map<String, Integer> parseValueMap(Object value, boolean servo)
            throws CommandValidationException {
        Map<String, Object> object = requireObject(value, servo ? "ServoMap" : "LedMap");
        Map<String, Integer> result = new LinkedHashMap<String, Integer>();
        for (Map.Entry<String, Object> entry : object.entrySet()) {
            int integer = requireInteger(entry.getValue(), entry.getKey());
            RobotProfile.ValueRange range = servo
                    ? profile.axisRange(entry.getKey())
                    : profile.ledRange(entry.getKey());
            if (range == null || !range.contains(integer)) {
                throw new CommandValidationException(
                        (servo ? "unknown or out-of-range servo: "
                                : "unknown or out-of-range LED: ") + entry.getKey());
            }
            result.put(entry.getKey(), Integer.valueOf(integer));
        }
        return result;
    }

    private ValidatedCommand parseIdle(Object root) throws CommandValidationException {
        Map<String, Object> object = requireObject(root, "idle motion");
        requireOnlyFields(object, IDLE_FIELDS, "idle motion");
        double speed = object.containsKey("Speed")
                ? requireFiniteNumber(object.get("Speed"), "Speed")
                : 1.0d;
        int pause = object.containsKey("Pause")
                ? requireInteger(object.get("Pause"), "Pause")
                : 1000;
        if (speed <= 0.0d || speed > limits.maximumIdleSpeed()) {
            throw new CommandValidationException("Speed is outside its range");
        }
        if (pause < 0 || pause > limits.maximumIdlePauseMilliseconds()) {
            throw new CommandValidationException("Pause is outside its range");
        }
        return ValidatedCommand.idle(speed, pause, profile.idlePoses(speed));
    }

    private ValidatedCommand parseAudio(byte[] payload) throws CommandValidationException {
        if (payload.length == 0 || payload.length > limits.maximumWavBytes()) {
            throw new CommandValidationException("WAV payload is empty or too large");
        }
        try {
            PcmAudioData audio = WavDecoder.decode(
                    payload,
                    new WavDecodeLimits(
                            limits.maximumWavBytes(),
                            limits.maximumAudioDurationMilliseconds()));
            return ValidatedCommand.audio(audio);
        } catch (WavDecodingException failure) {
            throw new CommandValidationException("invalid WAV payload", failure);
        }
    }

    private Object parseJson(byte[] payload) throws CommandValidationException {
        if (payload.length == 0 || payload.length > limits.maximumJsonBytes()) {
            throw new CommandValidationException("JSON payload is empty or too large");
        }
        final String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(payload))
                    .toString();
        } catch (CharacterCodingException failure) {
            throw new CommandValidationException("JSON payload is not valid UTF-8", failure);
        }
        return StrictJsonParser.parse(text);
    }

    private static int requireInteger(Object value, String field)
            throws CommandValidationException {
        if (!(value instanceof Long)) {
            throw new CommandValidationException(field + " must be an integer");
        }
        long integer = ((Long) value).longValue();
        if (integer < Integer.MIN_VALUE || integer > Integer.MAX_VALUE) {
            throw new CommandValidationException(field + " is outside the integer range");
        }
        return (int) integer;
    }

    private static double requireFiniteNumber(Object value, String field)
            throws CommandValidationException {
        if (!(value instanceof Number)) {
            throw new CommandValidationException(field + " must be numeric");
        }
        double number = ((Number) value).doubleValue();
        if (!Double.isFinite(number)) {
            throw new CommandValidationException(field + " must be finite");
        }
        return number;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> requireObject(Object value, String field)
            throws CommandValidationException {
        if (!(value instanceof Map<?, ?>)) {
            throw new CommandValidationException(field + " must be a JSON object");
        }
        return (Map<String, Object>) value;
    }

    @SuppressWarnings("unchecked")
    private static List<Object> requireArray(Object value, String field)
            throws CommandValidationException {
        if (!(value instanceof List<?>)) {
            throw new CommandValidationException(field + " must be a JSON array");
        }
        return (List<Object>) value;
    }

    private static void requireOnlyFields(
            Map<String, Object> object,
            Set<String> allowed,
            String name) throws CommandValidationException {
        for (String field : object.keySet()) {
            if (!allowed.contains(field)) {
                throw new CommandValidationException("unknown " + name + " field");
            }
        }
    }

    private static Set<String> fields(String... values) {
        java.util.LinkedHashSet<String> result = new java.util.LinkedHashSet<String>();
        Collections.addAll(result, values);
        return Collections.unmodifiableSet(result);
    }
}
