# Phase G — Controlled Production Runtime Acceptance

## 1. Purpose and hard boundary

This runbook prepares and records a **human-run** acceptance of commit
`bd299ae1bbc0d0514d5b60a0ca2d45125a01f1d6`. It does not authorize an automated
agent to connect to an Edison, deploy, start a JVM, play audio, or operate any
robot hardware. Every command under “Human only” must be reviewed and executed
by the designated operator.

The acceptance target is the isolated candidate. Never overwrite the current
production directory, replace its JARs, stop its process automatically, disable
services, use `killall`, or write directly to a device file. A STOP result ends
the run; do not continue with another hardware test.

## 2. Source inspection and known startup behavior

The candidate has two independent startup paths:

1. `main.App.main()` creates a two-thread executor and submits both
   `TCPServer(Params.port)` and `PoseExecutorThread`.
2. `Params` reads `ROBOT_TYPE` and `PORT` from `System.properties` in the JVM
   working directory. The checked-in port is `22222`.
3. `PoseExecutorThread.run()` immediately calls `RobotSys.initialize()`.
4. For `ROBOT_TYPE=Sota`, `RobotSys.initialize()` constructs the public VSTONE
   objects, calls `mem.Connect()`, `InitRobot_Sota()`, `ServoOn()`, then applies
   an initial pose, torque values, and LED values and waits 1500 ms.
5. `TCPServer` dispatches `audio_stream_v1` after the first legacy framed
   command. Construction creates `StreamingAudioPlayer` but does not open ALSA.
6. `System.loadLibrary("robotcontroller_alsa")`, JNI entry, and
   `snd_pcm_open("default")` occur only when a valid `START` reaches
   `AlsaPcm.open()`.

Consequently, **CONNECTION_READY proves only that the streaming connection was
acquired without opening the audio JNI/ALSA path**. It does not prove that JVM
startup was hardware-effect-free. The legacy `RobotSys.initialize()` effects
occur independently and earlier. This is a known safety concern in the
candidate, not a Phase G tooling change.

The streaming response matrix, copied from the production constants, is:

```text
STATUS
0x80 0x01  CONNECTION_READY
0x80 0x02  STARTED
0x80 0x03  ENDED
0x80 0x04  CANCELLED

ERROR
0x81 0x01  BUSY
0x81 0x02  PROTOCOL_ERROR
0x81 0x03  AUDIO_ERROR
0x81 0x04  QUEUE_OVERFLOW
```

Issue assessment:

- Problem: application startup performs robot connection, ServoOn, initial
  pose/torque, and LED writes before an audio command.
- Impact: starting the candidate can move or energize the robot before G.4.
- Reproduction condition: start `main.App` with `ROBOT_TYPE=Sota` and a working
  public VSTONE API connection.
- Cause: unconditional `RobotSys.initialize()` in `PoseExecutorThread.run()`.
- Possible future fix: explicit lifecycle initialization and operator policy
  before listen; this must not be changed in Phase G because it changes the
  acceptance target.
- Blocker status: Phase G is blocked unless the operator explicitly approves
  these already-known startup effects, establishes a safe physical area, and
  has the existing manual emergency procedure ready. Any effect beyond the
  reviewed legacy startup sequence is `STARTUP_SAFETY_FAILURE` and STOP.

## 3. PC-side candidate build (G.0–G.1)

For final acceptance, Repository HEAD is the commit containing the current
Phase G tooling. The production source baseline remains
`bd299ae1bbc0d0514d5b60a0ca2d45125a01f1d6`. The build script requires that
baseline to be an ancestor of HEAD and requires `src/`, `native/`, `test/`,
`System.properties`, `.classpath`, `.project`, and `.settings/` to be identical
to the baseline, including no untracked inputs in those paths.

For development and pre-commit verification, only the five Phase G preparation
files may differ and the build report labels that state `DEVELOPMENT`. For the
final acceptance build after those files are committed, `git status --porcelain`
must produce no output: no unexpected tracked, untracked, or staged changes.

Run on the Windows build PC. This command does not access an Edison and creates
output outside Git. Select a new, nonexistent output directory for each build:

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse origin/feature/java-audio-streaming

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\build_phase_g.ps1 `
  -DependencyDirectory C:\Users\tiio\Workspace\lib `
  -OutputDirectory <new-empty-output-directory>
```

The script fails closed unless the production baseline is an ancestor, the
production/test inputs match it, repository changes are within the rule above,
both `java` and `javac` are Java 8, all six dependency hashes match, compilation
succeeds, the JAR contains `main/App.class`, and the manifest matches. It records
Repository HEAD, production baseline, baseline integrity, worktree state, and
the newly generated JAR SHA-256. JAR hashes are recorded per build and are not
expected to be identical across rebuilds.

Expected candidate before native placement:

```text
<new-empty-output-directory>/
├─ phase-g-build-report.txt
├─ javac.log
└─ RobotController/
   ├─ RobotController.jar
   ├─ System.properties
   ├─ lib/                         (the six verified JARs)
   └─ native/                      (intentionally empty on the PC)
```

The build script always leaves `native/` empty. It has no option to find,
validate, build, download, or copy a native binary. Only the human deployment
step may later place the fixed Phase F.2 binary after verifying its identity.

PASS: all checks say PASS and the report records the candidate JAR hash.

FAIL/STOP: baseline ancestry/integrity failure, unexpected repository change,
non-Java-8 runtime/compiler, dependency mismatch, compilation error, manifest
mismatch, or missing JAR entry.

## 4. PCM fixtures on the PC

Human-run commands; the generated binary fixtures remain outside Git:

```powershell
New-Item -ItemType Directory -Force C:\Users\tiio\Workspace\phase-g-pcm | Out-Null
ffmpeg -f lavfi -i "sine=frequency=440:duration=4" -ar 24000 -ac 1 `
  -f s16le -acodec pcm_s16le C:\Users\tiio\Workspace\phase-g-pcm\a-440hz-4s.pcm
ffmpeg -f lavfi -i "sine=frequency=880:duration=2" -ar 24000 -ac 1 `
  -f s16le -acodec pcm_s16le C:\Users\tiio\Workspace\phase-g-pcm\b-880hz-2s.pcm
Get-FileHash -Algorithm SHA256 C:\Users\tiio\Workspace\phase-g-pcm\*.pcm
```

Expected sizes are 192000 bytes for A and 96000 bytes for B. Both must be raw
24000 Hz, mono, signed 16-bit little-endian PCM. Record both hashes in the
result. Do not commit them.

## 5. Isolated human deployment (G.2)

**Human only; do not run from an automated agent.** First review G.0/G.1 and
the startup concern above. Copy to a new directory such as:

```text
/home/root/robotcontroller_phase_g_bd299ae/
```

An operator may use their approved transfer procedure, for example:

```powershell
scp -r <final-build-output>\RobotController `
  root@<edison-host>:/home/root/robotcontroller_phase_g_bd299ae/
```

On Edison, the operator must locate the already-built Phase F.2 binary using
known provenance, verify it before copying, and verify it again at:

```text
/home/root/robotcontroller_phase_g_bd299ae/RobotController/native/librobotcontroller_alsa.so
```

Required SHA-256:

```text
1119B2666681885CAA03C22C8F16118A2A849AA14B3B7158D1962500E716306B
```

Do not rebuild the `.so`, extract implementation details from vendor JARs,
replace production, or deploy into the current production directory.

PASS: isolated files and all recorded hashes match.

FAIL/STOP: transfer ambiguity, collision with production, missing provenance,
permissions/layout error, or any mismatch.

## 6. Startup preflight and startup (G.3)

**Human only.** Before starting anything:

1. Confirm the physical robot area is safe and the known startup ServoOn,
   pose/torque/LED effects are explicitly approved.
2. Confirm the current production process has not been modified or stopped by
   this procedure.
3. Read `PORT` from the isolated `System.properties` and use a read-only socket
   listing to check for a conflict. If port 22222 is in use, STOP. Do not resolve
   it by automatically stopping the existing process.
4. Confirm the candidate directory, all hashes, Java 8, log destination, and
   operator-controlled shutdown/emergency procedure.
5. Confirm the native directory is selected through `java.library.path`.

After approval, the human operator may start the isolated candidate from its
own working directory and capture stdout/stderr:

```sh
cd /home/root/robotcontroller_phase_g_bd299ae/RobotController
java -Djava.library.path="$PWD/native" -jar RobotController.jar
```

PASS: only the reviewed legacy startup sequence occurs, the JVM remains alive,
and the port listens without conflict.

FAIL/STOP: any unreviewed motion/torque/LED/audio effect, connection/init error,
port conflict, process/native crash, or native/ALSA-related error before START.

## 7. Protocol-only connection (G.4)

From the PC, a human runs:

```powershell
python .\tools\phase_g_audio_client.py probe --host <edison-host> --port 22222
```

Expected: `CONNECTION_READY`, then clean client disconnect. This path sends no
START or PCM. The audio library, JNI entry, and ALSA `default` device must not
be opened by this connection. Legacy robot initialization has already occurred
at JVM startup as described in section 2.

PASS: CONNECTION_READY is decoded and no audio-native error/effect occurs.

FAIL/STOP: no response, wrong response, AUDIO/JNI/ALSA activity caused by the
probe, or JVM/native failure.

## 8. START and short playback (G.5–G.6)

START cannot be accepted independently of opening the production ALSA path.
At the first valid START, the expected path is
`System.loadLibrary` → JNI → `snd_pcm_open("default")`; only then may STARTED
be returned. The human operator runs:

```powershell
python .\tools\phase_g_audio_client.py normal `
  --host <edison-host> --port 22222 `
  --pcm-a C:\Users\tiio\Workspace\phase-g-pcm\a-440hz-4s.pcm
```

The client sends each DATA body as 2–960 even PCM bytes, paced at 48000
bytes/second. It waits for STARTED before DATA and for ENDED after END.

PASS requires all of:

- CONNECTION_READY and STARTED in order;
- audible 440 Hz playback from the intended speaker;
- mouth LED synchronization observed by the operator;
- END followed by ENDED;
- no JVM/native crash or unexpected robot effect.

Any missing item is FAIL/STOP. In particular, START → AUDIO_ERROR, silence
after STARTED, unsynchronized mouth LED, or missing ENDED ends the run.

## 9. CANCEL and fresh restart (G.7)

Run only after G.6 passes:

```powershell
python .\tools\phase_g_audio_client.py cancel-restart `
  --host <edison-host> --port 22222 `
  --pcm-a C:\Users\tiio\Workspace\phase-g-pcm\a-440hz-4s.pcm `
  --pcm-b C:\Users\tiio\Workspace\phase-g-pcm\b-880hz-2s.pcm `
  --cancel-after 1.0
```

On one TCP connection the client waits for STARTED A, sends one second of A in
real time, sends CANCEL, waits for CANCELLED, then waits for STARTED B before
sending B and ending it.

PASS requires CANCELLED, prompt audible stop of A, no residual/reappearing A,
STARTED B, distinct 880 Hz B playback with B mouth synchronization, and ENDED B.

FAIL/STOP: missing CANCELLED, clearly continuing A, START B failure, stale A
during B, missing ENDED B, or any JVM/native crash.

## 10. Limited failures after normal success (G.8)

Do not perform G.8 unless G.0–G.7 all pass. Do not stress queue limits or send
large malformed packets on hardware.

### BUSY

In terminal 1, hold the single streaming connection:

```powershell
python .\tools\phase_g_audio_client.py probe --host <edison-host> --port 22222 --hold-seconds 20
```

While held, terminal 2 runs the same probe. Expected terminal 2 result is
decoded `ERROR BUSY`; terminal 1 remains healthy. An unexpected status, hang,
or process failure is STOP.

### Invalid state

Run exactly one bounded END-in-IDLE check:

```powershell
python .\tools\phase_g_audio_client.py invalid-state --host <edison-host> --port 22222
```

The exact wire sequence is the framed `audio_stream_v1` command,
`CONNECTION_READY`, then a one-byte record body `0x03` (END) while IDLE. The
production server must return framed `0x81 0x02` (`PROTOCOL_ERROR`) and close
that connection. The client sends no START, DATA, PCM, CANCEL, malformed length,
or oversized body. Any other response, an open connection after the error, or a
process failure is STOP.

### Disconnect cleanup

This check is optional. It opens the device only after G.5–G.7 have already
passed, sends exactly one 960-byte PCM DATA chunk after STARTED, closes the
socket without END/CANCEL, waits 0.5 seconds, and opens a fresh protocol-only
connection:

```powershell
python .\tools\phase_g_audio_client.py disconnect-active `
  --host <edison-host> --port 22222 `
  --pcm-a C:\Users\tiio\Workspace\phase-g-pcm\a-440hz-4s.pcm `
  --reconnect-delay 0.5
```

Expected observations are prompt cleanup of the short active session, no stale
audio continuing, and `CONNECTION_READY` on the fresh connection. `BUSY`, stale
audio, missing readiness, JVM/native failure, or an unexpected effect is STOP.

## 11. Universal STOP conditions

Stop the candidate using the pre-approved operator procedure, preserve logs,
classify the failure, and do not advance if any of these occurs:

- artifact or dependency hash mismatch;
- unexpected startup hardware behavior;
- unresolved TCP port conflict;
- native/ALSA dependency error before START;
- no CONNECTION_READY;
- START → AUDIO_ERROR;
- no sound after STARTED;
- sound without synchronized mouth LED;
- no ENDED after END;
- no CANCELLED after CANCEL;
- A clearly continues after CANCEL;
- START B fails;
- stale A reappears during B;
- JVM crash or native crash.

Do not respond to a STOP by disabling services, using `killall`, deleting lock
files, writing devices, or running an unreviewed diagnostic. Preserve the exact
command, timestamps, stdout/stderr, hashes, and operator observation.

## 12. Failure classification

| Classification | Typical symptom | Stage | Next safe evidence to inspect |
|---|---|---|---|
| `PROVENANCE_FAILURE` | commit/hash/dirty-tree mismatch | G.0 | Git status, exact hashes, build report |
| `BUILD_FAILURE` | javac/JAR creation fails | G.0 | `javac.log`, Java/Javac versions, source count |
| `PACKAGING_FAILURE` | missing JAR/class/manifest/lib/native layout | G.1 | candidate listing, manifest, hashes |
| `DEPLOYMENT_ENVIRONMENT_FAILURE` | transfer, permission, Java, directory error | G.2–G.3 | operator command/output, path, Java version |
| `STARTUP_SAFETY_FAILURE` | unapproved startup hardware effect | G.3 | startup log and operator observation; no extra probe |
| `PORT_CONFLICT` | bind failure or port already occupied | G.3 | read-only listener/process listing |
| `PROTOCOL_INTEGRATION_FAILURE` | missing/wrong STATUS, framing/state error | G.4–G.8 | client log plus server stdout/stderr |
| `JNI_LOAD_FAILURE` | UnsatisfiedLinkError / library not found | G.5 | java.library.path, native filename/hash, JVM error |
| `ALSA_OPEN_FAILURE` | START → AUDIO_ERROR at open/configure | G.5 | server exception and ALSA error text |
| `ALSA_ROUTING_FAILURE` | STARTED/writes succeed but intended speaker silent | G.6 | operator observation and existing routing config |
| `MOUTH_SYNC_FAILURE` | sound plays but mouth LED absent/out of sync | G.6–G.7 | timestamps, input hash, operator LED observation |
| `DRAIN_LIFECYCLE_FAILURE` | END hangs/errors or ENDED absent | G.6/G.7 | client barrier time, server drain/close error |
| `CANCEL_LIFECYCLE_FAILURE` | CANCELLED absent or A continues | G.7 | cancel timestamp, server drop/close error, observation |
| `GENERATION_ISOLATION_FAILURE` | old A appears during B | G.7 | ordered client log and operator audio observation |
| `RESTART_FAILURE` | START B fails after CANCELLED | G.7 | response/error, server open/cleanup log |
| `DISCONNECT_CLEANUP_FAILURE` | next connection BUSY/fails after disconnect | G.8 | connection timestamps and server cleanup log |
| `NATIVE_PROCESS_FAILURE` | JVM crash, native crash, fatal signal | any runtime stage | JVM/native crash file and last safe log; no rerun |

## 13. PC verification commands

These commands are localhost/device-free:

```powershell
python .\tools\test_phase_g_audio_client.py
python -m py_compile .\tools\phase_g_audio_client.py .\tools\test_phase_g_audio_client.py
```

The existing Java test mains must still report 14 and 16 passing groups. The
Phase G changes do not modify production Java and must not change those results.
