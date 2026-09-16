# Phase G Acceptance Result

> Human-run acceptance record for the isolated Phase G production candidate.
> No Phase G STOP condition occurred. This acceptance does not close the
> separate intermittent XRUN investigation.

## Provenance

- Date/time and timezone: 2026-09-16, Asia/Tokyo / JST (+09:00)
- Operator: Takamasa Iio
- Repository HEAD: `8e0502be496710a512d3286eb62e1bf8cdd12f94`
- Production source baseline: `bd299ae1bbc0d0514d5b60a0ca2d45125a01f1d6`
- Branch: `feature/java-audio-streaming`
- Repository working tree state during final build: CLEAN
- Acceptance repository state (no unexpected tracked/untracked/staged changes): PASS
- Production source baseline integrity: PASS
- PC candidate directory: `C:\Users\tiio\Workspace\RobotController-phase-g-production-8e0502b\RobotController`
- PC build report: `C:\Users\tiio\Workspace\RobotController-phase-g-production-8e0502b\phase-g-build-report.txt`
- Edison candidate directory: `/home/root/robotcontroller_phase_g_production_8e0502b`
- TCP port: `22222`
- RobotController.jar SHA-256: `2AACCEA0C7558D25411D69F6D8BCFBAD27D4ED040F50F3989CA75DCC3E6FE400`
- System.properties SHA-256: `9A08F313F839812F6634353F0772EEA6A43BDD776F9F1D79C2C2E54B487EE166`
- phase-g-build-report.txt SHA-256: `A3B39E4C5C8C7BE332112740E7DA5567A6DE9BF35D7538B31BDA6CE4974A174C`
- `librobotcontroller_alsa.so` SHA-256: `1119B2666681885CAA03C22C8F16118A2A849AA14B3B7158D1962500E716306B`
- Native expected SHA-256 matched: PASS
- Dependency hash verification (6/6): PASS
- PCM A path / SHA-256 / bytes: `C:\Users\tiio\Workspace\phase-g-pcm\a-440hz-4s.pcm` / `BB69EC3FAB7B06E66B822D90CFB52F5D53BC4BDDD22A4136F9756C9B2C026A4D` / 192000
- PCM B path / SHA-256 / bytes: `C:\Users\tiio\Workspace\phase-g-pcm\b-880hz-2s.pcm` / `31529F371FFD65981AFFDC6B114FB4862A107453FD46493575941BDB1B3AF289` / 96000
- PCM format: 24000 Hz, mono, S16_LE, 48000 bytes/second
- Java version on build PC: Eclipse Temurin OpenJDK 1.8.0_502
- Build PC `java`: `C:\Program Files\Eclipse Adoptium\jdk-8.0.502.7-hotspot\bin\java.exe`
- Build PC `javac`: `C:\Program Files\Eclipse Adoptium\jdk-8.0.502.7-hotspot\bin\javac.exe`
- Java version on Edison: `java version "1.8.0_40"`; Java(TM) SE Runtime Environment (build 1.8.0_40-b25); Java HotSpot(TM) Client VM (build 25.40-b25, mixed mode)
- Application class compatibility: all 49 application classes have major version 52

### Dependency hashes

| Dependency | SHA-256 |
|---|---|
| `core-2.2.jar` | `C6963B3DDC11B8A1FF4EBF65E93314CC6AF341685F70C98C752094FA59BEF492` |
| `gson-2.8.5.jar` | `233A0149FC365C9F6EDBD683CFE266B19BDC773BE98EABDAF6B3C924B48E7D81` |
| `javase-2.2.jar` | `CC32F41B3FCFF840BCDD08F14D24E7C170E382BD5C5A81A072AC075E66CC8426` |
| `jna-4.1.0.jar` | `1AA37E9EA6BAA0EE152D89509F758F0847EAC66EC179B955CAFE0919E540A92E` |
| `json-20180813.jar` | `518080049BA83181914419D11A25D9BC9833A2D729B6A6E7469FA52851356DA8` |
| `sotalib.jar` | `7C3B45F42139A651E2C5D021C18EBF217CDB9BE5AF25569E910221D88D71BFFA` |

PC and Edison deployment hashes matched for RobotController.jar,
System.properties, `librobotcontroller_alsa.so`, and all six dependency JARs.

## G.0 — Artifact verification

- Result: PASS
- Production baseline is an ancestor of Repository HEAD: PASS
- Production/test inputs match the baseline: PASS
- Acceptance repository state clean: PASS
- Production source count: 23
- Generated class count: 49
- Dependencies 6/6: PASS
- Java 8 runtime/compiler: PASS
- Java compile: PASS
- Compiler errors: 0
- Compiler warnings: 47 (serial: 6; cast: 41; permitted existing legacy warnings)
- Manifest Main-Class: PASS (`main.App`)
- Manifest Class-Path: PASS (the six expected libraries)
- `main/App.class` exactly once: PASS
- All application class versions equal 52: PASS
- Candidate JAR hash recorded: PASS
- Notes: The warnings were reviewed as existing permitted legacy warnings and were not acceptance failures.

## G.1–G.2 — Isolated package and deployment

### G.1 — Isolated package

- Result: PASS
- Candidate is isolated from production: PASS
- Candidate layout complete: PASS
- Candidate root contained exactly `RobotController.jar`, `System.properties`, `lib/`, and `native/`.
- `lib/` contained exactly the six expected dependency JARs.
- `native/` was empty before human native placement.
- Candidate total files before native placement: 8
- Unexpected `.class`, `.java`, `.c`, `.h`, `.log`, `.tmp`, diagnostic JAR, or diagnostic `.so`: none
- Diagnostic strings and diagnostic artifact hashes: absent

### G.2 — Isolated deployment

- Result: PASS
- Existing production was not overwritten/stopped: PASS
- Deployed hashes match PC records: PASS
- Edison target: `/home/root/robotcontroller_phase_g_production_8e0502b`
- The target did not exist before deployment.
- RobotController.jar, System.properties, and all six dependency JAR hashes matched between PC and Edison.
- The fixed production native source hash was verified before copy, and the destination native hash matched afterward: `1119B2666681885CAA03C22C8F16118A2A849AA14B3B7158D1962500E716306B`.
- Diagnostic native code was not used.

## G.3 — Startup

- Result: PASS
- Port conflict absent: PASS
- Legacy RobotSys startup effects explicitly approved: YES
- Observed startup effects matched reviewed behavior: PASS
- Native/ALSA error before START absent: PASS
- JVM/listener stable: PASS
- Startup command: `java -Djava.library.path=./native -jar RobotController.jar`
- Before startup, port 22222 was not in use.
- Startup output included `[Info][CRobotSock]Connected server` and `[Info][CRobotMotion]MasterCtrlPeriod 16667.0`.
- After startup, `tcp6 :::22222` was listening and the JVM remained alive.
- Notes: No physical behavior beyond the reviewed startup effects is asserted. After all tests, the operator stopped the candidate with Ctrl+C, after which no listener remained on port 22222. This shutdown did not stop SotaAppManager or `vsmd_edison`.

## G.4 — CONNECTION_READY

- Result: PASS
- CONNECTION_READY received: PASS
- Probe sent no START/PCM: PASS
- Audio native/ALSA path remained unopened by probe: PASS
- Listener remained active on port 22222: PASS
- Notes: Client result was `PROBE PASS`. No audio-native failure or effect was observed from the probe.

## G.5 — STARTED

- Result: PASS
- STARTED received: PASS
- JNI library discovery: PASS
- `snd_pcm_open("default")`: PASS
- Notes: In this implementation STARTED is returned only after the production native load/open path succeeds. Playback subsequently succeeded.

## G.6 — Playback and END

- Result: PASS
- Speaker playback: PASS
- Mouth LED synchronization: PASS
- END → ENDED: PASS
- Unexpected hardware effect absent: PASS
- Test input: PCM A, 440 Hz, 4 seconds, 192000 bytes
- Client pacing: 200 chunks; nominal 4.000 seconds; send span 3.980 seconds
- Pacing configuration: `prebuffer_chunks=0`; `max_catchup_chunks=0`
- Pacing observations: `catchup_events=0`; `unrecoverable_rebases=0`; `rebases=0`; `max_lateness_ms=14.899`; `max_send_ms=1.890`
- Protocol sequence: CONNECTION_READY → STARTED → ENDED
- Client result: `NORMAL PASS pcm_bytes=192000`
- Notes: The operator observed approximately four seconds of normal playback from the intended speaker and mouth LED synchronization. No JVM/native crash or unexpected runtime effect occurred.

## G.7 — CANCEL

- Result: PASS
- CANCEL timestamp: `2026-09-16T07:39:58.915516Z`
- CANCELLED timestamp: `2026-09-16T07:39:59.050918Z`
- CANCELLED received: PASS
- Audio A stopped: PASS
- Residual A after CANCEL absent: PASS
- PCM sent before CANCEL: 48000 bytes (nominal 1.000 second)
- Observed cancel latency: Protocol CANCEL-to-CANCELLED interval approximately 135 ms; acoustic stop was observed promptly but was not instrumented.
- Notes: A played normally, stopped after approximately one second, and was not heard again.

## G.7 — Fresh restart

- Result: PASS
- STARTED B: PASS
- B playback: PASS
- Mouth LED B synchronization: PASS
- Stale A replay absent: PASS
- ENDED B: PASS
- Test input: PCM B, 880 Hz, 2.000 nominal seconds, 96000 bytes
- Protocol sequence: START B → STARTED → END B → ENDED
- Client result: `CANCEL_RESTART PASS`
- Pacing B: `prebuffer=0`; `catch-up=0`; `rebases=0`; `max_lateness_ms=13.681`
- Notes: B playback was normal and distinct from A; no stale A replay was heard.

## G.8 — Limited failures

### BUSY

- Result: PASS
- Terminal 1 received CONNECTION_READY at approximately `2026-09-16T07:42:45.228274Z`, held the connection for 20 seconds, and completed `PROBE PASS`.
- Terminal 2 received `ERROR BUSY (0x01)` at approximately `2026-09-16T07:42:50.510976Z`.
- Terminal 2 displayed `result FAIL: Server ERROR: BUSY (0x01)` because BUSY is an error for an ordinary probe invocation. For this G.8 check, ERROR BUSY was the expected server result.
- The held first connection remained healthy.

### Invalid protocol state

- Result: PASS
- Sequence: CONNECTION_READY → send END while IDLE → `ERROR PROTOCOL_ERROR (0x02)` → connection closed
- Client result: `INVALID_STATE PASS error=PROTOCOL_ERROR connection=CLOSED`
- The server remained listening on port 22222 afterward.
- Expected server exception: `main.TCPServer$ProtocolFailure: END received while idle.` at `TCPServer.java:166`
- Explanation: This test intentionally sent END while idle. The server detected a ProtocolFailure, sent PROTOCOL_ERROR, and closed the offending socket. `RecvThread` currently calls `printStackTrace()` for that ProtocolFailure, so the stack trace is expected current behavior, not a Phase G runtime acceptance failure. The RobotController process and listener remained alive, and the subsequent disconnect-active check passed.

### Disconnect cleanup

- Result: PASS
- Sequence: CONNECTION_READY → START → STARTED → send exactly 960 PCM bytes → close active connection → wait 0.5 seconds → fresh CONNECTION_READY
- Client result: `DISCONNECT_ACTIVE PASS fresh_connection=CONNECTION_READY`
- The active streaming slot was released, no BUSY state remained, and the JVM/native path remained operational.
- Audible playback was not required for the 20 ms fixture fragment.

## Observed logs

Representative excerpts only; no binary PCM is included.

```text
Startup:
[Info][CRobotSock]Connected server
[Info][CRobotMotion]MasterCtrlPeriod 16667.0
tcp6 :::22222 LISTEN

G.4:
STATUS CONNECTION_READY
result PROBE PASS

G.5/G.6:
STATUS CONNECTION_READY
STATUS STARTED
pacing pcm_bytes=192000 chunks=200 nominal_seconds=4.000 send_span_seconds=3.980
STATUS ENDED
result NORMAL PASS pcm_bytes=192000

G.7 CANCEL and restart:
CANCEL sent 2026-09-16T07:39:58.915516Z
STATUS CANCELLED 2026-09-16T07:39:59.050918Z
STATUS STARTED
STATUS ENDED
result CANCEL_RESTART PASS

G.8 BUSY:
2026-09-16T07:42:45.228274Z STATUS CONNECTION_READY
2026-09-16T07:42:50.510976Z ERROR BUSY (0x01)

G.8 invalid state:
ERROR PROTOCOL_ERROR (0x02)
main.TCPServer$ProtocolFailure: END received while idle.
    at main.TCPServer.java:166
result INVALID_STATE PASS error=PROTOCOL_ERROR connection=CLOSED

G.8 disconnect-active:
STATUS CONNECTION_READY
STATUS STARTED
connection closed after 960 PCM bytes
STATUS CONNECTION_READY
result DISCONNECT_ACTIVE PASS fresh_connection=CONNECTION_READY
```

## Failure record

- First failed/STOP stage: None
- Failure classification: None
- Exact symptom: None
- Last successful barrier: G.8 disconnect cleanup / fresh CONNECTION_READY
- Relevant timestamps: See observed logs
- Relevant safe logs/information: See G.0–G.8 records
- Candidate stopped with approved procedure: YES
- Later hardware stages skipped: N/A

## Diagnostic artifact preservation

- Diagnostic checkpoint branch: `codex/phase-g-xrun-diagnostics`
- Diagnostic checkpoint commit: `ae4b7f6a83df0592e6e60d52bb8eb8ddbffe0244`
- This separate branch preserves diagnostic code and evidence; it is not the production acceptance branch.
- The production acceptance JAR does not contain diagnostic runtime code.

## Overall

- Result: ACCEPTED
- Acceptance scope: Phase G streaming runtime only
- Mandatory G.0–G.8 tests: all PASS
- Optional disconnect-active check: PASS
- Intermittent XRUN investigation: OPEN
- Operator signature/approval: Takamasa Iio

### Remaining limitations/observations

**INTERMITTENT XRUN OBSERVED / NOT RELIABLY REPRODUCIBLE**

Intermittent ALSA XRUN / playback underrun remains an open known issue. During
earlier long-playback diagnostics, an audible dropout was observed together
with `snd_pcm_writei -> -EPIPE` (`Broken pipe`) and a successful
`snd_pcm_recover()`. The root cause is **partially isolated / not fully
closed**; Phase G acceptance does not close this issue.

Diagnostic evidence further showed:

- `snd_pcm_writei` can block for roughly 40–55 ms as normal ALSA backpressure; a slow write alone does not imply a dropout.
- Mid-stream Java queue starvation/inter-write gaps up to approximately 64.235 ms occurred without an audible dropout.
- One actual dropout correlated with ALSA XRUN / `-EPIPE`.
- The `aplay` control completed 10/10 without dropout.
- The exact rare trigger was not reproduced reliably.

The acceptance result is therefore limited to the successful human-run Phase G
streaming runtime matrix above. It does not claim that the XRUN/dropout issue is
resolved or that production audio is fully reliable.
