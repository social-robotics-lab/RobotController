# VSTONE公開Java API capability matrix

## 1. 目的と調査境界

本書は、Java版RobotControllerのVSTONE adapter設計に必要な公開API capabilityを、2026-08-08時点の公式JavaDoc、公式sample、公式support情報、およびrepository内の現行interfaceと照合したevidenceである。Sotaを優先し、CommUとDogは差分だけを記録する。

本調査では実機、device、AppManager、VSMD、audio outputを操作していない。`sotalib.jar`のdownload、逆コンパイル、disassembly、`javap`、strings抽出、reflection、private member調査も行っていない。公開APIの存在は、対象Edisonに配置されたJARでの存在や実機semanticsを保証しない。

判定語は次の意味で使用する。

* **CONFIRMED**: 指定した公式公開資料でclass、method、signature、定数、またはsample使用法を確認した。
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

| Capability | Status | Public class | Public method | Signature | Official source | Legacy reference | Remaining uncertainty | Manual test |
|---|---|---|---|---|---|---|---|---|
| Sota mouth LED ID `14` | **WITHDRAWN ASSUMPTION** | N/A | N/A | N/A | `CSotaMotion` constantsとconstant valuesにSota mouth LED IDなし。ID 14は`CCommUMotion.SV_MOUTH` | legacy `LedConverter_Sota`とhistorical VSMD evidenceはID 14を使用 | Sota mouth-only public IDの有無 | IDを使う試験は禁止。VSTONE clarification待ち |
| Sota complete LED pose | **CONFIRMED**（API） | `CRobotPose` | `setLED_Sota` | `void setLED_Sota(Color eye_L, Color eye_R, int mouth, Color powerbtn)` | `CRobotPose` JavaDoc、official `MotionSample.java` | legacy Pose pathもfull LED valuesを構成 | brightness範囲、他LED保持、実機反映 | Gate 1A |
| LED pose commit | **CONFIRMED**（API） | `CRobotMotion` | `play` | `boolean play(CRobotPose pose, int msec)`およびlock-key overload | `CRobotMotion` JavaDoc、official sample | legacy `PoseExecutorThread`が`play`を使用 | LED-only transition、rate、return false semantics | Gate 1A／1C |
| Native voice-sync disable | **CONFIRMED**（API） | `CSotaMotion` | `disabeMouthLEDVoiceSync` | `void disabeMouthLEDVoiceSync()` | `CSotaMotion` JavaDoc | legacyは直接利用していない | effect、idempotency、failure、他owner interaction | Gate 1B |
| Native voice-sync enable | **CONFIRMED**（API） | `CSotaMotion` | `enabeMouthLEDVoiceSync` | `void enabeMouthLEDVoiceSync()` | `CSotaMotion` JavaDoc | legacyは直接利用していない | restore semantics、元状態がdisabledの場合 | Gate 1B／1D |
| Native voice-sync state query | **NOT AVAILABLE**（surveyed API） | `CSotaMotion` | none found | N/A | `CSotaMotion` JavaDoc method list | legacyにもreliable getterなし | installed version、vendor-approved query | Gate 1 preflight／vendor clarification |
| LED lock surface | **CONFIRMED**（API） | `CRobotMotion` | `LockLEDHandle`／`UnLockLEDHandle` | `boolean LockLEDHandle(Byte[] ids)`、`boolean LockLEDHandle(String LockKey, Byte[] ids)`、対応する`void UnLockLEDHandle(...)` | `CRobotMotion` JavaDoc | legacy `RobotSys`にnon-keyed使用例あり | exact Sota IDs、duplicate、thread、process、crash semantics | Gate 1 ownership subtest only after ID confirmation |
| Axis read ordering | **CONFIRMED**（API） | `CRobotMotion` | `getDefaultIDs`／`getReadpos` | `Byte[] getDefaultIDs()`、`Short[] getReadpos()` | `CRobotMotion` JavaDoc | legacy reads vendor arrays | logical profile、unit conversion、installed behavior | read-only later gate |
| In-memory vendor audio candidate | **CONFIRMED**（API surface） | `CWavePlayer` | constructor／`run`／`stop`／`getLine` | `CWavePlayer(AudioInputStream)`、`void run()`、`void stop()`、`SourceDataLine getLine()` | `CWavePlayer` JavaDoc | legacy uses external `aplay`; not reusable | Edison format、start/stop/flush/close、line ownership | audio-specific later gate |
| Playback position | **INFERRED**（adapter feasibility） | `SourceDataLine`／`DataLine` | `getLongFramePosition`／`getMicrosecondPosition` | Java SE 8 inherited methods | Oracle Java SE 8 JavaDoc | legacy has no device playhead | Edison precision、latency、monotonicity | audio-specific later gate |
| Running motion physical cancel | **NOT AVAILABLE**（surveyed API） | `CRobotMotion` | none found | N/A | `CRobotMotion` JavaDoc method list | legacy has logical thread stop but no safe public cancel proof | vendor-approved stop method、physical semantics | separate future gate; Gate 1対象外 |
| Dog-specific public adapter | **UNKNOWN** | none confirmed | none confirmed | N/A | official package/all-classes survey | legacy reuses `CSotaMotion`; official根拠ではない | Dog official class、profile、capabilities | Sota後のfuture gate |

## 3. Sota mouth LEDとvoice-sync

| Capability | 判定 | 公開APIまたは観測 | 設計上の結論 | 残る確認 |
|---|---|---|---|---|
| Sota全LED poseの構築 | CONFIRMED | `CRobotPose.setLED_Sota(Color eye_L, Color eye_R, int mouth, Color powerbtn)` | eyes、mouth、power buttonを一つのposeへ設定できる | 各値のinstalled JAR上の厳密な許容範囲 |
| poseのhardware反映 | CONFIRMED | `CRobotMotion.play(CRobotPose pose, int msec)`、`play(..., String LockKey)`、`play(..., String LockKey, boolean ledposcheck)` | `CRobotPose`変更だけではなく、`play`をcommit境界にする | `msec=0`等のLED-only更新semanticsとrate limit |
| mouth最大値のsample | CONFIRMED | 公式`MotionSample.java`が`setLED_Sota(..., 255, ...)`を「口LED(Max)」として使用 | 255は公式sample上の最大例 | installed JARで0..255全域が受理されるか、範囲外時の挙動 |
| mouthだけを指定するpose primitive | INFERRED | `CRobotPose.SetLed(Byte[] ids, Short[] leds)`または`SetLed(Map<Byte,Short>)`はsubsetを表現できる | 公開されたSota mouth LED IDが確認できれば独立更新候補になる | Sota mouth LEDの公式ID、値表現、`play`時の他LED保持 |
| Sota mouth LEDの公開ID | UNKNOWN | `CSotaMotion`の公開定数は8個のservo ID。mouth LED定数はJavaDocで確認できない | 数値IDを推測、legacyから転記、またはtestへ固定しない | VSTONEへの問い合わせまたは公式資料による確認 |
| native voice-sync無効化 | CONFIRMED（surface） | `CSotaMotion.disabeMouthLEDVoiceSync()` | spellingを修正せず、そのままfacade内でだけ呼ぶ | installed JARでの存在、効果、冪等性、failure表現 |
| native voice-sync有効化 | CONFIRMED（surface） | `CSotaMotion.enabeMouthLEDVoiceSync()` | cleanupでrestore候補 | 元の状態を復元できるか、冪等性、failure表現 |
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

VSTONE lockはvendor handleの利用権であり、Sota全体のcross-process mutexとはみなさない。新adapterではsingle hardware worker上でlock、key付き`play`、unlockを行い、lock成功前にvoice-syncやLED状態を変更しない。unlockはbest effort cleanupに含めるが、release失敗を成功として隠さない。exact mouth LED IDが未確認の間、mouth-only lockは実装しない。

## 5. Servo、pose、read、lifecycle

| `RobotBackend` operation | 判定 | 公開API mapping候補 | Gap / gate |
|---|---|---|---|
| `initialize` | CONFIRMED（surface） | `new CRobotMem()` → `Connect()` → `new CSotaMotion(mem)` → `InitRobot_Sota()` | construction、class loading、startupで`ServoOn`、initial pose、LED、audioを実行しない。partial failure時は`Disconnect()`を試みる |
| lifecycle query | INFERRED | `CRobotMem.isConected()`（公式spelling）とadapter state | vendor APIだけではprojectの7状態を表現しないためadapterが所有する |
| `readAxes` | CONFIRMED（surface） | `getDefaultIDs()`と`getReadpos()` | JavaDocはread positionの順序がdefault IDs順と説明する。ID→logical nameと単位変換はprofile/manual gate |
| `applyPose` | CONFIRMED（surface） | `CRobotPose.SetPose(...)`、必要なら`SetLed(...)`、`CRobotMotion.play(...)` | angle range、単位、transition、lock key、return false、exceptionのtranslationが必要 |
| interpolation completion | CONFIRMED（surface） | `isEndInterpAll()`、`waitEndinterpAll()` | `Thread.sleep(duration)`だけで完了を断定しない。interrupt/cancelとの統合が必要 |
| running interpolation cancel | UNKNOWN | 公開method一覧にrunning motion stop/cancelを確認できない | `requestRobotStop`をphysical stopとして実装済みにできない。generationによる後続抑止と実機動作停止を区別する |
| servo power | CONFIRMED（surface） | `ServoOn()`、`ServoOff()` | 現行`RobotBackend`は明示的servo power lifecycleを持たない。自動startup/shutdownへ埋め込まず、robot別安全方針を先に決める |
| `close` | INFERRED | owned unlock、voice-sync restore、`CRobotMem.Disconnect()` | cleanup順序、各failure後の続行、元voice-sync状態、servo状態はmanual/design gate |

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

`setLED_Sota`と`play`は **CONFIRMED**。現時点の安全側設計候補は、adapter内の`LedCoordinator`がeyes、mouth、power buttonのvalidated logical stateを一括所有し、更新ごとに完全なLED poseを組み立てる方式である。ただし、`play`が未指定servo状態へ与える影響、rate limit、lock ID範囲を確認するまではproduction実装しない。

### Case C — voice-syncが外部制御を妨げる

現行JavaDocにdisable/enable surfaceはあるが、installed JARとの差と実際の競合semanticsは **UNKNOWN**。2019年の公式support回答とのversion差もあるため、disable、direct update、zero、restoreの順序をmanual gateにする。

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

## 10. VSTONEへの確認事項

1. 現行JavaDocに対応する`sotalib.jar`のversion、配布元、Edison image互換性は何か。
2. Sota mouth LEDを`SetLed`で単独指定できる公開IDまたは公開constantはあるか。
3. `setLED_Sota`のmouth引数の厳密な範囲、範囲外時の挙動、更新頻度上限は何か。
4. LED-only `CRobotPose`を`play`したとき、未指定servo/LEDは保持されるか。
5. `disabeMouthLEDVoiceSync`／`enabeMouthLEDVoiceSync`の初期状態、冪等性、失敗通知、query方法は何か。
6. keyed/non-keyed LED lockのthread、process、key、重複、crash、partial overlap semanticsは何か。
7. interpolation実行中に公開APIだけで安全にcancel/stopできるか。
8. `CWavePlayer.stop()`のblocking、flush、line close、再呼出しsemanticsは何か。
9. `getLine()`を取得できる時点と、`getLongFramePosition()`のEdison上の精度は何か。
10. Dog向けの公式Java motion class、profile、公開sampleは存在するか。

これらが未解決の間、Sota mouth-only control、元voice-sync状態の完全な復元、running motion physical stop、Dog adapterをproduction-readyと表現しない。
