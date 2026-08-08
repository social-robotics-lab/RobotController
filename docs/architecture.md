# docs/architecture.md

## 1. 文書の目的と現行方針

本書はRobotControllerの内部アーキテクチャ、責務分割、依存関係、並行処理、状態管理および拡張方法を定義する。

production targetは`docs/decisions/adr-java-only-redesign.md`に従うJava 8単一process applicationであり、新実装は`java_server/`に置く。本書のうちPython production server、AppManager／VSMD direct write、一時WAV file、`aplay`を前提とする既存節はhistorical design recordであり、現行Java設計の根拠としてADRまたは`docs/plans/java-redesign-migration-plan.md`より優先しない。

### 1.1 2026-08-08 Java application slice

現在実装済みのhardware-free経路は次のとおりである。

```text
Main / explicit configuration
  -> SingleInstanceProcessLock (FileChannel / non-blocking tryLock)
  -> RobotControllerApplication lifecycle owner
  -> backend initialize on SerializedHardwareWorker
  -> ready
  -> BoundedTcpServer bind / accept
  -> LegacyConnectionHandler
  -> FrameCodec + strict UTF-8 / JSON / WAV validation
  -> ApplicationCommandDispatcher
     |- Motion / Pose / Idle generation scheduler
     |- SerializedHardwareWorker (bounded, single thread)
     |    `- RobotBackend
     `- AudioSessionCoordinator (bounded, separate owned thread)
          |- canonical PcmAudioData -> AudioOutput / AudioPlaybackSession
          |- same canonical PcmAudioData -> MouthEnvelopeAnalyzer
          |- PlaybackClock.playedFrames() -> current envelope window
          `- LatestHardwareCommandMailbox -> SerializedHardwareWorker -> MOUTH LED
```

所有権と上限は次のように固定する。

* `ServerSocket`とaccept threadは`BoundedTcpServer`が所有する。
* accepted socketはconnection executorへの投入前からserverが追跡し、rejection、handler完了、shutdownの全経路でcloseする。
* connection executorはfixed worker数とbounded queueを持ち、overflow時はそのsocketだけをcloseする。
* `RobotBackend`のinitialize、Pose、read、stop、closeはsingle `SerializedHardwareWorker`から実行する。
* hardware queueはboundedであり、enqueue時のtokenに加えてbackend call直前にもgenerationを検証する。
* Motion、direct Pose、Idle Motionは同じ`MOTION` generationを共有し、replacementまたはstopで旧世代を無効化する。
* strict WAV validationはmemory内で一度だけcanonical `PcmAudioData`へdecodeする。coordinatorは同じimmutable objectをaudio outputとmouth envelope解析の両方へ渡し、再decodeしない。
* audioは`AUDIO` generationとbounded single coordinator workerを使い、blocking session lifecycleでrobot hardware workerを占有しない。
* mouth synchronizerのperiodic wakeupは時間windowをFIFOで進めず、毎回`PlaybackClock.playedFrames()`を読み、現在のplayheadに対応するbrightnessだけを選ぶ。
* `LatestHardwareCommandMailbox`はdrain task最大1件と置換可能なpending値最大1件だけを保持する。mouth backend callは通常commandと同じ`SerializedHardwareWorker`上で実行され、選択時にもaudio generationを再検証する。
* hardware-independent default envelopeは20 ms window、noise gate 0.02、gain 2.0、compression exponent 0.5、attack 40 ms、release 100 ms、brightness 0..16である。hardware固有curveへの変換は将来adapterの責務とする。
* replacementは旧generation無効化、synchronizer cancel、pending clear、owned playback stop、generation-aware mouth zero、resource close、新session startの順で行う。
* normal completion、stop、playback／clock／mouth output failure、shutdownはpending clearとbest-effort mouth zeroを含む共通cleanupへ収束する。旧completionのzero commandもhardware実行直前のgeneration checkで新sessionへ作用できない。
* shutdownはlisten／active socket、motion、audio generation／playback／mouth、全generation、backend、hardware workerの順に閉じる。

Mock compositionは明示的な`--backend=mock`選択時だけ利用できる。`--backend=vstone`はvendor object、vendor JAR、listen socketを生成する前に起動失敗する。Mockのlogical `MOUTH` writeはcoordinatorとserializationのtest oracleであり、VSTONE adapter、real audio output、LED lock／native voice-sync、actual mouth LEDは未実装である。Mock testの成功を実機semanticsの確認とはみなさない。

process lock pathはcommand-line設定から取得し、既定値は`java.io.tmpdir`直下の`robot-controller.lock`をabsolute／normalized pathとして使用する。親directoryは自動作成せず、`tryLock()`競合時はretry、sleep、lock file削除を行わない。applicationがchannelと`FileLock`を所有し、startup failureまたは通常shutdownの最後にrelease／closeする。pathnameはunlinkしない。このlockは同じpathとadvisory lock規約へ参加するprocess間だけを調停する。

Maven packageは`target/robot-controller-dist/`へthin `RobotController.jar`、runtime `lib/`、command-line option説明を含む`config/`を生成する。artifactはrepository外absolute path、vendor JAR、hardware resourceを含めない。Mock smokeは配布directoryをworking directoryとして実行する。

## 2. 設計原則

1. プロトコルとハードウェアを分離する。
2. ロボット固有処理をバックエンドへ隔離する。
3. ハードウェアアクセスを直列化する。
4. 動作の所有者を常に一つにする。
5. 停止処理を冪等にする。
6. 古いタスクがキャンセル後に再開しないようにする。
7. Windows上で実機なしにテストできるようにする。
8. Edison等の古い環境で不要な依存を増やさない。
9. 外部互換性と内部実装を分離する。
10. 安全でない推測より、明示的な拒否を選ぶ。
11. 本番コードをCPython 3.6.15で構文解析・実行可能に保つ。

## 3. システム構成

```text
TCP Client
    |
    v
TCP Server
    |
    v
Frame Codec
    |
    v
Command Router
    |
    +--------------------+
    |                    |
    v                    v
Input Validator      Response Encoder
    |
    v
Application Services
    |
    +---------+----------+-----------+
    |         |          |           |
    v         v          v           v
Motion     Audio      Axis Read    Status
Service    Service    Service      Service
    |
    v
Robot Coordinator
    |
    v
Hardware Worker
    |
    v
Robot Backend
    |
    +---------+---------+---------+
    |         |         |         |
    v         v         v         v
Mock      Sota      CommU       Dog
```

live Sota write経路には、protocol framingとは独立したOS-level process coordinationを置く。

```text
External command client
    -> Legacy V1 / V2 TCP server 22222
    -> RobotController application
    -> whole-Sota FcntlProcessLock ownership
    -> Sota Backend
    +-> AppManager TCP 6495 (interpolation timer lease / slot)
    `-> VSMD TCP 6498 (validated memory access)
```

`FcntlProcessLock`は協調RobotController process間でSota 1台全体を所有するためのadvisory lockである。AppManager leaseは補間timer資源の割当てであり、このprocess lockと同じ概念ではない。

## 4. 推奨ディレクトリ構成

```text
python_server/
├── pyproject.toml
├── README.md
├── src/
│   └── robot_controller/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── errors.py
│       ├── logging_config.py
│       │
│       ├── protocol/
│       │   ├── __init__.py
│       │   ├── frame.py
│       │   ├── commands.py
│       │   ├── legacy_v1.py
│       │   └── validation.py
│       │
│       ├── server/
│       │   ├── __init__.py
│       │   ├── tcp_server.py
│       │   ├── connection.py
│       │   └── limits.py
│       │
│       ├── application/
│       │   ├── __init__.py
│       │   ├── command_router.py
│       │   ├── controller.py
│       │   └── lifecycle.py
│       │
│       ├── motion/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── scheduler.py
│       │   ├── player.py
│       │   ├── interpolator.py
│       │   └── cancellation.py
│       │
│       ├── audio/
│       │   ├── __init__.py
│       │   ├── manager.py
│       │   ├── wav.py
│       │   └── process.py
│       │
│       ├── hardware/
│       │   ├── __init__.py
│       │   ├── backend.py
│       │   ├── capabilities.py
│       │   ├── worker.py
│       │   ├── registry.py
│       │   ├── profiles.py
│       │   ├── mock.py
│       │   ├── sota_edison.py
│       │   ├── commu.py
│       │   └── dog.py
│       │
│       └── observability/
│           ├── __init__.py
│           ├── events.py
│           └── metrics.py
│
└── tests/
    ├── unit/
    ├── integration/
    ├── compatibility/
    ├── fixtures/
    └── hardware/
```

実際の構成は対象Pythonバージョンに合わせて簡略化してよい。ただし、責務分離は維持する。

## 5. データモデル

### 5.1 Pose

概念的には次の値を持つ。

```python
import typing

class Pose:
    duration_ms: int
    servo_positions: typing.Mapping[str, int]
    led_values: typing.Mapping[str, int]
```

生成時点で検証済みかつ正規化済みとする。

### 5.2 Motion

```python
class Motion:
    poses: typing.Sequence[Pose]
```

Motion内部に未検証の辞書を保持しない。

### 5.3 IdleMotionSettings

```python
class IdleMotionSettings:
    speed: float
    pause_ms: int
```

### 5.4 Axes

```python
Axes = typing.Mapping[str, int]
```

内部単位と外部単位が異なる場合、バックエンド境界で変換する。

### 5.5 Python 3.6.15制約

インタフェースには原則として`abc.ABC`を使用する。型注釈には`typing.List`、`typing.Dict`、`typing.Mapping`、`typing.Optional`等を使用する。

`from __future__ import annotations`、組み込み型ジェネリクス、`X | None`、標準ライブラリの`dataclasses`、`typing.Protocol`、`asyncio.run()`およびPython 3.7以降で追加された構文・標準ライブラリAPIを使用しない。開発ツールによる自動書き換えで本番コードへPython 3.6非互換構文を導入しない。

## 6. プロトコル層

プロトコル層は以下だけを担当する。

* フレームの読み書き
* 長さ検証
* UTF-8デコード
* JSON解析
* コマンド名の識別
* 外部データから内部モデルへの変換
* `read_axes`応答のエンコード

Frame Codecは固定最大値を内部に持たず、読み取りごとに呼び出し側から`max_length`を受け取る。正常系v1で有効な長さは`0 <= length <= min(max_length, 2147483647)`とする。4バイトbig-endianヘッダを非負値として復号した後、`0x80000000`以上または`max_length`超過を本文確保前に拒否する。長さ0は`b""`として返し、コマンド固有の空データ検証は上位層で行う。

プロトコル層は以下を行わない。

* サーボ操作
* LED操作
* `aplay`実行
* スレッド管理
* モーション競合判断
* ロボット種別固有の通信

## 7. サーバー層

### 7.1 接続処理

各接続について次を行う。

1. 接続制限を確認する
2. 読み取りタイムアウトを設定する
3. コマンドフレームを読む
4. 必要ならペイロードフレームを読む
5. Command Routerへ渡す
6. 応答がある場合だけ送信する
7. 接続を閉じる

### 7.2 接続数

無制限のcached thread poolは使用しない。

初期版は同期ソケットと上限付き`concurrent.futures.ThreadPoolExecutor`を使用する。`max_workers`の初期既定値は16とする。

Executor内部の待ち行列が無制限にならないよう、accept後に接続ハンドラー数の入場制限を行い、実行中と投入待ちを合わせて初期既定値16を超えて保持しない。上限到達時の接続はハードウェア操作へ進めず、安全に拒否または閉じる。初期版では`asyncio`を採用しない。

### 7.3 タイムアウト

少なくとも以下を分ける。

* 接続受付後のコマンドヘッダ待ち
* コマンド本文待ち
* ペイロードヘッダ待ち
* ペイロード本文待ち
* バックエンド処理待ち

初期既定値は、コマンドフレーム、JSONフレームおよび`read_axes`応答送信を5秒、WAVペイロードフレームを30秒とする。すべて設定で変更可能とする。

Session層がコマンド種別に応じてペイロードのタイムアウトを選択し、接続ハンドラーが応答送信のタイムアウトを適用する。Frame CodecとTCP Serverはコマンド種別を解釈しない。これらは絶対期限ではなく、各ブロッキングsocket操作の無通信タイムアウトであり、各段階の正常終了・例外終了のどちらでも呼び出し前のsocket timeoutへ復元する。

### 7.4 ライフサイクル

サーバー起動状態は次の名前へ統一する。

```text
starting
initializing
ready
degraded
stopping
stopped
failed
```

初期版は`starting`で構成を読み、`initializing`でバックエンドと単一Hardware Workerを初期化する。初期化成功後に`ready`へ遷移し、その後でTCP listenを開始する。したがって、`ready`前のネットワークスレッドからロボットコマンドが実行される経路を作らない。

回復可能な機能低下は`degraded`、回復不能な初期化または実行失敗は`failed`、正常終了は`stopping`を経て`stopped`とする。

## 8. Command Router

Command Routerは、コマンドを対応するApplication Serviceへ振り分ける。

```text
play_pose         -> MotionService.play_pose
stop_pose         -> MotionService.stop_pose
play_motion       -> MotionService.play_motion
stop_motion       -> MotionService.stop_motion
play_idle_motion  -> MotionService.play_idle
stop_idle_motion  -> MotionService.stop_idle
play_wav          -> AudioService.play
stop_wav          -> AudioService.stop
read_axes         -> AxisService.read
```

巨大な `if/elif` へ集中させず、コマンド定義表またはハンドラー登録方式を使用する。

初期段階では、Routerが依存する`RobotCommandTarget`をApplication Command Serviceが実装する。複数のTCP workerはこのServiceの有界FIFOキューへ同期的にコマンドを投入し、下位Targetの完了まで待つ。下位Targetを呼ぶのはServiceが所有する単一worker threadだけとし、TCP workerから直接呼び出さない。

## 9. Motion Scheduler

### 9.1 目的

Motion Schedulerは、Pose、MotionおよびIdle Motionの競合を一元管理する。

### 9.2 動作モード

以下はMotion Scheduler内部の動作モードであり、7.4節のサーバー起動状態とは別の概念である。

```text
IDLE
DIRECT_POSE
MOTION
IDLE_MOTION
STOPPING
FAILED
```

ここでの `IDLE` は「アイドルモーション実行中」ではなく、動作タスクがない状態を意味する。

### 9.3 優先順位

既定値は次とする。

```text
stop > direct pose > motion > idle motion
```

### 9.4 新しい要求の扱い

* direct poseは実行中のmotionとidle motionをキャンセルする。
* motionは実行中のidle motionをキャンセルする。
* motion実行中に新しいmotionを受けた場合は、既定では古いmotionを置換する。
* idle motion実行中に再度idle motionを受けた場合は、設定を置換する。
* stopは対象タスクがなくても成功扱いとする。
* 音声はサーボ動作とは別の所有権で管理する。

### 9.5 世代番号

Schedulerは単調増加するgenerationを持つ。

新しい動作または停止を受理するたびにgenerationを進める。

各タスクは開始時generationを保持し、ハードウェア指令前に現在generationと一致するか確認する。

停止または置換された古い世代は、キュー投入時だけでなく、単一Hardware Workerが実際にハードウェア指令を送る直前にも世代を検証する。これにより、キャンセルされたタスクがsleepから復帰した場合や、古い指令がWorkerキューに残った場合にも送信を防ぐ。

### 9.6 停止

停止処理は次を行う。

1. generationを進める
2. 対象タスクへキャンセルを通知する
3. 未実行キューを破棄する
4. 必要なら現在位置を読み取る
5. バックエンドごとの安全な保持処理を行う
6. 停止完了状態へ遷移する

無条件のトルクOFFは共通処理に含めない。

### 9.7 初期Scheduler実装

Schedulerは`RobotCommandTarget`としてRouterの下に配置し、そのdownstreamを`SerializedRobotCommandTarget`とする。Mock構成はRecording Target、Serialized Target、Motion Scheduler、外部コマンド専用Logging Decorator、Routerの順に組み立てる。TCP workerはSchedulerを並行して呼べるが、実際の下位Target呼び出しは引き続き単一command workerだけが行う。

`play_motion`はMotionを1件だけactiveとして登録した時点で戻る。専用Scheduler threadはPoseを入力順に1回ずつ送信し、`duration_ms / 1000.0`をcancel Eventでinterruptibleに待つ。新しいMotion、Direct Pose、Idle Motionまたは停止要求はgenerationを進めて古い処理を無効化する。各下位Pose送信前後、wait後、完了状態更新前にgenerationを再確認し、古いMotionが新しい状態を`NONE`へ戻すことを防ぐ。

`stop_motion`はactive generationを無効化して待機を解除し、進行中の下位Pose送信が完了したことを確認してから`stop_pose`を直列化層へ送る。このため、`stop_motion`が戻った後に停止対象generationの残りPoseは送信されない。Idle MotionのPose生成、stopの優先キュー、サーボ補間および実機の遷移時間実現方式はこのSchedulerの責務に含めない。

## 10. 補間

### 10.1 共通方針

補間方式はバックエンドの能力によって異なる。

```text
Backend A:
    実機側が遷移時間を受け付ける
    -> 目標値と時間を1回送信

Backend B:
    実機側が即時目標値だけを受け付ける
    -> Python側で中間値を生成
```

### 10.2 補間能力

バックエンドは次を能力として公開する。

* native timed pose support
* software interpolation required
* maximum update rate
* readable current position
* simultaneous multi-axis update
* LED support
* torque control support

### 10.3 ソフトウェア補間

初期実装は線形補間でよい。

将来、次を追加可能な構造にする。

* ease-in/ease-out
* smoothstep
* 速度上限
* 加速度上限
* 軸別補間

補間周期を固定回数のsleepだけで決めず、単調増加時計で経過時間を測る。

## 11. Hardware Worker

### 11.1 目的

ハードウェアデバイスへのアクセスを一つの実行系列へ直列化する。

### 11.2 入力

Workerは、検証済みの内部コマンドだけを受け付ける。

例:

```text
Initialize
ReadAxes
ApplyPose
SetLed
Stop
Close
```

### 11.3 キュー

* 有界キューとする。
* キュー満杯時の方針を明示する。

Application Command Serviceはcapacity 16、enqueue timeout 1秒を変更可能な実装設定として持ち、FIFO順で処理する。公開メソッドは下位Targetの結果または例外が確定するまで同期的に待つ。

上位Motion Schedulerが古いgenerationの無効化、interruptible waitおよびMotionのPose展開を担当する。Serialized WorkerはMotion Schedulerから渡された各PoseをFIFOで1回実行するだけで、補間、sleepまたはMotion全体の完了待ちを行わない。stop専用の優先キューとキュー内項目削除は実装しない。

### 11.4 排他

I2Cとシリアルポートを複数スレッドから直接操作しない。

## 12. Robot Backend

概念的なインタフェースは次のようにする。

```python
import abc
import typing

class RobotBackend(abc.ABC):
    @abc.abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def capabilities(self) -> RobotCapabilities:
        raise NotImplementedError

    @abc.abstractmethod
    def profile(self) -> RobotProfile:
        raise NotImplementedError

    @abc.abstractmethod
    def read_axes(self) -> typing.Mapping[str, int]:
        raise NotImplementedError

    @abc.abstractmethod
    def apply_pose(self, pose: Pose) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def stop_motion(self) -> None:
        raise NotImplementedError
```

実装では`typing.Protocol`を使用せず、原則として`abc.ABC`を使用する。

### 12.1 RobotProfile

プロファイルは以下を定義する。

* 公開軸名
* 内部ID
* 外部範囲
* 内部範囲
* 変換式
* LED名
* LED内部ID
* 初期姿勢
* アイドル姿勢
* 安全上限
* 読み出し対象軸
* 未対応機能

### 12.2 Mock Backend

Mockは実機と同じインタフェースを実装し、決定論的に動作する。

Mockはログを出すだけでなく、内部状態を更新して `read_axes` へ反映する。

### 12.3 Edison Sota Backend

Edison版Sotaの標準Backend候補は、実機deviceへ直接アクセスせず、
TCP `127.0.0.1:6498`の`vsmd_edison`を利用する。

```text
MotionSchedulingCommandTarget
→ SerializedRobotCommandTarget
→ 将来のVsmdSotaCommandTarget
├→ VsmdMemoryClient / VsmdTypedMemory
│  → VsmdTcpTransport
│  → TCP 127.0.0.1:6498 / vsmd_edison
│  → UART / I2C / GPIO / shared memory
└→ AppManagerLedLockLease
   → AppManagerTcpTransport
   → TCP 127.0.0.1:6495 / SotaAppManager.jar
```

Protocol codec、TCP Transport、byte/typed memory、確認済みSota memory map、
read-only probe、口LEDドメインモデルは`hardware/vsmd/`へ隔離する。詳細、
確認済み事項、静的解析による確認、未確認事項は
[`sota-backend-design.md`](sota-backend-design.md)に定義する。

2026-07-28、次の接続構成でread-only経路を実機確認した。

```text
Windows 11 / Python 3.14.3
→ 127.0.0.1:6498
→ SSH local port forwarding
→ Intel Edison 127.0.0.1:6498
→ vsmd_edison
```

この試験ではbanner、selector、AudioDiff、`InterpLEDTarget[14]`、
`InterpLEDOutput[14]`、`ServoReadPos` 32要素を読み取り、Codec、Transport、
byte/typed memory、memory map、probeまでのread-only層がSSH tunnel越しにも
動作することを確認した。VSMD writeは送信しておらず、servoまたはLEDの状態変化も
観測されなかった。これは`VsmdSotaCommandTarget`の統合やproduction writeの
検証ではない。既定Composition Rootは引き続きMockである。実測値と実行記録は
[`protocol-compatibility.md`](protocol-compatibility.md)および
[`sota-backend-design.md`](sota-backend-design.md)に集約する。

2026-08-01、専用のraw-axis observerについてIntel Edison上のread-only runtime
acceptanceを完了した。observerのread pathは次のとおりである。

```text
SotaAxisReadOnlyObserver.observe()
  -> VsmdSotaRawAxisStateSource.read_raw_positions()
  -> VsmdTypedMemory.read_s16_array()
  -> VsmdMemoryClient.read_bytes()
  -> VsmdTcpTransport.send() / read_line()
  -> 32 signed S16 values
  -> CSV output
```

memory read requestは`transport.send()`からTCP 6498へ送信される。これはnetwork送信を
伴うVSMD read pathであり、network I/Oがないという意味のread-onlyではない。このobserver
pathは`write_bytes()`、`encode_write_request()`、typed memory write、AppManager、servo
target writeへ接続しない。read pathのruntime acceptanceをwrite pathの安全性または互換性へ
一般化しない。raw index mappingとdegree変換の実機妥当性は未確認であり、live servo writeは
引き続き禁止する。詳細は
[`edison-read-only-axis-observer-acceptance.md`](edison-read-only-axis-observer-acceptance.md)
を参照する。

実機上の`sotalib.jar`通信をPCAPで確認したVSMD write形式は
`w 0124 9c 0c\r\n`のようにcommand、4桁lower-case hexadecimal address、
各2桁lower-case hexadecimal byteをASCII space 1個で区切る。Codecはこの
wire表現だけを生成し、network I/Oとは分離する。readのPython APIはsizeを
byte数の整数で受けるが、wire tokenはlower-case hexadecimalで生成する。
したがって64 bytesは`R 0e80 40\r\n`であり、`R 0e80 64\r\n`はVSMD側で
`0x64`、つまり100 bytesとして解釈される。

read responseは`#0124 8a 00 \r\n`のように最後のbyteとCRLFの間へASCII
space 1個を含む場合がある。Codecは末尾spaceを0個または1個だけ許可し、
行頭space、連続space、tab、LF単独、token幅不正は拒否する。

TCP 6495は1 request / 1 connection、server-first Java serialization header、
compact ASCII JSON + LF、限定Java response decoder、single-release leaseへ分離する。
2026-07-31のcompetition probeでは、異なるkeyのAとBが同じLED ID 14を同時に
LOCKでき、それぞれ別の有効なtimer slotへCONVERTした。したがってAppManagerは
interpolation timer lease／slotを割り当てるが、LED-ID-exclusive cross-process
arbitrationは提供しない。同一`AppManagerVsmdLedLock` instance内の重複拒否はlocal
adapter behaviorである。

協調process間の排他は`robot_controller.process_lock.ProcessLock`と
`robot_controller.posix_process_lock.FcntlProcessLock`が担う。既定path
`/run/lock/robot-controller-sota.lock`を`LOCK_EX | LOCK_NB`で取得し、粒度はSota
1台全体である。live Sota double opt-in時はApplication、Backend、server socket、
AppManager／VSMD transportの構築前に取得し、競合時はretryせずfail-closedする。
lock fileは通常終了時にunlinkしない。crash、`SIGKILL`、電源断ではkernelがfdを
閉じてlockを解放する。

このlockはadvisoryであり、同じguardを使用しない外部programやTCP 6495／6498への
直接接続を防止しない。productionでは外部clientを原則TCP 22222のguard済みserverへ
集約する。lockを迂回するfallback、`InterpLEDOutput`への直接write、接続時の
`InitRobot()`・`ServoOn()`・初期Pose相当は実装しない。

既存のFutaba UART codec/transport/probeは削除せず、低レベル調査用の
experimental Backendとして隔離する。`vsmd_edison`が提供する補間、可動域、
現在位置、LEDおよびI2C制御を再利用できないため、標準Backendにはしない。

### 12.4 非公式実装の出典管理

非公式な低レベル実装を参照するときは、`docs/protocol-compatibility.md`のReference baselines節へ、リポジトリURL、検証済みの完全なcommit SHA、確認日、ライセンス、コピーしたコードか仕様だけを参考にした再実装か、および各レジスタ・ID・パケット・可動範囲の検証状態を記録する。

完全なcommit SHAまたは値の根拠を確認できない場合は推測せずTODOとし、その値を実機ドライバへ実装しない。

## 13. Audio Manager

Audio Managerは、音声の保存、再生、停止、後始末を一元管理する。

### 13.1 再生処理

1. WAVを検証する
2. 安全な一時ディレクトリに一意なファイルを作る
3. 再生プロセスを起動する
4. PIDまたはプロセスオブジェクトを保持する
5. 終了を監視する
6. 一時ファイルを削除する

### 13.2 停止処理

* 管理中のプロセスだけに停止を要求する。
* 一定時間で終了しない場合だけ強制終了する。
* 開始前、終了済み、停止済みでも例外にしない。

### 13.3 口LED連動

口LED連動はAudio Managerとバックエンドの追加機能として実装可能にする。

初期移行の必須機能とは分離し、音声再生そのものを先に完成させる。

## 14. 設定

設定項目の例を以下に示す。

```yaml
server:
  host: "0.0.0.0"
  port: 22222
  max_connections: 16
  command_json_read_timeout_seconds: 5
  wav_read_timeout_seconds: 30
  max_command_bytes: 64
  max_json_bytes: 1048576
  max_wav_bytes: 20971520

robot:
  type: "Mock"

motion:
  max_pose_duration_ms: 60000
  max_motion_poses: 1000
  interpolation_interval_ms: 50

audio:
  player_command: ["aplay"]
  temporary_directory: null

security:
  allowed_networks: []
```

上記の接続数、タイムアウトおよびフレーム上限は初期既定値として確定済みであり、設定で変更可能とする。Frame Codecへはフレーム種別に対応する値を`max_length`として渡す。

## 15. 例外設計

例外を少なくとも次に分類する。

* ProtocolError
* FrameTooLargeError
* ConnectionClosedError
* DecodeError
* ValidationError
* UnknownCommandError
* RobotNotReadyError
* UnsupportedCapabilityError
* HardwareCommunicationError
* HardwareTimeoutError
* MotionConflictError
* AudioPlaybackError
* ConfigurationError

v1では例外をクライアントへ構造化送信しない場合でも、内部で分類する。

## 16. ログ

ログには相関可能な接続IDまたはコマンドIDを付ける。

推奨フィールド:

```text
timestamp
level
event
connection_id
remote_address
command
robot_type
generation
duration_ms
result
error_type
```

WAV内容や巨大なJSON全体を通常ログへ出さない。

## 17. テスト構成

### Unit

* Frame Codec
* Validator
* JSON変換
* Scheduler
* 補間
* Profile変換
* Audio Manager
* CPython 3.6.15構文互換性

### Integration

* TCP接続からMock Backendまで
* 複数接続
* 部分受信
* タイムアウト
* キャンセル
* サーバー終了

### Compatibility

* `robo-tutorial`相当クライアント
* Java版と同じ正常入力
* `read_axes`応答

### Hardware

* 明示的なマーカーを付ける
* 既定では実行しない
* 1試験ずつ人間が確認する
* 試験値をコードへハードコードせず、検証済みfixtureを使用する

pytestはPython 3.6対応版へ固定し、初期候補を`pytest==6.2.5`とする。開発ツールが新しいPython上で動作する場合も、本番コードへPython 3.6非互換構文を導入しない。

## 18. デプロイ

Windowsおよび現在のproduction Composition RootではMockで実行する。

```text
robot.type = Mock
```

mouth LEDのSota Backendは、次のdouble opt-in時だけproduction serverで選択する。

```text
ROBOT_MOUTH_LED_BACKEND=sota_vsmd
ROBOT_HARDWARE_LIVE_WRITE_ENABLED=true
```

この場合、serverは設定validation後、Application／Backend／listen socketの生成前に
whole-Sota process lockを取得する。競合時は起動を継続しない。Mock、Unavailable、
live write無効の経路はlockもlive transportも生成しない。full
`VsmdSotaCommandTarget`とSota単一軸制御は別の未完了gateである。

実機への配布物は、可能であれば次を含む。

* Pythonパッケージ
* 設定ファイル
* 起動スクリプト
* ログ設定
* バージョン情報
* 手動ロールバック手順
