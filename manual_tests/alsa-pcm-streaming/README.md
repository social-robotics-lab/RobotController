# ALSA `default` raw-PCM streaming / native mouth-sync feasibility gate

This directory contains a standalone, human-operated Intel Edison probe for one narrow
question: can Java 8 stream raw PCM through JNI and the public libasound API to ALSA PCM
`default`, producing normal speaker audio while Sota's already-configured native mouth
voice-sync visibly follows it?

The probe is a feasibility gate, not a production backend. It does not implement a TCP
session, queue, cancellation architecture, RobotController integration, or direct mouth
control. One run records one operator observation for the tested Edison image, ALSA
configuration, native library, JVM, input file, and settings; it is not a general guarantee.

## Existing human observations and working hypothesis

The following observations predate this probe and are recorded here as inputs to the gate:

| Path | Speaker | Native mouth sync |
| --- | --- | --- |
| `aplay` of the reference WAV through its default route | YES | YES |
| `aplay -D plughw:2,0` of the reference WAV | YES | NO |
| raw reference PCM through `aplay -D default` | YES | YES |
| Java Sound `SourceDataLine` probe | NO, despite normal Java write accounting | NO |
| Java/JNI/libasound `default`, without `LD_PRELOAD`, before this bootstrap | `snd_pcm_open()` failed | Not reached |
| Same JNI probe with `LD_PRELOAD=/usr/lib/libasound.so.2` | Opened; operator entered `q` before playback | Not observed |
| Java/JNI/libasound `default`, internal RTLD_GLOBAL bootstrap, no `LD_PRELOAD` | YES | YES |

The observed `/etc/asound.conf` playback route was conceptually:

```text
default -> plug -> plugvssnd -> type vssnd -> dmixer -> hw:CODEC
```

Therefore, the ALSA `default` path is the current primary candidate for preserving native
mouth sync without spawning an external player. These observations do **not** establish that
`vssnd` is the sole mouth-sync implementation or explain its private implementation. This
probe relies on ALSA configuration resolution and does not recreate `plugvssnd`, `vssnd`,
`dmixer`, or `hw:CODEC` itself.

Before this bootstrap change, the no-`LD_PRELOAD` JNI run failed while ALSA tried to load
`/usr/lib/alsa-lib/libasound_module_pcm_vssnd.so`; `snd_pcm_open("default")` returned `-6`.
With `/usr/lib/libasound.so.2` preloaded into process-global scope, the same probe opened
successfully and reported 2229 buffer frames and 557 period frames, matching the previously
observed default-route values. The operator entered `q`, so that run produced no audio.

The current probe-specific hypothesis is that the externally loaded `vssnd` PCM plugin needs
public ALSA symbols that were not visible in global dynamic-loader scope during the original
Java/JNI run, and that preloading promoted libasound into that scope. This is not yet a general
finding and does not identify `vssnd` as the sole mouth-sync implementation.

### Confirmed human playback evidence, 2026-08-21

The existing `raw` mode was compiled and run manually on Edison without `LD_PRELOAD` after
the internal RTLD_GLOBAL bootstrap was added:

```text
PCM:               24000 Hz, mono, S16_LE
Chunk:             20 ms, 960 bytes, 480 frames
Requested latency: 100 ms
Actual buffer:     2229 frames
Actual period:     557 frames
Total written:     61056 bytes, 30528 frames

Audio normal:                 YES
Native mouth LED sync:        YES
Problematic click/dropout:    NO
Result: ALSA_DEFAULT_STREAMING_WITH_NATIVE_MOUTH_SYNC_OBSERVED
```

The human operator also observed `/usr/lib/libasound.so.2.0.0`,
`/usr/lib/alsa-lib/libasound_module_pcm_vssnd.so`, and `/tmp/.vssnd.bin` mapped in the Java
process. These are observations for that runtime and run, not a portable guarantee or an
analysis of private plugin implementation.

## Scope and safety boundary

The Java source incrementally reads a raw PCM file with `FileInputStream`; it never loads the
whole file into memory. The JNI source uses the public libasound PCM API and the public dynamic
loader API. Before any ALSA call, it reopens `/usr/lib/libasound.so.2` with
`RTLD_NOW | RTLD_GLOBAL` so later ALSA external plugins can resolve its public symbols. The
primary gate opens the literal PCM name `default` in blocking playback mode. Do not substitute
a hardware PCM for the primary gate.

The absolute libasound path is specific to the validated Edison runtime and is not yet a
portable production configuration. The probe does not set `LD_PRELOAD`, use `dlsym()`, replace
the linked ALSA API, or directly load the `vssnd` plugin. `/etc/asound.conf` and ALSA's standard
plugin loader remain responsible for route and plugin resolution.

The probe:

- creates no WAV or temporary audio file;
- starts no external process;
- uses no Java Sound API;
- imports no VSTONE class and calls no VSTONE API;
- issues no mouth LED, other LED, servo, or torque command;
- accesses no device path directly;
- changes no ALSA or RobotController configuration; and
- is outside `java_server/pom.xml` and must not be added to the Maven reactor.

This probe produces physical speaker output when run. Codex and other automated agents must
not connect to Edison, deploy, compile on Edison, open an ALSA device, run this probe, run an
external player, or observe the robot. A human operator reviews, builds, and runs it manually.
Use a short, non-sensitive reference PCM already characterized through the `default` route,
a conservative system volume, and the site's approved emergency procedure.

Stop before starting if the robot/asset, input hash or format, Java version, native build,
PCM name, ALSA configuration, volume, buffer/period values, or command differs from the
reviewed plan. After playback starts, unexpected physical behavior, persistent audio, a
cleanup error, or operator uncertainty is a stop condition. Do not stop services, kill
unrelated processes, remove lock files, or issue robot commands as a workaround.

## Files

```text
manual_tests/alsa-pcm-streaming/
|-- README.md
|-- src/
|   `-- AlsaPcmProbe.java
`-- native/
    `-- alsa_pcm_probe_jni.c
```

The JNI header is deliberately not committed. A human generates
`native/generated/AlsaPcmProbe.h` from the exact Java source used for the run.

## Java CLI

```text
AlsaPcmProbe raw <file.pcm> <sample-rate> <channels> <chunk-ms> <latency-ms> [pcm-name]

AlsaPcmProbe cancel-restart <stream-a.pcm> <stream-b.pcm> <sample-rate> <channels>
    <chunk-ms> <latency-ms> [pcm-name]
```

The optional PCM name defaults to `default`. The primary gate is:

```sh
java \
  -Djava.library.path=. \
  -cp out \
  AlsaPcmProbe \
  raw \
  reference.pcm \
  24000 \
  1 \
  20 \
  100 \
  default
```

The cancel/restart gate uses:

```sh
java \
  -Djava.library.path=. \
  -cp out \
  AlsaPcmProbe \
  cancel-restart \
  stream-a.pcm \
  stream-b.pcm \
  24000 \
  1 \
  20 \
  100 \
  default
```

The initial input is headerless `S16_LE`, 24000 Hz, mono PCM. The probe validates that the
file is non-empty, frame-aligned, and no longer than 60 seconds. It does not parse WAV and
performs no format conversion.
For this format:

```text
frame size = 1 channel * 2 bytes = 2 bytes
20 ms      = 24000 frames/sec * 0.020 sec = 480 frames
chunk size = 480 frames * 2 bytes = 960 bytes
```

For other CLI values, the chunk frame count is rounded to the nearest whole frame and printed
before playback. The primary gate must use the fixed values above.

For `cancel-restart`, stream A and stream B must be different, non-empty, frame-aligned files
of at most 60 seconds each. Prepare two clearly distinguishable 24 kHz mono S16_LE utterances.
Stream A must be long enough for the operator to hear it and press ENTER before EOF; stream B
should be a short utterance with clearly different content. The probe does not synthesize
audio, and raw PCM assets are not committed to this repository.

## JNI surface and ALSA sequence

The Java class declares only this native surface:

```text
long openPcm(String pcmName, int sampleRate, int channels, int latencyMicros)
int writePcm(long handle, byte[] data, int offset, int length)
long getBufferFrames(long handle)
long getPeriodFrames(long handle)
void drainPcm(long handle)
void dropPcm(long handle)
void closePcm(long handle)
```

`openPcm` allocates a small native context and returns an opaque `jlong`; conversion uses
`intptr_t`. An internal registry validates handles, permits the context to be freed on close,
and makes null, stale, and repeated close requests harmless. The Java owner serializes access,
zeros its handle before closing, and prevents use after close. JNI has no thread or queue.

The blocking bootstrap/open/setup sequence is:

```text
dlopen("/usr/lib/libasound.so.2", RTLD_NOW | RTLD_GLOBAL)
snd_pcm_open(name, SND_PCM_STREAM_PLAYBACK, 0)
snd_pcm_set_params(
    SND_PCM_FORMAT_S16_LE,
    SND_PCM_ACCESS_RW_INTERLEAVED,
    channels,
    sampleRate,
    softResample=1,
    latencyMicros)
snd_pcm_get_params(... actualBufferFrames, actualPeriodFrames)
```

The first bootstrap call retains its handle in `g_libasound_global`; repeated calls succeed
without another `dlopen()`. The handle intentionally remains open for process lifetime. The
probe does not call `dlclose()` after a PCM closes and does not add a `JNI_OnUnload` lifecycle.
This keeps global symbols available while ALSA external plugins may still need them.

Requested and actual buffer/period values are not assumed to be equal. The probe prints the
actual frame counts returned by `snd_pcm_get_params()` before operator confirmation.

Each Java chunk and native range is checked for frame alignment. JNI converts bytes to frames,
calls `snd_pcm_writei()`, and advances across partial positive writes until the complete range
has been accepted. A negative write is passed to `snd_pcm_recover()`. Recovery is bounded to
three attempts per Java native-write call; failure or exhaustion becomes `java.io.IOException`.
There is no unbounded retry and no silent XRUN suppression.

Native failures report the operation, ALSA error code, and `snd_strerror()` text, for example:

```text
snd_pcm_open(default) failed: -2: No such file or directory
```

A bootstrap failure becomes `java.io.IOException` and includes the absolute path, the
`RTLD_NOW|RTLD_GLOBAL` purpose, and `dlerror()` text. It is not printed only to native stderr,
and the probe does not continue to `snd_pcm_open()` after bootstrap failure.

The native layer never terminates the JVM. Normal EOF uses `snd_pcm_drain()` followed by close.
Abort and exception paths attempt `snd_pcm_drop()` and close. The Java input stream is closed on
all paths; cleanup failures are retained rather than hiding the primary failure.

## Incremental Java streaming and diagnostics

The Java loop fills one reusable chunk buffer, preserving frame boundaries even if a file read
is short:

```text
FileInputStream read(s) until one chunk or EOF
  -> one JNI write of the frame-aligned bytes
  -> native partial-write/recovery loop
  -> next file read(s)
```

It records with `System.nanoTime()`:

- open complete;
- first native write begin and end;
- EOF;
- drain complete; and
- close complete.

It also prints file-read calls, Java-to-native write calls, bytes read/written, and frames
written. These measurements describe the software path only; they do not prove physical
latency or visual synchronization accuracy.

## Cancel/restart mode design

This mode is a human-only feasibility check for a Realtime-style response replacement:

```text
fresh stream A PCM session
  -> incremental A writer thread
  -> operator cancel request
  -> A writer observes cancel flag between chunk writes
  -> snd_pcm_drop() (never drain A)
  -> snd_pcm_close()
  -> bounded writer join confirms complete A ownership release
  -> fresh stream B PCM session
  -> incremental B playback
  -> normal B EOF
  -> snd_pcm_drain()
  -> snd_pcm_close()
```

The initial gate deliberately chooses close/reopen instead of reusing the dropped handle with
`snd_pcm_prepare()`. This costs another open but gives the clearest isolation between old and
new audio and answers the narrower feasibility question first: can buffered A audio be
discarded before a fresh B stream starts? It does not decide the production session design.

The A writer is the sole owner of A's `NativePcm`, input stream, `writePcm()`, `dropPcm()`, and
`closePcm()` calls. The operator/main thread only sets a volatile cancel flag and waits. Thus
drop or close never races a native write, and B is not opened until the A writer has terminated.
There is no path by which the old A writer can write into B's fresh handle.

The main thread waits at most 5 seconds for A's first write and at most 5 seconds for A writer
termination. A timeout is a hard failure: B is not opened, `Thread.stop()` is never used, and
the daemon A writer retains cleanup ownership if its current blocking native write later
returns. Under the expected blocking ALSA behavior, each 20 ms write returns and the writer
performs best-effort drop and close itself.

Cancel timestamps include the request, A's last successful write, drop begin/end, A close,
B open begin/end, and B first write begin/end. The report calculates request-to-drop-complete
and request-to-B-first-write elapsed time. These are software timestamps and are not acoustic
stop/start latency measurements.

No new JNI methods are added. The mode reuses `openPcm`, `writePcm`, `dropPcm`, `drainPcm`, and
`closePcm`; the existing RTLD_GLOBAL bootstrap and ALSA configuration resolution are unchanged.

## Human-only build on Edison

Review the exact sources first. The validated Edison runtime has `alsa-lib 1.0.28-r0` and
`/usr/lib/libasound.so.2`, but not system-installed development headers. The human operator
uses the previously downloaded and extracted `alsa-lib-dev 1.0.28-r0` headers under
`~/alsa-pcm-gate/packages/alsa-lib-dev-unpack`; this procedure does not install that package.
With a Java 8 JDK and C99 compiler on the human-controlled target:

```sh
cd manual_tests/alsa-pcm-streaming
mkdir -p out native/generated

javac \
  -encoding UTF-8 \
  -source 8 \
  -target 8 \
  -d out \
  src/AlsaPcmProbe.java

javah \
  -classpath out \
  -d native/generated \
  AlsaPcmProbe

ALSA_DEV_ROOT="$HOME/alsa-pcm-gate/packages/alsa-lib-dev-unpack"

gcc \
  -D_POSIX_C_SOURCE=200809L \
  -std=c99 \
  -fPIC \
  -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -I"$ALSA_DEV_ROOT/usr/include" \
  -Inative/generated \
  -o librobotcontroller_alsa_probe.so \
  native/alsa_pcm_probe_jni.c \
  /usr/lib/libasound.so.2 \
  -ldl
```

`-D_POSIX_C_SOURCE=200809L` is retained because the human Edison build with the ALSA 1.0.28
headers required it to avoid the observed `struct timespec` redefinition conflict. Linking
keeps the ordinary libasound dependency and adds `-ldl` only for the bootstrap API.

The human operator must confirm the Edison compiler layout, `JAVA_HOME`, JNI headers,
libasound headers/library, and output architecture. Do not fetch vendor binaries or private
headers to make the build pass. Preserve the source, generated header, shared-library, and
reference PCM hashes in local operator evidence.

## Human-only run: Step A, pre-playback RTLD_GLOBAL gate

Use the same `reference.pcm` previously observed to produce speaker audio and native mouth
sync through raw `aplay -D default` playback; another external-player run is not part of this
gate. From this directory, run the primary command shown above **without `LD_PRELOAD`**. The
probe itself must not set or inject `LD_PRELOAD`.

After ALSA has opened and the actual parameters are displayed, the probe prints:

```text
ALSA PCM STREAMING FEASIBILITY GATE

PCM name:
default

Input:
24000 Hz
mono
S16_LE

Chunk: 20 ms / 960 bytes
Requested latency: 100 ms
Actual buffer frames: ...
Actual period frames: ...

This probe:
- does NOT call an external player
- does NOT create WAV files
- does NOT use Java Sound SourceDataLine
- does NOT call VSTONE Java APIs
- does NOT control mouth LED
- does NOT control servo
- does NOT write LED state

Observe:
1. speaker audio
2. mouth LED
3. clicks/dropouts

Press ENTER to start.
q aborts.
```

For Step A, do not press ENTER during remote operation. Reaching the confirmation prompt with:

```text
PCM name:
default
Actual buffer frames: 2229
Actual period frames: 557
Press ENTER to start.
q aborts.
```

is recorded as the human pre-playback observation
`RTLD_GLOBAL_BOOTSTRAP_OPEN_OBSERVED`. Enter `q` and require:

```text
RESULT:
ABORTED_BEFORE_PLAYBACK
```

This observation means only that the no-`LD_PRELOAD` process reached the guarded prompt with
the expected ALSA parameters. It does not change the probe's existing RESULT classifications
and is not evidence of speaker output or mouth sync.

## Later human-only physical playback gate

Only when a human operator is physically able to observe the robot and has approved the
physical gate may they press ENTER. On normal EOF, the operator is asked:

```text
Operator: was audio playback normal? [yes/no]:
Operator: did the mouth LED visibly follow the audio? [yes/no]:
Operator: were clicks/dropouts heard? [yes/no]:
Operator note:
```

The bounded classifications are:

```text
audio YES, mouth YES, clicks/dropouts NO
  -> ALSA_DEFAULT_STREAMING_WITH_NATIVE_MOUTH_SYNC_OBSERVED

audio YES, mouth NO
  -> ALSA_DEFAULT_STREAMING_AUDIO_ONLY_OBSERVED

audio NO, or any other unaccepted combination
  -> ALSA_DEFAULT_STREAMING_PLAYBACK_NOT_ACCEPTED
```

Even the first result is one observation, not proof of a general property or of `vssnd`'s
implementation. Production persistent TCP streaming, `AudioStreamSession`, cancellation,
playhead semantics, and an ALSA backend may be designed only after reviewing an accepted gate.

## Human-only cancel/restart physical gate

Run the `cancel-restart` command only with a human physically able to hear the speaker and see
the mouth LED. Before playback the probe prints both paths, format, chunk, requested and actual
ALSA parameters, safety exclusions, and this guarded prompt:

```text
ALSA CANCEL / RESTART FEASIBILITY GATE

Press ENTER to begin Gate.
q aborts.
```

After ENTER, wait until stream A is clearly audible. The probe then displays:

```text
STREAM A PLAYING

Press ENTER to CANCEL A and START B.
q aborts whole Gate.
```

Press ENTER while A is speaking. The writer stops accepting A chunks, calls
`snd_pcm_drop()`—not drain—closes A, and terminates. Only after the bounded join succeeds does
the main thread print `STREAM A CANCELLED` / `STREAM B STARTING` and open B. The first complete
B write prints `STREAM B PLAYING`. B plays to normal EOF, drains, and closes.

At completion, answer:

```text
Operator: did stream A play normally before cancel? [yes/no]:
Operator: did stream A stop promptly after cancel? [yes/no]:
Operator: was any old stream A audio heard after stream B began? [yes/no]:
Operator: did stream B start and play normally? [yes/no]:
Operator: did the mouth LED follow stream A before cancel? [yes/no]:
Operator: did the mouth LED follow stream B? [yes/no]:
Operator: were problematic clicks/pops/dropouts heard? [yes/no]:
Operator note:
```

The classifications are evaluated in this order:

```text
A not stopped promptly, or old A heard after B began
  -> ALSA_CANCEL_NOT_ACCEPTED

A cancel observed, but A/B playback otherwise not accepted or problematic audio heard
  -> ALSA_CANCEL_OBSERVED_RESTART_NOT_ACCEPTED

A and B audio accepted, but native mouth sync missing for either stream
  -> ALSA_CANCEL_RESTART_AUDIO_ONLY_OBSERVED

A normal before cancel, prompt stop, no A leak, B normal,
mouth sync for A and B, and no problematic click/pop/dropout
  -> ALSA_CANCEL_RESTART_WITH_NATIVE_MOUTH_SYNC_OBSERVED
```

Cutting arbitrary PCM can produce a small click. This Gate rejects a clearly unpleasant or
large click/pop, repeated abnormal audio, or a dropout that prevents normal B playback; it does
not require mathematically click-free cancellation.

Any A writer timeout, A EOF before cancellation, native error, cleanup error, unexpected
physical behavior, or operator uncertainty fails the Gate. B is never opened before confirmed
A writer termination. A cancel/failure uses drop and close; B failure uses drop and close; only
normal B EOF uses drain and close.

## Manual evidence template

```text
Date:
Operator / safety observer:
Robot / asset ID:
Edison image:
Java version:
ALSA configuration identity / hash:
Probe source revision / SHA-256:
Generated JNI header SHA-256:
Native library SHA-256:
Reference PCM provenance / SHA-256:
Reference PCM format and duration:
Command:

PCM name:
Requested sample rate / channels / format:
Chunk ms / frames / bytes:
Requested latency:
Actual buffer frames:
Actual period frames:
Timing and statistics:

Speaker audio normal: YES / NO
Mouth LED visibly followed audio: YES / NO
Clicks/dropouts heard: YES / NO
Operator note:
Probe result:
Exception / cleanup exception:
Unexpected physical behavior:
Stop condition / action taken:
RTLD_GLOBAL bootstrap pre-playback result:
```

For the cancel/restart Gate, additionally record both PCM hashes and recognizable contents,
A/B statistics, every cancel/restart timestamp, request-to-drop and request-to-B-write elapsed
times, all seven observations, and the bounded result label.

The no-`LD_PRELOAD` raw playback result is now observed as successful for the recorded runtime.
Cancel latency, residual A audio, B restart playback, and B native mouth sync remain **UNKNOWN**
until a human completes the cancel/restart Gate.
