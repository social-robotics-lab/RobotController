# VSTONE公開Java API capability matrix

## 1. 目的と調査境界

本書は、Java版RobotControllerのVSTONE adapter設計に必要な公開API capabilityを、2026-08-08時点の公式JavaDoc、公式sample、公式support情報、repository内の現行interface、および2026-08-18にユーザーから提示されたmanual run logと照合したevidenceである。Sotaを優先し、CommUとDogは差分だけを記録する。

本調査では実機、device、AppManager、VSMD、audio outputを操作していない。`sotalib.jar`のdownload、逆コンパイル、disassembly、`javap`、strings抽出、reflection、private member調査も行っていない。公開APIの存在は、対象Edisonに配置されたJARでの存在や実機semanticsを保証しない。

判定語は次の意味で使用する。

* **CONFIRMED**: 指定した公式公開資料でclass、method、signature、定数、またはsample使用法を確認した。
* **OBSERVED**: ユーザー提供のmanual run logで特定の実行結果を観測した。公式仕様や別環境での一般的semanticsは保証しない。
* **INFERRED**: 複数の公開APIから実装可能性を推定できるが、公式資料が目的のsemanticsを直接保証していない。
* **UNKNOWN**: 公開資料で必要な情報を確認できず、推測による実装を禁止する。

## 2. 参照baseline

| 種別 | 参照 | 固定情報 | 確認日 |
|---|---|---|---|
| 公式JavaDoc | [CRobotMotion](https://sota.vstone.co.jp/sota/javadoc/jp/vstone/RobotLib/CRobotMotion.html)、[CRobotPose](https://sota.vstone.co.jp/sota/javadoc/jp/vstone/RobotLib/CRobotPose.html)、[CSotaMotion](https://sota.vstone.co.jp/sota/javadoc/jp/vstone/RobotLib/CSotaMotion.html)、[CCommUMotion](https://sota.vstone.co.jp/sota/javadoc/jp/vstone/RobotLib/CCommUMotion.html)、[CRobotMem](https://sota.vstone.co.jp/sota/javadoc/jp/vstone/RobotLib/CRobotMem.html)、[CWavePlayer](https://sota.vstone.co.jp/sota/javadoc/jp/vstone/RobotLib/CWavePlayer.html)、[constant values](https://sota.vstone.co.jp/sota/javadoc/constant-values.html) | Web公開版。JAR versionとの対応は未表示 | 2026-08-08 |
| 公式sample | [vstoneofficial/SotaSample](https://github.com/vstoneofficial/SotaSample)、[MotionSample.java](https://github.com/vstoneofficial/SotaSample/blob/c80b4d88fb4cc7f006d5881616f95a07ac61e195/src/jp/vstone/sotasample/MotionSample.java) | `master` = `c80b4d88fb4cc7f006d5881616f95a07ac61e195` | 2026-08-08 |
| 公式support | [口LED制御に関する2019年回答](https://sota.vstone.co.jp/sota/forum/detail.php?forum_cd=111)、[sotalib.jarの対象環境に関する2023年回答](https://sota.vstone.co.jp/sota/forum/detail.php?forum_cd=211)、[Edison上のJava 8に関する回答](https://sota.vstone.co.jp/sota/forum/detail.php?forum_cd=178) | 回答時点の情報であり、現行JavaDocとの差はversion差の可能性がある | 2026-08-08 |
| Java SE 8 | [SourceDataLine](https://docs.oracle.com/javase/8/docs/api/javax/sound/sampled/SourceDataLine.html)、[DataLine](https://docs.oracle.com/javase/8/docs/api/javax/sound/sampled/DataLine.html) | Java 8 public API | 2026-08-08 |
| 安全情報 | [Sota使用上の注意](https://www.vstone.co.jp/sotamanual/index.php?cmd=read&page=%E4%BD%BF%E7%94%A8%E4%B8%8A%E3%81%AE%E6%B3%A8%E6%84%8F&word=%E5%86%8D%E8%B5%B7%E5%8B%95) | 公式manual | 2026-08-08 |

公式sampleは参照したが、sourceを新実装へcopyしていない。repository内のlegacy Java実装は互換性と過去の利用例の比較対象に限定し、公開API確認の根拠にはしていない。

### 2.1 Canonical capability ledger

次表はproduction設計判断へ入力できる公開capabilityのcanonical indexである。詳細とstatusの根拠は後続節に記録する。

| Capability | Status | Public class | Public method | Signature | Official source / observed evidence | Legacy reference | Remaining uncertainty | Manual test |
|---|---|---|---|---|---|---|---|---|
| Manual Gate 1 readiness | **READY FOR HUMAN SOURCE REVIEW OF LIMITED LED-LOCK REVISION** | `CRobotPose`／`CRobotMotion`／`CSotaMotion` | `setLED_Sota`／key付きservo・LED lock／public map getters／3引数key付き`play`／native voice-sync disable・enable | 下記各API signature | 公式JavaDoc、固定commitのofficial `MotionSample.java`、ユーザー提供manual log | legacy使用例はservo非依存性の安全根拠にしない | LED lock acquisitionとlock保持中のvisible response | Gate 1A-0、option 3、Gate 1A-1、Gate 1Bは観測済み。Gate 1LはNOT EXECUTED。options 5・9はBLOCKED |
| `CRobotPose` constructor initial servo-map semantics | **OBSERVED NULL / UNDOCUMENTED** | `CRobotPose` | constructor／`getPose` | `new CRobotPose()`、`Map<Byte, Short> getPose()` | ユーザー提供option 3 log | N/A | 環境・version間の一貫性 | tested runtimeでbefore/afterともnull |
| `CRobotPose` constructor initial torque-map semantics | **OBSERVED NULL / UNDOCUMENTED** | `CRobotPose` | constructor／`getTorque` | `new CRobotPose()`、`Map<Byte, Short> getTorque()` | ユーザー提供option 3 log | N/A | 環境・version間の一貫性 | tested runtimeでbefore/afterともnull |
| `CRobotPose` constructor initial LED-map semantics | **OBSERVED NULL / UNDOCUMENTED** | `CRobotPose` | constructor／`getLed` | `new CRobotPose()`、`Map<Byte, Short> getLed()` | ユーザー提供option 3 log | N/A | 環境・version間の一貫性 | tested runtimeでbeforeはnull |
| `setLED_Sota` effect on servo map | **OBSERVED NO CHANGE** | `CRobotPose` | `setLED_Sota`／`getPose` | 上記 | ユーザー提供option 3 log | N/A | 他runtime/versionでの一貫性 | nullからnull、before/after equal |
| `setLED_Sota` effect on torque map | **OBSERVED NO CHANGE** | `CRobotPose` | `setLED_Sota`／`getTorque` | 上記 | ユーザー提供option 3 log | N/A | 他runtime/versionでの一貫性 | nullからnull、before/after equal |
| `setLED_Sota` effect on LED map | **OBSERVED POPULATED** | `CRobotPose` | `setLED_Sota`／`getLed` | 上記 | ユーザー提供option 3 log | N/A | exact ID semantics、他runtime/versionでの一貫性 | nullからsize 10、before/after not equal |
| Tested runtime LED map entry `id=14,value=64` | **OBSERVED ONLY** | `CRobotPose` | `setLED_Sota`／`getLed` | `LOW=64` | ユーザー提供option 3 log | historical codeもID 14を使用するが根拠にはしない | Sota公式public IDかはUNKNOWN | 公式ID specificationとして扱わない |
| Vendor shutdown hook may call `ServoOff` | **OBSERVED REPEATEDLY** | vendor runtime shutdown hook | `CRobotMotion.ServoOff` | stack trace上のcall | ユーザー提供manual run log（二回以上） | probe sourceに明示的callなし | exact trigger、ordering、physical effect、safe resolution | disconnect後にsocket write failure／NPE／Cmd Send Error。ServoOff成功とは判定しない |
| Sota mouth LED ID `14` | **WITHDRAWN ASSUMPTION** | N/A | N/A | N/A | `CSotaMotion` constantsとconstant valuesにSota mouth LED IDなし。ID 14は`CCommUMotion.SV_MOUTH` | legacy `LedConverter_Sota`とhistorical VSMD evidenceはID 14を使用 | Sota mouth-only public IDの有無 | IDを使う試験は禁止。VSTONE clarification待ち |
| Sota complete LED pose | **CONFIRMED**（API） | `CRobotPose` | `setLED_Sota` | `void setLED_Sota(Color eye_L, Color eye_R, int mouth, Color powerbtn)` | `CRobotPose` JavaDoc、official `MotionSample.java` | legacy Pose pathもfull LED valuesを構成 | brightness範囲、他LED保持、実機反映 | Gate 1A |
| LED pose commit candidate | **CONFIRMED**（API surface）／**OBSERVED ONCE** | `CRobotMotion` | `play` | `boolean play(CRobotPose pose, int msec, String LockKey)` | `CRobotMotion` JavaDoc、official sample、Gate 1A-1 manual log | legacy `PoseExecutorThread`が`play`を使用 | LED-only poseの一般的servo非依存保証、transition、return false semantics | LOW=64のguarded playを一回実行。return `true`、servo movementはOBSERVED NONE |
| Guarded LED-only play servo movement | **OBSERVED NONE IN ONE RUN** | `CRobotMotion` | `play` | 上記3引数版 | ユーザー提供Gate 1A-1 manual log | N/A | 他runtime、反復時、sound／torqueへの一般化 | Gate 1A-1 servo safety observationだけPASS。vendor guaranteeではない |
| Guarded LED-only play return | **OBSERVED TRUE IN ONE RUN** | `CRobotMotion` | `play` | 上記3引数版 | ユーザー提供Gate 1A-1 manual log | N/A | `true`のexact hardware semantics | visible mouth responseの証明にはしない |
| Visible mouth response without explicit native voice-sync disable | **OBSERVED NO CHANGE IN ONE RUN** | `CRobotPose`／`CRobotMotion` | `setLED_Sota`／`play` | LOW=64、1000 ms、key付きplay | ユーザー提供Gate 1A-1 manual log | N/A | overwrite、ownership、lock、commitのどれが原因か | mouth control NOT CONFIRMED。Gate 1A overall NOT PASSED |
| Visible LED response after explicit native voice-sync disable request | **OBSERVED NO CHANGE IN ONE RUN** | `CSotaMotion`／`CRobotMotion` | `disabeMouthLEDVoiceSync`／3引数`play` | option 6→7 limited sequence、LOW=64 | ユーザー提供Gate 1B manual log | N/A | LED ownership、commit、other owner interaction | disable/playともnormal/true、servo movement・soundなし、mouth/eyes/power changeなし |
| Native voice-sync-only hypothesis | **NOT SUPPORTED BY THIS OBSERVATION** | `CSotaMotion` | disable／enable | 両callがnormal return | ユーザー提供Gate 1B manual log | N/A | returnと実stateの関係、他owner | disable単独ではmanual updateをvisibleにしなかった。sole-cause断定はしない |
| LED ownership / no-change cause | **UNKNOWN** | `CRobotMotion` | `LockLEDHandle`／`UnLockLEDHandle` | derived full LED set、play keyと同じkey | Gate 1A-1／1Bはいずれもno visible change | low-level historical evidenceをproduction根拠にしない | lock acquisition、lock保持中response、commit、other owner | option 10～12でだけ切り分ける。direct ID 14 writeなし |
| Gate 1 all-servo guard | **CONFIRMED**（API surface）／**OBSERVED ONCE**（acquisition） | `CRobotMotion` | `getDefaultIDs`／`LockServoHandle`／`UnLockServoHandle` | `Byte[] getDefaultIDs()`、`boolean LockServoHandle(String, Byte[])`、`void UnLockServoHandle(String, Byte[])` | `CRobotMotion` JavaDocとユーザー提供manual log | legacy usageはguardの安全証明にしない | initialization副作用、全ID coverage、lock failure／crash／process semantics | default ID count 8、lock successを一度観測。一般化しない |
| Native voice-sync disable | **CONFIRMED**（API）／**RETURNED NORMALLY ONCE** | `CSotaMotion` | `disabeMouthLEDVoiceSync` | `void disabeMouthLEDVoiceSync()` | `CSotaMotion` JavaDoc、Gate 1B manual log | legacyは直接利用していない | actual state、idempotency、failure、他owner interaction | normal returnだけを記録。visible LED changeなし |
| Native voice-sync enable | **CONFIRMED**（API）／**RETURNED NORMALLY ONCE** | `CSotaMotion` | `enabeMouthLEDVoiceSync` | `void enabeMouthLEDVoiceSync()` | `CSotaMotion` JavaDoc、Gate 1B manual log | legacyは直接利用していない | restore semantics、元状態がdisabledの場合 | original state restoreの証明にはしない |
| Native voice-sync state query | **NOT AVAILABLE**（surveyed API） | `CSotaMotion` | none found | N/A | `CSotaMotion` JavaDoc method list | legacyにもreliable getterなし | installed version、vendor-approved query | Gate 1 preflight／vendor clarification |
| LED lock surface | **CONFIRMED**（API） | `CRobotMotion` | `LockLEDHandle`／`UnLockLEDHandle` | `boolean LockLEDHandle(Byte[] ids)`、`boolean LockLEDHandle(String LockKey, Byte[] ids)`、対応する`void UnLockLEDHandle(...)` | `CRobotMotion` JavaDoc | legacy `RobotSys`にnon-keyed使用例あり | thread、process、crash、partial overlap semantics | full LED IDsをfresh `setLED_Sota()->getLed().keySet()`から導出するGate 1Lだけ準備済み |
| Gate 1 LED lock acquisition | **UNKNOWN / NOT EXECUTED** | `CRobotMotion` | key付き`LockLEDHandle` | `LED_TEST_KEY`＋derived full LED set | N/A | N/A | return、ownership effect | option 10 human-only、failureはfail-closed |
| Visible LED response while lock held with play key | **UNKNOWN / NOT EXECUTED** | `CRobotMotion` | key付きlock＋3引数key付き`play` | lock key == play key、LOW=64 | N/A | N/A | visible response、sole cause | option 11 human-only。locked/current ID集合一致をplay前に確認 |
| Four-argument `play(..., ledposcheck)` | **CONFIRMED SURFACE / NOT TESTED** | `CRobotMotion` | `play` | `play(CRobotPose, int, String, boolean)` | `CRobotMotion` JavaDoc | N/A | `ledposcheck` semantics、safety | LED lock単独でvisibleにならない場合のpotential later diagnostic。今回未使用 |
| Axis read ordering | **CONFIRMED**（API） | `CRobotMotion` | `getDefaultIDs`／`getReadpos` | `Byte[] getDefaultIDs()`、`Short[] getReadpos()` | `CRobotMotion` JavaDoc | legacy reads vendor arrays | logical profile、unit conversion、installed behavior | read-only later gate |
| In-memory vendor audio candidate | **CONFIRMED**（API surface） | `CWavePlayer` | constructor／`run`／`stop`／`getLine` | `CWavePlayer(AudioInputStream)`、`void run()`、`void stop()`、`SourceDataLine getLine()` | `CWavePlayer` JavaDoc | legacy uses external `aplay`; not reusable | Edison format、start/stop/flush/close、line ownership | audio-specific later gate |
| Playback position | **INFERRED**（adapter feasibility） | `SourceDataLine`／`DataLine` | `getLongFramePosition`／`getMicrosecondPosition` | Java SE 8 inherited methods | Oracle Java SE 8 JavaDoc | legacy has no device playhead | Edison precision、latency、monotonicity | audio-specific later gate |
| Running motion physical cancel | **NOT AVAILABLE**（surveyed API） | `CRobotMotion` | none found | N/A | `CRobotMotion` JavaDoc method list | legacy has logical thread stop but no safe public cancel proof | vendor-approved stop method、physical semantics | separate future gate; Gate 1対象外 |
| Dog-specific public adapter | **UNKNOWN** | none confirmed | none confirmed | N/A | official package/all-classes survey | legacy reuses `CSotaMotion`; official根拠ではない | Dog official class、profile、capabilities | Sota後のfuture gate |

## 3. Sota mouth LEDとvoice-sync

| Capability | 判定 | 公開APIまたは観測 | 設計上の結論 | 残る確認 |
|---|---|---|---|---|
| Sota全LED poseの構築 | CONFIRMED | `CRobotPose.setLED_Sota(Color eye_L, Color eye_R, int mouth, Color powerbtn)` | eyes、mouth、power buttonを一つのposeへ設定できる | 各値のinstalled JAR上の厳密な許容範囲 |
| poseのsoftware structure diagnostic | CONFIRMED（surface）／OBSERVED | `new CRobotPose()`、`getPose()`、`getTorque()`、`getLed()`、`setLED_Sota(...)` | before/after mapをcopyしてentryと差分を表示し、`play()`を呼ばない | servo／torqueはnullのまま、LEDはnullからsize 10へ変化。LOW=64でid 14/value 64を観測 |
| poseのhardware反映候補 | CONFIRMED（surface）／OBSERVED TWICE | `CRobotMotion.play(CRobotPose pose, int msec)`、`play(..., String LockKey)`、`play(..., String LockKey, boolean ledposcheck)` | 3引数版はGate 1A-1とGate 1Bで各一回`true`、servo movementなし。Gate 1L option 11も同じ3引数版だけをone-shot使用 | disable前後ともmouth/eyes/power visible changeなし。4引数版はNOT TESTED |
| mouth最大値のsample | CONFIRMED | 公式`MotionSample.java`が`setLED_Sota(..., 255, ...)`を「口LED(Max)」として使用 | 255は公式sample上の最大例 | installed JARで0..255全域が受理されるか、範囲外時の挙動 |
| mouthだけを指定するpose primitive | INFERRED | `CRobotPose.SetLed(Byte[] ids, Short[] leds)`または`SetLed(Map<Byte,Short>)`はsubsetを表現できる | 公開されたSota mouth LED IDが確認できれば独立更新候補になる | Sota mouth LEDの公式ID、値表現、`play`時の他LED保持 |
| Sota mouth LEDの公開ID | UNKNOWN | `CSotaMotion`の公開定数は8個のservo ID。mouth LED定数はJavaDocで確認できない | 数値IDを推測、legacyから転記、またはtestへ固定しない | VSTONEへの問い合わせまたは公式資料による確認 |
| native voice-sync無効化 | CONFIRMED（surface）／RETURNED NORMALLY ONCE | `CSotaMotion.disabeMouthLEDVoiceSync()` | spellingを修正せず、そのままfacade内でだけ呼ぶ | actual state、効果、冪等性、failure表現。disable後もvisible LED changeなし |
| native voice-sync有効化 | CONFIRMED（surface）／RETURNED NORMALLY ONCE | `CSotaMotion.enabeMouthLEDVoiceSync()` | cleanupでconfigured enable候補 | 元の状態を復元できるか、冪等性、failure表現。normal returnはoriginal-state restoreの証明ではない |
| native voice-sync current-state getter | UNKNOWN | 公開JavaDocにgetterを確認できない | 「常にenableへ戻す」を元状態の復元と同義にしない | startup時の既定状態、query手段、owner間の契約 |
| 旧versionとの整合 | UNKNOWN | 2019年の公式support回答は当時、口LEDの外部制御とvoice-sync on/offを利用できないとしていた。現行JavaDocはenable/disable surfaceを掲載する | installed JARのprovenanceとAPI versionをmanual gateにする | API追加version、Edison搭載JARとの差、移行可否 |

`docs/plans/java-redesign-migration-plan.md`にあったSota mouth LED ID `14`は公式JavaDocで確認できない。公開定数のID `14`として確認できるものは`CCommUMotion.SV_MOUTH`、すなわちCommUのmouth servoであり、Sota mouth LEDへ流用してはならない。

`docs/decisions/adr-java-only-redesign.md` 9.4は本checkpointで改訂し、ID `14` candidateを **WITHDRAWN ASSUMPTION** として正式に撤回した。今後、公式根拠のない数値ID sequenceをproduction設計へ復活させる場合は別の明示的ADR reviewを必要とする。

## 4. LED lockとownership

| Capability | 判定 | 公開signature | 公開資料から分かること | UNKNOWNのsemantics |
|---|---|---|---|---|
| thread owner lock | CONFIRMED（surface） | `boolean CRobotMotion.LockLEDHandle(Byte[] ids)` | JavaDocは現在threadへLED制御をlockし、lock外threadから制御できないと説明する | 同一threadでの再取得、部分重複、thread終了時、例外時の状態 |
| keyed lock | CONFIRMED（surface） | `boolean LockLEDHandle(String LockKey, Byte[] ids)` | 対応keyを使う`play`が必要で、取得可否をbooleanで返す | keyのscope、他processとの排他、timeout、fairness、crash recovery |
| unlock | CONFIRMED（surface） | `void UnLockLEDHandle(Byte[] ids)`、`void UnLockLEDHandle(String LockKey, Byte[] ids)` | 対応するrelease surfaceがある | 二重release、誤key、部分failure、失敗の通知 |
| cross-process exclusive ownership | UNKNOWN | 公開JavaDocに保証なし | OS-level process lockとは別責務として扱う | AppManagerや別processとの競合時の実挙動 |

VSTONE lockはvendor handleの利用権であり、Sota全体のcross-process mutexとはみなさない。guarded probeでは`getDefaultIDs()`の全servoを専用keyでlockし、異なるkeyをLED `play`へ渡す。Gate 1Lではmouth-only IDを推測せず、fresh `setLED_Sota()` poseが生成したfull LED key setを導出し、play keyと同じ`LED_TEST_KEY`で一回だけlockする。lock falseならoption 11へ進まず、unlockはoption 12とbest-effort cleanupに含める。数値IDのhard-code、mouth-only LED lock、cross-process保証への一般化は行わない。

## 5. Servo、pose、read、lifecycle

| `RobotBackend` operation | 判定 | 公開API mapping候補 | Gap / gate |
|---|---|---|---|
| `initialize` | CONFIRMED（surface） | 公式sample順の`new CRobotMem()` → `new CSotaMotion(mem)` → `Connect()` → `InitRobot_Sota()` | construction、class loading、startupでservo power、initial pose、LED、audioを実行しない。partial failure時は`Disconnect()`を試みる |
| lifecycle query | INFERRED | `CRobotMem.isConected()`（公式spelling）とadapter state | vendor APIだけではprojectの7状態を表現しないためadapterが所有する |
| `readAxes` | CONFIRMED（surface） | `getDefaultIDs()`と`getReadpos()` | JavaDocはread positionの順序がdefault IDs順と説明する。ID→logical nameと単位変換はprofile/manual gate |
| `applyPose` | CONFIRMED（surface） | `CRobotPose.SetPose(...)`、必要なら`SetLed(...)`、`CRobotMotion.play(...)` | angle range、単位、transition、lock key、return false、exceptionのtranslationが必要 |
| interpolation completion | CONFIRMED（surface） | `isEndInterpAll()`、`waitEndinterpAll()` | `Thread.sleep(duration)`だけで完了を断定しない。interrupt/cancelとの統合が必要 |
| running interpolation cancel | UNKNOWN | 公開method一覧にrunning motion stop/cancelを確認できない | `requestRobotStop`をphysical stopとして実装済みにできない。generationによる後続抑止と実機動作停止を区別する |
| servo power | CONFIRMED（surface） | `ServoOn()`、`ServoOff()` | 現行`RobotBackend`は明示的servo power lifecycleを持たない。自動startup/shutdownへ埋め込まず、robot別安全方針を先に決める |
| `close` | INFERRED／OBSERVED RISK | owned unlock、voice-sync restore、`CRobotMem.Disconnect()` | cleanup順序、各failure後の続行、元voice-sync状態、servo状態はmanual/design gate。disconnect後にvendor shutdown hookの`ServoOff` attemptとsocket write failure／NPE／Cmd Send Errorを二回以上観測 |

Sotaの公開servo定数は`SV_BODY_Y`、`SV_L_SHOULDER`、`SV_L_ELBOW`、`SV_R_SHOULDER`、`SV_R_ELBOW`、`SV_HEAD_Y`、`SV_HEAD_P`、`SV_HEAD_R`で、公式constant valuesは順に1..8である。これはservo IDの確認であり、degree変換比、可動域、initial positionの確認ではない。

## 6. Robot別capability差

| Robot | 判定 | 公開surface | 現時点の扱い |
|---|---|---|---|
| Sota | CONFIRMED（一部） | `CSotaMotion(CRobotMem)`、`InitRobot_Sota()`、8 servo constants、mouth voice-sync enable/disable、`setLED_Sota` | 最優先。mouth-only ID、voice-sync semantics、range、lock挙動はmanual/VSTONE gate |
| CommU | CONFIRMED（一部） | `CCommUMotion(CRobotMem)`、`InitRobot_CommU()`、14 servo constants、`LipSyncEnable(boolean)`、`setLED_CommU` | Sota adapterの定数やvoice-sync APIを共有しない。ID 14はCommU mouth servo |
| Dog | UNKNOWN | 調査した公式`jp.vstone.RobotLib` class一覧にDog固有motion classを確認できない | legacy実装が`CSotaMotion`を使うことを公式根拠にしない。公開APIとrobot profileが確認されるまでunsupported |

## 7. Audio APIと現行audio boundary

| Capability | 判定 | 公開API | 現行interfaceへのmapping / gap |
|---|---|---|---|
| memory由来streamの再生候補 | CONFIRMED（surface） | `new CWavePlayer(AudioInputStream)` | canonical `PcmAudioData`からJava SE `AudioInputStream`を構築すればfile不要のadapter候補。Edison上の対応formatはmanual gate |
| playback start | CONFIRMED（surface） | `CWavePlayer implements Runnable`、`run()` | `AudioPlaybackSession.start()`はadapter所有threadでrunする候補 |
| stop | CONFIRMED（surface） | `CWavePlayer.stop()` | stopの冪等性、blocking解除、flush、return後のdevice状態はUNKNOWN |
| line access | CONFIRMED（surface） | `CWavePlayer.getLine()` returns `SourceDataLine` | lineが利用可能になる時点とownershipはUNKNOWN |
| playhead | CONFIRMED（Java SE surface） | `DataLine.getLongFramePosition()`、`getMicrosecondPosition()` | `PlaybackClock`へ直接対応する形。Edisonでの単調性、精度、buffer latencyはmanual gate |
| completion/state | INFERRED | `run()` return、`CWavePlayer.isUsed()` | `isUsed()`の意味がJavaDocで明確でない。adapter自身がthread completionを所有する必要がある |
| cleanup | INFERRED | `CWavePlayer.stop()`、取得した`SourceDataLine`の`stop/flush/drain/close` | 誰がlineをcloseするか、normal/error/replace時の順序をmanual testとfake facadeで固定する |

Java SE `SourceDataLine`のplayheadはAPI形状として利用できるが、wall-clock開始時刻だけで同期精度を断定しない。`CWavePlayer` wrapperはsessionごとにthread、player、line、completion、stop-once、close-onceを所有し、global process killや固定一時fileを使用しない。

## 8. 現行Java実装とのgap分類

### Case A — mouth-only public primitive

`SetLed`はsubsetを表現できるが、Sota mouth LEDの公式IDが未確認であるため **UNKNOWN**。IDが公式に確認され、他LEDを変更しないことがmanual acceptanceで確認できた場合だけ採用候補とする。

### Case B — full LED pose coordination

`setLED_Sota`と`play`の公開surfaceは **CONFIRMED** だが、両者を組み合わせたLED-only commitの一般的servo非依存semanticsは **UNKNOWN**。公式sampleはservo power、pose、LED設定、`play(...)`を組み合わせており、安全なLED-only使用例ではない。option 3ではconstructor直後と`setLED_Sota`後のservo／torque mapがともにnull、LED mapだけがnullからsize 10へ変化した。Gate 1A-1とGate 1BのLOW updateはいずれも`play()` true、servo movement／soundなし、mouth／eyes／power visible changeなしだった。Gate 1Lはfresh poseのfull LED key setをsame play keyでlockする一変数だけを追加する。ID 14/value 64はtested runtimeのOBSERVED map entryであり、公式ID specificationではない。servo safety observationはPASSだがvisible LED controlとGate 1A全体は未確認であり、production実装は行わない。

### Case C — voice-syncが外部制御を妨げる

Gate 1Bではdisable/enable surfaceがnormal returnし、disable中の同条件LOW `play()`もtrueだったが、mouth／eyes／power visible changeはなかった。したがってnative voice-syncだけがmanual updateを見えなくしていたという仮説は今回支持されなかった。ただしactual sync state、LED ownership、commit、other owner interactionは **UNKNOWN** のままである。次のGate 1Lではfresh pose由来のfull LED set lockだけを追加し、direct ID 14 writeや4引数playは導入しない。

結論として、現時点はCase Bをadapter設計の保守的baselineとし、Case A/Cの結果で最終決定する。現在の`AudioSessionCoordinator`はlogical `MOUTH`更新だけを送っており、`RobotBackend.acquireLedOwnership`、`disableNativeMouthVoiceSync`、restore、releaseをsession lifecycleから呼んでいない。この結線gapはVSTONE adapter実装前に解消し、順序とfailure cleanupをfakeでtestする必要がある。

推奨boundaryは次のとおりである。

```text
AudioSessionCoordinator
  -> VstoneMouthSession (generation-scoped lifecycle)
     -> LedCoordinator (complete validated LED state)
        -> VstonePublicApiFacade
           -> CRobotPose / CSotaMotion public methods only

VstoneAudioOutput
  -> VstoneAudioPlaybackSession
     -> CWavePlayer / SourceDataLine public methods only
```

vendor objectをfacade外へ公開せず、robot hardware callはsingle hardware worker、blocking audioは別のowned workerで実行する。

## 9. Vendor JAR受入checklistとMaven方針

実装開始前にoperatorが公式配布物について次を記録し、reviewする。

* 配布元URLまたは公式media、取得日、提供者
* artifact filename、vendor version、build/release識別子
* SHA-256
* 対応robot、Edison image、Java version
* license全文、社内保存可否、repository commit可否、再配布可否
* 必要な追加JAR、native library、service、environment
* Java 8 compatibility
* artifact size、transitive/runtime dependency
* vendor support/maintenance状態と既知security情報
* 公開JavaDocとinstalled JARのpublic signature一致確認方法

2023年の公式support回答は`sotalib.jar`をSota上での実行向けとし、それ以外の環境での動作を未検証・非supportとしている。default Windows build/testは引き続きvendor JARを要求しない。

推奨候補は、provenance、license、SHA-256を確認した後にだけ有効になる専用Maven profileと、アクセス制御された組織内Maven repositoryの組合せである。versionを固定し、dependencyをVSTONE moduleだけへ限定する。再配布が許可されない場合はoperator-provisioned local Maven repositoryをfallback候補とし、`systemPath`、個人absolute path、public repositoryへのJAR commitは採用しない。このphaseではdependencyもprofileも追加しない。

## 10. VSTONEへの任意の追加確認事項

次の問い合わせはrisk reductionに有用だが、guarded Gate 1 probe準備またはhuman executionの必須解除条件ではない。manual evidenceと不一致があれば、production設計を進めず再reviewする。

1. 現行JavaDocに対応する`sotalib.jar`のversion、配布元、Edison image互換性は何か。
2. Sota mouth LEDを`SetLed`で単独指定できる公開IDまたは公開constantはあるか。
3. `setLED_Sota`のmouth引数の厳密な範囲、範囲外時の挙動、更新頻度上限は何か。
4. `new CRobotPose()`へ`setLED_Sota(...)`だけを適用して`play`したとき、未指定servo fieldはskipされ、servo target、torque、interpolationへ一切のcommandまたは状態変化を生じないか。`ServoOn()`なしでLEDだけを反映できるか。`play`を使わない公開LED-only commit methodがある場合はexact signatureと対応versionは何か。
5. `disabeMouthLEDVoiceSync`／`enabeMouthLEDVoiceSync`の初期状態、冪等性、失敗通知、query方法は何か。
6. keyed/non-keyed LED lockのthread、process、key、重複、crash、partial overlap semanticsは何か。
7. interpolation実行中に公開APIだけで安全にcancel/stopできるか。
8. `CWavePlayer.stop()`のblocking、flush、line close、再呼出しsemanticsは何か。
9. `getLine()`を取得できる時点と、`getLongFramePosition()`のEdison上の精度は何か。
10. Dog向けの公式Java motion class、profile、公開sampleは存在するか。

これらが未解決でもguarded manual probeはhuman-onlyで実施できるが、Sota mouth-only control、元voice-sync状態の完全な復元、running motion physical stop、Dog adapterをproduction-readyと表現しない。
