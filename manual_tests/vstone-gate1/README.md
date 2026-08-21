# VSTONE Gate 1 guarded manual probe

## Status

```text
Probe preparation: READY FOR HUMAN SOURCE REVIEW OF LED-LOCK LIMITED REVISION
Manual execution: HUMAN-ONLY
Gate 1A-0: PASS OBSERVED ONCE (default servo IDs=8; guard acquired)
Option 3 diagnostic: OBSERVED (servo=null, torque=null, LED populated after setLED_Sota)
Gate 1A-1 servo safety: PASS / OBSERVED NO MOVEMENT IN ONE RUN
Gate 1A-1 play return: true; visible mouth/eyes/power response: NO CHANGE
Gate 1A mouth control: NOT CONFIRMED; Gate 1A overall: NOT PASSED
Gate 1B disable/enable calls: RETURNED NORMALLY
Gate 1B play after disable: true; visible mouth/eyes/power response: NO CHANGE
Gate 1B: DIAGNOSTIC OBSERVATION ONLY; visible LED control NOT CONFIRMED
Gate 1L LED ownership/lock: UNKNOWN / OPTIONS 10-12 NOT EXECUTED
Options 5 and 9: BLOCKED
Production adapter: BLOCKED UNTIL GATE 1 PASS
Codex vendor-JAR compile: NOT PERFORMED
```

このdirectoryはproduction sourceでも自動testでもない。通常の`java_server` Maven reactorからcompile／executeされず、CIまたはCodexを含む自動エージェントから実行してはならない。実機での使用にはrobot管理者、operator、安全監視者によるsource reviewと明示的opt-inが必要である。

## Purpose and residual risk

`CRobotPose.setLED_Sota(...)`で作成したposeを`CRobotMotion.play(...)`したとき、servoへ絶対に影響しないというvendor guaranteeは確認できていない。option 3のmanual diagnosticでは、`new CRobotPose()`直後のservo／torque／LED mapはいずれも`null`、`setLED_Sota(...)`後もservo／torque mapは`null`のまま、LED mapだけがsize 10へ変化した。従来の「mapはnon-nullかつempty」というstructural invariantを撤回し、servo／torque mapの`null OR empty`をcommand dataなしとして扱う。

1. option 1で従来どおりinitialize/connectし、option 2で全default servo guardを取得する。
2. option 3で`new CRobotPose()`直後の`getPose()`、`getTorque()`、`getLed()`をcopyしてsizeとentryを表示する。
3. local Java objectにだけ`setLED_Sota(...)`を適用し、同じ3 mapを再度copyして表示する。
4. before/afterの等価性、added keys、removed keys、changed valuesをsoftware-sideで計算する。map iteration orderはsemanticとして扱わない。
5. option 3は`CRobotMotion.play()`、servo power、pose write、torque write、voice-sync writeを呼ばない。
6. option 4を、全servo guard、diagnostic完了、one-shot state、play直前のnull-or-empty invariantを満たす場合に限って有効にする。
7. option 4のservo safetyがPASSした場合だけoption 6～8をnative mouth voice-syncの限定切り分けとして使用する。Gate 1Bではdisable単独でもvisible changeがなかったため、option 10～12だけをderived LED-ID lockの比較として追加する。option 5と9はdispatcherでblockする。

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
* servo動作を意図した試験ではなく、このrevisionではoption 1、2、3、4、6、7、10、11、12、8だけを順に行う。

## Current guarded workflow: 1, 2, 3, 4, 6, 7, 10, 11, 12, 8, STOP

このrevisionで推奨する順序は **1 → 2 → 3 → 4 → 6 → 7 → 10 → 11 → 12 → 8 → c → STOP** だけである。LED-lock比較中はoption 7直後にoption 8を実行せず、voice-sync restore pendingのまま10→11→12へ進む。option 5（brightness sequence）とoption 9（rate test）はblockされ、write pathへ進まない。option 4、7、11、cleanup zeroは同じsingle source callの3引数`play(...)` helperを使う。4引数版は使用しない。

1. 起動直後にhardware writeが行われていないことをconsoleで確認する。
2. option 1を選び、physical preflightを再確認して`READY`を入力する。
3. `Connect()`と`InitRobot_Sota()`のreturn、exception、予期しないphysical state changeを記録する。変化があれば中止する。
4. option 2を選ぶ。`getDefaultIDs()`がnon-null／non-empty／全要素non-nullであることをprobeが確認し、全IDのservo guardを取得する。lockがfalseならLED writeなしでABORTする。
5. option 3を選び、`BEFORE setLED_Sota`と`AFTER setLED_Sota`のservo／torque／LED mapのsize、全entry、等価性、added／removed／changedを再確認する。servo／torque mapの`null OR empty`をcommand dataなしとして扱う。
6. `NO play() was called.`とoption 3完了表示を確認する。`setLED_Sota()`はlocal `CRobotPose` objectを変更するためだけに使われ、diagnostic中に`CRobotMotion.play()`は呼ばれない。
7. option 4を選び、servo guard、default servo count、異なるkey、servo／torque mapの`NULL`または`EMPTY`、LED map size、configured `LOW`を確認する。
8. ENTERでexactly one low `play(...)`を実行する。`q`はplay前にABORTする。falseまたはexception時にretryしない。
9. 最優先でservo movement、次にunexpected servo soundへ明示的にyes/noで回答する。いずれかがYESならGate 1A-1 FAILとして、cleanup mouth-zeroを含む追加`play()`を禁止する。
10. mouthのvisible changeへyes/noで回答し、eyesとpower LEDはfree textで記録する。servo safetyとmouth responseを別々に表示し、Gate 1A全体をPASSにしない。
11. option 6を選ぶ。warningを読み、ENTERで`disabeMouthLEDVoiceSync()`を一回だけ要求する。option 6は`play()`、LED lock、direct LED-ID writeを行わない。current-state getterがないため実状態はUNKNOWNである。
12. option 7を選び、disable attempt／normal return／restore pendingをpre-play表示で確認する。ENTERでoption 4と同じLOW条件の`play(...)`を一回だけ行い、servo movement、sound、mouth、eyes、powerを記録する。**ここでoption 8を実行しない。**
13. option 10を選ぶ。fresh `setLED_Sota()` poseの`getLed().keySet()`からLED ID集合を導出・検証し、表示されたIDとkeyを確認してENTERする。option 10は`LockLEDHandle(VSTONE_GATE1_LED_TEST, derivedIds)`だけを一回呼び、`play()`しない。falseならfail-closedで終了し、retryしない。
14. option 11を選ぶ。fresh LOW poseのLED ID集合とlocked集合が順序非依存で一致すること、servo／torque mapがnull-or-emptyであること、LED lock keyとplay keyが一致することを確認する。ENTERで3引数`play(...)`をexactly one回実行し、servo movement、sound、mouth、eyes、powerを明示的yes/noで記録する。
15. option 12を選び、option 10で実際に取得したkeyとID cloneを使って`UnLockLEDHandle(...)`を一回要求する。
16. option 8を選び、`enabeMouthLEDVoiceSync()`を一回だけ要求する。normal return後だけrestore-pendingをclearする。これは元状態復元の証明ではない。
17. `c`または`q`でcleanupし、必要なmouth-zero、LED-lock release fallback、configured voice-sync enable fallback、servo guard release、disconnect、exception、physical stateを記録してSTOPする。

観測済みoption 3出力の要約:

```text
BEFORE setLED_Sota
Servo map size: -1 / <null>
Torque map size: -1 / <null>
LED map size: -1 / <null>

AFTER setLED_Sota
Servo map size: -1 / <null>
Torque map size: -1 / <null>
LED map size: 10

Servo map equal before/after: YES
Torque map equal before/after: YES
LED map equal before/after: NO

NO play() was called.
LED observed entry for configured LOW=64: id=14, value=64
```

上記ID 14はtested runtimeで得られたmap entryの**OBSERVED**値であり、Sota mouth LEDの公式public ID specificationではない。

## Later guarded gates

Gate 1A-1では`play()` true、servo movement／unexpected soundなし、mouth／eyes／power visible changeなしを観測した。Gate 1Bでもdisable callはnormal returnし、同じLOW `play()`はtrue、servo movement／soundなし、mouth／eyes／power visible changeなし、その後のenable callもnormal returnした。したがってnative voice-sync disable単独ではmanual `setLED_Sota` updateをvisibleにできず、voice-syncだけが原因という仮説は支持されなかった。次はderived full LED ID setをplay keyと同じkeyでlockする一変数だけをoption 10～12で比較する。LED ownership結果はまだ **UNKNOWN**、Gate 1A全体はNOT PASSED、option 5と9はblockしたままである。

## Cleanup

normal quit、operator abort、exceptionの`finally`から次をbest effortで行う。

1. LED playを試みていた場合だけ、guarded LED-only poseで`Cleanup mouth zero — not part of LED-lock diagnostic measurement`を一回試みる。LED lock保持中ならlocked ID setとの一致を再確認し、unlock前に同じplay keyで行う。ただしmovementまたはunexpected sound後は追加`play`を行わない。
2. probeがLED lockを保持している場合、option 10で保存したkeyとID cloneでreleaseを試みる。normal release後はstateをclearし、cleanupで二重unlockしない。
3. probeがvoice-sync disableを試み、configured enableが未完了の場合だけenableを試みる。
4. probeが取得したall-default-servo guardだけを同じkeyとID集合でreleaseする。
5. 接続している場合だけ`Disconnect()`を試みる。
6. secondary exceptionをconsoleへ記録し、physical stateを人間が確認する。

cleanupでもservo pose、torque、power stateを変更するAPIは呼ばない。process crash、JVM abort、電源断でJava cleanupが走るとは保証しない。異常終了試験はこのrunbookの承認範囲外である。

二回以上のmanual runで、probe cleanupがservo guardをreleaseし`Disconnect()`した後、VSTONE library shutdown hookが`CRobotMotion.ServoOff(...)`を試み、disconnected socketへのwrite failure／`NullPointerException`／`Cmd Send Error`が発生した。probe sourceは`ServoOn()`／`ServoOff()`を明示的に呼んでいない。これはServoOffが実機へ成功した証拠ではなく、vendor runtimeのshutdown時write attemptとして分離して記録する。cleanup順序は変更せず、probeへServoOn／ServoOff、reflection、private APIを追加しない。

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

Gate: 1A-0 / option 3 / Gate 1A-1 / Gate 1B / Gate 1L / cleanup
Servo guard acquired:
Default servo ID count:
Before servo / torque / LED maps:
After servo / torque / LED maps:
Map equality / added / removed / changed:

setLED_Sota local mutation requested:
Option 3 play() called: NO
Gate 1A-1 play() attempted:
Gate 1A-1 play() return:
Gate 1A-1 servo movement: YES / NO
Gate 1A-1 unexpected servo sound: YES / NO
Gate 1A-1 mouth visibly changed: YES / NO
Gate 1A-1 either eye visibly changed: YES / NO
Gate 1A-1 power visibly changed: YES / NO
Gate 1A-1 servo safety result:
Gate 1A overall result:

Voice-sync disable attempted / returned normally:
Gate 1B manual play() attempted / returned:
Gate 1B servo movement: YES / NO
Gate 1B unexpected servo sound: YES / NO
Gate 1B mouth visibly changed: YES / NO
Gate 1B either eye visibly changed: YES / NO
Gate 1B power visibly changed: YES / NO
Configured enable attempted / returned normally:
Original voice-sync state restored: UNKNOWN

Derived LED IDs:
LockLEDHandle attempted / returned:
Locked LED IDs:
Gate 1L current pose LED IDs:
LED ID sets equal:
Gate 1L play() attempted / returned:
Gate 1L servo movement / unexpected sound:
Gate 1L mouth / eyes / power visibly changed:
UnLockLEDHandle attempted / returned normally:
Exception:

Observed mouth:
Observed eyes:
Observed power LED:
Other observation:

Independent result / FAIL / ABORT:
```

観測していないphysical motion、torque、LED、audio状態を推測で補完しない。Gate 1A-0、option 3、Gate 1A-1、Gate 1Bの既存観測を保持する。Gate 1A-1とGate 1Bではservo movement／soundなしと`play()` trueを観測した一方、mouth／eyes／power visible changeはなかった。native voice-sync disable単独ではvisible controlを確認できず、Gate 1A全体は未確認である。Gate 1LはNOT EXECUTEDであり、そのevidence reviewが終わるまでproduction VSTONE adapterを実装しない。
