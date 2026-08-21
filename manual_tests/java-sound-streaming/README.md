# Java Sound `SourceDataLine` streaming feasibility gate

This directory contains a standalone, human-operated diagnostic for answering one narrow
question on Intel Edison: can Java SE 8 stream a reference WAV through
`SourceDataLine.write()` to the speaker, and does Sota's already-configured native mouth
voice-sync visibly follow that playback without any LED command from the probe?

The probe does not establish production readiness or physical acoustic latency. Its timing
values report Java API call timing and line positions only. A result is one operator
observation for the tested Edison image, Java runtime, audio provider, file, and settings.

## Scope and safety boundary

`src/SourceDataLineProbe.java` uses Java SE 8 `javax.sound.sampled` and `java.io` APIs only.
It has no VSTONE JAR dependency, does not import `jp.vstone.*`, does not invoke `aplay` or
any other process, does not access a device file directly, and does not issue servo, LED,
torque, or mouth voice-sync commands. It is deliberately outside `java_server/pom.xml` and
must not be added to the production Maven reactor.

The `wav` mode produces speaker audio. Codex must not compile or execute this probe on
Edison, connect to Edison, deploy it, run audio playback, or observe the robot. A human
operator performs the manual procedure with a safety observer where required. Start with
a conservative system volume and use a short, non-sensitive reference WAV whose speaker
and mouth behavior was already characterized; this gate does not require another `aplay`
run.

Direct mouth-LED investigation is paused while Java Sound streaming/native mouth-sync
feasibility is evaluated first, because production audio is intended to bypass temporary
WAV files and external playback processes. This probe does not replace or erase existing
Gate 1A/1B observations and does not add another LED-lock probe.

## CLI

Compile with a Java 8 JDK on the target only after human review:

```sh
cd manual_tests/java-sound-streaming
mkdir -p out
javac -encoding UTF-8 -source 8 -target 8 -d out src/SourceDataLineProbe.java
```

Inventory mixers without opening or starting an audio line:

```sh
java -cp out SourceDataLineProbe list
```

Run the guarded WAV streaming probe:

```sh
java -cp out SourceDataLineProbe wav reference.wav 20 100
```

Both duration arguments must be base-10 integers in `1..60000`. All CLI arguments and WAV
format/conversion requirements are validated before a `SourceDataLine` is opened. The
operator is shown the selected line and actual buffer size after `open`, then must press
ENTER before `start`; entering `q` closes the line and streams without playback.

Before confirming playback, the operator must verify the expected robot/asset, Java version,
reference WAV hash and duration, conservative volume, and displayed mixer/format/buffer. If
any item is unexpected, enter `q` and record an abort. This first probe intentionally has no
asynchronous playback-cancel command, so use a short reference clip. If unexpected physical
behavior occurs after start, follow the site's human-approved emergency procedure and record
the observation; do not stop services, kill unrelated processes, remove lock files, or issue
robot commands as a workaround.

The expected outcome is one bounded result label plus timing/statistics and human observations.
There is no runtime installation or robot-state rollback: normal and failure paths close their
owned Java Sound line and streams, and the probe changes no persistent configuration. A cleanup
exception requires human verification of the audio/runtime state before any later gate. The
operator may remove the locally compiled `out` directory after preserving source/artifact hashes
with the evidence.

## `list` mode

`list` prints the Java version and every value returned by `AudioSystem.getMixerInfo()`.
For each mixer it prints index, name, vendor, version, description, all advertised source
line information, and whether a `SourceDataLine` class is advertised. It only queries
public Java Sound inventory APIs and never opens or starts a line.

## WAV decode and streaming path

The WAV is opened with `AudioSystem.getAudioInputStream(file)`. The source format is
printed, then the probe requires a finite positive sample rate and one or two channels.
The canonical playback target is:

```text
PCM_SIGNED
16 bit
source sample rate
source channel count (mono or stereo)
little endian
```

If the source is not already exactly canonical, the probe requires Java Sound to advertise
that conversion and obtains a converted `AudioInputStream`. Unsupported conversion aborts;
the probe does not guess a different playback format.

The complete WAV or decoded PCM is never copied into memory. One frame-aligned byte array
is allocated and reused in this loop:

```text
AudioInputStream.read(chunk)
  -> SourceDataLine.write(frame-aligned portion)
  -> next read
```

The frame and byte calculations are:

```text
frames = round(sampleRate * durationMs / 1000)
bytes  = frames * frameSize
```

The result must be nonzero, frame-aligned, and fit Java Sound's signed integer byte-count
API. A 20 ms chunk and 100 ms requested buffer are the initial recommended values. The
line is opened with `line.open(targetFormat, requestedBufferBytes)`. Requested and actual
buffer sizes are both printed; equality is not assumed.

Candidate mixers that advertise the target format, the selected concrete line class, and
the selected line information are printed. Standard Java Sound does not expose the owning
mixer from every arbitrary `Line`, so candidate output is diagnostic context rather than
an assertion about provider ownership. No reflection or private-field inspection is used.

## Playback, partial writes, and cleanup

After operator confirmation, playback follows this sequence:

```text
line.start()
  -> repeated streaming read/write
  -> normal EOF
  -> line.drain()
  -> line.stop()
  -> line.close()
  -> stream close
```

Each `SourceDataLine.write()` request is frame-aligned. The return value is checked and a
partial positive write advances the offset and retries the remaining frames. Zero,
negative, over-reported, or non-frame-aligned returns fail closed.

`drain()` is called only after normal EOF. Operator abort or any exception uses best-effort
`line.stop()`, `line.flush()`, `line.close()`, and stream close. A cleanup exception is
printed and attached as a suppressed exception so it does not hide the original failure.

## Timing and statistics

`System.nanoTime()` records program start, line-open completion, line start, first-write
begin/return, EOF, drain completion, and close completion. At completion the probe also
reports `getLongFramePosition()` and `getMicrosecondPosition()`.

The final statistics include source/target formats, chunk and buffer settings, actual
buffer bytes, read/write calls, total bytes read/written, total frames written, line
positions, and wall-clock time from `start` through `drain`. These are software/provider
diagnostics and do not prove physical speaker latency or mouth-sync accuracy.

## Operator observation and gate result

Immediately before `line.start()`, the probe states that it calls neither external playback
nor VSTONE APIs, controls no mouth LED or servo, and writes no LED state. The operator is
asked to observe speaker audio and the mouth LED. After playback it records:

```text
Operator: was audio playback normal? [yes/no]:
Operator: did the mouth LED visibly follow the audio? [yes/no]:
Operator: were clicks/dropouts heard? [yes/no]:
Operator note:
```

The bounded result labels are:

```text
audio YES, mouth YES, clicks/dropouts NO
  -> SOURCE_DATA_LINE_WITH_NATIVE_MOUTH_SYNC_OBSERVED

audio YES, mouth NO
  -> SOURCE_DATA_LINE_AUDIO_ONLY_OBSERVED

all other combinations
  -> SOURCE_DATA_LINE_PLAYBACK_NOT_ACCEPTED
```

Do not generalize these labels beyond the recorded manual observation. In particular,
visible mouth movement does not prove how native sync is implemented, and no movement does
not prove that all Java Sound configurations lack native sync.

If Java Sound playback is accepted but native mouth sync is not observed, the next separate
gate may evaluate the VSTONE public `CWavePlayer(AudioInputStream)` and its public
`getLine()` result. `CWavePlayer` is intentionally not imported or implemented here.

## Manual evidence template

```text
Date:
Operator / safety observer:
Robot / asset ID:
Edison image:
Java version:
Probe source revision / SHA-256:
Reference WAV provenance / SHA-256:
Reference WAV format:
Command:

Mixer / provider diagnostic:
Selected line class / info:
Source format:
Target format:
Chunk ms / bytes:
Requested buffer ms / bytes:
Actual buffer bytes:
Timing and statistics:

Speaker audio normal: YES / NO
Mouth LED visibly followed audio: YES / NO
Clicks/dropouts heard: YES / NO
Operator note:
Probe result:
Exception / cleanup exception:
Unexpected physical behavior:
Stop condition / action taken:
```
