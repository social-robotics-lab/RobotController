# VSTONE Gate 1 guarded manual probe

## Status

```text
Probe preparation: READY FOR HUMAN SOURCE REVIEW
Manual execution: HUMAN-ONLY / NOT EXECUTED
Production adapter: BLOCKED UNTIL GATE 1 PASS
Vendor JAR compile: NOT COMPILED
```

このdirectoryはproduction sourceでも自動testでもない。通常の`java_server` Maven reactorからcompile／executeされず、CIまたはCodexを含む自動エージェントから実行してはならない。実機での使用にはrobot管理者、operator、安全監視者によるsource reviewと明示的opt-inが必要である。

## Purpose and residual risk

`CRobotPose.setLED_Sota(...)`で作成したLED-only poseを`CRobotMotion.play(...)`したとき、servoへ絶対に影響しないというvendor guaranteeは確認できていない。今回のprobeは、公式公開APIのkey付きservo lockを安全柵として次の多重防御を行う。

1. `CRobotPose`へservo targetまたはtorqueを設定しない。
2. LED設定の前後および各`play`直前に`getPose().isEmpty()`と`getTorque().isEmpty()`を確認する。
3. `getDefaultIDs()`で得た全servo IDを`VSTONE_GATE1_SERVO_GUARD`でlockする。
4. `play`には異なる`VSTONE_GATE1_LED_TEST` keyを渡す。
5. servo power、pose、torqueを変更するAPIをprobeから呼ばない。
6. 初回writeはoperatorが明示開始する1回だけとし、後続Gateはmanual PASS確認で段階的に解放する。
7. rate testは10／20／25 Hz、各2秒だけに限定する。

公式JavaDocはkey付きservo lockを「play時にキーが一致しない制御出来ない」と説明する。ただし、これはLED-only `play`の無副作用保証、`InitRobot_Sota()`の無副作用保証、lockのcross-process保証、実機安全性の証明ではない。guardの実挙動とphysical motionの有無は人間が観測する。

参照した公開資料:

* [CRobotPose JavaDoc](https://sota.vstone.co.jp/sota/javadoc/jp/vstone/RobotLib/CRobotPose.html)
* [CRobotMotion JavaDoc](https://sota.vstone.co.jp/sota/javadoc/jp/vstone/RobotLib/CRobotMotion.html)
* [CSotaMotion JavaDoc](https://sota.vstone.co.jp/sota/javadoc/jp/vstone/RobotLib/CSotaMotion.html)
* [CRobotMem JavaDoc](https://sota.vstone.co.jp/sota/javadoc/jp/vstone/RobotLib/CRobotMem.html)
* [Official MotionSample.java at `c80b4d88fb4cc7f006d5881616f95a07ac61e195`](https://github.com/vstoneofficial/SotaSample/blob/c80b4d88fb4cc7f006d5881616f95a07ac61e195/src/jp/vstone/sotasample/MotionSample.java)

Sota mouth LED ID `14`は撤回済みの仮定であり、このprobeは数値LED IDや`SetLed`を使用しない。

## Source boundary

[`src/VstoneGate1Probe.java`](src/VstoneGate1Probe.java)だけがmanual probe sourceである。vendor JARをrepositoryへ追加せず、production POMも変更しない。JARのdownload、探索、逆コンパイル、disassembly、`javap`によるimplementation解析、reflection、private API抽出を行わない。

probeは起動引数が不正な場合、VSTONE objectを構築する前に終了する。LED levelはsourceへ既定値として埋め込まず、installed official runtimeに対して人間がreviewした`ZERO LOW MEDIUM HIGH`の4値を起動時に明示する。probeのguarded candidate domainは0..255かつstrictly increasingであるが、このvalidation自体をinstalled runtimeの仕様根拠にしてはならない。

eyesとpower LEDは、現在値を取得できると仮定せず、operatorが事前承認したknown test state `Color.BLACK`へ変更する。transitionは公式sampleの使用例と同じ1000 msを明示的に使用する。この値をservo安全性の根拠にはしない。

## Human compile procedure

前提として、operatorは公式配布元、version、Edison image対応、license、SHA-256を記録したVSTONE JARだけを用いる。以下のplaceholderを実pathへ置換する。repositoryへJARをcopyしない。

```sh
cd manual_tests/vstone-gate1
mkdir -p out
javac -encoding UTF-8 -source 8 -target 8 \
  -cp "<PATH_TO_OFFICIAL_VSTONE_JARS>/*" \
  -d out src/VstoneGate1Probe.java
```

compile後の実行例は、施設reviewで承認された値へplaceholderを置換する。

```sh
java -cp "out:<PATH_TO_OFFICIAL_VSTONE_JARS>/*" \
  VstoneGate1Probe <ZERO> <LOW> <MEDIUM> <HIGH>
```

Windows上でcompileだけを行う場合はclasspath separatorを`;`にする。compile成功は実機安全性を証明しない。CodexはJARを提供されていないためcompileしていない。

## Physical preflight

実行前にすべてを確認し、evidenceへ記録する。

* robotが安定した場所にあり、転倒・落下しない。
* 可動部周囲に障害物がなく、人の指や物が関節部にない。
* operatorと安全監視者が即座に試験または電源を停止できる。
* current RobotController、automatic motion application、その他のrobot processが動いていない。
* process競合をservice停止、process kill、lock file削除で回避しない。
* `vsmd_edison`、robot設定、device fileを変更しない。
* installed JARと公開JavaDocのversion対応、公式provenance、SHA-256、licenseを記録する。
* 4つのmouth levelと`Color.BLACK`のtest stateをoperatorが事前承認する。
* servo動作を意図した試験ではなく、最初はGate 1A-0と1A-1だけを行う。

## First execution: Gate 1A-0 and 1A-1 only

初回sessionではmenu option 1～4以外を実行しない。

1. 起動直後にhardware writeが行われていないことをconsoleで確認する。
2. option 1を選び、physical preflightを再確認して`READY`を入力する。
3. `Connect()`と`InitRobot_Sota()`のreturn、exception、予期しないphysical state changeを記録する。変化があれば中止する。
4. option 2を選ぶ。`getDefaultIDs()`がnon-null／non-empty／全要素non-nullであることをprobeが確認し、全IDのservo guardを取得する。lockがfalseならLED writeなしでABORTする。
5. option 3を選び、servo map 0、torque map 0、LED map non-zeroを確認する。このstepは`play`しない。
6. option 4を選ぶ。表示されるguard、異なるkey、各map size、operator監視警告を確認する。
7. ENTERでlow LED updateを1回だけ実行する。`play` return、mouth／eyes／power LED、音、exceptionを記録する。
8. 人間がservo movementの有無を回答する。少しでもmovementがあればFAILとして以降を実行しない。
9. `c`または`q`でcleanupし、mouth zero attempt、servo guard release、disconnectとphysical stateを確認する。

## Later guarded gates

Gate 1A-1を人間がPASSとした後だけ、option 5は`ZERO → LOW → MEDIUM → HIGH → ZERO`を各ENTER入力で一stepずつ実行する。各stepで新しいposeとstructural checkを使い、servo movementがあれば即ABORTする。

Gate 1A全体を人間がPASSとした後だけ、option 6で`disabeMouthLEDVoiceSync()`を一回試みる。option 7でdisable要求中のmanual LED updateを一回行い、native側の上書きを人間が観測する。option 8で`enabeMouthLEDVoiceSync()`を試みる。current-state getterがないため、これはconfigured enable attemptであり、未知の元状態を復元したとは表現しない。

Gate 1Aと1Bを人間がPASSとした後だけ、option 9で10、20、25 Hzのいずれか一つを選べる。各sessionは2秒、最大20／40／50 updatesで停止し、requested target rate／requested updates／successful／failed／elapsedを表示する。これはJava側のrequested timingであり、hardwareが同じrateで反映したという保証ではない。`Thread.sleep()`の精度、vendor側latency、queueing、visible lag／jitterは人間が観測・記録する。50 Hzや無限loopは実装していない。終了時はmouth zeroを試みる。各rateは別sessionとして人間が開始・観測する。

## Cleanup

normal quit、operator abort、exceptionの`finally`から次をbest effortで行う。

1. LED playを試みていた場合だけ、guarded LED-only poseでmouth zeroを試みる。ただし人間がservo movementを報告した後はhard stopを優先し、追加の`play`を行わない。
2. probeがvoice-sync disableを試み、configured enableが未完了の場合だけenableを試みる。
3. probeが取得したall-default-servo guardだけを同じkeyとID集合でreleaseする。
4. 接続している場合だけ`Disconnect()`を試みる。
5. secondary exceptionをconsoleへ記録し、physical stateを人間が確認する。

cleanupでもservo pose、torque、power stateを変更するAPIは呼ばない。process crash、JVM abort、電源断でJava cleanupが走るとは保証しない。異常終了試験はこのrunbookの承認範囲外である。

## Evidence template

```text
Date:
Operator / safety observer:
Robot / asset ID:
Java:
VSTONE runtime / Edison image:
sotalib.jar path:
sotalib.jar version / source / license:
sotalib.jar SHA-256:
Probe source revision / SHA-256:

Gate: 1A-0 / 1A-1 / 1A-2 / 1B / 1C / cleanup
Servo guard acquired:
Default servo ID count:
Servo map empty:
Torque map empty:
Play key differs from servo guard key:

Requested LED state:
play() return:
Exception:

Observed mouth:
Observed eyes:
Observed power LED:
Observed servo movement: YES / NO
Other observation:

PASS / FAIL / ABORT:
```

観測していないphysical motion、torque、LED、audio状態を推測で補完しない。manual Gate 1のPASS／FAILはまだ未確定であり、PASS evidenceのreviewが終わるまでproduction VSTONE adapterを実装しない。
