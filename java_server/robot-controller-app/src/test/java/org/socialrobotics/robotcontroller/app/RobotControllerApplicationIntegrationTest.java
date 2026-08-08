package org.socialrobotics.robotcontroller.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.Test;
import org.socialrobotics.robotcontroller.core.backend.RobotBackendException;
import org.socialrobotics.robotcontroller.core.backend.RobotLifecycleState;
import org.socialrobotics.robotcontroller.core.audio.AudioPlaybackState;
import org.socialrobotics.robotcontroller.core.audio.MouthEnvelopeAnalyzer;
import org.socialrobotics.robotcontroller.core.audio.MouthEnvelopeConfig;
import org.socialrobotics.robotcontroller.mock.MockAudioOutput;
import org.socialrobotics.robotcontroller.mock.MockAudioPlaybackSession;
import org.socialrobotics.robotcontroller.mock.MockOperationHook;
import org.socialrobotics.robotcontroller.mock.MockRobotBackend;

public final class RobotControllerApplicationIntegrationTest {
    @Test
    public void startupPoseAndReadAxesTravelThroughTcpAndHardwareWorker() throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        Map<String, Integer> axes = new HashMap<String, Integer>();
        axes.put("HEAD_Y", Integer.valueOf(7));
        axes.put("HEAD_P", Integer.valueOf(-2));
        backend.seedAxes(axes);
        RobotControllerApplication application = createApplication(backend, defaultConfig());
        application.start();
        try {
            assertEquals(RobotLifecycleState.READY, application.lifecycleState());
            assertTrue(application.localPort() > 0);

            byte[] response = sendForResponse(application.localPort(), "read_axes", null);
            String json = new String(response, StandardCharsets.UTF_8);
            assertTrue(json.contains("\"HEAD_Y\":7"));
            assertTrue(json.contains("\"HEAD_P\":-2"));

            assertNoResponse(
                    application.localPort(),
                    "play_pose",
                    "{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":12}}"
                            .getBytes(StandardCharsets.UTF_8));
            awaitHistoryCount(backend, "applyPose", 1);
            assertEquals(Integer.valueOf(12), backend.currentAxes().get("HEAD_Y"));
            assertEquals(1, backend.maximumConcurrentBackendCalls());
        } finally {
            application.close();
        }
        assertEquals(RobotLifecycleState.STOPPED, application.lifecycleState());
    }

    @Test
    public void invalidRequestsCloseOnlyTheirConnectionAndReturnNoLegacyErrorFrame()
            throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        backend.seedAxes(Collections.singletonMap("HEAD_Y", Integer.valueOf(3)));
        RobotControllerApplication application = createApplication(backend, defaultConfig());
        application.start();
        try {
            assertRejectedWithoutResponse(application.localPort(), "unknown_command", null);
            assertRejectedWithoutResponse(
                    application.localPort(),
                    "play_pose",
                    "{".getBytes(StandardCharsets.UTF_8));
            assertRejectedWithoutResponse(application.localPort(), "play_pose", null);
            assertRejectedWithoutResponse(
                    application.localPort(),
                    "read_axes",
                    "{}".getBytes(StandardCharsets.UTF_8));
            assertRejectedWithoutResponse(
                    application.localPort(),
                    "play_pose",
                    "{\"Msec\":1,\"ServoMap\":{\"HEAD_P\":6}}"
                            .getBytes(StandardCharsets.UTF_8));

            byte[] response = sendForResponse(application.localPort(), "read_axes", null);
            assertTrue(new String(response, StandardCharsets.UTF_8).contains("\"HEAD_Y\":3"));
            assertEquals(RobotLifecycleState.READY, application.lifecycleState());
        } finally {
            application.close();
        }
    }

    @Test
    public void oversizedAndTruncatedFramesDoNotStopServer() throws Exception {
        ApplicationConfiguration configuration = defaultConfig().toBuilder()
                .maximumCommandFrameBytes(16)
                .build();
        MockRobotBackend backend = new MockRobotBackend();
        backend.seedAxes(Collections.singletonMap("HEAD_Y", Integer.valueOf(1)));
        RobotControllerApplication application = createApplication(backend, configuration);
        application.start();
        try {
            Socket oversized = connect(application.localPort());
            try {
                oversized.getOutputStream().write(new byte[] {0, 0, 0, 17});
                oversized.shutdownOutput();
                assertEquals(-1, oversized.getInputStream().read());
            } finally {
                oversized.close();
            }

            Socket truncated = connect(application.localPort());
            try {
                truncated.getOutputStream().write(new byte[] {0, 0, 0, 9, 'r', 'e'});
                truncated.shutdownOutput();
                assertEquals(-1, truncated.getInputStream().read());
            } finally {
                truncated.close();
            }

            assertTrue(new String(
                    sendForResponse(application.localPort(), "read_axes", null),
                    StandardCharsets.UTF_8).contains("\"HEAD_Y\":1"));
        } finally {
            application.close();
        }
    }

    @Test
    public void backendExceptionIsContainedAndWorkerContinues() throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        backend.failOperation("applyPose", new RobotBackendException("injected"));
        RobotControllerApplication application = createApplication(backend, defaultConfig());
        application.start();
        try {
            assertNoResponse(
                    application.localPort(),
                    "play_pose",
                    "{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":1}}"
                            .getBytes(StandardCharsets.UTF_8));
            backend.clearFailure("applyPose");
            assertNoResponse(
                    application.localPort(),
                    "play_pose",
                    "{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":2}}"
                            .getBytes(StandardCharsets.UTF_8));
            awaitHistoryCount(backend, "applyPose", 2);
            assertEquals(Integer.valueOf(2), backend.currentAxes().get("HEAD_Y"));
        } finally {
            application.close();
        }
    }

    @Test
    public void hardwareQueueSaturationRejectsOverflowWithoutConcurrentBackendCalls()
            throws Exception {
        final CountDownLatch firstPoseEntered = new CountDownLatch(1);
        final CountDownLatch releasePose = new CountDownLatch(1);
        MockRobotBackend backend = new MockRobotBackend(new MockOperationHook() {
            @Override
            public void duringOperation(String operationName) throws InterruptedException {
                if ("applyPose".equals(operationName)) {
                    firstPoseEntered.countDown();
                    releasePose.await();
                }
            }
        });
        ApplicationConfiguration configuration = defaultConfig().toBuilder()
                .connectionWorkerCount(3)
                .connectionQueueCapacity(3)
                .hardwareCommandQueueCapacity(1)
                .build();
        RobotControllerApplication application = createApplication(backend, configuration);
        ExecutorService clients = Executors.newFixedThreadPool(3);
        application.start();
        try {
            Future<?> first = clients.submit(sendPose(application.localPort(), 1));
            assertTrue(firstPoseEntered.await(2, TimeUnit.SECONDS));
            Future<?> second = clients.submit(sendPose(application.localPort(), 2));
            awaitCondition(new Condition() {
                @Override
                public boolean isSatisfied() {
                    return application.queuedHardwareCommandCount() == 1;
                }
            });
            Future<?> third = clients.submit(sendPose(application.localPort(), 3));
            third.get(2, TimeUnit.SECONDS);
            releasePose.countDown();
            first.get(2, TimeUnit.SECONDS);
            second.get(2, TimeUnit.SECONDS);
            assertEquals(1, backend.maximumConcurrentBackendCalls());
            // The second queued direct pose is stale after the third replacement attempt.
            assertEquals(1, historyCount(backend, "applyPose"));
        } finally {
            releasePose.countDown();
            clients.shutdownNow();
            application.close();
        }
    }

    @Test
    public void connectionExecutorSaturationClosesExcessConnection() throws Exception {
        ApplicationConfiguration configuration = defaultConfig().toBuilder()
                .connectionWorkerCount(1)
                .connectionQueueCapacity(1)
                .socketTimeoutMilliseconds(2_000)
                .build();
        RobotControllerApplication application = createApplication(
                new MockRobotBackend(), configuration);
        application.start();
        Socket first = connect(application.localPort());
        Socket second = null;
        Socket excess = null;
        try {
            awaitCondition(new Condition() {
                @Override
                public boolean isSatisfied() {
                    return application.activeConnectionHandlerCount() == 1;
                }
            });
            second = connect(application.localPort());
            final RobotControllerApplication observed = application;
            awaitCondition(new Condition() {
                @Override
                public boolean isSatisfied() {
                    return observed.queuedConnectionCount() == 1;
                }
            });
            excess = connect(application.localPort());
            excess.setSoTimeout(2_000);
            assertEquals(-1, excess.getInputStream().read());
        } finally {
            first.close();
            if (second != null) {
                second.close();
            }
            if (excess != null) {
                excess.close();
            }
            application.close();
        }
    }

    @Test
    public void shutdownClosesConnectionBlockedInPartialFrameAndIsIdempotent()
            throws Exception {
        RobotControllerApplication application = createApplication(
                new MockRobotBackend(), defaultConfig());
        application.start();
        Socket socket = connect(application.localPort());
        socket.setSoTimeout(2_000);
        socket.getOutputStream().write(new byte[] {0, 0});
        awaitCondition(new Condition() {
            @Override
            public boolean isSatisfied() {
                return application.activeConnectionHandlerCount() == 1;
            }
        });

        application.close();
        application.close();

        assertEquals(-1, socket.getInputStream().read());
        socket.close();
        assertEquals(RobotLifecycleState.STOPPED, application.lifecycleState());
    }

    @Test
    public void partialHeaderSocketTimeoutClosesOnlyThatConnection() throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        backend.seedAxes(Collections.singletonMap("HEAD_Y", Integer.valueOf(4)));
        RobotControllerApplication application = createApplication(
                backend,
                defaultConfig().toBuilder().socketTimeoutMilliseconds(100).build());
        application.start();
        try {
            Socket socket = connect(application.localPort());
            socket.setSoTimeout(2_000);
            try {
                socket.getOutputStream().write(new byte[] {0, 0});
                socket.getOutputStream().flush();
                assertEquals(-1, socket.getInputStream().read());
            } finally {
                socket.close();
            }

            assertTrue(new String(
                    sendForResponse(application.localPort(), "read_axes", null),
                    StandardCharsets.UTF_8).contains("\"HEAD_Y\":4"));
        } finally {
            application.close();
        }
    }

    @Test
    public void tcpListenStartsOnlyAfterBackendInitializationCompletes() throws Exception {
        final CountDownLatch initializeEntered = new CountDownLatch(1);
        final CountDownLatch releaseInitialize = new CountDownLatch(1);
        MockRobotBackend backend = new MockRobotBackend(new MockOperationHook() {
            @Override
            public void duringOperation(String operationName) throws InterruptedException {
                if ("initialize".equals(operationName)) {
                    initializeEntered.countDown();
                    releaseInitialize.await();
                }
            }
        });
        final int port = reservePort();
        final RobotControllerApplication application = createApplication(
                backend,
                defaultConfig().toBuilder().listenPort(port).build());
        ExecutorService starter = Executors.newSingleThreadExecutor();
        try {
            Future<?> started = starter.submit(new Runnable() {
                @Override
                public void run() {
                    try {
                        application.start();
                    } catch (Exception failure) {
                        throw new RuntimeException(failure);
                    }
                }
            });
            assertTrue(initializeEntered.await(2, TimeUnit.SECONDS));
            assertEquals(RobotLifecycleState.INITIALIZING, application.lifecycleState());
            assertFalse(canConnect(port));

            releaseInitialize.countDown();
            started.get(2, TimeUnit.SECONDS);
            assertTrue(canConnect(port));
        } finally {
            releaseInitialize.countDown();
            starter.shutdownNow();
            application.close();
        }
    }

    @Test
    public void replacingMotionPreventsRemainingOldPosesAndStopsAreIdempotent()
            throws Exception {
        final CountDownLatch firstPoseEntered = new CountDownLatch(1);
        final CountDownLatch releaseFirstPose = new CountDownLatch(1);
        MockRobotBackend backend = new MockRobotBackend(new MockOperationHook() {
            @Override
            public void duringOperation(String operationName) throws InterruptedException {
                if ("applyPose".equals(operationName)
                        && firstPoseEntered.getCount() > 0L) {
                    firstPoseEntered.countDown();
                    releaseFirstPose.await();
                }
            }
        });
        RobotControllerApplication application = createApplication(backend, defaultConfig());
        application.start();
        try {
            assertNoResponse(
                    application.localPort(),
                    "play_motion",
                    ("[{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":1}},"
                            + "{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":2}}]")
                            .getBytes(StandardCharsets.UTF_8));
            assertTrue(firstPoseEntered.await(2, TimeUnit.SECONDS));
            assertNoResponse(
                    application.localPort(),
                    "play_motion",
                    "[{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":3}}]"
                            .getBytes(StandardCharsets.UTF_8));
            releaseFirstPose.countDown();
            awaitCondition(new Condition() {
                @Override
                public boolean isSatisfied() {
                    return Integer.valueOf(3).equals(backend.currentAxes().get("HEAD_Y"));
                }
            });
            assertNoResponse(application.localPort(), "stop_motion", null);
            assertNoResponse(application.localPort(), "stop_motion", null);
            assertEquals(2, historyCount(backend, "applyPose"));
        } finally {
            releaseFirstPose.countDown();
            application.close();
        }
    }

    @Test
    public void idleMotionUsesProfilePosesAndStopPreventsFurtherQueuedPose() throws Exception {
        final CountDownLatch idlePoseEntered = new CountDownLatch(1);
        final CountDownLatch releaseIdlePose = new CountDownLatch(1);
        MockRobotBackend backend = new MockRobotBackend(new MockOperationHook() {
            @Override
            public void duringOperation(String operationName) throws InterruptedException {
                if ("applyPose".equals(operationName)) {
                    idlePoseEntered.countDown();
                    releaseIdlePose.await();
                }
            }
        });
        RobotControllerApplication application = createApplication(backend, defaultConfig());
        ExecutorService stopper = Executors.newSingleThreadExecutor();
        application.start();
        try {
            assertNoResponse(
                    application.localPort(),
                    "play_idle_motion",
                    "{\"Speed\":10,\"Pause\":0}".getBytes(StandardCharsets.UTF_8));
            assertTrue(idlePoseEntered.await(2, TimeUnit.SECONDS));
            Future<?> stopped = stopper.submit(new Runnable() {
                @Override
                public void run() {
                    try {
                        assertNoResponse(application.localPort(), "stop_idle_motion", null);
                    } catch (Exception failure) {
                        throw new RuntimeException(failure);
                    }
                }
            });
            awaitCondition(new Condition() {
                @Override
                public boolean isSatisfied() {
                    return application.queuedHardwareCommandCount() == 1;
                }
            });
            releaseIdlePose.countDown();
            stopped.get(2, TimeUnit.SECONDS);
            assertNoResponse(application.localPort(), "stop_idle_motion", null);
            assertEquals(1, historyCount(backend, "applyPose"));
        } finally {
            releaseIdlePose.countDown();
            stopper.shutdownNow();
            application.close();
        }
    }

    @Test
    public void playAndStopWavUseOwnedMockAudioSessionWithoutLegacyAck() throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        final MockAudioOutput audioOutput = new MockAudioOutput();
        ManualMouthSyncScheduler scheduler = new ManualMouthSyncScheduler();
        RobotControllerApplication application = new RobotControllerApplication(
                defaultConfig(),
                backend,
                audioOutput,
                scheduler,
                deterministicMouthAnalyzer());
        application.start();
        try {
            assertNoResponse(application.localPort(), "play_wav", monoPcmWav());
            awaitCondition(new Condition() {
                @Override
                public boolean isSatisfied() {
                    return audioOutput.sessions().size() == 1;
                }
            });
            MockAudioPlaybackSession session = audioOutput.sessions().get(0);
            assertEquals(AudioPlaybackState.PLAYING, session.state());
            scheduler.runLatest();
            awaitCondition(new Condition() {
                @Override
                public boolean isSatisfied() {
                    Integer value = backend.currentLedValues().get("MOUTH");
                    return value != null && value.intValue() > 0;
                }
            });
            for (String threadName : backend.ledWriteThreadHistory("MOUTH")) {
                assertEquals("robot-hardware-worker", threadName);
            }
            assertNoResponse(application.localPort(), "stop_wav", null);
            assertNoResponse(application.localPort(), "stop_wav", null);
            assertEquals(AudioPlaybackState.CLOSED, session.state());
            assertEquals(Integer.valueOf(0), backend.currentLedValues().get("MOUTH"));
        } finally {
            application.close();
        }
    }

    @Test
    public void applicationShutdownOwnsAudioSessionAndPreventsLateMouthUpdate()
            throws Exception {
        MockRobotBackend backend = new MockRobotBackend();
        MockAudioOutput audioOutput = new MockAudioOutput();
        ManualMouthSyncScheduler scheduler = new ManualMouthSyncScheduler();
        RobotControllerApplication application = new RobotControllerApplication(
                defaultConfig(),
                backend,
                audioOutput,
                scheduler,
                deterministicMouthAnalyzer());
        application.start();
        assertNoResponse(application.localPort(), "play_wav", monoPcmWav());
        MockAudioPlaybackSession session = audioOutput.sessions().get(0);
        scheduler.runLatest();
        awaitCondition(new Condition() {
            @Override
            public boolean isSatisfied() {
                Integer value = backend.currentLedValues().get("MOUTH");
                return value != null && value.intValue() > 0;
            }
        });

        application.close();
        int writeCountAfterClose = backend.ledValueHistory("MOUTH").size();
        scheduler.runAll();

        assertEquals(AudioPlaybackState.CLOSED, session.state());
        assertEquals(Integer.valueOf(0), backend.currentLedValues().get("MOUTH"));
        assertEquals(writeCountAfterClose, backend.ledValueHistory("MOUTH").size());
        assertTrue(scheduler.closed);
        assertEquals(RobotLifecycleState.STOPPED, application.lifecycleState());
    }

    @Test
    public void backendInitializationFailureNeverListensAndClosesPartialResources()
            throws Exception {
        int port = reservePort();
        MockRobotBackend backend = new MockRobotBackend();
        backend.failOperation("initialize", new RobotBackendException("injected initialize"));
        RobotControllerApplication application = createApplication(
                backend, defaultConfig().toBuilder().listenPort(port).build());

        try {
            application.start();
            fail("expected startup failure");
        } catch (ApplicationStartupException expected) {
            // Expected.
        }

        assertEquals(RobotLifecycleState.FAILED, application.lifecycleState());
        assertFalse(canConnect(port));
        assertEquals(0, historyCount(backend, "setLed"));
        assertEquals(1, historyCount(backend, "close"));
    }

    private static RobotControllerApplication createApplication(
            MockRobotBackend backend,
            ApplicationConfiguration configuration) {
        return new RobotControllerApplication(configuration, backend, new MockAudioOutput());
    }

    private static ApplicationConfiguration defaultConfig() {
        return ApplicationConfiguration.builder()
                .listenHost("127.0.0.1")
                .listenPort(0)
                .connectionWorkerCount(2)
                .connectionQueueCapacity(2)
                .hardwareCommandQueueCapacity(2)
                .maximumCommandFrameBytes(64)
                .maximumJsonFrameBytes(1_048_576)
                .maximumWavFrameBytes(20_971_520)
                .socketTimeoutMilliseconds(1_000)
                .shutdownTimeoutMilliseconds(2_000)
                .backendSelection(BackendSelection.MOCK)
                .build();
    }

    private static Runnable sendPose(final int port, final int value) {
        return new Runnable() {
            @Override
            public void run() {
                try {
                    assertNoResponse(
                            port,
                            "play_pose",
                            ("{\"Msec\":0,\"ServoMap\":{\"HEAD_Y\":" + value + "}}")
                                    .getBytes(StandardCharsets.UTF_8));
                } catch (Exception failure) {
                    throw new RuntimeException(failure);
                }
            }
        };
    }

    private static void assertNoResponse(int port, String command, byte[] payload)
            throws Exception {
        Socket socket = connect(port);
        socket.setSoTimeout(2_000);
        try {
            ByteArrayOutputStream request = new ByteArrayOutputStream();
            writeFrame(request, command.getBytes(StandardCharsets.UTF_8));
            if (payload != null) {
                writeFrame(request, payload);
            }
            socket.getOutputStream().write(request.toByteArray());
            socket.getOutputStream().flush();
            socket.shutdownOutput();
            assertEquals(-1, socket.getInputStream().read());
        } finally {
            socket.close();
        }
    }

    private static void assertRejectedWithoutResponse(
            int port,
            String command,
            byte[] payload) throws Exception {
        try {
            assertNoResponse(port, command, payload);
        } catch (SocketException resetByPeer) {
            // Windows may use RST when a rejected request leaves an unread extra frame.
        }
    }

    private static byte[] sendForResponse(int port, String command, byte[] payload)
            throws Exception {
        Socket socket = connect(port);
        socket.setSoTimeout(2_000);
        try {
            ByteArrayOutputStream request = new ByteArrayOutputStream();
            writeFrame(request, command.getBytes(StandardCharsets.UTF_8));
            if (payload != null) {
                writeFrame(request, payload);
            }
            socket.getOutputStream().write(request.toByteArray());
            socket.getOutputStream().flush();
            return readFrame(socket.getInputStream());
        } finally {
            socket.close();
        }
    }

    private static Socket connect(int port) throws IOException {
        Socket socket = new Socket();
        socket.connect(new InetSocketAddress("127.0.0.1", port), 2_000);
        return socket;
    }

    private static void writeFrame(OutputStream output, byte[] payload) throws IOException {
        int length = payload.length;
        output.write((length >>> 24) & 0xff);
        output.write((length >>> 16) & 0xff);
        output.write((length >>> 8) & 0xff);
        output.write(length & 0xff);
        output.write(payload);
        output.flush();
    }

    private static byte[] readFrame(InputStream input) throws IOException {
        byte[] header = readFully(input, 4);
        int length = ((header[0] & 0xff) << 24)
                | ((header[1] & 0xff) << 16)
                | ((header[2] & 0xff) << 8)
                | (header[3] & 0xff);
        return readFully(input, length);
    }

    private static byte[] readFully(InputStream input, int length) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream(length);
        while (bytes.size() < length) {
            int value = input.read();
            if (value < 0) {
                throw new EOFException("truncated frame");
            }
            bytes.write(value);
        }
        return bytes.toByteArray();
    }

    private static void awaitHistoryCount(
            final MockRobotBackend backend,
            final String operation,
            final int expected) throws Exception {
        awaitCondition(new Condition() {
            @Override
            public boolean isSatisfied() {
                return historyCount(backend, operation) >= expected;
            }
        });
    }

    private static int historyCount(MockRobotBackend backend, String operation) {
        int count = 0;
        for (String observed : backend.operationHistory()) {
            if (operation.equals(observed)) {
                count++;
            }
        }
        return count;
    }

    private static void awaitCondition(Condition condition) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
        while (!condition.isSatisfied()) {
            if (System.nanoTime() >= deadline) {
                fail("condition was not satisfied before timeout");
            }
            Thread.yield();
        }
    }

    private static int reservePort() throws IOException {
        ServerSocket socket = new ServerSocket(0);
        try {
            return socket.getLocalPort();
        } finally {
            socket.close();
        }
    }

    private static boolean canConnect(int port) throws IOException {
        Socket socket = new Socket();
        try {
            socket.connect(new InetSocketAddress("127.0.0.1", port), 100);
            return true;
        } catch (IOException expected) {
            return false;
        } finally {
            socket.close();
        }
    }

    private static byte[] monoPcmWav() {
        int frameCount = 20;
        byte[] wav = new byte[44 + frameCount * 2];
        putAscii(wav, 0, "RIFF");
        putIntLittleEndian(wav, 4, wav.length - 8);
        putAscii(wav, 8, "WAVE");
        putAscii(wav, 12, "fmt ");
        putIntLittleEndian(wav, 16, 16);
        putShortLittleEndian(wav, 20, 1);
        putShortLittleEndian(wav, 22, 1);
        putIntLittleEndian(wav, 24, 1000);
        putIntLittleEndian(wav, 28, 2000);
        putShortLittleEndian(wav, 32, 2);
        putShortLittleEndian(wav, 34, 16);
        putAscii(wav, 36, "data");
        putIntLittleEndian(wav, 40, frameCount * 2);
        for (int frame = 0; frame < frameCount; frame++) {
            putShortLittleEndian(wav, 44 + frame * 2, 30000);
        }
        return wav;
    }

    private static MouthEnvelopeAnalyzer deterministicMouthAnalyzer() {
        return new MouthEnvelopeAnalyzer(
                new MouthEnvelopeConfig(20, 0.0d, 1.0d, 1.0d, 0, 0, 255));
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

    private interface Condition {
        boolean isSatisfied();
    }

    private static final class ManualMouthSyncScheduler implements MouthSyncScheduler {
        private final List<ManualMouthSyncHandle> handles =
                new ArrayList<ManualMouthSyncHandle>();
        private boolean closed;

        @Override
        public synchronized MouthSyncHandle schedule(Runnable task) {
            ManualMouthSyncHandle handle = new ManualMouthSyncHandle(task);
            handles.add(handle);
            return handle;
        }

        synchronized void runLatest() {
            for (int index = handles.size() - 1; index >= 0; index--) {
                ManualMouthSyncHandle handle = handles.get(index);
                if (!handle.cancelled) {
                    handle.run();
                    return;
                }
            }
        }

        synchronized void runAll() {
            for (ManualMouthSyncHandle handle
                    : new ArrayList<ManualMouthSyncHandle>(handles)) {
                handle.run();
            }
        }

        @Override
        public synchronized void close() {
            closed = true;
            for (ManualMouthSyncHandle handle : handles) {
                handle.cancel();
            }
        }
    }

    private static final class ManualMouthSyncHandle implements MouthSyncHandle {
        private final Runnable task;
        private boolean cancelled;

        private ManualMouthSyncHandle(Runnable task) {
            this.task = task;
        }

        @Override
        public synchronized void cancel() {
            cancelled = true;
        }

        private synchronized void run() {
            if (!cancelled) {
                task.run();
            }
        }
    }
}
