# VSTONE公開API manual acceptance runbook

## 1. Status、目的、実行権限

**Status: DRAFT / NOT EXECUTED / HUMAN-ONLY**

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
* API surface、LED ID、brightness範囲、lock対象IDが推測に依存する
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
* `CRobotMotion.LockLEDHandle(...)`、`UnLockLEDHandle(...)`、key付き`play(...)`
* `CSotaMotion.disabeMouthLEDVoiceSync()`、`enabeMouthLEDVoiceSync()`
* `CRobotPose.setLED_Sota(...)`、`SetLed(...)`
* `CWavePlayer(AudioInputStream)`、`stop()`、`getLine()`

signature不一致が一つでもあればwrite testへ進まず、installed versionと公式資料の不一致として記録する。

## 5. Manual Gate 1 — Mouth LED / native voice-sync / LED ownership

最初のmanual acceptanceはこのGate 1だけに限定する。servo motion、torque変更、full RobotController deployment、production adapter、motionとの同時実行、Dog／CommUを含めない。Phase Aの最小initializationを通過した後、次の1A～1Dを一つずつ人間が開始する。

### Gate 1A — Mouth brightness

`setLED_Sota(...)`と`play(...)`の公開APIだけを使用し、次を確認する。

* mouth brightnessが変化する。
* `ZERO`へ戻せる。
* `LOW`から承認済みの複数段階で目視差を記録できる。
* eyes／power LEDのbefore/afterと副作用を記録できる。
* servo、torque、audioに予期しない変化がない。

### Gate 1B — Native voice-sync

exact vendor spellingの`disabeMouthLEDVoiceSync()`が機能し、disable中のmanual mouth updateがnative側から上書きされないことを確認する。最後に`enabeMouthLEDVoiceSync()`でpreflightに定めたconfigured targetへ戻せることを確認する。current-state getterがないため、未知の元状態を復元したとは記録しない。

### Gate 1C — Update rate

`ZERO`～`LOW`の範囲で **10 Hz → 20 Hz → 25 Hz** を独立sessionとして確認する。50 Hzは25 Hzで要求を満たせず、安全性と必要性をreviewerが承認した場合だけ候補にする。高頻度探索を目的にせず、queue lag、commit latency、flicker、他LED stateを記録する。

### Gate 1D — Cleanup and ownership

normal completion、operator stop、一つの承認済みerror caseで、mouth `ZERO`、configured voice-sync restore attempt、owned LED lock release、audio/resource close、`Disconnect()`を個別に確認する。exact Sota LED lock対象が公式確認できない場合はownership testを推測で実行せず、Gate 1をBLOCKEDとする。

### Gate 1 pass / fail criteria

Gate 1全体のminimum passは次のすべてを満たすことである。

* mouth brightnessを公開APIだけで制御でき、`ZERO`へ戻せる。
* native voice-sync disable中にapplication updateを維持でき、configured targetへrestoreできる。
* eyes／power LED stateを破壊しないfull-state coordination方式を設計できる観測結果がある。
* 10～25 Hzのうち必要なmouth update rateで、明白なqueue lag、unbounded latency、flicker、exceptionがない。
* ownership対象が公式確認済みで、取得したownershipをreleaseできる。
* normal／stop／approved error pathのresource closeが確認できる。

一項目でも満たせない、観測不能、または公式根拠不足ならFAILまたはBLOCKEDとし、VSTONE production adapter実装を開始しない。Case A、Case Bの変更、vendor問い合わせ、requirements変更のいずれが必要かを別reviewで決める。

## 6. Phase A — Initialization and read-only observation

1. 承認済みprocess lockが取得済みであることを再確認する。
2. `CRobotMem`を構築し、`Connect()`のreturn、elapsed time、exceptionを記録する。
3. `CSotaMotion`を構築し、`InitRobot_Sota()`のreturn、elapsed time、exceptionを記録する。
4. initialization前後で、servo motion、torque、eyes、mouth、power LED、audioに変化がないことをoperatorが観測する。
5. `getDefaultIDs()`と`getReadpos()`を一度だけ取得し、配列長、ID順、return/exceptionだけを記録する。値をdegreeへ変換せず、可動域を推測しない。
6. `Disconnect()`を行い、process lockを承認済み順序でreleaseする。
7. resource、thread、processが残っていないことを確認する。

予期しない状態変化があれば以降を中止する。`InitRobot_Sota()`が無副作用であると、この一回の観測だけから一般化しない。

## 7. Phase B — Mouth control primitive

このphaseは、VSTONEが公式に次を確認した場合だけ実行する。

* 採用する方式が、mouth-only `SetLed`かfull `setLED_Sota`か
* mouth-only方式の場合はexact public LED ID
* brightnessの厳密な最小値、最大値、許容型、範囲外時の挙動
* `play`のtransition値と、未指定servo/LED保持semantics
* lock対象IDとkeyの要件

### 7.1 Test values

確認済み範囲を`MIN`から`MAX`とし、次のsymbolic levelをoperatorが数値へ変換してrecordへ固定する。

| Symbol | Numeric value | 根拠 |
|---|---:|---|
| ZERO | | 公式仕様上の消灯値 |
| LOW | | 範囲内の保守的な低輝度 |
| MEDIUM | | 範囲内の中間値 |
| HIGH | | MAX未満の値 |
| MAX | | 公式仕様上の最大値 |

公式sampleはmouthに255を「Max」として使用するが、installed JARの0..255全域を確認するまでは自動的に`MAX=255`、`ZERO=0`と確定しない。

### 7.2 Single-update sequence

各stepの間にoperator pauseを置き、自動loopにしない。

1. baselineのeyes、mouth、power LED、native voice-sync、audio状態を記録する。
2. exact対象IDが確認済みの場合だけLED lockを一回取得し、boolean resultを記録する。失敗時は状態を変えず終了する。
3. native voice-syncを一回disableし、return/exceptionと観測を記録する。
4. `ZERO`を一回commitし、mouth以外のLED、servo、torque、audioに変化がないことを確認する。
5. `LOW`を短時間だけ一回commitし、期待値、観測輝度、他状態への影響を記録する。
6. `ZERO`へ戻す。
7. 問題がない場合だけ`MEDIUM`、`HIGH`、`MAX`を一つずつ同じ手順で確認する。眩しさ、発熱、flickerがあれば上位levelへ進まない。
8. 最後に`ZERO`をcommitする。
9. 試験前状態の定義に従ってnative voice-syncをrestoreする。getterがない場合は「元状態へ復元」と断定せず、設定した目標状態とoperator観測を記録する。
10. lockを一回releaseし、`Disconnect()`、process lock releaseを行う。

eyesまたはpower LEDが変化した場合はCase Bのstate coordination不足として不合格にし、部分updateを推測で試さない。

## 8. Phase C — Update frequency characterization

Phase Bが全てpassし、VSTONEがupdate rateとtransition semanticsを確認した後だけ実施する。brightnessは`ZERO`と`LOW`の間に限定し、短い固定windowを使う。

Gate 1では **10 Hz → 20 Hz → 25 Hz** の順に確認する。各rateは独立sessionとして実行し、次へ自動移行しない。50 Hzは25 Hzで要求を満たせず、安全性と必要性をreviewerが承認した場合だけ別の追加caseとして実行する。

各rateで次を記録する。

* requested interval、actual monotonic timestamp、commit duration
* successful/false/exception count
* skipped/coalesced update count
* flicker、stutter、lag、eyes/power LEDへの影響
* audioなしの状態でnative voice-syncが割り込むか
* final zero、restore、unlock、disconnectの成否

false、exception、unbounded latency、queue growth、目視可能な不安定、cleanup failureが一度でもあれば停止し、rateを上げない。50 Hzをdefaultに採用する根拠にはしない。

## 9. Phase D — Native voice-sync interaction

このphaseはVSTONEからenable/disable semanticsと試験方法が確認できた後だけ実行する。

| Case | Audio | Native sync target | Direct mouth update | Expected | Observed |
|---|---|---|---|---|---|
| D1 | off | enabled | none | vendor既定状態 | |
| D2 | off | disabled | LOW then ZERO | direct updateだけが反映 | |
| D3 | short/low-volume | enabled | none | native syncだけが反映 | |
| D4 | short/low-volume | disabled | LOW/ZERO | native syncがdirect updateを上書きしない | |
| D5 | stopped | restored | none | 設定したpost-test状態 | |

audio試験は別の明示的operator opt-inを必要とする。短い、低音量のcanonical PCMだけをmemoryから再生し、一時file、`aplay`、global process killを使用しない。左右channel、sample rate、sample size、mixer/deviceの対応は先に確認する。

current-state getterが公開されていないため、test開始時のnative sync状態が不明ならD1以降を実行しない。restore failure時は再試行loopやservice停止をせず、VSTONE承認済みrecoveryへ移行する。

## 10. Phase E — LED ownership semantics

exact対象ID、key規約、安全なrecoveryが公式に確認された場合だけ実施する。異常終了試験とcross-process試験はこの基本runbookに含めない。

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
3. mouth `ZERO`を、所有権がまだ有効な場合だけ一回commitする
4. owned audio playbackをstopし、owned resourceをcloseする
5. configured native voice-sync targetをrestoreする
6. owned LED lockをreleaseする
7. `CRobotMem.Disconnect()`を行う
8. process lockをreleaseする。lock pathnameをunlinkしない
9. thread/process/resource残存とrobot状態をoperatorが確認する

cleanup順序はmanual結果とVSTONE回答により変更し得る。現在状態をqueryできないため、voice-syncの「復元」はpreflightで明示したconfigured targetへの設定を意味し、未知の元状態を復元したとは表現しない。

### Abnormal termination candidate

process crash、`SIGKILL`相当、電源断、JVM abortを使う試験は、LED/voice-sync/lock/audio状態が残留する可能性があるため本runbookでは **NOT APPROVED** とする。VSTONEが安全なrecovery、予想状態、監視者、rollbackを提示し、別の危険分析済みrunbookが承認された場合だけ人間が実施する。

## 14. Evidence record

一つのtest caseにつき次を保存する。raw evidenceの保存先、機密性、Git追跡可否は事前に決める。

Gate 1開始時は次の欄を空欄のままcopyし、人間が実測結果だけを記入する。本checkpointでは結果を記入しない。

```text
Date:
Operator:
Robot model:
Edison Java version:
VSTONE runtime:
sotalib.jar path:
sotalib.jar SHA-256:
sotalib.jar provenance:

Test: Gate 1A / 1B / 1C / 1D
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

このrunbookが未実行である間、VSTONE mouth LED、native voice-sync、real audio output、running motion stop、Dog adapterをproduction-readyと表現しない。
