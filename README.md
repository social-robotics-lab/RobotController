# RobotController

## 概要

Sota・CommUなどをTCP経由で制御するJavaプログラムです。従来のWAV再生・姿勢・モーション制御に加え、`audio_stream_v1`によるPCM音声ストリーミングに対応しています。

このREADMEは、Phase G受入済みコミット`94f885961d458fa5ea1e9415c17695f86a0518cb`の実装を説明します。2026年9月16日のSotaでの人手による受入試験は成功していますが、長時間再生時のまれなALSA XRUN・音声途切れの調査は継続中です。

## 対応ロボットと動作環境

- 従来の制御経路にはSota・CommU・Dogの実装があります。`System.properties`の`ROBOT_TYPE`で選択します。
- 新型ストリーミングの実機受入対象はIntel Edison上のSotaです。CommU・Dogでの新型ストリーミング動作は未検証です。
- ビルド・実行には**Java 8**が必要です。受入時のPCはTemurin OpenJDK 1.8.0_502、EdisonはJava 1.8.0_40でした。
- ストリーミングには、対象機のABIに適合するJNIライブラリ`librobotcontroller_alsa.so`とALSA環境が必要です。JNIはALSAの`default`を開き、`/usr/lib/libasound.so.2`を使用します。
- 従来型`play_wav`には`aplay`が必要です。新型ストリーミングは`aplay`を使用しません。

## ビルド方法

ここで扱うのはビルドと生成物の静的検証までです。Java・JNIの既存機能は変更しません。以下のSotaへのSSH/SCP・Edison上のコマンドは**操作者本人が手動で実行**します。自動エージェントは実機へ接続しません。既存ファイルの変更・削除・上書き、JVM起動、音声再生、サーボ・LED操作、既存サービスの停止、ALSAデバイスへの書き込みは今回の作業に含めません。

### 依存JARの準備と照合

Sota標準ライブラリの格納場所は `/home/vstone/lib` です。実機で確認されたのは `core-2.2.jar`、`javase-2.2.jar`、`jna-4.1.0.jar`、`sotalib.jar`、`gson-2.6.1.jar` ですが、現在の受入済みビルドには次の**6つすべて**が必要です。

| ファイル | 取得元・注意 |
|---|---|
| `core-2.2.jar` | Sotaの `/home/vstone/lib` からコピー |
| `gson-2.8.5.jar` | 別途取得。Sotaの2.6.1では代用不可 |
| `javase-2.2.jar` | Sotaの `/home/vstone/lib` からコピー |
| `jna-4.1.0.jar` | Sotaの `/home/vstone/lib` からコピー |
| `json-20180813.jar` | 別途取得。確認済みの標準JAR一覧には存在しない |
| `sotalib.jar` | Sotaの `/home/vstone/lib` からコピー。[VSTONE公式サンプル](https://github.com/vstoneofficial/SotaSample)も参照 |

不足する2つの案内ページは [Gson 2.8.5（Maven Central）](https://central.sonatype.com/artifact/com.google.code.gson/gson/2.8.5) と [JSON 20180813](https://mvnrepository.com/artifact/org.json/json/20180813) です。Maven Centralの取得先は [GsonのJAR](https://repo.maven.apache.org/maven2/com/google/code/gson/gson/2.8.5/gson-2.8.5.jar)、[JSONのJAR](https://repo.maven.apache.org/maven2/org/json/json/20180813/json-20180813.jar) です。PCでダウンロードし、必要ならEdisonへ転送してください。古いTLS環境から取得できなくても検証を無効化しないでください。

**6つとも**以下のSHA-256と照合します。値の基準は変更しない [Windowsビルドスクリプト](tools/build_phase_g.ps1) です。ファイル名を変更して別バージョンを同じものとして扱ってはいけません。不一致なら中止してファイル名・実測ハッシュ・取得元を報告し、要件の緩和や別JARへの自動切替を行いません。

| ファイル | SHA-256 |
|---|---|
| `core-2.2.jar` | `C6963B3DDC11B8A1FF4EBF65E93314CC6AF341685F70C98C752094FA59BEF492` |
| `gson-2.8.5.jar` | `233A0149FC365C9F6EDBD683CFE266B19BDC773BE98EABDAF6B3C924B48E7D81` |
| `javase-2.2.jar` | `CC32F41B3FCFF840BCDD08F14D24E7C170E382BD5C5A81A072AC075E66CC8426` |
| `jna-4.1.0.jar` | `1AA37E9EA6BAA0EE152D89509F758F0847EAC66EC179B955CAFE0919E540A92E` |
| `json-20180813.jar` | `518080049BA83181914419D11A25D9BC9833A2D729B6A6E7469FA52851356DA8` |
| `sotalib.jar` | `7C3B45F42139A651E2C5D021C18EBF217CDB9BE5AF25569E910221D88D71BFFA` |

Windowsでは、作業親フォルダで次を手動実行します。`SOTA_HOST` は操作者が実際の接続先に置換します。依存用フォルダは未作成の名前を選び、既存JARへ上書きしません。

```powershell
New-Item -ItemType Directory -Path ./robotcontroller-deps -ErrorAction Stop
foreach ($name in @("core-2.2.jar", "javase-2.2.jar", "jna-4.1.0.jar", "sotalib.jar")) {
  scp "root@${SOTA_HOST}:/home/vstone/lib/$name" ./robotcontroller-deps/
  if ($LASTEXITCODE -ne 0) { throw "SCP失敗: $name" }
}
# 取得したgson-2.8.5.jarとjson-20180813.jarも、このフォルダに保存します。
Get-FileHash -Algorithm SHA256 ./robotcontroller-deps/*.jar
```

macOSでは、作業親フォルダで次を手動実行します。

```sh
(
set -eu
mkdir ./robotcontroller-deps
for name in core-2.2.jar javase-2.2.jar jna-4.1.0.jar sotalib.jar; do
  scp "root@${SOTA_HOST}:/home/vstone/lib/$name" ./robotcontroller-deps/
done
# 取得したgson-2.8.5.jarとjson-20180813.jarも、このフォルダに保存します。
shasum -a 256 ./robotcontroller-deps/*.jar
)
```

Edison上では次のようにコピーします。`/home/root/robotcontroller-deps` は未作成であることを確認し、既存なら別の名前を選びます。`/home/vstone/lib` は読み取り元としてのみ使い、書き込み・移動・削除しません。

```sh
(
set -eu
mkdir /home/root/robotcontroller-deps
cp /home/vstone/lib/core-2.2.jar /home/root/robotcontroller-deps/
cp /home/vstone/lib/javase-2.2.jar /home/root/robotcontroller-deps/
cp /home/vstone/lib/jna-4.1.0.jar /home/root/robotcontroller-deps/
cp /home/vstone/lib/sotalib.jar /home/root/robotcontroller-deps/
# PCで取得した不足の2つも、操作者がこの新規フォルダへSCP等で転送します。
for jar in /home/root/robotcontroller-deps/*.jar; do
  openssl dgst -sha256 "$jar"
done
)
```

上のハッシュ表示は表と手動照合します。Edisonで `sha256sum`・`shasum` がない場合も、確認済みの `openssl dgst -sha256` を利用できます。OpenSSLの終了コードが0で、出力末尾が64桁の16進数であることを確認してください。大文字・小文字は区別しません。各ビルドスクリプトも6つを自動照合し、不一致で停止します。[RobotController_bin](https://github.com/social-robotics-lab/RobotController_bin)の配布JARが新型ストリーミング対応版かは未確認です。

### WindowsでのJavaビルド

Java 8 **JDK** の `java`・`javac`・`jar` をPATHに設定します。未導入なら [Temurin JDK 8](https://adoptium.net/temurin/releases/?version=8) などからPCのOS・CPUに適合するJDKを用意します。JREだけではビルドできません。

上記の依存用フォルダを置いた作業親フォルダで、次を実行します。clone先と出力先は未作成の名前を選びます。

```powershell
git clone https://github.com/social-robotics-lab/RobotController.git RobotController-src
if ($LASTEXITCODE -ne 0) { throw "clone失敗" }
Set-Location RobotController-src
java -version
javac -version
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./tools/build_phase_g.ps1 `
  -DependencyDirectory ../robotcontroller-deps `
  -OutputDirectory ../robotcontroller-java-build
```

出力先 `../robotcontroller-java-build` はスクリプトが自動生成するため、事前作成しません。依存用フォルダはリポジトリの隣です。既存の [tools/build_phase_g.ps1](tools/build_phase_g.ps1) は変更しません。READMEの未コミット編集や無関係な未追跡ファイルがあると停止するため、クリーンなチェックアウトを使います。

### macOS・LinuxでのJavaビルド

[tools/build_java.sh](tools/build_java.sh) をPOSIXシェルで実行します。macOSでは `/usr/bin/sh`、Edisonでは利用可能な `/bin/sh` を使えます。Bash固有構文や実行権限の付与は不要です。必要なものはJava 8 JDK、Git（production baselineを含む履歴）、標準的なシェル用ツール、およびSHA-256計算ツールです。スクリプトは `sha256sum` → `shasum -a 256` → `openssl dgst -sha256` の順に利用可能なものを選びます。選んだツールが計算に失敗した場合や64桁の16進数を取得できない場合は停止し、別ツールへ切り替えてエラーを隠しません。浅いcloneは使わないでください。

macOSでJDK 8を導入後、上記と同じ作業親フォルダから実行する例です。

```sh
(
set -eu
git clone https://github.com/social-robotics-lab/RobotController.git RobotController-src
cd RobotController-src
# main統合前は今回の作業ブランチを選びます。
git checkout codex/portable-java-build
export JAVA_HOME=$(/usr/libexec/java_home -v 1.8)
/usr/bin/sh tools/build_java.sh \
  --dependency-dir ../robotcontroller-deps \
  --output-dir ../robotcontroller-java-build
)
```

オプションは `--dependency-dir DIR` と `--output-dir NEW_DIR` の両方が必須、`--help` で説明を表示します。相対パスは**呼び出した作業ディレクトリ基準**です。出力先はリポジトリ外の未作成パスを指定し、その親ディレクトリはあらかじめ存在する必要があります。空フォルダやシンボリックリンクを含め、既存の出力先は再利用しません。パス中のコロン・改行は非対応です。

`JAVA_HOME` を指定すればその `bin/java`・`bin/javac`・`bin/jar`、未指定ならPATH上のものを使用します。javaとjavacの両方が1.8でなければ停止します。production baseline `bd299ae1bbc0d0514d5b60a0ca2d45125a01f1d6` の祖先関係、保護対象入力の同一性・未追跡入力の不存在、クリーンな作業ツリー、6依存JARのハッシュを検査してから出力を作成します。既存Windowsスクリプトの制約は変更しません。

### Javaの成果物と静的検証

両OSのビルドは同じ `src/` の全JavaソースをUTF-8・Java 8ターゲット・`-Xlint:all` でコンパイルし、出力先内に次の構成を生成します。

```text
RobotController/
├── RobotController.jar
├── System.properties
├── lib/
│   ├── core-2.2.jar
│   ├── gson-2.8.5.jar
│   ├── javase-2.2.jar
│   ├── jna-4.1.0.jar
│   ├── json-20180813.jar
│   └── sotalib.jar
└── native/                       （Javaビルド直後は空）
```

Manifestの `Main-Class` は `main.App`、`Class-Path` は次の順序です。JAR内では長い行が継続行に折り返されます。

```text
lib/core-2.2.jar lib/gson-2.8.5.jar lib/javase-2.2.jar lib/jna-4.1.0.jar lib/json-20180813.jar lib/sotalib.jar
```

シェル版はJARを静的に展開して、全クラスの一覧・内容がコンパイラ出力と一致すること、全クラスのmajor versionが52（Java 8）であること、`main/App.class` とManifest、コピー後の依存ハッシュ、設定ファイルの同一性を検証します。結果・HEAD・JDKバージョン・JARと設定ファイルのハッシュは `java-build-report.txt`、警告は `javac.log`、JAR処理は `jar.log`、クラス一覧は `classes.txt` に記録します。`classes/`・`inspect/` などは配布フォルダの外側です。失敗した出力は調査用に残し、最終行の `Build status: PASS` がないものは採用しません。再試行は新しい出力先を使います。

Windows版の報告は `phase-g-build-report.txt` です。Windows版と比較するときは、ソース一覧、クラス一覧（過去の受入時は23ソース・49クラス）、展開したManifest、6依存JARを照合します。JAR全体のSHA-256は生成日時・JDK等で変わり得るため一致を要求しません。

### EdisonのJNIビルド環境の準備

[native/Makefile](native/Makefile) を変更せず使用します。必要条件はIntel EdisonのYocto Linux、対象CPU/ABIに対応したJava 8 JDK（`javac`・`javah`・JNIヘッダ）、GCC、make、ALSA開発ヘッダ、既存の `/usr/lib/libasound.so.2` です。検証には `file`・`readelf`（binutils）と、SHA-256計算用の `openssl` 等も用意します。

操作者によるEdison実ビルドではJava 8 JDK **1.8.0_40**、GCC **4.9.1**、出荷時の `alsa-lib` **1.0.28-r0 / core2-32** を使用しました。JDKのパス例は `/home/vstone/java/jdk1.8.0_40` です。別の実機ではパス・版・アーキテクチャを確認してください。ALSAヘッダは後述の新規作業フォルダに準備します。

```sh
cat /etc/os-release
uname -m
command -v git gcc make file readelf openssl opkg ar tar
gcc --version
gcc -dumpmachine
make --version
# 実際に確認したパスを設定します（以下は過去の例）。
export JAVA_HOME=/home/vstone/java/jdk1.8.0_40
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
"$JAVA_HOME/bin/javah" -version
test -f "$JAVA_HOME/include/jni.h" && test -f "$JAVA_HOME/include/linux/jni_md.h"
test -f /usr/lib/libasound.so.2
file "$JAVA_HOME/bin/java" /usr/lib/libasound.so.2
readelf -h /usr/lib/libasound.so.2
# opkgが存在する場合のみ、導入済みパッケージを読み取り確認します。
command -v opkg >/dev/null && opkg list-installed
opkg print-architecture
```

不足する場合は次のように準備します。システムJDK・ランタイムライブラリは更新・置換しません。

- JDK: 実機イメージの提供元または信頼できる保管済み配布物から、Edisonの32-bit x86・Yoctoのlibcに適合するJava 8 **JDK** を取得し、新規作業フォルダへ展開します。配布元のハッシュ・利用条件を確認し、`JAVA_HOME` を指定します。PC用JDKや64-bit Linux JDKを流用しません。Edison用JDK配布URLは未確認です。
- GCC・make: 同じEdisonイメージのYocto BSP/SDK・保管済みフィードで、対象アーキテクチャ・libc・依存関係が一致する開発ツールを準備します。実機ビルドには**Edisonで実行できる**コンパイラが必要で、PC用クロスコンパイラだけでは不足します。取得URLと不足時の具体的な導入パッケージ一式は未確認です。適合性を確認できなければ作業を止め、イメージ情報・不足項目を報告します。
- ALSA: 出荷時の `alsa-lib` が **1.0.28-r0 / core2-32** の実機では、以下の確認済み開発パッケージを使用します。版・アーキテクチャが異なる実機では、そのまま適用せず互換性を確認してください。

開発パッケージは `alsa-lib-dev_1.0.28-r0_core2-32.ipk`、操作者が確認した取得先は [Edison core2-32フィード](http://repo.opkg.net/edison/repo/core2-32/) です。実機では `opkg download alsa-lib-dev` で取得できました。このコマンドは既存のopkgフィード設定・パッケージ索引を参照するため、新しい実機でも同じ取得元・版を利用できることを確認します。取得できない場合や別の版が選ばれた場合は停止し、適合する保存済みパッケージをPCから転送する方法も検討してください。フィード設定・システムパッケージを自動変更しません。

以下は操作者用の手動手順です。`headers` は未作成の名前を選びます。固定SHA-256と照合してから、`ar` で `data.tar.gz` を取り出し、作業フォルダ内だけに展開します。

```sh
(
set -eu
headers=/home/root/robotcontroller-alsa-headers-YYYYMMDD-01
mkdir "$headers"
cd "$headers"
opkg download alsa-lib-dev
package=alsa-lib-dev_1.0.28-r0_core2-32.ipk
test -f "$package"
output=$(openssl dgst -sha256 < "$package")
digest=$(printf '%s\n' "$output" | awk 'NR==1 {digest=$NF} END {if (NR!=1) exit 1; print tolower(digest)}')
test "$digest" = 81de5dfb29144afb0edecb6bfbed80c06fa88634ebee9b49a845496c3853acce
ar t "$package"
ar p "$package" data.tar.gz > data.tar.gz
tar -tzf data.tar.gz
mkdir unpack
tar -xzf data.tar.gz -C unpack
test -f unpack/usr/include/alsa/asoundlib.h
printf 'ALSA_INCLUDE_DIR=%s/unpack/usr/include\n' "$headers"
)
```

`opkg download` は取得だけに使用し、`opkg install`・`opkg upgrade` は実行しません。パッケージにライブラリやリンクが含まれていても `/usr/include`・`/usr/lib` へ配置せず、展開先の `usr/include` だけをビルド時に参照します。システム側のALSAは更新・置換しません。Makefileは既存の `/usr/lib/libasound.so.2` を直接リンクします。

Yoctoのパッケージはビルド対象・設定に依存します。[Yoctoのパッケージ資料](https://docs.yoctoproject.org/4.0.26/dev-manual/packages.html)は一般的な説明であり、現在のディストリビューション向け手順を古いEdisonにそのまま適用するものではありません。必要な配布物が見つからない場合は環境準備が残課題です。

### EdisonでJavaとJNIをビルドする手順（操作者用）

依存6JARと上記の開発環境を準備してから、既存配置とは別の新規作業ディレクトリで行います。`work` の名前は毎回変更し、以降は同じシェル内で実行します。以下のサブシェルは途中の失敗で停止します。

```sh
(
set -eu
work=/home/root/robotcontroller-build-YYYYMMDD-01
mkdir "$work"
cd "$work"
git clone https://github.com/social-robotics-lab/RobotController.git source
cd source
# main統合前は、今回の作業ブランチを明示します。
git checkout codex/portable-java-build
git rev-parse HEAD
# 実機で確認済みのパスを設定します。
export JAVA_HOME=/home/vstone/java/jdk1.8.0_40
export ALSA_INCLUDE_DIR=/home/root/robotcontroller-alsa-headers-YYYYMMDD-01/unpack/usr/include
test -f "$ALSA_INCLUDE_DIR/alsa/asoundlib.h"
sh tools/build_java.sh \
  --dependency-dir /home/root/robotcontroller-deps \
  --output-dir "$work/java-output"
# 必ずJavaビルド後に、未ビルドの隔離ソースで実行します。
test ! -e native/build && test ! -L native/build
test ! -e native/generated && test ! -L native/generated
if make -C native \
  JAVA_HOME="$JAVA_HOME" \
  ALSA_INCLUDE_DIR="$ALSA_INCLUDE_DIR" > "$work/jni-build.log" 2>&1; then
  cat "$work/jni-build.log"
else
  cat "$work/jni-build.log" >&2
  exit 1
fi
test -f native/build/librobotcontroller_alsa.so
printf 'JNI make exit status: 0\n' > "$work/jni-build-status.txt"
)
```

Java版は `java-output/RobotController/RobotController.jar`、JNI版は `source/native/build/librobotcontroller_alsa.so` に生成されます。この手順は両者を既存の稼働版へコピーしません。

**Gitなし・古いTLSの場合の代替**: PCでGitHubから通常cloneし、今回のブランチをcheckoutしてHEADを記録します。クリーンなcloneを `.git` と全履歴を含めてアーカイブ化し、操作者がSCP等でEdisonの新規作業フォルダへ転送します。Edison側でアーカイブ一覧と展開先を確認してから、新規の `source` として展開します。ソースZIPだけではproduction baseline検証に必要な履歴がないため不足します。PCで `git bundle create RobotController.bundle --all` として転送し、Edisonでローカルcloneする方法も使えます。EdisonにGit自体がなければ、互換GitをBSP/SDK等から準備する必要があります。Gitなしで検証を飛ばすモードはありません。

### Edison生成物の静的検証（起動しない）

上記と同じ `work` の絶対パスを設定し、操作者が実行します。

```sh
(
set -eu
work=/home/root/robotcontroller-build-YYYYMMDD-01
candidate="$work/java-output/RobotController"
so="$work/source/native/build/librobotcontroller_alsa.so"
test -f "$candidate/RobotController.jar"
test -f "$so"
cat "$work/java-output/java-build-report.txt"
cat "$work/java-output/manifest-unfolded.txt"
cat "$work/java-output/classes.txt"
cat "$work/java-output/javac.log"
cat "$work/jni-build.log"
cat "$work/jni-build-status.txt"
for artifact in "$candidate/RobotController.jar" "$candidate/System.properties" \
  "$candidate"/lib/*.jar "$so"; do
  openssl dgst -sha256 "$artifact" || exit 1
done > "$work/artifact-sha256.txt"
cat "$work/artifact-sha256.txt"
file "$so" /usr/lib/libasound.so.2
readelf -h "$so" > "$work/jni-elf-header.txt"
readelf -d "$so" > "$work/jni-dynamic.txt"
readelf -Ws "$so" > "$work/jni-symbols.txt"
cat "$work/jni-elf-header.txt" "$work/jni-dynamic.txt"
grep 'Java_utils_AlsaPcm_native' "$work/jni-symbols.txt"
grep 'snd_' "$work/jni-symbols.txt"
)
```

ハッシュは上表と照合し、Java報告の最終行付近の `Build status: PASS`、全クラスmajor version 52、Manifestの2項目、JAR内クラス一覧、コンパイルログとmake終了値0を確認します。警告は内容を確認し、未確認の警告を成功扱いしません。

ELFヘッダは `Type: DYN` の共有ライブラリであること、`Class`・`Data`・`Machine`・ABIが対象Edisonと既存 `libasound.so.2` に適合することを確認します（過去の対象は32-bit x86、ELF32・little endian・Intel 80386）。`NEEDED` に `libasound.so.2` があり、その他の依存ライブラリも実機上のものと適合することを確認します。`readelf -Ws` では以下の7つが**定義済みのGLOBALシンボル**（UNDではない）であることを確認します。

```text
Java_utils_AlsaPcm_nativeOpen
Java_utils_AlsaPcm_nativeWrite
Java_utils_AlsaPcm_nativeGetBufferFrames
Java_utils_AlsaPcm_nativeGetPeriodFrames
Java_utils_AlsaPcm_nativeDrain
Java_utils_AlsaPcm_nativeDrop
Java_utils_AlsaPcm_nativeClose
```

ALSAの `snd_pcm_open`・`snd_pcm_set_params`・`snd_pcm_get_params`・`snd_pcm_writei`・`snd_pcm_recover`・`snd_pcm_drain`・`snd_pcm_drop`・`snd_pcm_close`・`snd_strerror` は動的リンク用の未定義参照として存在し、実機のALSAで提供されることを確認します。静的検証では `ldd` やJVMによるライブラリロードは使いません。

2026年11月4日に受けた操作者の実機確認報告では、上記の開発ヘッダとJava 8 JDK 1.8.0_40・GCC 4.9.1を使用した `make -C native` が成功しました。生成物はELF32・little-endian・Intel 80386・Type DYNで、`libasound.so.2` への動的リンクとJNIエントリポイント7つを確認しています。`.so` のSHA-256は `1119b2666681885caa03c22c8f16118a2a849aa14b3b7158d1962500e716306b` で、Phase G受入済みバイナリと完全一致しました。詳細は[検証記録](docs/build-environment-validation-2026-11-02.md)を参照してください。

再ビルドした `.so` のSHA-256は記録しますが、別の環境で過去の受入済みバイナリとの完全一致を必須とはしません。異なるハッシュの生成物を稼働版へ自動的に置き換えません。**ビルド成功は実機動作確認ではありません。** EdisonでのJava本体のビルドは成功ログが提示されていないため未検証です。macOSでのビルドも未検証です。実機での起動・動作検証とmain統合は、今回とは別に結果を確認してから扱います。

## Sotaへの配置と起動（人間による手動操作のみ）

この節は既存の運用説明です。今回のビルド確認ではここに進まず、生成物の静的検証で止めて結果を報告してください。再ビルドしたJNIを過去の受入済みライブラリと同等の動作確認済みと扱ってはいけません。

**起動するだけで既存の初期化処理がロボットに作用します。** Sotaでは接続、`ServoOn`、初期姿勢、torque・LED設定が行われます。TCP待受と初期化は別スレッドであり、接続成功はロボット初期化完了の保証ではありません。安全な作業場所と操作者による確認が必要です。

[受入手順](docs/phase-g-acceptance.md)の前提条件・停止条件を確認し、既存のproduction配置を上書きしない隔離フォルダを使用してください。受入結果に記録された配置先は`/home/root/robotcontroller_phase_g_production_8e0502b`です。これは過去の配置記録であり、上書き先の指定ではありません。

上の構成に`native/librobotcontroller_alsa.so`を加えます。受入に使用したネイティブライブラリのSHA-256は次のとおりです。

```text
1119B2666681885CAA03C22C8F16118A2A849AA14B3B7158D1962500E716306B
```

JVMの作業ディレクトリにある`System.properties`を読み込みます。Sotaの設定例は次のとおりです。

```properties
ROBOT_TYPE=Sota
PORT=22222
```

ポート競合、ファイル・依存JAR・ネイティブライブラリのハッシュ、Java 8、停止手順を確認した後、人間が配置先のディレクトリで起動します。

```bash
java -Djava.library.path=./native -jar RobotController.jar
```

競合や予期しない動作があれば停止し、既存サービスの停止・設定変更で自動回避しないでください。自動エージェントは実機への接続・配置・起動・テストを行いません。

## 通信プロトコルの概要

TCPポートの初期値は`22222`です。TCPの1回の送受信とフレーム境界は一致しないため、受信側は指定バイト数がそろうまで繰り返し読み取る必要があります。

すべてのメッセージを次の形式で送ります。長さは本文のバイト数で、4バイトのヘッダ自身を含みません。

```text
[本文長: 4バイト、big-endian整数][本文: 指定バイト数]
```

長さはJavaのsigned intで解釈されます。負数となる`0x80000000`以上を送らないでください。最初の本文はコマンド名そのものです。改行・NUL終端・引用符は付けません。コマンド名はASCII、JSONもASCIIで表現すれば既存実装のデフォルトcharsetへの依存を避けられます。現行の従来経路はcharsetを明示しておらず、厳密なUTF-8検証を提供しません。

従来型は原則1接続1コマンドです。`audio_stream_v1`だけは最初のコマンド後も接続を保持し、複数の音声を順に処理できます。どちらも同じTCPポートを使用します。

## 従来型通信プロトコル

コマンドを第1フレーム、必要なペイロードを第2フレームとして送ります。ペイロード不要のコマンドには第2フレームを送りません。

| コマンド | 第2フレームの本文 | サーバーからの返信 |
|---|---|---|
| `play_wav` | WAVファイル全体のバイナリ | なし |
| `stop_wav` | 不要 | なし |
| `play_pose` | 姿勢のJSONオブジェクト | なし |
| `stop_pose` | 不要 | なし |
| `play_motion` | 姿勢オブジェクトのJSON配列 | なし |
| `stop_motion` | 不要 | なし |
| `play_idle_motion` | `Speed`・`Pause`を指定するJSONオブジェクト | なし |
| `stop_idle_motion` | 不要 | なし |
| `read_axes` | 不要 | 軸名と角度のJSONオブジェクトを1フレーム |

`read_axes`以外にはACK・成功・エラー・再生完了の応答はありません。切断や送信成功を動作完了の通知として扱わないでください。

### 姿勢・モーション・アイドル動作

姿勢は整数の`Msec`（ミリ秒）と、`ServoMap`または`LedMap`の少なくとも一方を含みます。サーボ値は各ロボットの変換処理で扱う角度（度）、LED値は0〜255の整数です。以下は書式の例であり、実機への実行指示ではありません。

```json
{"Msec":1000,"ServoMap":{"HEAD_Y":0},"LedMap":{"MOUTH":0}}
```

名前・角度範囲は機種に依存します。Sotaの軸名は`BODY_Y`、`L_SHOU`、`L_ELBO`、`R_SHOU`、`R_ELBO`、`HEAD_Y`、`HEAD_P`、`HEAD_R`です。LED名は`PWR_BTN_R/G/B`、`R_EYE_R/G/B`、`L_EYE_R/G/B`、`MOUTH`です（`R/G/B`はそれぞれ別キーの略記）。CommUなどの名前・変換範囲は[servo](src/servo)と[led](src/led)の機種別Converterを確認してください。範囲外値を丸める旧処理もありますが、不正値を前提にせずクライアント側で検証してください。

モーションは同じ姿勢形式の配列です。各要素を順番に投入し、要素ごとの`Msec`だけ待機します。ハードウェア上の完了通知は返しません。

```json
[{"Msec":500,"ServoMap":{"HEAD_Y":0}},{"Msec":500,"ServoMap":{"HEAD_Y":0}}]
```

アイドル動作は次の形式です。

```json
{"Speed":1.0,"Pause":1000}
```

省略時は`Speed=1.0`、`Pause=1000`です。組み込みの2姿勢を交互に使い、移動時間は`(int)(1000 / Speed)`ミリ秒、その後の待機は`Pause`ミリ秒です。正の有限なSpeedと非負のPauseをクライアント側で検証してください。現行実装には十分な範囲検証がありません。

`stop_pose`は現在角度を読み、100ミリ秒の姿勢として投入する旧処理です。`stop_motion`・`stop_idle_motion`は対応するFutureをcancelします。全キューを消去する安全停止や、開始前の停止の冪等性を保証するものではありません。

### 軸の読み取り

`read_axes`を送ると、次のようなJSON本文を4バイト長ヘッダ付きで受信します。キー順・空白は固定ではなく、機種と取得された軸によってキーが変わります。

```json
{"HEAD_Y":0,"HEAD_P":0,"HEAD_R":0,"BODY_Y":0,"L_SHOU":0,"L_ELBO":0,"R_SHOU":0,"R_ELBO":0}
```

値は機種別Converterで変換された整数の角度です。上記は応答書式の例で、実機観測値ではありません。

### 従来型WAV再生

`play_wav`はWAV全体を受信して作業ディレクトリの固定名`__temp_wav`へ保存し、外部プロセス`aplay`を起動します。再生終了を待つ応答はありません。WAVの対応形式は利用先の`aplay`と音声環境に依存します。

`stop_wav`には`killall aplay`を起動する旧処理があり、他の`aplay`にも影響し得ます。新型の`CANCEL`とは別機能であり、新型ストリームの停止には使用しません。

## 新型音声ストリーミング（audio_stream_v1）

### 接続とフレーミング

第1フレームの本文にASCIIの`audio_stream_v1`（15バイト）を送ります。接続を獲得できると`CONNECTION_READY`、他のストリーミング接続が保持中なら`BUSY`を返してその新規接続を閉じます。待機中でも接続枠を保持するため、同時に保持できるストリーミング接続は1つです。

`CONNECTION_READY`は音声用の接続枠を取得した意味です。この時点ではJNIライブラリのロードやALSAのopenは行いません。JVM起動時のロボット初期化による作用がないという意味ではありません。

以後の送信レコード・応答もすべて同じ4バイト長ヘッダ付きです。レコード種別は文字列ではなく本文先頭の1バイトです。JSONやWAVヘッダは送りません。

```text
最初のコマンド: 00 00 00 0F + ASCIIの audio_stream_v1
START:          00 00 00 01 01
DATA:           [4バイト長 = 1 + PCMバイト数] 02 [PCM]
END:            00 00 00 01 03
CANCEL:         00 00 00 01 04
ENDED応答:      00 00 00 02 80 03
```

### 音声フォーマットと送信速度

| 項目 | 固定仕様 |
|---|---|
| サンプルレート | 24,000 Hz |
| チャンネル | モノラル |
| サンプル | signed 16-bit little-endian PCM（S16_LE） |
| PCMフレーム | 1サンプル＝2バイト |
| PCMデータ速度 | 48,000 bytes/sec |
| DATAのPCM部分 | 2〜960バイト、偶数長 |
| DATA本文全体 | 種別1バイト＋PCM、3〜961バイト |

長さヘッダはbig-endian、PCMサンプルはlittle-endianです。フォーマット交渉やサンプルレート指定のフィールドはありません。異なる形式の音声は送信前に変換してください。

クライアントが48,000 bytes/secを基準にペーシングします。960バイトのPCMは20ミリ秒に相当します。標準クライアントは送信済みバイト数による絶対スケジュールを使い、1チャンク分を超えて遅れた場合は基準を現在時刻に移して追い付きの一括送信を避けます。ファイル全体を無制限に先送りしないでください。

サーバーのPCMキューは25チャンクです。最大長なら24,000バイト（0.5秒相当）ですが、これはALSA側のバッファ・処理中チャンク・TCPバッファを含まない上限です。投入は空き待ち20ミリ秒で失敗すると中止処理に進みます。別途、終端制御用の予約スロットがあります。JNIのALSA設定は遅延100,000マイクロ秒を要求しますが、実際のバッファ・periodサイズはデバイスに依存し、通信プロトコルでは通知しません。

DATAごとのACKも、現在のキュー残量・再生位置の通知もありません。クライアントは送信中もエラーを検出できるよう応答を監視し、エラーを受けたらDATA送信を止めます。

### 送信レコードと状態遷移

ここでの「待機」は接続獲得後または正常な終端後、「再生中」はSTARTが成功したストリームを表します。

| レコード | 本文の先頭 | 本文長 | 許される状態 | 成功時 |
|---|---|---:|---|---|
| START | `0x01` | 1 | 待機 | 新しいwriter・キュー・ALSAデバイスを用意し、STARTED → 再生中 |
| DATA | `0x02` | 3〜961、PCM部分は偶数長 | 再生中 | PCMを投入。成功応答なし |
| END | `0x03` | 1 | 再生中 | 残りのPCMを処理し、drain・close後にENDED → 待機 |
| CANCEL | `0x04` | 1 | 再生中 | 未処理PCMを破棄し、drop・close後にCANCELLED → 待機 |

STARTEDを待ってからDATAを送ります。ENDまたはCANCELを送ったら、対応する応答を待ってから次のSTARTを送ります。サーバーもこれらの終端処理中は次のレコードを読み進めません。STARTの重複、待機中のDATA・END・CANCELはPROTOCOL_ERRORです。CANCELは待機中に繰り返せる操作ではありません。

内部では開始中・終了処理中・失敗・クローズなどの状態も管理します。音声ごとのgenerationと新しいwriter・キュー・デバイスによって古い音声を分離します。切断時は活動中ストリームの中止・リソース解放を試み、正常に解放できた場合に接続枠を返します。切断は正常な再生完了通知の代替にはなりません。

### サーバー応答と再生完了の意味

応答本文は**常に2バイト**です。先頭はSTATUS `0x80`またはERROR `0x81`、次がコードです。ヘッダ込みでは6バイトになります。

| 応答 | 本文 | 意味 |
|---|---|---|
| CONNECTION_READY | `80 01` | 接続枠を獲得。まだ音声デバイスを開いていない |
| STARTED | `80 02` | ALSAデバイスのopen・設定が成功し、音声を受け入れる準備が完了 |
| ENDED | `80 03` | 受理済みPCMの処理、ALSAの正常なdrain、closeとwriter終了の待機が成功 |
| CANCELLED | `80 04` | 未処理PCMの破棄、ALSAのdrop・closeとwriter終了の待機が成功 |

DATAの送信成功はTCPへの送信処理が成功したことだけを表し、再生完了を保証しません。STARTEDも発音開始や全音声の再生終了を保証しません。

**ENDに対するENDEDを待つことで、正常な再生終了と次の音声の開始を同期できます。** サーバーは残りのPCMを処理し、`snd_pcm_drain()`と`snd_pcm_close()`の成功を待ってからENDEDを返します。外部マイクなどで物理的な音響出力の終了を直接測定した通知ではありません。

CANCELLEDは正常完走ではなく、中止処理の完了です。既に処理中の書き込みが終わるまで待つ場合があり、CANCELの送信直後に停止したとは判断できません。

### エラーとタイムアウト

| エラー | 本文 | 現行実装の扱い |
|---|---|---|
| BUSY | `81 01` | 接続枠を取得できず、新規接続を閉じる |
| PROTOCOL_ERROR | `81 02` | 不正な種別・長さ・状態遷移。cleanupを試み、接続を閉じる |
| AUDIO_ERROR | `81 03` | open・write・drain・drop・closeなどの音声処理失敗、または内部待機タイムアウト。接続を閉じる |
| QUEUE_OVERFLOW | `81 04` | PCMキューへの投入失敗。中止・cleanup成功後に返し、接続は待機に戻る |

ストリームのレコード本文は最大961バイトです。空本文、負数長、上限超過、途中で切れたヘッダ・本文、未知の種別、不正なPCM長を拒否します。ただし、最初のコマンドフレームは従来の読み取り経路であり、この961バイト制限の対象ではありません。

START・END・CANCELおよびcleanupの内部バリア待機設定は5,000ミリ秒です。これは各処理の待機制御であり、TCP read timeoutやネイティブ呼び出しの強制中断期限ではありません。サーバー側にソケットread timeoutは設定されていないため、クライアントで接続・送信・応答待ちに期限を設けてください。

**ENDが失敗・タイムアウト・切断した場合は、正常終了したものとして次の音声を再生しないでください。** CANCELLEDが得られない場合も中止完了は未確認です。エラー・予期しない応答・EOFでは送信を停止し、接続を閉じて状況を確認します。cleanupの完了が確認できない場合、サーバーは接続枠を保持して後続をBUSYにすることがあります。無制限再試行や強制的なデバイス解放は行わないでください。

QUEUE_OVERFLOW後は実装上同一接続でSTARTできますが、それまでの音声は中止されています。遅れて送ったDATAは待機中の不正入力になります。継続する場合も受信結果と送信状態を確認し、単に残りのPCMを送り続けないでください。ネットワーク障害などではエラー応答自体が届かない場合もあります。

## 通信シーケンス例

以下の矢印はすべて長さヘッダ付きフレームです。DATAには成功応答がありません。

### 通常の音声再生

```text
クライアント                         RobotController
  |-- audio_stream_v1 ----------------->|
  |<---------------- CONNECTION_READY --|
  |-- START --------------------------->|
  |<------------------------- STARTED --|
  |-- DATA（PCM、速度制御）------------->|
  |-- DATA（PCM、速度制御）------------->|
  |-- END ----------------------------->|
  |                    残りPCM → drain → close → writer終了
  |<--------------------------- ENDED --|
```

### 再生途中のキャンセルと再開

```text
接続 → audio_stream_v1 → CONNECTION_READY
START → STARTED → DATA → DATA → CANCEL → CANCELLED
START → STARTED → 別の音声のDATA → END → ENDED
```

CANCELLEDを受信するまで新しいSTARTを送りません。CANCELは再生中ストリームを中止し、その続きから再開するpause/resumeではありません。

### 2文以上の連続再生

```text
接続 → audio_stream_v1 → CONNECTION_READY
START → STARTED → 1文目のDATAを順次送信 → END → ENDEDを確認
START → STARTED → 2文目のDATAを順次送信 → END → ENDEDを確認
START → STARTED → 3文目のDATAを順次送信 → END → ENDEDを確認
接続を閉じる
```

同じTCP接続を維持し、文ごとに新しいSTARTを使います。先のENDEDが確認できなければ次の文に進みません。

### Pythonでのフレーム処理

以下は実機への接続・実行を含まないヘルパー例です。ソケットのタイムアウト設定とエラー応答の処理は呼び出し側で行います。

```python
import struct


def send_frame(sock, body):
    sock.sendall(struct.pack(">i", len(body)) + body)


def receive_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise EOFError("フレーム受信中に切断されました")
        data.extend(part)
    return bytes(data)


def receive_stream_response(sock):
    size = struct.unpack(">i", receive_exact(sock, 4))[0]
    if size != 2:
        raise ValueError("応答本文長が不正です")
    body = receive_exact(sock, 2)
    if body[0] == 0x81:
        raise RuntimeError("サーバーエラー: 0x%02x" % body[1])
    if body[0] != 0x80 or body[1] not in (1, 2, 3, 4):
        raise ValueError("未知の応答です")
    return body[1]  # 呼び出し側で期待した状態コードか確認する
```

送信本文はコマンドなら`b"audio_stream_v1"`、STARTなら`b"\x01"`、DATAなら`b"\x02" + pcm`、ENDなら`b"\x03"`、CANCELなら`b"\x04"`です。受信をDATAのたびに待つと、成功時には応答がないため停止してしまいます。送信とエラー監視を適切に組み合わせてください。ペーシングと終端待ちを含む既存クライアントは[tools/phase_g_audio_client.py](tools/phase_g_audio_client.py)を参照してください。

## 互換性と現在の制限事項

- 従来型の9コマンドは維持されています。新型は明示的な`audio_stream_v1`コマンドで選択する独立した音声経路です。
- `play_wav`と新型ストリーミングに共通の音声デバイス排他制御はありません。同時利用はデバイス競合の可能性があるため避けてください。
- pause/resumeは未実装です。中止はCANCEL、次の音声は新しいSTARTを使います。
- ストリーミングの同時保持は1接続です。認証・TLSや接続全体の上限、従来経路の堅牢な入力検証を提供する実装ではありません。信頼できるネットワークで使用し、不正・過大な従来フレームを送らないでください。
- 起動時のServoOn・姿勢・torque・LED制御、従来停止処理、無制限の接続処理用スレッドなどの旧挙動は残っています。このREADME更新で安全性を改善したものではありません。
- SotaのPhase Gでは短い音声の再生・口LED同期、中止と別音声の再開、BUSY、不正状態、切断後の再接続が操作者によって確認されています。CommUの新型経路や任意の環境・長時間再生の信頼性を保証する結果ではありません。
- 長時間再生の調査ではALSA XRUN（`snd_pcm_writei`の`-EPIPE`）に伴う音声途切れが観察されています。回復処理の成功は音声が途切れなかった意味ではなく、まれな発生条件と根本原因は未解決です。

## 関連ドキュメントと検証

- [ビルド環境整備のオフライン検証結果・残課題](docs/build-environment-validation-2026-11-02.md)
- [macOS・Linux用Javaビルド](tools/build_java.sh)
- [ビルドスクリプトのオフライン試験](tools/test_build_java.sh)（実行: `sh tools/test_build_java.sh /path/to/deps`。ローカルcloneと生成物を一時フォルダに残します。実機には接続しません）
- [Phase Gの手動受入手順・停止条件](docs/phase-g-acceptance.md)
- [2026年9月16日の実機受入結果](docs/phase-g-result-2026-09-16.md)
- [PC用ビルドスクリプト](tools/build_phase_g.ps1)
- [JNIビルド定義](native/Makefile)
- [TCPコマンド・レコード・応答コード](src/main/TCPServer.java)
- [フレーム読み書き](src/main/ServerIO.java)
- [音声ストリームの所有権・終了処理](src/utils/StreamingAudioPlayer.java)
- [Java側ALSA境界](src/utils/AlsaPcm.java)
- [ALSA JNI実装](native/robotcontroller_alsa_jni.c)
- [従来型クライアントの例](https://github.com/social-robotics-lab/robotcontroller_client)

PC上のオフライン確認には`python tools/test_phase_g_audio_client.py`を使用できます。これはlocalhostの偽サーバーとの試験であり、実機を必要としません。Java側にもfake deviceを使う[test/](test)があり、`utils.StreamingAudioPlayerTest`は14群、`main.AudioStreamingProtocolTest`は16群です。これらの成功は実機の安全性やXRUN問題の解決を証明しません。実機試験は受入手順を確認した人間だけが実施します。
