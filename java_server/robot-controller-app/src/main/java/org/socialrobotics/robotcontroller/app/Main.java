package org.socialrobotics.robotcontroller.app;

import java.util.concurrent.CountDownLatch;

/** Executable RobotController entry point. */
public final class Main {
    private Main() {
    }

    /** Starts the explicitly configured application and owns process shutdown. */
    public static void main(String[] arguments) throws Exception {
        final ApplicationConfiguration configuration =
                ApplicationConfiguration.fromArguments(arguments);
        final RobotControllerApplication application =
                RobotControllerComposition.create(configuration);
        final CountDownLatch shutdownComplete = new CountDownLatch(1);
        Thread shutdownHook = new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    application.close();
                } finally {
                    shutdownComplete.countDown();
                }
            }
        }, "robot-controller-shutdown");
        Runtime.getRuntime().addShutdownHook(shutdownHook);
        boolean smokeTest = contains(arguments, "--smoke-test");
        try {
            application.start();
            if (smokeTest) {
                application.close();
                removeShutdownHookIfPossible(shutdownHook);
                return;
            }
            shutdownComplete.await();
        } catch (InterruptedException failure) {
            application.close();
            removeShutdownHookIfPossible(shutdownHook);
            Thread.currentThread().interrupt();
            throw failure;
        } catch (Exception failure) {
            application.close();
            removeShutdownHookIfPossible(shutdownHook);
            throw failure;
        }
    }

    private static boolean contains(String[] values, String expected) {
        for (String value : values) {
            if (expected.equals(value)) {
                return true;
            }
        }
        return false;
    }

    private static void removeShutdownHookIfPossible(Thread shutdownHook) {
        try {
            Runtime.getRuntime().removeShutdownHook(shutdownHook);
        } catch (IllegalStateException ignored) {
            // JVM shutdown already owns the hook.
        }
    }
}
