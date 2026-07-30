# Sota Backend設計：`vsmd_edison` TCP基盤

## 1. 位置付け

Sotaの標準Backend候補は、Futaba UARTやI2Cへ直接アクセスせず、
`127.0.0.1:6498`で待ち受ける標準制御デーモン`vsmd_edison`を利用する。

```text
MotionSchedulingCommandTarget
→ SerializedRobotCommandTarget
→ 将来のVsmdSotaCommandTarget
→ VsmdMemoryClient / typed memory
→ VsmdTcpTransport
→ TCP 127.0.0.1:6498
→ vsmd_edison
```

今回完成させるのは`VsmdProtocolCodec`相当の純粋関数、TCP Transport、
byte/typed memory、確認済みSota memory map、read-only probe、および
Fake lockで試験可能な口LEDドメインモデルである。`VsmdSotaCommandTarget`は
まだComposition Rootへ接続しない。Mockが引き続き既定構成である。

既存の`hardware/futaba_codec.py`、UART Transport境界、旧capability probeは
削除しない。ただし、これらは未確認の直接制御方式を調べるためのexperimental
基盤であり、Sota標準Backendにはしない。`sotalib.jar`が通常利用する
補間・可動域・現在位置・LED/I2C制御を`vsmd_edison`側に残すためである。

## 2. 根拠の分類

### 2.1 実機で確認済み

2026-07-28までの人手による実機調査で次を確認した。

#### read-only probe実機試験

Windows 11上のPython 3.14.3からSSH local port forwardingを使用し、Intel Edison上の
`vsmd_edison`へ次の経路で接続した。

```text
Windows Python 3.14.3
→ 127.0.0.1:6498
→ SSH local port forwarding
→ Intel Edison 127.0.0.1:6498
→ vsmd_edison
```

実行コマンドと結果は次のとおりである。

```powershell
cd C:\Users\tiio\Workspace\RobotController\python_server
py -3.14 -m robot_controller.hardware.vsmd.probe
```

```text
READ-ONLY VSMD probe: endpoint=127.0.0.1:6498 connect_timeout=1.0 read_timeout=1.0 write_timeout=1.0
server_banner=#vs-rc020 (Oct 31 2018 14:44:11)
mouth_selector address=292 value=138
AudioDiff address=138 value=0
InterpLEDTarget[14] address=2716 value=0
InterpLEDOutput[14] address=3228 value=0
ServoReadPos base=3712 length=32 values=0,5,-899,0,904,2,-2,-8,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
```

この試験で、接続とbanner、read Codec/Transport、byte/typed memory、確認済み
memory map、read-only probeまでの層が動作した。`ServoReadPos`は64 bytes
（wire size `40`）から32個のsigned little-endian S16として復号できた。上記の
個別値は姿勢や時刻で変化するためgolden vectorにはしない。

probeはread requestだけを送り、VSMD write requestを送信しなかった。試験中に
servoまたはLEDの状態変化は発生せず、`vsmd_edison`、SotaAppManager、device fileへ
変更を加えていない。

* `vsmd_edison`はTCP `127.0.0.1:6498`で待ち受ける。
* 接続直後に`#vs-`で始まる改行終端bannerを返す。
* read requestは`R {address:04x} {size_hex}\r\n`である。
* read responseは`#{address:04x} {byte:02x} ... \r\n`であり、最後のbyte後に
  ASCII spaceが1個入る場合がある。
* typed値はlittle-endianである。
* Sotaの口LEDはglobal LED ID 14であり、2番目のLED driverではlocal index 6。
* `InterpLEDOutput[14]`は`3200 + 14 * 2 = 3228`である。
* 口LEDselectorの音声同期sourceは138、通常補間output sourceは3228である。
* 人手によるJava/sotalib試験のgolden behaviorは次のとおり。

```text
LED14_LOCK_ACQUIRED=true
ORIGINAL_SELECTOR=138
ORIGINAL_TARGET=0
ORIGINAL_OUTPUT=0
SELECTOR=3228
AFTER_ON_TARGET=16
AFTER_ON_OUTPUT=16
AFTER_OFF_TARGET=0
AFTER_OFF_OUTPUT=0
RESTORED_SELECTOR=138
RESTORED_TARGET=0
RESTORED_OUTPUT=0
LED14_LOCK_RELEASED=true
```

復元後、短いWAVに対する口LED音声同期も正常であった。

### 2.2 Java bytecodeまたはPCAP解析で確認済み

同じPCAPで次のwrite列を確認した。これは実測済みbyte列である。

```text
w 01f6 00 00\r\n
w 0b9c f6 01\r\n
w 0124 9c 0c\r\n
w 0a9c 10 00\r\n
w 01f6 0b 00\r\n
w 0a9c 00 00\r\n
w 0124 8a 00\r\n
w 0b9c f4 01\r\n
```

確認された対応は次のとおり。

* `w 0124 9c 0c`: selector `0x0124`へ3228を書込む。
* `w 0124 8a 00`: selectorをAudioDiff address 138へ復元する。
* `w 0a9c 10 00`: `InterpLEDTarget[14]`へ16を書込む。
* `w 0a9c 00 00`: `InterpLEDTarget[14]`へ0を書込む。
* `w 0b9c f6 01`: `InterpLEDTriggerPointer[14]`へ`0x01f6`を書込む。
* `w 01f6 0b 00`: timer address `0x01f6`へ11を書込む。
* `w 0b9c f4 01`: TriggerPointerを`0x01f4`へ復元する。

captureから各writeの対応は確認できるが、TriggerPointerの割当規則、
timer addressの排他・所有権、lock protocolは未確認である。この観測だけから
Python版production lockを実装しない。

* Java版は`CRobotMem`と`CSotaMotion`を利用する。
* Java版の公開口LED IDは14である。
* `SotaAppManager.jar`はTCP `127.0.0.1:6495`で補間timerのlock、keyから
  timer addressへの変換、unlockを処理する。
* 1 request / 1 connectionで、server-first Java serialization headerの後に
  compact ASCII JSON + LFを送り、Java serialized responseをEOFまで受信する。
* 現在のPython構成は
  `MotionSchedulingCommandTarget → SerializedRobotCommandTarget → hardware target`
  で下位I/Oを単一workerへ直列化する。
* このリポジトリには`CRobotSock`本体、`sotalib.jar`または
  `SotaAppManager.jar`のsourceは含まれない。

### 2.3 未確認

* lock競合時の全応答と、他processによる重複lockを安全に検出する方法。
* process異常終了後のlock回復手順とstale owner処理。
* servo/LEDの全memory fieldの意味と更新順序。
* write送信後のdaemon内部適用時点。したがって失敗したwriteは自動再送しない。
* 496..558の範囲を越えた、lock keyからtimer slotへの完全な割当規則。
* Pythonからの安全なproduction LED write。
* `VsmdSotaCommandTarget`の完全統合。
* VSMDが許容する最大read size。
* 全responseで末尾ASCII spaceが必ず付くかどうか。

未確認値を推測したproduction fallbackは作らない。

## 3. Codec

`robot_controller.hardware.vsmd.codec`はsocketを操作しない。

* `encode_read_request(address, size)`
* `decode_read_response(data_line, expected_address, expected_size)`
* `encode_write_request(address, payload)`
* `parse_server_banner(line)`

addressは0..65535、sizeは正、payloadは非空とする。writeはlower-case `w`、
4桁lower-case hexadecimal address、各2桁lower-case hexadecimal byteを
ASCII spaceちょうど1個で区切り、CRLFで終端する。readのPython APIではsizeを
byte数の整数で受け、wireではlower-case hexadecimalへ変換する。

```text
R 0124 2   → 2 bytes
R 0e80 40  → 64 bytes
R 0e80 64  → 100 bytes
```

responseは4桁address、2桁byte token、要求address、要求byte数を完全一致で
検証する。末尾ASCII spaceは0個または1個だけ許可し、行頭space、連続space、
tab、末尾space 2個、余分・不足byte、不正hex、bannerのresponse誤認を拒否する。

## 4. TCP Transport

`VsmdTcpTransport`はconnect/read/write timeout、最大行長、内部line bufferを持つ。
fragmented receiveとcoalesced receiveの双方を処理し、bannerと最初のresponseが
同じ`recv()`に入ってもresponseを失わない。`connect()`と`close()`は冪等で、
context managerに対応する。raw socketは公開しない。

自動再接続と自動retryは行わない。特にwriteの送信開始後はdaemon側結果が不明に
なるため、`VsmdWriteOutcomeUnknownError`として上位判断へ戻し、重複実行を避ける。
通常のRobotControllerへ統合するときも、このTransportは単一hardware workerから
呼ぶ。

## 5. Memoryとtyped access

`VsmdMemoryClient`は次のbyte APIだけを持つ。

```text
read_bytes(address, size)
write_bytes(address, payload)
```

`VsmdTypedMemory`はU8/S8/U16/S16/U32/S32、U8/S16/U16 arrayをlittle-endian
で変換する。`bool`、非整数、型の範囲外、address spaceを越えるindexは拒否し、
maskや切り捨てを行わない。array element addressは
`calculate_indexed_address()`へ共通化する。

## 6. 確認済みmemory map

| 名前 | address/base | length |
| --- | ---: | ---: |
| `AUDIO_DIFF_VALUE_ADDRESS` | 138 | - |
| `MOUTH_LED_SELECTOR_ADDRESS` | 292 | - |
| `MOUTH_LED_AUDIO_SOURCE_ADDRESS` | 138 | - |
| `MOUTH_LED_NORMAL_SOURCE_ADDRESS` | 3228 | - |
| `INTERP_TARGET_TIME_BASE` | 496 | 32 |
| `INTERP_LED_TARGET_BASE` | 2688 | 16 |
| `INTERP_LED_OUTPUT_BASE` | 3200 | 16 |
| `SERVO_READ_POSITION_BASE` | 3712 | 32 |

`InterpLEDTarget`は指令値、`InterpLEDOutput`はdaemonが周期更新する出力値である。
口LED制御はTargetへ書き、Outputへ直接書いてはならない。

## 7. 口LEDドメインモデル

`SotaMouthLedController`は次の状態遷移を表す。

1. LED 14 lock取得。
2. selectorとTarget[14]を保存。
3. selectorが138または3228であることを確認。
4. selectorを3228へ切り替える。
5. Target[14]と正規の補間timerを使ってbrightnessを変更。
6. 終了時は安全値0、selector、元Targetの順で復元を試みる。
7. 例外や`KeyboardInterrupt`でもlock releaseを必ず試みる。

selector復元は元Target復元より先に試す。未知selectorでは一切writeせず
fail-closedにする。`close()`は冪等である。

`VsmdLedLock`は抽象のみである。production既定の
`UnavailableVsmdLedLock`は`VsmdLedLockUnavailableError`をwrite前に送出する。
したがって、現在のproduction構成にlockなしLED write経路は存在しない。

### 7.1 AppManager lock候補

`AppManagerProtocolCodec`はcompact request JSONと、`OK`、`NG`、`null`、確認済み
`java.lang.Short`だけを扱う。汎用Java deserializerではない。
`AppManagerTcpTransport`はTCP 6495へ1 requestごとに接続し、server-first headerを
検証してからASCII JSON + LFを1回送信し、4096 bytes以下のresponseをEOFまで読む。
自動retryは行わない。

`AppManagerLedLock.acquire_leds(ids)`は呼出しごとに
`python-led-<uuid4 hex>`形式のASCII keyを生成し、LOCK OK、key変換、timer address
検証の後に`AppManagerLedLockLease`を返す。leaseはkey、取得時IDsのtuple、timer
addressを保持し、UNLOCKは1回しか送らない。二重releaseは成功後no-op、失敗後は
同じ例外を再送出し、network retryを行わない。

LOCK OK後のconvert失敗では同じkey/IDsでbest-effort UNLOCKを1回試す。cleanupの
結果も不明なら`AppManagerOutcomeUnknownError`とする。lockはmutexではなく
TriggerPointer stack操作なので、同じLEDを複数keyで重ねず、leaseをnon-LIFO順に
解放しない。他processとの排他所有を保証せず、異常終了時の自動解放もない。

この候補は`VsmdLedLock`のproduction既定値を置換せず、Composition Rootにも接続
しない。実機LED writeは引き続き無効である。wire詳細とgolden vectorsは
[`protocol-compatibility.md`](protocol-compatibility.md)へ集約する。

### 7.2 mouth LED抽象へのadapter準備

`AppManagerVsmdLedLock`は`VsmdLedLock`を実装し、取得した
`AppManagerLedLockLease`を引数なしで解放できるadapter leaseとして返す。既存
`SotaMouthLedController`はleaseを返すlockと従来どおり`None`を返すFake lockの
双方を扱う。`AppManagerLeaseInterpolationTimer`はactive leaseから取得したtimer
addressへdurationを書き、固定LED indexからtimer addressを推測しない。同一adapter
内の重複LED leaseはnetwork request前に拒否するが、他processとのmutexは保証しない。

VSMD処理とcleanupの双方が失敗した場合は`VsmdMouthLedCleanupError`に元処理と
cleanupの両例外を保持し、release失敗を隠さない。adapterとtimerは未使用の
production候補であり、Composition Rootと既定`UnavailableVsmdLedLock`は変更しない。

socketを生成しない手動診断は次で実行できる。

```powershell
python -m robot_controller.hardware.vsmd.app_manager_mouth_led_dry_run
```

このdry-runはFake AppManager transportとFake VSMD memoryへ既存controllerが生成した
read/writeを記録するだけで、`live_network=false`、`live_write=false`である。
2026-07-29のlock-only実機試験ではtimer address `0x01f6`を取得し、TriggerPointerが
`0x01f4 → 0x01f6 → 0x01f4`と復元された。観測writeはtimer初期化と
TriggerPointer変更・復元だけで、selector、Target、Outputへのwriteはなかった。
この時点ではactual LED pulse testは未実施だった。

### 7.3 明示実行専用mouth LED live probe候補

`app_manager_mouth_led_probe`は人間が明示的に実行する診断候補であり、
`--confirm-live-write`がない場合はTCP 6495/6498のtransportもmemory clientも生成
しない。Composition Root、server起動経路、既定Backendには接続せず、既定
`UnavailableVsmdLedLock`も変更しない。

初期版はLED ID 14、level 1..16、transition duration 50..200 ms、hold duration
100..1000 ms（既定500 ms）、1 pulseだけをコードで
強制する。preflightでselector `0x008a`、Target 0、Output、TriggerPointerをreadし、
安全条件を満たす場合だけLOCKとCONVERTを行う。lock後は確認済み
`InterpLEDTriggerPointer[14]`アドレス`0x0b9c`がleaseのtimer addressと一致するまで
Target/timer writeを開始しない。pulseとselector/Target/timerのcleanupは既存
`SotaMouthLedController`へ委譲する。

UNLOCK後はleaseのstate、`is_released`、共有`OK`応答定数がすべて明示的成功である
場合だけpostflightを行い、selector、Target、TriggerPointerの復元を検証する。
Outputは表示するが時間差を考慮して一致条件にしない。release失敗または結果不明では
server側stackが残る可能性があるため、postflight、再LOCK、UNLOCK再送、adapter予約の
強制解除を行わずfail-closedで終了する。

2026-07-29のlive試験ではlock、VSMD write、cleanup、release、状態復元は成功したが、
物理mouth LEDは点灯しなかった。旧実装が200 msを200 control ticksとして直接
書いたためOutputが1までしか進まなかった。Vstone Javaと同じく、実機からpreflightで
`MasterCtrlPeriod` (`0x0040`, U32 µs)を1回readし、durationをfloor変換したticksへ
変換するよう修正した。同じperiodをprobe終了まで使うことで、1回の診断内でtimer換算
基準が変わらない設計とした。このtimer換算修正時点ではFake検証までで、
physical illumination gateは未完了だった。後述の同日実機試験で確認を進めた。

CLIの`result=success`はprotocol、memory operation、cleanup、release、postflightの
成功だけを表す。物理発光の自動確認ではないため、
`control_sequence_completed=true`と`physical_illumination=not_verified`も表示する。

修正版live probeは上昇transitionの完了を確認してから指定時間をwriteなしで保持し、
既存controllerの`turn_off(transition_duration_ms)`でTarget 0と正のtimer ticksを
設定して下降transitionも確認する。timer 0によるcleanupだけではOutputが0へ戻らない
ことが実機observerで確認されたため、selectorを復元する前に正規の下降補間を行う。
上昇・下降とも`pointer → remaining_before → output → remaining_after → lease timer`
の順にreadする。これは原子的snapshotではなく逐次observationである。Outputがphaseの
要求値、前後のRemainingTimeがともに0、TriggerPointerがlease timer addressの場合
だけ完了とする。timer値は診断用に記録するが成功条件には含めない。不一致は
`RemainingTime == 0`でも即時失敗とせず、最大3回だけ再確認する。
追加deadlineは`(timer_ticks + 2) * MasterCtrlPeriod`を基準に50～500 msへ制限し、
最初の4-read snapshotは途中のdeadline判定で破棄しない。deadlineは次のsnapshotを
開始するかだけを制御し、各snapshotの取得時間とpoll attemptを記録する。各readは
既存read timeoutで有界である。未完了・deadline・read失敗でも既存cleanupと
単一UNLOCKを通り、retry、再LOCK、UNLOCK再送は行わない。

selector、Target、TriggerPointerの復元は`routing_state_restored`として報告する。
Outputはselector復元後に物理mouth LEDへ接続されないため復元条件にはせず、
preflight値との一致を`interpolation_output_restored`で別に表示する。cleanup前の
下降確認でOutput 0を取得した場合だけ`interpolation_output_safe_zero=true`とする。
preflight Outputが非0なら、LOCK/CONVERT後もselectorをAudioDiffのまま維持し、
Target 0と正のtimerでOutput 0へ正規化してからselectorを切り替える。正規化失敗時は
selectorを切り替えない。selector切替後の処理が失敗した場合は、transportが利用可能
なら正のtimerによるemergency fade-downをbest-effortで1回行い、その後に既存closeと
単一UNLOCKを行う。primary errorとemergency/cleanup errorは別々に保持する。

2026-07-29の実機試験ではoperatorが物理点灯を確認し、Python LED write経路は
実証された。一方、非原子的なOutput 13 / RemainingTime 0を旧判定が失敗扱いし、
fade-downへ進まずtimer 0 cleanup後もOutput 16が残った。selectorはAudioDiffへ
復元された。補間完了後にtimer slot `0xffff`も観測したが意味論は未確認であり、
成功条件にはしない。

同日、逐次observation判定、selector切替前の正timer正規化、正timer fade-downを
含む再試験が終了code 0で成功した。normalization、rise、hold、fall、cleanup、
単一UNLOCK、routing復元がすべて完了し、試験後observer 3 samplesでOutput 0を
確認した。operatorによる物理点灯、bounded rise/hold/fall、安全なOutput 0終了の
3 gatesはcompleteである。CLIは目視を判定できないため
`physical_illumination=not_verified`を引き続き表示する。

逐次readにはSSH forwarding経由でnormalization `286.932 ms`、rise `222.331 ms`、
fall `242.134 ms`を要した。したがってhold 500 msはrise確認後の最低保持時間であり、
最大輝度の厳密な500 ms保持を保証しない。詳細な実測値と証拠inventoryは
[`evidence/mouth-led-live-test-2026-07-29.md`](evidence/mouth-led-live-test-2026-07-29.md)
を参照する。

```powershell
python -m robot_controller.hardware.vsmd.app_manager_mouth_led_probe `
  --app-manager-host 127.0.0.1 --app-manager-port 16495 `
  --vsmd-host 127.0.0.1 --vsmd-port 16498 `
  --led-id 14 --level 16 --duration-ms 200 --hold-ms 500 `
  --confirm-live-write
```

### 7.4 通常aplay用read-only observer

`mouth_led_observer`は明示実行専用で、TCP 6498から
MasterCtrlPeriod、AudioDiff、selector、Target、Output、TriggerPointer、
確認済みtimer領域内のpointer先、RemainingTimeを有限回readしてCSVへ出力する。
TCP 6495、LOCK、write、自動retry、Composition Root登録は使用しない。不正な
TriggerPointerは追跡readせず、`trigger_timer_value`を空欄にする。

```powershell
python -m robot_controller.hardware.vsmd.mouth_led_observer `
  --vsmd-host 127.0.0.1 `
  --vsmd-port 16498 `
  --interval-ms 20 `
  --samples 250
```

要求intervalと`time.monotonic()`で測定した実intervalを両方記録する。通常の
`aplay`観測は人間が手動で実行する。full observerは各addressを逐次readするため
sampling intervalはbest-effortで、CSV 1行は原子的snapshotではない。SSH tunnel
経由の20 ms指定では実測約350 msだった。AudioDiffだけを高頻度で追うfocused modeは
将来課題とする。

## 8. read-only probe

人間が実機で手動実行する場合だけ、次を使用する。2026-07-28にはWindows 11 /
Python 3.14.3からSSH tunnel経由でこのコマンドが成功した。

```powershell
cd C:\Users\tiio\Workspace\RobotController\python_server
py -3.14 -m robot_controller.hardware.vsmd.probe
```

このprobeはbanner、接続先、timeout、selector、AudioDiff、Target[14]、
Output[14]、ServoReadPos 32要素を表示する。read requestの送信だけを行い、
memory write APIや`--write`、`--execute`、`--disable-voice-sync`、
`--dry-run`を持たない。import時には接続しない。

Codexを含む自動エージェントは実機で実行しない。

### 検証済みテスト環境

実機probeと同時点で記録されたテスト結果は次のとおりである。

| 環境 | 結果 |
| --- | --- |
| Windows Python 3.14.3 | `693 passed` |
| Windows Python 3.6.8 | `693 passed` |
| `python:3.6.15-buster`、Python 3.6.15、pytest 6.2.5 | `691 passed, 2 skipped` |

Docker環境では`python -m compileall -q src`も成功した。2件のskip理由はこの記録では
確認していないため、結果値のみを記載する。

## 9. hardware safety

`vsmd_edison`を停止・disable・再起動しない。`/dev/ttyMFD1`、
`/dev/i2c-1`、GPIO、`/dev/shm/vsmd_mem`へPythonから直接writeしない。
probeはmemory readだけに限定し、servo、LED、torque、初期Poseを変更しない。
自動テストはsocket stubとFake memory/lock/timerだけを使う。

`UnavailableVsmdLedLock`のfail-closed動作は維持し、Python版production口LED制御は
有効化しない。`VsmdSotaCommandTarget`は既定Composition Rootへ接続せず、既定
BackendはMockのままとする。

実機でのread-only probeは人間が内容を確認して手動実行する。実機write試験は
lock protocol、復元順、低輝度・短時間の試験手順を別途レビューした後に限り、
自動テストとは分離して行う。

## 10. 次の解析項目

次の事項を追加解析し、実機writeとは分離してレビューする。

1. lock競合時の全responseとstack状態。
2. 他processによる同一LED lockを検出できるか。
3. non-LIFO unlock時のJava側挙動と回復手順。
4. process異常終了後のstale stackを安全に回復する運用。
5. lock取得後にだけTarget/selector writeが許可されることの実機確認。
6. Java `LockLEDHandle`/`UnLockLEDHandle`との追加golden vector比較。

これらと安全な実機試験手順を確定した後にのみproduction既定lockやexperimentalな
Composition Root設定を検討する。

## 11. experimental Futaba直接制御基盤の扱い

既存の`FutabaPacketCodec`、`SotaTransport`、`PosixSerialTransport`、
`SotaCapabilityProbe`は削除しない。公式manual、対象servo model、完全な
packet golden vector、device、baud、register、checksum、可動域が未確認のため、
現在どおりfail-closedな実験用境界として残す。

この経路で将来調査する場合も次の安全条件を維持する。

* `PosixSerialTransport`は確認済みUART条件が揃うまでdeviceをopenしない。
* model allowlist確定前にtorque、位置、Goal Time、LEDを書かない。
* torque enableを初期化時に推測で行わず、通常stopをtorque offにしない。
* 現在位置holdやGoal Timeの物理的意味をJavaの100 ms Poseだけから推測しない。
* 結果不明のposition、time、torque packetを自動再送しない。
* 非公式実装を参照する場合はURL、完全commit SHA、確認日、license、利用方法、
  各低レベル値の検証状態を`protocol-compatibility.md`へ記録する。

このexperimental経路を標準BackendまたはComposition Rootの既定値へ昇格させない。

## 12. 診断CLIから再利用Backendへのmouth LED pulse抽出

2026-07-29に実機検証したmouth LED pulse制御シーケンスは、
`hardware/vsmd/app_manager_mouth_led_pulse.py`の
`SotaMouthLedPulseOperation`へ抽出した。診断CLI
`app_manager_mouth_led_probe.py`は引数解析、`--confirm-live-write`確認、
依存生成、結果表示、exit code変換だけを担当する。

再利用境界は`hardware/mouth_led_backend.py`の`MouthLedBackend`であり、
`pulse_mouth_led(level, rise_ms, hold_ms, fall_ms)`を公開する。安全範囲は
実機検証済みのlevel 1..16、rise/fall 50..200 ms、hold 100..1000 msに
限定し、`bool`は整数として受理しない。VSMD address、timer address、
AppManager lock keyは呼出し引数へ公開しない。

`hardware/sota/backend.py`の`SotaVsmdBackend`は同一インスタンス内のpulseを
`threading.Lock`で直列化し、LOCK/CONVERT、normalization、rise、hold、
fade-down、selector復元、単一UNLOCKまでを既存のfail-closed手順で実行する。
lock、VSMD write、UNLOCKの自動retryは行わず、bounded observationだけを使う。
結果はtimer値、非原子的なread観測、cleanup、routing復元、lock解放を含む
構造化オブジェクトであり、物理的な発光を自動的に成功扱いしない。

この抽出時点ではComposition Rootへ接続せず、既定production BackendをUnavailable
としていた。後続の二重opt-in接続は14節に記載する。

## 13. 2026-07-30 抽出operationの実機回帰

抽出後の`SotaMouthLedPulseOperation`を既存の明示実行専用probe CLIから呼び出し、
物理Sota上で回帰確認した。MasterCtrlPeriodは`16667 us`、rise/fallはそれぞれ
11 ticks、割当timer addressは`0x01f6`だった。

```text
rise_reached_target=true
hold_completed=true
fade_down_completed=true
interpolation_output_safe_zero=true
routing_state_restored=true
lock_released=true
pulse_completed=true
result=success
```

riseはOutput 16へ到達し、hold後のfade-downでOutput 0へ戻った。cleanup後は
selector `0x008a`、target 0、output 0、TriggerPointer `0x01f4`となり、試験後の
read-only observationも安定していた。operatorは物理的なmouth LEDの
rise、hold、fade-down、消灯を確認した。preflight Outputは0だったため、
この回帰ではnormalization writeを必要としなかった。

この実機試験時点のCLIは`SotaVsmdBackend.pulse_mouth_led()`ではなく、
`SotaMouthLedPulseOperation`を直接生成していた。このため今回の結果は抽出operation、
AppManager lock、VSMD制御、cleanup、UNLOCKの実機証跡であり、
`SotaVsmdBackend` wrapper自体やComposition Root integrationの証跡ではない。

その後、probe CLIのコード経路は次のように変更した。

```text
app_manager_mouth_led_probe
    -> SotaVsmdBackend.pulse_mouth_led()
    -> SotaMouthLedPulseOperation
```

Backendの生成と`mouth_led_id`設定、`level`、`rise_ms`、`hold_ms`、`fall_ms`の転送、
成功結果と型付き失敗の表示、live確認前にBackendを生成しないことはFakeで回帰確認
した。その後、変更後のBackend経路も実機回帰した。Composition Root経路の
実機smokeは別gateであり、未実施である。

```text
thin_probe_uses_sota_vsmd_backend_in_code = complete
sota_vsmd_backend_fake_regression = complete
thin_probe_uses_sota_vsmd_backend = complete
sota_vsmd_backend_regression_on_hardware = complete
composition_root_opt_in = complete
edison_python36_direct_execution = complete
production_command_integration = pending
```

Composition Root経路の人手による実機smokeとEdison-local Python 3.6実行は後続で
completeとなった。次のvalidation stageはproduction command integrationである。

詳細:
[`evidence/mouth-led-pulse-operation-regression-2026-07-30.md`](evidence/mouth-led-pulse-operation-regression-2026-07-30.md)

## 14. Composition Rootへの二重opt-in接続

mouth LED Backendの設定と選択は`mouth_led_composition.py`へ集約し、既存の
`MockApplicationConfig`、`create_mock_application()`、`MockApplication`へ接続した。
Application Containerは次を公開する。

```text
mouth_led_backend: MouthLedBackend
mouth_led_backend_diagnostics:
    requested_backend_kind
    resolved_backend_kind
    live_hardware_write_enabled
    mouth_led_backend_configured
    unavailable_reason
```

既定kindは`unavailable`である。`mock`はhardware-free Backendを選択する。
`sota_vsmd`は`ROBOT_HARDWARE_LIVE_WRITE_ENABLED=true`との二重opt-inが成立した
場合だけ`SotaVsmdBackend`を構築する。live writeが無効な場合は
`Sota VSMD backend requested, but live hardware write is disabled.`をreasonとして
保持したUnavailableへfail-closedする。

booleanは文字列`true`と`false`だけを受理する。portは1..65535、timeoutは有限かつ
正、maximum line lengthは正の整数、hostは非空、mouth LED IDは検証済み14だけを
受理する。boolをintegerとして扱わず、NaN、Infinity、曖昧なboolean、未知kindを
configuration errorとして拒否する。

Sota設定には`ROBOT_SOTA_APP_MANAGER_HOST`、`ROBOT_SOTA_APP_MANAGER_PORT`、
`ROBOT_SOTA_APP_MANAGER_TIMEOUT`、`ROBOT_SOTA_VSMD_HOST`、
`ROBOT_SOTA_VSMD_PORT`、`ROBOT_SOTA_VSMD_CONNECT_TIMEOUT`、
`ROBOT_SOTA_VSMD_READ_TIMEOUT`、`ROBOT_SOTA_VSMD_WRITE_TIMEOUT`、
`ROBOT_SOTA_VSMD_MAX_LINE_LENGTH`、`ROBOT_SOTA_MOUTH_LED_ID`を使用する。
未指定値には既存transportのloopback endpointとtimeout、line length、LED ID 14を
使用する。

Backendの構築はconnection-freeである。Composition Root、Container、server startup、
次のsmoke CLIのdry-runでは、TCP接続、AppManager LOCK、VSMD read/write、sleep、
LED pulseを行わない。

```powershell
python -m robot_controller.diagnostics.mouth_led_backend_smoke
```

smoke CLIは通常と同じenvironment設定、`MockApplicationConfig`、
`create_mock_application()`を通す。既定はdry-runである。live実行時だけ
`container.mouth_led_backend.pulse_mouth_led()`を1回呼び、
`--level`、`--rise-ms`、`--hold-ms`、`--fall-ms`を既存の安全範囲で検証する。
CLI自身は`SotaVsmdBackend`を直接生成しない。

production protocol、legacy protocol v1、command handler、Router、TCP connection
handlerにはmouth LED Backendを接続していない。

```text
composition_root_opt_in_in_code = complete
composition_root_fake_regression = complete
composition_root_opt_in = complete
edison_python36_direct_execution = complete
production_command_integration = pending
```

double opt-in configurationは実機試験で正常に解決された。Composition Rootは
`SotaVsmdBackend`を生成し、Application Containerはsmoke CLIへ同Backendを供給した。
物理pulse、Output 0への復帰、selectorとTriggerPointerの復元、同一keyによる単一
LOCK/UNLOCKが成功した。

production protocol、legacy protocol v1、command handler、Router、TCP connection
handlerは引き続き未接続である。Edison-local CPython 3.6実行は後続試験でcomplete
となり、次のgateはproduction command integrationである。

詳細:
[`evidence/mouth-led-composition-root-regression-2026-07-30.md`](evidence/mouth-led-composition-root-regression-2026-07-30.md)

## 15. Edison-local実行で判明したlease pointer反映遅延

Edison上のPython 3.6からComposition Root smoke CLIを直接実行したところ、
AppManagerのLOCKとCONVERTは成功し、lease timer `0x01f6`を返したが、直後の
TriggerPointer readはLOCK前の`0x01f4`を返した。operationは
`VsmdMouthLedStateError`で中止され、物理LEDは点灯しなかった。

原因はLOCKの失敗ではなく、AppManager応答とVSMD TriggerPointer更新の可視化が
原子的ではないことである。ローカルreadはSSH転送経由より速いため、一時的な旧値を
観測できる。

operationは取得済みlease timer addressを期待値とし、既存の注入済み
`monotonic_function`と`sleep_function`を使ってTriggerPointer readだけを待つ。

```text
lock pointer timeout = 1.0 second
lock pointer poll interval = 0.01 second
```

timeoutとintervalは有限かつ正で、intervalはtimeout以下とする。boolは数値として
受理しない。公開`MouthLedBackend.pulse_mouth_led()` APIとCLI引数には露出しない。

pollingはLOCK／CONVERT成功とlease timer取得の後、selector、Target、timer、
normalization、riseの各writeより前に行う。期待値へ収束するまでmouth LED制御writeは
0回である。LOCK、CONVERT、lease取得、socket、pulse全体を再試行しない。

timeout errorにはexpected pointer、last observed pointer、lease timer、attempt数、
timeoutを含める。timeoutまたはpolling read失敗でも既存cleanupで同一leaseを
最大1回UNLOCKする。UNLOCKも失敗した場合は`VsmdMouthLedCleanupError`にprimary
pointer errorとcleanup errorの双方を保持する。

成功結果および利用可能な内部診断には次を保持する。

```text
lock_pointer_poll_attempt
lock_pointer_initial_value
lock_pointer_final_value
lock_pointer_wait_duration_ms
lock_pointer_converged
```

既存のoperation、Backend、Composition Root、production isolation gateは変更しない。
Edison-local CPython 3.6.15による修正後の成功確認を実施した。

```text
composition_root_opt_in = complete
edison_python36_direct_execution = complete
production_command_integration = pending
```

最初のTriggerPointer readは旧値`0x01f4`を返し、poll attempt 1で約13 ms後に
lease pointer `0x01f6`へ収束した。LOCKとCONVERTは再試行されず、LOCK、CONVERT、
UNLOCKはそれぞれ1回だった。物理pulseは成功し、Output 0、selector `0x008a`、
TriggerPointer `0x01f4`へ復帰した。

次のgateはproduction command integrationである。

詳細:
[`evidence/mouth-led-edison-python36-regression-2026-07-30.md`](evidence/mouth-led-edison-python36-regression-2026-07-30.md)

## 16. Production command integration

The Composition Root now wraps the existing robot target with
`MouthLedBackendCommandTarget`, using the exact `MouthLedBackend` instance
resolved from `MockApplicationConfig`. The wrapper is placed below the
existing `SerializedRobotCommandTarget`, so `mouth_led_pulse` uses the same
single command worker as the other commands. No new thread, queue, scheduler,
retry, Backend construction, AppManager construction, or transport
construction occurs in the handler.

After strict v2 decoding, the current router passes one immutable
`MouthLedPulse(level, rise_ms, hold_ms, fall_ms)` to the command target. The
target calls the injected Backend exactly once:

```text
v2 production connection handler
    -> CurrentCommandRouter
    -> existing serialized command service
    -> MouthLedBackendCommandTarget
    -> Composition Root supplied MouthLedBackend.pulse_mouth_led()
```

The default remains `UnavailableMouthLedBackend`. Sending a valid command in
that state returns `MOUTH_LED_BACKEND_UNAVAILABLE`; it does not construct a
Sota Backend or open an AppManager/VSMD connection. The existing double
opt-in remains unchanged:

```text
ROBOT_MOUTH_LED_BACKEND=sota_vsmd
ROBOT_HARDWARE_LIVE_WRITE_ENABLED=true
```

Server construction and startup remain connection-free and pulse-free.
Backend access starts only after a complete recognized command has passed
validation. Typed VSMD transport, lock/interpolation-state, and cleanup
failures are preserved as causes and translated to the sanitized
`MOUTH_LED_OPERATION_FAILED` response. Unexpected failures become
`INTERNAL_ERROR`.

The code and Fake regression gates were completed before the hardware run.
The production v2 route was then confirmed on the Edison with one
`v2/mouth_led_pulse` request. The physical LED illuminated and turned off,
the response reported success, Output returned to zero, selector and
TriggerPointer were restored, and a single LOCK/CONVERT/UNLOCK sequence
completed with the same key.

```text
production_command_integration_in_code = complete
production_command_fake_regression = complete
production_command_register_regression = complete
production_command_physical_confirmation = complete
production_command_integration = complete
phase7_mouth_led_golden_path = complete

edison_python36_direct_execution = complete
composition_root_opt_in = complete
sota_vsmd_backend_regression_on_hardware = complete
```

The double opt-in and fail-closed default are unchanged. Normal startup still
resolves to `UnavailableMouthLedBackend` unless both explicit Sota settings
are present. The successful production test does not make live writes the
default.

This result completes only the production mouth LED command path. The full
legacy-v1-facing `VsmdSotaCommandTarget` is not integrated into the
Composition Root. The next design gate covers lock contention, non-LIFO
release, and abnormal-process recovery:

```text
phase7_fault_recovery = pending
full_sota_command_target_integration = pending
```

Detailed production-command evidence:
[`evidence/mouth-led-production-command-visual-confirmation-2026-07-30.md`](evidence/mouth-led-production-command-visual-confirmation-2026-07-30.md)

## 17. mouth LED fault-recovery boundary

同一`AppManagerVsmdLedLock` instanceは、activeなLED IDの重複をlocal reservationで
AppManager送信前にfail-closed拒否する。別instanceは状態を共有せず、cross-process
相当の競合判断をAppManagerへ委譲する。LOCK拒否後はCONVERT、UNLOCK、VSMD
read/writeへ進まず、再試行もしない。

`AppManagerLedLockLease`だけが生成key、immutable IDs、CONVERT済みtimer addressを
所有する。releaseは単回attemptであり、成功後だけadapter reservationを解放する。
失敗またはoutcome unknownではreservationを維持して再取得を拒否する。CONVERT後の
best-effort UNLOCKも1回だけで、双方が失敗した場合は
`AppManagerAcquireCleanupError`にprimary acquisition errorとcleanup errorを保持する。

`SotaMouthLedPulseOperation`と`SotaMouthLedController`は`BaseException`をcleanup
対象にするため、通常例外に加えて`KeyboardInterrupt`と`SystemExit`でも、可能な
Target 0、timer 0、selector復元、単一UNLOCKを試みる。cleanup不能を成功結果には
しない。production command層の成功応答へも変換しない。hard terminationでは
`finally`自体が動かないため、コード上の完全回復は保証しない。

Fake-only smokeは次で実行でき、live transportやsocketを生成しない。

```powershell
python -m robot_controller.diagnostics.mouth_led_fault_recovery_smoke
```

運用回復手順は
[`operations/sota-mouth-led-lock-recovery.md`](operations/sota-mouth-led-lock-recovery.md)
を参照する。production正常系シーケンス、公開`MouthLedBackend` API、v1/v2 wire
protocolは変更しない。

```text
phase7_fault_recovery_in_code = complete
phase7_fault_recovery_fake_regression = complete
phase7_fault_recovery = pending
full_sota_command_target_integration = pending
```
