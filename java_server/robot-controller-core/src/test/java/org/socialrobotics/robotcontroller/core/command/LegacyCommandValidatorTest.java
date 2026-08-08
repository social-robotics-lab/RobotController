package org.socialrobotics.robotcontroller.core.command;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.fail;

import java.nio.charset.StandardCharsets;

import org.junit.Before;
import org.junit.Test;
import org.socialrobotics.robotcontroller.core.protocol.LegacyV1Command;

public final class LegacyCommandValidatorTest {
    private LegacyCommandValidator validator;

    @Before
    public void createValidator() {
        validator = new LegacyCommandValidator(
                RobotProfile.sotaCompatibilityProfile(),
                new CommandValidationLimits(60_000, 100, 10.0d, 60_000, 1_048_576,
                        20_971_520, 600_000));
    }

    @Test
    public void decodesExactUtf8CommandName() throws Exception {
        assertEquals(
                LegacyV1Command.PLAY_POSE,
                LegacyCommandDecoder.decode("play_pose".getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    public void rejectsMalformedUtf8AndUnknownCommand() throws Exception {
        expectDecodeFailure(new byte[] {(byte) 0xc3, (byte) 0x28});
        expectDecodeFailure("PLAY_POSE".getBytes(StandardCharsets.UTF_8));
    }

    @Test
    public void validatesPoseIntoImmutableModel() throws Exception {
        String json = "{\"Msec\":250,\"ServoMap\":{\"HEAD_Y\":20},"
                + "\"LedMap\":{\"MOUTH\":16}}";

        ValidatedCommand command = validator.validate(
                LegacyV1Command.PLAY_POSE,
                json.getBytes(StandardCharsets.UTF_8));

        assertEquals(250, command.pose().transitionMilliseconds());
        assertEquals(Integer.valueOf(20), command.pose().axisDegrees().get("HEAD_Y"));
        assertEquals(Integer.valueOf(16), command.pose().ledValues().get("MOUTH"));
    }

    @Test
    public void rejectsMalformedJsonMissingFieldsAndUnknownFields() throws Exception {
        expectValidationFailure(LegacyV1Command.PLAY_POSE, "{");
        expectValidationFailure(LegacyV1Command.PLAY_POSE, "{\"ServoMap\":{\"HEAD_Y\":0}}");
        expectValidationFailure(
                LegacyV1Command.PLAY_POSE,
                "{\"Msec\":1,\"ServoMap\":{\"HEAD_Y\":0},\"extra\":1}");
    }

    @Test
    public void rejectsWrongTypesDuplicateKeysAndNonStandardNumbers() throws Exception {
        expectValidationFailure(
                LegacyV1Command.PLAY_POSE,
                "{\"Msec\":true,\"ServoMap\":{\"HEAD_Y\":0}}");
        expectValidationFailure(
                LegacyV1Command.PLAY_POSE,
                "{\"Msec\":1,\"Msec\":2,\"ServoMap\":{\"HEAD_Y\":0}}");
        expectValidationFailure(
                LegacyV1Command.PLAY_IDLE_MOTION,
                "{\"Speed\":NaN,\"Pause\":0}");
    }

    @Test
    public void rejectsUnknownAndOutOfRangeRobotValuesWithoutClamping() throws Exception {
        expectValidationFailure(
                LegacyV1Command.PLAY_POSE,
                "{\"Msec\":1,\"ServoMap\":{\"UNKNOWN\":0}}");
        expectValidationFailure(
                LegacyV1Command.PLAY_POSE,
                "{\"Msec\":1,\"ServoMap\":{\"HEAD_P\":6}}");
        expectValidationFailure(
                LegacyV1Command.PLAY_POSE,
                "{\"Msec\":1,\"LedMap\":{\"MOUTH\":256}}");
    }

    @Test
    public void acceptsInclusiveNumericBoundariesWithoutClamping() throws Exception {
        ValidatedCommand minimums = validator.validate(
                LegacyV1Command.PLAY_POSE,
                ("{\"Msec\":0,\"ServoMap\":{\"BODY_Y\":-61,\"HEAD_P\":-27},"
                        + "\"LedMap\":{\"MOUTH\":0}}")
                        .getBytes(StandardCharsets.UTF_8));
        ValidatedCommand maximums = validator.validate(
                LegacyV1Command.PLAY_POSE,
                ("{\"Msec\":60000,\"ServoMap\":{\"BODY_Y\":61,\"HEAD_P\":5},"
                        + "\"LedMap\":{\"MOUTH\":255}}")
                        .getBytes(StandardCharsets.UTF_8));
        ValidatedCommand idleMaximums = validator.validate(
                LegacyV1Command.PLAY_IDLE_MOTION,
                "{\"Speed\":10,\"Pause\":60000}".getBytes(StandardCharsets.UTF_8));

        assertEquals(0, minimums.pose().transitionMilliseconds());
        assertEquals(60_000, maximums.pose().transitionMilliseconds());
        assertEquals(Integer.valueOf(255), maximums.pose().ledValues().get("MOUTH"));
        assertEquals(10.0d, idleMaximums.idleSpeed(), 0.0d);
        assertEquals(60_000, idleMaximums.idlePauseMilliseconds());
    }

    @Test
    public void validatesMotionAndRejectsEmptyOrOversizedMotion() throws Exception {
        ValidatedCommand command = validator.validate(
                LegacyV1Command.PLAY_MOTION,
                ("[{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":1}},"
                        + "{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":2}}]")
                        .getBytes(StandardCharsets.UTF_8));
        assertEquals(2, command.motion().size());

        expectValidationFailure(LegacyV1Command.PLAY_MOTION, "[]");
        StringBuilder exactMaximum = new StringBuilder("[");
        for (int index = 0; index < 100; index++) {
            if (index > 0) {
                exactMaximum.append(',');
            }
            exactMaximum.append("{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":0}}");
        }
        exactMaximum.append(']');
        assertEquals(
                100,
                validator.validate(
                        LegacyV1Command.PLAY_MOTION,
                        exactMaximum.toString().getBytes(StandardCharsets.UTF_8))
                        .motion().size());

        StringBuilder oversized = new StringBuilder(exactMaximum.substring(
                0, exactMaximum.length() - 1));
        oversized.append(",{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":0}}");
        oversized.append(']');
        expectValidationFailure(LegacyV1Command.PLAY_MOTION, oversized.toString());
    }

    @Test
    public void validatesIdleDefaultsAndBounds() throws Exception {
        ValidatedCommand defaults = validator.validate(
                LegacyV1Command.PLAY_IDLE_MOTION,
                "{}".getBytes(StandardCharsets.UTF_8));
        assertEquals(1.0d, defaults.idleSpeed(), 0.0d);
        assertEquals(1000, defaults.idlePauseMilliseconds());

        expectValidationFailure(
                LegacyV1Command.PLAY_IDLE_MOTION,
                "{\"Speed\":0,\"Pause\":0}");
        expectValidationFailure(
                LegacyV1Command.PLAY_IDLE_MOTION,
                "{\"Speed\":1,\"Pause\":60001}");
    }

    @Test
    public void enforcesPayloadPresenceAndAbsence() throws Exception {
        try {
            validator.validate(LegacyV1Command.PLAY_POSE, null);
            fail("expected missing payload rejection");
        } catch (CommandValidationException expected) {
            // Expected.
        }
        try {
            validator.validate(
                    LegacyV1Command.READ_AXES,
                    "{}".getBytes(StandardCharsets.UTF_8));
            fail("expected unexpected payload rejection");
        } catch (CommandValidationException expected) {
            // Expected.
        }
    }

    @Test
    public void validatesWavInMemory() throws Exception {
        ValidatedCommand command = validator.validate(
                LegacyV1Command.PLAY_WAV,
                monoPcmWav());

        assertNotNull(command.audio());
        assertEquals(1, command.audio().frameCount());
    }

    private void expectDecodeFailure(byte[] bytes) throws Exception {
        try {
            LegacyCommandDecoder.decode(bytes);
            fail("expected command decode failure");
        } catch (CommandValidationException expected) {
            // Expected.
        }
    }

    private void expectValidationFailure(LegacyV1Command command, String json)
            throws Exception {
        try {
            validator.validate(command, json.getBytes(StandardCharsets.UTF_8));
            fail("expected validation failure for " + json);
        } catch (CommandValidationException expected) {
            // Expected.
        }
    }

    private static byte[] monoPcmWav() {
        byte[] wav = new byte[46];
        putAscii(wav, 0, "RIFF");
        putIntLittleEndian(wav, 4, 38);
        putAscii(wav, 8, "WAVE");
        putAscii(wav, 12, "fmt ");
        putIntLittleEndian(wav, 16, 16);
        putShortLittleEndian(wav, 20, 1);
        putShortLittleEndian(wav, 22, 1);
        putIntLittleEndian(wav, 24, 8000);
        putIntLittleEndian(wav, 28, 16000);
        putShortLittleEndian(wav, 32, 2);
        putShortLittleEndian(wav, 34, 16);
        putAscii(wav, 36, "data");
        putIntLittleEndian(wav, 40, 2);
        putShortLittleEndian(wav, 44, 123);
        return wav;
    }

    private static void putAscii(byte[] destination, int offset, String value) {
        byte[] bytes = value.getBytes(StandardCharsets.US_ASCII);
        System.arraycopy(bytes, 0, destination, offset, bytes.length);
    }

    private static void putIntLittleEndian(byte[] destination, int offset, int value) {
        destination[offset] = (byte) value;
        destination[offset + 1] = (byte) (value >>> 8);
        destination[offset + 2] = (byte) (value >>> 16);
        destination[offset + 3] = (byte) (value >>> 24);
    }

    private static void putShortLittleEndian(byte[] destination, int offset, int value) {
        destination[offset] = (byte) value;
        destination[offset + 1] = (byte) (value >>> 8);
    }
}
