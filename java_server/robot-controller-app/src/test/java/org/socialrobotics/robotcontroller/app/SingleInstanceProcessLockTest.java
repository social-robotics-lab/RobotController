package org.socialrobotics.robotcontroller.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.util.concurrent.TimeUnit;

import org.junit.Test;

public final class SingleInstanceProcessLockTest {
    @Test
    public void competingAcquisitionFailsClosedAndReleaseAllowsReacquisition()
            throws Exception {
        Path directory = Files.createTempDirectory("robot-controller-lock-test-");
        Path path = directory.resolve("controller.lock");
        SingleInstanceProcessLock first = SingleInstanceProcessLock.acquire(path);
        try {
            assertEquals(path.toAbsolutePath().normalize(), first.path());
            try {
                SingleInstanceProcessLock.acquire(path);
                fail("expected process-lock competition");
            } catch (ProcessLockException expected) {
                assertTrue(expected.getMessage().contains(path.toString()));
            }
        } finally {
            first.close();
            first.close();
        }

        SingleInstanceProcessLock reacquired = SingleInstanceProcessLock.acquire(path);
        reacquired.close();
    }

    @Test
    public void missingParentDirectoryFailsWithoutCreatingIt() throws Exception {
        Path directory = Files.createTempDirectory("robot-controller-lock-parent-test-");
        Path missing = directory.resolve("missing");
        Path path = missing.resolve("controller.lock");

        try {
            SingleInstanceProcessLock.acquire(path);
            fail("expected process-lock open failure");
        } catch (ProcessLockException expected) {
            assertTrue(expected.getMessage().contains(path.toString()));
        }
        assertTrue(!Files.exists(missing));
    }

    @Test
    public void separateJvmProcessPreventsCompetingAcquisition() throws Exception {
        Path path = Files.createTempDirectory("robot-controller-cross-process-lock-test-")
                .resolve("controller.lock");
        String javaExecutable = System.getProperty("os.name").startsWith("Windows")
                ? "java.exe"
                : "java";
        Process holder = new ProcessBuilder(
                Paths.get(System.getProperty("java.home"), "bin", javaExecutable).toString(),
                "-cp",
                System.getProperty("java.class.path"),
                LockHolderMain.class.getName(),
                path.toString())
                .redirectErrorStream(true)
                .start();
        BufferedReader output = new BufferedReader(
                new InputStreamReader(holder.getInputStream(), "UTF-8"));
        PrintWriter input = new PrintWriter(
                new OutputStreamWriter(holder.getOutputStream(), "UTF-8"), true);
        try {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5L);
            while (!output.ready()) {
                if (!holder.isAlive() || System.nanoTime() >= deadline) {
                    fail("lock-holder JVM did not become ready");
                }
                Thread.yield();
            }
            assertEquals("locked", output.readLine());

            try {
                SingleInstanceProcessLock.acquire(path);
                fail("expected cross-process lock competition");
            } catch (ProcessLockException expected) {
                assertTrue(expected.getMessage().contains(path.toString()));
            }
        } finally {
            input.println("release");
            if (!holder.waitFor(5L, TimeUnit.SECONDS)) {
                holder.destroy();
                holder.waitFor(5L, TimeUnit.SECONDS);
            }
        }
        assertEquals(0, holder.exitValue());

        SingleInstanceProcessLock reacquired = SingleInstanceProcessLock.acquire(path);
        reacquired.close();
    }

    /** Separate-JVM fixture used to verify the operating system lock boundary. */
    public static final class LockHolderMain {
        private LockHolderMain() {
        }

        public static void main(String[] arguments) throws Exception {
            SingleInstanceProcessLock lock = SingleInstanceProcessLock.acquire(
                    Paths.get(arguments[0]));
            try {
                System.out.println("locked");
                System.out.flush();
                new BufferedReader(new InputStreamReader(System.in, "UTF-8")).readLine();
            } finally {
                lock.close();
            }
        }
    }
}
