package org.socialrobotics.robotcontroller.core.protocol;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class LegacyV1CommandTest {
    @Test
    public void modelsExactLegacyCommandSurface() {
        String[] expected = new String[] {
            "play_wav", "stop_wav", "play_pose", "stop_pose",
            "play_motion", "stop_motion", "play_idle_motion",
            "stop_idle_motion", "read_axes"
        };
        assertEquals(expected.length, LegacyV1Command.values().length);
        for (String name : expected) {
            assertEquals(name, LegacyV1Command.fromWireName(name).wireName());
        }
        assertNull(LegacyV1Command.fromWireName("READ_AXES"));
    }

    @Test
    public void onlyReadAxesHasSuccessfulResponseFrame() {
        for (LegacyV1Command command : LegacyV1Command.values()) {
            if (command == LegacyV1Command.READ_AXES) {
                assertEquals(
                        LegacyV1ResponseContract.RESPONSE_FRAME,
                        command.responseContract());
            } else {
                assertEquals(
                        LegacyV1ResponseContract.NO_RESPONSE,
                        command.responseContract());
            }
        }
    }

    @Test
    public void payloadRequirementsMatchLegacyFraming() {
        assertTrue(LegacyV1Command.PLAY_WAV.payloadRequired());
        assertTrue(LegacyV1Command.PLAY_POSE.payloadRequired());
        assertTrue(LegacyV1Command.PLAY_MOTION.payloadRequired());
        assertTrue(LegacyV1Command.PLAY_IDLE_MOTION.payloadRequired());
        assertFalse(LegacyV1Command.STOP_WAV.payloadRequired());
        assertFalse(LegacyV1Command.READ_AXES.payloadRequired());
    }
}
