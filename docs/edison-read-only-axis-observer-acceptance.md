# Intel Edison Sota raw-axis observer read-only runtime acceptance

## 1. Document status

```text
Status: Completed
Acceptance type: Read-only runtime acceptance
Target platform: Intel Edison / Yocto
Target revision: 9008d062847d46ed0f85c7cb5c942c74ff7411e9
Execution date: 2026-08-01
```

対象commitのmessageは`Add opt-in read-only Sota axis diagnostics`である。実行者名は
回収証跡から確認できないため記載しない。

本書は、実機で観測した事実、reviewed implementation pathから判断した事項、未確認事項を
分離して記録する。今回の成功はlive motion readinessまたはservo write safetyを示さない。
**Live servo writeは引き続き禁止する。**

## 2. Scope

対象moduleは次のread-only observerである。

```text
python -m robot_controller.hardware.vsmd.sota_axis_observer
```

今回確認した範囲は次のとおりである。

* Intel Edison上のCPython 3.6.15でのmodule import
* confirmation optionなしでのfail-closed動作
* `127.0.0.1:6498`へのVSMD memory-read request
* `ServoReadPos`相当のmemory areaからの32個のsigned S16取得
* `--samples 1 --interval-ms 100`による1 sample取得
* `--samples 10 --interval-ms 100`による10 samples連続取得
* CSV header、列数、row数、sample sequence、timing field、S16範囲の検証
* 最終検査時点で**pycache**、*.pyc、*.pyoが検出されなかったことの確認
* Windowsへの証跡回収、exact file set検証、SHA-256 manifest作成

32個の値はraw storage indexとしてのみ扱う。公開物理軸へのmappingやdegree変換はscope外である。

## 3. Safety boundary

今回の「read-only」はVSMD memory operationについての分類であり、network上で一切送信を
行わないという意味ではない。VSMD memory readにはrequestが必要なので、TCP 6498へencoded
read requestを送信し、`transport.send()`および`socket.sendall()`を使用する。一方、
reviewed implementation path contains no VSMD memory-write operation.

reviewed implementation pathおよび今回選択した実行経路には、次の操作を含まない。

* `write_bytes()`
* `encode_write_request()`
* `write_s16()`
* `write_s16_array()`
* servo target write
* torque write
* LED write
* AppManager command
* TCP 6495接続
* TCP 22222 listen
* service操作
* process終了
* process lock取得
* `/dev/ttyMFD1`へのアクセス
* `/dev/i2c-1`へのアクセス

これはsource reviewと選択されたprogram pathに基づく限定的な記述である。今回network captureは
行っていないため、実機trafficから「write可能なpacketが送信されなかった」と証明したものでは
ない。また、機体の物理状態に関するoperator observationは証跡に含まれない。

## 4. Environment

### 4.1 Intel Edison

実施記録として提供されたplatform情報は次のとおりである。

```text
OS/kernel: Linux edison 3.10.17-poky-edison+
Architecture: i686
Python executable: /home/root/bin/python3
Python: CPython 3.6.15
Compiler information reported by Python: GCC 4.9.1
VSMD endpoint: 127.0.0.1:6498
```

回収証跡`runtime-preflight.stdout`はPython executable、Python 3.6.15、GCC 4.9.1を
直接記録している。OS/kernelとi686はoperator提供の実施記録であり、回収した26件のmanifest
対象fileには独立した`uname`出力は含まれない。Access was performed through the operator's
configured SSH jump host. 接続先、username、credentialは記録しない。

### 4.2 Windows bundle preparation

operator-localなbundle作成環境は次のとおりである。

```text
Repository:
C:\Users\tiio\Workspace\RobotController

Local Python used for bundle validation:
C:\Users\tiio\Workspace\RobotController\python_server\.venv\Scripts\python.exe

Local Python version:
Python 3.14.3
```

これらのWindows absolute pathはoperator-local pathであり、他環境で同じpathを要求しない。
Python 3.14.3でのstaging validationはEdison互換性の根拠ではない。Edison互換性は、実機の
CPython 3.6.15でimportとobserver実行が成功したことによって確認した。

## 5. Bundle integrity

archiveは次のexact setで構成された。

```text
18 Python runtime dependency files
REVISION.txt
deployed-files.txt
20 regular files total
6 directory entries
26 archive members total
```

`deployed-files.txt`と`archive-members.txt`から、このfile setとmember countを確認した。
archive SHA-256は次のとおりである。

```text
330f5c922da408f6cca25918f7aa3ad5920ada734a2179785bda8280c927ad31
```

Windows側の計算値、checksum sidecar、Edison上でCPython 3.6.15標準ライブラリの
`hashlib.sha256`により計算した値は一致した。回収証跡では
`robot_controller_axis_observer_9008d06.tar.gz.sha256`と
`checksum-validation-python.txt`がこの値を記録している。

Edisonには`sha256sum`commandが存在せず、最初のchecksum検証は次のerrorで失敗した。

```text
sha256sum: command not found
```

失敗証跡は`checksum-validation-sha256sum-missing.txt`として削除せず保存した。その後、
別名の`checksum-validation-python.txt`を作成し、`hashlib.sha256`で成功を確認した。

## 6. Import provenance

Windows staging bundleでは次を確認した。

```text
staged_import_validation=passed
```

Edison deploymentの`runtime-preflight.stdout`と関連exit evidenceは次を示す。

```text
python_executable=/home/root/bin/python3
python_version=3.6.15
imported observer path = expected observer path
runtime preflight exit code=0
runtime preflight stderr=empty
runtime_preflight=passed
```

`robot_controller.hardware.vsmd.errors`が`robot_controller.errors.HardwareProbeError`へ
依存するため、最終bundleには次のruntime dependencyを含めた。

```text
src/robot_controller/errors.py
```

`deployed-files.txt`と`archive-members.txt`の双方で収録を確認した。

## 7. Confirmation-gate negative test

confirmation optionなしの実行結果は次のとおりであった。

```text
exit code=1
stdout=empty
stderr:
error=--confirm-read-only-axis-observation is required
```

これにより、confirmation optionなしではobserverが正常なobservation pathへ進まないことを、
実装順序とprocess outputから確認した。network captureは行っていないため、TCP packetが絶対に
送信されなかったというnetwork-level assertionではない。

## 8. Read-only smoke results

### 8.1 Smoke 1

```text
samples=1
interval-ms=100
exit code=0
stderr=empty
CSV validation=passed
```

参考として、取得された`raw_00`から`raw_31`は次のとおりである。

```text
0, -5, -899, 0, 904, 2, -2, -8, 4,
0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
```

この値を物理軸名、degree、姿勢または正常状態へ変換・解釈しない。

### 8.2 Smoke 10

```text
samples=10
interval-ms=100
exit code=0
stderr=empty
CSV validation=passed
```

### 8.3 CSV validation

両smokeで次を検証した。

* exact headerおよび37 columns
* `sample_index`
* 4 timing fields
* 32 raw fields
* raw値がcanonical base-10 integer
* raw値がsigned S16範囲内
* row countが要求sample countと一致
* sample indexが0から連続
* timing値がfinite
* elapsedおよびactual intervalがnon-negative

validator evidenceはsmoke 1で`validated_rows=1`、smoke 10で`validated_rows=10`、
双方で`validated_columns=37`、`raw_value_type=signed_s16`を記録した。

## 9. Bytecode check

deploymentの最終検査結果は次のとおりである。

```text
bytecode checker exit code=0
bytecode checker stdout=empty
bytecode checker stderr=empty
deployment_bytecode_check=passed
```

checkerが正常終了し、検出pathをstdoutへ出力せず、errorも出力しなかったため、最終検査
時点で**pycache**、*.pyc、*.pyoが検出されなかったことを確認した。

## 10. Evidence

Windowsへ回収したoperator-local evidence directoryとmanifestは次のとおりである。

```text
C:\Users\tiio\robot-controller-axis-observer-evidence-9008d06
C:\Users\tiio\robot-controller-axis-observer-evidence-9008d06\retrieved-evidence.sha256
```

repositoryへこのevidence directory自体は追加しない。検証結果は次のとおりである。

```text
retrieved file count=26
exact retrieved-file-set validation=passed
critical evidence validation=passed
SHA-256 manifest creation=passed
hashed evidence file count=26
```

26件すべてについてmanifestの期待hashと再計算したSHA-256が一致した。manifestを個別hashの
source of truthとし、本書には全hashを転記しない。空fileのSHA-256は次のとおりである。

```text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

このhashは、空であることが期待されたnegative-test stdout、両smoke stderr、runtime
preflight stderr、bytecode checker stdout／stderrのmanifest entryと一致する。

## 11. Problems encountered and resolutions

以下はoperatorから提供されたprocedure recordである。再検証時は同じfailure modeを避ける。

### 11.1 Windows PowerShell 5.1

発生した問題:

* 使用環境の`New-Item`では`-LiteralPath`を利用できなかった。
* 複数行Pythonを`python -c`へ渡すとnative command argument processingで引用符が壊れた。
* 対話的に1 commandずつ貼り付けると、失敗後も後続commandが実行された。

対応:

* `New-Item`では`-Path`を使用した。
* 複数行Pythonは一時helper scriptとして実行した。
* PowerShell全体を`& { ... }`で囲み、`$ErrorActionPreference='Stop'`を設定した。

### 11.2 Edison interactive bash

interactive shellで`set -u`を有効にしたところ、promptまたはshell hookが未設定変数
`text`を参照し、次のerrorで接続が閉じた。

```text
-bash: text: unbound variable
```

そのため、次の形式の非対話bashで実行した。

```sh
bash --noprofile --norc -s <<'RUNBOOK'
# reviewed commands
RUNBOOK
```

### 11.3 Edison checksum utility

`sha256sum: command not found`となったため、CPython 3.6.15標準ライブラリの
`hashlib.sha256`を使用した。失敗証跡は保持し、別名の成功証跡を作成した。

## 12. What was confirmed

実機実行または回収証跡から確認した事項は次のとおりである。

* Edison上のCPython 3.6.15でobserverをimport可能
* 展開bundleから期待したmoduleがimportされた
* confirmation gateが機能した
* VSMD `127.0.0.1:6498`から32個のsigned S16を取得できた
* 1 sampleを取得できた
* 100 ms指定で10 samplesを連続取得できた
* CSV formatが期待仕様と一致した
* confirmed smoke実行時にstderrが発生しなかった
* 最終検査時点で**pycache**、*.pyc、*.pyoが検出されなかった
* 証跡を回収し、26件のhash manifestを作成・再検証した

## 13. Source reviewからのみ判断した事項

observerの選択経路は次のとおりである。

```text
SotaAxisReadOnlyObserver.observe()
  -> VsmdSotaRawAxisStateSource.read_raw_positions()
  -> VsmdTypedMemory.read_s16_array()
  -> VsmdMemoryClient.read_bytes()
  -> VsmdTcpTransport.send() / read_line()
  -> 32 signed S16 values
  -> CSV output
```

このreviewed pathはread requestを`transport.send()`でTCP 6498へ送るが、
`VsmdMemoryClient.write_bytes()`またはtyped write methodへ分岐しない。これは実装経路の
review結果であり、network captureによるpacket-level証明ではない。

## 14. What was not confirmed

以下は今回の実機acceptanceでは確認していない。

* `raw_00`～`raw_31`と8つの公開物理軸との対応
* `ServoReadPos[32]`のindex mapping
* raw値からdegreeへの実機上の変換妥当性
* 各軸の正方向
* 各軸の原点とoffset
* gear ratioの実機適合性
* 32値が同一control tickのatomic snapshotか
* read値がactual position、target position、encoder値のどれか
* torque state
* servo target write address
* servo target write protocol
* write completion条件
* motion interpolation
* motion stop
* motion cancel
* queue flush
* safe return to origin
* 異常時のrollback
* live servo writeの安全性

今回の成功から、all robot axesが正しく読めたこと、physical joint angle、既知jointとの対応、
atomicity、Java版との完全互換性、正常姿勢、live motion readiness、write safetyは導けない。

## 15. Next safe investigation

次工程はlive writeではなく、`Phase 8A: read-only ServoReadPos[32] mapping investigation`
とする。この工程でも次を禁止する。

* servo target write
* torque change
* automatic pose initialization
* blind mapping assumption
* `axis_id - 1` assumption
* Java array orderの無検証流用

mappingを候補から確認済みへ昇格するには、mapping根拠とoperator-observed physical correlationを
記録しなければならない。operator-observed physical correlationは観察方法を別途reviewした
上で実施し、torque stateとvendor-approved procedureが確認されるまで、関節を手動で
動かさない。物理観測は人間が安全条件を確認した手動工程として分離し、observerのraw index
変化との対応を記録する。これを満たすまでsingle-axis write工程へ進まない。

## 16. Re-execution notes

再実行時は、長いrunbookを本書から復元せず、review済み手順を使用する。特に次を維持する。

* revision、working tree、bundle exact set、checksumをfail-closedで検証する。
* `PYTHONDONTWRITEBYTECODE=1`と`python -B`を併用する。
* confirmationなしnegative testをconfirmed smokeより先に実行する。
* 1 sampleが完全に成功した場合だけ10 samplesへ進む。
* evidenceはno-clobberとし、失敗証跡を削除、rename、上書きしない。
* Edisonではreview済みcommandを非対話bashで実行する。
* retry、parameter変更、service操作、process終了、process lock削除を行わない。
* robotや関節へ触れず、live servo writeを行わない。

## 17. Conclusion

commit `9008d062847d46ed0f85c7cb5c942c74ff7411e9`のread-only Sota raw-axis
observerは、Intel Edison上のCPython 3.6.15で、明示的なoperator confirmationの下、
VSMDから32個のsigned S16値を1回および10回連続して取得し、期待するCSV形式で出力できる
ことが確認された。この結果によりread-only observation pathはruntime acceptedとする。

ただし、物理軸mapping、degree変換の実機妥当性、control-tick atomicity、torque、servo
target write、motion control、停止・復帰の安全性は未確認である。**Live servo writeは
引き続き禁止する。**
