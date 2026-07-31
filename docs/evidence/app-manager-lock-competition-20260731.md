# AppManager lock competition evidence (2026-07-31)

## Scope

This document records one manually initiated AppManager lock-only competition
probe on an Intel Edison Sota. It records observed behavior, not a claim about
physical illumination or unobserved AppManager internals. No code or test was
changed as part of this evidence update, and the live probe was not rerun.

The original hypothesis was that, while Client A held LED ID 14, Client B using
a different key would receive `NG`. The live result refuted that hypothesis:
both clients acquired LED ID 14 and received different interpolation timer
addresses.

## Tested revision and environment

| Item | Value |
| --- | --- |
| Branch | `feature/python-robot-controller` |
| Commit | `432e657656829a0428e5cefe2465d75a65f5ec33` |
| Commit message | `Add AppManager lock competition probe` |
| Hardware | Vstone Sota / Intel Edison |
| OS | Yocto Linux |
| Python | CPython 3.6.15 |
| Python executable | `/home/root/bin/python3` |
| Deployment directory | `/home/root/robot_controller_edison_smoke` |
| SotaAppManager | `127.0.0.1:6495` |
| VSMD | `127.0.0.1:6498` |
| LED ID | `14` |

## Deployment bundle and extraction

The Windows and Edison SHA-256 values matched.

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `robot_controller_edison_smoke.tar.gz` | 148134 bytes | `803277B3B0D3A496D851E52812FC28878A79D9184591E864DA0CEE6F25360D41` |

The Edison `tar` command did not extract the source file with the long path
`robot_controller_edison_smoke/src/robot_controller/hardware/vsmd/app_manager_lock_competition_probe.py`.
Python 3.6 standard-library `tarfile` inspection found both expected members:

```text
match_count=2
robot_controller_edison_smoke/src/robot_controller/hardware/vsmd/app_manager_lock_competition_probe.py
robot_controller_edison_smoke/tests/unit/hardware/vsmd/test_app_manager_lock_competition_probe.py
```

After archive-path validation, `tarfile.extractall()` completed successfully.
The recorded checks were:

```text
python_tar_extract_exit_code=0
probe_file_exists=0
probe_test_file_exists=0
compileall_exit_code=0
probe_import=success
probe_import_exit_code=0
```

The `*_file_exists=0` values are recorded command exit codes and mean that both
files existed.

## Confirmation-required dry run

The module was run without `--confirm-live-lock`:

```text
robot_controller.hardware.vsmd.app_manager_lock_competition_probe
```

It created no socket and was designed not to connect to AppManager or VSMD:

```text
live_network=false
live_lock=false
result=confirmation_required
dry_run_exit_code=0
```

## Live probe conditions

```text
host=127.0.0.1
port=6495
led_id=14
timeout=2.0
key_prefix=phase7-lock
confirm_live_lock=true
```

The keys were `phase7-lock-a`, `phase7-lock-b`, and `phase7-lock-c`. The
expected sequence was A LOCK and CONVERT, B rejection while A remained active,
A UNLOCK, then C LOCK, CONVERT, and UNLOCK.

## Observed probe result

Client A acquired LED 14 and converted its key to timer address 502. Contrary
to the expected success condition, Client B also acquired LED 14. The probe
classified this as an unexpected lock error and exited with status 1:

```text
SotaAppManager LED lock competition probe
live_network=true
live_lock=true
led_id=14

client_a_key=phase7-lock-a
client_a_lock_acquired=true
client_a_timer_address=502

client_b_key=phase7-lock-b
client_b_lock_rejected=false
result=failure
error_type=AppManagerCompetitionUnexpectedLockError
error=client B unexpectedly acquired the contested LED
probe_exit_code=1
```

This is a failure relative to the probe's original hypothesis, not a cleanup
failure. The known-lease cleanup path sent B UNLOCK and then A UNLOCK; both
responses were `OK`. No automatic retry occurred, and the probe was run only
once. Client C was not reached.

## Packet-capture reconstruction

Capture metadata:

```text
file=/home/root/mouth_led_lock_competition_20260731_01.pcap
filter=tcp port 6495 or tcp port 6498
```

AppManager command counts were:

```text
INTERP_LOCK = 2
INTERP_CNV_KEY_2_ADDR = 2
INTERP_UNLOCK = 2
```

Per-connection reconstruction was:

| Sequence | Client port | Command | Key | IDs | Response |
| ---: | ---: | --- | --- | --- | --- |
| 1 | 59776 | `INTERP_LOCK` | `phase7-lock-a` | `[14]` | `OK` |
| 2 | 59777 | `INTERP_CNV_KEY_2_ADDR` | `phase7-lock-a` | — | `502` |
| 3 | 59778 | `INTERP_LOCK` | `phase7-lock-b` | `[14]` | `OK` |
| 4 | 59779 | `INTERP_CNV_KEY_2_ADDR` | `phase7-lock-b` | — | `504` |
| 5 | 59780 | `INTERP_UNLOCK` | `phase7-lock-b` | `[14]` | `OK` |
| 6 | 59781 | `INTERP_UNLOCK` | `phase7-lock-a` | `[14]` | `OK` |

Key occurrence counts were three for A, three for B, and zero for C. Thus,
while A's lease remained active, B used a different key to acquire the same LED
ID and received a separate timer address:

```text
Client A: LED 14, timer address 502
Client B: LED 14, timer address 504
```

## TCP 6498 attribution limitation

The capture contained 478 packets in total, of which 410 matched TCP 6498. The
competition probe constructs only AppManager transport; it does not construct
VSMD transport. Because the filter captured all loopback traffic for ports
6495 and 6498, the 410 TCP 6498 packets are consistent with routine
communication from an existing process and cannot be attributed to the probe.

Accordingly, the previously proposed criterion `PCAP overall TCP 6498 packets
= 0` is not usable for this environment. A future test would need process-level
attribution or a more narrowly attributable capture. This limitation does not
change the directly observed AppManager request/response sequence above.

## Read-only post-test observation

After capture stopped, a read-only VSMD observer exited successfully. All three
samples reported:

```text
master_control_period_us=16667
audio_diff=0
selector=138
target=0
output=0
trigger_pointer=500
trigger_timer_value=65535
remaining_time=0
observer_exit_code=0
```

These observations are consistent with both known leases having been unlocked
and the observable mouth LED state returning to the pre-test safe state. The
test was conducted remotely, so physical mouth LED illumination was not
observed:

```text
operator_observed_physical_illumination=unavailable_remote
```

This evidence does not state that the physical mouth LED remained dark.

## Confirmed facts and bounded conclusions

Confirmed by this run:

* Different keys can successfully `INTERP_LOCK` the same LED ID concurrently.
* The two keys converted to different interpolation timer addresses.
* Both known leases returned `OK` to UNLOCK in B-then-A order.
* The probe made no automatic retry and did not reach Client C.
* Post-test read-only values returned to the recorded safe state.

Design conclusion:

```text
SotaAppManager INTERP_LOCK is not a cross-process, LED-ID-exclusive mutex.
```

It may be described as an interpolation timer lease/slot allocation and
release mechanism. This run does not establish AppManager's internal timer
stack structure, trigger-pointer allocation rules, non-LIFO behavior, or
physical illumination behavior.

The Fake cross-client rejection test and the original live-probe success
condition documented a hypothesis. They remain useful for typed `NG` handling,
but the 2026-07-31 live evidence refutes their use as proof that AppManager
provides cross-process exclusion.

## Operational and gate impact

Until a separate coordination mechanism is designed and verified:

```text
Only one RobotController process may control mouth LED 14.
Multiple RobotController processes must not control the same Sota LED IDs.
```

Local overlap rejection inside one `AppManagerVsmdLedLock` instance remains
valid, but it does not protect separate instances or processes. A future
cross-process design may use a single command server, dedicated broker, Unix
domain socket coordinator, or OS lockfile; no mechanism is selected or
implemented by this documentation change.

```text
lock-only competition probe: completed_with_unexpected_semantics
cross-process LED exclusion: not provided by SotaAppManager
phase7_fault_recovery: pending design correction
Phase 8: do not start
```

The probe does not need to be rerun to establish this result. Phase 8 must not
start on the assumption that AppManager arbitrates multiple RobotController
processes.

## External evidence inventory

Raw PCAP, result, log, and CSV files remain on the Edison under `/home/root` and
are intentionally not added to Git.

| Evidence | Size | SHA-256 |
| --- | ---: | --- |
| `mouth_led_lock_competition_20260731_01.pcap` | 44862 bytes | `dac950a7373d82aae3c850a6b86dd6ac8589f8bbada42eea16095630fb118d28` |
| `mouth_led_lock_competition_20260731_01_result.txt` | 365 bytes | `5ec560a1a9c2eac0fda842e274d9c8a797ac6cb94e92efad6fc25dc92ad40ca7` |
| `mouth_led_lock_competition_20260731_01_tcpdump.log` | 162 bytes | `cea78483cefbb6634ce41ee6210d84384f05364bc53f949b52ff7c9dbc237095` |
| `mouth_led_lock_competition_20260731_01_observer.csv` | 460 bytes | `9e728d08114abfeb9994d57a8ec1db0176801ebe2bcaefa0c0c194714bfb6993` |
