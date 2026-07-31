# Sota mouth LED lock recovery

## Scope

This runbook covers suspected stale or conflicting AppManager mouth LED lock
state after an ordinary process error, operator interruption, or hard
termination. It does not authorize automated hardware operations. The
production normal pulse path has already been verified. The 2026-07-31 live
lock-only competition probe completed, but it disproved the cross-process
exclusion assumption; the Phase 7 fault-recovery gate remains pending a
design correction.

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
7. After recovery, do not treat a successful LOCK and CONVERT as proof of
   exclusive ownership. Confirm that no other RobotController process controls
   the same LED IDs before considering any LED control write.

Record the owning process, known key/IDs status, read-only observations,
operator decision, and result. `phase7_fault_recovery` remains pending until
cross-process exclusion is redesigned and separately verified.

## Interim operating constraint

The 2026-07-31 live result established that SotaAppManager does not provide an
exclusive LED-ID mutex. Until a separate coordination mechanism is designed,
deployed, and verified:

```text
Only one RobotController process may control mouth LED 14.
Multiple RobotController processes must not control the same Sota LED IDs.
```

The current `AppManagerVsmdLedLock` local reservation remains useful for
rejecting overlap within one adapter instance. It does not coordinate separate
instances or processes. If multiple processes require LED control, use an
operator-reviewed design such as a single command server, dedicated broker,
Unix domain socket coordinator, or OS lockfile. This runbook does not select or
implement that mechanism.

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
2. Client B immediately requests LED 14 while A remains active. The original
   hypothesis expected `NG` and `AppManagerLockRejectedError`; the 2026-07-31
   live run refuted that hypothesis because B received `OK` and converted its
   key to a different timer address.
3. Client A releases its known lease exactly once.
4. Client C immediately acquires LED 14 after A releases, then releases its
   known lease exactly once.

The explicit evidence keys are `<key-prefix>-a`, `<key-prefix>-b`, and
`<key-prefix>-c`; the default prefix is `phase7-lock`. The probe performs no
automatic retry and never sends an UNLOCK for an unknown key.

The 2026-07-31 run stopped after the unexpected B acquisition. Its capture
therefore contained:

```text
TCP 6495 INTERP_LOCK = 2
TCP 6495 INTERP_CNV_KEY_2_ADDR = 2
TCP 6495 INTERP_UNLOCK = 2
```

Client C was not reached. Cleanup sent B UNLOCK followed by A UNLOCK, and both
responses were `OK`. The probe made no automatic retry and does not need to be
rerun to establish the observed semantics.

The broad capture filter also recorded 10 TCP 6498 packets from an existing
process. The probe implementation constructs only AppManager transport and
does not construct VSMD transport, so those packets must not be attributed to
the probe. Conversely, the capture cannot establish `TCP 6498 packets = 0` for
the environment; future attribution requires process-level observation or a
narrower capture method.

Do not interpret `INTERP_LOCK` as a cross-process mutex or LED-ID-exclusive
lock. Treat it as an interpolation timer lease/slot allocation and release
mechanism; its internal timer stack, trigger-pointer allocation rules, and
non-LIFO behavior remain unverified. The remote run did not provide a physical
illumination observation, so it does not establish whether the mouth LED was
lit or dark.

Detailed evidence and artifact hashes are recorded in
[`../evidence/app-manager-lock-competition-20260731.md`](../evidence/app-manager-lock-competition-20260731.md).

```text
lock-only competition probe: completed_with_unexpected_semantics
cross-process LED exclusion: not provided by SotaAppManager
phase7_fault_recovery: pending design correction
Phase 8: do not start
```
