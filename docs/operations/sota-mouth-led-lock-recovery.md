# Sota mouth LED lock recovery

## Scope

This runbook covers suspected stale or conflicting AppManager mouth LED lock
state after an ordinary process error, operator interruption, or hard
termination. It does not authorize automated hardware operations. The
production normal pulse path has already been verified; the Phase 7 live
lock-contention recovery gate remains pending.

Ordinary exceptions, `KeyboardInterrupt`, and `SystemExit` trigger
best-effort Target 0, timer 0, selector restoration, and one UNLOCK attempt.
`kill -9`, kernel panic, and power loss can prevent Python `finally` from
running, so cleanup is not guaranteed.

## Prohibited recovery actions

Do not:

* automatically UNLOCK an unknown key;
* issue blind or global UNLOCK requests across LEDs;
* automatically stop or restart AppManager, `vsmd_edison`, or system
  services;
* infer and overwrite VSMD memory;
* automatically retry LOCK, CONVERT, a socket request, or a complete pulse;
* continue with a VSMD control write after lock rejection;
* use an automated script to carry out live recovery.

## Operator sequence

1. Stop submitting new mouth LED writes.
2. Determine whether the RobotController process that owned the request is
   still running. Do not terminate unrelated processes.
3. Check AppManager and `vsmd_edison` availability using approved read-only
   operational observation. Do not change service state.
4. Use the read-only mouth LED observer to inspect selector, Target, Output,
   TriggerPointer, RemainingTime, and the validated pointed timer slot.
5. Only when the exact owning key and LED IDs are known, prepare an explicit
   operator-reviewed release plan. Do not infer a key from a timer address.
6. If the key is unknown, do not force release. Escalate to an operational
   decision that may include a controlled robot restart under the site safety
   procedure.
7. After recovery, resume with an explicitly reviewed lock-only test. Confirm
   acquire, CONVERT, and release before considering any LED control write.

Record the owning process, known key/IDs status, read-only observations,
operator decision, and result. `phase7_fault_recovery` remains pending until
the separately approved live lock-only contention test is completed.

## Offline verification

The following diagnostic uses only in-memory Fake transport and Fake memory.
It creates no socket and performs no live read or write:

```powershell
python -m robot_controller.diagnostics.mouth_led_fault_recovery_smoke
```

## Live AppManager lock-only competition probe

The dedicated operator probe uses only the configured SotaAppManager endpoint
on TCP 6495. It does not construct a VSMD transport, connect to TCP 6498,
read or write LED memory, or illuminate the LED. It does not operate servos,
torque, or services.

Without explicit confirmation it creates no socket:

```powershell
python -m robot_controller.hardware.vsmd.app_manager_lock_competition_probe
```

The output must end with:

```text
live_network=false
live_lock=false
result=confirmation_required
```

A live lock-only run requires the explicit `--confirm-live-lock` option and
must be initiated by an operator under an approved capture and safety plan.
The probe synchronizes three independent AppManager clients without sleeping:

1. Client A acquires and keeps LED 14 active.
2. Client B immediately requests LED 14 while A remains active. `NG` and
   `AppManagerLockRejectedError` are the expected success condition; B must
   send no CONVERT or UNLOCK.
3. Client A releases its known lease exactly once.
4. Client C immediately acquires LED 14 after A releases, then releases its
   known lease exactly once.

The explicit evidence keys are `<key-prefix>-a`, `<key-prefix>-b`, and
`<key-prefix>-c`; the default prefix is `phase7-lock`. The probe performs no
automatic retry and never sends an UNLOCK for an unknown key.

For a successful default run, verify the packet capture contains exactly:

```text
TCP 6495 INTERP_LOCK = 3
TCP 6495 INTERP_CNV_KEY_2_ADDR = 2
TCP 6495 INTERP_UNLOCK = 2
TCP 6498 packets = 0
```

Any different count, unexpected B acquisition, cleanup failure, or packet on
TCP 6498 makes the live gate unsuccessful. Review the probe output and packet
capture before changing `phase7_fault_recovery`; code and Fake regression
completion alone do not complete the live gate.
