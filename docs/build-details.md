# ビルドの詳細技術資料

この文書はREADMEから移管したビルド技術情報と、Windows開発用ビルドの仕様です。初心者向けの順序付き手順は[README](../README.md#robotcontrollerのビルド方法)、CA証明書の設定は[別文書](git-certificate-setup.md)を参照してください。

## 正式ビルドと開発用ビルド

| 項目 | build_java.sh | build_phase_g.ps1 | build_java_dev.ps1 |
|---|---|---|---|
| 用途 | macOS/Linux/Edisonの厳格なビルド | WindowsのPhase G正式ビルド | Windowsで編集中のJavaをビルド |
| Java 8 JDK・依存6JARの固定SHA-256 | 検査 | 検査 | 検査 |
| production baselineの祖先・入力一致 | 要求 | 要求 | 要求しない |
| 未コミットJava変更 | 拒否 | 拒否 | 許可（追加Javaも対象） |
| 作業ツリー | クリーンを要求 | Phase G準備5ファイルのみ例外、それ以外は拒否 | クリーンを要求しない |
| 全classのmajor version 52・格納内容の比較 | 検査 | Java 8ターゲットで生成、全classの事後走査はしない | 検査 |
| Manifest・依存のコピー | 検査 | 検査 | 検査（コピー後のハッシュも照合） |
| JNI | ビルド・配置・ロードしない | 同左 | 同左 |
| 報告 | java-build-report.txt | phase-g-build-report.txt | java-dev-build-report.txt |

厳格なビルドで作業ツリーを検査するのは、受入済みproduction入力（baseline `bd299ae1bbc0d0514d5b60a0ca2d45125a01f1d6`）に未記録の変更や追加ファイルが混入することを防ぐためです。開発用のPASSはJava成果物の静的検証成功を表し、受入済みソースとの一致・実機動作・リリース受入を証明しません。既存2スクリプトの制約は変更していません。

### Windows開発用スクリプトの入出力

Windows PowerShell 5.1で、以下をリポジトリ直下から実行します。相対パスは呼び出し時の作業ディレクトリ基準です。`JAVA_HOME` があればそのbinを優先し、なければPATHの `java`・`javac`・`jar` を使用します。Gitも必要です。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\build_java_dev.ps1 `
  -DependencyDirectory ../robotcontroller-lib `
  -OutputDirectory ../robotcontroller-output
```

両引数は必須です。出力先の親は存在する必要があり、出力先自体は未作成にします。自身や別のGitリポジトリ内への出力、既存ディレクトリ・ファイルへの出力を拒否します。パスの別名でこの制限を回避できないよう、出力先祖先のjunction・symlink（reparse point）も拒否します。通常の実ディレクトリを指定してください。

現在の `src/` 配下の全JavaファイルをUTF-8・`-source 1.8 -target 1.8 -Xlint:all` でコンパイルします。23ソース・49クラスは現行ソースの測定値であり、将来の開発でも固定数を要求するものではありません。全コンパイラ出力とJAR内classについてmagicとmajor version 52を検査し、一覧と内容のSHA-256を比較します。ManifestのMain-Class・Class-Path、コピーした依存6JARと設定のハッシュも確認します。入力ファイルは書き換えず、ビルド中にソース・設定が変化した場合も停止します。

出力直下には `classes/`、`MANIFEST.MF`、`javac.log`、`jar.log`、`java-dev-build-report.txt` を作成します。配布フォルダ `RobotController/` の構成は後述の正式ビルドと共通で、`native/` は空です。レポートには開発用であること、JDK、ソース・class数、警告数、検証項目、JAR・依存ハッシュ、最終 `Build status: PASS` を記録します。失敗時は非ゼロ終了し、出力作成後の失敗ではINCOMPLETEのレポートとログを残します。次回は新しい出力名を使います。

## 検証結果の読み方

- [2026年11月2日開始の検証記録](build-environment-validation-2026-11-02.md)は履歴資料です。追補に11月4日のJNI成功報告、11月5日のBusyBox od対応があります。記録時点の「未検証」を今回の現状と混同しません。
- 2026年11月12日の操作者報告では、新しいEdisonでJava全体の23ソース・49クラス、全major version 52、エラー0、依存6JAR・Manifest、最終 `Build status: PASS` が確認されています。JNIは以前の操作者報告でPhase G受入済みバイナリとSHA-256一致が確認されています。自動エージェントが実機で再実行した結果ではありません。
- 2026年9月16日の[Phase G実機受入結果](phase-g-result-2026-09-16.md)と、ビルド成功は別の記録です。ビルドだけでXRUNの解消や機体の安全性は判断できません。

### 今回のPC検証（2026年11月12日・日本時間）

Windows PowerShell 5.1、Temurin Java/Javac 1.8.0_502、既存のPC生成物から固定SHA-256を再照合した依存6JARを使用しました。開発用回帰試験17件が成功し、未コミット変更・baselineから変更したコミットのビルド、依存/JDK/コンパイル/不正classの拒否、出力先保護、元のproduction入力の不変を確認しました。Java 8以外のjava/javacの拒否は模擬コマンドによる検証です。

変更していないWindows正式版、シェル版の既存オフライン試験（通常ハッシュとOpenSSLのみの経路を含む）も成功しました。現行ソースは23件・49クラス・エラー0・既存警告47件でした。シェル版の初回確認はWindows checkoutのCRLF変換で構文エラーになったため、既存スクリプトを編集せず `core.autocrlf=false` の隔離cloneで構文検査と回帰試験を実施しました。Javaのfake-device回帰14群＋16群、Pythonのlocalhost回帰44件も成功しました。

文書のPowerShell/sh実行例35ブロックの構文、相対リンクとアンカー44件、見出し階層、通信説明・サンプル・制限事項の保持、移管元の技術情報の保持を確認しました。実機への接続・転送・JNIビルド・起動・操作、CA設定の実機再検証、macOS/Linux/Edisonでの今回の実行は行っていません。

## ビルド環境の検証方法とよくある失敗

- 正式シェル版：`sh -n tools/build_java.sh`、`sh -n tools/test_build_java.sh`、利用可能なら `dash -n`、`git diff --check`、`sh tools/test_build_java.sh /path/to/deps`。ローカルcloneと出力を一時フォルダに残し、実機へ接続しません。OpenSSLのみのPATHとBusyBox odのオプション制約を模擬する試験も含みます。
- Windows開発用：`powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/test_build_java_dev.ps1 -DependencyDirectory ../robotcontroller-lib`。一時cloneで通常ビルド、未コミット/コミット済み変更、依存欠落・不一致、JDK拒否、コンパイル・成果物検証の失敗、出力先の保護を検査します。試験は偽JDKも使いますが、通常ビルドは実Java 8で実行します。
- 既存Python回帰：`python -B tools/test_phase_g_audio_client.py`。localhostの偽サーバーを使用します。Javaにもfake deviceの[test/](../test)があり、`utils.StreamingAudioPlayerTest` は14群、`main.AudioStreamingProtocolTest` は16群です。

| 症状 | 対処 |
|---|---|
| java/javacが1.8でない・jarが見つからない | Java 8 JDKのJAVA_HOME/PATHを確認。JREだけでは不可 |
| dependency missing / hash mismatch | 6ファイル名・取得元・固定SHA-256を確認。gson 2.6.1を改名しない |
| Worktree must be clean / baseline differs | 正式版は別のクリーンなcheckoutを使う。編集中のJavaは開発用スクリプトでビルドする |
| Output already exists / Git内の出力 | リポジトリ外に新しい出力名を指定。既存出力は削除・再利用しない |
| javac failed | 出力先のjavac.logを確認。開発用は修正後に新しい出力先で再試行 |
| 証明書検証失敗 | [CA設定](git-certificate-setup.md)を確認。TLS検証を無効化しない |
| 古いGit/TLS・Git履歴不足 | 後述の履歴付きPC clone転送を使用。アーカイブだけでbaseline検査を回避しない |
| ALSAヘッダ・javah不足 | 対象Edisonに適合するJDK/開発ヘッダを準備。システムALSAは置換しない |
| JNIのABI/依存が不一致 | 配置・ロードせず対象環境を確認。file/readelfで静的検証する |
| 起動時のポート競合・予期しない動作 | 操作者が停止手順を確認。既存サービスを自動停止しない |

旧READMEの技術情報は本資料の以下の節に移管しています。依存の取得・照合、macOS例、Gitなし環境への全履歴転送、JNIの7シンボルとALSA参照、過去の配置先なども保持しています。以下の手動コマンドのパス例は、READMEの簡易手順と異なる独立した作業例です。

## 厳格なビルドの入力・出力と環境

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

**6つとも**以下のSHA-256と照合します。値の基準は変更しない [Windowsビルドスクリプト](../tools/build_phase_g.ps1) です。ファイル名を変更して別バージョンを同じものとして扱ってはいけません。不一致なら中止してファイル名・実測ハッシュ・取得元を報告し、要件の緩和や別JARへの自動切替を行いません。

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

出力先 `../robotcontroller-java-build` はスクリプトが自動生成するため、事前作成しません。依存用フォルダはリポジトリの隣です。既存の [tools/build_phase_g.ps1](../tools/build_phase_g.ps1) は変更しません。READMEの未コミット編集や無関係な未追跡ファイルがあると停止するため、クリーンなチェックアウトを使います。

### macOS・LinuxでのJavaビルド

[tools/build_java.sh](../tools/build_java.sh) をPOSIXシェルで実行します。macOSでは `/usr/bin/sh`、Edisonでは利用可能な `/bin/sh` を使えます。Bash固有構文や実行権限の付与は不要です。必要なものはJava 8 JDK、Git（production baselineを含む履歴）、標準的なシェル用ツール、およびSHA-256計算ツールです。スクリプトは `sha256sum` → `shasum -a 256` → `openssl dgst -sha256` の順に利用可能なものを選びます。選んだツールが計算に失敗した場合や64桁の16進数を取得できない場合は停止し、別ツールへ切り替えてエラーを隠しません。浅いcloneは使わないでください。

macOSでJDK 8を導入後、上記と同じ作業親フォルダから実行する例です。

```sh
(
set -eu
git clone https://github.com/social-robotics-lab/RobotController.git RobotController-src
cd RobotController-src
# 最新mainを使用します（履歴を省略しないclone）。
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

[native/Makefile](../native/Makefile) を変更せず使用します。必要条件はIntel EdisonのYocto Linux、対象CPU/ABIに対応したJava 8 JDK（`javac`・`javah`・JNIヘッダ）、GCC、make、ALSA開発ヘッダ、既存の `/usr/lib/libasound.so.2` です。検証には `file`・`readelf`（binutils）と、SHA-256計算用の `openssl` 等も用意します。

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
# 最新mainを使用します。
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

**Gitなし・古いTLSの場合の代替**: PCでGitHubから履歴付きcloneし、ビルド対象のコミットをcheckoutしてHEADを記録します。クリーンなcloneを `.git` と全履歴を含めてアーカイブ化し、操作者がSCP等でEdisonの新規作業フォルダへ転送します。Edison側でアーカイブ一覧と展開先を確認してから、新規の `source` として展開します。ソースZIPだけではproduction baseline検証に必要な履歴がないため不足します。PCで `git bundle create RobotController.bundle --all` として転送し、Edisonでローカルcloneする方法も使えます。EdisonにGit自体がなければ、互換GitをBSP/SDK等から準備する必要があります。Gitなしで検証を飛ばすモードはありません。

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

2026年11月4日に受けた操作者の実機確認報告では、上記の開発ヘッダとJava 8 JDK 1.8.0_40・GCC 4.9.1を使用した `make -C native` が成功しました。生成物はELF32・little-endian・Intel 80386・Type DYNで、`libasound.so.2` への動的リンクとJNIエントリポイント7つを確認しています。`.so` のSHA-256は `1119b2666681885caa03c22c8f16118a2a849aa14b3b7158d1962500e716306b` で、Phase G受入済みバイナリと完全一致しました。詳細は[検証記録](build-environment-validation-2026-11-02.md)を参照してください。

再ビルドした `.so` のSHA-256は記録しますが、別の環境で過去の受入済みバイナリとの完全一致を必須とはしません。異なるハッシュの生成物を稼働版へ自動的に置き換えません。**ビルド成功は実機動作確認ではありません。** 2026年11月12日に操作者からEdison上のJava全体ビルド成功（23ソース・49クラス・major version 52・依存6JAR・Manifest・最終PASS）が報告され、その後mainへ統合されました。これは操作者の報告であり、今回のPC試験による実機再検証ではありません。macOSでの実ビルドは未検証です。

## Sotaへの配置と起動（人間による手動操作のみ）

この節は既存の運用説明です。今回のビルド確認ではここに進まず、生成物の静的検証で止めて結果を報告してください。再ビルドしたJNIを過去の受入済みライブラリと同等の動作確認済みと扱ってはいけません。

**起動するだけで既存の初期化処理がロボットに作用します。** Sotaでは接続、`ServoOn`、初期姿勢、torque・LED設定が行われます。TCP待受と初期化は別スレッドであり、接続成功はロボット初期化完了の保証ではありません。安全な作業場所と操作者による確認が必要です。

[受入手順](phase-g-acceptance.md)の前提条件・停止条件を確認し、既存のproduction配置を上書きしない隔離フォルダを使用してください。受入結果に記録された配置先は`/home/root/robotcontroller_phase_g_production_8e0502b`です。これは過去の配置記録であり、上書き先の指定ではありません。

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


## 実装と既存資料への参照

- [厳格なシェル版](../tools/build_java.sh)・[Windows正式版](../tools/build_phase_g.ps1)・[開発用Windows版](../tools/build_java_dev.ps1)
- [JNIビルド定義](../native/Makefile)
- [TCPコマンド・レコード・応答コード](../src/main/TCPServer.java)・[フレーム読み書き](../src/main/ServerIO.java)
- [音声ストリームの所有権・終了処理](../src/utils/StreamingAudioPlayer.java)
- [Java側ALSA境界](../src/utils/AlsaPcm.java)・[ALSA JNI実装](../native/robotcontroller_alsa_jni.c)
- [Phase G手動受入手順・停止条件](phase-g-acceptance.md)・[受入結果テンプレート](phase-g-result-template.md)
