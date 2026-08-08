# RobotController Java再実装 段階的移行計画

作成日: 2026-08-03 JST
更新日: 2026-08-08 JST
前提ADR: `adr-java-only-redesign.md`
方針: greenfield implementation / legacy-spec preservation / small-step migration / hardware-safe

## 1. Migration strategy

現行Java applicationを新実装のsource baseとして直接大改修しない。現行`src/`はlegacy reference implementationとして保存し、正常系legacy protocol、axis／LED conversion、command behaviorのcharacterization sourceとして利用する。

新実装は`java_server/`へ構築し、次の順序でproduction replacementへ進む。

```text
freeze legacy reference
→ document and characterize current behavior
→ build new pure-Java core with Mock
→ implement in-memory audio and PCM envelope
→ add VSTONE adapters behind interfaces
→ integrate audio + mouth LED session
→ package without replacing production
→ manual hardware acceptance
→ controlled cutover with rollback
```

各phaseは、原則として次を守る。

```text
document contract
→ add tests
→ implement one boundary
→ verify compatibility and safety
→ record unresolved semantics
→ proceed only after exit gate
```

実機を使うphaseは最後に限定し、自動エージェントは実行しない。

### 1.1 2026-08-08 implementation checkpoint

hardware-free application sliceとして、Phase 2／3／4の必要部分、Phase 8／9／10のapplication skeleton、およびPhase 14のMock packaging skeletonを実装した。

完了した範囲:

* explicit configuration、composition root、lifecycle owner、`Main`
* backend `ready`後のTCP bind
* bounded connection executorとcontrolled socket shutdown
* legacy frame、strict UTF-8、dependency-free strict JSON、command／profile validation
* bounded single hardware worker、exception containment、generation再検査
* Pose／Motion／legacy Sota idle sequenceのreplacementとidempotent stop
* Mock audio sessionの別owned workerとin-memory WAV validation
* Mock backendまでのlocalhost TCP integration testとlegacy response contract
* thin executable `RobotController.jar` + internal module `lib/` layout

このcheckpointで未完了の範囲:

* VSTONE backendとvendor JAR解決
* real audio output、VSTONE mouth LED ownership／voice-sync
* robot別production profileとCommU／Dog idle integration
* 実機上のrunning interpolation stop semantics
* Edison packaging、deploy、systemd、manual hardware acceptance

したがって本checkpointはJava再実装全体またはproduction readinessの完了を意味しない。

### 1.2 2026-08-08 audio session checkpoint

Phase 10／12のうちVSTONE非依存部分を追加実装した。

完了した範囲:

* `AudioSessionCoordinator`によるaudio generation、playback、mouth synchronization、replacement、stop、failure、shutdownのownership
* strict validationで一度だけ生成したcanonical PCMをplaybackとenvelope解析へ共有
* `PlaybackClock.playedFrames()`を基準にした現在window選択
* pending値最大1件の`LatestHardwareCommandMailbox`とsingle hardware worker経由のlogical `MOUTH` write
* completion／replacement raceを含むexecute直前generation rejection
* normal completion、repeated stop、open／playhead／mouth output failure、application shutdownのmouth zeroとresource close
* manual scheduler、Mock playhead、latch／execution hookによる実時間sleep非依存test
* legacy `play_wav` TCPからMock audio／mouthまでのno-ACK integration test

未完了の範囲:

* Java SoundまたはVSTONE公開APIによるreal audio output
* VSTONE mouth LED adapter、LED ownership、native voice-sync disable／restore、hardware固有brightness mapping
* adapter failure時のhardware lifecycle degraded／failed方針
* Edisonおよび実機でのplayhead精度、LED更新、安全な継続動作のmanual acceptance

このcheckpointのlogical `MOUTH`出力はMock観測用であり、Sota mouth LED実機可否の確認ではない。

### 1.3 2026-08-08 hardware-free hardening checkpoint

VSTONE実装前の境界として、次を完了した。

* legacy v1全9 commandのraw wire normal-path testと`read_axes` semantic response確認
* signed 4-byte length、EOF、configured exact limit／limit+1、UTF-8、JSON、payload過不足、numeric／collection boundaryの固定corpus
* command-line設定値の既定値・明示値・不正値test。`--listen-port=0`は`--smoke-test`専用
* Java NIO `FileChannel.tryLock()`を使うconfigurable single-instance lockと、競合／backend init／TCP bind failureのrelease test
* startup順序をconfig validation → process lock → backend init → ready → listenへ固定
* thin JAR、runtime `lib/`、CLI説明`config/`からなる`robot-controller-dist/`
* effective configurationとlifecycle遷移のpayload非出力startup logging

未完了のまま維持する範囲はVSTONE backend、vendor JAR、real audio output、実mouth LED／voice-sync、Edison deploy、systemd、manual hardware acceptanceである。次phaseはこのcheckpointを維持したまま、公開VSTONE Java API boundaryとmanual acceptance gateを設計する。

## 2. Target repository layout

```text
RobotController/
├─ src/                    # legacy reference implementation; 原則凍結
├─ java_server/            # new Java implementation
│  ├─ pom.xml
│  ├─ robot-controller-core/
│  ├─ robot-controller-backend-mock/
│  ├─ robot-controller-backend-vstone/
│  └─ robot-controller-app/
├─ python_server/          # design/test oracle and historical evidence
└─ docs/
```

最初から多数の細粒度moduleへ分割しない。VSTONE dependency isolation、Mock-only test、composition boundaryに必要なmoduleだけを作る。

## 3. Global gates

すべてのphaseに適用する。

* Java 8 source／target compatibilityを維持する。
* default testはWindows + Mock backend + Mock audioで完結する。
* `sotalib.jar`をcore／protocol／audio-analysis testへ要求しない。
* legacy v1正常系のframeとresponse有無を変更しない。
* queue、connection、payload、decoded audio durationに明示的上限を設ける。
* VSTONE servo／LED／axis APIはsingle robot hardware workerからだけ呼ぶ。
* audio outputはowned audio executorで管理する。
* mouth LED periodic updateはlatest-value coalescingを使う。
* normal audio pathでtemporary WAV fileを作らない。
* new production codeで`aplay`と`killall`を使用しない。
* 実機deploy、実機test、servo／LED／torque操作は人間が手動で行う。
* historical evidenceを書き換えない。
* `robot_controller_edison_smoke.sha256`を変更、stage、commitしない。
* JARの逆コンパイル、bytecode disassembly、private member抽出を行わない。

## 4. Phase 0 — Checkpoint, branch, and documentation baseline

### Goal

方針転換後の基準点を固定し、Python移植branchからJava再実装作業を分離する。

### Actions

1. local branch、HEAD、remote、statusを確認する。
2. protected untracked fileのhashを確認する。
3. remote tip `d36f91a9826e35e256b4a7a0373a1ca4fe2ed8c4`との一致を確認する。
4. `feature/java-robot-controller-redesign`を作成する。
5. ADR、current architecture inventory、本migration planをrepositoryへ追加する。
6. `AGENTS.md`、`docs/requirements.md`、`docs/architecture.md`、`docs/migration-plan.md`の更新scopeをreviewする。
7. Codexへの個別指示はrepository外から与え、prompt、会話log、作業依頼文をcommitしない。
8. 恒久的な決定だけをADR、plan、requirements等へ反映する。

### Code policy

Documentation-only。Java／Python codeを変更しない。

### Exit criteria

* branch checkpointが記録されている。
* ADRがAcceptedになっている。
* protected fileが不変である。
* remote tracking branchが設定されている。
* Java-only greenfield方針と禁止事項が文書上のsingle source of truthになっている。

## 5. Phase 1 — Reproducible Java 8 build foundation

### Goal

Eclipse manual exportだけに依存しない、Windowsで再現可能なnew implementationのbuild／test shellを作る。

### Proposed direction

Maven reactorを第一候補とする。最初は次の4 moduleに限定する。

```text
robot-controller-core
robot-controller-backend-mock
robot-controller-backend-vstone
robot-controller-app
```

### Actions

* `java_server/`を作成する。
* Java 8 source／targetを固定する。
* JUnit等のtest dependencyを導入する。
* production dependencyとtest dependencyを分離する。
* VSTONE JARを`backend-vstone`だけへ隔離する。
* default reactor testからVSTONE moduleをcompile可能な形で扱う方法を決める。vendor JARがない環境では明示profileまたはdocumented skipを使用し、core testを妨げない。
* Mock-only compositionをdefaultにする。
* dependency inventory、hash、license／provenance表を作る。
* Eclipse projectとlegacy sourceを変更しない。

### Tests

* clean checkoutからcore／mock／app testを実行できる。
* Windowsでone-command testが動く。
* VSTONE JARなしでcore／mock testがcompile／passする。
* Java 8 bytecode targetを検証する。

### Exit criteria

* buildがdocumented one-commandで再現できる。
* legacy sourceをcompile targetへ混在させていない。
* production artifact layoutの方針が文書化されている。

## 6. Phase 2 — Protocol characterization and golden vectors

### Goal

現行clientが依存するlegacy v1正常系をbyte単位で固定する。

### Initial test targets

* 4-byte big-endian header
* zero-length frameのcodec behavior
* partial header／partial payload
* EOF
* negative length
* oversized frame
* command charset
* `play_pose` framing
* `play_motion` framing
* `stop_pose`
* `stop_motion`
* `play_idle_motion`
* `stop_idle_motion`
* `play_wav`
* `stop_wav`
* `read_axes` response frame
* unknown command
* malformed JSON

### Actions

* pure `FrameCodec`を新実装する。
* input／output streamを使うunit testを作る。
* Python側testと既存clientからgolden byte vectorsを移植する。
* commandごとのpayload requirementとresponse contractをtable化する。
* error時のconnection close policyを定義する。
* `play_wav` payloadはbinaryとしてそのままprotocol layerを通し、file pathへ変換しない。

### Compatibility rule

正常系の受理bytesとresponse有無を維持する。不正入力時のcrash、hang、unchecked exceptionは再現しない。

### Exit criteria

* protocol testがhardwareなしで100%実行できる。
* v1 command matrixがtestと文書で一致する。
* payload sizeとtimeoutのlimitが設定可能である。

## 7. Phase 3 — Command model and strict validation

### Goal

raw JSON／byte arrayをschedulerやbackendへ直接流さず、validated immutable command modelへ変換する。

### Actions

* `PlayPoseCommand`、`PlayMotionCommand`、`PlayAudioCommand`、`ReadAxesCommand`等を定義する。
* robot-independent validationとRobotProfile validationを分離する。
* `Msec`、`Pause`、`Speed`、motion length、WAV payload sizeのlimitを定義する。
* unknown field、unknown axis、unknown LED、wrong typeをrejectする。
* clamp／reject policyをaxis profileに明記する。
* error taxonomyを定義する。
* `PlayAudioCommand`はvalidated payload metadataを持つが、このphaseでは実再生しない。

### Tests

* boundary values
* wrong top-level JSON type
* missing required field
* unknown key
* overflow／underflow
* malformed UTF-8
* binary payload size
* Sota／CommU／Dog profile validation

### Exit criteria

* unvalidated inputがscheduler／backendへ到達しない。
* validation policyがrobot profileとcommand typeごとにtest化されている。

## 8. Phase 4 — Backend API, Mock robot, and Mock audio

### Goal

application logicからVSTONE dependencyとreal audio deviceを切り離す。

### Actions

* `RobotBackend`、`RobotCapabilities`、`RobotProfile`、`BackendFactory`を導入する。
* `AudioOutput`、`AudioPlaybackSession`、`PlaybackClock`を導入する。
* `MockRobotBackend`と`MockAudioOutput`を実装する。
* current axes、LED、mouth voice-sync、LED ownership、operation history、audio position、fault injectionを保持する。
* application composition rootでMock／VSTONEを選択する。

### Design constraints

* MotionとIdle Motionのsequence展開はschedulerに置く。
* Backendはprimitive operationを中心とする。
* Mock playback clockはtestから任意位置へ進められる。

### Tests

* apply pose
* read axes
* LED state
* LED ownership
* native mouth voice-sync state
* audio start／stop／completion
* controllable playback position
* fault injection
* close idempotence
* unsupported capability

### Exit criteria

* server、protocol、scheduler、audio testがVSTONE JARとaudio deviceなしで動く。
* Mockで全legacy commandのapplication effectを検証できる。

## 9. Phase 5 — In-memory WAV decode and canonical PCM

### Goal

一時fileなしでWAV payloadを検証・decodeし、audio outputとmouth analysisが共有するimmutable PCM modelを作る。

### Actions

* `WavPayloadValidator`または同等componentを実装する。
* RIFF／WAVE chunk structureをboundedに検証する。
* `ByteArrayInputStream`と`AudioSystem.getAudioInputStream()`を使用するadapterを作る。
* supported format setを既存client payloadから決める。
* canonical PCM representationを定義する。
* payload size、decoded frame count、duration、memory使用量に上限を設ける。
* normal pathでdisk writeを行わないtestを作る。

### Initial format gate

少なくとも次を明示する。

```text
encoding
sample rate
sample size
channels
endianness
frame size
maximum payload
maximum decoded duration
```

### Tests

* valid mono／stereo PCM WAV
* silence
* empty／truncated chunk
* invalid RIFF size
* unsupported encoding
* odd chunk padding
* frame misalignment
* oversized payload
* duration limit
* no filesystem access

### Exit criteria

* WAV bytesからcanonical PCMまでhardwareなしでdeterministically変換できる。
* temporary WAV fileを作るcode pathがない。

## 10. Phase 6 — Mouth envelope analysis

### Goal

同じPCMから、deterministicでtest可能なmouth brightness timelineを生成する。

### Actions

* `MouthEnvelopeAnalyzer`を実装する。
* configurable windowを20～50 ms範囲で扱う。
* RMSまたはmean absolute amplitudeを採用し、選択理由を文書化する。
* multi-channel aggregation、noise gate、compression、attack、release、clampを実装する。
* outputをtimestamp／frame rangeとbrightnessのimmutable sequenceにする。
* thresholdとcurveをconfiguration objectへ置く。

### Tests

* all-zero silence → all-zero brightness
* constant low amplitude
* constant high amplitude
* impulse
* clipped samples
* stereo imbalance
* attack smoothing
* release smoothing
* deterministic golden vectors
* brightness boundary

### Exit criteria

* 実時間、audio device、VSTONE APIなしでenvelopeを検証できる。
* magic numberがconfigurationへ集約されている。

## 11. Phase 7 — Audio playback engines

### Goal

memory上のaudioをowned sessionとして再生し、stop／position／completionをapplicationから管理する。

### Implementations

1. `JavaSoundAudioOutput`
   * `SourceDataLine`へcanonical PCMをstreaming writeする。
   * owned lineだけをstop／flush／closeする。
2. `VstoneWavePlayerOutput`
   * `CWavePlayer(AudioInputStream)`をadapter化する。
   * VSTONE module内だけに置く。
   * `getLine()`からplayback clockを取得する候補とする。

### Actions

* audio executorをsingle owned executorにする。
* playback session state machineを作る。
* generation replacementを実装する。
* `stop_wav`をidempotent session stopへmappingする。
* `drain`、`flush`、`close` policyを正常完了とcancelで分ける。
* playback positionのmonotonicityをMockでtestする。

### Tests

* start／complete
* stop before start
* double stop
* replacement
* write failure
* line unavailable
* partial write
* cancellation while blocked
* no external process
* no filesystem use

### Exit criteria

* Desktop／Mockでaudio session lifecycleがtestできる。
* `aplay`、`killall`、temporary WAV fileがnew codeに存在しない。
* VSTONE adapterはstatic compile/test可能だが、このphaseで実機実行しない。

## 12. Phase 8 — Lifecycle and safe startup

### Goal

listen前のinitialization完了と、明示的failure handlingを保証する。

### State machine

```text
starting → initializing → ready
                    ↘ degraded
                    ↘ failed
ready/degraded → stopping → stopped
```

### Actions

* composition rootがdependencyを順序立てて構築する。
* process lock取得をhardware object生成より前に置く。
* backend initialization成功後にだけTCP listenを開始する。
* startup時のServoOn、initial pose、torque、LEDを個別policyへ分離する。
* audio subsystem initializationはaudio deviceを無条件openしない。
* shutdown hookとcontrolled close sequenceを導入する。
* exit codeを定義する。

### Tests

* initialization success／failure
* ready前command拒否
* repeated stop
* partial initialization rollback
* close order
* process lock contention fail-closed
* audio subsystem unavailable policy

### Exit criteria

* startup時のhardware effectが明示的policyで説明できる。
* `ready`前のrobot command pathが存在しない。
* stop／closeが冪等である。

## 13. Phase 9 — Bounded network server

### Goal

legacy 1-connection-1-commandを維持しつつ、resource exhaustionを防ぐ。

### Actions

* bounded `ThreadPoolExecutor`を使用する。
* maximum connections、accept backlog、socket timeoutを設定する。
* command header、payloadごとのsize limitを適用する。
* unknown command、timeout、EOF、malformed payloadのclose policyを統一する。
* network threadはparse、validate、submitだけを行う。

### Tests

* saturation／rejection
* slowloris相当のpartial frame
* timeout
* abrupt disconnect
* concurrent clients
* shutdown中accept停止
* oversized WAV payload

### Exit criteria

* thread、queue、payloadがすべてboundedである。
* network threadからbackend／audio lineへの直接callがない。

## 14. Phase 10 — Single robot hardware worker and scheduler

### Goal

すべてのrobot hardware operationを単一workerで直列化し、Pose、Motion、Idle Motion、mouth LED ownershipを統一する。

### Operation envelope

```text
operationId
generationId
commandType
source
submittedAt
deadline
payload
completion
```

### Actions

* bounded robot hardware queueを導入する。
* enqueue時とexecute直前にlifecycle／generationを確認する。
* MotionをPose operation列へ展開する。
* Idle Motionを同じschedulerで管理する。
* direct PoseがMotion／Idleを置換するpolicyを定義する。
* read axesもhardware worker経由にする。
* timeoutとcompletion futureを導入する。
* mouth LED periodic values用latest-value mailboxを導入する。
* discrete robot commandとmouth updateのfairness／priorityを定義する。

### Tests

* FIFO／priority policy
* no concurrent backend calls
* stale generation rejection
* queue full
* deadline expiration
* Motion／Idle／Pose replacement
* read axes ordering
* mouth update coalescing
* no mouth backlog
* robot command starvation prevention

### Exit criteria

* backend callの最大同時実行数が常に1である。
* stale operationがbackendへ到達しない。
* MotionとIdle Motionがinterleaveしない。
* mouth LED updateがunboundedに蓄積しない。

## 15. Phase 11 — VSTONE robot and mouth LED adapters

### Goal

公式Java APIだけを使い、Sota／CommU／Dog adapterおよびSota mouth LED primitiveを実装する。

### Actions

* `backend-vstone` moduleへvendor importを隔離する。
* `SotaRobotBackend`、`CommuRobotBackend`、`DogRobotBackend`を実装する。
* capability差を明示する。
* existing converter rangeとgear ratioをprofileへ移す。
* initialize、read axes、apply pose、LED、closeをadapter化する。
* `getDefaultIDs()`と`getReadpos()`の対応を使い、配列順を独自推測しない。
* Sota mouth LED primitiveを次の公開API候補で実装する。

```text
LockLEDHandle(lockKey, [14])
disabeMouthLEDVoiceSync()
CRobotPose.SetLed({14 -> value})
play(pose, transitionMs, lockKey)
enabeMouthLEDVoiceSync()
UnLockLEDHandle(lockKey, [14])
```

* lock／play return valueとexceptionをtyped backend errorへ変換する。
* unsupported semanticsを成功として扱わない。

### Static tests

* adapter mapping
* profile completeness
* no vendor import outside VSTONE module
* mouth LED ID 14 mapping
* cleanup call order with facade／fake
* exception translation
* Java 8 compile

### Exit criteria

* core modulesに`jp.vstone.RobotLib` importがない。
* backendごとのsupported／unsupported operationが明示されている。
* vendor内部実装へ依存しない。
* 実機で確認していないbehaviorはunverifiedと明示されている。

## 16. Phase 12 — Integrated audio + mouth LED session

### Goal

同一PCM、audio playback clock、Sota mouth LED primitiveを一つのgeneration-scoped sessionとして統合する。

### Session sequence

```text
validate and decode WAV
→ compute mouth envelope
→ create audio generation
→ acquire mouth LED ownership
→ disable native mouth voice sync
→ start audio playback
→ read playback position
→ select current envelope value
→ coalesce mouth LED target
→ repeat until completion/cancel
→ mouth target 0
→ restore native mouth voice sync
→ release LED ownership
→ close playback session
```

### Actions

* `AudioPlaybackService`と`MouthLedSynchronizer`を統合する。
* playback positionからenvelope indexを決める。
* fake clockでdeterministic integration testを作る。
* audio completion、stop、replacement、disconnect、shutdownを同一cleanup pathへ収束させる。
* voice-sync switch後のfailureをfault injectionする。
* restoration／unlock failure時にbackend healthを`degraded`／`failed`へ遷移させる。
* mouth LED startup failure時のaudio-only fallback policyをconfiguration化する。

### Tests

* silence playback
* speech-like envelope
* playback position jump
* audio stops before envelope end
* replacement while playing
* stale animator cannot write
* LED queue coalescing
* mouth zero before restore
* restore before unlock
* lock failure before state change
* failure after voice-sync disable
* cleanup error aggregation
* repeated `stop_wav`

### Exit criteria

* Mock上でaudio positionとmouth LED timelineが対応する。
* stop／replacement後にold generationのLED writeがない。
* every state-changing pathにrestore／unlock attemptがある。
* real hardware未接続のままintegration testがpassする。

## 17. Phase 13 — Stop, cancel, disconnect, and recovery semantics

### Goal

停止概念を分離し、commandごとのcontractを明確にする。

### Actions

* logical cancel
* pending queue cancel
* running robot operation stop request
* physical safe stop capability
* running audio stop／flush
* mouth LED restoration
* disconnect policy
* repeated stop idempotence
* startup recovery policy

### Rules

* official APIが提供しないrunning robot stopを実装済みと表示しない。
* stop responseはlegacy v1では追加しない。
* disconnect後の継続／cancelをcommand種別ごとに固定する。
* process crash後のvoice-sync／lock recoveryを推測で自動化しない。公開APIによるmanual recovery手順とstartup gateを先に作る。

### Tests

* stop before start
* double stop
* stop while queued
* stop while running
* replacement race
* disconnect before／after acceptance
* audio line failure
* mouth restore failure
* shutdown during audio

### Exit criteria

* stop semanticsがtest名と文書で一意である。
* stop後に旧generationが新規backend／audio callを行わない。

## 18. Phase 14 — Packaging and deployment preparation

### Goal

既存運用artifactと比較可能なproduction packageを作る。

### Actions

* Main-Classを固定する。
* thin JAR + `RobotController_lib`または別方式を決定する。
* `System.properties` schemaとsampleを更新する。
* audio format、payload、duration、mouth LED profile設定を追加する。
* dependency hash manifestを生成する。
* startup command、working directory、log pathを文書化する。
* normal operationにwriteable working directoryが不要であることを確認する。
* rollback packageを用意する。
* existing Java baselineを削除しない。

### Tests

* clean package assembly
* missing dependency failure
* invalid configuration failure
* Mock composition smoke
* package content verification
* packageにtemporary audio path／aplay dependencyがないこと

### Exit criteria

* 同一inputから同一layoutを再生成できる。
* deployment前checklistとrollback手順が存在する。

## 19. Phase 15 — Manual hardware acceptance

### Goal

unit／integration testで確認できないJava Sound、VSTONE API、実機timingを、人間が段階的に確認する。

### Preconditions

* 全Windows testがpass
* static safety review完了
* exact artifact hash記録
* operator approval
* emergency procedure確認
* no automated deploy／test
* production RobotControllerと競合processが停止していることを人間が確認
* `vsmd_edison`は停止しない

### Order A: process and read-only

1. process start／whole-Sota lock／readinessだけを確認
2. read-only axes
3. controlled shutdown

### Order B: audio without manual mouth control

1. short supported PCM WAVをmemoryから再生
2. temporary fileが作られないことを確認
3. `CWavePlayer`／`SourceDataLine`のavailabilityを確認
4. completion、stop、replacementを確認
5. playback positionの単調性とおおよそのlatencyを記録

### Order C: mouth LED primitive

1. LED ID 14 ownership取得だけを確認
2. native mouth voice-sync disableの効果を確認
3. brightness 1～16の単発低輝度pulse
4. zero復帰
5. native voice-sync restore
6. unlock
7. postflightで通常状態を確認

### Order D: integrated short lip-sync

1. short mono PCM WAV
2. 50 ms update、brightness 0～16
3. stop
4. replacement
5. silence section
6. audio completion cleanup
7. operatorによる同期感とunexpected effectの記録

### Order E: interaction with robot motion

1. audio + mouth LED only
2. audio + read axes
3. audio + one small safe pose
4. bounded motion
5. stop／disconnect／shutdown

### Order F: robot expansion

1. Sota acceptance完了後にCommU
2. Dogはcapabilityを確認し、unsupported featureを明示

### Evidence

各試験はrevision、artifact hash、configuration、operator、実行command、input WAV hash／format、observed result、latency、LED behavior、cleanup result、unexpected effectを記録する。historical evidenceは後から書き換えない。

### Exit criteria

* robot別acceptance criteriaを満たす。
* legacy client正常系が確認される。
* audioにtemporary file、external `aplay`、global `killall`がない。
* mouth LEDがaudio positionに追従する。
* completion／stop／replacementでzero、restore、unlockが確認される。
* unsafe behaviorまたは未説明behaviorがない。

## 20. Phase 16 — Controlled production cutover

### Goal

既存production artifactを直ちに削除せず、新実装へ制御可能に切り替える。

### Actions

* current distributionをhash付きでbackupする。
* new distributionを別directoryへ配置する。
* startup commandを明示的に切り替える。
* smoke checklistを人間が実行する。
* rollback commandを事前確認する。
* initial operation期間はstructured logとhealth stateを確認する。

### Exit criteria

* rollback可能である。
* accepted client use casesが通る。
* old artifactが保存されている。
* production evidenceが記録されている。

## 21. Recommended first implementation slice

最初のcode変更は、実機behaviorへ触れない範囲に限定する。

```text
1. java_server Maven reactor
2. Java 8 build/test shell
3. FrameCodec and golden tests
4. backend/audio interfaces
5. MockRobotBackend and MockAudioOutput
6. in-memory WAV validator skeleton
7. canonical PCM model
8. MouthEnvelopeAnalyzer with deterministic tests
9. no VSTONE runtime invocation
10. no legacy source modification
```

このsliceでは`RobotSys`、legacy Pose／Motion、startup、vendor backend、real audio device、mouth LEDを実行しない。最初からproduction VSTONE integrationまで進めると、protocol、audio algorithm、hardware semanticsの差分を分離できなくなるためである。

## 22. Documentation updates required before code work

* `AGENTS.md`: final productをJava-only greenfieldへ変更し、Java 8、audio、mouth LED rulesを追加
* `docs/requirements.md`: Java runtime、Mock test、official API boundary、in-memory audioを反映
* `docs/architecture.md`: new single-process Java architectureへ置換
* `docs/migration-plan.md`: Python production migrationをhistorical扱いへ変更
* `docs/protocol-compatibility.md`: protocol contractは原則維持し、Java characterization testへの参照を追加
* audio／mouth LED design document: format、envelope、clock、cleanup、manual gatesを記録
* evidence files: historical recordとして変更しない

## 23. Completion definition

Java再実装が完了したと判断できるのは、次をすべて満たした場合である。

* Java 8 production artifactが再現可能にbuildできる。
* WindowsでMock backendとMock audioを用いたtestが実行できる。
* legacy v1正常系compatibilityがgolden testで固定されている。
* network、robot hardware queue、payload、audio durationがboundedである。
* all VSTONE robot callsがsingle robot hardware worker経由である。
* startup、stop、shutdownが明示的state machineで管理される。
* stopが冪等で、旧generationがhardware／audio commandを出さない。
* Sota、CommU、Dogがprofile／backendとして分離される。
* official Java API以外のproduction robot hardware accessがない。
* `play_wav`がdisk WAV fileを作らずmemory上で再生される。
* new production codeが`aplay`と`killall`を使用しない。
* same PCMからmouth envelopeが生成される。
* playback positionに基づいてmouth LEDが同期される。
* mouth LED updateがcoalescedされ、backlogを作らない。
* completion／stop／failureでmouth zero、voice-sync restore、unlockが試行される。
* manual hardware acceptance evidenceがrobot別に存在する。
* controlled rollback手順が存在する。
