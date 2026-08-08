package org.socialrobotics.robotcontroller.core.command;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

import org.socialrobotics.robotcontroller.core.protocol.LegacyV1Command;

/** Strict UTF-8 decoder for the exact legacy command-name frame. */
public final class LegacyCommandDecoder {
    private LegacyCommandDecoder() {
    }

    public static LegacyV1Command decode(byte[] commandBytes)
            throws CommandValidationException {
        if (commandBytes == null) {
            throw new NullPointerException("commandBytes");
        }
        final String commandName;
        try {
            commandName = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(commandBytes))
                    .toString();
        } catch (CharacterCodingException failure) {
            throw new CommandValidationException("command name is not valid UTF-8", failure);
        }
        LegacyV1Command command = LegacyV1Command.fromWireName(commandName);
        if (command == null) {
            throw new CommandValidationException("unknown legacy command");
        }
        return command;
    }
}
