# Sota mouth LED lock recovery

## Scope

This runbook covers suspected stale or conflicting AppManager mouth LED lock
state after an ordinary process error, operator interruption, or hard
termination. It does not authorize automated hardware operations. The
production normal pulse path has already been verified. The 2026-07-31 live
lock-only competition probe completed, but it disproved the cross-process
exclusion assumption. The separate whole-Sota `FcntlProcessLock` design is now
implemented and verified for cooperating RobotController processes, completing
the Phase 7 fault-recovery gate.

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
* use an automated script to carry out live recovery;
* treat the existence of `/run/lock/robot-controller-sota.lock` as proof that
  a process currently owns the lock;
* unlink that pathname manually to resolve contention;
* stop AppManager, `vsmd_edison`, or another service to bypass process-lock
  contention.

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
7. After recovery, do not treat a successful AppManager LOCK and CONVERT as
   proof of exclusive ownership. A write-capable RobotController process must
   own the whole-Sota process lock before considering an LED control write.

Record the owning process, known key/IDs status, read-only observations,
operator decision, and result. `phase7_fault_recovery` is complete; unresolved
live operational state still requires the same fail-closed escalation.

## Whole-Sota process coordination

The 2026-07-31 live result established that SotaAppManager does not provide an
exclusive LED-ID mutex. AppManager allocates interpolation timer leases or
slots. Cooperating RobotController processes use:

```text
implementation: robot_controller.posix_process_lock.FcntlProcessLock
default path: /run/lock/robot-controller-sota.lock
scope: whole Sota robot
mode: flock(LOCK_EX | LOCK_NB)
```

The current `AppManagerVsmdLedLock` local reservation remains useful for
rejecting overlap within one adapter instance. It does not coordinate separate
instances or processes. The compatibility class name containing `Lock` is not
evidence of cross-process mutex semantics.

Each process-lock object makes one acquisition attempt and holds its file
descriptor for the process lifecycle. `close()` is idempotent. Normal shutdown
does not unlink the pathname. A crash, `SIGKILL`, or power loss releases the
kernel lock when the process file descriptor is closed; the pathname may remain
and can be reused.

Contention raises `ProcessLockUnavailableError` immediately. There is no retry,
sleep, or blocking wait. This is an advisory lock: it cannot prevent an
external program that does not use the guard, a direct TCP 6495/6498 client, or
a process using another pathname. Operational policy must require every
write-capable RobotController process and live diagnostic to use the same
guard. External command clients should normally use the guarded TCP 22222
production server.

## Guarded and unguarded entry points

The production `python -m robot_controller.mock_server` path acquires the lock
only when both live Sota settings are active:

```text
ROBOT_MOUTH_LED_BACKEND=sota_vsmd
ROBOT_HARDWARE_LIVE_WRITE_ENABLED=true
```

It validates settings, acquires the lock, then constructs the application,
Backend, and server. Contention therefore creates no Backend, listen socket,
AppManager transport, or VSMD transport. Shutdown closes the application,
restores signal handlers, then closes the process lock.

The direct-live paths `mouth_led_backend_smoke`,
`app_manager_mouth_led_probe`, `app_manager_lock_competition_probe`, and
`app_manager_probe` use the same guard after their explicit live confirmation.
Without confirmation they create neither the process lock nor a live transport.

The read-only `mouth_led_observer`, Fake-only
`mouth_led_fault_recovery_smoke`, Fake-only `app_manager_mouth_led_dry_run`,
the `mouth_led_command_client` that talks to the guarded server, and socket-free
dry-runs do not acquire the lock. This preserves concurrent read-only
observation of a production server.

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
The probe was designed to synchronize three independent AppManager clients
without sleeping. Its intended sequence was:

1. Client A acquires and keeps LED 14 active.
2. Client B immediately requests LED 14 while A remains active. The original
   hypothesis expected `NG` and `AppManagerLockRejectedError`; the 2026-07-31
   live run refuted that hypothesis because B received `OK` and converted its
   key to a different timer address.
3. Client A releases its known lease exactly once.
4. Client C immediately acquires LED 14 after A releases, then releases its
   known lease exactly once.

The fourth step was not reached in the 2026-07-31 run.

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

The broad capture contained 478 packets in total, including 410 TCP 6498
packets that may be routine traffic from an existing process. The probe
implementation constructs only AppManager transport and does not construct
VSMD transport, so those packets must not be attributed to the probe.
Conversely, the capture cannot establish `TCP 6498 packets = 0` for the
environment; future attribution requires process-level observation or a
narrower capture method.

Do not interpret `INTERP_LOCK` as a cross-process mutex or LED-ID-exclusive
lock. Treat it as an interpolation timer lease/slot allocation and release
mechanism; its internal timer stack, trigger-pointer allocation rules, and
non-LIFO behavior remain unverified. The remote run did not provide a physical
illumination observation, so it does not establish whether the mouth LED was
lit or dark.

## Process-lock verification evidence

Intel Edison CPython 3.6.15 preflight confirmed `fcntl` import, `flock`
availability, `/run/lock` existence and writability, first nonblocking exclusive
acquisition, rejection of a second independent open with EACCES/EAGAIN,
successful cleanup, and exit code 0. It did not connect to AppManager, VSMD,
LEDs, or device files.

Ubuntu WSL 2 with Linux Python 3.14.4 and pytest 9.1.1 completed 3 subprocess
integration tests and 17 process-lock unit tests; the full Linux suite reported
1101 passed and 2 skipped. The tests confirmed immediate contender rejection
while the holder remained active, acquisition after normal close, acquisition
after holder `SIGKILL`, and acquisition with the pathname still present.
The Windows full suite reported 1100 passed and 3 skipped; the three skips are
the Linux-only process-lock integration tests. Python 3.6 grammar parsing
covered 104 source/test files, and `compileall -q src` succeeded.

Not yet confirmed are execution of the latest actual `FcntlProcessLock` class
on Edison, the subprocess integration test on Linux CPython 3.6.15,
non-cooperating external programs, physical illumination during the competition
probe, AppManager's internal timer allocation algorithm, and process-level
attribution of TCP 6498 traffic. These are future operational acceptance items,
not Phase 7 blockers.

Detailed evidence and artifact hashes are recorded in
[`../evidence/app-manager-lock-competition-20260731.md`](../evidence/app-manager-lock-competition-20260731.md).

```text
lock-only competition probe: completed_with_observed_slot_allocation
cross-process LED exclusion: provided for cooperating RobotController processes by whole-Sota FcntlProcessLock
SotaAppManager LED-ID-exclusive arbitration: not provided
phase7_fault_recovery: complete
Phase 8: allowed after this documentation correction is committed and pushed
```
