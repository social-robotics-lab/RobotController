package org.socialrobotics.robotcontroller.app;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;
import java.util.Collections;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

/** Controlled accept loop with a bounded fixed-size connection executor. */
final class BoundedTcpServer implements AutoCloseable {
    private static final Logger LOGGER = Logger.getLogger(BoundedTcpServer.class.getName());

    private final ApplicationConfiguration configuration;
    private final ConnectionProcessor processor;
    private final ThreadPoolExecutor connections;
    private final Set<Socket> ownedSockets = Collections.newSetFromMap(
            new ConcurrentHashMap<Socket, Boolean>());
    private final Object lifecycleLock = new Object();
    private volatile boolean running;
    private boolean closed;
    private volatile ServerSocket serverSocket;
    private Thread acceptThread;

    BoundedTcpServer(
            ApplicationConfiguration configuration,
            ConnectionProcessor processor) {
        if (configuration == null || processor == null) {
            throw new NullPointerException("configuration and processor are required");
        }
        this.configuration = configuration;
        this.processor = processor;
        final AtomicInteger sequence = new AtomicInteger();
        this.connections = new ThreadPoolExecutor(
                configuration.connectionWorkerCount(),
                configuration.connectionWorkerCount(),
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(configuration.connectionQueueCapacity()),
                new ThreadFactory() {
                    @Override
                    public Thread newThread(Runnable runnable) {
                        Thread thread = new Thread(
                                runnable,
                                "robot-connection-" + sequence.incrementAndGet());
                        thread.setDaemon(false);
                        return thread;
                    }
                },
                new ThreadPoolExecutor.AbortPolicy());
    }

    /** Binds and starts accepting. No socket is created by the constructor. */
    void start() throws IOException {
        synchronized (lifecycleLock) {
            if (running || closed) {
                throw new IllegalStateException("TCP server is already running");
            }
            ServerSocket created = new ServerSocket();
            boolean bound = false;
            try {
                created.setReuseAddress(true);
                int backlog = configuration.connectionWorkerCount()
                        + configuration.connectionQueueCapacity();
                created.bind(
                        new InetSocketAddress(
                                configuration.listenHost(), configuration.listenPort()),
                        backlog);
                bound = true;
                serverSocket = created;
                running = true;
                acceptThread = new Thread(new Runnable() {
                    @Override
                    public void run() {
                        acceptLoop();
                    }
                }, "robot-tcp-accept");
                acceptThread.setDaemon(false);
                acceptThread.start();
            } finally {
                if (!bound) {
                    closeQuietly(created);
                }
            }
        }
    }

    int localPort() {
        ServerSocket socket = serverSocket;
        return socket == null ? -1 : socket.getLocalPort();
    }

    int activeConnectionHandlerCount() {
        return connections.getActiveCount();
    }

    int queuedConnectionCount() {
        return connections.getQueue().size();
    }

    private void acceptLoop() {
        while (running) {
            Socket socket = null;
            try {
                socket = serverSocket.accept();
                ownedSockets.add(socket);
                final Socket accepted = socket;
                connections.execute(new Runnable() {
                    @Override
                    public void run() {
                        try {
                            processor.process(accepted);
                        } catch (IOException failure) {
                            LOGGER.log(Level.FINE, "connection ended with I/O failure");
                        } catch (RuntimeException failure) {
                            LOGGER.log(Level.WARNING, "connection handler failure", failure);
                        } finally {
                            ownedSockets.remove(accepted);
                            closeQuietly(accepted);
                        }
                    }
                });
            } catch (RejectedExecutionException rejected) {
                if (socket != null) {
                    ownedSockets.remove(socket);
                    closeQuietly(socket);
                }
            } catch (SocketException failure) {
                if (running) {
                    LOGGER.log(Level.WARNING, "TCP accept failed", failure);
                }
            } catch (IOException failure) {
                if (running) {
                    LOGGER.log(Level.WARNING, "TCP accept failed", failure);
                }
            }
        }
    }

    @Override
    public void close() {
        synchronized (lifecycleLock) {
            if (closed) {
                return;
            }
            closed = true;
            running = false;
            closeQuietly(serverSocket);
            serverSocket = null;
            for (Socket socket : ownedSockets) {
                closeQuietly(socket);
            }
            connections.shutdownNow();
        }
        boolean interrupted = false;
        try {
            Thread currentAcceptThread = acceptThread;
            if (currentAcceptThread != null && currentAcceptThread != Thread.currentThread()) {
                currentAcceptThread.join(configuration.shutdownTimeoutMilliseconds());
            }
            connections.awaitTermination(
                    configuration.shutdownTimeoutMilliseconds(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException failure) {
            interrupted = true;
        } finally {
            if (interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private static void closeQuietly(ServerSocket socket) {
        if (socket != null) {
            try {
                socket.close();
            } catch (IOException ignored) {
                // Best effort during controlled shutdown.
            }
        }
    }

    private static void closeQuietly(Socket socket) {
        if (socket != null) {
            try {
                socket.close();
            } catch (IOException ignored) {
                // Best effort during controlled shutdown or rejection.
            }
        }
    }
}
