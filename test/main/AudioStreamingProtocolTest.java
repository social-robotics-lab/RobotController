package main;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import utils.StreamingAudioTestFixture;
import utils.StreamingAudioTestFixture.FakeDevice;

/** Localhost, fake-device integration tests for audio_stream_v1. */
public final class AudioStreamingProtocolTest {
    private static final long WAIT_MILLIS = 3000L;
    private static final int SOCKET_TIMEOUT_MILLIS = 3000;
    private static final int NO_RESPONSE_TIMEOUT_MILLIS = 100;

    private static final int START = 0x01;
    private static final int DATA = 0x02;
    private static final int END = 0x03;
    private static final int CANCEL = 0x04;
    private static final int STATUS = 0x80;
    private static final int ERROR = 0x81;
    private static final int CONNECTION_READY = 0x01;
    private static final int STARTED = 0x02;
    private static final int ENDED = 0x03;
    private static final int CANCELLED = 0x04;
    private static final int BUSY = 0x01;
    private static final int PROTOCOL_ERROR = 0x02;
    private static final int AUDIO_ERROR = 0x03;
    private static final int QUEUE_OVERFLOW = 0x04;

    private static final Set<Integer> OBSERVED_RESPONSES = new HashSet<Integer>();
    private static int groupsRun;

    private AudioStreamingProtocolTest() {
    }

    public static void main(String[] args) throws Exception {
        run("default TCPServer construction is native-lazy", new CheckedRunnable() {
            @Override public void run() throws Exception { testNativeLazyConstruction(); }
        });
        run("legacy command remains one-shot without ACK", new CheckedRunnable() {
            @Override public void run() throws Exception { testLegacyNoAck(); }
        });
        run("CONNECTION_READY and BUSY exclusivity", new CheckedRunnable() {
            @Override public void run() throws Exception { testReadyAndBusy(); }
        });
        run("START and END barriers with DATA no ACK", new CheckedRunnable() {
            @Override public void run() throws Exception { testStartDataEndBarriers(); }
        });
        run("CANCEL barrier then fresh START", new CheckedRunnable() {
            @Override public void run() throws Exception { testCancelThenStart(); }
        });
        run("persistent END/CANCEL response lifecycles", new CheckedRunnable() {
            @Override public void run() throws Exception { testPersistentLifecycles(); }
        });
        run("queue overflow cleanup and recovery", new CheckedRunnable() {
            @Override public void run() throws Exception { testQueueOverflow(); }
        });
        run("AUDIO_ERROR on START", new CheckedRunnable() {
            @Override public void run() throws Exception { testStartAudioError(); }
        });
        run("AUDIO_ERROR after asynchronous write failure", new CheckedRunnable() {
            @Override public void run() throws Exception { testWriteAudioError(); }
        });
        run("invalid records in IDLE", new CheckedRunnable() {
            @Override public void run() throws Exception { testInvalidIdleTransitions(); }
        });
        run("START while STREAMING aborts", new CheckedRunnable() {
            @Override public void run() throws Exception { testStartWhileStreaming(); }
        });
        run("malformed and unknown records", new CheckedRunnable() {
            @Override public void run() throws Exception { testMalformedAndUnknown(); }
        });
        run("oversized and negative frame lengths", new CheckedRunnable() {
            @Override public void run() throws Exception { testInvalidFrameLengths(); }
        });
        run("truncated frame cleanup", new CheckedRunnable() {
            @Override public void run() throws Exception { testTruncatedBody(); }
        });
        run("disconnect cleanup and reconnect", new CheckedRunnable() {
            @Override public void run() throws Exception { testDisconnectAndReconnect(); }
        });
        run("END and CANCEL prevent pipelined reads", new CheckedRunnable() {
            @Override public void run() throws Exception { testBarrierReadOrdering(); }
        });
        assertAllResponseFramesObserved();
        System.out.println("ALL TESTS PASSED (" + groupsRun + ")");
    }

    private static void testNativeLazyConstruction() {
        TCPServer server = new TCPServer(0);
        assertTrue(server != null, "default TCPServer construction");
    }

    private static void testLegacyNoAck() throws Exception {
        StreamingAudioTestFixture fixture = fixture(2);
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = Session.open(server, "unknown_safe_command");
        session.expectClosed(false);
    }

    private static void testReadyAndBusy() throws Exception {
        StreamingAudioTestFixture fixture = fixture(2);
        FakeDevice device = fixture.addDevice("busy-owner");
        TCPServer server = new TCPServer(0, fixture.player());
        Session first = openAudio(server);
        Session second = Session.open(server, "audio_stream_v1");
        second.expectError(BUSY);
        second.expectClosed(false);

        first.sendRecord(START);
        first.expectStatus(STARTED);
        first.sendRecord(END);
        first.expectStatus(ENDED);
        first.finishNormally();
        assertOperations(device, "drain", "close");
        fixture.awaitWritersTerminated();
    }

    private static void testStartDataEndBarriers() throws Exception {
        StreamingAudioTestFixture fixture = fixture(2);
        fixture.blockOpen();
        FakeDevice device = fixture.addDevice("barrier-end");
        device.blockClose();
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);

        session.sendRecord(START);
        fixture.awaitOpenEntered();
        session.expectNoRecord();
        fixture.releaseOpen();
        session.expectStatus(STARTED);

        session.sendData(11, 2);
        device.awaitWriteEntered();
        session.expectNoRecord();
        session.sendData(12, 960);
        session.sendRecord(END);
        device.awaitCloseEntered();
        session.expectNoRecord();
        device.releaseClose();
        session.expectStatus(ENDED);
        session.finishNormally();
        assertOperations(device, "write:11", "write:12", "drain", "close");
        fixture.awaitWritersTerminated();
    }

    private static void testCancelThenStart() throws Exception {
        StreamingAudioTestFixture fixture = fixture(2);
        FakeDevice first = fixture.addDevice("cancel-a");
        FakeDevice second = fixture.addDevice("cancel-b");
        first.blockWrite();
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);

        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendData(21, 2);
        first.awaitWriteEntered();
        session.sendRecord(CANCEL);
        session.expectNoRecord();
        first.releaseWrite();
        session.expectStatus(CANCELLED);

        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendData(22, 2);
        second.awaitWriteEntered();
        session.sendRecord(END);
        session.expectStatus(ENDED);
        session.finishNormally();
        assertOperations(first, "write:21", "drop", "close");
        assertOperations(second, "write:22", "drain", "close");
        assertBefore(fixture.events(), "cancel-a:close", "open:cancel-b");
        fixture.awaitWritersTerminated();
    }

    private static void testPersistentLifecycles() throws Exception {
        StreamingAudioTestFixture fixture = fixture(2);
        FakeDevice first = fixture.addDevice("persistent-a");
        FakeDevice second = fixture.addDevice("persistent-b");
        FakeDevice third = fixture.addDevice("persistent-c");
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);

        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendRecord(END);
        session.expectStatus(ENDED);
        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendRecord(CANCEL);
        session.expectStatus(CANCELLED);
        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendRecord(END);
        session.expectStatus(ENDED);
        session.finishNormally();

        assertOperations(first, "drain", "close");
        assertOperations(second, "drop", "close");
        assertOperations(third, "drain", "close");
        fixture.awaitWritersTerminated();
    }

    private static void testQueueOverflow() throws Exception {
        StreamingAudioTestFixture fixture = fixture(1);
        FakeDevice first = fixture.addDevice("overflow-a");
        FakeDevice second = fixture.addDevice("overflow-b");
        first.blockWrite();
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);

        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendData(31, 2);
        first.awaitWriteEntered();
        session.sendData(32, 2);
        session.sendData(33, 2);
        session.expectNoRecord();
        first.releaseWrite();
        session.expectError(QUEUE_OVERFLOW);
        assertOperations(first, "write:31", "drop", "close");

        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendRecord(END);
        session.expectStatus(ENDED);
        session.finishNormally();
        assertOperations(second, "drain", "close");
        fixture.awaitWritersTerminated();
    }

    private static void testStartAudioError() throws Exception {
        StreamingAudioTestFixture fixture = fixture(1);
        fixture.failOpen(new IOException("injected open failure"));
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);
        session.sendRecord(START);
        session.expectError(AUDIO_ERROR);
        session.expectClosed(true);
        fixture.awaitWritersTerminated();
    }

    private static void testWriteAudioError() throws Exception {
        StreamingAudioTestFixture fixture = fixture(2);
        FakeDevice device = fixture.addDevice("write-error");
        device.failWrite(new IOException("injected write failure"));
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);
        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendData(41, 2);
        device.awaitClosed();
        session.sendRecord(END);
        session.expectError(AUDIO_ERROR);
        session.expectClosed(true);
        assertOperations(device, "write:41", "drop", "close");
        fixture.awaitWritersTerminated();
    }

    private static void testInvalidIdleTransitions() throws Exception {
        for (int record : new int[] { DATA, END, CANCEL }) {
            StreamingAudioTestFixture fixture = fixture(1);
            TCPServer server = new TCPServer(0, fixture.player());
            Session session = openAudio(server);
            if (record == DATA) {
                session.sendData(1, 2);
            } else {
                session.sendRecord(record);
            }
            session.expectError(PROTOCOL_ERROR);
            session.expectClosed(true);
        }
    }

    private static void testStartWhileStreaming() throws Exception {
        StreamingAudioTestFixture fixture = fixture(1);
        FakeDevice device = fixture.addDevice("duplicate-start");
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);
        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendRecord(START);
        session.expectError(PROTOCOL_ERROR);
        session.expectClosed(true);
        assertOperations(device, "drop", "close");
        fixture.awaitWritersTerminated();
    }

    private static void testMalformedAndUnknown() throws Exception {
        assertIdleProtocolError(new byte[0]);
        assertIdleProtocolError(new byte[] { (byte) START, 0 });
        assertActiveProtocolError(new byte[] { (byte) DATA });
        assertActiveProtocolError(new byte[] { (byte) DATA, 1, 2, 3 });
        assertActiveProtocolError(new byte[] { (byte) END, 0 });
        assertActiveProtocolError(new byte[] { (byte) CANCEL, 0 });
        assertActiveProtocolError(new byte[] { 0x7f });
    }

    private static void testInvalidFrameLengths() throws Exception {
        assertActiveInvalidLength(962);
        assertActiveInvalidLength(-1);
        assertActiveInvalidLength(Integer.MAX_VALUE);
    }

    private static void testTruncatedBody() throws Exception {
        assertActiveTruncatedFrame(false);
        assertActiveTruncatedFrame(true);
    }

    private static void assertActiveTruncatedFrame(boolean header) throws Exception {
        StreamingAudioTestFixture fixture = fixture(1);
        FakeDevice device = fixture.addDevice(header
                ? "truncated-header" : "truncated-body");
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);
        session.sendRecord(START);
        session.expectStatus(STARTED);
        if (header) {
            session.sendRaw(new byte[] { 0, 0 });
        } else {
            session.sendDeclaredBody(100, new byte[] { (byte) DATA, 1, 2 });
        }
        session.shutdownOutput();
        session.expectError(PROTOCOL_ERROR);
        session.expectClosed(true);
        assertOperations(device, "drop", "close");
        fixture.awaitWritersTerminated();
    }

    private static void assertIdleProtocolError(byte[] body) throws Exception {
        StreamingAudioTestFixture fixture = fixture(1);
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);
        session.sendBody(body);
        session.expectError(PROTOCOL_ERROR);
        session.expectClosed(true);
    }

    private static void testDisconnectAndReconnect() throws Exception {
        StreamingAudioTestFixture fixture = fixture(2);
        FakeDevice first = fixture.addDevice("disconnect-a");
        FakeDevice second = fixture.addDevice("disconnect-b");
        TCPServer server = new TCPServer(0, fixture.player());

        Session disconnected = openAudio(server);
        disconnected.sendRecord(START);
        disconnected.expectStatus(STARTED);
        disconnected.sendData(51, 2);
        first.awaitWriteEntered();
        disconnected.closeClient();
        disconnected.awaitServer(true);
        first.awaitClosed();
        assertOperations(first, "write:51", "drop", "close");

        Session replacement = openAudio(server);
        replacement.sendRecord(START);
        replacement.expectStatus(STARTED);
        replacement.sendRecord(END);
        replacement.expectStatus(ENDED);
        replacement.finishNormally();
        assertOperations(second, "drain", "close");
        fixture.awaitWritersTerminated();
    }

    private static void testBarrierReadOrdering() throws Exception {
        testEndReadOrdering();
        testCancelReadOrdering();
    }

    private static void testEndReadOrdering() throws Exception {
        StreamingAudioTestFixture fixture = fixture(2);
        FakeDevice first = fixture.addDevice("ordered-end-a");
        FakeDevice second = fixture.addDevice("ordered-end-b");
        first.blockClose();
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);
        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendRecord(END);
        session.sendRecord(START);
        first.awaitCloseEntered();
        session.expectNoRecord();
        first.releaseClose();
        session.expectStatus(ENDED);
        session.expectStatus(STARTED);
        session.sendRecord(END);
        session.expectStatus(ENDED);
        session.finishNormally();
        assertOperations(second, "drain", "close");
        fixture.awaitWritersTerminated();
    }

    private static void testCancelReadOrdering() throws Exception {
        StreamingAudioTestFixture fixture = fixture(2);
        FakeDevice first = fixture.addDevice("ordered-cancel-a");
        FakeDevice second = fixture.addDevice("ordered-cancel-b");
        first.blockWrite();
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);
        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendData(61, 2);
        first.awaitWriteEntered();
        session.sendRecord(CANCEL);
        session.sendRecord(START);
        session.expectNoRecord();
        first.releaseWrite();
        session.expectStatus(CANCELLED);
        session.expectStatus(STARTED);
        session.sendRecord(END);
        session.expectStatus(ENDED);
        session.finishNormally();
        assertOperations(second, "drain", "close");
        fixture.awaitWritersTerminated();
    }

    private static void assertActiveProtocolError(byte[] body) throws Exception {
        StreamingAudioTestFixture fixture = fixture(1);
        FakeDevice device = fixture.addDevice("protocol-" + body.length + "-" + body[0]);
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);
        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendBody(body);
        session.expectError(PROTOCOL_ERROR);
        session.expectClosed(true);
        assertOperations(device, "drop", "close");
        fixture.awaitWritersTerminated();
    }

    private static void assertActiveInvalidLength(int length) throws Exception {
        StreamingAudioTestFixture fixture = fixture(1);
        FakeDevice device = fixture.addDevice("length-" + length);
        TCPServer server = new TCPServer(0, fixture.player());
        Session session = openAudio(server);
        session.sendRecord(START);
        session.expectStatus(STARTED);
        session.sendDeclaredBody(length, new byte[0]);
        session.expectError(PROTOCOL_ERROR);
        session.expectClosed(true);
        assertOperations(device, "drop", "close");
        fixture.awaitWritersTerminated();
    }

    private static StreamingAudioTestFixture fixture(int capacity) {
        return new StreamingAudioTestFixture(capacity, 20L, 1000L);
    }

    private static Session openAudio(TCPServer server) throws Exception {
        Session session = Session.open(server, "audio_stream_v1");
        session.expectStatus(CONNECTION_READY);
        return session;
    }

    private static void assertAllResponseFramesObserved() {
        int[] required = {
            key(STATUS, CONNECTION_READY), key(STATUS, STARTED),
            key(STATUS, ENDED), key(STATUS, CANCELLED),
            key(ERROR, BUSY), key(ERROR, PROTOCOL_ERROR),
            key(ERROR, AUDIO_ERROR), key(ERROR, QUEUE_OVERFLOW)
        };
        for (int response : required) {
            if (!OBSERVED_RESPONSES.contains(Integer.valueOf(response))) {
                throw new AssertionError("Required response frame was not observed: "
                        + response);
            }
        }
    }

    private static int key(int type, int code) {
        return (type << 8) | code;
    }

    private static void assertOperations(FakeDevice device, String... expected) {
        assertEquals(Arrays.asList(expected), device.operations(), "fake operations");
    }

    private static void assertBefore(
            List<String> values, String first, String second) {
        int firstIndex = values.indexOf(first);
        int secondIndex = values.indexOf(second);
        assertTrue(firstIndex >= 0 && secondIndex >= 0 && firstIndex < secondIndex,
                "Expected " + first + " before " + second + ": " + values);
    }

    private static void run(String name, CheckedRunnable runnable) throws Exception {
        runnable.run();
        groupsRun++;
        System.out.println("PASS: " + name);
    }

    private static void assertTrue(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void assertEquals(Object expected, Object actual, String message) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(message + ": expected=" + expected
                    + ", actual=" + actual);
        }
    }

    private interface CheckedRunnable {
        void run() throws Exception;
    }

    private static final class Session {
        private final Socket client;
        private final DataInputStream input;
        private final DataOutputStream output;
        private final Thread serverThread;
        private final CountDownLatch serverDone;
        private final FailureBox failure;

        private Session(
                Socket client,
                Thread serverThread,
                CountDownLatch serverDone,
                FailureBox failure) throws IOException {
            this.client = client;
            this.serverThread = serverThread;
            this.serverDone = serverDone;
            this.failure = failure;
            input = new DataInputStream(client.getInputStream());
            output = new DataOutputStream(client.getOutputStream());
        }

        private static Session open(final TCPServer server, String command)
                throws Exception {
            final InetAddress loopback = InetAddress.getByName("127.0.0.1");
            final ServerSocket listener = new ServerSocket(0, 1, loopback);
            listener.setSoTimeout(SOCKET_TIMEOUT_MILLIS);
            final CountDownLatch done = new CountDownLatch(1);
            final FailureBox failure = new FailureBox();
            Thread handler = new Thread(new Runnable() {
                @Override public void run() {
                    try (ServerSocket ownedListener = listener;
                            Socket accepted = ownedListener.accept()) {
                        server.handleConnection(accepted);
                    } catch (Throwable throwable) {
                        failure.value = throwable;
                    } finally {
                        done.countDown();
                    }
                }
            }, "audio-stream-test-handler");
            handler.start();
            Socket client = new Socket(loopback, listener.getLocalPort());
            client.setSoTimeout(SOCKET_TIMEOUT_MILLIS);
            Session session = new Session(client, handler, done, failure);
            session.sendBody(command.getBytes(StandardCharsets.US_ASCII));
            return session;
        }

        private void sendRecord(int type) throws IOException {
            sendBody(new byte[] { (byte) type });
        }

        private void sendData(int value, int length) throws IOException {
            byte[] body = new byte[length + 1];
            body[0] = (byte) DATA;
            Arrays.fill(body, 1, body.length, (byte) value);
            sendBody(body);
        }

        private void sendBody(byte[] body) throws IOException {
            sendDeclaredBody(body.length, body);
        }

        private void sendDeclaredBody(int declaredLength, byte[] body)
                throws IOException {
            output.writeInt(declaredLength);
            output.write(body);
            output.flush();
        }

        private void sendRaw(byte[] data) throws IOException {
            output.write(data);
            output.flush();
        }

        private void expectStatus(int code) throws IOException {
            expectResponse(STATUS, code);
        }

        private void expectError(int code) throws IOException {
            expectResponse(ERROR, code);
        }

        private void expectResponse(int type, int code) throws IOException {
            int length = input.readInt();
            assertEquals(Integer.valueOf(2), Integer.valueOf(length),
                    "response frame body length");
            int actualType = input.readUnsignedByte();
            int actualCode = input.readUnsignedByte();
            assertEquals(Integer.valueOf(type), Integer.valueOf(actualType),
                    "response type");
            assertEquals(Integer.valueOf(code), Integer.valueOf(actualCode),
                    "response code");
            OBSERVED_RESPONSES.add(Integer.valueOf(key(type, code)));
        }

        private void expectNoRecord() throws IOException {
            int previous = client.getSoTimeout();
            client.setSoTimeout(NO_RESPONSE_TIMEOUT_MILLIS);
            try {
                int value = input.read();
                if (value < 0) {
                    throw new EOFException("Connection closed while expecting no response.");
                }
                throw new AssertionError("Unexpected response byte: " + value);
            } catch (SocketTimeoutException expected) {
                // A bounded socket timeout proves no response crossed the barrier.
            } finally {
                client.setSoTimeout(previous);
            }
        }

        private void shutdownOutput() throws IOException {
            client.shutdownOutput();
        }

        private void finishNormally() throws Exception {
            shutdownOutput();
            expectClosed(false);
        }

        private void expectClosed(boolean allowIOException) throws Exception {
            int value = input.read();
            assertEquals(Integer.valueOf(-1), Integer.valueOf(value),
                    "connection EOF");
            awaitServer(allowIOException);
            client.close();
        }

        private void closeClient() throws IOException {
            client.close();
        }

        private void awaitServer(boolean allowIOException) throws Exception {
            if (!serverDone.await(WAIT_MILLIS, TimeUnit.MILLISECONDS)) {
                throw new AssertionError("TCP handler did not terminate.");
            }
            serverThread.join(WAIT_MILLIS);
            assertTrue(!serverThread.isAlive(), "TCP handler thread leaked.");
            Throwable throwable = failure.value;
            if (throwable == null) {
                return;
            }
            if (allowIOException && throwable instanceof IOException) {
                return;
            }
            if (throwable instanceof Exception) {
                throw (Exception) throwable;
            }
            if (throwable instanceof Error) {
                throw (Error) throwable;
            }
            throw new AssertionError(throwable);
        }
    }

    private static final class FailureBox {
        private volatile Throwable value;
    }
}
