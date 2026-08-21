import java.awt.Color;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

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
    private boolean poseDiagnosticCompleted;
    private boolean firstSingleUpdateExecuted;
    private boolean gate1A1ServoSafetyPassed;
    private boolean gate1A1PlayReturned;
    private boolean gate1A1ServoMovementObserved;
    private boolean gate1A1MouthChanged;
    private boolean gate1A1EyeChanged;
    private boolean gate1A1PowerChanged;
    private boolean gate1A1UnexpectedServoSound;
    private String gate1A1EyeObservation;
    private String gate1A1PowerObservation;
    private boolean voiceSyncDisableAttemptedByProbe;
    private boolean voiceSyncDisableReturnedNormally;
    private boolean voiceSyncNeedsRestore;
    private boolean voiceSyncManualUpdateExecuted;
    private boolean gate1BManualPlayReturned;
    private boolean gate1BServoMovementObserved;
    private boolean gate1BUnexpectedServoSound;
    private boolean gate1BManualMouthChanged;
    private boolean gate1BEyeChanged;
    private boolean gate1BPowerChanged;
    private String gate1BEyeObservation;
    private String gate1BPowerObservation;
    private boolean voiceSyncEnableReturnedNormally;
    private boolean ledLockAttempted;
    private boolean ledLockAcquired;
    private Byte[] ledLockIds;
    private boolean ledLockUpdateExecuted;
    private boolean ledLockPlayReturned;
    private boolean ledLockServoMovementObserved;
    private boolean ledLockUnexpectedServoSound;
    private boolean ledLockMouthChanged;
    private boolean ledLockEyeChanged;
    private boolean ledLockPowerChanged;
    private String ledLockObservation;
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
                } else if ("6".equals(command)) {
                    disableVoiceSync();
                } else if ("7".equals(command)) {
                    executeVoiceSyncManualUpdate();
                } else if ("8".equals(command)) {
                    enableVoiceSyncAndRecordGate();
                } else if ("10".equals(command)) {
                    acquireLedLock();
                } else if ("11".equals(command)) {
                    executeLedLockSingleUpdate();
                } else if ("12".equals(command)) {
                    releaseLedLock();
                } else if (isTemporarilyBlockedOption(command)) {
                    reportTemporaryGateBlock(command);
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
        System.out.println("Probe source explicitly called ServoOn/ServoOff: NO");
        System.out.println("Vendor runtime shutdown hook behavior: may attempt ServoOff;"
                + " observed repeatedly during prior manual runs");
        System.out.println("Diagnostic checkpoint: options 4, 6, 7, 10, 11, 12, and 8"
                + " are bounded;"
                + " options 5 and 9 are blocked.");
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
        System.out.println("3 - inspect CRobotPose structure before/after setLED_Sota (NO play)");
        System.out.println("4 - Gate 1A-1: execute ONE low LED update");
        System.out.println("5 - BLOCKED: Gate 1A-2 brightness sequence");
        System.out.println("6 - Gate 1B: request native mouth voice-sync disable ONCE");
        System.out.println("7 - Gate 1B: execute ONE low LED update after disable request");
        System.out.println("8 - Gate 1B: request native mouth voice-sync enable ONCE"
                + " (after option 12 for Gate 1L)");
        System.out.println("9 - BLOCKED: Gate 1C rate test");
        System.out.println("10 - Gate 1L: acquire derived setLED_Sota LED lock");
        System.out.println("11 - Gate 1L: execute ONE low LED update while lock is held");
        System.out.println("12 - Gate 1L: release the acquired LED lock");
        System.out.println("c - cleanup and quit");
        System.out.println("q - quit through cleanup");
        System.out.println("State: initialized=" + initialized
                + ", servoGuard=" + servoGuardAcquired
                + ", poseDiagnostic=" + poseDiagnosticCompleted
                + ", Gate1A1ServoSafety=" + gate1A1ServoSafetyPassed
                + ", Gate1A1MouthChanged=" + gate1A1MouthChanged
                + ", voiceSyncDisableAttempted=" + voiceSyncDisableAttemptedByProbe
                + ", voiceSyncRestorePending=" + voiceSyncNeedsRestore
                + ", Gate1BManualUpdate=" + voiceSyncManualUpdateExecuted
                + ", ledLockAttempted=" + ledLockAttempted
                + ", ledLockAcquired=" + ledLockAcquired
                + ", Gate1LLockUpdate=" + ledLockUpdateExecuted);
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
        require(!poseDiagnosticCompleted,
                "CRobotPose diagnostic is intentionally one-shot in this process");

        CRobotPose pose = new CRobotPose();
        Map<Byte, Short> servoBefore = snapshotMap(pose.getPose());
        Map<Byte, Short> torqueBefore = snapshotMap(pose.getTorque());
        Map<Byte, Short> ledBefore = snapshotMap(pose.getLed());

        System.out.println();
        System.out.println("BEFORE setLED_Sota");
        printNamedMap("Servo", servoBefore);
        printNamedMap("Torque", torqueBefore);
        printNamedMap("LED", ledBefore);

        pose.setLED_Sota(TEST_EYE_COLOR, TEST_EYE_COLOR, levels.low, TEST_POWER_COLOR);

        Map<Byte, Short> servoAfter = snapshotMap(pose.getPose());
        Map<Byte, Short> torqueAfter = snapshotMap(pose.getTorque());
        Map<Byte, Short> ledAfter = snapshotMap(pose.getLed());

        System.out.println();
        System.out.println("AFTER setLED_Sota");
        printNamedMap("Servo", servoAfter);
        printNamedMap("Torque", torqueAfter);
        printNamedMap("LED", ledAfter);

        System.out.println();
        printMapComparison("Servo", servoBefore, servoAfter);
        printMapComparison("Torque", torqueBefore, torqueAfter);
        printMapComparison("LED", ledBefore, ledAfter);

        poseDiagnosticCompleted = true;
        System.out.println();
        System.out.println("NO play() was called.");
        System.out.println("No LED, servo, or torque hardware write was requested by option 3.");
        System.out.println("Option 3 diagnostic completed.");
        System.out.println("Option 4 is the first enabled hardware-write gate in this revision.");
    }

    private void executeFirstSingleUpdate()
            throws ProbeAbortException, IOException {
        requireWriteGuard();
        require(poseDiagnosticCompleted, "run option 3 before the first LED update");
        require(!firstSingleUpdateExecuted, "the first single update is intentionally one-shot");

        boolean played = performOneLedPlay(
                levels.low,
                "Gate 1A-1 ONE low LED-only update",
                true);
        firstSingleUpdateExecuted = true;
        gate1A1PlayReturned = played;

        gate1A1ServoMovementObserved = askYesNo(
                "Operator: Was ANY servo movement observed? [yes/no]: ");
        if (gate1A1ServoMovementObserved) {
            suppressFurtherLedPlay("observed servo movement");
            System.err.println("Gate 1A-1 FAIL");
            throw new ProbeAbortException("servo movement observed; all later gates are prohibited");
        }

        gate1A1UnexpectedServoSound = askYesNo(
                "Operator: Was ANY unexpected servo sound heard? [yes/no]: ");
        if (gate1A1UnexpectedServoSound) {
            suppressFurtherLedPlay("unexpected servo sound");
            System.err.println("Gate 1A-1 FAIL");
            throw new ProbeAbortException(
                    "unexpected servo sound observed; all later LED plays are prohibited");
        }

        gate1A1ServoSafetyPassed = true;
        gate1A1MouthChanged = askYesNo(
                "Operator: Did the mouth LED visibly change? [yes/no]: ");
        gate1A1EyeChanged = askYesNo(
                "Operator: Did either eye LED visibly change? [yes/no]: ");
        gate1A1PowerChanged = askYesNo(
                "Operator: Did the power LED visibly change? [yes/no]: ");
        gate1A1EyeObservation = askObservation(
                "Operator: optional eye LED observation (ENTER for empty): ");
        gate1A1PowerObservation = askObservation(
                "Operator: optional power LED observation (ENTER for empty): ");

        System.out.println("Gate 1A-1 observations:");
        System.out.println("  play() returned true: " + yesNo(gate1A1PlayReturned));
        System.out.println("  servo movement: NO");
        System.out.println("  unexpected servo sound: NO");
        System.out.println("  mouth visibly changed: " + yesNo(gate1A1MouthChanged));
        System.out.println("  either eye visibly changed: " + yesNo(gate1A1EyeChanged));
        System.out.println("  power visibly changed: " + yesNo(gate1A1PowerChanged));
        System.out.println("  eye note: " + printableObservation(gate1A1EyeObservation));
        System.out.println("  power note: " + printableObservation(gate1A1PowerObservation));
        System.out.println("Gate 1A-1 servo safety: PASS (operator observation only).");
        if (gate1A1MouthChanged) {
            System.out.println("Gate 1A-1 mouth response: OBSERVED CHANGE.");
        } else {
            System.out.println("Gate 1A-1 mouth response: NO VISIBLE CHANGE;"
                    + " mouth control is NOT CONFIRMED.");
        }
        System.out.println("Gate 1A overall remains NOT PASSED; option 5 stays blocked.");
        require(played, "Gate 1A-1 play returned false; no retry is permitted");
        System.out.println("Next approved step: option 6 only.");
    }

    private void disableVoiceSync() throws ProbeAbortException, IOException {
        requireWriteGuard();
        require(poseDiagnosticCompleted, "run option 3 before Gate 1B");
        require(firstSingleUpdateExecuted,
                "execute the Gate 1A-1 single update before Gate 1B");
        require(gate1A1ServoSafetyPassed,
                "Gate 1A-1 servo safety observation must PASS before Gate 1B");
        require(!voiceSyncDisableAttemptedByProbe,
                "voice-sync disable has already been attempted by this probe");

        System.out.println("GATE 1B NATIVE MOUTH VOICE-SYNC DISABLE WARNING");
        System.out.println("This calls motion.disabeMouthLEDVoiceSync() exactly once.");
        System.out.println("The public API has no current-state getter.");
        System.out.println("The probe cannot know the original voice-sync state.");
        System.out.println("No play(), LED lock, or direct LED-ID write occurs in option 6.");
        System.out.println("Cleanup will request configured enable if restoration remains pending.");
        System.out.println("A later enable call is not proof that the original state was restored.");
        requirePressEnter("Press ENTER to attempt native voice-sync disable once, or q to abort: ");
        voiceSyncDisableAttemptedByProbe = true;
        voiceSyncNeedsRestore = true;
        motion.disabeMouthLEDVoiceSync();
        voiceSyncDisableReturnedNormally = true;
        System.out.println("Disable call returned normally; actual hardware state remains unverified.");
        System.out.println("Next approved step: option 7 only.");
    }

    private void executeVoiceSyncManualUpdate()
            throws ProbeAbortException, IOException {
        requireWriteGuard();
        require(gate1A1ServoSafetyPassed,
                "Gate 1A-1 servo safety observation must PASS before Gate 1B");
        require(voiceSyncDisableAttemptedByProbe,
                "this probe must attempt voice-sync disable before the manual update");
        require(voiceSyncDisableReturnedNormally,
                "voice-sync disable did not return normally");
        require(voiceSyncNeedsRestore,
                "this probe must attempt voice-sync disable before the manual update");
        require(!voiceSyncManualUpdateExecuted,
                "voice-sync manual observation update is intentionally one-shot");

        boolean played = performOneLedPlay(
                levels.low,
                "Gate 1B ONE manual update while sync disable is requested",
                true,
                true);
        voiceSyncManualUpdateExecuted = true;
        gate1BManualPlayReturned = played;

        gate1BServoMovementObserved = askYesNo(
                "Operator: Was ANY servo movement observed? [yes/no]: ");
        if (gate1BServoMovementObserved) {
            suppressFurtherLedPlay("observed servo movement");
            throw new ProbeAbortException("servo movement observed during Gate 1B");
        }

        gate1BUnexpectedServoSound = askYesNo(
                "Operator: Was ANY unexpected servo sound heard? [yes/no]: ");
        if (gate1BUnexpectedServoSound) {
            suppressFurtherLedPlay("unexpected servo sound");
            throw new ProbeAbortException("unexpected servo sound observed during Gate 1B");
        }

        gate1BManualMouthChanged = askYesNo(
                "Operator: Did the mouth LED visibly change? [yes/no]: ");
        gate1BEyeChanged = askYesNo(
                "Operator: Did either eye LED visibly change? [yes/no]: ");
        gate1BPowerChanged = askYesNo(
                "Operator: Did the power LED visibly change? [yes/no]: ");
        gate1BEyeObservation = askObservation(
                "Operator: optional eye LED observation (ENTER for empty): ");
        gate1BPowerObservation = askObservation(
                "Operator: optional power LED observation (ENTER for empty): ");

        System.out.println("Gate 1B manual-update observations:");
        System.out.println("  play() returned true: " + yesNo(gate1BManualPlayReturned));
        System.out.println("  servo movement: NO");
        System.out.println("  unexpected servo sound: NO");
        System.out.println("  mouth visibly changed: " + yesNo(gate1BManualMouthChanged));
        System.out.println("  either eye visibly changed: " + yesNo(gate1BEyeChanged));
        System.out.println("  power visibly changed: " + yesNo(gate1BPowerChanged));
        System.out.println("  eye note: " + printableObservation(gate1BEyeObservation));
        System.out.println("  power note: " + printableObservation(gate1BPowerObservation));
        if (gate1BManualMouthChanged || gate1BEyeChanged || gate1BPowerChanged) {
            System.out.println("A visible LED change after the disable request was observed,");
            System.out.println("but this alone does not prove native voice sync was the sole cause.");
        } else {
            System.out.println("No mouth/eye/power change was observed after the disable request.");
            System.out.println("LED ownership, locking, or commit behavior remains unresolved.");
        }
        require(played, "Gate 1B manual update play returned false; no retry is permitted");
        System.out.println("Next LED-lock diagnostic step: option 10.");
        System.out.println("Do NOT run option 8 yet when performing the LED-lock comparison.");
    }

    private void acquireLedLock() throws ProbeAbortException, IOException {
        requireWriteGuard();
        require(poseDiagnosticCompleted, "run option 3 before LED ownership testing");
        require(gate1A1ServoSafetyPassed,
                "Gate 1A-1 servo safety observation must PASS before LED ownership testing");
        require(voiceSyncDisableAttemptedByProbe,
                "voice-sync disable must be attempted before LED ownership testing");
        require(voiceSyncDisableReturnedNormally,
                "voice-sync disable must return normally before LED ownership testing");
        require(voiceSyncNeedsRestore,
                "voice-sync restore must remain pending during LED ownership testing");
        require(voiceSyncManualUpdateExecuted,
                "run option 7 as the no-LED-lock comparison baseline first");
        require(!gate1BServoMovementObserved,
                "servo movement was observed during the option 7 baseline");
        require(!gate1BUnexpectedServoSound,
                "unexpected servo sound was observed during the option 7 baseline");
        require(!ledLockAttempted, "LED lock acquisition is intentionally one-shot");
        require(!ledLockAcquired, "LED lock is already acquired");

        Byte[] discovered = discoverLedIdsFromCheckedPose();

        System.out.println();
        System.out.println("GATE 1 LED OWNERSHIP DIAGNOSTIC");
        System.out.println("Purpose:");
        System.out.println("  Acquire the LEDs represented by a fresh setLED_Sota() pose,");
        System.out.println("  using the same key later passed to play().");
        System.out.println("No play() will occur in this option.");
        System.out.println("Servo guard: ACQUIRED");
        System.out.println("Servo guard key: " + SERVO_GUARD_KEY);
        System.out.println("LED lock key: " + LED_TEST_KEY);
        System.out.println("Future play key: " + LED_TEST_KEY);
        System.out.println("Servo guard key differs from future play key: "
                + yesNo(!SERVO_GUARD_KEY.equals(LED_TEST_KEY)));
        System.out.println("Discovered LED IDs from pose.getLed(): "
                + formatLedIds(discovered));
        System.out.println("LED ID source: CRobotPose.setLED_Sota() -> getLed().keySet()");
        System.out.println("No numeric LED IDs are hard-coded by this probe.");
        requirePressEnter("Press ENTER to call LockLEDHandle() once. q aborts: ");

        ledLockAttempted = true;
        boolean locked = motion.LockLEDHandle(LED_TEST_KEY, discovered);
        System.out.println("LockLEDHandle returned: " + locked);
        if (!locked) {
            System.err.println("LED lock acquisition FAILED.");
            System.err.println("No LED play with LED-lock hypothesis will be attempted.");
            throw new ProbeAbortException("LockLEDHandle returned false; no retry is permitted");
        }

        ledLockIds = discovered.clone();
        ledLockAcquired = true;
        System.out.println("Gate 1 LED lock ACQUIRED with the future play key.");
        System.out.println("Next approved step: option 11 only.");
    }

    private void executeLedLockSingleUpdate()
            throws ProbeAbortException, IOException {
        requireWriteGuard();
        require(gate1A1ServoSafetyPassed,
                "Gate 1A-1 servo safety observation must PASS before LED ownership testing");
        require(voiceSyncDisableAttemptedByProbe,
                "voice-sync disable must be attempted before the LED-lock update");
        require(voiceSyncDisableReturnedNormally,
                "voice-sync disable must return normally before the LED-lock update");
        require(voiceSyncNeedsRestore,
                "voice-sync restore must remain pending during the LED-lock update");
        require(voiceSyncManualUpdateExecuted,
                "run option 7 as the no-LED-lock comparison baseline first");
        require(!gate1BServoMovementObserved,
                "servo movement was observed during the option 7 baseline");
        require(!gate1BUnexpectedServoSound,
                "unexpected servo sound was observed during the option 7 baseline");
        require(ledLockAttempted, "run option 10 before the LED-lock update");
        require(ledLockAcquired, "LED lock is not acquired");
        validateLedIds(ledLockIds);
        require(!ledLockUpdateExecuted,
                "the LED-lock diagnostic update is intentionally one-shot");

        boolean played = performOneLedPlay(
                levels.low,
                "Gate 1 LED-lock diagnostic ONE LOW update",
                true,
                true,
                ledLockIds);
        ledLockUpdateExecuted = true;
        ledLockPlayReturned = played;

        ledLockServoMovementObserved = askYesNo(
                "Operator: Was ANY servo movement observed? [yes/no]: ");
        if (ledLockServoMovementObserved) {
            suppressFurtherLedPlay("observed servo movement");
            System.err.println("SERVO SAFETY FAILURE");
            throw new ProbeAbortException(
                    "servo movement observed during the LED-lock diagnostic");
        }

        ledLockUnexpectedServoSound = askYesNo(
                "Operator: Was ANY unexpected servo sound heard? [yes/no]: ");
        if (ledLockUnexpectedServoSound) {
            suppressFurtherLedPlay("unexpected servo sound");
            System.err.println("SERVO SAFETY FAILURE");
            throw new ProbeAbortException(
                    "unexpected servo sound observed during the LED-lock diagnostic");
        }

        ledLockMouthChanged = askYesNo(
                "Operator: Did the mouth LED visibly change? [yes/no]: ");
        ledLockEyeChanged = askYesNo(
                "Operator: Did either eye LED visibly change? [yes/no]: ");
        ledLockPowerChanged = askYesNo(
                "Operator: Did the power LED visibly change? [yes/no]: ");
        ledLockObservation = askObservation(
                "Operator: optional LED observation (ENTER for empty): ");

        if (ledLockMouthChanged || ledLockEyeChanged || ledLockPowerChanged) {
            System.out.println("OBSERVED:");
            System.out.println("visible LED behavior changed after acquiring the"
                    + " setLED_Sota LED IDs");
            System.out.println("with the same key used for play().");
            System.out.println("This does not prove LockLEDHandle was the sole root cause.");
        } else {
            System.out.println("OBSERVED:");
            System.out.println("play() returned " + played + ", but no visible mouth/eye/power"
                    + " LED change occurred");
            System.out.println("while the derived LED ID set was locked with the play key.");
            System.out.println("LED lock alone did not make the manual LED update visible.");
            System.out.println("The four-argument play(..., ledposcheck) remains a potential"
                    + " later diagnostic only; it is not enabled here.");
        }

        printLedControlDiagnosticSummary();
        System.out.println("No retry is permitted, including when play() returned false.");
        System.out.println("Next approved step: option 12, regardless of visible result.");
    }

    private void releaseLedLock() throws ProbeAbortException, IOException {
        requireInitialized();
        require(ledLockAttempted, "this probe has not attempted LED lock acquisition");
        require(ledLockAcquired, "LED lock is not currently acquired");
        require(ledLockUpdateExecuted,
                "execute the one-shot LED-lock update before interactive release");
        validateLedIds(ledLockIds);

        System.out.println("LED lock key: " + LED_TEST_KEY);
        System.out.println("Locked LED IDs: " + formatLedIds(ledLockIds));
        requirePressEnter("Press ENTER to call UnLockLEDHandle() once. q aborts: ");
        motion.UnLockLEDHandle(LED_TEST_KEY, ledLockIds);
        ledLockAcquired = false;
        ledLockIds = null;
        System.out.println("LED lock release returned normally.");
        System.out.println("Next approved step: option 8 configured voice-sync enable.");
    }

    private void enableVoiceSyncAndRecordGate()
            throws ProbeAbortException, IOException {
        requireWriteGuard();
        require(voiceSyncDisableAttemptedByProbe,
                "this probe has not attempted voice-sync disable");
        require(voiceSyncManualUpdateExecuted,
                "execute the one-shot manual update before restore");
        require(voiceSyncNeedsRestore, "voice-sync restore is not currently pending");
        if (ledLockAttempted) {
            require(ledLockUpdateExecuted,
                    "complete option 11 before enabling voice sync");
            require(!ledLockAcquired,
                    "release the LED lock with option 12 before enabling voice sync");
        } else {
            System.out.println("LED-lock diagnostic was not started.");
            System.out.println("For the recommended comparison, use options 10, 11, and 12"
                    + " before option 8.");
        }

        requirePressEnter("Press ENTER to attempt configured enable, or q to abort: ");
        motion.enabeMouthLEDVoiceSync();
        voiceSyncEnableReturnedNormally = true;
        voiceSyncNeedsRestore = false;
        System.out.println("Enable call returned normally.");
        System.out.println("This is not proof that the original voice-sync state was restored.");
        printGate1ObservationSummary();
        System.out.println("Gate 1A overall remains NOT PASSED.");
        System.out.println("Gate 1B is an observation only; no broad PASS is assigned.");
        System.out.println("Options 5 and 9 remain blocked. Select c or q for cleanup, then STOP.");
    }

    private boolean performOneLedPlay(int mouth, String label, boolean requireOperatorEnter)
            throws ProbeAbortException, IOException {
        return performOneLedPlay(mouth, label, requireOperatorEnter, false, null);
    }

    private boolean performOneLedPlay(
            int mouth,
            String label,
            boolean requireOperatorEnter,
            boolean printVoiceSyncState)
            throws ProbeAbortException, IOException {
        return performOneLedPlay(
                mouth, label, requireOperatorEnter, printVoiceSyncState, null);
    }

    private boolean performOneLedPlay(
            int mouth,
            String label,
            boolean requireOperatorEnter,
            boolean printVoiceSyncState,
            Byte[] expectedLockedLedIds)
            throws ProbeAbortException, IOException {
        requireWriteGuard();
        CRobotPose pose = createCheckedLedPose(mouth);
        System.out.println();
        System.out.println(label);
        printHardChecks(pose, mouth);
        if (expectedLockedLedIds != null) {
            printLedLockChecks(pose, expectedLockedLedIds);
        }
        if (printVoiceSyncState) {
            System.out.println("Voice-sync disable attempted by probe: "
                    + yesNo(voiceSyncDisableAttemptedByProbe));
            System.out.println("Voice-sync disable returned normally: "
                    + yesNo(voiceSyncDisableReturnedNormally));
            System.out.println("Voice-sync restore pending: " + yesNo(voiceSyncNeedsRestore));
            System.out.println("Actual native voice-sync state: UNKNOWN (no public getter)");
        }
        if (requireOperatorEnter) {
            requirePressEnter(
                    "Press ENTER to execute exactly ONE play(). q aborts without play(): ");
        }

        validateImmediatelyBeforePlay(pose);
        if (expectedLockedLedIds != null) {
            requireLedIdSetsEqual(pose, expectedLockedLedIds);
        }
        anyLedPlayAttempted = true;
        boolean result = motion.play(pose, TRANSITION_MSEC, LED_TEST_KEY);
        System.out.println("play() return: " + result);
        return result;
    }

    private CRobotPose createCheckedLedPose(int mouth) throws ProbeAbortException {
        CRobotPose pose = new CRobotPose();
        requireNoServoOrTorqueData(pose, "before setLED_Sota");
        pose.setLED_Sota(TEST_EYE_COLOR, TEST_EYE_COLOR, mouth, TEST_POWER_COLOR);
        requireNoServoOrTorqueData(pose, "after setLED_Sota");
        Map<Byte, Short> led = pose.getLed();
        require(led != null && !led.isEmpty(),
                "ABORT: LED pose contains no LED data after setLED_Sota");
        return pose;
    }

    private Byte[] discoverLedIdsFromCheckedPose() throws ProbeAbortException {
        CRobotPose pose = createCheckedLedPose(levels.low);
        Byte[] ids = ledIdsFromPose(pose);
        validateLedIds(ids);
        return ids;
    }

    private Byte[] ledIdsFromPose(CRobotPose pose) throws ProbeAbortException {
        Map<Byte, Short> led = pose.getLed();
        require(led != null && !led.isEmpty(),
                "LED map must be populated before discovering LED IDs");
        Byte[] ids = led.keySet().toArray(new Byte[led.size()]);
        validateLedIds(ids);
        return ids;
    }

    private void validateLedIds(Byte[] ids) throws ProbeAbortException {
        require(ids != null, "LED ID array is null");
        require(ids.length > 0, "LED ID array is empty");
        Set<Byte> unique = new HashSet<Byte>();
        for (int index = 0; index < ids.length; index++) {
            Byte id = ids[index];
            require(id != null, "LED ID array contained null at index " + index);
            require(unique.add(id), "LED ID array contained duplicate ID " + id);
        }
    }

    private void requireLedIdSetsEqual(CRobotPose pose, Byte[] lockedIds)
            throws ProbeAbortException {
        validateLedIds(lockedIds);
        Byte[] currentIds = ledIdsFromPose(pose);
        require(ledIdSetsEqual(lockedIds, currentIds),
                "ABORT: current LED pose IDs differ from the locked LED ID set."
                        + " No play() was performed.");
    }

    private boolean ledIdSetsEqual(Byte[] first, Byte[] second)
            throws ProbeAbortException {
        validateLedIds(first);
        validateLedIds(second);
        Set<Byte> firstSet = new HashSet<Byte>(Arrays.asList(first));
        Set<Byte> secondSet = new HashSet<Byte>(Arrays.asList(second));
        return firstSet.equals(secondSet);
    }

    private String formatLedIds(Byte[] ids) throws ProbeAbortException {
        validateLedIds(ids);
        Byte[] sorted = ids.clone();
        Arrays.sort(sorted);
        return Arrays.toString(sorted);
    }

    private void printLedLockChecks(CRobotPose pose, Byte[] lockedIds)
            throws ProbeAbortException {
        require(ledLockAcquired, "LED lock is not acquired");
        validateLedIds(lockedIds);
        Byte[] currentIds = ledIdsFromPose(pose);
        boolean equal = ledIdSetsEqual(lockedIds, currentIds);

        System.out.println("LED lock: ACQUIRED");
        System.out.println("LED lock key: " + LED_TEST_KEY);
        System.out.println("Play key: " + LED_TEST_KEY);
        System.out.println("Servo guard key differs from play key: "
                + yesNo(!SERVO_GUARD_KEY.equals(LED_TEST_KEY)));
        System.out.println("LED lock key equals play key: YES");
        System.out.println("Locked LED IDs: " + formatLedIds(lockedIds));
        System.out.println("Current pose LED IDs: " + formatLedIds(currentIds));
        System.out.println("LED ID sets equal: " + yesNo(equal));
        System.out.println("No numeric LED IDs are hard-coded by this probe.");
        require(equal,
                "ABORT: current LED pose IDs differ from the locked LED ID set."
                        + " No play() was performed.");
    }

    private void validateImmediatelyBeforePlay(CRobotPose pose)
            throws ProbeAbortException {
        requireWriteGuard();
        requireNoServoOrTorqueData(pose, "immediately before play");
        Map<Byte, Short> led = pose.getLed();
        require(led != null && !led.isEmpty(),
                "ABORT: LED map is empty immediately before play");
    }

    private void requireNoServoOrTorqueData(CRobotPose pose, String stage)
            throws ProbeAbortException {
        Map<Byte, Short> servo = pose.getPose();
        Map<Byte, Short> torque = pose.getTorque();
        require(isNullOrEmpty(servo),
                "ABORT: LED pose unexpectedly contains servo data " + stage);
        require(isNullOrEmpty(torque),
                "ABORT: LED pose unexpectedly contains torque data " + stage);
    }

    private static boolean isNullOrEmpty(Map<?, ?> map) {
        return map == null || map.isEmpty();
    }

    private void printHardChecks(CRobotPose pose, int mouth) throws ProbeAbortException {
        Map<Byte, Short> servo = pose.getPose();
        Map<Byte, Short> torque = pose.getTorque();
        Map<Byte, Short> led = pose.getLed();
        System.out.println("About to perform ONE LED-only play()");
        System.out.println("Servo guard: " + (servoGuardAcquired ? "ACQUIRED" : "NOT ACQUIRED"));
        System.out.println("Default servo count: "
                + (servoIds == null ? -1 : servoIds.length));
        System.out.println("Servo guard key: " + SERVO_GUARD_KEY);
        System.out.println("Play key: " + LED_TEST_KEY);
        System.out.println("Keys different: "
                + (!SERVO_GUARD_KEY.equals(LED_TEST_KEY) ? "YES" : "NO"));
        System.out.println("Servo map: " + structuralMapState(servo));
        System.out.println("Torque map: " + structuralMapState(torque));
        System.out.println("LED map size: " + sizeOrMinusOne(led));
        System.out.println("Requested mouth: " + configuredMouthLabel(mouth));
        System.out.println("Probe source explicitly called ServoOn/ServoOff: NO");
        System.out.println("Vendor runtime shutdown hook behavior: may attempt ServoOff;"
                + " observed repeatedly during prior manual runs");
        System.out.println("NO servo motion is intended.");
        validateImmediatelyBeforePlay(pose);
    }

    private static String structuralMapState(Map<Byte, Short> map) {
        if (map == null) {
            return "NULL";
        }
        if (map.isEmpty()) {
            return "EMPTY";
        }
        return "NON-EMPTY (size=" + map.size() + ")";
    }

    private String configuredMouthLabel(int mouth) {
        if (mouth == levels.zero) {
            return "ZERO=" + mouth;
        }
        if (mouth == levels.low) {
            return "LOW=" + mouth;
        }
        if (mouth == levels.medium) {
            return "MEDIUM=" + mouth;
        }
        if (mouth == levels.high) {
            return "HIGH=" + mouth;
        }
        return "VALUE=" + mouth;
    }

    private static Map<Byte, Short> snapshotMap(Map<Byte, Short> map) {
        return map == null ? null : new LinkedHashMap<Byte, Short>(map);
    }

    private static void printNamedMap(String name, Map<Byte, Short> map) {
        System.out.println(name + " map size: " + sizeOrMinusOne(map));
        System.out.println(name + " entries:");
        if (map == null) {
            System.out.println("  <null>");
        } else if (map.isEmpty()) {
            System.out.println("  <empty>");
        } else {
            for (Map.Entry<Byte, Short> entry : map.entrySet()) {
                System.out.println("  id=" + entry.getKey() + ", value=" + entry.getValue());
            }
        }
    }

    private static void printMapComparison(
            String name,
            Map<Byte, Short> before,
            Map<Byte, Short> after) {
        System.out.println(name + " map equal before/after: "
                + (mapsEqual(before, after) ? "YES" : "NO"));
        printAddedKeys(before, after);
        printRemovedKeys(before, after);
        printChangedValues(before, after);
    }

    private static boolean mapsEqual(Map<Byte, Short> before, Map<Byte, Short> after) {
        if (before == null) {
            return after == null;
        }
        return before.equals(after);
    }

    private static void printAddedKeys(
            Map<Byte, Short> before,
            Map<Byte, Short> after) {
        System.out.println("  added keys:");
        boolean found = false;
        if (after != null) {
            for (Map.Entry<Byte, Short> entry : after.entrySet()) {
                if (before == null || !before.containsKey(entry.getKey())) {
                    System.out.println("    id=" + entry.getKey()
                            + ", value=" + entry.getValue());
                    found = true;
                }
            }
        }
        if (!found) {
            System.out.println("    <none>");
        }
    }

    private static void printRemovedKeys(
            Map<Byte, Short> before,
            Map<Byte, Short> after) {
        System.out.println("  removed keys:");
        boolean found = false;
        if (before != null) {
            for (Map.Entry<Byte, Short> entry : before.entrySet()) {
                if (after == null || !after.containsKey(entry.getKey())) {
                    System.out.println("    id=" + entry.getKey()
                            + ", value=" + entry.getValue());
                    found = true;
                }
            }
        }
        if (!found) {
            System.out.println("    <none>");
        }
    }

    private static void printChangedValues(
            Map<Byte, Short> before,
            Map<Byte, Short> after) {
        System.out.println("  changed values:");
        boolean found = false;
        if (before != null && after != null) {
            for (Map.Entry<Byte, Short> entry : before.entrySet()) {
                Byte key = entry.getKey();
                if (after.containsKey(key)
                        && !valuesEqual(entry.getValue(), after.get(key))) {
                    System.out.println("    id=" + key
                            + ", before=" + entry.getValue()
                            + ", after=" + after.get(key));
                    found = true;
                }
            }
        }
        if (!found) {
            System.out.println("    <none>");
        }
    }

    private static boolean valuesEqual(Short before, Short after) {
        return before == null ? after == null : before.equals(after);
    }

    private static boolean isTemporarilyBlockedOption(String command) {
        return "5".equals(command)
                || "9".equals(command);
    }

    private void reportTemporaryGateBlock(String command) {
        System.out.println("Option " + command + " is blocked in this diagnostic revision.");
        System.out.println("Gate 1A-2 brightness and Gate 1C rate testing remain blocked.");
        System.out.println("No play() was performed.");
        System.out.println("Approved workflow: 1, 2, 3, 4, 6, 7, 10, 11, 12, 8,"
                + " then cleanup and STOP.");
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
                "further LED play is suppressed after an unsafe servo observation");
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

    private String askObservation(String prompt) throws IOException, ProbeAbortException {
        String value = readTrimmedLine(prompt);
        require(value != null, "operator observation input ended unexpectedly");
        System.out.println("Recorded observation: " + printableObservation(value));
        return value;
    }

    private void printGate1ObservationSummary() {
        System.out.println("Independent observation summary:");
        System.out.println("  Gate 1A-1 servo safety: "
                + (gate1A1ServoSafetyPassed ? "PASS (operator observation only)" : "NOT PASSED"));
        System.out.println("  Gate 1A-1 play() returned true: " + yesNo(gate1A1PlayReturned));
        System.out.println("  Gate 1A-1 mouth visibly changed: " + yesNo(gate1A1MouthChanged));
        System.out.println("  Gate 1A-1 either eye visibly changed: "
                + yesNo(gate1A1EyeChanged));
        System.out.println("  Gate 1A-1 power visibly changed: "
                + yesNo(gate1A1PowerChanged));
        System.out.println("  Gate 1A-1 unexpected servo sound: "
                + yesNo(gate1A1UnexpectedServoSound));
        System.out.println("  Gate 1B disable attempted: "
                + yesNo(voiceSyncDisableAttemptedByProbe));
        System.out.println("  Gate 1B disable returned normally: "
                + yesNo(voiceSyncDisableReturnedNormally));
        System.out.println("  Gate 1B manual play() returned true: "
                + yesNo(gate1BManualPlayReturned));
        System.out.println("  Gate 1B servo movement: "
                + yesNo(gate1BServoMovementObserved));
        System.out.println("  Gate 1B unexpected servo sound: "
                + yesNo(gate1BUnexpectedServoSound));
        System.out.println("  Gate 1B mouth visibly changed: "
                + yesNo(gate1BManualMouthChanged));
        System.out.println("  Gate 1B either eye visibly changed: "
                + yesNo(gate1BEyeChanged));
        System.out.println("  Gate 1B power visibly changed: "
                + yesNo(gate1BPowerChanged));
        System.out.println("  Gate 1B eye note: " + printableObservation(gate1BEyeObservation));
        System.out.println("  Gate 1B power note: "
                + printableObservation(gate1BPowerObservation));
        System.out.println("  LED lock attempted: " + yesNo(ledLockAttempted));
        System.out.println("  LED lock currently acquired: " + yesNo(ledLockAcquired));
        System.out.println("  Gate 1L update executed: " + yesNo(ledLockUpdateExecuted));
        if (ledLockUpdateExecuted) {
            System.out.println("  Gate 1L play() returned true: "
                    + yesNo(ledLockPlayReturned));
            System.out.println("  Gate 1L mouth visibly changed: "
                    + yesNo(ledLockMouthChanged));
            System.out.println("  Gate 1L either eye visibly changed: "
                    + yesNo(ledLockEyeChanged));
            System.out.println("  Gate 1L power visibly changed: "
                    + yesNo(ledLockPowerChanged));
        }
        System.out.println("  configured enable returned normally: "
                + yesNo(voiceSyncEnableReturnedNormally));
        System.out.println("  original voice-sync state restored: UNKNOWN");
    }

    private void printLedControlDiagnosticSummary() {
        System.out.println();
        System.out.println("LED CONTROL DIAGNOSTIC SUMMARY");
        System.out.println("Option 4:");
        System.out.println("  voice-sync disable requested: NO");
        System.out.println("  LED lock acquired: NO");
        System.out.println("  play returned true: " + yesNo(gate1A1PlayReturned));
        System.out.println("  mouth changed: " + yesNo(gate1A1MouthChanged));
        System.out.println("  eyes changed: " + yesNo(gate1A1EyeChanged));
        System.out.println("  power changed: " + yesNo(gate1A1PowerChanged));
        System.out.println("Option 7:");
        System.out.println("  voice-sync disable requested: YES");
        System.out.println("  LED lock acquired: NO");
        System.out.println("  play returned true: " + yesNo(gate1BManualPlayReturned));
        System.out.println("  mouth changed: " + yesNo(gate1BManualMouthChanged));
        System.out.println("  eyes changed: " + yesNo(gate1BEyeChanged));
        System.out.println("  power changed: " + yesNo(gate1BPowerChanged));
        System.out.println("Option 11:");
        System.out.println("  voice-sync disable requested: YES");
        System.out.println("  LED lock acquired: YES");
        System.out.println("  play returned true: " + yesNo(ledLockPlayReturned));
        System.out.println("  mouth changed: " + yesNo(ledLockMouthChanged));
        System.out.println("  eyes changed: " + yesNo(ledLockEyeChanged));
        System.out.println("  power changed: " + yesNo(ledLockPowerChanged));
        System.out.println("  note: " + printableObservation(ledLockObservation));
        System.out.println("Servo movement in any tested play: "
                + yesNo(gate1A1ServoMovementObserved
                        || gate1BServoMovementObserved
                        || ledLockServoMovementObserved));
        System.out.println("Unexpected servo sound in any tested play: "
                + yesNo(gate1A1UnexpectedServoSound
                        || gate1BUnexpectedServoSound
                        || ledLockUnexpectedServoSound));
        System.out.println("No automatic root-cause conclusion is assigned.");
    }

    private static String yesNo(boolean value) {
        return value ? "YES" : "NO";
    }

    private static String printableObservation(String value) {
        if (value == null) {
            return "<not recorded>";
        }
        return value.length() == 0 ? "<empty>" : value;
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

    private void suppressFurtherLedPlay(String reason) {
        furtherLedPlaySuppressed = true;
        System.err.println("Hard stop after " + reason
                + ": cleanup will not issue another LED play.");
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
                performOneLedPlay(
                        levels.zero,
                        "Cleanup mouth zero — not part of LED-lock diagnostic measurement",
                        false,
                        false,
                        ledLockAcquired ? ledLockIds : null);
            } catch (Throwable failure) {
                System.err.println("Cleanup mouth zero failed: " + describe(failure));
            }
        } else if (anyLedPlayAttempted && furtherLedPlaySuppressed) {
            System.err.println(
                    "Cleanup mouth zero skipped after movement or unexpected servo sound.");
        }

        if (ledLockAcquired && motion != null && ledLockIds != null) {
            try {
                motion.UnLockLEDHandle(LED_TEST_KEY, ledLockIds);
                ledLockAcquired = false;
                ledLockIds = null;
                System.out.println("Cleanup LED lock release completed.");
            } catch (Throwable failure) {
                System.err.println("Cleanup LED lock release failed: " + describe(failure));
            }
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
