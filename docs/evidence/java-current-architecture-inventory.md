# RobotController Java現行構造・リスク調査

作成日: 2026-08-03 JST
更新日: 2026-08-04 JST
対象リポジトリ: `social-robotics-lab/RobotController`
対象branch: `feature/python-robot-controller`
調査種別: documentation-only / static inspection
位置づけ: 新Java実装のlegacy baselineおよびcharacterization source

## 1. 調査範囲と安全境界

本調査は、GitHub上の対象branchにあるrepository metadata、Java source、既存文書および公開Java API文書を読み取る静的調査に限定した。Java／Python codeの変更、commit、push、実機接続、実機deploy、RobotController起動、JAR解析、VSMD／AppManager通信、servo／LED／torque操作、service／process操作は実施していない。

`sotalib.jar`の逆コンパイル、bytecode disassembly、private implementation抽出、内部protocol推定も実施していない。

2026-08-04の更新では、次を追加で整理した。

* 現行の音声再生path
* 一時WAV fileと`aplay`／`killall`への依存
* Sota口LEDの現行mapping
* VSTONE公開Java APIで確認できるin-memory audioおよびmouth LED関連surface
* 新Java実装に必要なaudio playback／lip-sync architecture
* 旧sourceを直接大改修せず、新実装を別source treeで構築する理由

## 2. Repository checkpoint

### 2.1 Remoteで確認できた状態

| Item | Result |
|---|---|
| Repository | `social-robotics-lab/RobotController` |
| Branch | `feature/python-robot-controller` |
| Remote tip | `d36f91a9826e35e256b4a7a0373a1ca4fe2ed8c4` |
| Tip subject | `Document Sota SDK and memdef provenance` |
| Base branch | `main` |
| `main` tip at comparison | `31ce13ada9792a30691304663d3e36719a845d4f` |
| Difference from `main` | ahead by 56 commits, behind by 0 |
| Phase 8b2d evidence | remote branchに存在することを確認 |

### 2.2 この環境から確認できない状態

ユーザーPCのローカルrepositoryにはアクセスできないため、次は未検証である。

* local `HEAD`とremote tipの一致
* tracked working treeがcleanか
* indexがcleanか
* `robot_controller_edison_smoke.sha256`以外のuntracked fileがないか
* 保護対象fileのSHA-256が維持されているか

作業開始前に、ユーザーPCで次を確認する必要がある。

```powershell
cd C:\Users\tiio\Workspace\RobotController

git branch --show-current
git rev-parse HEAD
git rev-parse origin/feature/python-robot-controller
git status --short
git log -3 --oneline
Get-FileHash .\robot_controller_edison_smoke.sha256 -Algorithm SHA256
```

期待するremote tipは次である。

```text
d36f91a9826e35e256b4a7a0373a1ca4fe2ed8c4
```

保護対象fileについて期待するSHA-256は、引継ぎ資料に記録された次の値である。

```text
0BF02AF8A83777B4F033C26A481A05C563726D8960F80AC24778F26CAD55CE59
```

## 3. Build方法とdependency

### 3.1 現行build model

現行repositoryはEclipse Java projectである。

* `.project`は`org.eclipse.jdt.core.javabuilder`を使用する。
* `.classpath`は`src`をsource root、`bin`をoutput directoryとしている。
* JRE containerは`JavaSE-1.8`である。
* `.settings/org.eclipse.jdt.core.prefs`はsource、compliance、targetをすべて`1.8`に固定している。
* READMEはEclipseから実行可能JARをexportする手順を前提としている。

repository内で、Maven、Gradle、Antによる再現可能なCLI build定義は確認できなかった。repository内の`META-INF/MANIFEST.MF`も確認できなかった。運用中distributionのManifestはoperator evidenceにより、`Main-Class: main.App`と外部JARへの`Class-Path`を持つことが確認されている。

### 3.2 Compile-time dependency

`.classpath`とREADMEが列挙するdependencyは次のとおりである。

```text
lib/core-2.2.jar
lib/gson-2.8.5.jar
lib/javase-2.2.jar
lib/jna-4.1.0.jar
lib/json-20180813.jar
lib/sotalib.jar
```

役割は概ね次のとおりである。

| Dependency | 主用途 |
|---|---|
| `core-2.2.jar` | ZXing coreと推定されるが、現行Java source上の使用箇所は今回未追跡 |
| `javase-2.2.jar` | ZXing JavaSEと推定されるが、現行Java source上の使用箇所は今回未追跡 |
| `gson-2.8.5.jar` | repositoryの主要command pathでは`org.json`が使われており、使用箇所は今回未追跡 |
| `jna-4.1.0.jar` | VSTONE側依存または過去機能の可能性があるが、使用箇所は今回未追跡 |
| `json-20180813.jar` | command payload、Pose、Motion、LED、Servo mapのJSON処理 |
| `sotalib.jar` | `jp.vstone.RobotLib`の公式Java API |

未使用dependencyの断定はせず、新実装開始時にimport inventoryとdependency graphを作成する。

### 3.3 Runtime dependency

現行実装は次へ依存する。

* Java 8
* `System.properties`
* VSTONE公式Java APIと実機runtime
* 音声再生用`aplay`
* 音声停止用`killall`
* current working directoryへ書き込めること

`SpeechPlayer`は固定名`__temp_wav`へ書き込み、`killall aplay`でsystem-wideに`aplay`を停止する。この挙動は新設計へ継承しない。

新Java実装では、音声payloadをmemory上でdecodeし、Java SoundまたはVSTONE公開`CWavePlayer(AudioInputStream)` adapterで再生する。production codeから`ProcessBuilder("aplay", ...)`、`killall aplay`および一時WAV fileを除去する。

### 3.4 Test infrastructure

inspected Eclipse metadataにはJava test source set、JUnit dependency、test runner設定がない。Windowsで実機なしに実行できるJava unit test基盤は、現時点ではrepositoryに確立されていない。

## 4. Java source inventory

```text
src/
├─ main/
│  ├─ App.java
│  ├─ Params.java
│  ├─ ServerIO.java
│  └─ TCPServer.java
├─ servo/
│  ├─ RobotSys.java
│  ├─ ServoConverter.java
│  ├─ ServoConverter_Sota.java
│  ├─ ServoConverter_CommU.java
│  └─ ServoConverter_Dog.java
├─ led/
│  ├─ LedConverter.java
│  ├─ LedConverter_Sota.java
│  ├─ LedConverter_CommU.java
│  └─ LedConverter_Dog.java
└─ utils/
   ├─ AxisReader.java
   ├─ SpeechPlayer.java
   ├─ PosePlayer.java
   ├─ PoseExecutorThread.java
   ├─ MotionPlayer.java
   ├─ MotionExecutorThread.java
   ├─ IdleMotionPlayer.java
   └─ IdleMotionExecutorThread.java
```

### 4.1 主要責務

| Source | 現行責務 |
|---|---|
| `main.App` | process entry point。TCP serverとPose executorを開始 |
| `main.Params` | static initializerで`System.properties`を読み込み、robot typeとportを保持 |
| `main.ServerIO` | 4-byte big-endian length-prefixed frameのread/write |
| `main.TCPServer` | accept loop、connection thread生成、command dispatch |
| `servo.RobotSys` | vendor object生成、robot初期化、ServoOn、初期Pose／torque／LED、idle pose定義 |
| `servo.ServoConverter*` | 公開軸名とservo ID／vendor値の変換、範囲clamp |
| `led.LedConverter*` | 公開LED名とLED ID／値の変換 |
| `utils.PosePlayer` | Poseの最低限のfield確認とglobal queueへの投入 |
| `utils.PoseExecutorThread` | global queueをtakeし、`CRobotPose`を生成して`RobotSys.motion.play()`を呼ぶ |
| `utils.MotionPlayer` | single-thread executorと`Future`の管理 |
| `utils.MotionExecutorThread` | Motion配列を順にPose queueへ投入し、`Thread.sleep()`で進行 |
| `utils.IdleMotionPlayer` | idle motion executorと`Future`の管理 |
| `utils.IdleMotionExecutorThread` | idle poseを無限反復してPose queueへ投入 |
| `utils.AxisReader` | `RobotSys.motion.getReadpos()`を直接呼び出す |
| `utils.SpeechPlayer` | WAV一時file作成、`aplay`起動、`killall aplay` |

## 5. Entry pointとstartup sequence

### 5.1 Entry point

`main.App.main()`は固定サイズ2の`ExecutorService`を作成し、次をほぼ同時に開始する。

```text
Thread A: TCPServer
Thread B: PoseExecutorThread
```

### 5.2 実際のinitialization経路

```text
App.main
  └─ PoseExecutorThread.run
       └─ RobotSys.initialize
            ├─ new CRobotMem
            ├─ robot typeに応じたCRobotMotion生成
            ├─ CRobotMem.Connect
            ├─ InitRobot_Sota / InitRobot_CommU
            ├─ ServoOn
            ├─ CommUではLipSyncEnable(true)
            ├─ initial CRobotPose生成
            ├─ SetPose
            ├─ SetTorque
            ├─ SetLed
            ├─ motion.play(..., 1500)
            └─ wait(1500)
```

Dog backendも`CSotaMotion`と`InitRobot_Sota()`を使用する。

### 5.3 Startup上の問題

1. TCP listenとhardware initializationの順序が保証されない。`TCPServer`が先にlistenし、`RobotSys.motion`初期化前にcommandを受理できる。
2. 起動そのものがServoOn、torque、初期Pose、LED出力を伴う。
3. initialization失敗時、`motion`が`null`になってもprocess全体をfail-closedに停止しない。
4. lifecycle state、readiness gate、health stateがない。
5. startup rollback、resource close、shutdown hookがない。

## 6. TCP、thread、connection model

### 6.1 Connection model

`TCPServer`は`ServerSocket.accept()`を無限loopし、connectionごとに`RecvThread`をcached thread poolへ投入する。各connectionは原則1 commandを処理し、finallyでsocketをcloseする。

### 6.2 問題

* `Executors.newCachedThreadPool()`でconnection thread数に上限がない。
* accept数、同時connection数、queue、request rateに上限がない。
* socket read timeoutがない。
* frame headerまたはpayloadを送らないclientがthreadを占有し続けられる。
* executorをshutdownする経路がない。
* network threadが`SpeechPlayer`、`AxisReader`、各Playerを直接呼ぶ。
* command dispatchは文字列のif/else連鎖であり、unknown command、invalid payload、internal errorのpolicyが明示されていない。
* disconnectは、すでにdispatch済みのMotion、Idle Motion、Pose、audioをcancelしない。

## 7. Frame codecとprotocol処理

`ServerIO`は4-byte big-endian signed intを読み、同じ形式でresponseを書く。これはlegacy protocol v1の基本wire formatと一致する。

ただし、現行実装には次の問題がある。

* negative lengthを拒否しない。
* maximum lengthを持たない。
* `new byte[dataSize]`前の範囲検証がない。
* EOFを明示的に処理しない。`InputStream.read()`の`-1`がsizeへ加算され、unchecked exceptionまたは不正loopへ進む可能性がある。
* command、JSONのcharsetを明示せずplatform defaultへ依存する。
* malformed JSONやconverter exceptionはconnection threadからunchecked exceptionとして漏れる。
* response有無の契約はdispatch implementationに埋め込まれている。

正常系wire compatibilityは維持しつつ、不正入力時のlegacy crash／hangは再現しない方針が妥当である。

## 8. Pose queueとhardware access

### 8.1 Pose queue

`PoseExecutorThread.q`はstaticなunbounded `LinkedBlockingQueue<JSONObject>`である。

```text
play_pose ─┐
play_motion ├─ PosePlayer.play ─> unbounded Pose queue ─> PoseExecutorThread ─> motion.play
idle motion ┘
```

Pose、Motion、Idle Motionが最終的に同一queueを通る点は、vendor `motion.play()`の一部直列化には寄与する。しかし、次は直列化されない。

* `AxisReader.read()`からの`motion.getReadpos()`
* `RobotSys` initialization
* Servo／LED handle lock関連method
* audio process
* 将来追加されるmouth LED animation
* 将来追加される別hardware operation

### 8.2 Queue上の問題

* queueがunboundedである。
* operation ID、source、priority、deadline、generation IDがない。
* pending operationの選択的cancelができない。
* stale operationを識別できない。
* enqueue時とexecute時のlifecycle validationがない。
* `JSONObject`を内部command modelとして直接流している。

## 9. Motion／Idle Motion scheduler

### 9.1 Motion

`MotionPlayer`はstatic single-thread executorを持ち、`play()`ごとに`MotionExecutorThread`をsubmitする。新しいMotionは古いMotionを明示的に置換せず、executor queueへ並ぶ。

`MotionExecutorThread`は各要素をPose queueへ投入した後、`Msec`だけsleepする。

### 9.2 Idle Motion

`IdleMotionPlayer`も独立したstatic single-thread executorを持つ。MotionとIdle Motionは別executorで同時進行でき、どちらも同じPose queueへ投入する。そのため、両者のPoseがinterleaveする。

### 9.3 問題

* Motion、Idle Motion、direct Poseの所有権・優先順位がない。
* repeated `play()`が前generationを自動停止しない。
* executor queueがboundedではない。
* speedが0または負数の場合の検証がない。
* `pause`、`Msec`、array lengthの上限がない。
* sleepを実時間に固定しており、test clockを注入できない。

## 10. 現行audio implementation

### 10.1 `play_wav`

現行`SpeechPlayer.play(byte[])`は次を行う。

```text
TCP payload bytes
  → fixed path "__temp_wav"
  → Files.write(...)
  → ProcessBuilder("aplay", path)
```

問題は次のとおりである。

* payload全体を固定名fileへ書き込む。
* concurrent `play_wav`で同一fileが競合する。
* working directoryのwrite permissionへ依存する。
* process起動後のfile lifetimeが明示されない。
* WAV header、encoding、sample rate、channel、bit depth、payload sizeを検証しない。
* playback completion、position、buffer、underflowをapplicationが把握できない。
* playback generationとconnection／command generationが結び付いていない。

### 10.2 `stop_wav`

`SpeechPlayer.stop()`は、保持しているprocessがaliveの場合に次を実行する。

```text
ProcessBuilder("killall", "aplay")
```

この処理はRobotControllerが起動したprocessだけでなく、system上の別`aplay`まで終了させる可能性がある。停止対象のownershipが不明確であり、新実装へ継承しない。

### 10.3 Legacy compatibilityとして残すもの

通信上は次を維持する。

* command名`play_wav`
* 第2frameにWAV binaryを送る方式
* `stop_wav`
* legacy v1では正常時responseを追加しない

内部実装として、一時file、`aplay`、`killall`を維持する必要はない。

## 11. Sota口LEDの現行状態

### 11.1 Java source上のmapping

`LedConverter_Sota`は、公開名`MOUTH`をLED ID `14`へ対応付け、値を0～255へclampする。

ただし現行audio pathは、WAV波形を解析して`MOUTH`へ値を送っていない。口LED点灯は、`aplay`とSota側の既存音声連動機構に依存している。

### 11.2 既存Python調査の位置づけ

過去のPython調査では、AppManager／VSMDを介して口LED ID 14のselector、target、interpolation、cleanup、routing restorationおよびlock releaseを扱うpathが構築され、保守的な単発pulseについて実機確認が行われた。

このevidenceは次の理解に有用である。

* 口LEDの物理IDは14である。
* 通常の音声連動routingと明示的LED補間routingは競合し得る。
* 制御開始前のownership、終了時の0復帰、routing restoration、lock releaseが必要である。
* 単発pulseが成功しても、連続lip-syncの更新周期、長時間動作、audio同期は未確認である。

ただし、Javaオンリーproduction方針では、Pythonで用いた低レベルmemory writeをproductionへ移植しない。公開Java APIだけで実装可能かを先に検証する。

## 12. 公開Java APIから確認できるaudio／mouth LED surface

公開JavaDoc上、次のsurfaceが存在する。

### 12.1 In-memory audio

`jp.vstone.RobotLib.CWavePlayer`:

```text
CWavePlayer(AudioInputStream)
run()
stop()
getLine() -> SourceDataLine
isUsed()
```

したがって、受信したWAV bytesを`ByteArrayInputStream`と`AudioSystem.getAudioInputStream()`で`AudioInputStream`へ変換し、disk fileを作らずに再生するadapterを構成できる可能性がある。

Java SE 8の`SourceDataLine`にも、streaming write、`stop()`、`flush()`、`drain()`、`getLongFramePosition()`、`getMicrosecondPosition()`がある。VSTONE `CWavePlayer.getLine()`が実機上で有効なlineを返す場合、実再生位置をmouth LED同期clockとして利用できる可能性がある。

### 12.2 Mouth LED voice sync

`CSotaMotion`には、公開JavaDoc上で次のmethodが存在する。名称のmisspellingを含め、API名はこのとおりである。

```text
disabeMouthLEDVoiceSync()
enabeMouthLEDVoiceSync()
```

### 12.3 LED ownershipとoutput

`CRobotMotion`には次がある。

```text
LockLEDHandle(Byte[] ids)
LockLEDHandle(String lockKey, Byte[] ids)
UnLockLEDHandle(...)
play(CRobotPose pose, int msec, String lockKey)
```

`CRobotPose`には次がある。

```text
SetLed(Map<Byte, Short>)
SetLed(Byte[], Short[])
setLED_Sota(..., int mouth, ...)
```

したがって、公開APIだけを使う候補pathは次である。

```text
Lock LED ID 14 with an owned key
  → disabeMouthLEDVoiceSync()
  → play audio from in-memory AudioInputStream
  → submit coalesced LED ID 14 targets through CRobotPose + play(..., lockKey)
  → set mouth LED to 0
  → enabeMouthLEDVoiceSync()
  → unlock LED ID 14
```

これは公開surfaceから導けるcandidate designであり、実機runtime semanticsの確認済みを意味しない。

## 13. 新audio／lip-sync subsystemに必要な設計

### 13.1 同一PCMを二つの用途へ使う

```text
WAV payload
  → strict in-memory decode
  → canonical PCM
       ├─ audio output
       └─ mouth envelope analysis
```

音声出力とは別に録音deviceやloopbackを読む方式は採用しない。同じPCMを使うことで、解析対象と再生対象の不一致を避ける。

### 13.2 Envelope生成

候補処理は次である。

```text
20～50 ms window
  → channel aggregation
  → RMSまたはmean absolute amplitude
  → noise gate
  → dynamic range compression
  → attack／release smoothing
  → bounded mouth brightness
```

最初の実機acceptanceでは、過去に物理確認された保守的範囲を参考に、0～16程度の低輝度、50 ms程度の更新周期から開始する。これは最終仕様ではなく、manual acceptance profileである。

### 13.3 Playback clock

LED更新をwall-clock sleepだけへ依存させると、audio device bufferの分だけmouth LEDが先行し得る。可能であれば、次をclock sourceとして使う。

```text
SourceDataLine.getLongFramePosition()
または
SourceDataLine.getMicrosecondPosition()
```

line positionの精度と単調性は実機上で確認する。利用できない場合のfallbackは、bounded bufferingを考慮したmonotonic clockとするが、推測で補正値を固定しない。

### 13.4 Executorとhardware serialization

audio outputはblocking I/Oを含むため、servo／LED hardware worker上で再生してはならない。

```text
Owned audio executor
  └─ AudioPlaybackSession / SourceDataLine or CWavePlayer

Single robot hardware worker
  └─ mouth LED lock, voice-sync switch, LED target, restore, unlock
```

mouth LEDの周期更新を通常FIFOへすべて蓄積すると遅延時に古いbrightnessが残る。そのため、mouth LED updateはlatest-value coalescing mailboxとし、未実行の古い値を破棄する。

### 13.5 Cleanup order

通常完了、`stop_wav`、replacement、exception、shutdownの全pathで、少なくとも次を試みる。

```text
invalidate audio generation
  → stop/flush owned audio line
  → stop mouth LED animator
  → discard pending mouth values
  → set mouth LED to zero
  → restore voice sync
  → release LED lock
  → close audio resources
```

voice-syncを切り替えた後のrestoreまたはunlockに失敗した場合は、単なるaudio failureとして握りつぶさず、backendを`degraded`または`failed`へ遷移させる。

## 14. 未確認事項

次は公開APIの存在だけでは確定できない。

* Intel EdisonのJava 8 runtimeで`AudioSystem`／`CWavePlayer`が対象PCM WAVを再生できるか
* `CWavePlayer.getLine()`のframe positionが実再生位置として十分安定するか
* Java再生時に既存native mouth syncが動作するか
* `disabeMouthLEDVoiceSync()`／`enabeMouthLEDVoiceSync()`の実機効果とidempotence
* LED ID 14のlockと`play(..., lockKey)`が期待どおり連続更新を排他するか
* 連続更新可能な安全な周期と輝度範囲
* servo motionとmouth LED更新を同時に行った場合のlatency
* process異常終了時にvoice sync／lock stateがどうなるか
* startup recoveryで公式APIのみを使って安全にnormal stateへ戻せるか

これらはJAR解析ではなく、公開APIを使った小さなmanual hardware acceptanceで確認する。

## 15. Stop semantics

### 15.1 `stop_pose`

`PosePlayer.stop()`は次を行う。

1. `AxisReader.read()`で現在値を読む。
2. 現在値を`ServoMap`へ変換する。
3. `Msec=100`のPoseを作る。
4. そのPoseを既存queueの末尾へ追加する。

したがって、次は行わない。

* pending Poseのqueue clear
* 実行中補間の停止
* Motion／Idle Motionの停止
* stale operationの無効化
* hardware safe stopの保証

### 15.2 `stop_motion`と`stop_idle_motion`

`Future.cancel(true)`で生成threadへinterruptを送る。しかし、すでにPose queueへ投入済みのcommandは残る。`future`が未設定の場合は`NullPointerException`となり得る。stopの冪等性はない。

### 15.3 `stop_wav`

現行`stop_wav`はglobal `killall aplay`であり、owned session cancellationではない。新設計では`AudioPlaybackSession`とgeneration IDに対するidempotent stopへ変更する。

### 15.4 分離すべき停止概念

新設計では、次を別々の契約として定義する必要がある。

1. logical cancel: 古いgenerationから新規hardware／audio commandを出させない。
2. pending queue cancel: 未実行operationを破棄する。
3. running robot operation stop: 公式APIが許す範囲で補間中operationを停止する。
4. running audio stop: owned line／playerを停止し、bufferをflushする。
5. mouth LED restoration: 0、voice-sync restoration、unlockを行う。
6. physical safe stop: 機体固有の安全状態へ移行する。

公式APIに存在しないrunning stopやphysical stopを実装済みと仮定してはならない。

## 16. Validationとerror handling

### 16.1 現行validation

`PosePlayer`は`Msec`の存在と、`ServoMap`または`LedMap`の存在だけを確認する。Servo converterは既知軸について値をclampする。WAV payloadは実質的に未検証である。

### 16.2 不足

* top-level JSON type
* unknown／missing field policy
* duplicate semantic field
* integer以外、NaN、Infinity相当値
* `Msec`、`Pause`、`Speed`の範囲
* Motion element数
* Servo／LED map size
* unknown axis／LED名
* WAV payload size
* RIFF／WAVE structure
* PCM encoding、sample rate、channel、sample size、frame alignment
* decoded duration上限
* frame size
* connection数
* queue length

`ServoConverter_Sota`ではunknown keyに対する`map.get(key)`のunboxingで`NullPointerException`となり得る。clampはlegacy behaviorであり、新仕様でclampを維持するかrejectへ変更するかをrobot profile単位で明文化する必要がある。

## 17. Process・resource lifecycle

* `App`のexecutorを保持・shutdownしない。
* TCP connection executorをshutdownしない。
* Motion／Idle executorをshutdownしない。
* server socketのcontrolled close pathがない。
* audio process／temporary fileのcontrolled lifecycleがない。
* `CRobotMem`／`CRobotMotion`のclose sequenceがない。
* `RobotSys.unLockServoLedHandle()`をnormal shutdownから呼ぶ経路がない。
* shutdown hookがない。
* uncaught exception policyがない。
* startup失敗時のexit code policyがない。
* `Params`は設定error時に`System.exit(0)`を使い、failureをsuccess exitとして報告する。

## 18. 主要リスク評価

| Priority | Risk | 根拠 | 新設計での対策 |
|---|---|---|---|
| Critical | startup時の無条件hardware出力 | `RobotSys.init*()` | explicit initialization policyとreadiness gate |
| Critical | stop後も旧commandが実行される | unbounded Pose queue、generationなし | generation ID、queue cancel、stale rejection |
| Critical | MotionとIdle Motionのinterleave | 独立executorから同一queueへ投入 | 単一scheduler／ownership policy |
| High | connection resource exhaustion | cached thread pool、timeoutなし | bounded executor、socket timeout、connection limit |
| High | oversized／negative frame | size validationなし | strict frame codecとcommand別limit |
| High | hardware accessが完全には直列化されない | `AxisReader`がnetwork threadから直接APIを呼ぶ | 全robot hardware operationをsingle workerへ集約 |
| High | lifecycle不在 | listenとinitializeがrace | state machine、ready前listen禁止 |
| High | stopが非冪等 | nullable Futureを直接cancel | idempotent state transition |
| High | global `killall aplay` | `SpeechPlayer.stop()` | owned audio sessionのみ停止 |
| High | fixed temporary WAV file | `__temp_wav` | in-memory decode／playback |
| High | manual lip-sync cleanup failure | voice-sync switch、LED lock、zero restorationが必要 | scoped session、finally cleanup、degraded state |
| Medium | default charset依存 | `new String(byte[])` | protocol charset固定 |
| Medium | static mutable global state | `RobotSys`、Player群 | dependency injectionとinstance lifecycle |
| Medium | WAV／PCM未検証 | raw payloadをそのままfile化 | bounded format validatorとcanonical PCM model |
| Medium | lip-sync command backlog | 周期LED値を通常FIFOへ入れると遅延する | latest-value coalescing mailbox |
| Medium | reproducible build不在 | Eclipse exportのみ | Java 8対応CLI buildとtest profile |

## 19. 再設計時に維持するbaseline

維持するもの:

* 4-byte big-endian length prefix
* command名を第1frameとして受信
* payloadが必要なcommandは第2frameを受信
* 原則1 connection 1 command
* `read_axes`のみ正常時responseを返す
* `play_wav`がWAV binaryを第2frameで受け取ること
* `stop_wav` command名
* Sota／CommU／Dogの公開command surface
* 正常な既存clientが送るpayloadの意味
* VSTONE公式Java APIの使用

維持しないもの:

* crash、hang、resource exhaustion
* default charset依存
* unbounded queue／thread
* startup時の暗黙hardware output
* temporary WAV file
* external `aplay`
* system-wide `killall`
* stopの非冪等性
* disconnect後に無制限で継続する旧generation
* native `aplay`連動だけに依存したmouth LED behavior

## 20. 新実装のsource placement

現行`src/`はlegacy reference implementationとして原則凍結する。新実装は別source treeへ置く。

```text
RobotController/
├─ src/                    # legacy reference; 原則変更しない
├─ java_server/            # new Java implementation
│  ├─ pom.xml
│  ├─ robot-controller-core/
│  ├─ robot-controller-backend-mock/
│  ├─ robot-controller-backend-vstone/
│  └─ robot-controller-app/
├─ python_server/          # design/test oracle; production targetではない
└─ docs/
```

physical module数は必要最小限とし、VSTONE JARを隔離するboundaryを最優先する。protocol、scheduler、audio analysisを細かく別moduleへ分割すること自体を目的にしない。

## 21. 結論

Javaオンリーの新実装は妥当である。現行Javaを直接大規模改修するより、legacy wire contractと正常系behaviorをcharacterization testで固定し、`java_server/`に新しいJava 8 applicationを構築する方が、安全性、保守性、testabilityを高めやすい。

音声については、legacy `play_wav` protocolを維持しながら、内部をin-memory PCM playbackへ置き換えられる。口LEDについては、同じPCMからenvelopeを作り、playback positionに同期してLED ID 14へcoalesced updateを送る設計が可能である。ただし、VSTONE公開APIの実機semanticsは未確認であり、production化前にmanual acceptance gateを通す必要がある。

次のcode変更phaseへ進む前に、ADR、migration plan、Codex implementation instructionを採択し、branch checkpointとprotected fileを人間が確認することをexit gateとする。
