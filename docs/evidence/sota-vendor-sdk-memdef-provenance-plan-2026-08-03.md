# Sota vendor SDK artifact and active memdef provenance plan (2026-08-03)

## 1. Purpose

本計画は、Phase 8b2dで不足していたvendor SDK artifactとactive memory definitionのidentity、
選択根拠、license上の調査可能範囲を、human operatorによるread-only調査で確立するための
手順と受入条件を定める。

目的はstatic investigationへ必要なartifact provenanceを渡すことであり、vendor SDK内部write
path、servo target address、active memdef内容またはruntime motion behaviorをこの計画だけで
確認済みにすることではない。

```text
Application-to-SDK boundary: completed
Vendor SDK artifact identification and binary provenance: completed
Deployed memdef candidate identity: completed
Active memdef selection mechanism: unverified
Vendor SDK internal write-path analysis: blocked pending source/license confirmation
```

## 2. Current blocker

Local repositoryには`jp.vstone.RobotLib` source、vendor JAR、active `memdef.conf`のcopyがない。
そのため`CRobotPose.SetPose()`／`CRobotMotion.play()`より下流のwrite path、final conversion、
target memory mapping、enable／interpolation／stop sequenceを追跡できない。

Human-operated read-only調査では次のprocessが観測された。

| PID | Observed command | cwd / executable | Interpretation |
| ---: | --- | --- | --- |
| 345 | `/home/vstone/java/jdk1.8.0_40/bin/java -jar /home/vstone/lib/SotaAppManager.jar -Dfile.encoding=UTF8` | cwd `/home/vstone/vstonemagic/app`; exe `/home/vstone/java/jdk1.8.0_40/bin/java` | SotaAppManagerの観測。RobotController classpathの根拠ではない |
| 346 | `/opt/sota/sotalogger/goSotaLogger` | not recorded | Sota logger。vendor SDK selectionの根拠ではない |

観測時点でRobotController Java processは動作していなかった。したがってprocess-level runtime
class loading observationは存在しない。Identity確認のためにRobotControllerを起動してはならない。

ただしoperatorはcurrent deploymentを次のとおり確認した。

```text
OPERATOR-CONFIRMED OPERATIONAL SELECTION
/home/root/RobotController_bin
```

`/home/vstone/vstonemagic/app/jar/RobotController_bin_private`は現在使用されないinactive historical
copyであり、過去の外部program登録copyが残る可能性がある。削除、変更、実行しない。

Current `RobotController.jar` manifestは`Main-Class: main.App`と次を記録する。

```text
Class-Path: . RobotController_lib/core-2.2.jar RobotController_lib/gson-2.8.5.jar RobotController_lib/javase-2.2.jar RobotController_lib/jna-4.1.0.jar RobotController_lib/json-20180813.jar RobotController_lib/sotalib.jar
```

したがって次は**PACKAGE-CONFIRMED LOAD TARGET**である。

```text
/home/root/RobotController_bin/RobotController_lib/sotalib.jar
```

Read-only entry inspectionでこのJARが`jp.vstone.RobotLib` classesを含むことも確認された。

Current distribution内の次のdependencyはmanifestまたは存在確認で記録されたartifactである。

* `/home/root/RobotController_bin/RobotController.jar`
* `/home/root/RobotController_bin/RobotController_lib/sotalib.jar`
* `/home/root/RobotController_bin/RobotController_lib/jna-4.1.0.jar`
* `/home/root/RobotController_bin/RobotController_lib/json-20180813.jar`
* `/home/root/RobotController_bin/RobotController_lib/javase-2.2.jar`
* `/home/root/RobotController_bin/RobotController_lib/core-2.2.jar`
* `/home/root/RobotController_bin/RobotController_lib/opencv-310.jar`
* `/home/root/RobotController_bin/RobotController_lib/gson-2.8.5.jar`
* `/home/root/RobotController_bin/RobotController_lib/SRClientHelper.jar`
* `/home/vstone/lib/SotaAppManager.jar`（別processのartifactでありRobotController dependencyではない）

次のbinary identityは**CONFIRMED at the investigation time**である。

| File | SHA-256 |
| --- | --- |
| `/home/root/RobotController_bin/RobotController_lib/sotalib.jar` | `7c3b45f42139a651e2c5d021c18ebf217cdb9be5af25569e910221d88d71bffa` |
| `/home/vstone/lib/sotalib.jar` | `7c3b45f42139a651e2c5d021c18ebf217cdb9be5af25569e910221d88d71bffa` |

両original filesは調査時点でbyte-for-byte identicalである。Distribution内JARをSDK内部static
investigationの主対象とし、`/home/vstone/lib/sotalib.jar`は同じhashを持つ調査時点のbinaryに
限定してprovenance sourceとして使用できる。将来どちらかが置換された場合は再hashが必要である。
これはpackage-level load targetとbinary identityの確認であり、process-level runtime load観測ではない。

Initial memdef searchは`/home/root`、`/opt`、`/usr/local`だけを対象としていた。後続のread-only
調査で`/home/vstone/vstonemagic`配下のdeployed candidateとvariantを確認した。Candidate identityは
完了したが、sotalib／SotaAppManagerによるactive selection mechanismは**UNVERIFIED**である。

## 3. Safety boundary

本計画はoperatorが内容をreviewした後に手動実施するmetadata／file-contentのread-only調査だけを
許可する。自動agentはremote execution、SSH、Edison接続または実機通信を行わない。

次を禁止する。

* RobotControllerまたはcandidate JARの起動
* class loadingを伴うJava programの実行
* SotaAppManager、logger、VSMDその他processの停止、再起動、signal送信
* `systemctl`、`service`、`kill`、`killall`
* file作成、変更、削除、rename、copy、展開、再圧縮、`chmod`、`chown`、symlink変更
* process／debugger／`strace` attach、memory dump
* `/dev/ttyMFD1`、`/dev/i2c-1`その他device access
* VSMD／AppManager connection、memory read／write
* servo、LED、torque、pose、motion command
* deployment、packageまたはhash toolのinstall
* `/run/lock/robot-controller-sota.lock`のunlink
* license確認前のdecompilationまたはbytecode disassembly

RobotController起動pathにはsource-levelで`InitRobot_Sota()`、`ServoOn()`、torque、initial pose、
LED設定が見えるため、provenance確認目的の起動も禁止する
(`src/servo/RobotSys.java:103-121`)。

## 4. Required vendor SDK information

各candidate JARについて次を記録する。

| Field | Required content |
| --- | --- |
| Absolute path | symlink解決前の発見pathと解決後のcanonical path |
| Filename | caseを含むexact basename |
| File size | bytes |
| SHA-256 | original file全体のdigestと使用tool |
| Modification timestamp | timezoneまたはraw system表示を含む |
| JAR manifest | `META-INF/MANIFEST.MF`のread-only出力 |
| Implementation version | manifest値。欠落時は`not present` |
| Specification version | manifest値。欠落時は`not present` |
| Package/class presence | `jp/vstone/RobotLib/`および必要class entryの存在 |
| Startup classpath | startup script、manifest `Class-Path`、起動設定に記載されたexact order |
| Process command line match | 自然に動作中なら`/proc/PID/cmdline`、不在なら`not observable` |
| Candidate inventory | 同名、別path、別size、別hash、別versionを省略しない一覧 |
| Active-selection basis | configuration／自然なprocess／manifestを結ぶ説明 |
| Source availability | exact versionに対応するsourceの所在、hash、提供条件 |
| Decompilation permission | license／契約上の明示根拠。推測しない |
| License | title、version、copyright holder、取得元 |
| Redistribution | repository内外へのcopy可否と条件 |
| Commit permission | JAR／source／derived textそれぞれの可否 |

JAR本体はlicenseとredistribution条件が確認されるまでrepositoryへ追加しない。存在が確認された
candidateをfilenameまたはmtimeだけでload targetとして扱わない。Current distribution内
`sotalib.jar`についてはoperational selection、manifest、package entry、SHA-256の組合せにより
artifact identificationとbinary provenanceが完了しているが、license上のinspection permissionは
未確認である。

## 5. Required active memdef information

### 5.1 Confirmed deployed candidate identity

次はhuman-operated read-only metadata／hash／content調査で確認済みである。

| Classification | Path | Type | Size | mtime | SHA-256 |
| --- | --- | --- | ---: | --- | --- |
| **CONFIGURATION-LEVEL CONFIRMED deployed candidate** | `/home/vstone/vstonemagic/memdef.conf` | regular file; not symlink | 2491 bytes | `2015-06-19` | `9d289f1659384f92d7796c9e5031826804adca952aee0d24641f4c162169af11` |
| **CONFIRMED Sota Normal variant** | `/home/vstone/vstonemagic/memdef/memdef.conf.sota` | file | 2491 bytes | `2016-05-19` | `9d289f1659384f92d7796c9e5031826804adca952aee0d24641f4c162169af11` |

両fileはSHA-256一致と`cmp -s`により調査時点でbyte-for-byte identicalであり、top-level fileは
Sota Normal variantの内容を持つ。将来置換時は再hashする。

| Other candidate variant | SHA-256 |
| --- | --- |
| `memdef.conf.sota_im` | `c02b68130b1471c2821cdb9dc41d8090fb602a32e33a756bf76d69556502894c` |
| `memdef.conf.sota_im_T1` | `d6e494e260763a9681182d8e4a2fac20bc4c3761e440c9ffd58f5fe252bf9fb7` |
| `memdef.conf.sota_im_bat` | `12a203cefea4ff40f4764c6b02215067cb30acc4e0891378c3be7b509dba6d79` |
| `memdef.conf.sota_bat` | `9387dd3dc71416db3ae1375ba4bb2d4ff969fb9722305737c1f8fa0a35eac59e` |
| `memdef.conf2.sota_pi` | `286dccefc27dee13c928e79297a670622f1e1940155c3573b29a9e8469679cc1` |

Top-level fileはconfiguration-levelで`Model: Sota_Normal`、`ServoBusNum: 8`、8個の
`ServoSettings`を含む。ほかに`isModefied: false`、`ServoBusProtocol: 1`、`ServoEN: 0`、
`ServoSendEN: 1`、`I2CSendEN: 1`、lock detection fieldsが確認された。各`ServoSettings`には
`id`、`readAngleEn`、`readAngleBank`、`max`、`min`、`offset`がある。

`ServoEN`の値0および`ServoSendEN`の値1をmemory addressまたはbooleanと断定しない。これらの
configuration fieldはwrite sequence、safe range、final offset、`ServoReadPos` indexの根拠でもない。
Vendor SDK内部意味論は**UNVERIFIED**である。

Field-name searchで検出された対象名は`ServoEN`と`ServoSendEN`だけだった。Top-level本文に
`ServoReadPos`、servo target／target address、`Interp`の明示的field名は確認されず、このfileを
VSMD memory address一覧として扱わない。定義がSDK内部または別resourceに存在する可能性は残るが、
別の場所に必ず存在するとは断定しない。

PID 345のopen FD name searchはemptyだった。観測時点でmemdef名を含むopen FDを確認できなかった
ことだけが**CONFIRMED**であり、非使用、load後close、別名／relative path／JAR resource／別process
経由の可能性は**NOT ESTABLISHED**である。

### 5.2 Information still required for active selection

各memdef candidateについて次を記録または確認する。

* symlink解決前と解決後のabsolute path、filename
* file size、original fileのSHA-256、modification timestamp
* search rootとsearch commandを含むcandidate全件一覧
* startup script／起動設定内のexplicit pathまたはoption
* Java command line／manifest／wrapperからの参照
* startup scriptで設定されるenvironment variableからの参照
* startup時の`cd`とcurrent working directory依存のrelative path resolution
* vendor SDKで定義されるdefault search pathとfallback order
* JAR resource内にmemdefが内包される可能性とentry path
* symlink chainと最終regular file
* 複数候補からactive fileを選択する完全な規則と優先順位
* runtime fileとrepository copyのbyte-for-byte SHA-256一致確認方法

mtimeが最新、filenameが一致、top-levelに配置されている、Sota Normal variantと同一、candidateが
1つだけ、という理由だけでactiveと判断しない。配置されたSota Normal configurationであることは
configuration-level confirmedだが、active selectionにはload ruleの直接根拠が必要である。

## 6. Evidence required to establish artifact identity

Artifact identityの根拠には、同一operator sessionまたは明確に紐付く記録として次を必要とする。

1. Host/platform識別情報と調査日時（credentialやsecretは記録しない）。
2. Candidate inventoryのabsolute path、canonical path、size、mtime、SHA-256。
3. Original JARからstream表示したmanifestとpackage/class entry list。
4. Startup script／設定の該当行と、そのfile自体のpath、size、mtime、SHA-256。
5. RobotControllerが自然に動作中の場合だけ、`ps`、`/proc/PID/cmdline`、cwd、exeのread-only記録。
6. Manifest `Class-Path`、startup classpath、process command lineの一致／差異表。
7. Exact artifactに適用されるlicense／契約資料とsource availabilityの記録。

RobotControllerが動作していない場合はprocess evidenceを捏造せず`not observable`と記録し、startup
configurationだけで受入可能かをAcceptance criteriaに照らす。確認のためにprocessを起動しない。

## 7. Evidence required to establish active selection

Vendor SDKについては次のchainを説明できなければならない。

```text
reviewed startup entry
  -> exact Java executable and working directory
  -> exact -jar / -cp / -classpath or manifest Class-Path resolution
  -> canonical candidate JAR path
  -> recorded SHA-256 and package/class identity
```

Current distributionについてはoperator-confirmed selection、manifest `Class-Path`、package entry、
original-file SHA-256によってこのchainのartifact identity部分を満たした。RobotController processが
停止中だったため、process-level runtime class loadingは`not observed`として維持する。

Active memdefについては次のchainを説明できなければならない。

```text
reviewed startup entry and working directory
  -> command option / environment / SDK default / JAR resource selection rule
  -> symlink and relative-path resolution
  -> canonical original file or exact JAR resource
  -> recorded SHA-256
```

Top-level candidateのcanonical path、metadata、SHA-256、Sota Normal variantとのbinary identityまでは
確認済みである。未確認境界は、SDK／AppManagerがどのruleでそのfileまたは別resourceを選択し、
いつloadするかである。PID 345のmemdef-name FD searchがemptyだったことはselection否定に使わない。

複数候補は全件を残し、なぜ選択されないかもconfigurationまたはselection ruleで説明する。
SotaAppManagerのcommand lineをRobotControllerのclasspathまたはmemdef selectionへ一般化しない。

## 8. Read-only operator procedure

以下はhuman operatorが1 commandずつreviewして手動実行する例である。pathとPIDは観測結果に
合わせて置換し、失敗時に自動retry、search範囲拡大、別command実行を行わない。出力を上書き
保存するcommandは例示しない。

### 8.1 Existing process observation

```sh
ps -ef
cat /proc/{PID}/cmdline
readlink -f /proc/{PID}/cwd
readlink -f /proc/{PID}/exe
```

`cmdline`はNUL区切りであることを記録する。RobotController processがなければ`not running`と記録し、
起動しない。既知PID 345はSotaAppManagerでありRobotControllerではない。

### 8.2 Candidate discovery

```sh
find /home/root /home/vstone /opt /usr/local -type f \( -name '*.jar' -o -iname '*memdef*' \) -print
grep -R -n -E 'RobotController|sotalib|memdef|java.*(-jar|-cp|-classpath)' /etc/init.d /etc/rc.d /home/root /home/vstone /opt /usr/local
```

Permission errorも削除せず記録し、search coverageを過大評価しない。`find`結果が0件でも不存在と
断定しない。startup script候補に対してのみ、必要最小限の追加`grep`を人間がreviewする。

### 8.3 Metadata and symlink resolution

```sh
ls -ld /absolute/candidate/path
ls -l /absolute/candidate/path
readlink -f /absolute/candidate/path
```

### 8.4 SHA-256

最初に既存`openssl`が利用可能なら、original fileそのものをhashする。

```sh
openssl dgst -sha256 /absolute/candidate/path
```

`openssl`が利用できない場合だけ、既存CPythonをread-onlyで使用する。

```sh
/home/root/bin/python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" /absolute/candidate/path
```

`sha256sum`はEdisonで見つからなかった。hash toolを追加installしない。artifactを変換、展開、
再圧縮せず、hash対象はoriginal file全体とする。使用したexecutable pathとcommandを記録する。

### 8.5 Read-only JAR inspection

既存`unzip`が利用可能な場合だけ、stdoutへstream表示する。JARを実行せず、fileへ展開しない。

```sh
unzip -p /absolute/candidate.jar META-INF/MANIFEST.MF
unzip -l /absolute/candidate.jar
unzip -l /absolute/candidate.jar | grep 'jp/vstone/RobotLib/'
unzip -l /absolute/candidate.jar | grep -i 'memdef'
```

`unzip`がなければtoolをinstallせず`not inspectable with installed read-only tools`と記録する。
`java -jar`、target class loading、`jar xf`は実行しない。

## 9. Data recording template

### 9.1 Session

```text
Operator:
Observation date/time/timezone:
Host/platform identifier (non-secret):
RobotController process state: running naturally / not running
Commands reviewed and executed:
Permission errors or incomplete search roots:
```

### 9.2 Vendor artifact candidate

```text
Discovered path:
Canonical path:
Filename:
Size bytes:
Modification timestamp:
SHA-256:
Hash tool and executable:
Manifest present:
Manifest Implementation-Version:
Manifest Specification-Version:
Manifest Class-Path:
jp/vstone/RobotLib present:
Relevant class entries:
Startup reference:
Natural process command-line match / not observable:
Source availability:
License evidence:
Decompilation allowed / prohibited / unknown:
Redistribution allowed / prohibited / unknown:
Repository commit allowed / prohibited / unknown:
Classification: candidate / active provenance confirmed / rejected
Reason:
```

### 9.3 Memdef candidate

```text
Discovered path or JAR resource path:
Canonical path:
Filename:
Size bytes:
Modification timestamp:
SHA-256:
Search roots and command:
Startup-script reference:
Command-line reference:
Environment-variable reference:
Startup cwd and relative-path resolution:
SDK default search rule evidence:
Symlink chain:
Repository-copy path and SHA-256:
Candidate selection precedence:
Classification: candidate / active provenance confirmed / rejected
Reason:
```

## 10. License and redistribution constraints

* Vendor JAR、source、memdef、manifest以外のextracted content、decompiled outputは、applicable license、
  contract、copyright holder、redistribution条件が確認されるまでrepositoryへ追加しない。
* License不明時はdecompilation、copy、redistribution、derived-source commitを禁止する。
* Manifestやpackage listingの記録も、公開／commit可能範囲をlicense reviewで判定する。
* Licenseがstatic inspectionを許してもredistributionを許すとは限らないため別項目で記録する。
* Source提供物はbinaryとversion／hashの対応が説明できなければ調査対象のidentity根拠にしない。
* Repositoryへ残せる既定成果物は、secretとvendor contentを含まないmetadata、hash、path、判断記録
  だけとし、それもlicense／security review後にcommitする。

## 11. Acceptance criteria

Vendor SDK artifact identity／binary provenanceについて、次は**CONFIRMED**である。

* Current deployment directoryはoperator-confirmedで`/home/root/RobotController_bin`。
* `RobotController_bin_private`はinactive historical copy。
* `RobotController.jar` manifestの`Main-Class`と`Class-Path`。
* Distribution内`sotalib.jar`がpackage-confirmed direct load targetであること。
* JARに`jp.vstone.RobotLib` classesが含まれること。
* Distribution内JARと`/home/vstone/lib/sotalib.jar`のSHA-256一致および調査時点のbinary identity。

Deployed memdef candidate identityについて、次は**CONFIRMED**である。

* Top-level candidateのcanonical path、regular-file type、size、mtime、SHA-256。
* `memdef.conf.sota`のpath、size、mtime、SHA-256。
* 両fileの調査時点でのbinary identityとtop-levelがSota Normal variant内容を持つこと。
* `Model: Sota_Normal`、`ServoBusNum: 8`、8個の`ServoSettings`。
* Top-level本文に明示的な`ServoReadPos`、servo target／target address、`Interp` field名を確認できないこと。

このidentity confirmationはsemantic version、source availability、license permission、active memdef、
process-level runtime loadを確認したものではない。Vendor SDK internal static investigationを開始可能と
するには、さらに次を満たす必要がある。

* SDK／AppManagerがactive fileまたはexact JAR resourceを選択する直接的なruleを確認できる。
* Confirmed candidate identityとactive selection resultを結び付けられる。
* 複数memdef候補からのselection rule、load path／timing、非選択理由を説明できる。
* License上可能なsource inspection、decompilation、引用、redistribution、commit範囲が明確である。

## 12. Rejection criteria

次のいずれかなら**CONFIRMED**にしない。

* Filenameだけが一致する、candidateが1つだけ、またはmtimeが最新という理由だけでactiveとする。
* `/home/root/RobotController_bin/RobotController_lib/sotalib.jar`の存在だけでload targetとする
  （今回のconfirmationは存在だけでなくoperational selection、manifest、package listing、hashに基づく）。
* RobotController不在時のSotaAppManager process情報をRobotController classpathへ流用する。
* JAR version、SHA-256、startup classpath、working directoryまたはsymlink解決先が不明。
* `jp.vstone.RobotLib` package／classの存在を確認できない。
* Candidate path／SHA-256だけからactiveとし、selection rule、load path／timingが不明。
* Incomplete searchでmemdef不存在を結論する。
* Repository copyとruntime fileのSHA-256が異なる、または比較対象がoriginal bytesでない。
* 複数候補の優先順位を説明できない。
* License不明のままdecompile、extract、copy、redistributeまたはcommitする。
* Identity確認のためRobotController／JARを起動、processへattach、実機通信を行う。

## 13. Artifacts that must not be committed

License、redistribution、secret reviewが完了するまで次をcommitしない。

* `RobotController.jar`、`sotalib.jar`、`SotaAppManager.jar`およびその他vendor／third-party JAR本体
* active／candidate memdef file本体とJAR内resourceのcopy
* vendor source archive、decompiled source／bytecode-derived pseudocode
* JAR展開directory、class file、native library
* startup configurationのfull copyにcredential、token、host secret、personal dataが含まれるもの
* `/proc` dump、environment dump、memory dump、device data
* license上redistribution不可または不明なmanifest／listingの過剰な転載

`robot_controller_edison_smoke.sha256`は別のprotected untracked fileであり、変更、移動、stage、
commit、cleanによる削除を行わない。

## 14. Handoff back to static investigation

Vendor binary identityとdeployed memdef candidate identityに加え、active selection mechanismと
licenseのacceptance criteriaを満たした後、次の
sanitized handoff packageを用意する。

* active JARとmemdefのcanonical path、SHA-256、version、selection chain
* candidate comparison tableと非選択理由
* license判定と許可されたinspection method
* sourceまたはbinary inspectionで参照可能なclass／resource boundary
* unresolved ambiguity、search coverage、operator observation limitation

Phase 8b2d static investigationはこのidentityに固定して再開し、まず`CRobotPose.SetPose()`、
`CRobotMotion.play()`、`CSotaMotion`、memory accessor、AppManager wrapper、memdef target fieldを追跡する。
Artifact hashまたはselection ruleが変わった場合は結果を流用せずprovenanceを再確認する。

## 15. Explicit prohibition on live write

**Provenance収集とその成功はlive motion readinessまたはwrite safetyを意味しない。Servo target
address、final conversion、enable／interpolation／stop／rollback／safe rangeが別途確認されるまで、
single-axis live write、RobotController起動、servo／LED／torque command、VSMD／AppManager通信、
memory writeおよびlive-write code実装を引き続き禁止する。**
