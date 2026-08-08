import java.awt.Color;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.Map;

import jp.vstone.RobotLib.CRobotMem;
import jp.vstone.RobotLib.CRobotPose;
import jp.vstone.RobotLib.CSotaMotion;

/**
 * Human-operated, bounded diagnostic for VSTONE Sota Manual Gate 1.
 *
 * <p>This class is intentionally outside the production Maven reactor. It must
 * be compiled with an operator-provided official VSTONE runtime and must never
 * be executed by CI or an automated agent.</p>
 */
public final class VstoneGate1Probe {
    private static final String SERVO_GUARD_KEY = "VSTONE_GATE1_SERVO_GUARD";
    private static final String LED_TEST_KEY = "VSTONE_GATE1_LED_TEST";
    private static final int TRANSITION_MSEC = 1000;
    private static final int RATE_DURATION_MSEC = 2000;
    private static final Color TEST_EYE_COLOR = Color.BLACK;
    private static final Color TEST_POWER_COLOR = Color.BLACK;

    private final BufferedReader console;
    private final LedLevels levels;

    private CRobotMem memory;
    private CSotaMotion motion;
    private Byte[] servoIds;

    private boolean connectionAttempted;
    private boolean connected;
    private boolean initialized;
    private boolean servoGuardAcquired;
    private boolean guardAcquisitionFailed;
    private boolean poseInspectionCompleted;
    private boolean firstSingleUpdateExecuted;
    private boolean gate1A1Passed;
    private boolean brightnessStepsCompleted;
    private boolean gate1APassed;
    private boolean voiceSyncDisableAttemptedByProbe;
    private boolean voiceSyncNeedsRestore;
    private boolean voiceSyncManualUpdateExecuted;
    private boolean gate1BPassed;
    private boolean rate10Executed;
    private boolean rate20Executed;
    private boolean rate25Executed;
    private boolean anyLedPlayAttempted;
    private boolean furtherLedPlaySuppressed;
    private boolean abortRequested;
    private boolean cleanupCompleted;

    private VstoneGate1Probe(BufferedReader console, LedLevels levels) {
        this.console = console;
        this.levels = levels;
    }

    /**
     * Starts the interactive diagnostic. Invalid or missing LED levels exit
     * before any VSTONE object is constructed.
     *
     * @param args four operator-approved integer levels: ZERO LOW MEDIUM HIGH
     */
    public static void main(String[] args) {
        LedLevels levels = LedLevels.parse(args);
        if (levels == null) {
            return;
        }

        BufferedReader console = new BufferedReader(new InputStreamReader(System.in));
        VstoneGate1Probe probe = new VstoneGate1Probe(console, levels);
        try {
            probe.runInteractive();
        } catch (Throwable failure) {
            System.err.println("ABORT: unexpected probe failure: " + describe(failure));
        } finally {
            probe.cleanup();
        }
    }

    private void runInteractive() throws IOException {
        printBanner();
        while (!abortRequested) {
            printMenu();
            String command = readTrimmedLine("Select: ");
            if (command == null || "q".equalsIgnoreCase(command)) {
                System.out.println("Quit requested; running best-effort cleanup.");
                return;
            }
            if ("c".equalsIgnoreCase(command)) {
                System.out.println("Cleanup requested.");
                return;
            }

            try {
                if ("1".equals(command)) {
                    initialize();
                } else if ("2".equals(command)) {
                    acquireServoGuard();
                } else if ("3".equals(command)) {
                    inspectLedOnlyPose();
                } else if ("4".equals(command)) {
                    executeFirstSingleUpdate();
                } else if ("5".equals(command)) {
                    executeBrightnessSteps();
                } else if ("6".equals(command)) {
                    disableVoiceSync();
                } else if ("7".equals(command)) {
                    executeVoiceSyncManualUpdate();
                } else if ("8".equals(command)) {
                    enableVoiceSyncAndRecordGate();
                } else if ("9".equals(command)) {
                    executeRateTest();
                } else {
                    System.out.println("Unknown selection; no operation performed.");
                }
            } catch (ProbeAbortException failure) {
                requestAbort(failure.getMessage());
            } catch (Throwable failure) {
                requestAbort("operation failed: " + describe(failure));
            }
        }
    }

    private void printBanner() {
        System.out.println("VSTONE Gate 1 guarded manual diagnostic");
        System.out.println();
        System.out.println("Servo write guard: not acquired");
        System.out.println("No hardware write has been performed.");
        System.out.println("This probe does not automatically determine physical safety.");
        System.out.println("Operator must report whether ANY servo movement occurs.");
        System.out.println();
        System.out.println("Operator-approved mouth levels:");
        System.out.println("  ZERO=" + levels.zero);
        System.out.println("  LOW=" + levels.low);
        System.out.println("  MEDIUM=" + levels.medium);
        System.out.println("  HIGH=" + levels.high);
        System.out.println("Known requested eye/power test state: Color.BLACK");
        System.out.println("Transition: " + TRANSITION_MSEC + " ms");
    }

    private void printMenu() {
        System.out.println();
        System.out.println("1 - initialize/connect (no LED play)");
        System.out.println("2 - acquire all-default-servo guard (no LED play)");
        System.out.println("3 - prepare LED-only pose and inspect (no play)");
        System.out.println("4 - Gate 1A-1: execute ONE low LED update");
        System.out.println("5 - Gate 1A-2: operator-stepped brightness sequence");
        System.out.println("6 - Gate 1B: disable native voice sync");
        System.out.println("7 - Gate 1B: execute ONE update while sync is disabled");
        System.out.println("8 - Gate 1B: enable sync and record manual result");
        System.out.println("9 - Gate 1C: bounded 10/20/25 Hz test");
        System.out.println("c - cleanup and quit");
        System.out.println("q - quit through cleanup");
        System.out.println("State: initialized=" + initialized
                + ", servoGuard=" + servoGuardAcquired
                + ", Gate1A=" + gate1APassed
                + ", Gate1B=" + gate1BPassed);
    }

    private void initialize() throws IOException, ProbeAbortException {
        require(!initialized, "already initialized");
        require(!guardAcquisitionFailed, "servo guard previously failed; restart the probe");

        System.out.println();
        System.out.println("INITIALIZATION PREFLIGHT");
        System.out.println("Initialization may have undocumented hardware side effects.");
        System.out.println("Confirm stable placement, clear joints, no competing robot process,");
        System.out.println("immediate stop readiness, and reviewed official LED levels.");
        String approval = readTrimmedLine("Type READY to connect/init, or q to abort: ");
        require("READY".equals(approval), "initialization not approved by operator");

        memory = new CRobotMem();
        motion = new CSotaMotion(memory);
        connectionAttempted = true;
        boolean connectResult = memory.Connect();
        require(connectResult, "CRobotMem.Connect returned false");
        connected = true;

        boolean initResult = motion.InitRobot_Sota();
        require(initResult, "CSotaMotion.InitRobot_Sota returned false");
        initialized = true;
        System.out.println("Initialization completed. No LED play was requested.");
        System.out.println("Operator: record any unexpected physical state change now.");
    }

    private void acquireServoGuard() throws ProbeAbortException, IOException {
        requireInitialized();
        require(!servoGuardAcquired, "servo guard is already acquired");
        require(!guardAcquisitionFailed, "servo guard previously failed; restart the probe");

        Byte[] discovered = motion.getDefaultIDs();
        validateServoIds(discovered);
        servoIds = discovered.clone();

        System.out.println("Default servo IDs validated; count=" + servoIds.length);
        System.out.println("No LED operation will occur in Gate 1A-0.");
        requirePressEnter("Press ENTER to acquire the all-default-servo guard, or q to abort: ");

        boolean locked = motion.LockServoHandle(SERVO_GUARD_KEY, servoIds);
        if (!locked) {
            guardAcquisitionFailed = true;
            throw new ProbeAbortException(
                    "LockServoHandle returned false; no LED operation is permitted");
        }
        servoGuardAcquired = true;
        System.out.println("Gate 1A-0 servo guard ACQUIRED.");
        System.out.println("Guard key: " + SERVO_GUARD_KEY);
    }

    private void inspectLedOnlyPose() throws ProbeAbortException {
        requireWriteGuard();
        CRobotPose pose = createCheckedLedPose(levels.low);
        printPoseMaps(pose);
        poseInspectionCompleted = true;
        System.out.println("Structural inspection completed. play() was not called.");
    }

    private void executeFirstSingleUpdate()
            throws ProbeAbortException, IOException {
        requireWriteGuard();
        require(poseInspectionCompleted, "run option 3 before the first LED update");
        require(!firstSingleUpdateExecuted, "the first single update is intentionally one-shot");

        boolean played = performOneLedPlay(
                levels.low,
                "Gate 1A-1 ONE low LED-only update",
                true);
        firstSingleUpdateExecuted = true;
        require(played, "Gate 1A-1 play returned false");

        if (askYesNo("Operator: was ANY servo movement observed? [yes/no]: ")) {
            suppressLedPlayAfterMovement();
            throw new ProbeAbortException("servo movement observed; all later gates are prohibited");
        }
        gate1A1Passed = askYesNo(
                "Operator: confirm Gate 1A-1 observation PASS? [yes/no]: ");
        require(gate1A1Passed, "operator did not confirm Gate 1A-1 PASS");
    }

    private void executeBrightnessSteps()
            throws ProbeAbortException, IOException {
        require(gate1A1Passed, "Gate 1A-1 must PASS before brightness steps");
        require(!brightnessStepsCompleted, "brightness sequence is intentionally one-shot");

        int[] sequence = new int[] {
            levels.zero, levels.low, levels.medium, levels.high, levels.zero
        };
        String[] names = new String[] {"ZERO", "LOW", "MEDIUM", "HIGH", "ZERO"};
        for (int index = 0; index < sequence.length; index++) {
            boolean played = performOneLedPlay(
                    sequence[index],
                    "Gate 1A-2 step " + (index + 1) + "/" + sequence.length
                            + " " + names[index],
                    true);
            require(played, "brightness step play returned false");
            if (askYesNo("Operator: was ANY servo movement observed? [yes/no]: ")) {
                suppressLedPlayAfterMovement();
                throw new ProbeAbortException(
                        "servo movement observed during brightness steps");
            }
        }

        brightnessStepsCompleted = true;
        gate1APassed = askYesNo("Operator: confirm complete Gate 1A PASS? [yes/no]: ");
        require(gate1APassed, "operator did not confirm Gate 1A PASS");
    }

    private void disableVoiceSync() throws ProbeAbortException, IOException {
        require(gate1APassed, "Gate 1A must PASS before native voice-sync testing");
        requireWriteGuard();
        require(!voiceSyncDisableAttemptedByProbe,
                "voice-sync disable has already been attempted by this probe");

        System.out.println("The public API has no current-state getter.");
        System.out.println("The probe cannot know whether voice sync was already disabled.");
        requirePressEnter("Press ENTER to attempt disable once, or q to abort: ");
        voiceSyncDisableAttemptedByProbe = true;
        voiceSyncNeedsRestore = true;
        motion.disabeMouthLEDVoiceSync();
        System.out.println("Disable call returned normally; hardware state is not auto-verified.");
    }

    private void executeVoiceSyncManualUpdate()
            throws ProbeAbortException, IOException {
        require(voiceSyncNeedsRestore,
                "this probe must attempt voice-sync disable before the manual update");
        require(!voiceSyncManualUpdateExecuted,
                "voice-sync manual observation update is intentionally one-shot");

        boolean played = performOneLedPlay(
                levels.low,
                "Gate 1B ONE manual update while sync disable is requested",
                true);
        require(played, "Gate 1B manual update play returned false");
        voiceSyncManualUpdateExecuted = true;
        if (askYesNo("Operator: was ANY servo movement observed? [yes/no]: ")) {
            suppressLedPlayAfterMovement();
            throw new ProbeAbortException("servo movement observed during Gate 1B");
        }
        System.out.println("Operator: record whether native voice sync overwrote the mouth state.");
    }

    private void enableVoiceSyncAndRecordGate()
            throws ProbeAbortException, IOException {
        requireWriteGuard();
        require(voiceSyncDisableAttemptedByProbe,
                "this probe has not attempted voice-sync disable");
        require(voiceSyncManualUpdateExecuted,
                "execute the one-shot manual update before restore");
        require(voiceSyncNeedsRestore, "voice-sync restore is not currently pending");

        requirePressEnter("Press ENTER to attempt configured enable, or q to abort: ");
        motion.enabeMouthLEDVoiceSync();
        voiceSyncNeedsRestore = false;
        System.out.println("Enable call returned normally.");
        System.out.println("This is a configured enable attempt, not proof of original-state restore.");
        gate1BPassed = askYesNo("Operator: confirm Gate 1B observation PASS? [yes/no]: ");
        require(gate1BPassed, "operator did not confirm Gate 1B PASS");
    }

    private void executeRateTest() throws ProbeAbortException, IOException {
        require(gate1APassed, "Gate 1A must PASS before rate testing");
        require(gate1BPassed, "Gate 1B must PASS before rate testing");
        requireWriteGuard();

        String selection = readTrimmedLine("Select exactly 10, 20, or 25 Hz (q aborts): ");
        if ("q".equalsIgnoreCase(selection)) {
            throw new ProbeAbortException("rate test aborted by operator");
        }
        int hz;
        try {
            hz = Integer.parseInt(selection);
        } catch (NumberFormatException invalid) {
            throw new ProbeAbortException("invalid rate selection");
        }
        require(hz == 10 || hz == 20 || hz == 25,
                "only 10, 20, and 25 Hz are implemented");
        require(!wasRateExecuted(hz),
                "the selected rate is intentionally limited to one session per process");

        int maximumUpdates = hz * RATE_DURATION_MSEC / 1000;
        System.out.println("Bounded rate session: " + hz + " Hz, "
                + RATE_DURATION_MSEC + " ms, at most " + maximumUpdates + " updates.");
        System.out.println("This is a requested target rate, not a hardware timing guarantee.");
        printStaticGuardSummary();
        requirePressEnter("Press ENTER to start this bounded session, or q to abort: ");
        markRateExecuted(hz);

        int requested = 0;
        int successful = 0;
        int failed = 0;
        long started = System.nanoTime();
        long periodNanos = 1_000_000_000L / hz;
        long nextDeadline = started;
        try {
            for (int index = 0; index < maximumUpdates; index++) {
                int mouth = (index & 1) == 0 ? levels.low : levels.zero;
                requested++;
                boolean played = performOneLedPlay(
                        mouth,
                        "Gate 1C " + hz + " Hz update " + (index + 1),
                        false);
                if (played) {
                    successful++;
                } else {
                    failed++;
                    break;
                }

                nextDeadline += periodNanos;
                long remaining = nextDeadline - System.nanoTime();
                if (remaining > 0L) {
                    long sleepMillis = remaining / 1_000_000L;
                    int sleepNanos = (int) (remaining % 1_000_000L);
                    try {
                        Thread.sleep(sleepMillis, sleepNanos);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        System.err.println("Rate session interrupted; stopping bounded loop.");
                        break;
                    }
                }
            }
        } finally {
            try {
                performOneLedPlay(levels.zero, "Gate 1C final mouth zero", false);
            } catch (Throwable cleanupFailure) {
                System.err.println("Rate-session zero failed: " + describe(cleanupFailure));
            }
        }

        long elapsedMillis = (System.nanoTime() - started) / 1_000_000L;
        System.out.println("Rate result: requested=" + requested
                + ", successful=" + successful
                + ", failed=" + failed
                + ", elapsedMs=" + elapsedMillis);
        System.out.println("Operator: confirm whether ANY servo movement was observed.");
        if (askYesNo("Was ANY servo movement observed? [yes/no]: ")) {
            suppressLedPlayAfterMovement();
            throw new ProbeAbortException("servo movement observed during rate testing");
        }
    }

    private boolean performOneLedPlay(int mouth, String label, boolean requireOperatorEnter)
            throws ProbeAbortException, IOException {
        requireWriteGuard();
        CRobotPose pose = createCheckedLedPose(mouth);
        System.out.println();
        System.out.println(label);
        printHardChecks(pose);
        if (requireOperatorEnter) {
            requirePressEnter("Press ENTER to execute once, or q to abort: ");
        }

        validateImmediatelyBeforePlay(pose);
        anyLedPlayAttempted = true;
        boolean result = motion.play(pose, TRANSITION_MSEC, LED_TEST_KEY);
        System.out.println("play() return: " + result);
        return result;
    }

    private CRobotPose createCheckedLedPose(int mouth) throws ProbeAbortException {
        CRobotPose pose = new CRobotPose();
        requireEmptyStructuralMaps(pose, "before setLED_Sota");
        pose.setLED_Sota(TEST_EYE_COLOR, TEST_EYE_COLOR, mouth, TEST_POWER_COLOR);
        requireEmptyStructuralMaps(pose, "after setLED_Sota");
        Map<Byte, Short> led = pose.getLed();
        require(led != null && !led.isEmpty(),
                "ABORT: LED pose contains no LED data after setLED_Sota");
        return pose;
    }

    private void validateImmediatelyBeforePlay(CRobotPose pose)
            throws ProbeAbortException {
        requireWriteGuard();
        requireEmptyStructuralMaps(pose, "immediately before play");
        Map<Byte, Short> led = pose.getLed();
        require(led != null && !led.isEmpty(),
                "ABORT: LED map is empty immediately before play");
    }

    private void requireEmptyStructuralMaps(CRobotPose pose, String stage)
            throws ProbeAbortException {
        Map<Byte, Short> servo = pose.getPose();
        Map<Byte, Short> torque = pose.getTorque();
        require(servo != null && servo.isEmpty(),
                "ABORT: LED pose unexpectedly contains servo data " + stage);
        require(torque != null && torque.isEmpty(),
                "ABORT: LED pose unexpectedly contains torque data " + stage);
    }

    private void printHardChecks(CRobotPose pose) throws ProbeAbortException {
        Map<Byte, Short> servo = pose.getPose();
        Map<Byte, Short> torque = pose.getTorque();
        Map<Byte, Short> led = pose.getLed();
        System.out.println("About to perform ONE LED-only play()");
        System.out.println("Servo guard: " + (servoGuardAcquired ? "ACQUIRED" : "NOT ACQUIRED"));
        System.out.println("Servo guard key: " + SERVO_GUARD_KEY);
        System.out.println("Play key: " + LED_TEST_KEY);
        System.out.println("Keys different: "
                + (!SERVO_GUARD_KEY.equals(LED_TEST_KEY) ? "YES" : "NO"));
        System.out.println("Servo map size: " + sizeOrMinusOne(servo));
        System.out.println("Torque map size: " + sizeOrMinusOne(torque));
        System.out.println("LED map size: " + sizeOrMinusOne(led));
        System.out.println("Servo power methods called by probe: NO");
        System.out.println("Operator must visually monitor the robot.");
        validateImmediatelyBeforePlay(pose);
    }

    private void printPoseMaps(CRobotPose pose) {
        System.out.println("Servo map size: " + sizeOrMinusOne(pose.getPose()));
        System.out.println("Torque map size: " + sizeOrMinusOne(pose.getTorque()));
        System.out.println("LED map size: " + sizeOrMinusOne(pose.getLed()));
    }

    private void printStaticGuardSummary() {
        System.out.println("Servo guard: " + (servoGuardAcquired ? "ACQUIRED" : "NOT ACQUIRED"));
        System.out.println("Servo guard key: " + SERVO_GUARD_KEY);
        System.out.println("Play key: " + LED_TEST_KEY);
        System.out.println("Keys different: " + !SERVO_GUARD_KEY.equals(LED_TEST_KEY));
        System.out.println("Each update creates and structurally checks a new LED-only pose.");
    }

    private void validateServoIds(Byte[] ids) throws ProbeAbortException {
        require(ids != null, "getDefaultIDs returned null");
        require(ids.length > 0, "getDefaultIDs returned an empty array");
        for (int index = 0; index < ids.length; index++) {
            require(ids[index] != null, "getDefaultIDs contained null at index " + index);
        }
    }

    private void requireInitialized() throws ProbeAbortException {
        require(initialized && connected && memory != null && motion != null,
                "initialize/connect must succeed first");
    }

    private void requireWriteGuard() throws ProbeAbortException {
        requireInitialized();
        require(!guardAcquisitionFailed, "servo guard acquisition previously failed");
        require(servoGuardAcquired, "all-default-servo guard is not acquired");
        require(!furtherLedPlaySuppressed,
                "further LED play is suppressed after observed servo movement");
        validateServoIds(servoIds);
        require(!SERVO_GUARD_KEY.equals(LED_TEST_KEY),
                "servo guard key and LED play key must differ");
    }

    private void requirePressEnter(String prompt)
            throws IOException, ProbeAbortException {
        String line = readTrimmedLine(prompt);
        require(line != null && line.length() == 0,
                "operator did not approve this operation");
    }

    private boolean askYesNo(String prompt) throws IOException, ProbeAbortException {
        String value = readTrimmedLine(prompt);
        if ("yes".equalsIgnoreCase(value)) {
            return true;
        }
        if ("no".equalsIgnoreCase(value)) {
            return false;
        }
        throw new ProbeAbortException("expected an explicit yes or no response");
    }

    private String readTrimmedLine(String prompt) throws IOException {
        System.out.print(prompt);
        System.out.flush();
        String line = console.readLine();
        return line == null ? null : line.trim();
    }

    private void requestAbort(String reason) {
        abortRequested = true;
        System.err.println("ABORT: " + reason);
        System.err.println("No later Gate 1 operation is permitted in this process.");
    }

    private void suppressLedPlayAfterMovement() {
        furtherLedPlaySuppressed = true;
        System.err.println("Hard stop: cleanup will not issue another LED play after movement.");
    }

    private boolean wasRateExecuted(int hz) {
        if (hz == 10) {
            return rate10Executed;
        }
        if (hz == 20) {
            return rate20Executed;
        }
        return rate25Executed;
    }

    private void markRateExecuted(int hz) {
        if (hz == 10) {
            rate10Executed = true;
        } else if (hz == 20) {
            rate20Executed = true;
        } else {
            rate25Executed = true;
        }
    }

    private void cleanup() {
        if (cleanupCompleted) {
            return;
        }
        cleanupCompleted = true;
        System.out.println("Starting best-effort cleanup.");

        if (anyLedPlayAttempted
                && servoGuardAcquired
                && motion != null
                && !furtherLedPlaySuppressed) {
            try {
                performOneLedPlay(levels.zero, "Cleanup mouth zero", false);
            } catch (Throwable failure) {
                System.err.println("Cleanup mouth zero failed: " + describe(failure));
            }
        } else if (anyLedPlayAttempted && furtherLedPlaySuppressed) {
            System.err.println("Cleanup mouth zero skipped after observed servo movement.");
        }

        if (voiceSyncDisableAttemptedByProbe && voiceSyncNeedsRestore && motion != null) {
            try {
                motion.enabeMouthLEDVoiceSync();
                voiceSyncNeedsRestore = false;
                System.out.println("Cleanup configured voice-sync enable attempt completed.");
            } catch (Throwable failure) {
                System.err.println("Cleanup voice-sync enable failed: " + describe(failure));
            }
        }

        if (servoGuardAcquired && motion != null && servoIds != null) {
            try {
                motion.UnLockServoHandle(SERVO_GUARD_KEY, servoIds);
                servoGuardAcquired = false;
                System.out.println("Cleanup servo guard release completed.");
            } catch (Throwable failure) {
                System.err.println("Cleanup servo guard release failed: " + describe(failure));
            }
        }

        if (connectionAttempted && memory != null) {
            try {
                memory.Disconnect();
                connected = false;
                connectionAttempted = false;
                System.out.println("Cleanup disconnect completed.");
            } catch (Throwable failure) {
                System.err.println("Cleanup disconnect failed: " + describe(failure));
            }
        }
        System.out.println("Best-effort cleanup finished; verify physical state manually.");
    }

    private static int sizeOrMinusOne(Map<Byte, Short> map) {
        return map == null ? -1 : map.size();
    }

    private static void require(boolean condition, String message)
            throws ProbeAbortException {
        if (!condition) {
            throw new ProbeAbortException(message);
        }
    }

    private static String describe(Throwable failure) {
        String message = failure.getMessage();
        return failure.getClass().getName()
                + (message == null ? "" : ": " + message);
    }

    private static final class LedLevels {
        private final int zero;
        private final int low;
        private final int medium;
        private final int high;

        private LedLevels(int zero, int low, int medium, int high) {
            this.zero = zero;
            this.low = low;
            this.medium = medium;
            this.high = high;
        }

        private static LedLevels parse(String[] args) {
            if (args == null || args.length != 4) {
                printUsage();
                return null;
            }
            int[] values = new int[4];
            for (int index = 0; index < args.length; index++) {
                try {
                    values[index] = Integer.parseInt(args[index]);
                } catch (NumberFormatException invalid) {
                    System.err.println("Invalid integer LED level: " + args[index]);
                    printUsage();
                    return null;
                }
                if (values[index] < 0 || values[index] > 255) {
                    System.err.println("LED level outside guarded candidate range 0..255: "
                            + values[index]);
                    return null;
                }
            }
            if (!(values[0] < values[1]
                    && values[1] < values[2]
                    && values[2] < values[3])) {
                System.err.println("Require strictly increasing ZERO LOW MEDIUM HIGH levels.");
                return null;
            }
            if (values[0] != 0) {
                System.err.println("ZERO must be exactly 0 for guarded cleanup.");
                return null;
            }
            return new LedLevels(values[0], values[1], values[2], values[3]);
        }

        private static void printUsage() {
            System.err.println("Usage: VstoneGate1Probe <ZERO> <LOW> <MEDIUM> <HIGH>");
            System.err.println("Provide only values approved for the installed official runtime.");
            System.err.println("No VSTONE object is constructed when validation fails.");
        }
    }

    private static final class ProbeAbortException extends Exception {
        private static final long serialVersionUID = 1L;

        private ProbeAbortException(String message) {
            super(message);
        }
    }
}
