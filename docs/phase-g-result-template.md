# Phase G Acceptance Result

> Complete this record during a human-run acceptance. A STOP condition makes
> Overall `REJECTED`; do not continue to later hardware stages.

## Provenance

- Date/time and timezone:
- Operator:
- Repository HEAD:
- Production source baseline:
- Branch:
- Repository working tree state:
- Acceptance repository state (no unexpected tracked/untracked/staged changes): PASS / FAIL / NOT_RUN / UNKNOWN
- Production source baseline integrity: PASS / FAIL / NOT_RUN / UNKNOWN
- PC candidate directory:
- Edison candidate directory:
- TCP port:
- RobotController.jar SHA-256:
- `librobotcontroller_alsa.so` SHA-256:
- Native expected SHA-256 matched: PASS / FAIL / NOT_RUN / UNKNOWN
- Dependency hash verification (6/6): PASS / FAIL / NOT_RUN / UNKNOWN
- PCM A path / SHA-256 / bytes:
- PCM B path / SHA-256 / bytes:
- Java version on build PC:
- Java version on Edison:

## G.0 — Artifact verification

- Production baseline is an ancestor of Repository HEAD: PASS / FAIL / NOT_RUN / UNKNOWN
- Production/test inputs match the baseline: PASS / FAIL / NOT_RUN / UNKNOWN
- Acceptance repository state clean: PASS / FAIL / NOT_RUN / UNKNOWN
- Dependencies 6/6: PASS / FAIL / NOT_RUN / UNKNOWN
- Java 8 runtime/compiler: PASS / FAIL / NOT_RUN / UNKNOWN
- Java compile: PASS / FAIL / NOT_RUN / UNKNOWN
- Manifest Main-Class: PASS / FAIL / NOT_RUN / UNKNOWN
- Manifest Class-Path: PASS / FAIL / NOT_RUN / UNKNOWN
- Candidate JAR hash recorded: PASS / FAIL / NOT_RUN / UNKNOWN
- Notes:

## G.1–G.2 — Isolated package and deployment

- Candidate is isolated from production: PASS / FAIL / NOT_RUN / UNKNOWN
- Existing production was not overwritten/stopped: PASS / FAIL / NOT_RUN / UNKNOWN
- Candidate layout complete: PASS / FAIL / NOT_RUN / UNKNOWN
- Deployed hashes match PC records: PASS / FAIL / NOT_RUN / UNKNOWN
- Notes:

## G.3 — Startup

- Port conflict absent: PASS / FAIL / NOT_RUN / UNKNOWN
- Legacy RobotSys startup effects explicitly approved: YES / NO / NOT_RUN / UNKNOWN
- Observed startup effects matched reviewed behavior: PASS / FAIL / NOT_RUN / UNKNOWN
- Native/ALSA error before START absent: PASS / FAIL / NOT_RUN / UNKNOWN
- JVM/listener stable: PASS / FAIL / NOT_RUN / UNKNOWN
- Notes:

## G.4 — CONNECTION_READY

- CONNECTION_READY received: PASS / FAIL / NOT_RUN / UNKNOWN
- Probe sent no START/PCM: PASS / FAIL / NOT_RUN / UNKNOWN
- Audio native/ALSA path remained unopened by probe: PASS / FAIL / NOT_RUN / UNKNOWN
- Notes:

## G.5 — STARTED

- STARTED received: PASS / FAIL / NOT_RUN / UNKNOWN
- JNI library discovery: PASS / FAIL / NOT_RUN / UNKNOWN
- `snd_pcm_open("default")`: PASS / FAIL / NOT_RUN / UNKNOWN
- Notes:

## G.6 — Playback and END

- Speaker playback: PASS / FAIL / NOT_RUN / UNKNOWN
- Mouth LED synchronization: PASS / FAIL / NOT_RUN / UNKNOWN
- END → ENDED: PASS / FAIL / NOT_RUN / UNKNOWN
- Unexpected hardware effect absent: PASS / FAIL / NOT_RUN / UNKNOWN
- Notes:

## G.7 — CANCEL

- CANCEL timestamp:
- CANCELLED received: PASS / FAIL / NOT_RUN / UNKNOWN
- Audio A stopped: PASS / FAIL / NOT_RUN / UNKNOWN
- Residual A after CANCEL absent: PASS / FAIL / NOT_RUN / UNKNOWN
- Observed cancel latency:
- Notes:

## G.7 — Fresh restart

- STARTED B: PASS / FAIL / NOT_RUN / UNKNOWN
- B playback: PASS / FAIL / NOT_RUN / UNKNOWN
- Mouth LED B synchronization: PASS / FAIL / NOT_RUN / UNKNOWN
- Stale A replay absent: PASS / FAIL / NOT_RUN / UNKNOWN
- ENDED B: PASS / FAIL / NOT_RUN / UNKNOWN
- Notes:

## G.8 — Limited failures

- BUSY: PASS / FAIL / NOT_RUN / UNKNOWN
- Invalid protocol state: PASS / FAIL / NOT_RUN / UNKNOWN
- Disconnect cleanup: PASS / FAIL / NOT_RUN / UNKNOWN
- Notes:

## Observed logs

```text
Paste or reference the preserved client/server log excerpts, without binary PCM.
```

## Failure record

- First failed/STOP stage:
- Failure classification:
- Exact symptom:
- Last successful barrier:
- Relevant timestamps:
- Relevant safe logs/information:
- Candidate stopped with approved procedure: YES / NO
- Later hardware stages skipped: YES / NO

Allowed classifications:

```text
PROVENANCE_FAILURE
BUILD_FAILURE
PACKAGING_FAILURE
DEPLOYMENT_ENVIRONMENT_FAILURE
STARTUP_SAFETY_FAILURE
PORT_CONFLICT
PROTOCOL_INTEGRATION_FAILURE
JNI_LOAD_FAILURE
ALSA_OPEN_FAILURE
ALSA_ROUTING_FAILURE
MOUTH_SYNC_FAILURE
DRAIN_LIFECYCLE_FAILURE
CANCEL_LIFECYCLE_FAILURE
GENERATION_ISOLATION_FAILURE
RESTART_FAILURE
DISCONNECT_CLEANUP_FAILURE
NATIVE_PROCESS_FAILURE
```

## Overall

- Result: ACCEPTED / REJECTED
- Acceptance scope: Phase G streaming runtime only
- Remaining limitations/observations:
- Operator signature/approval:
