# Sota single-axis write-path static investigation (2026-08-03)

## 1. Status

```text
Status: Incomplete — stopped at the repository source boundary
Phase: 8b2d
Investigation type: Local static inspection only
Investigated revision: 57aa7c5a549848b9273b336d38afae56239b714e
Write-path runtime confirmation: Not performed
Live servo write readiness: Not established

Application-to-SDK boundary: completed
Vendor SDK artifact identification and binary provenance: completed
Deployed memdef candidate identity: completed
Active memdef selection mechanism: unverified
Vendor SDK internal write-path analysis: blocked pending source/license confirmation
```

アプリケーションのTCP受信から`CRobotMotion.play(CRobotPose, int)`呼出しまでと、
その呼出しへ渡す`Short`値への変換は追跡できた。後続のoperator evidenceにより、現在の
配布物が直接loadするvendor SDK JARと実機搭載copyの調査時点でのbinary identityも確認した。
Deployed Sota Normal memdef candidateのpath、content identity、metadataも確認した。しかし、
`jp.vstone.RobotLib`のJava source、memdefのactive selection mechanism、およびlicense上許可された
binary inspection範囲が未確認であるため、vendor API内部からservo target memory writeまでの
主要経路は追跡できていない。

これは作業指示の停止条件「active memdefを特定できない」および、確認済みbinaryに対する
許可済みstatic inspection手段がまだない状態に該当する。したがって本phaseは完了扱いにせず、
`docs/migration-plan.md`は更新しない。

## 2. Scope

次をlocal repository内で静的に調査した。

* legacy TCP `play_pose`／`play_motion`からJava motion APIまでのcall chain
* Sota公開degreeから`CRobotPose.SetPose()`へ渡す`Short`値までの変換
* repository内に見える初期化、servo enable、停止、cancel、例外、disconnect処理
* servo target memory field、address、型、index、write順序を確定できる根拠の有無
* AppManager／handle lockとPython whole-Sota process lockの適用境界

単一軸Poseと複数軸Poseは同じ`JSONObject`、`Map<Byte, Short>`、`CRobotPose.SetPose(Map)`
経路を通る。単一軸専用のJava write pathはrepository source内にない。

## 3. Safety boundary

本調査ではsourceと文書のread、およびdocumentation fileの作成だけを行った。
SSH、Edison接続、実機通信、VSMD／AppManager接続、memory read／write、servo／torque／LED
command、service／process操作、device file access、deploy、実機testは行っていない。

JavaまたはPythonのrobot-control programを起動しておらず、single-axis live write用codeも
実装していない。Process signal、debugger／`strace` attach、memdef変更／copy、license確認前の
decompilation／bytecode disassemblyも行っていない。`/run/lock/robot-controller-sota.lock`には
アクセスもunlinkもしていない。

## 4. Investigated revision

作業開始時に次を確認した。

| Item | Result |
| --- | --- |
| Branch | `feature/python-robot-controller` |
| `HEAD` | `57aa7c5a549848b9273b336d38afae56239b714e` |
| `origin/feature/python-robot-controller` | `57aa7c5a549848b9273b336d38afae56239b714e` |
| Tracked working tree | clean |
| Index | clean |
| Untracked | `robot_controller_edison_smoke.sha256` only |
| Protected-file SHA-256 | `0BF02AF8A83777B4F033C26A481A05C563726D8960F80AC24778F26CAD55CE59` |

## 5. Sources inspected

主要なsourceは次のとおりである。

* `AGENTS.md`
* `docs/requirements.md`
* `docs/architecture.md`
* `docs/protocol-compatibility.md`
* `docs/migration-plan.md`
* `docs/evidence/sota-axis-physical-correlation-2026-08-03.md`
* `docs/edison-read-only-axis-observer-acceptance.md`
* `src/main/App.java`
* `src/main/TCPServer.java`
* `src/main/ServerIO.java`
* `src/servo/RobotSys.java`
* `src/servo/ServoConverter.java`
* `src/servo/ServoConverter_Sota.java`
* `src/utils/PosePlayer.java`
* `src/utils/PoseExecutorThread.java`
* `src/utils/MotionPlayer.java`
* `src/utils/MotionExecutorThread.java`
* `src/utils/AxisReader.java`
* `python_server/src/robot_controller/hardware/vsmd/sota_memory_map.py`
* `python_server/src/robot_controller/hardware/vsmd/codec.py`
* `python_server/src/robot_controller/hardware/vsmd/memory.py`
* `python_server/src/robot_controller/hardware/vsmd/typed_memory.py`
* `python_server/src/robot_controller/hardware/vsmd/transport.py`
* `python_server/src/robot_controller/posix_process_lock.py`

Repository-wide symbol search、`rg --files`、`git ls-tree -r HEAD`およびlocal Git historyの
JAR／memdef path searchを行った。`jp.vstone.RobotLib` source、vendor JAR、`memdef.conf`は
見つからなかった。逆コンパイル対象そのものがなく、ライセンス判断もできないため、
逆コンパイルは行っていない。

### 5.1 Post-investigation operator-provided environment evidence

本書作成後のhuman-operated read-only調査から、次のruntime environment情報が提供された。
これはlocal static investigationで得たsource根拠ではなく、artifact provenanceを確認済みに
昇格させるものでもない。

* 観測時点でRobotController Java processは動作していなかった。
* PID 345は`/home/vstone/lib/SotaAppManager.jar`を`-jar`で実行するSotaAppManagerであり、
  cwdは`/home/vstone/vstonemagic/app`、executableは
  `/home/vstone/java/jdk1.8.0_40/bin/java`だった。
* PID 346は`/opt/sota/sotalogger/goSotaLogger`だった。
* **OPERATOR-CONFIRMED OPERATIONAL SELECTION:** current RobotController distributionは
  `/home/root/RobotController_bin`である。
* `/home/vstone/vstonemagic/app/jar/RobotController_bin_private`は現在の運用では使用されない
  inactive historical copyである。過去の外部program登録copyが残る可能性があるため、削除、
  変更、実行しない。
* **CONFIRMED:** `/home/root/RobotController_bin/RobotController.jar` manifestは
  `Main-Class: main.App`と次の`Class-Path`を記録する。

  ```text
  . RobotController_lib/core-2.2.jar RobotController_lib/gson-2.8.5.jar RobotController_lib/javase-2.2.jar RobotController_lib/jna-4.1.0.jar RobotController_lib/json-20180813.jar RobotController_lib/sotalib.jar
  ```

* **PACKAGE-CONFIRMED LOAD TARGET:** operationally selected distributionを基準にすると、
  RobotControllerが直接参照するvendor SDK artifactは
  `/home/root/RobotController_bin/RobotController_lib/sotalib.jar`である。
* **CONFIRMED:** read-only JAR entry inspectionでこの`sotalib.jar`に
  `jp.vstone.RobotLib` classesが含まれることを確認した。
* **CONFIRMED (binary identity at the investigation time):** 次の2 original filesは同じ
  SHA-256を持ち、調査時点でbyte-for-byte identicalである。

  | File | SHA-256 |
  | --- | --- |
  | `/home/root/RobotController_bin/RobotController_lib/sotalib.jar` | `7c3b45f42139a651e2c5d021c18ebf217cdb9be5af25569e910221d88d71bffa` |
  | `/home/vstone/lib/sotalib.jar` | `7c3b45f42139a651e2c5d021c18ebf217cdb9be5af25569e910221d88d71bffa` |

* したがってdistributionがload対象とする`sotalib.jar`は実機搭載
  `/home/vstone/lib/sotalib.jar`と同一binaryであり、後者を現在のRobotController用vendor SDK
  artifactのprovenance sourceとして扱える。Static investigationの主対象はdirect load targetで
  あるdistribution内JARとする。`/home/vstone/lib/sotalib.jar`の解析結果を使う場合も、上記hashが
  一致する調査時点のbinaryに限定する。
* 将来いずれかのfileが置換された場合、このidentityは継承せず両original filesのSHA-256を
  再確認する。
* 最初のmemdef検索は`/home/root`、`/opt`、`/usr/local`だけが対象で、`/home/vstone`を
  含まなかった。後続調査で`/home/vstone`配下のcandidateを確認したが、最初のempty resultを
  不存在または非使用の根拠にはしない。
* Edisonには`sha256sum`がなかった。将来のhash取得はoriginal fileに対して
  `openssl dgst -sha256`、次に既存CPythonの`hashlib.sha256`を使い、toolを追加installしない。

上記load targetはoperational selectionとpackage manifestに基づく確認であり、RobotController
processによるruntime class loading observationではない。RobotControllerのstartupには
`InitRobot_Sota()`、`ServoOn()`、torque、initial pose、LED設定を含むvisible legacy sequenceが
あるため、artifact identity確認の目的でもRobotControllerを起動してはならない。

### 5.2 Deployed memdef candidate evidence

Human operatorによるread-only metadata、hash、content searchから次を確認した。

#### 5.2.1 Candidate identity

| Classification | Path | Type | Size | mtime | SHA-256 |
| --- | --- | --- | ---: | --- | --- |
| **CONFIGURATION-LEVEL CONFIRMED deployed candidate** | `/home/vstone/vstonemagic/memdef.conf` | regular file; not symlink | 2491 bytes | `2015-06-19` | `9d289f1659384f92d7796c9e5031826804adca952aee0d24641f4c162169af11` |
| **CONFIRMED Sota Normal variant** | `/home/vstone/vstonemagic/memdef/memdef.conf.sota` | file | 2491 bytes | `2016-05-19` | `9d289f1659384f92d7796c9e5031826804adca952aee0d24641f4c162169af11` |

Canonical top-level pathは`/home/vstone/vstonemagic/memdef.conf`である。両original filesはSHA-256が
一致し、`cmp -s`でも一致したため、**調査時点でbyte-for-byte identical**である。Top-level fileは
Sota Normal variantの内容を持つ。将来どちらかが置換された場合、このidentityを継承せず再hashする。

次は異なるSHA-256を持つcandidate variantである。mtimeだけでactiveと判断しない。

| Candidate variant | SHA-256 |
| --- | --- |
| `memdef.conf.sota_im` | `c02b68130b1471c2821cdb9dc41d8090fb602a32e33a756bf76d69556502894c` |
| `memdef.conf.sota_im_T1` | `d6e494e260763a9681182d8e4a2fac20bc4c3761e440c9ffd58f5fe252bf9fb7` |
| `memdef.conf.sota_im_bat` | `12a203cefea4ff40f4764c6b02215067cb30acc4e0891378c3be7b509dba6d79` |
| `memdef.conf.sota_bat` | `9387dd3dc71416db3ae1375ba4bb2d4ff969fb9722305737c1f8fa0a35eac59e` |
| `memdef.conf2.sota_pi` | `286dccefc27dee13c928e79297a670622f1e1940155c3573b29a9e8469679cc1` |

#### 5.2.2 Configuration content

Top-level fileについて次は**CONFIGURATION-LEVEL CONFIRMED**である。

```text
Model: Sota_Normal
isModefied: false
ServoBusProtocol: 1
ServoBusNum: 8
ServoEN: 0
ServoSendEN: 1
I2CSendEN: 1
ServoLockDetectTime: 20
ServoLockDetectThreshold: 150
ServoLockDetectMaxTorque: 50
ServoSettings count: 8
```

各`ServoSettings`は少なくとも`id`、`readAngleEn`、`readAngleBank`、`max`、`min`、`offset`を含む。
これらはrobot model／servo configuration fieldとして確認しただけであり、次の意味を与えない。

* `ServoEN`の値0または`ServoSendEN`の値1をmemory addressやbooleanと解釈しない。
* これらの値だけからwrite／enable sequenceを導かない。
* `max`／`min`をphysical safe live-write rangeと解釈しない。
* `offset`をfinal VSMD write offsetと解釈しない。
* `readAngleBank`を`ServoReadPos` raw indexと解釈しない。

Vendor SDK内部での各fieldの意味論は**UNVERIFIED**である。

Top-level file本文のfield-name searchでは`ServoEN`と`ServoSendEN`だけが検出され、
`ServoReadPos`、`Servo.*Target`／`Target.*Servo`に相当するservo target field、target memory address、
`Interp` fieldの明示的定義は確認されなかった。このfileをVSMD memory address一覧として扱わず、
robot model／servo configuration fileとして扱う。Target definitionがvendor SDK内部または別resourceに
存在する可能性は残るが、「別の場所に必ず存在する」とは断定しない。

#### 5.2.3 Process file-descriptor observation

稼働中のPID 345に対する`ls -l /proc/345/fd | grep -i memdef`はemptyだった。

* **CONFIRMED:** 観測時点でPID 345が名前に`memdef`を含むopen file descriptorを保持していることは
  確認できなかった。
* **NOT ESTABLISHED:** PID 345がmemdefを使用しないこと、起動時load後にcloseした可能性、別名、
  relative path、JAR resourceまたは別process経由でloadした可能性。

Empty resultを非使用の証拠にしない。`sotalib.jar`または`SotaAppManager.jar`がtop-level fileを
実際に読み込むこと、load path、load timing、relative／absolute selection、variant priorityは
すべて**UNVERIFIED**である。

## 6. Java command-to-motion call chain

### 6.1 Direct Pose

次は**CONFIRMED (source-level, not runtime confirmed)**である。

1. `App.main()`がTCP serverと単一の`PoseExecutorThread`を並行起動する
   (`src/main/App.java:21-24`)。
2. `TCPServer.RecvThread.run()`が`ServerIO.read()`でcommand frameを読み、
   `play_pose`ならpayload frameを`PosePlayer.play(byte[])`へ渡す
   (`src/main/TCPServer.java:49-64`)。
3. `PosePlayer.play(byte[])`はplatform default charsetで`String`化し、
   `new JSONObject(text)`でparseして共有`LinkedBlockingQueue`へ追加する
   (`src/utils/PosePlayer.java:13-34`, `src/utils/PoseExecutorThread.java:16`)。
4. `PoseExecutorThread.run()`がqueueから`JSONObject`を取り、`Msec`を`getInt()`で取得する
   (`src/utils/PoseExecutorThread.java:21-25`)。
5. `ServoMap`があれば`ServoConverter.jsonToMap()`から
   `ServoConverter_Sota.jsonToMap()`へ委譲し、`Map<Byte, Short>`を作る
   (`src/utils/PoseExecutorThread.java:26-28`, `src/servo/ServoConverter.java:11-17`)。
6. mapは`CRobotPose.SetPose(Map<Byte, Short>)`へ渡される
   (`src/utils/PoseExecutorThread.java:25-29`)。
7. `PoseExecutorThread.play()`が`RobotSys.motion.play(pose, msec)`を呼ぶ
   (`src/utils/PoseExecutorThread.java:34,41-42`)。
8. Sotaでは`RobotSys.motion`の宣言型は`CRobotMotion`、生成実体は
   `new CSotaMotion(mem)`である (`src/servo/RobotSys.java:17,65-68,103-104`)。

この先、`CRobotMotion.play()`／`CSotaMotion`内部からVSMD memory writeまでのsourceは
repositoryにない。したがってstep 7以降は**UNVERIFIED**であり、target field、write method、
enable／interpolation処理を補完しない。

### 6.2 Motion

次は**CONFIRMED (source-level, not runtime confirmed)**である。

1. `play_motion` payloadは`TCPServer`から`MotionPlayer.play(byte[])`へ渡される
   (`src/main/TCPServer.java:65-69`)。
2. `MotionPlayer`はplatform default charsetで`String`化し、`JSONArray`へparseし、
   single-thread executorへ`MotionExecutorThread`をsubmitする
   (`src/utils/MotionPlayer.java:12-32`)。
3. `MotionExecutorThread.run()`は各`JSONObject`の`Msec`を読み、
   `PosePlayer.play(obj)`へqueueingしてから`Thread.sleep(msec)`する
   (`src/utils/MotionExecutorThread.java:13-22`)。
4. 以後はdirect Poseと同じ共有queue、conversion、`CRobotPose.SetPose()`、
   `RobotSys.motion.play()`経路である。

複数軸Poseも単一軸Poseも、`ServoMap` entry数以外に分岐はない。

## 7. Servo target memory mapping

Servo target mappingは次の理由で確定できなかった。

| Question | Finding | Classification |
| --- | --- | --- |
| Target field name | repository内に定義なし | **UNVERIFIED** |
| Base address／element offset | repository内に根拠なし | **UNVERIFIED** |
| Data type／signedness | API境界は`Short`だがmemory field型は不明 | **UNVERIFIED** |
| Byte order | generic VSMD typed writeはlittle-endianだがservo targetへの適用は不明 | **UNVERIFIED** |
| Array length | repository内に根拠なし | **UNVERIFIED** |
| Servo ID/index relation | `CRobotPose` map keyはID 1～8だがmemory index relationは不明 | **UNVERIFIED** |
| Whole-array／individual write | repository内に根拠なし | **UNVERIFIED** |
| Read-modify-write | repository内に根拠なし | **UNVERIFIED** |
| Java transport method | `CRobotMotion.play()`より下流のsourceなし | **UNVERIFIED** |

`SERVO_READ_POSITION_BASE = 3712`、length 32はread-only fieldの定義である
(`python_server/src/robot_controller/hardware/vsmd/sota_memory_map.py:27-28`)。
これは`ServoReadPos`であり、servo target addressとして使用してはならない。

GenericなPython VSMD stackには`encode_write_request()`、`write_bytes()`、`write_s16()`、
`write_s16_array()`、`write_s16_at()`が存在する
(`codec.py:152`, `memory.py:42`, `typed_memory.py:88,120,130`)。また既存文書は
generic write wireをlower-case `w`、typed値をlittle-endianとして記録する
(`docs/protocol-compatibility.md:521-530`)。しかし、これらはservo target fieldのaddress、
layout、sequenceを証明しない。

## 8. Degree-to-internal conversion

### 8.1 Application conversion

次は`CRobotPose.SetPose()`へ渡す値について
**CONFIRMED (source-level, not runtime confirmed)**である。`d`はJSON `getInt()`で取得した
整数degree、`clamp()`はinclusive rangeへのsaturationである。

| Axis / ID | Accepted application range | `Short` value passed to `CRobotPose` | Source |
| --- | ---: | --- | --- |
| `BODY_Y` / 1 | -61..61 | `(short)(clamp(d,-61,61) * 10 * 2.429)` | `ServoConverter_Sota.java:10,15,32-35` |
| `L_SHOU` / 2 | -180..60 | `(short)(clamp(d,-180,60) * 10)` | `ServoConverter_Sota.java:16,37-40` |
| `L_ELBO` / 3 | -90..65 | `(short)(clamp(d,-90,65) * 10)` | `ServoConverter_Sota.java:17,42-45` |
| `R_SHOU` / 4 | -60..180 | `(short)(clamp(d,-60,180) * 10)` | `ServoConverter_Sota.java:18,47-50` |
| `R_ELBO` / 5 | -65..90 | `(short)(clamp(d,-65,90) * 10)` | `ServoConverter_Sota.java:19,52-55` |
| `HEAD_Y` / 6 | -85..85 | `(short)(clamp(d,-85,85) * 10 * 1.75)` | `ServoConverter_Sota.java:11,20,57-60` |
| `HEAD_P` / 7 | -27..5 | `(short)(clamp(d,-27,5) * 10)` | `ServoConverter_Sota.java:21,62-65` |
| `HEAD_R` / 8 | -30..30 | `(short)(clamp(d,-30,30) * 10 * 1.75)` | `ServoConverter_Sota.java:12,22,67-70` |

Ratioを含む式は`double`演算後にJava narrowing conversionで`short`へcastされるため、
fractional partはzero方向へ切り捨てられる。converter内にrounding、zero offset、
explicit sign inversionはない。ratioを含まない式は整数の10倍である。range saturation後の
値は`short`範囲内に収まる。

`JSONObject.getInt()`自体の実装sourceはrepositoryにないため、JSON libraryが受理する
入力型や変換規則までは本調査で確定しない。また上表のrange commentがphysical safe range、
mechanical limitまたはvendor-approved limitであることは確認されていない。

### 8.2 Vendor SDK and VSMD conversion

`CRobotPose.SetPose()`または`CRobotMotion.play()`が上表の`Short`をさらに変換するか、
offset、sign、gear ratio、saturationを追加するかは**UNVERIFIED**である。よって
VSMDへ書き込まれる最終`internal_value`の式は確定しない。

## 9. Enable and interpolation sequence

### 9.1 Visible initialization

`PoseExecutorThread.run()`はqueue loop前に`RobotSys.initialize()`を呼ぶ
(`PoseExecutorThread.java:19-23`)。Sota初期化のvisible sequenceは次のとおりであり、
**CONFIRMED (source-level, not runtime confirmed)**である。

1. `new CRobotMem()` (`RobotSys.java:21-23`)
2. `new CSotaMotion(mem)` (`RobotSys.java:103-104`)
3. `mem.Connect()` (`RobotSys.java:105`)
4. `motion.InitRobot_Sota()` (`RobotSys.java:106`)
5. `motion.ServoOn()` (`RobotSys.java:107`)
6. initial pose／torque／LEDを`CRobotPose`へ設定 (`RobotSys.java:108-119`)
7. `motion.play(pose, 1500)` (`RobotSys.java:120`)
8. `CRobotUtil.wait(1500)` (`RobotSys.java:121`)

これはautomatic pose initializationとtorque設定を含む危険なlegacy behaviorである。
Python版で互換動作として無条件に再現してはならない。

### 9.2 Per-command sequence boundary

Visible per-Pose sequenceは`SetPose()`から`motion.play(pose,msec)`までだけである。
target writeだけで動作するか、`ServoEN`／`ServoSendEN`が必要か、interpolation timer／slot、
AppManager command、field write順、polling、completion、busy、timeoutはvendor SDK sourceと
active selection／field semanticsが不明なためすべて**UNVERIFIED**である。

`PoseExecutorThread`自身は`motion.play()`後にwait／pollを行わない。これがblocking APIか
asynchronous APIかもrepository sourceだけでは確認できない。Motion側の`Thread.sleep(msec)`は
次のPoseのqueueing間隔であり、VSMD completion判定の根拠ではない。

## 10. Stop and cancel semantics

次は**CONFIRMED (source-level, not runtime confirmed)**である。

* `stop_pose`はvendor stop APIを呼ばない。`AxisReader.read()`で現在値を読み、`Msec=100`の
  新しいPoseとして共有queueへ追加する (`PosePlayer.java:37-45`)。
* `stop_pose`は既存queueをclearせず、実行中commandをcancelせず、stale Poseへgeneration IDを
  与えない。このためstop Poseの後に以前のqueued Poseが実行され得る。
* `stop_motion`は保存された`Future`へ`cancel(true)`するだけである
  (`MotionPlayer.java:35-36`)。開始前は`future == null`になり得る。
* `MotionExecutorThread`はsleep中の`InterruptedException`を空のcatchで握りつぶして終了する
  (`MotionExecutorThread.java:15-22`)。既にPose queueへ入ったentryは削除しない。
* `PoseExecutorThread`はinterrupt時にstack traceを出してworker loop全体を終了し、queueを
  cleanupしない (`PoseExecutorThread.java:21-38`)。
* 元位置への復帰、rollback、queue flush、torque off、explicit interpolation stopは見えない。

Vendor `motion.play()`内部のcancel／stop、AppManager lease release、stale target処理は
source不足のため**UNVERIFIED**である。

## 11. Exception and disconnect behavior

次は**CONFIRMED (source-level, not runtime confirmed)**である。

* TCP workerは`IOException`だけをcatchしてstack traceを出す。finallyでclient socketをcloseする
  (`TCPServer.java:49-87`)。
* JSON parse、conversion、null lookup等のunchecked exceptionはTCP workerでcatchされない。
* payloadを`PosePlayer`／`MotionPlayer`へ渡した後のsocket closeまたはclient disconnectは、
  queue／executorへ渡したcommandをcancelしない。
* `PoseExecutorThread`は`InterruptedException`以外をcatchしないため、conversionまたはvendor APIの
  unchecked exceptionで唯一のPose workerが終了し得る。
* repository Java sourceには`CRobotMem`／VSMD connection close、server shutdown、executor shutdown、
  retry、timeout、safe return、exception rollbackが見えない。

Network write outcome、vendor timeout、SDK connection cleanupは**UNVERIFIED**である。無期限待機の
有無もSDK sourceなしでは判断できない。

## 12. AppManager and process coordination

`RobotSys`にはSota ID 1～8を`motion.LockServoHandle()`／`UnLockServoHandle()`へ渡すmethodがある
(`RobotSys.java:27-37,46-56`)。しかしrepository-wide call searchではこれらのwrapperを呼ぶ箇所が
ない。lockの実体、AppManager command、lease／slot、保護資源、別processとの競合処理は
vendor SDK sourceがないため**UNVERIFIED**である。

既存の確定済み方針ではAppManager `INTERP_LOCK`はinterpolation timer lease／slotであり、
whole-Sota cross-process mutexではない (`AGENTS.md` 4.6)。Python production write pathは
`FcntlProcessLock`をhardware/backend/server/AppManager/VSMD transport生成前にnonblockingで取得し、
競合時にfail-closedする必要がある。default pathと`LOCK_EX | LOCK_NB`実装境界は
`python_server/src/robot_controller/posix_process_lock.py:22,57-82`にある。

今回このcoordinationは実装していない。将来のcomposition rootでは、最初のSota write-capable
objectを生成する前、すなわちlegacy `new CRobotMem()`相当より前にwhole-Sota lockを取得すべきである。

## 13. Confirmed findings

すべて、特記しない限り**source-level confirmed / not runtime confirmed**である。

* TCP `play_pose`／`play_motion`から`RobotSys.motion.play()`までのcall chain。
* 単一軸と複数軸が同じmap／Pose／motion API pathを通ること。
* Sota axis nameからservo ID 1～8へのapplication mapping。
* `CRobotPose`へ渡す前のclamp、10倍、3軸のgear ratio、Java castによるzero方向切捨て。
* startup pathが`InitRobot_Sota()`、`ServoOn()`、initial pose／torque／LED、1500 ms playを行うこと。
* legacy stopがqueue clear／generation cancellationを実装していないこと。
* disconnectが既にdispatchしたmotionをcancelしないこと。
* generic VSMD write wireとPython typed-memory helperの存在。ただしservo target mappingではない。
* configuration-level confirmed事項として、repositoryの`System.properties:4`は`ROBOT_TYPE=Sota`。
* 既存evidenceで`ServoReadPos` index 1～8とphysical axis/sign correlationはruntime confirmedだが、
  target writeまたはdegree accuracyはruntime confirmedではない。
* **OPERATOR-CONFIRMED OPERATIONAL SELECTION:** current distributionは
  `/home/root/RobotController_bin`で、`RobotController_bin_private`はinactive historical copy。
* **PACKAGE-CONFIRMED LOAD TARGET:** manifest `Class-Path`がdistribution内`sotalib.jar`を直接参照。
* **CONFIRMED binary provenance:** distribution内と`/home/vstone/lib`の`sotalib.jar`は記録済み
  SHA-256が一致し、調査時点でbyte-for-byte identical。これはprocess-level runtime confirmation
  ではない。
* **CONFIRMED deployed memdef candidate identity:** top-level `memdef.conf`とSota Normal variantは
  記録済みSHA-256および`cmp -s`が一致し、調査時点でbyte-for-byte identical。
* **CONFIGURATION-LEVEL CONFIRMED:** top-level fileは`Model: Sota_Normal`、`ServoBusNum: 8`、8個の
  `ServoSettings`を含む。`ServoEN`等のvendor SDK semanticsは確認していない。
* **CONFIRMED field-name absence within this file:** top-level本文には明示的な`ServoReadPos`、
  servo target／target address、`Interp` field名を確認できなかった。

## 14. Inferred findings

* **INFERRED:** direct Poseが短時間に複数投入された場合、唯一のPose workerが共有queue順に
  `motion.play()`を呼ぶ。ただしvendor APIのblocking性が不明なためphysical serializationは未確認。
* **INFERRED:** `stop_pose`後に古いqueued commandが再開する可能性がある。queueをclearせずstop Poseを
  tailへ追加するsource構造に基づくが、具体的runtime interleavingは未確認。
* **INFERRED:** Java serverは別processとのwhole-Sota exclusionを保証しない。見えるsourceに
  process lock取得がなくhandle-lock wrapperも未使用だが、vendor SDK内部動作は不明。

## 15. Unverified items

* top-level `memdef.conf`をactiveとして選択するmechanism、load path、load timing、variant priority
* `sotalib.jar`または`SotaAppManager.jar`がtop-level fileを実際に読み込むこと
* `ServoEN`、`ServoSendEN`、`readAngleBank`、`max`、`min`、`offset`のvendor SDK内部意味論
* vendor SDK source availability、semantic version、license、redistribution／decompilation可否
* servo target field名、base address、element offset、length、signedness、byte order
* servo IDとtarget array indexの対応
* whole-array／individual write、read-modify-writeの有無
* `CRobotPose.SetPose()`以降の追加変換、offset、sign、range処理
* `ServoEN`、`ServoSendEN`、target、trigger、timerのwrite順
* target writeだけでmotionが始まるか
* AppManager interpolation lease／slotの取得・release sequence
* `CRobotMotion.play()`のblocking性、completion／busy／timeout判定
* exception、timeout、disconnect時のvendor cleanupとwrite outcome
* interpolation stop、rollback、safe return、torque state
* stop後のVSMD stale target behavior
* `ServoReadPos`がactual／target／encoderのどれを表すか
* absolute physical degree accuracy、mechanical zero、zero offset、safe motion range

## 16. Risks

* startupだけで`ServoOn()`、torque 100、initial pose、LED設定を行うlegacy pathがある。
* TCP serverとinitialization workerは並行起動し、明示的なready gateがない。
* stopはhold-like Poseをqueueへ追加するだけで、古いqueueを破棄しない。
* motion cancelは既にqueueへ移されたPoseを回収しない。
* workerのunchecked exceptionでPose処理が永続的に停止し得る。
* JSONとcommand decodingがplatform default charsetへ依存する。
* timeout、queue bound、connection bound、generation ID、rollbackがJava sourceにない。
* vendor source／active memdefなしにread addressをtarget addressと誤認すると、未知memoryへのwriteになる。

これらはPython版で再現すべき互換挙動ではなく、安全設計上のriskとして扱う。

## 17. Preconditions still missing before live write

少なくとも次が不足する。

1. 確認済みSHA-256のvendor JARに対してlicense上許可されるstatic inspection範囲、または同一binaryに
   対応する`jp.vstone.RobotLib` source。
2. 確認済みdeployed memdef candidateからactive file／resourceを選ぶ規則と対象runtimeとの対応証跡。
3. servo target address／型／index／write granularityの一意なsource根拠。
4. degreeから最終memory valueまでの全変換とphysical degree accuracyの確認。
5. enable、interpolation、completion、busy、timeout、stop、cancel、releaseの完全なsequence。
6. operator-approved safe range、mechanical zero／offset、支持・緊急停止・safe return手順。
7. whole-Sota process lockを含むPython production composition root設計とreview。
8. timeout／disconnect／partial-write outcome unknown時のfail-safe方針。

## 18. Recommended next phase

次工程もlive writeではなく、missing-source acquisition and provenance verificationとする。

* Vendor SDK binary identityは確認済みとし、次にsource availability、semantic version、license、
  redistribution／decompilation可否を人間が確認する。
* Deployed Sota Normal memdef candidate identityは確認済みとし、次にactive selection mechanism、load
  path／timing、variant priorityを実機通信を伴わないreview可能な資料から確認する。
* sourceが提供される場合は`CRobotPose.SetPose()`、`CRobotMotion.play()`、`CSotaMotion`、
  memory accessor、AppManager wrapperを順に再調査する。
* JARだけの場合は、licenseとrepository規約が逆コンパイルを明確に許容すると確認されてから、
  別途reviewされたstatic-only工程として扱う。
* servo target address、最終変換、write sequenceが一意になるまでmigration planを完了更新しない。

## 19. Explicit prohibition on live write

**本調査はsingle-axis live writeへ進む根拠を提供しない。servo target address、最終変換、
enable／interpolation／stop／rollbackが未確認であるため、single-axis live write、torque変更、
automatic pose initialization、servo commandの実施およびそのためのcode実装を引き続き禁止する。**
