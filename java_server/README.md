# RobotController Java server

`java_server/` is the Java 8 reimplementation area. The repository-root `src/` tree remains the legacy reference implementation and is not part of this Maven reactor.

## Implemented slice

The current hardware-free slice provides:

* an explicit application configuration and `Main` composition root;
* a configurable non-blocking Java NIO single-instance process lock acquired before backend initialization;
* lifecycle sequencing `starting -> initializing -> ready`, with TCP bind only after Mock backend initialization;
* a fixed-size, bounded connection executor and controlled socket shutdown;
* strict legacy v1 framing, UTF-8 decoding, dependency-free JSON parsing, command validation, and command-specific frame limits;
* a bounded single hardware worker that rechecks generation immediately before each backend call;
* Pose, Motion, and legacy Sota idle-pose scheduling with replacement/cancel generations;
* memory-only WAV validation followed by one canonical PCM object shared by Mock playback and mouth-envelope analysis;
* an `AudioSessionCoordinator` that owns audio generation, replacement, idempotent stop, completion, failure, and shutdown cleanup;
* playhead-based mouth synchronization using `playedFrames()` rather than advancing a FIFO timeline from wall-clock sleeps;
* a latest-value mailbox with at most one pending mouth update, serialized through the existing hardware worker;
* generation-aware mouth updates and zero cleanup that prevent late completion or stale pending work from affecting a replacement session;
* the legacy response rule: only `read_axes` returns a frame; no ACK or v1 error frame was added;
* command-by-command localhost wire tests for all nine legacy v1 commands, plus a fixed malformed/boundary corpus from the TCP socket through the Mock backend.

The Mock composition uses the documented Sota public axis and LED names. Values outside the documented ranges are rejected rather than silently clamped.

## Modules

* `robot-controller-core`: frame codec, strict command model/validation, generation tokens, the bounded hardware worker, latest-value hardware mailbox, backend/audio contracts, canonical PCM, WAV decoding, and mouth-envelope analysis.
* `robot-controller-backend-mock`: deterministic robot/audio fakes, LED value/thread history, state snapshots, operation history, controllable/failable playback clock, blocking hooks, and one-shot fault injection.
* `robot-controller-backend-vstone`: reserved boundary for public VSTONE Java API adapters. It remains empty and requires no vendor JAR.
* `robot-controller-app`: configuration, lifecycle owner, bounded TCP server, protocol adapter, scheduler/dispatch, composition root, and executable packaging.

## Build and test

From the repository root on Windows:

```powershell
.\java_server\mvnw.cmd `
    -f .\java_server\pom.xml `
    clean verify
```

The compiler source/target is Java 8. Default tests use only localhost, Mock robot/audio implementations, and in-memory payloads. They do not access VSTONE hardware, serial devices, audio devices, system services, or external network services.

The Windows wrapper contains a small compatibility guard for PowerShell environments where a normal Maven user directory reports a null filesystem-link `Target`.

## Executable Mock package

The app build creates a self-contained distribution directory with a thin executable JAR, its runtime project dependencies, and the command-line configuration reference:

```text
robot-controller-app/target/robot-controller-dist/
|- RobotController.jar
|- lib/
   |- robot-controller-core-0.1.0-SNAPSHOT.jar
|  `- robot-controller-backend-mock-0.1.0-SNAPSHOT.jar
`- config/
   `- runtime-options.txt
```

Mock mode must be selected explicitly; there is no implicit production fallback:

```powershell
Set-Location .\java_server\robot-controller-app\target\robot-controller-dist
java -jar .\RobotController.jar `
    --backend=mock `
    --listen-host=127.0.0.1 `
    --listen-port=22222 `
    --process-lock-path=.\robot-controller.lock
```

A hardware-free startup/close smoke check is available:

```powershell
Set-Location .\java_server\robot-controller-app\target\robot-controller-dist
java -jar .\RobotController.jar `
    --backend=mock `
    --listen-port=0 `
    --smoke-test `
    --process-lock-path=.\smoke-test.lock
```

Supported command-line settings are `listen-host`, `listen-port`, `connection-workers`, `connection-queue-capacity`, `hardware-queue-capacity`, `command-frame-limit`, `json-frame-limit`, `wav-frame-limit`, `audio-duration-limit-ms`, `mouth-sync-interval-ms`, `socket-timeout-ms`, `shutdown-timeout-ms`, `process-lock-path`, and `backend`. Configuration is command-line only; invalid, unknown, empty, or out-of-range values fail before application composition. Port zero is reserved for explicit smoke mode.

Startup order is configuration validation, non-blocking process-lock acquisition, backend initialization, `ready`, then TCP bind/listen. The default lock path is `robot-controller.lock` under the platform `java.io.tmpdir`; relative configured paths are normalized to absolute paths. The parent directory must already exist. Lock contention fails closed without retrying, deleting the lock file, initializing the backend, or binding a socket. Normal shutdown and startup failure release the lock but intentionally retain the path.

Startup logs include the implementation version, backend, listen address, bounded worker/queue sizes, frame/audio limits, timeouts, process-lock path, and lifecycle transitions. Binary WAV/JSON payloads are never logged.

The thin layout intentionally leaves future VSTONE vendor JARs external under `lib/`; the current distribution contains no vendor JAR and no vendor JAR is unpacked into `RobotController.jar`.

## Deliberately not implemented

This slice does not implement or test a VSTONE backend, servo/LED/torque device access, a real audio output, Java Sound on Edison, actual mouth LED output/locking/voice-sync, deployment, systemd integration, or manual hardware acceptance. Selecting `--backend=vstone` fails before any vendor adapter or listen socket is constructed.

Mock `MOUTH` values demonstrate orchestration and serialized logical output only; they do not establish that a physical Sota mouth LED can be controlled safely. No temporary WAV file, `aplay`, or `killall` path is present in the new Java implementation.
