# ADR: RobotControllerをJavaオンリーで再実装する

* Status: Accepted — implementation pending
* Initial decision date: 2026-08-03
* Amended: 2026-08-04 — greenfield Java implementation、in-memory audio、PCM-driven mouth LEDを追加
* Amended: 2026-08-08 — VSTONE公開API監査に基づきSota mouth LED ID 14仮定を撤回し、Case B manual gateを追加
* Scope: production RobotController architecture
* Supersedes: Python production command serverを最終成果物とする方針

## 1. Context

既存RobotControllerは、VSTONE製Sota、CommU、DogをTCP経由で制御するJava 8 applicationであり、VSTONE公式の`jp.vstone.RobotLib`を使用している。

Python全面移植では、legacy protocol、validation、Mock backend、lifecycle、scheduler、process lock、read-only VSMD transportなどの設計・実装・testを蓄積できた。一方、Sotaのproduction servo write pathをPythonで安全に再実装するには、vendor SDK内部のtarget address、変換、補間、enable、stop、rollbackを確定する必要がある。

`sotalib.jar`には解析許可を裏付ける明示的licenseが確認されておらず、vendor SDKの逆コンパイル、bytecode disassembly、内部protocol推定を行わない方針を採用した。VSTONE公式Java APIを迂回したVSMD direct writeは、servo／motion production pathとして採用できない。

同時に、現行Java実装には次の問題がある。

* startup時にServoOn、initial Pose、torque、LED設定を暗黙に実行する。
* TCP listenとhardware initializationにreadiness gateがない。
* connection threadとqueueがunboundedである。
* Pose、Motion、Idle Motionのgeneration／ownershipがない。
* stopがqueue clearやstale command rejectionを行わない。
* `read_axes`がnetwork threadからvendor APIを直接呼ぶ。
* lifecycle、controlled shutdown、Mock backend、Windows unit test基盤がない。
* `play_wav`は固定一時fileを作り、external `aplay`を起動する。
* `stop_wav`は`killall aplay`によりowned process以外も停止し得る。
* mouth LEDはapplicationが波形から制御せず、`aplay`と既存systemの音声連動に依存する。

これらは局所的な修正ではなく、process lifecycle、networking、scheduler、hardware ownership、audio resource ownershipにまたがる。現行sourceを継ぎ足しながら改修すると、legacy behaviorと新behaviorの境界が不明確になり、regressionの原因を分離しにくい。

## 2. Decision

production RobotControllerを、Java 8互換の単一process applicationとして新規実装する。

現行`src/`はlegacy reference implementationとして原則凍結し、正常系protocolと変換behaviorのcharacterization source、comparison oracle、fallbackとして保存する。新実装は`java_server/`に置く。

```text
Legacy TCP client
    ↓
Bounded TCP server
    ↓
Legacy v1 protocol adapter / strict frame codec
    ↓
Validated immutable commands
    ↓
Command service / lifecycle manager
    ↓
Motion scheduler + audio session manager
    ↓
┌───────────────────────────────┬──────────────────────────────┐
│ Single robot hardware worker  │ Owned single audio executor  │
│ servo / LED / read / lock     │ PCM playback / audio line    │
└───────────────────────────────┴──────────────────────────────┘
    ↓                                          ↓
RobotBackend                              AudioOutput
├─ MockRobotBackend                      ├─ MockAudioOutput
├─ SotaRobotBackend                      ├─ JavaSoundAudioOutput
├─ CommuRobotBackend                     └─ VstoneWavePlayerOutput
└─ DogRobotBackend
    ↓
VSTONE official Java API
```

## 3. Production languageとsource strategy

* production serverはJavaだけで構成する。
* Python processとJava sidecar間のIPCは導入しない。
* Edison上ではJava 8で動作させる。
* buildとunit／integration testはWindows上で実行可能にする。
* 新実装を`java_server/`へ作成する。
* legacy `src/`はcharacterizationに必要な最小修正を除き変更しない。
* 新実装がmanual hardware acceptanceを通過するまで、既存production artifactを置換しない。

## 4. Hardware API boundary

* production robot hardware accessはVSTONE公式Java APIの公開範囲だけを使用する。
* `sotalib.jar`の逆コンパイル、disassembly、private implementation抽出を行わない。
* `/dev/ttyMFD1`、`/dev/i2c-1`へ直接accessしない。
* VSMD internal memory addressやwrite sequenceをproduction Javaへ移植しない。
* 公式APIに存在しないstop／cancel／rollbackを存在すると仮定しない。
* VSTONE importは`robot-controller-backend-vstone`へ隔離する。

Pythonで確認した口LED低レベルevidenceは、physical identity、cleanup requirement、risk理解のhistorical sourceとして保存するが、新Java production implementationの直接依存にはしない。

## 5. Compatibility boundary

legacy protocol v1の正常系を維持する。

* 4-byte big-endian length header
* command nameを第1frameとして受信
* 必要なcommandはpayloadを第2frameとして受信
* 原則1 connection 1 command
* `read_axes`のみ正常時response frameを返す
* responseを読まないlegacy commandへACKを追加しない
* `play_wav`はWAV binary payloadを受け取る
* `stop_wav` commandを維持する

互換対象外:

* legacy crash、hang、race、resource exhaustion
* malformed inputの暗黙変換
* JSON key orderと空白
* unsafe startupとunsafe stop
* 一時WAV file、`aplay` process、`killall`という内部実装
* audio playback開始時刻や口LED波形の完全一致

## 6. Concurrency boundary

* network threadはVSTONE APIとaudio lineを直接操作しない。
* すべてのservo、LED、axis read、VSTONE lock operationをbounded single robot hardware workerへ渡す。
* audio playbackはowned single audio executorで行い、blocking audio I/Oによってrobot hardware workerを占有しない。
* Pose、Motion、Idle Motion、mouth LED、audio lifecycleを明示的に調停する。
* operation IDとgeneration ID／cancel tokenを持たせる。
* stopまたは置換されたgenerationは、以後hardware／audio commandを発行できない。
* lifecycle stateを`starting`、`initializing`、`ready`、`degraded`、`stopping`、`stopped`、`failed`で表現する。
* `ready`前にrobot commandを受理しない。
* mouth LED periodic updateは通常FIFOへ全件蓄積せず、latest-value coalescing mailboxを使用する。

## 7. Backend abstraction

`RobotBackend`は、vendor APIをprotocol／application logicから隔離する。primitive responsibilityを中心とする。

```text
initialize
readAxes
applyPose
setLed
acquireLedOwnership
releaseLedOwnership
disableNativeMouthVoiceSync
enableNativeMouthVoiceSync
requestRobotStop
close
capabilities
```

すべてのrobotで同じmethodが利用可能とは仮定しない。unsupported capabilityは明示する。

`playMotion`とIdle Motionの時間展開は原則scheduler側へ置く。vendor APIがatomic primitiveを提供し、それを使う合理性とtest可能性がある場合だけcapabilityとして追加する。

## 8. Audio playback decision

### 8.1 No temporary file and no external player

新実装では、`play_wav` payloadをdiskへ書き出さない。次を禁止する。

```text
__temp_wav
Files.write(temp WAV for normal playback)
ProcessBuilder("aplay", ...)
ProcessBuilder("killall", "aplay")
```

WAV payloadはsizeとformatを検証し、memory上で`AudioInputStream`およびcanonical PCM modelへdecodeする。

### 8.2 AudioOutput abstraction

次のboundaryを設ける。

```text
AudioOutput
AudioPlaybackSession
PlaybackClock
```

production candidateは次の二つであり、configurationとmanual acceptanceにより選択する。

1. `VstoneWavePlayerOutput`
   * VSTONE公開`CWavePlayer(AudioInputStream)`をadapter化する。
   * `getLine()`が返す`SourceDataLine`をplayback clock候補として使う。
2. `JavaSoundAudioOutput`
   * Java SE 8の`SourceDataLine`へPCM bytesを直接writeする。
   * VSTONE audio adapterが利用できない場合の代替候補とする。

どちらも同じ`AudioOutput` contractを実装し、protocol／schedulerへVSTONE classを漏らさない。

### 8.3 Audio format policy

最初のproduction scopeは、実際の既存client payloadをcharacterizationした上で決める。最低限、次を検証する。

* RIFF／WAVE signature
* PCMまたは明示的に対応したencoding
* sample rate
* channel count
* sample size
* frame size／alignment
* data chunk length
* decoded durationとmemory上限

Java Soundがformat conversionを提供する場合でも、暗黙に任意formatを受理せず、対応表とtestを持つ。

## 9. PCM-driven mouth LED decision

### 9.1 Common source

mouth LEDは、audio outputへ渡すものと同じcanonical PCMから生成する。speaker outputの再録音、microphone入力、ALSA loopback、別processのvolume monitorは使用しない。

```text
canonical PCM
  ├─ AudioOutput
  └─ MouthEnvelopeAnalyzer
       → MouthEnvelope
       → MouthLedSynchronizer
```

### 9.2 Envelope algorithm

初期algorithmはdeterministicかつtest可能にする。

* configurable 20～50 ms window
* RMSまたはmean absolute amplitude
* multi-channel aggregation
* noise gate
* bounded dynamic-range compression
* attack／release smoothing
* brightness clamp
* silence時は0

具体的thresholdとcurveはconfigurationとgolden testへ置き、codeにmagic numberとして散在させない。

### 9.3 Playback-position synchronization

mouth LEDは、可能な場合`SourceDataLine.getLongFramePosition()`または`getMicrosecondPosition()`を基準に、現在再生されているwindowのbrightnessを選ぶ。

wall-clockだけを使うfallbackを用意する場合でも、audio buffer量を推測した固定offsetを根拠なく入れない。clock precisionとlatencyはmanual acceptanceで記録する。

### 9.4 VSTONE public mouth LED path

**Decision amendment — WITHDRAWN ASSUMPTION:** Sota mouth LEDのpublic LED IDは現時点で確認できていない。従来candidateに含めていたID `14`をSota mouth LEDとして扱わない。公開資料上、ID `14`として確認できるものは`CCommUMotion.SV_MOUTH`、すなわちCommUのmouth servoであり、Sota mouth LED controlの根拠には使用できない。production implementationでは、未確認のLED ID、低レベル定数、legacy mappingを推測で採用しない。

Sotaのprovisional architecture candidateは **Case B: full LED state coordination** とする。`CRobotPose.setLED_Sota(Color eye_L, Color eye_R, int mouth, Color powerbtn)`の存在は公式公開APIで確認済みである。これはhardware behaviorの確認ではなく、production-ready designの確定でもない。

```text
Eye state ───────┐
Mouth brightness ├─> LedCoordinator
Power LED state ─┘      └─> complete Sota LED state
                              └─> VSTONE public API adapter
                                      └─> CRobotPose.setLED_Sota(...)
                                           + CRobotMotion.play(...)
```

`LedCoordinator`は全logical LED stateの単一ownerであり、次を不変条件とする。

* mouth synchronizerは`setLED_Sota()`を直接呼ばない。
* eye commandは現在のmouth stateを消さない。
* mouth updateはeye／power stateを古い値へ戻さない。
* complete LED stateの合成とcommitは既存serialized hardware pathを通す。
* old audio generationはmouth stateを更新できない。

`CSotaMotion.disabeMouthLEDVoiceSync()`と`CSotaMotion.enabeMouthLEDVoiceSync()`の存在は公開APIで確認済みである。method名の`disabe`／`enabe`はvendor JavaDocどおりのspellingをfacade内で使用し、修正した名称をvendor methodとして記述しない。

current-state getter、disable／enableの冪等性、process crash後・restart後の状態、他process、LED lock、audio playbackとのinteractionはUNKNOWNである。adapterは自分がdisableしたsessionに対してzero、configured restore attempt、unlockを行うresource ownershipを持つ。ただし元状態を取得できないため、元々disabledだった状態へ`enable`を送ってよいかはmanual acceptanceまたはvendor clarificationで決定する。

Case Bについても、mouth brightnessの実機反映、eyes／power LEDとの相互作用、高頻度更新、native voice-syncとの競合、cleanup時の復元は未確認である。これらをGate 1で確認するまで、production VSTONE adapterを実装しない。

### 9.5 Initial acceptance profile

最初のmanual acceptanceはmouth LED、native voice-sync、LED ownership、cleanupだけに限定する。servo motion、torque、full RobotController deployment、integrated motionを含めない。

```text
Gate 1A: setLED_Sota(...) mouth brightness / zero / eyes and power side effects
Gate 1B: disabeMouthLEDVoiceSync() / manual update / enabeMouthLEDVoiceSync()
Gate 1C: 10 Hz -> 20 Hz -> 25 Hz; 50 Hz only if justified
Gate 1D: mouth zero / configured voice-sync restore / ownership release / resource close
```

brightness値は公式範囲とinstalled runtimeを確認してからsymbolic `ZERO`／`LOW`から設定する。Gate 1のpass／fail、停止条件、未記入evidence templateは`docs/plans/vstone-manual-acceptance-runbook.md`を正とする。

### 9.6 LED lockとprocess lockの責務分離

`CRobotMotion.LockLEDHandle(...)`／`UnLockLEDHandle(...)`の公開API存在はCONFIRMEDである。single-process ownership semanticsはPARTIALLY CONFIRMEDでmanual validationが必要であり、cross-process exclusion、crash recovery、reentrant／duplicate acquisitionはUNKNOWNである。

`SingleInstanceProcessLock`はRobotController process全体の多重起動を防ぐ。VSTONE LED lockはvendor API上のLED ownership／arbitration候補である。前者を取得できても、別VSTONE application、vendor daemon、native voice-syncとのLED競合が防止されたとはみなさない。いずれのlockも他方の代替にせず、VSTONE lockをcross-process mutexとして保証しない。

## 10. AudioSession lifecycle

一つの`play_wav`は、一つの`AudioSession`として管理する。

```text
sessionId
generationId
validatedAudio
playbackSession
mouthEnvelope
mouthLedOwnership
state
completion
```

新しい`play_wav`は既存audio generationを置換する。古いgenerationはaudio write、mouth LED update、restore後の再更新を行えない。

### 10.1 Normal completion

```text
audio reaches end
→ stop animator
→ mouth target 0
→ restore native mouth voice sync
→ release LED ownership
→ drain/close audio resources
→ session completed
```

### 10.2 Stop／replacement／failure

```text
invalidate generation
→ stop and flush owned playback
→ stop animator
→ discard coalesced pending mouth value
→ request mouth 0
→ restore native voice sync
→ release LED ownership
→ close resources
```

cleanupはbest-effortで全stepを試みるが、最初のerrorを失わない。voice-sync restorationまたはunlockが不明な場合はbackendを`degraded`または`failed`へ遷移させる。

### 10.3 Mouth LED startup failure policy

manual lip-sync開始前に安全に失敗し、robot stateを変更していない場合は、configurationによりaudio-only playbackを許可できる。state変更後のfailureはaudio-onlyへ黙って継続せず、cleanupを行う。

legacy v1ではerror ACKを追加しないが、structured logとhealth stateを残す。

## 11. Mock backend and testability

Windows上のdefault development compositionはMock backendとMock audio outputとする。Mockは少なくとも次を保持する。

* current axis state
* LED state
* LED ownership state
* native mouth voice-sync state
* applied operation history
* audio bytes／format／playback state
* controllable playback clock
* lifecycle state
* generation ID
* cancel／stop state
* execution log
* fault injection point

audio／mouth LED testは実時間sleepへ依存せず、fake clockとdeterministic line positionを注入する。

## 12. Build and module direction

Java 8互換のreproducible CLI buildを導入する。物理moduleはboundary上必要なものへ限定する。

```text
java_server/
├─ pom.xml
├─ robot-controller-core/
├─ robot-controller-backend-mock/
├─ robot-controller-backend-vstone/
└─ robot-controller-app/
```

### 12.1 Module responsibility

`robot-controller-core`:

* frame codec
* protocol adapter
* validation
* immutable command model
* lifecycle
* scheduler
* backend／audio interfaces
* PCM model
* mouth envelope analysis
* generation／cancel

`robot-controller-backend-mock`:

* robot Mock
* audio Mock
* playback clock fake
* fault injection

`robot-controller-backend-vstone`:

* VSTONE robot adapter
* `CWavePlayer` audio adapter
* Sota mouth LED ownership／voice-sync／output adapter
* CommU／Dog capability adapter

`robot-controller-app`:

* composition root
* bounded TCP server
* configuration
* logging
* packaging entry point

必須条件:

* default Windows testで`sotalib.jar`を要求しない。
* VSTONE moduleだけが`sotalib.jar`へ依存する。
* dependency JARのversion、hash、license／provenanceを記録する。
* Java 8 source／targetをCIで検証する。
* production JAR layoutを再現可能にする。

## 13. Alternatives considered

### 13.1 PythonからVSMDへ直接write

Rejected。servo target memory、変換、補間、enable、stop、rollbackが確認できず、公式APIを迂回するため。

### 13.2 Pythonで確認したmouth LED memory pathをJava productionへ移植

Rejected as default production design。口LED調査evidenceは有用だが、Java-only方針では公開Java APIが存在する。まず公式`CSotaMotion`、`CRobotMotion`、`CRobotPose`による実装を試験する。公開APIで要件を満たせないことがmanual evidenceで確認された場合だけ、別ADRで再検討する。

### 13.3 `sotalib.jar`を解析して再実装

Rejected。解析許可を裏付けるlicenseが確認できず、vendor内部実装へ依存するため。

### 13.4 Python server + Java sidecar

Rejected。IPC versioning、二重process lifecycle、partial failure、deployment artifact、logging、health checkが増え、全体複雑性を下げる目的に反するため。

### 13.5 現行Javaを継ぎ足し改修

Rejected as primary strategy。static global state、unbounded executors、unsafe startup、audio process ownership不足が全体にまたがり、変更の影響を分離しにくい。legacy sourceはreferenceとして保持し、新実装を別treeへ構築する。

### 13.6 Javaで全面rewriteして一括置換

Rejected。new implementation自体は採用するが、一括production replacementは行わない。characterization test、Mock acceptance、manual hardware gateを通じて段階的に置換する。

### 13.7 `aplay`を維持してnative mouth syncへ依存

Rejected as target architecture。一時file、external process、global kill、playback position不足が残る。rollback用legacy behaviorとしてのみ保存する。

### 13.8 PCMをすべて`Clip`へloadする

Not selected as default。短音声では単純だが、payload sizeに比例してline側memoryも使用し、streaming／position／stop behaviorの制御が限定される。`SourceDataLine`系sessionを優先する。

## 14. Consequences

### 14.1 Positive

* vendor-supported robot API boundaryを維持できる。
* Java↔Python IPCと二重process運用を除去できる。
* protocol、scheduler、audio analysis、lip-syncをWindowsでtestできる。
* 一時WAV file、`aplay`、global `killall`を除去できる。
* audio sessionとmouth LED ownershipを同じgenerationで管理できる。
* Sota、CommU、Dogを共通application logicで扱える。
* unsafe legacy behaviorを互換対象から除外できる。
* Pythonで得たtest／設計資産を再利用できる。

### 14.2 Negative

* Java側へtest基盤とarchitecture seamを新設する必要がある。
* Java 8という古いruntime制約を維持する必要がある。
* VSTONE dependencyの配布、license、build provenanceを管理する必要がある。
* Java Sound／ALSAの実機compatibilityを手動確認する必要がある。
* mouth LED同期algorithmとlatencyを評価する必要がある。
* official APIのstop／lock／voice-sync semanticsが限定的な場合、完全なrecoveryを保証できない。

### 14.3 Risks

* build migrationがproduction packagingを変えるrisk
* refactor中にnormal-path wire behaviorが変わるrisk
* backend abstractionがvendor APIの能力差を隠しすぎるrisk
* stopという名称に複数の意味を混在させるrisk
* audio line bufferによるmouth LED timing offset
* mouth LED周期commandがrobot commandをstarveするrisk
* abnormal process terminationでvoice-sync／lock stateが残るrisk
* Edison Java Sound implementationが想定formatを扱えないrisk

これらは段階的migration、golden vectors、capability model、coalescing、fault-injection test、manual acceptance gateで管理する。

## 15. Invariants

再設計中に破ってはならない不変条件:

1. 実機自動deploy・自動test・servo／LED／torque操作を行わない。
2. `vsmd_edison`を停止しない。
3. device fileへ直接writeしない。
4. vendor SDK内部を解析しない。
5. normal-path legacy v1 wire contractをtestで固定する。
6. `read_axes`以外へv1 ACKを追加しない。
7. Windows default testはMock backendを使用する。
8. VSTONE dependencyをcore moduleへ漏らさない。
9. startupとstopを明示的state transitionとして扱う。
10. 古いgenerationをaudio executorとhardware workerの両方で再検証する。
11. normal `play_wav` pathでdisk WAV fileを作らない。
12. external `aplay`とglobal `killall`を新production implementationで使用しない。
13. mouth LEDのperiodic updateをunbounded FIFOへ蓄積しない。
14. voice-syncを無効化したsessionは、zero、restore、unlockを必ずcleanup pathへ持つ。
15. public VSTONE APIの実機semanticsを確認前にverifiedと表現しない。
16. Sota mouth LED IDを推測、legacy mapping、低レベルevidenceからproductionへ転記しない。
17. full Sota LED poseは単一`LedCoordinator`で合成し、個別producerから直接commitしない。

## 16. Open questions

* Intel Edison上で`CWavePlayer(AudioInputStream)`が既存clientのPCM WAVを安定再生できるか
* `CWavePlayer.getLine()`が安定したplayback positionを返すか
* pure `SourceDataLine`と`CWavePlayer`のどちらをproduction defaultにするか
* supported WAV format setとmaximum duration／payload
* `disabeMouthLEDVoiceSync()`／`enabeMouthLEDVoiceSync()`のidempotence
* Sota mouth-only public LED IDが存在するか。存在する場合のofficial constantとsemantics
* confirmed対象IDに対するkeyed LED lockと`play(..., lockKey)`の実機semantics
* safe update rate、brightness range、attack／release curve
* audioとservo motion同時実行時のlatency
* crash後のvoice-sync／lock recovery procedure
* CommUの`LipSyncEnable(boolean)`とnew audio engineの統合方法
* Dogにmouth LED capabilityが存在するか、unsupportedとするか
* Javaから利用するwhole-Sota process lockの実装方式
* Maven artifact化できないvendor JARの管理方法
* thin JAR + lib directoryとshaded JARのどちらを採用するか
* startup時のServoOnを明示commandとするか、operator-approved initialization stepとするか
* connection切断後にaccepted commandを継続するかcancelするかのcommand別policy
* legacy clamp behaviorを維持する範囲とstrict rejectへ変更する範囲

## 17. Review trigger

次の場合は本ADRを見直す。

* VSTONEが公式Python APIを提供した。
* Java 8 runtimeを更新できることが正式に確認された。
* official APIに安全なcancel／stop semanticsが追加された。
* official Java mouth LED APIが要件を満たさないことがmanual evidenceで確定した。
* CWavePlayer／Java SoundがEdison上でin-memory playbackを実現できないことが確定した。
* Sota、CommU、Dogのproduction deploymentが単一processでは成立しない根拠が得られた。
