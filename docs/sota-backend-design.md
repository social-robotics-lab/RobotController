# Sota Backend設計とread-only capability probe

## 1. このフェーズの位置付け

本書は、将来のSota実機Backendに先立つ安全設計と、サーボを駆動しない
capability probeの境界を定義する。現時点では`SotaCommandTarget`、実機用
`RobotProfile`、UART実装、Goal Position／Goal Time／torque／LEDの書き込みを
実装しない。本番TCP ServerとMock Serverにもprobeを組み込まない。

2026-07-26に、次のリポジトリ内資料を確認した。

* `AGENTS.md`
* `docs/requirements.md`
* `docs/architecture.md`
* `docs/migration-plan.md`
* Python版の`motion_scheduler.py`、`command_service.py`、
  `command_target.py`、`profiles.py`、`errors.py`
* Java版の`ServoConverter_Sota.java`、`LedConverter_Sota.java`、
  `RobotSys.java`、`AxisReader.java`、`PoseExecutorThread.java`、
  `PosePlayer.java`、`MotionPlayer.java`、`MotionExecutorThread.java`
* リポジトリ全体のRobotLib、Futaba、UART、packet、checksum、baud、
  serial、Goalおよびtorqueに関するファイルと文字列
* Futaba公式「コマンド方式サーボ」製品資料および公式manual一覧

リポジトリ内にはVSTONE RobotLibの実装JAR／ソース、Futabaサーボ仕様書、
通信仕様書、既知packet sampleまたはpacket test vectorが存在しない。
Java版は`jp.vstone.RobotLib`の高水準APIを呼ぶだけである。このため、低水準
packetの具体値をJava版から導出したとは扱わない。

Futaba公式製品資料では、コマンド方式サーボ共通のfield順序が
`Header + ID + Flag + Address + Count + Length + Data + Checksum`であることを
確認した。ただし、Sota搭載servoのmodelをリポジトリ資料から特定できないため、
特定modelのmanualにあるaddress、flag、baud、checksum等をSota用として採用
しない。

確認した公式ページ（2026-07-26）:

* <https://www.futaba.co.jp/product/industrial_servo/command_type_servos>
* <https://www.futaba.co.jp/product/industrial_servo/command_type_servos/robot_download/manual>

## 2. 確認できた範囲

Java版から確認できるのは次の高水準情報である。

* Sotaの公開軸名とJava版内部IDは、`BODY_Y=1`、`L_SHOU=2`、
  `L_ELBO=3`、`R_SHOU=4`、`R_ELBO=5`、`HEAD_Y=6`、`HEAD_P=7`、
  `HEAD_R=8`である。
* `AxisReader`はID 1から8に対し、RobotLibの`getReadpos()`が返す配列を
  対応付ける。低水準read packetは見えない。
* Java版には軸ごとの角度変換・クランプ値があるが、これは既存アプリケーション
  の変換であり、サーボモデルの物理安全域としては未検証である。
* LEDの公開名とJava版内部IDの対応は確認できるが、LED transportや
  registerは確認できない。
* `RobotSys`はRobotLibの初期化後に`ServoOn()`、pose、torqueおよびLEDを
  設定する。この副作用をread-only probeでは再利用しない。
* `PoseExecutorThread`は`motion.play(pose, msec)`へミリ秒値を渡すが、
  RobotLib内部のGoal Time変換は見えない。
* Java版`PosePlayer.stop()`は現在位置を読み、100 msのPoseとして送り直す。
  これは停止候補の参考にはなるが、物理的安全性は検証されていない。

次は未確定であり、実機送信可能なコードへ値を置かない。

| 項目 | 状態 |
| --- | --- |
| シリアルdevice | TBD: architectureに候補記載はあるが実機構成で未確認 |
| baud rate／UART条件 | TBD: hardware probe/manual verification |
| サーボモデルとモデル番号 | TBD: manual verification |
| field順序 | Futaba公式資料でHeader, ID, Flag, Address, Count, Length, Data, Checksumを確認 |
| packet header値、flags、address、length、countの意味 | TBD: verified model manual |
| checksum方式 | TBD: verified manual/test vector |
| read命令とresponse形式 | TBD: verified manual/test vector |
| model／position／torque／温度／電圧register | TBD: verified manual |
| broadcast ID | TBD: verified manual |
| Goal Timeの単位、上限、量子化 | TBD: model-specific manual |
| torque操作と安全停止 | TBD: model-specific manual/hardware test |
| サーボ可動範囲 | TBD: mechanical and model verification |

## 3. 将来の層構造

```text
MotionSchedulingCommandTarget
→ SerializedRobotCommandTarget
→ SotaCommandTarget
→ SotaTransport
→ Edison UART／VSTONE hardware
```

* Motion SchedulerはMotionのPose展開、時間進行、所有権、generationおよび
  cancelを担当する。
* Serialized Serviceは下位呼び出しを有界キューで単一スレッド化する。
* 将来のSotaCommandTargetはPose、stop、axes、WAV、LED等の実機上の意味、
  Profile変換およびcapability判定を担当する。
* Transportはbytesの送受信、明示的timeout、partial read、device closeだけを
  担当する。
* Packet Codecは確認済みpacket定義によるencode／decode、長さ、ID、
  checksumおよびresponse構造の検証だけを担当する。

Codec、TransportおよびprobeへMotion、軸名、Profile、retry、torque方針を
混在させない。

## 4. Packet Codecのfail-closed方針

`hardware/futaba_codec.py`は、公式資料で確認したfield順序を使用し、
headerとchecksum関数を
`FutabaPacketDefinition`として明示注入する純粋Codec境界を提供する。
header、checksum、read addressおよびflagsの既定値はない。現在のリポジトリ
資料だけでは実機用definitionを構築できないため、テストのheader／checksumは
構造試験専用であり、実機仕様を表さない。

確認済みマニュアルを入手した後、次を別々の既知vectorで確認する。

1. read requestのexpected bytes
2. 正常responseのexpected bytes
3. checksum不正、header不正、length不正
4. unexpected ID、stale response、partial response
5. 最大response長

encode後に同じCodecでdecodeするだけの循環試験を仕様根拠にしない。

## 5. Transport

`SotaTransport`の境界は次である。

```text
open()
write(bytes)
read_exact(size, timeout) -> bytes
close()
```

context managerに対応し、`close()`は冪等とする。`read_exact`はpartial readを
結合し、EOF、timeoutおよびEINTRを区別する。例外文字列へbuffer全体を含めない。
Windowsテストでは`FakeSotaTransport`を用いる。fakeはwrite履歴のsnapshotを
返し、外部変更で内部記録を壊せない。

`PosixSerialTransport`は現時点ではfail closedである。import時に`termios`を
読み込まずdeviceをopenしない。UART条件の根拠が確定するまで、POSIX上でも
`open()`を拒否する。標準ライブラリだけの実装ではbaud定数、raw mode、
exclusive openおよびtimeoutのOS差を個別検証する必要がある。pyserialは実装を
簡素化する一方、Python 3.6／Yocto対応、導入方法、ライセンスおよび追加依存を
評価する必要があるため、このフェーズでは追加しない。

## 6. capability probe

`tools/sota_probe.py`は既定でdry-runである。device、baud rate、servo IDsを
必須指定し、IDの総当たりやdevice自動検出を行わない。dry-runではtransportを
構築もopenもしない。

実行には`--execute-read-only`を要求する。ただし、現在は確認済みread packet
definitionがないため、deviceをopenする前に
`UnverifiedHardwareSpecificationError`で拒否する。仕様確定後も
`ReadOnlyRequest`が許可する操作は`read_model`だけであり、write系operationを
構築できない。

probe coreはservoごとに結果を分離する。一台のtimeout／checksum不正により、
明示指定された後続IDの結果を失わない。raw responseは`--show-raw`時だけ表示
する。通常出力はdevice、baud、指定ID、応答有無、model identifier、対応可否、
および限定されたerror型だけとする。

現時点でmodel allowlistは空である。未知modelを対応済みに推測しない。

## 7. サーボモデル確認とready条件

将来のBackend初期化は、各設定済みservo IDからmodel情報を読み、検証済み
allowlistと照合する。

* 未知modelはfail closedとする。
* 一部IDだけ応答しない場合もreadyにしない。
* model確認前にtorque、位置、Goal TimeまたはLEDを書かない。
* probe結果と設定済みIDの過不足を初期化エラーにする。
* ID重複を拒否する。

model番号を読むregister／packetはTBDである。

将来のSota Backendは最低限、device open、UART条件設定、設定済み全servoの
応答、model allowlist、ID重複なし、Profileとの軸対応、`read_axes`、必要な
LED／WAV機能の初期状態を確認後にreadyとする。ready前にTCP listenしない。

## 8. Goal Time

`Pose.duration_ms`をhardware時間へ変換する責務は将来のSotaCommandTarget側に
置く。次はすべてTBDである。

* model別の単位、最小／最大、量子化方法
* 範囲外をrejectするかclampするか
* 0 msの物理的意味
* 複数servoへ同じGoal Timeを送る方法
* Goal PositionとGoal Timeを同一packetへ含められるか
* model間の差異

Schedulerは現在と同じ`duration_ms`だけ待つ。packet送信時間の累積による
Motion driftを単調時計で測定し、補正するかは実機Backend試験後に決める。
通信結果が不明な副作用packetは盲目的に再送しない。

## 9. stopの物理的意味

次の三つを区別する。

1. Scheduler generationのcancel
2. 古いgenerationの後続Poseを送らない保証
3. 現在動作中のservoを物理的に停止する操作

現行SchedulerとSerialized Serviceは、stop後の古いPose投入を論理的に防ぐ。
ただし、Transportへwriteを開始済みの一packetを途中で取り消すことはできない。
実機I/O直前にもgenerationを再確認するAPIが必要かは、SotaCommandTarget設計時
に検討する。

物理停止の候補は、現在位置を読み、その値を新しい目標位置として、検証済みの
短いGoal Timeまたはhold方法で送ることである。Java版の100 ms Poseは参考情報
にすぎず、実機検証前に仕様確定しない。torque offを通常stopの既定動作に
しない。

## 10. torqueの安全方針

* torque enableと位置目標を同一packetに混在させない。
* Backend初期化時に無条件でtorqueを有効化しない。
* 可能なら現在のtorque状態をreadで確認する。
* torque offを通常stopに使わない。
* shutdown時のtorque方針は明示設定とし、既定値を推測しない。
* 応答喪失など結果不明のtorque packetを盲目的に再送しない。

## 11. timeout、response検証およびretry

read requestの送信timeoutとresponse待ちtimeoutを分離する。responseでは
partial length、header、checksum、servo ID、packet length、stale responseを
検証する。readのretry回数は設定化し、既定値は仕様・実機試験後に決める。
Goal Position、Goal Time、torque等の副作用writeは、結果不明時に自動再送
しない。

## 12. 実機probe前チェックリスト

実行は人間が内容を確認して手動で行う。Codex等の自動エージェントは実機で
実行しない。

- [ ] 検証済み公式manual、版、対象model、test vectorを記録した
- [ ] model read address／flags／length／checksumを独立vectorで確認した
- [ ] deviceとbaud rateを対象機の設定から確認した
- [ ] servo IDsを設定資料と物理構成から確認し、総当たりしない
- [ ] 対応model allowlistを確定した
- [ ] Java RobotControllerを人間が停止した
- [ ] 同じUARTを使用中の別processがないことを確認した
- [ ] aplay／LED processとは別にUART所有processを確認した
- [ ] probeが送る全bytesをレビューし、readだけであることを確認した
- [ ] robotを物理的に安定させ、緊急停止手順を担当者が把握した
- [ ] timeout、ログ保存、Java版への復帰手順を確認した
- [ ] probe終了時にdeviceがcloseされることを確認した

probeはprocessを自動killせず、`systemctl`を呼ばず、実機設定を変更しない。
