# AGENTS.md

## 1. この文書の目的

このファイルは、Codexを含む自動コーディングエージェントが本リポジトリを変更する際に、常に従うべき開発原則を定める。

本プロジェクトの目的は、既存のJava版RobotControllerとの正常系通信互換性を維持しながら、安全性、保守性、テスト可能性を高めた新しいJava版RobotControllerを再実装することである。

新実装は、Windows上のモック環境で実機なしに検証でき、最終的にIntel Edison上のJava 8で動作し、Sota、CommU、DogをVSTONE公式Java APIの公開範囲内で制御する。

既存Java版はlegacy reference implementationおよびfallbackとして保存する。既存Python版の設計、テスト、evidenceは、仕様参照、test oracle、historical recordとして保存するが、最終的なproduction serverとはしない。

## 2. 参照すべき情報源

判断に迷った場合は、次の優先順位で参照すること。

1. 本リポジトリの `AGENTS.md`
2. `docs/decisions/adr-java-only-redesign.md`
3. `docs/plans/java-redesign-migration-plan.md`
4. `docs/requirements.md`
5. `docs/architecture.md`
6. `docs/protocol-compatibility.md`
7. `docs/evidence/java-current-architecture-inventory.md`
8. 新Java実装のsourceおよびtest（原則として `java_server/` 以下）
9. 既存Java版RobotController実装（legacy reference implementation）
10. `RobotController_TCP_Server_Documentation_ja.md`
11. 既存Python実装、test、evidence（仕様参照、test oracle、historical record）
12. `social-robotics-lab/robo-tutorial` その他の既存クライアント実装
13. VSTONE公式JavaDoc、公式sample repository、公式取扱説明書
14. 非公式の低レベル実装や外部資料

参照時には、次の区別を厳守する。

* Codexへの個別作業指示はrepository外から与える一時的な実行入力であり、参照文書としてrepositoryへ保存しない。
* 明示的な方針変更がない限り、prompt、作業依頼文、会話logまたはその要約をrepositoryへ追加してはならない。
* 恒久的な決定だけをADR、requirements、architecture、planまたはevidenceへ反映する。
* `docs/decisions/adr-java-only-redesign.md`は、Javaオンリー再実装を採用した設計判断の基準文書である。
* `docs/plans/java-redesign-migration-plan.md`は、現在有効な段階的移行計画である。
* `docs/requirements.md`、`docs/architecture.md`、`docs/protocol-compatibility.md`にPython production serverを最終成果物とする記述が残っている場合、その部分はJavaオンリー方針への更新が完了するまで暫定的な旧記述として扱う。
* ADRと新移行計画に反する旧記述を優先してはならない。
* `docs/migration-plan.md`はPython全面移植を前提としたhistorical documentであり、現在の実装計画として使用しない。
* `docs/evidence/`以下の文書は、作成時点の観測・調査結果を記録したevidenceである。現在の設計方針に合わせて過去の事実を書き換えてはならない。
* 既存Java版は通信互換性、robot profile、VSTONE API使用例の参照元であるが、そのstartup、stop、thread、queue、validation、exception handling等の危険な挙動を新実装へそのまま継承してはならない。
* 既存Python版はproduction implementationではない。protocol、validation、scheduler、generation／cancel、process lock、Mock backend、口LED調査等の参照実装およびtest oracleとして利用する。
* VSTONEハードウェア制御については、公式JavaDoc、公式sample、公式取扱説明書などの公開資料を、非公式資料や推測より優先する。
* `sotalib.jar`の逆コンパイル、bytecode disassembly、private implementation抽出、内部memory addressやwrite sequenceの推測を行ってはならない。

文書、source、test、実機観測に不一致がある場合は、独断で仕様を変更せず、不一致、影響範囲、確認に必要な追加作業を報告すること。

## 3. 変更範囲

### 3.1 新Java実装

* 新しいproduction Java codeは原則として `java_server/` 以下に配置する。
* `java_server/`はJava 8、Maven、JUnitを前提とした独立したbuildおよびtest単位とする。
* 新Java実装は、protocol、application service、scheduler、hardware backend、audio subsystemを責務ごとに分離する。
* Windows上のdefault buildおよびtestは、VSTONE実機、Intel Edison、ALSA device、AppManager、VSMDを必要としてはならない。
* 実機依存実装は明示的なadapterまたはprofileへ隔離する。

### 3.2 既存Java版

* repository直下の既存 `src/`、Eclipse project metadata、既存build手順は、legacy reference implementationとして扱う。
* 明示的な指示がない限り、既存Javaコードを変更しない。
* 既存Javaコードを、新Java実装の内部構造の雛形として無批判にcopyしない。
* 既存Java版の不具合、例外、競合、hang、unbounded queue、unbounded thread生成、危険なstartup副作用を意図的に再現しない。
* 正常な既存クライアントとの通信互換性は維持する。

### 3.3 既存Python版

* `python_server/`は、仕様参照、test oracle、historical implementationとして保存する。
* 明示的な指示がない限り、Python版へ新しいproduction機能を追加しない。
* Python版の低レベルhardware実装を、新Java版へそのまま移植しない。
* Python版を変更する場合に限り、第7.2節、第8.3節、第9.4節のPython互換規則を適用する。

### 3.4 文書

* 現在有効な設計判断は `docs/decisions/` に記録する。
* 現在有効な移行計画は `docs/plans/` に記録する。
* 調査時点の事実や実機観測は `docs/evidence/` に記録する。
* historical documentを現在の設計に合わせて書き換えず、必要に応じてsuperseded注記と現行文書へのlinkを追加する。
* Codexへの個別指示書をrepositoryへ追加しない。

### 3.5 ローカル専用evidence

* `.local-evidence/`はGit追跡対象外のローカル専用保存領域である。
* Codexを含む自動エージェントは、タスクで明示的にexact pathを指定された場合を除き、`.local-evidence/`を列挙、検索、読み取り、変更、移動、削除してはならない。
* 通常のrepository調査では、`.local-evidence/`を探索対象から除外する。
* `.local-evidence/`の内容をsource、test、設計仕様の正とみなしてはならない。
* `.local-evidence/`内のfileをstage、commit、pushしてはならない。

### 3.6 Git操作

* `git add .`および`git add -A`を使用しない。
* stageするfileはpathを明示する。
* `git clean -f`、`git clean -fd`、`git reset --hard`を使用しない。
* 未追跡fileを独断で削除しない。
* branch変更、commit、push、pull request作成は、ユーザーから明示的な依頼がある場合だけ行う。
* `robot_controller_edison_smoke.sha256`を変更、stage、commit、push、削除してはならない。
* `robot_controller_edison_smoke.sha256`の期待SHA-256は次である。

```text
0BF02AF8A83777B4F033C26A481A05C563726D8960F80AC24778F26CAD55CE59
```

## 4. 実装方針

### 4.1 ハードウェア抽象化

* TCP server、protocol処理、validation、application service、motion scheduling、audio playbackと、実機device accessを分離する。
* すべてのロボット制御は共通のbackend interfaceを介して行う。
* Sota、CommU、Dogは個別のbackendまたはrobot profileとして実装する。
* 将来のrobot追加時に、TCP serverやcommand decoderを変更せず追加できる構造にする。
* Windows上の開発とtestでは、必ずMock backendを使用する。
* network thread、audio thread、scheduler threadからVSTONE APIを直接呼び出さない。
* VSTONE API呼び出しを行えるpackageまたはmoduleを明確に限定する。

### 4.2 通信互換性

legacy protocol v1について、次を維持する。

* 4 byteのbig-endian長さheader
* 正常系で有効な長さは `0 <= length <= min(command-specific configured limit, 2147483647)`
* `0x80000000`以上の値は、既存Java版では負数になるため拒否する
* Frame Codecは長さ0をempty payloadとしてdecodeし、必要な拒否はcommand layerで行う
* Frame Codecは固定最大値を内部に持たず、呼び出し側からcommand-specific maximumを受け取る
* headerに続く指定byte数のdata本体
* command名を第1 frameとして送信
* 必要なcommandではpayloadを第2 frameとして送信
* 原則として1 connection 1 command
* `read_axes`のみ正常時にresponse frameを返す
* 既存clientがresponseを読まないcommandには、v1ではACKを追加しない

構造化された成功・error responseは、後方互換なprotocol v2として別途設計する。

本プロジェクトで通信互換性があるとは、正常な既存clientが送るbyte列を受理し、同じcommand効果を発生させ、v1では `read_axes` だけがresponseを返すことをいう。

次は互換性の対象外とする。

* 処理timingの完全一致
* JSON key順序
* JSON空白
* 不正入力時の旧Java固有挙動
* 旧Java版のcrash、hang、race
* Javaの暗黙的な数値変換
* 旧実装のunsafe startupまたはunsafe stop behavior

### 4.3 入力検証

以下を必ず検証する。

* frame長
* command名の長さとUTF-8妥当性
* JSONの構文とtop-level型
* 必須field
* 数値の型、有限性、範囲
* servo名とLED名
* servo角度とLED値の範囲
* `Msec`、`Pause`、`Speed`の範囲
* motion要素数
* WAV dataの総size
* WAV container、codec、channel数、sample rate、sample size、frame alignment
* decode後PCM size
* queue長
* connection数
* timeout値
* audio session数
* mouth LED更新周期とbrightness範囲

不正入力を暗黙変換、切り捨て、clamp、または推測によって受理しない。clampを行う場合は、文書化された仕様と明示的なtestが必要である。

### 4.4 同時実行、queue、cancel

* Pose、Motion、Idle Motion、audio連動LEDが競合してhardwareへ指令を送らないようにする。
* TCP connection処理には、上限付き `ExecutorService` と上限付きqueueを使用する。
* `Executors.newCachedThreadPool()`を使用しない。
* hardware操作をnetwork threadから直接行わない。
* hardware accessは、所有権と順序を明確にした単一hardware workerまたは同等のserialized dispatcherへ渡す。
* queueは必ずboundedとし、overflow policyを明示する。
* 停止commandは冪等にする。
* 開始前、停止済み、完了済みの機能へ停止commandを送っても未処理例外を発生させない。
* Pose、Motion、Idle Motion、audio sessionにはgeneration IDまたはcancel tokenを割り当てる。
* 停止または置換された古いgenerationは、その後hardware commandやLED更新を送信できない設計にする。
* stop時はproducerのinterruptだけで完了とせず、queued command、実行中operation、hardware state、resource cleanupを扱う。
* thread interruptionを無視しない。interrupt statusの扱いを文書化し、必要に応じて復元する。
* 口LEDの周期更新は通常のFIFOへ蓄積せず、最新値だけを保持するcoalescing mailboxまたは同等の仕組みを使用する。

### 4.5 lifecycleと起動状態

起動状態名は `starting`、`initializing`、`ready`、`degraded`、`stopping`、`stopped`、`failed` に統一する。

* backend初期化が成功して `ready` へ遷移してからTCP listenを開始する。
* `ready` 前にrobot commandを実行できる経路を作らない。
* object constructionまたはclass loadingだけで実機I/Oを実行しない。
* startup時に無条件でServoOn、initial pose、torque設定、LED点灯、音声再生を行わない。
* shutdown hookだけにcleanupを依存せず、application serviceから明示的に停止可能にする。
* resource closeは冪等にする。
* initialization failure時に部分的に取得したresourceを解放する。
* `System.exit()`をlibraryまたは下位layerから呼び出さない。

### 4.6 VSTONE Java APIとSota coordination

* production hardware controlには、VSTONE公式Java APIの公開classおよび公開methodを優先して使用する。
* private member、reflection、bytecode解析、内部memory layoutの推測に依存しない。
* `CRobotMem`、`CRobotMotion`、`CSotaMotion`、`CRobotPose`等のvendor objectはVSTONE adapterの外へ公開しない。
* servo ID、LED ID、axis順序は、公式資料、公式API、検証済みrobot profileのいずれかで根拠を示す。
* read positionの配列順序を独自に仮定せず、公式APIで取得可能なID順序と対応付ける。
* 補間完了は単純な `Thread.sleep(duration)`だけで断定せず、公開APIで利用可能な完了状態または待機methodを評価する。
* LEDまたはservo handle lockを使用する場合は、lock key、取得範囲、release順序、failure cleanupを明示する。
* vendor APIのhandle lockをcross-process mutexとみなさない。
* 複数processによるwriteを防ぐ必要がある場合は、OS-level advisory lockを別の責務として設計する。
* process lock競合時はfail-closedとし、競合回避のためにservice停止、lock file削除、無制限retryを行わない。
* low-level AppManager／VSMD direct writeは新Java production実装のdefault pathとしない。
* 公式Java APIだけでは安全要件を満たせない場合は、実装を進めず、制約、代替案、VSTONEへの確認事項をADRまたはissueとして報告する。

### 4.7 音声再生と口LED

* production音声再生で`aplay`、`killall`、固定名一時WAV fileを使用しない。
* WAV payloadはmemory上で検証し、decode後のcanonical PCMをJava audio outputへ渡す。
* audio outputはinterfaceで抽象化し、Java Soundの `SourceDataLine` またはVSTONE公開Java APIを使用するadapterを実装可能にする。
* default Windows testでは実audio deviceを開かず、Mockまたはbuffering fakeを使用する。
* 音声再生と口LED animationは同一のaudio session lifecycleで管理する。
* 口LED envelopeは、実際に再生するものと同じcanonical PCMから生成する。
* envelope計算はwindowed RMSまたは文書化された同等手法を使用する。
* noise gate、dynamic range mapping、attack、release、minimum update intervalを設定可能かつtest可能にする。
* LED同期は、可能な限りaudio deviceの再生済みframe位置またはplayheadを基準にする。
* wall-clock上のthread開始時刻だけで同期を断定しない。
* 音声終了、停止、置換、decode error、audio device error、LED errorのすべてでcleanupを試みる。
* cleanupでは、口LEDをsafe zeroへ戻し、mouth voice syncを復元し、所有しているLED lockを解放する。
* 古いaudio generationが新しいsessionの口LEDを更新できないようにする。
* 実機確認前は、mouth voice-sync API、LED lock、継続的なlip-sync動作を `unverified` と扱う。
* Python版で確認済みの低レベル口LED経路はhistorical evidenceであり、新Java実装へ直接転記しない。

## 5. 安全に関する禁止事項

Codexを含む自動エージェントは、許可の有無にかかわらず、実機device、`systemctl`、servo、LED、torque、audio outputを操作してはならない。

以下は絶対的な禁止事項である。

* `/dev/i2c-1`への書き込み
* `/dev/ttyMFD1`への書き込み
* その他の実機device fileへの書き込み
* `systemctl stop vsmd_edison`
* `systemctl disable vsmd_edison`
* servoのON・OFF
* servo位置指令
* torque変更
* LED点灯指令
* 実機speakerからの音声再生
* `killall`や無差別なprocess終了
* 実機上の設定fileの変更
* 実機への自動deploy
* 実機上での自動test
* process lock競合を回避する目的でのservice、AppManager、`vsmd_edison`の停止
* `/run/lock/robot-controller-sota.lock`の手動unlink
* VSTONE vendor JARの逆コンパイルまたはdisassembly
* 実機device、AppManager、VSMDへのwriteを含むdiagnosticの自動実行

実機用codeを作成する場合も、エージェントは実行しない。エージェントが手順、期待結果、停止条件、記録様式を作成し、人間が内容を確認して手動実行すること。

operatorによる観測記録がないphysical motion、torque、LED、audio状態を推測または断定しない。

## 6. サーボ安全要件

* 未確認のservo ID、変換比、initial position、可動範囲を推測しない。
* robot種別ごとに検証済みのservo profileを使用する。
* 実機試験では、最初にread-onlyの角度取得を確認する。
* 動作試験は1 axis、小さい変位、低速、短時間から開始する。
* 範囲外値をclampするか拒否するかは文書化された仕様に従う。
* 不明な場合は拒否し、logへ記録する。
* process異常終了時に無条件でtorqueを切らない。機体の転倒や落下を考慮する。
* stop、disconnect、timeout時の安全状態をrobot種別ごとに定義する。
* Mock testの成功を実機安全性の証明とみなさない。

## 7. コード品質

### 7.1 Java production code

* production sourceはJava 8でcompileおよび実行できるようにする。
* Maven compiler設定でsourceおよびtargetを明示し、Java 9以降のlanguage featureまたはAPIを使用しない。
* package間の依存方向を明確にし、protocol layerからhardware adapterへ直接依存しない。
* domain modelおよびvalidated commandは、可能な限りimmutableにする。
* public APIにはJavadocを付ける。
* 複雑なlifecycle、concurrency、protocol boundaryには設計意図を説明するcommentを付ける。
* class名、method名、exception名は責務が分かるものにする。
* static mutable global stateを避ける。
* singletonへhardware resource、queue、session stateを隠さない。
* resourceは `AutoCloseable`、`Closeable`、try-with-resources、または明示的な冪等 `close()`で管理する。
* finalizerにresource解放を依存しない。
* `System.exit()`を下位layerから呼び出さない。
* exceptionを握りつぶさない。
* vendor exception、I/O exception、validation errorを、意味のあるapplication exceptionへ変換する。
* error logに秘密情報、音声payload、巨大なbinary dumpを出力しない。
* charsetを省略せず、protocol文字列には明示的にUTF-8を使用する。
* byte orderを省略せず、legacy frameではbig-endianを明示する。
* 経過時間には `System.nanoTime()`または注入したmonotonic clockを使用する。
* wall-clock時刻と経過時間を混同しない。
* testで長い実時間sleepを使用しない。
* clock、scheduler、audio playhead、executor、backendを注入可能にする。
* thread、executor、socket、audio line、vendor handleの所有者を明確にする。
* compiler warningを無視せず、追加したwarningの理由を報告する。
* reflectionによるprivate accessやunsupported internal APIを使用しない。

### 7.2 Python reference code

`python_server/`を明示的に変更する場合だけ、次を適用する。

* production相当の既存Python codeはCPython 3.6.15でsyntax parseおよび実行できる状態を維持する。
* Python codeには既存方針に沿ったtype hintを付ける。
* `from __future__ import annotations`、built-in generic、`X | None`、標準libraryの `dataclasses`、`typing.Protocol`、`asyncio.run()`を使用しない。
* Python 3.7以降で追加されたsyntaxまたは標準library APIを導入しない。
* public class、public function、複雑な処理にはdocstringを付ける。
* Python側へ新しいproduction hardware pathを追加しない。
* Java再実装に不要なPython refactorを行わない。

## 8. 依存関係とbuild

### 8.1 Java runtimeとMaven

* Intel Edison上のproduction runtimeはJava 8とする。
* 新Java実装のbuild entry pointは原則として `java_server/pom.xml` とする。
* Maven Wrapperを導入する場合は、追加理由、対応Java version、配布物、licenseを確認する。
* dependency versionは明示的に固定する。
* snapshot dependency、無制限version range、動的versionを使用しない。
* compile dependency、runtime dependency、test dependencyを分離する。
* Windows上のdefault `mvn test`および `mvn verify`は実機hardwareを必要としてはならない。
* test時にnetwork、audio device、AppManager、VSMDへ暗黙接続しない。
* build時にrepository外の個人directoryやabsolute pathへ依存しない。
* reproducibleなcommand-line buildを提供し、Eclipseのmanual exportだけに依存しない。

### 8.2 Java dependency追加時の確認事項

新しいJava dependencyを追加する場合は、次を確認して報告する。

* Java 8対応
* Intel Edison／Yocto環境での利用可能性
* pure Javaかnative libraryを必要とするか
* transitive dependency
* artifact size
* license
* maintenance状態
* security上の既知問題
* 標準libraryで代替できない理由
* Mock testとproduction runtimeの両方への影響

VSTONE vendor JARについては、次を守る。

* 公式配布物だけを使用する。
* provenance、version、SHA-256、license、配布可否を記録する。
* licenseが不明なJARをpublic repositoryへcommitしない。
* vendor JARへの依存をhardware adapterへ隔離する。
* default Mock testがvendor JARなしで成立する構成を優先する。
* 実機にあるJARを新しいversionへ自動置換しない。
* 内部classやprivate behaviorへ依存しない。

### 8.3 Python dependency

`python_server/`を変更する場合だけ、次を適用する。

* CPython 3.6.15互換性を維持する。
* dependency追加時はPython version、Yocto導入可能性、native extension、licenseを確認する。
* Python dependencyを新Java production runtimeの必須要件にしない。
* 開発tool用Pythonとproduction Java runtimeを混同しない。

### 8.4 非公式資料

非公式な低レベル実装や外部repositoryを参照するときは、repository URL、完全なcommit SHA、確認日、license、参照目的、copyの有無、検証状態を記録する。

ただし、非公式資料から次を新Java production実装へ採用してはならない。

* 未確認のregister address
* 未確認のservo／LED ID
* 未確認のpacket
* 未確認の可動範囲
* vendor private API
* reverse engineeringで得た内部implementation

外部repositoryの具体的なSHAは、本fileではなく `docs/protocol-compatibility.md` のReference baselines節または適切なevidence文書へ記録する。

## 9. テスト

変更には、原則として対応するtestを追加する。

### 9.1 Java unitおよびintegration test

* 新Java実装のtest frameworkはJUnitを使用する。
* JUnitおよびtest pluginのversionは `pom.xml`で固定し、Java 8互換性を確認する。
* default testはhardware-free、network-isolated、audio-device-freeとする。
* testは順序に依存させない。
* test間でstatic mutable stateを共有しない。
* 実時間の長いsleepを使用しない。
* fake clock、fake scheduler、Mock backend、fake audio outputを使用する。
* flaky testをretryで隠さない。
* test failure時に実機操作を自動fallbackとして実行しない。

最低限、次をtestする。

* frame encode／decode
* partial read
* EOF
* timeout
* length 0
* oversized frame
* invalid UTF-8
* invalid JSON
* unknown command
* command-specific size limit
* 正常なPose、Motion、Idle Motion
* 不正な数値
* servo／LED名validation
* queue overflow
* connection上限
* cancelとstopの冪等性
* generation置換
* disconnect後のcancel
* 複数commandの競合
* `read_axes`のJSON response
* backend initialization failure
* lifecycle state transition
* resource close
* exception translation
* logへのbinary payload非出力
* in-memory WAV validation
* unsupported WAV format rejection
* PCM decode
* audio playbackの開始、完了、置換、停止
* audio device failure
* mouth envelope計算
* noise gate、attack、release
* playheadと口LED frameの対応
* coalescing mailbox
* audio停止後のmouth LED zero
* mouth voice-sync復元
* LED lock release
* Mock backendへの正しい呼び出し

### 9.2 protocol compatibility test

* 既存 `robo-tutorial` clientと同じbyte列を用いるcompatibility testを含める。
* legacy v1では、`read_axes`以外へACKを追加していないことをtestする。
* JSON key順序または空白だけに依存するtestを作らない。
* 正常系compatibilityと、旧実装のbug再現を区別する。
* protocol golden vectorはsource control可能な小さいfixtureとして保存する。
* 大容量または機密性のあるraw evidenceをtest fixtureとしてcommitしない。

### 9.3 VSTONE adapter test

* VSTONE adapterのunit testでは、vendor APIを包む薄いboundaryまたはfakeを使用する。
* default CIで実機、audio device、AppManager、VSMDへ接続しない。
* vendor APIのmethod呼び出し順、lock key、release、error translationをtestする。
* VSTONE公開APIの実機上の意味論はMockだけで確定したと表現しない。
* 実機確認が必要な項目はmanual acceptance gateとして記録する。

### 9.4 Python test

`python_server/`を変更する場合だけ、既存のPython testを実行する。

* pytestはCPython 3.6対応versionを使用する。
* Python testの成功を新Java production実装のtest完了とみなさない。
* Python testはreference behaviorまたはtest oracleとして位置付ける。
* JavaとPythonの比較testを追加する場合は、比較対象がprotocol、validation、conversion、schedulerのどれかを明示する。

### 9.5 実機test

* 実機testは自動testと分離する。
* 明示的なhuman opt-inなしに実行されない構成にする。
* Codexを含む自動エージェントは実機testを実行しない。
* manual runbookには、前提条件、実行command、期待結果、停止条件、rollback、観測記録、SHA-256を含める。
* read-only確認をwrite確認より先に行う。
* servo testは1 axis、小変位、低速、短時間から開始する。
* audioおよび口LED testは低音量、短いPCM、保守的なLED brightnessから開始する。
* 実機test結果にはoperator observationを含める。
* 実機test未実施の機能をproduction-readyと表現しない。

## 10. タスクの進め方

大規模な一括実装を避け、検証可能な小さい変更に分割する。

各taskでは、次の順序を守る。

1. 関連文書、既存実装、testを確認する
2. 変更範囲、非対象、受入条件を明示する
3. 必要なtestを先に追加または定義する
4. 最小限の実装を行う
5. format、compile、unit test、integration test、静的解析を実行する
6. `git diff`およびstaged diffを確認する
7. safety、compatibility、resource ownershipへの影響を確認する
8. 未解決事項を報告する

各taskでは、次を行わない。

* 関係のない大規模refactor
* sourceと大量生成物の同時追加
* 文書化されていないprotocol変更
* 実機確認を伴わないhardware behaviorの断定
* test failureの無視
* scope外の`.local-evidence/`参照
* Codex個別指示のrepository追加
* protected fileの変更またはstage

## 11. 作業完了時の報告

作業完了時には、次を簡潔に報告すること。

* 変更したfile
* 実装した内容
* 実行したbuild、test、静的解析と結果
* 実行しなかったtest
* protocol compatibilityへの影響
* safetyへの影響
* dependencyへの影響
* resource ownershipとcleanupへの影響
* 残っている仮定または未解決事項
* 実機testが必要な場合のmanual手順
* `.local-evidence/`を参照した場合のexact pathと参照目的
* Codex個別指示をrepositoryへ追加していないこと
* `robot_controller_edison_smoke.sha256`を変更、stage、commitしていないこと

testに合格していない場合、buildできない場合、仕様が不明な場合、または実機確認が必要な場合は、完了したと表現しない。
