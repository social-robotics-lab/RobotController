package org.socialrobotics.robotcontroller.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Collections;

import org.junit.Test;
import org.socialrobotics.robotcontroller.mock.MockAudioOutput;
import org.socialrobotics.robotcontroller.mock.MockRobotBackend;

/** Command-by-command normal-path compatibility coverage at the raw legacy v1 wire. */
public final class LegacyV1WireCompatibilityIntegrationTest {
    @Test
    public void playWavUsesPayloadAndReturnsNoAck() throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.start();
            assertNoResponse(fixture.port(), "play_wav", minimalPcmWav());
            assertEquals(1, fixture.audioOutput.sessions().size());
        } finally {
            fixture.close();
        }
    }

    @Test
    public void stopWavUsesNoPayloadAndReturnsNoAck() throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.start();
            assertNoResponse(fixture.port(), "stop_wav", null);
        } finally {
            fixture.close();
        }
    }

    @Test
    public void playPoseUsesJsonPayloadAndReturnsNoAck() throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.start();
            assertNoResponse(
                    fixture.port(),
                    "play_pose",
                    utf8("{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":4}}"));
            awaitOperation(fixture.backend, "applyPose");
            assertEquals(Integer.valueOf(4), fixture.backend.currentAxes().get("HEAD_Y"));
        } finally {
            fixture.close();
        }
    }

    @Test
    public void stopPoseUsesNoPayloadAndReturnsNoAck() throws Exception {
        assertStopCommand("stop_pose");
    }

    @Test
    public void playMotionUsesJsonPayloadAndReturnsNoAck() throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.start();
            assertNoResponse(
                    fixture.port(),
                    "play_motion",
                    utf8("[{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":5}}]"));
            awaitAxis(fixture.backend, "HEAD_Y", 5);
            assertEquals(Integer.valueOf(5), fixture.backend.currentAxes().get("HEAD_Y"));
        } finally {
            fixture.close();
        }
    }

    @Test
    public void stopMotionUsesNoPayloadAndReturnsNoAck() throws Exception {
        assertStopCommand("stop_motion");
    }

    @Test
    public void playIdleMotionUsesJsonPayloadAndReturnsNoAck() throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.start();
            assertNoResponse(
                    fixture.port(),
                    "play_idle_motion",
                    utf8("{\"Speed\":1,\"Pause\":60000}"));
            awaitAxis(fixture.backend, "R_SHOU", 80);
        } finally {
            fixture.close();
        }
    }

    @Test
    public void stopIdleMotionUsesNoPayloadAndReturnsNoAck() throws Exception {
        assertStopCommand("stop_idle_motion");
    }

    @Test
    public void readAxesUsesNoPayloadAndReturnsOneBigEndianJsonFrame() throws Exception {
        Fixture fixture = new Fixture();
        fixture.backend.seedAxes(Collections.singletonMap("HEAD_Y", Integer.valueOf(7)));
        try {
            fixture.start();
            byte[] response = sendAndReadRaw(fixture.port(), "read_axes", null);
            int length = decodeLength(response);
            assertEquals(response.length - 4, length);
            String json = new String(response, 4, length, StandardCharsets.UTF_8);
            assertTrue(json.startsWith("{"));
            assertTrue(json.endsWith("}"));
            assertTrue(json.contains("\"HEAD_Y\":7"));
            assertEquals(1, count(fixture.backend, "readAxes"));
        } finally {
            fixture.close();
        }
    }

    private static void assertStopCommand(String command) throws Exception {
        Fixture fixture = new Fixture();
        try {
            fixture.start();
            assertNoResponse(fixture.port(), command, null);
            awaitOperation(fixture.backend, "requestRobotStop");
        } finally {
            fixture.close();
        }
    }

    private static byte[] sendAndReadRaw(int port, String command, byte[] payload)
            throws Exception {
        Socket socket = connect(port);
        try {
            OutputStream output = socket.getOutputStream();
            writeFrame(output, utf8(command));
            if (payload != null) {
                writeFrame(output, payload);
            }
            output.flush();
            ByteArrayOutputStream response = new ByteArrayOutputStream();
            InputStream input = socket.getInputStream();
            byte[] buffer = new byte[256];
            int read;
            while ((read = input.read(buffer)) >= 0) {
                response.write(buffer, 0, read);
            }
            return response.toByteArray();
        } finally {
            socket.close();
        }
    }

    private static void assertNoResponse(int port, String command, byte[] payload)
            throws Exception {
        assertEquals(0, sendAndReadRaw(port, command, payload).length);
    }

    private static Socket connect(int port) throws Exception {
        Socket socket = new Socket();
        socket.connect(new InetSocketAddress("127.0.0.1", port), 1_000);
        socket.setSoTimeout(2_000);
        return socket;
    }

    private static void writeFrame(OutputStream output, byte[] payload) throws Exception {
        int length = payload.length;
        output.write((length >>> 24) & 0xff);
        output.write((length >>> 16) & 0xff);
        output.write((length >>> 8) & 0xff);
        output.write(length & 0xff);
        output.write(payload);
    }

    private static int decodeLength(byte[] framed) {
        assertTrue(framed.length >= 4);
        return ((framed[0] & 0xff) << 24)
                | ((framed[1] & 0xff) << 16)
                | ((framed[2] & 0xff) << 8)
                | (framed[3] & 0xff);
    }

    private static void awaitOperation(MockRobotBackend backend, String operation)
            throws Exception {
        long deadline = System.nanoTime() + 2_000_000_000L;
        while (count(backend, operation) == 0) {
            if (System.nanoTime() >= deadline) {
                throw new AssertionError("operation not observed: " + operation);
            }
            Thread.yield();
        }
    }

    private static void awaitAxis(MockRobotBackend backend, String axis, int expected)
            throws Exception {
        long deadline = System.nanoTime() + 2_000_000_000L;
        while (!Integer.valueOf(expected).equals(backend.currentAxes().get(axis))) {
            if (System.nanoTime() >= deadline) {
                throw new AssertionError("axis value not observed: " + axis);
            }
            Thread.yield();
        }
    }

    private static int count(MockRobotBackend backend, String operation) {
        int count = 0;
        for (String observed : backend.operationHistory()) {
            if (operation.equals(observed)) {
                count++;
            }
        }
        return count;
    }

    private static byte[] utf8(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] minimalPcmWav() {
        byte[] wav = new byte[46];
        putAscii(wav, 0, "RIFF");
        putIntLittleEndian(wav, 4, wav.length - 8);
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

    private static final class Fixture implements AutoCloseable {
        private final MockRobotBackend backend = new MockRobotBackend();
        private final MockAudioOutput audioOutput = new MockAudioOutput();
        private final RobotControllerApplication application;

        private Fixture() throws Exception {
            ApplicationConfiguration configuration = ApplicationConfiguration.builder()
                    .backendSelection(BackendSelection.MOCK)
                    .listenHost("127.0.0.1")
                    .listenPort(0)
                    .connectionWorkerCount(2)
                    .connectionQueueCapacity(2)
                    .hardwareCommandQueueCapacity(8)
                    .socketTimeoutMilliseconds(500)
                    .shutdownTimeoutMilliseconds(2_000)
                    .processLockPath(Files.createTempDirectory(
                            "robot-controller-wire-test-").resolve("controller.lock"))
                    .build();
            application = new RobotControllerApplication(configuration, backend, audioOutput);
        }

        private void start() throws Exception {
            application.start();
        }

        private int port() {
            return application.localPort();
        }

        @Override
        public void close() {
            application.close();
        }
    }
}
