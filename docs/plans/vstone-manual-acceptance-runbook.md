# VSTONE公開API manual acceptance runbook

## 1. Status、目的、実行権限

**Status: DIAGNOSTIC REVISION PREPARATION ALLOWED / MANUAL EXECUTION HUMAN-ONLY**

**Production adapter: BLOCKED UNTIL GATE 1 PASS.** [`manual_tests/vstone-gate1/`](../../manual_tests/vstone-gate1/README.md)の現revisionは、Gate 1Bでnative voice-sync disable後もmouth／eyes／powerのvisible changeがなかった観測を受け、derived LED ID setのkey付きlockだけを新しい変数とするoption 10～12を限定的に追加する。option 5と9はinteractive menuからblockされる。source review、physical preflight、installed JARでのcompile、人間の明示的opt-inが完了するまで実行承認とみなさない。

ユーザー提供のmanual run logに基づく現在のcheckpointは次のとおりである。

```text
Gate 1A-0: PASS observed once
Default servo IDs count: 8
LockServoHandle: success
Previous option 3: ABORT
Current option 3 diagnostic: COMPLETED
Before: servo=null, torque=null, LED=null
After setLED_Sota: servo=null, torque=null, LED size=10
Observed with LOW=64: LED entry id=14,value=64
Gate 1A-1 play(): EXECUTED ONCE with LOW=64; returned true
Gate 1A-1 servo movement: OBSERVED NONE
Gate 1A-1 visible mouth/eyes/power response: OBSERVED NO CHANGE
Gate 1A-1 Java exception: NONE
Gate 1A-1 servo safety: PASS / OBSERVED NO MOVEMENT
Gate 1A mouth control: NOT CONFIRMED
Gate 1A overall: NOT PASSED
Gate 1B disable call: RETURNED NORMALLY
Gate 1B play after disable: returned true
Gate 1B servo movement / unexpected sound: NO / NO
Gate 1B visible mouth/eyes/power response: NO / NO / NO
Gate 1B configured enable call: RETURNED NORMALLY
Gate 1B: DIAGNOSTIC OBSERVATION ONLY
LED ownership / lock: UNKNOWN — next manual test
Gate 1 pose structural assumption: INVALIDATED
Next human workflow: 1 -> 2 -> 3 -> 4 -> 6 -> 7 -> 10 -> 11 -> 12 -> 8 -> c
```

無効になった仮定は「`new CRobotPose()`直後のservo／torque mapはnon-nullかつempty」である。tested runtimeでは両mapが`null`だったため、`null OR empty`をservo／torque command dataなしとして扱う。ID 14／value 64はtested runtimeでLOW=64を設定した際のOBSERVED map entryであり、公式public ID specificationではない。

本runbookは、Sota上の公式VSTONE Java APIについて、静的資料だけでは確定できないsemanticsを人間のoperatorが段階的に確認するための候補手順である。Codexを含む自動エージェントは、本書の手順、deploy、実機test、device access、servo、LED、audio output、service操作を実行してはならない。

実行には、VSTONE公式手順、施設の安全手順、robot管理者、operatorの事前reviewと明示的opt-inが必要である。本書単独では実行承認にならない。最初の目的はAPI capabilityの確認であり、production adapterの受入や実機安全性の証明ではない。

対象優先順位はSota、次にCommUである。Dogは公式公開APIが確認できるまで対象外とする。

## 2. Hard stop conditions

次のいずれかがある場合は開始しない、または直ちに安全手順へ移行して試験を中止する。

* robot model、電源、安全な設置、非常時対応、責任operatorが確認できない
* `sotalib.jar`の公式provenance、version、SHA-256、licenseが記録できない
* installed JARと利用する公開JavaDocの対応が確認できない
* current RobotController、別のrobot application、または競合processの停止をoperatorが確認できない
* process lockを取得できない、またはlock file削除やservice停止で競合回避する必要がある
* `vsmd_edison`、AppManager、robot設定を変更または停止しなければ試験できない
* 使用するpublic API、operatorが承認するbrightness値、`getDefaultIDs()`で取得するservo guard対象がreviewされていない
* servo、torque、姿勢、既存LED、音声が予期せず変化する
* 異音、発熱、振動、転倒・落下のおそれ、communication loss、exception、hangがある
* cleanup後にmouth zero、voice-sync状態、lock release、audio停止を確認できない

`killall`、無差別なprocess終了、`systemctl stop/disable vsmd_edison`、device fileへの直接write、lock fileの手動unlink、低レベルAppManager/VSMD write、vendor JAR解析を代替策として使用しない。

## 3. Preflight record

operatorは実行前に次を埋め、reviewerの承認を記録する。

| Field | Recorded value |
|---|---|
| Test ID / date / location | |
| Robot model / asset ID / serial | |
| Edison image / OS build | |
| `java -version`の完全な出力 | |
| Official JAR filename / version | |
| JAR source / acquisition date / provider | |
| JAR SHA-256 | |
| License / redistribution decision | |
| Required companion JAR/native/service | |
| Public JavaDoc version correspondence | |
| Test source revision / artifact SHA-256 | |
| Configuration hash | |
| Operator / safety observer / reviewer | |
| Current RobotController stopped | Yes / No |
| Other robot process absent | Yes / No |
| Whole-robot advisory lock acquired | Yes / No |
| `vsmd_edison` left running and unchanged | Yes / No |
| Emergency stop/rollback procedure reviewed | Yes / No |
| Robot mechanically supported and clear | Yes / No |
| Audio volume and test-area approval | |

JARのhash計算、process観測、lock取得方法は、対象imageで承認済みのread-only/operational手順を使う。本runbookは特定serviceの停止や独自lock迂回commandを定義しない。

## 4. Test artifact gate

実行artifactは人間がsource reviewし、次を満たすことを確認する。

guarded probe sourceは準備済みだが、vendor JARを用いたcompileとhuman source reviewは未実施である。`setLED_Sota(...)`のAPI存在やservo guardを、`play(...)`が本質的にservo非依存である保証へ読み替えてはならない。

* vendor importは専用VSTONE boundary内だけにある
* public classとpublic methodだけを使用する
* `ServoOn`、`ServoOff`、`SetTorque`、servo `SetPose`、initial poseを含まない
* constructionまたはclass loadingに実機I/Oを隠さない
* automatic retry、service操作、device direct access、reflectionを含まない
* bounded timeoutと明示的なnormal/error cleanupを持つ
* binary payload、JAR内容、機密情報をlogへ出力しない
* dry-runまたはAPI-presence checkと、実機状態を変えるtestが明確に分離されている
* operatorが一stepずつ開始でき、自動で次のwrite testへ進まない

compile/API-presence checkでは、installed JARに次のexact public surfaceが存在することを通常のJava compilation/linkingで確認する。JARの逆解析はしない。

* `CSotaMotion(CRobotMem)`、`InitRobot_Sota()`
* `CRobotMotion.getDefaultIDs()`、key付き`LockServoHandle(...)`／`UnLockServoHandle(...)`、key付き`play(...)`
* `CSotaMotion.disabeMouthLEDVoiceSync()`、`enabeMouthLEDVoiceSync()`
* `CRobotPose.setLED_Sota(...)`、`getPose()`、`getTorque()`、`getLed()`

signature不一致が一つでもあればwrite testへ進まず、installed versionと公式資料の不一致として記録する。

## 5. Manual Gate 1 — Guarded mouth LED / native voice-sync / cleanup

最初のmanual acceptanceはこのGate 1だけに限定する。servo motion、torque変更、full RobotController deployment、production adapter、motionとの同時実行、Dog／CommUを含めない。Phase Aの最小initializationを通過した後、次の1A～1Dを一つずつ人間が開始する。

現在推奨するhuman workflowは **option 1 → 2 → 3 → 4 → 6 → 7 → 10 → 11 → 12 → 8 → c → STOP** だけである。option 7はvoice-sync OFF／LED lockなしbaseline、option 11はvoice-sync OFF／derived LED lockありcomparisonである。LED-lock diagnostic中はoption 7直後にoption 8を実行しない。brightnessのoption 5とrate testのoption 9は開始しない。

### Gate 1A-0 — All-default-servo guard

`Connect()`と`InitRobot_Sota()`の後、`getDefaultIDs()`がnon-null、non-empty、全要素non-nullであることを確認する。全IDを専用servo guard keyで`LockServoHandle(...)`し、falseまたはexceptionならLED writeなしでABORTする。guard取得だけをPASSとして記録し、servo非動作を自動判定しない。

ユーザー提供のmanual runではdefault servo ID count 8とlock successが観測され、Gate 1A-0は一度PASSした。この観測は保持するが、lockの一般的semanticsや実機安全性へ一般化しない。

### Option 3 diagnostic — CRobotPose software structure

全default servo guard取得後、新しい`CRobotPose`を作り、公開getterの`getPose()`、`getTorque()`、`getLed()`が返すmapをそれぞれcopyする。sizeと全key/valueを`BEFORE setLED_Sota`として表示し、local objectへ`setLED_Sota(...)`だけを適用して同じmapを再度copyし、`AFTER setLED_Sota`として表示する。before/afterの等価性、added keys、removed keys、changed valuesを計算する。iteration orderはsemanticとして扱わない。

このdiagnosticは`motion.play()`、servo write、torque write、LED hardware write、voice-sync変更を行わない。`setLED_Sota()`はlocal `CRobotPose` mutationだけに使用する。option 3が正常完了した場合だけoption 4へ進める。

tested runtimeでは、beforeのservo／torque／LED mapはすべて`null`、afterのservo／torque mapも`null`、LED mapはsize 10と観測された。servo／torque mapはbefore/afterでequal、LED mapはnot equalだった。configured LOW=64に対して`id=14,value=64`がLED map内に観測された。これはinstalled runtimeの観測値に限定し、公式IDへ一般化しない。

### Gate 1A-1 — Single guarded LED-only update

**EXECUTED ONCE / SERVO SAFETY OBSERVED PASS / MOUTH CONTROL NOT CONFIRMED.** 既存runでは、LOW=64の`motion.play(pose, TRANSITION_MSEC, LED_TEST_KEY)`が`true`を返し、servo movementは観測されず、mouthのvisible changeも観測されず、Java exceptionもなかった。これは一回のoperator observationであり、LED-only `play`の一般的なservo無副作用保証ではない。

現revisionのoption 4は再現時も同じguardとone-shot条件を維持する。play return後はservo movement、unexpected servo sound、mouth visible changeを順に明示的yes/noで取得し、eyes／powerはfree textで取得する。movementまたはsoundがYESならFAILとし、cleanup mouth-zeroを含む追加`play()`をsuppressionする。movement／soundがNOならservo safetyだけをPASSとし、mouth responseやGate 1A全体へ広げない。

### Gate 1A-2 — Mouth brightness steps

**BLOCKED in the current probe revision (option 5).** The following remains future acceptance scope only.

`setLED_Sota(...)`と`play(...)`の公開APIだけを使用し、次を確認する。

* mouth brightnessが変化する。
* `ZERO`へ戻せる。
* `LOW`から承認済みの複数段階で目視差を記録できる。
* eyes／power LEDのbefore/afterと副作用を記録できる。
* servo、torque、audioに予期しない変化がない。

### Gate 1B — Native voice-sync

**EXECUTED / DIAGNOSTIC OBSERVATION ONLY.** `disabeMouthLEDVoiceSync()`はnormal returnし、同じLOW updateの`play()`も`true`を返した。operatorはservo movementなし、unexpected servo soundなし、mouth／eyes／power visible changeなしを観測し、最後の`enabeMouthLEDVoiceSync()`もnormal returnした。

1. option 6はGate 1A-1 servo safety PASS、guard保持、suppressionなしを要求し、ownership stateをcall前に記録してからexact vendor spellingの`disabeMouthLEDVoiceSync()`を一回だけ呼ぶ。`play()`、`setLED_Sota()+play()`、LED lock、direct ID 14 writeは行わない。
2. option 7はdisable attempted、normal return、restore pending、未実行を要求し、option 4と同じLOW条件を同じshared helperから一回だけ`play(...)`する。pre-playでvoice-sync状態がgetter不在のためUNKNOWNであることを表示する。実測ではreturn `true`でもvisible LED changeはなかった。
3. option 7はservo movement、unexpected servo sound、mouth visible change、eyes、powerをこの順で記録する。movementまたはsoundがYESならcleanup zeroを含む後続LED playをsuppressionするが、configured enable fallback、guard release、disconnectは継続する。
4. option 8はmouth changeのYES／NOにかかわらず`enabeMouthLEDVoiceSync()`を一回要求し、normal return後だけrestore pendingをclearする。これは元状態を復元した証明ではない。
5. Gate 1A-1 servo safety、Gate 1A-1 visible response、disable attempt、Gate 1B manual response、configured enable returnを独立して表示し、Gate 1AまたはGate 1Bの広いPASS booleanへまとめない。native voice-sync disable単独ではmanual updateをvisibleにできず、voice-syncだけが原因という仮説は今回支持されなかった。

### Gate 1L — Derived LED ownership / lock diagnostic

**LIMITED SEQUENCE ENABLED / NOT EXECUTED.** Temporary Gate 1Lは`LockLEDHandle`だけを新しい変数とし、4引数`play(..., ledposcheck)`、brightness、rate、direct LED ID writeを含めない。

1. option 10はoption 7完了、voice-sync restore pending、servo safety PASS、suppressionなしを要求する。fresh `CRobotPose`へ`setLED_Sota(...LOW...)`を適用し、servo／torque null-or-emptyとLED non-emptyを確認して、`getLed().keySet()`から重複／nullのない`Byte[]`を生成する。数値IDをhard-codeしない。
2. operatorへderived ID、`SERVO_GUARD_KEY`、`LED_TEST_KEY`を表示する。servo guard keyとfuture play keyは異なり、LED lock keyとfuture play keyは一致する。ENTER後、`LockLEDHandle(LED_TEST_KEY, derivedIds)`を一回だけ呼び、option 10では`play()`しない。false／exception時はfail-closed、retryなし、option 11禁止とする。
3. option 11はlock成功と同じvoice-sync OFF状態を要求する。fresh LOW poseのcurrent LED key setとoption 10で保存したlocked setを順序非依存で比較し、不一致ならplay前にABORTする。一致時だけ既存3引数`play(pose, 1000, LED_TEST_KEY)`を一回呼ぶ。
4. play直後にservo movement、unexpected servo sound、mouth、eyes、powerを明示的yes/noで記録する。movement／soundがYESならcleanup zeroをsuppressionするが、LED unlock、voice-sync enable、servo unlock、disconnectを続ける。
5. visible changeがあれば「same-key LED lock後にvisible behaviorが変わった」とだけ記録し、sole root causeとは断定しない。すべてNOなら「LED lock alone did not make the update visible」と記録できる。4引数playはpotential later diagnosticに留め、今回使用しない。
6. option 12はoption 10で実際にlockしたkeyとID cloneを`UnLockLEDHandle(...)`へ渡す。normal return後だけowned stateをclearする。実行されなければcleanup fallbackがbest effort releaseする。

### Gate 1C — Update rate

**BLOCKED in the current probe revision (option 9).** The following remains future acceptance scope only.

`ZERO`～`LOW`の範囲で **10 Hz → 20 Hz → 25 Hz** を独立sessionとして確認する。Guarded Gate 1 probeでは50 Hz、arbitrary rate、unbounded durationを禁止する。高頻度探索を目的にせず、queue lag、commit latency、flicker、他LED stateを記録する。

### Gate 1D — Cleanup and guarded resource ownership

normal completion、operator stop、一つの承認済みerror caseで、mouth `ZERO`、owned derived LED lock release、configured voice-sync enable attempt、all-default-servo guard release、`Disconnect()`を個別に確認する。Gate 1LのLED IDsはfresh `setLED_Sota()` poseから導出し、数値IDまたはmouth-only IDを推測しない。lock semanticsの一般化はGate 1L evidence review後も別判断とする。

### Gate 1 pass / fail criteria

Gate 1全体のminimum passは次のすべてを満たすことである。

* mouth brightnessを公開APIだけで制御でき、`ZERO`へ戻せる。
* native voice-sync disable中にapplication updateを維持でき、configured targetへrestoreできる。
* eyes／power LED stateを破壊しないfull-state coordination方式を設計できる観測結果がある。
* 10～25 Hzのうち必要なmouth update rateで、明白なqueue lag、unbounded latency、flicker、exceptionがない。
* 全default servo guardをwrite前に取得し、取得したguardを同じkey／ID集合でreleaseできる。
* normal／stop／approved error pathのresource closeが確認できる。

一項目でも満たせない、観測不能、または公式根拠不足ならFAILまたはBLOCKEDとし、VSTONE production adapter実装を開始しない。Case A、Case Bの変更、vendor問い合わせ、requirements変更のいずれが必要かを別reviewで決める。

## 6. Phase A — Initialization and read-only observation

1. 承認済みprocess lockが取得済みであることを再確認する。
2. 公式sampleと同じ順序で`CRobotMem`、`CSotaMotion`を構築し、`Connect()`のreturn、elapsed time、exceptionを記録する。
3. `InitRobot_Sota()`のreturn、elapsed time、exceptionを記録する。servo power APIは呼ばない。
4. initialization前後で、servo motion、torque、eyes、mouth、power LED、audioに変化がないことをoperatorが観測する。
5. `getDefaultIDs()`を一度だけ取得し、配列長、ID、return/exceptionだけを記録する。値をdegreeへ変換せず、可動域を推測しない。
6. 全default servo guardを同じkey／ID集合でreleaseし、`Disconnect()`、process lock releaseを行う。
7. resource、thread、processが残っていないことを確認する。

予期しない状態変化があれば以降を中止する。`InitRobot_Sota()`が無副作用であると、この一回の観測だけから一般化しない。

## 7. Phase B — Mouth control primitive

このphaseは、artifact review、physical preflight、Gate 1A-0をpassした後だけ実行する。次はvendor問い合わせの必須回答ではなく、operatorがinstalled runtimeと公開資料を照合し、residual riskとして記録する事項である。

* guarded probeではfull `setLED_Sota`だけを使い、数値LED IDを使わない
* installed runtimeに対してoperatorが承認したbrightness値と、その根拠
* transition 1000 ms、未指定servo／LED保持semantics、key付き`play`の残余リスク
* `getDefaultIDs()`で得た全servo ID、guard key、異なるplay key

### 7.1 Test values

確認済み範囲を`MIN`から`MAX`とし、次のsymbolic levelをoperatorが数値へ変換してrecordへ固定する。

| Symbol | Numeric value | 根拠 |
|---|---:|---|
| ZERO | | 公式仕様上の消灯値 |
| LOW | | 範囲内の保守的な低輝度 |
| MEDIUM | | 範囲内の中間値 |
| HIGH | | MAX未満の値 |
| MAX | | 公式仕様上の最大値 |

公式sampleはmouthに255を「Max」として使用するが、installed JARの0..255全域を確認するまでは自動的に`MAX=255`、`ZERO=0`と確定しない。probeは数値をdefault化せず、operator-approved `ZERO LOW MEDIUM HIGH`を起動引数で受け取る。

### 7.2 Single-update sequence

各stepの間にoperator pauseを置き、自動loopにしない。

1. baselineのeyes、mouth、power LED、native voice-sync、audio状態を記録する。
2. 全default servo guardを取得し、guard keyとplay keyが異なることを確認する。
3. option 3で新規poseのservo／torque／LED mapを`setLED_Sota(...)`前後にcopyし、size、entry、等価性、added／removed／changedを表示する。servo／torque mapの`null OR empty`をcommand dataなしとして扱う。
4. option 4でguard、異なるkey、map invariant、configured LOWを確認し、ENTER後にone low updateを一回だけcommitする。
5. servo movementを最優先で回答し、YESならFAILとして追加`play()`を禁止する。NOでもremaining observationを記録してSTOPする。
6. Gate 1A-2以降のwrite sequenceは現在すべてBLOCKEDとする。
7. cleanupで必要なmouth-zero、servo guard releaseと`Disconnect()`をbest effortで行い、post-cleanup exceptionを含めて記録する。

eyesまたはpower LEDが変化した場合はCase Bのstate coordination不足として不合格にし、部分updateを推測で試さない。

## 8. Phase C — Update frequency characterization

Gate 1AとGate 1Bを人間がpassと記録した後だけ実施する。brightnessは`ZERO`と`LOW`の間、各sessionは2秒に限定する。update rateとtransition semanticsは未確認のresidual riskとして記録する。

Gate 1では **10 Hz → 20 Hz → 25 Hz** の順に確認する。各rateは独立sessionとして実行し、次へ自動移行しない。50 HzはこのprobeとGate 1 acceptanceの対象外であり、実行しない。

各rateで次を記録する。

* requested interval、actual monotonic timestamp、commit duration
* successful/false/exception count
* skipped/coalesced update count
* flicker、stutter、lag、eyes/power LEDへの影響
* audioなしの状態でnative voice-syncが割り込むか
* final zero、restore、unlock、disconnectの成否

false、exception、unbounded latency、queue growth、目視可能な不安定、cleanup failureが一度でもあれば停止し、rateを上げない。

## 9. Phase D — Native voice-sync interaction

このphaseはGate 1Aを人間がpassと記録した後だけ実行する。enable／disable semanticsが未確認であること自体をmanual observationの対象とする。

| Case | Audio | Native sync target | Direct mouth update | Expected | Observed |
|---|---|---|---|---|---|
| D1 | off | enabled | none | vendor既定状態 | |
| D2 | off | disabled | LOW then ZERO | direct updateだけが反映 | |
| D3 | short/low-volume | enabled | none | native syncだけが反映 | |
| D4 | short/low-volume | disabled | LOW/ZERO | native syncがdirect updateを上書きしない | |
| D5 | stopped | restored | none | 設定したpost-test状態 | |

audio試験は別の明示的operator opt-inを必要とする。短い、低音量のcanonical PCMだけをmemoryから再生し、一時file、`aplay`、global process killを使用しない。左右channel、sample rate、sample size、mixer/deviceの対応は先に確認する。

current-state getterが公開されていないため、元々disabledだったかは判別できない。probeがdisableを試みた場合だけconfigured enableをcleanupで試み、これを未知の元状態の復元とは記録しない。failure時は再試行loopやservice停止を行わず、安全手順へ移行する。

## 10. Phase E — LED ownership semantics

このphaseはguarded Manual Gate 1の合否から分離したfuture gateである。exact LED対象ID、key規約、安全なrecoveryが確認できるまで実施しない。異常終了試験とcross-process試験はこの基本runbookに含めない。

1. owner hardware workerでkey付きlockを取得する。
2. 同一owner、同一keyの一回の`play`が成功するか確認する。
3. 別workerから同じ対象へ操作を試す必要がある場合は、VSTONEが安全性と期待returnを明示した専用試験だけを使う。
4. release後に、承認済みの新sessionが取得できるか確認する。
5. repeated acquire/release、wrong key、overlap IDは公式期待値がない限り試さない。

この結果をcross-process mutexの保証へ一般化しない。whole-robot advisory process lockは常に別に保持する。

## 11. Phase F — AudioOutput and PlaybackClock

mouth試験から独立して先に確認できるが、実audio出力の別opt-inが必要である。

1. supported formatの短い低音量PCMをmemory上の`AudioInputStream`へ構成する。
2. `CWavePlayer`をsession-owned threadで開始し、`getLine()`が利用可能になる時点を記録する。
3. `SourceDataLine.getLongFramePosition()`と`getMicrosecondPosition()`を低頻度でsampleし、単調性、granularity、最終値、buffer latencyを記録する。
4. normal completionでrun return、line state、resource closeを確認する。
5. 新しいsessionで一回だけ`stop()`を呼び、blocking解除、flush/close、再呼出し安全性を段階的に確認する。
6. replacementは旧sessionのstop/close完了後にだけ開始し、二つのlineが同時に所有されないことを確認する。

`isUsed()`の意味を推測してcompletion判定に使わない。lineのownershipが確認できない場合はadapterから直接`close()`せず、VSTONEへ問い合わせる。

## 12. Integrated lip-sync candidate

Phase B/C/D/Fが個別にpassした後だけ、次の順序を候補とする。

```text
validate/decode short PCM
-> acquire confirmed LED ownership
-> disable native voice-sync
-> start playback
-> sample SourceDataLine playhead
-> choose current envelope value
-> coalesce latest mouth target
-> ZERO
-> stop/close playback
-> restore configured native voice-sync state
-> release LED ownership
-> disconnect
```

最初は10 Hz、`ZERO`～`LOW`、短い音声とし、adequateでなければreview後に20 Hzへ上げる。stop、normal completion、replacementは別sessionで一つずつ確認する。motion、servo、torqueとの同時試験はSota acceptanceの最初の範囲に含めない。

## 13. Cleanup and recovery

normal、false return、exception、operator stopの全経路で次をbest effortで試み、各結果を別々に記録する。一つのfailureで残りのcleanupを省略しない。

1. future update generationを無効化する
2. periodic producerとpending mailboxを停止・clearする
3. mouth `ZERO`を、guardがまだ有効でservo movementもunexpected servo soundも報告されていない場合だけ、`Cleanup mouth zero — not part of LED-lock diagnostic measurement`として一回commitする。LED lock保持中はlocked/current ID集合を再確認し、unlock前に同じkeyで行う
4. guarded probeがowned LED lockを保持していれば、保存したkey／ID cloneでreleaseする
5. owned audio playbackをstopし、owned resourceをcloseする
6. configured native voice-sync targetをrestoreする
7. guarded probeではowned all-default-servo guard、future production gateではその他のowned lockをreleaseする
8. `CRobotMem.Disconnect()`を行う
9. process lockをreleaseする。lock pathnameをunlinkしない
10. thread/process/resource残存とrobot状態をoperatorが確認する

cleanup順序はmanual結果により変更し得る。VSTONEへの追加問い合わせは任意のrisk-reduction手段であり、Gate 1 probe実行の必須解除条件ではない。現在状態をqueryできないため、voice-syncの「復元」はpreflightで明示したconfigured targetへの設定を意味し、未知の元状態を復元したとは表現しない。

二回以上のmanual runで、servo guard releaseと`CRobotMem.Disconnect()`の後、VSTONE library shutdown hookが`CRobotMotion.ServoOff(...)`を試み、disconnected socketへのwrite failure／`NullPointerException`／`Cmd Send Error`が観測された。probe sourceは`ServoOn()`／`ServoOff()`を明示的に呼んでいない。観測結果はvendor runtimeのshutdown時write attemptであり、ServoOffが実機へ成功したとは記録しない。cleanup順序は現revisionで変更せず、probeからServoOff／ServoOnを追加せず、reflectionやprivate APIでshutdown hookを変更しない。

A post-cleanup vendor shutdown-hook exception may appear after `Disconnect()`. Record the full stack trace separately from the selected Gate 1 operation and do not treat it as evidence of a successful cleanup or hardware state transition.

### Abnormal termination candidate

process crash、`SIGKILL`相当、電源断、JVM abortを使う試験は、LED/voice-sync/lock/audio状態が残留する可能性があるため本runbookでは **NOT APPROVED** とする。VSTONEが安全なrecovery、予想状態、監視者、rollbackを提示し、別の危険分析済みrunbookが承認された場合だけ人間が実施する。

## 14. Evidence record

一つのtest caseにつき次を保存する。raw evidenceの保存先、機密性、Git追跡可否は事前に決める。

次の欄をcopyし、人間が実測結果だけを記入する。Gate 1A-0、option 3、Gate 1A-1、Gate 1Bの既存観測を保持し、Gate 1Lを新しい追補として記録する。

```text
Date:
Operator:
Robot model:
Edison Java version:
VSTONE runtime:
sotalib.jar path:
sotalib.jar SHA-256:
sotalib.jar provenance:

Test: Gate 1A-0 / option 3 / Gate 1A-1 / Gate 1B / Gate 1L / cleanup
Expected:
Observed:
PASS / FAIL / BLOCKED:
Notes:
```

詳細な再現性情報は次のschemaへ記録する。

```text
test_id:
date_time_timezone:
operator:
safety_observer:
reviewer:
robot_model_asset_serial:
os_edison_image:
java_version:
vendor_jar_name_version_sha256_source_license:
source_revision_artifact_sha256_config_sha256:
public_api_case:
preconditions:
exact_steps_approved:
expected_result:
observed_result:
return_values_exceptions:
monotonic_timestamps_latency:
servo_torque_led_audio_observation:
cleanup_zero_audio_restore_unlock_disconnect:
unexpected_effect:
pass_fail_blocked:
follow_up_question:
evidence_files_and_sha256:
```

観測していないphysical motion、torque、LED、audio状態を推測で補完しない。失敗したcaseも削除または上書きせず、追補として残す。

## 15. Acceptance gates

production adapter実装へ進む最低gateは次のとおりである。

* exact official JAR provenance/version/SHA/licenseが承認されている
* public signaturesがinstalled JARと一致する
* Sota mouth controlがCase AまたはCase Bとして一意に決まる
* brightness範囲、commit、rate、他LED保持が確認される
* voice-syncの開始状態、disable、restore、failure方針が決まる
* lock対象、owner、key、release、process lockとの境界が決まる
* audio format、stop、completion、line ownership、playhead精度が確認される
* normal/error cleanupがoperator観測を含めてpassする
* 未確認項目がcapabilityとして成功扱いされない

Gate 1A-0とGate 1A-1／1Bのservo safety観測だけではGate 1全体は未完了である。Gate 1A-1とGate 1Bのいずれでもmouth／eyes／power visible changeがなく、Gate 1LはNOT EXECUTEDであるため、VSTONE LED control、native voice-sync coordination、real audio output、running motion stop、Dog adapterをproduction-readyと表現しない。
