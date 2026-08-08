package org.socialrobotics.robotcontroller.app;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.socialrobotics.robotcontroller.core.command.CommandValidationException;
import org.socialrobotics.robotcontroller.core.command.LegacyCommandDecoder;
import org.socialrobotics.robotcontroller.core.command.LegacyCommandValidator;
import org.socialrobotics.robotcontroller.core.command.ValidatedCommand;
import org.socialrobotics.robotcontroller.core.protocol.FrameCodec;
import org.socialrobotics.robotcontroller.core.protocol.FrameCodecException;
import org.socialrobotics.robotcontroller.core.protocol.LegacyV1Command;

/** One-connection-one-command legacy v1 protocol adapter. */
final class LegacyConnectionHandler implements ConnectionProcessor {
    private static final Logger LOGGER =
            Logger.getLogger(LegacyConnectionHandler.class.getName());

    private final ApplicationConfiguration configuration;
    private final LegacyCommandValidator validator;
    private final ApplicationCommandDispatcher dispatcher;

    LegacyConnectionHandler(
            ApplicationConfiguration configuration,
            LegacyCommandValidator validator,
            ApplicationCommandDispatcher dispatcher) {
        this.configuration = configuration;
        this.validator = validator;
        this.dispatcher = dispatcher;
    }

    @Override
    public void process(Socket socket) throws IOException {
        socket.setSoTimeout(configuration.socketTimeoutMilliseconds());
        InputStream input = socket.getInputStream();
        OutputStream output = socket.getOutputStream();
        try {
            byte[] commandFrame = FrameCodec.readFrame(
                    input, configuration.maximumCommandFrameBytes());
            LegacyV1Command command = LegacyCommandDecoder.decode(commandFrame);
            byte[] payload = null;
            if (command.payloadRequired()) {
                int maximum = command == LegacyV1Command.PLAY_WAV
                        ? configuration.maximumWavFrameBytes()
                        : configuration.maximumJsonFrameBytes();
                payload = FrameCodec.readFrame(input, maximum);
            }
            if (input.available() > 0) {
                throw new CommandValidationException("unexpected extra payload");
            }
            ValidatedCommand validated = validator.validate(command, payload);
            byte[] response = dispatcher.dispatch(validated);
            if (response != null) {
                FrameCodec.writeFrame(
                        output, response, configuration.maximumJsonFrameBytes());
                output.flush();
            }
        } catch (SocketTimeoutException failure) {
            LOGGER.log(Level.FINE, "legacy connection timed out");
        } catch (FrameCodecException failure) {
            LOGGER.log(Level.FINE, "legacy frame rejected");
        } catch (CommandValidationException failure) {
            LOGGER.log(Level.FINE, "legacy command rejected");
        } catch (ApplicationDispatchException failure) {
            LOGGER.log(Level.WARNING, "legacy command execution failed: {0}",
                    failure.getMessage());
        }
    }
}
