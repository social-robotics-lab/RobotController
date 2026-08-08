package org.socialrobotics.robotcontroller.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Collections;
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

import org.junit.Test;
import org.socialrobotics.robotcontroller.mock.MockAudioOutput;
import org.socialrobotics.robotcontroller.mock.MockRobotBackend;

/** Fixed malformed/boundary corpus proving connection-local rejection and server survival. */
public final class LegacyV1MalformedInputIntegrationTest {
    @Test
    public void malformedCorpusNeverProducesV1ErrorFramesOrStopsTheServer()
            throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        backend.seedAxes(Collections.singletonMap("HEAD_Y", Integer.valueOf(9)));
        ApplicationConfiguration configuration = ApplicationConfiguration.builder()
                .backendSelection(BackendSelection.MOCK)
                .listenHost("127.0.0.1")
                .listenPort(0)
                .connectionWorkerCount(2)
                .connectionQueueCapacity(4)
                .hardwareCommandQueueCapacity(4)
                .maximumCommandFrameBytes(16)
                .maximumJsonFrameBytes(128)
                .maximumWavFrameBytes(46)
                .socketTimeoutMilliseconds(100)
                .shutdownTimeoutMilliseconds(2_000)
                .processLockPath(Files.createTempDirectory(
                        "robot-controller-malformed-test-").resolve("controller.lock"))
                .build();
        RobotControllerApplication application = new RobotControllerApplication(
                configuration, backend, new MockAudioOutput());
        application.start();
        try {
            for (int received = 0; received < 4; received++) {
                assertRejected(application.localPort(), new byte[received]);
            }
            assertRejected(application.localPort(), bytes(0x80, 0, 0, 0));
            assertRejected(application.localPort(), bytes(0xff, 0xff, 0xff, 0xff));
            assertRejected(application.localPort(), bytes(0x7f, 0xff, 0xff, 0xff));
            assertRejected(application.localPort(), frame(new byte[0]));
            assertRejected(application.localPort(), bytes(0, 0, 0, 17));
            assertRejected(application.localPort(), concat(bytes(0, 0, 0, 9), utf8("re")));
            assertRejected(application.localPort(), frame(bytes(0xc3, 0x28)));
            assertRejected(application.localPort(), frame(utf8("unknown_command")));
            assertRejected(application.localPort(), frame(utf8("play_pose")));
            assertRejected(application.localPort(), request("play_pose", utf8("{")));
            assertRejected(application.localPort(), request("play_pose", bytes(0xc3, 0x28)));
            assertRejected(application.localPort(), request("play_pose", utf8("[]")));
            assertRejected(application.localPort(), request(
                    "play_pose", utf8("{\"Msec\":0}")));
            assertRejected(application.localPort(), request(
                    "play_pose",
                    utf8("{\"Msec\":true,\"ServoMap\":{\"HEAD_Y\":0}}")));
            assertRejected(application.localPort(), request(
                    "play_pose",
                    utf8("{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":1000}}")));
            assertRejected(application.localPort(), request("read_axes", utf8("{}")));
            assertRejected(application.localPort(), concat(
                    frame(utf8("read_axes")), frame(utf8("{}"))));
            assertRejected(application.localPort(), request(
                    "play_idle_motion", new byte[129]));
            assertRejected(application.localPort(), request(
                    "play_wav", new byte[47]));

            byte[] response = exchange(application.localPort(), frame(utf8("read_axes")));
            assertTrue(response.length > 4);
            assertEquals(response.length - 4, decodeLength(response));
            assertTrue(new String(
                    response, 4, response.length - 4, StandardCharsets.UTF_8)
                    .contains("\"HEAD_Y\":9"));
        } finally {
            application.close();
        }
    }

    @Test
    public void exactCommandAndPayloadFrameLimitsRemainUsable() throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        ApplicationConfiguration configuration = ApplicationConfiguration.builder()
                .backendSelection(BackendSelection.MOCK)
                .listenPort(0)
                .connectionWorkerCount(1)
                .connectionQueueCapacity(1)
                .hardwareCommandQueueCapacity(4)
                .maximumCommandFrameBytes(16)
                .maximumJsonFrameBytes(64)
                .maximumWavFrameBytes(46)
                .socketTimeoutMilliseconds(500)
                .shutdownTimeoutMilliseconds(2_000)
                .processLockPath(Files.createTempDirectory(
                        "robot-controller-exact-limit-test-").resolve("controller.lock"))
                .build();
        RobotControllerApplication application = new RobotControllerApplication(
                configuration, backend, new MockAudioOutput());
        application.start();
        try {
            byte[] idle = padTo(utf8("{\"Speed\":1,\"Pause\":60000}"), 64);
            assertEquals(16, utf8("play_idle_motion").length);
            assertEquals(0, exchange(
                    application.localPort(), request("play_idle_motion", idle)).length);
            assertEquals(0, exchange(
                    application.localPort(), request("play_wav", minimalPcmWav())).length);
        } finally {
            application.close();
        }
    }

    @Test
    public void rejectedPayloadBytesAreNotWrittenToTheProtocolLog() throws Exception {
        Logger logger = Logger.getLogger(LegacyConnectionHandler.class.getName());
        Level originalLevel = logger.getLevel();
        CapturingHandler capture = new CapturingHandler();
        logger.setLevel(Level.ALL);
        logger.addHandler(capture);
        MockRobotBackend backend = new MockRobotBackend();
        ApplicationConfiguration configuration = ApplicationConfiguration.builder()
                .backendSelection(BackendSelection.MOCK)
                .listenPort(0)
                .connectionWorkerCount(1)
                .connectionQueueCapacity(1)
                .hardwareCommandQueueCapacity(2)
                .socketTimeoutMilliseconds(500)
                .shutdownTimeoutMilliseconds(2_000)
                .processLockPath(Files.createTempDirectory(
                        "robot-controller-log-test-").resolve("controller.lock"))
                .build();
        RobotControllerApplication application = new RobotControllerApplication(
                configuration, backend, new MockAudioOutput());
        try {
            application.start();
            assertRejected(application.localPort(), request(
                    "play_pose", utf8("SECRET_PAYLOAD_SHOULD_NOT_APPEAR")));
        } finally {
            application.close();
            logger.removeHandler(capture);
            logger.setLevel(originalLevel);
        }

        assertTrue(capture.records.size() > 0);
        for (LogRecord record : capture.records) {
            assertTrue(!record.getMessage().contains("SECRET_PAYLOAD_SHOULD_NOT_APPEAR"));
        }
    }

    private static void assertRejected(int port, byte[] request) throws Exception {
        assertEquals(0, exchange(port, request).length);
    }

    private static byte[] exchange(int port, byte[] request) throws Exception {
        Socket socket = new Socket();
        socket.connect(new InetSocketAddress("127.0.0.1", port), 1_000);
        socket.setSoTimeout(2_000);
        try {
            OutputStream output = socket.getOutputStream();
            output.write(request);
            output.flush();
            socket.shutdownOutput();
            ByteArrayOutputStream response = new ByteArrayOutputStream();
            InputStream input = socket.getInputStream();
            byte[] buffer = new byte[256];
            int read;
            try {
                while ((read = input.read(buffer)) >= 0) {
                    response.write(buffer, 0, read);
                }
            } catch (SocketException resetOrAbort) {
                if (response.size() != 0) {
                    throw resetOrAbort;
                }
                // Windows may use RST when rejecting a connection with unread input.
            }
            return response.toByteArray();
        } finally {
            socket.close();
        }
    }

    private static byte[] request(String command, byte[] payload) {
        return concat(frame(utf8(command)), frame(payload));
    }

    private static byte[] frame(byte[] payload) {
        int length = payload.length;
        return concat(
                bytes(length >>> 24, length >>> 16, length >>> 8, length), payload);
    }

    private static byte[] concat(byte[] first, byte[] second) {
        byte[] combined = new byte[first.length + second.length];
        System.arraycopy(first, 0, combined, 0, first.length);
        System.arraycopy(second, 0, combined, first.length, second.length);
        return combined;
    }

    private static byte[] bytes(int... values) {
        byte[] result = new byte[values.length];
        for (int index = 0; index < values.length; index++) {
            result[index] = (byte) values[index];
        }
        return result;
    }

    private static byte[] utf8(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] padTo(byte[] value, int size) {
        byte[] padded = new byte[size];
        System.arraycopy(value, 0, padded, 0, value.length);
        for (int index = value.length; index < padded.length; index++) {
            padded[index] = ' ';
        }
        return padded;
    }

    private static int decodeLength(byte[] framed) {
        return ((framed[0] & 0xff) << 24)
                | ((framed[1] & 0xff) << 16)
                | ((framed[2] & 0xff) << 8)
                | (framed[3] & 0xff);
    }

    private static byte[] minimalPcmWav() {
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
        return wav;
    }

    private static void putAscii(byte[] destination, int offset, String value) {
        byte[] bytes = utf8(value);
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

    private static final class CapturingHandler extends Handler {
        private final List<LogRecord> records = new ArrayList<LogRecord>();

        @Override
        public void publish(LogRecord record) {
            records.add(record);
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }
    }
}
