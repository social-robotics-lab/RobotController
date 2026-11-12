# RobotController

## 概要

Sota・CommUなどをTCP経由で制御するJavaプログラムです。従来のWAV再生・姿勢・モーション制御に加え、`audio_stream_v1`によるPCM音声ストリーミングに対応しています。

Sotaでの音声ストリーミングは実機受入済みです。長時間再生時のまれなALSA XRUN・音声途切れの調査は継続中です。受入結果は[検証記録](docs/phase-g-result-2026-09-16.md)を参照してください。

## 対応ロボットと動作環境

- 従来の制御経路にはSota・CommU・Dogの実装があります。`System.properties`の`ROBOT_TYPE`で選択します。
- 新型ストリーミングの実機受入対象はIntel Edison上のSotaです。CommU・Dogでの新型ストリーミング動作は未検証です。
- ビルド・実行には**Java 8**が必要です。受入時のPCはTemurin OpenJDK 1.8.0_502、EdisonはJava 1.8.0_40でした。
- ストリーミングには、対象機のABIに適合するJNIライブラリ`librobotcontroller_alsa.so`とALSA環境が必要です。JNIはALSAの`default`を開き、`/usr/lib/libasound.so.2`を使用します。
- 従来型`play_wav`には`aplay`が必要です。新型ストリーミングは`aplay`を使用しません。

## RobotControllerのビルド方法

RobotControllerは、音声ストリーミング再生にALSA（Advanced Linux Sound Architecture）を使用します。そのため、Javaプログラム本体の `RobotController.jar` に加えて、JavaからALSAを呼び出すJNIライブラリ `librobotcontroller_alsa.so` が必要です。

標準の方法では、JavaプログラムとJNIライブラリの両方をSotaのIntel Edison上でビルドします。Javaの開発中は、GitHubへコミットする前にWindows PCでJavaプログラムだけをビルドし、JARをEdisonに転送することもできます。

以下の2つの方法を説明します。

1. Edison上でJavaプログラムとJNIライブラリをビルドする方法（標準）
2. Windows PC上でJavaプログラムをビルドする方法（開発時のみ）

実機への接続・転送・ビルド・起動は、操作者が手動で行います。各コマンドが失敗したら次へ進まず、[詳細資料](docs/build-details.md)を確認してください。既存の作業用フォルダがある場合は別名を使い、以下のパスも読み替えます。

### Edison上でJavaの実行ファイルとJNIライブラリをビルドする方法

前提は、SotaのIntel Edison、Java 8 **JDK**、Git、curl、OpenSSL、GCC、make、opkg、ar、tarです。以下はEdisonのsh/bashで実行します。例はJDKが `/home/vstone/java/jdk1.8.0_40`、出荷時ALSAが `1.0.28-r0 / core2-32` の環境を対象とします。異なる環境やツールが不足する場合は、先に[JNIの環境準備](docs/build-details.md#edisonのjniビルド環境の準備)を確認してください。

**1. 作業ディレクトリを作る**

```sh
mkdir -p /home/root/robotcontroller-build
cd /home/root/robotcontroller-build
```

**2. 外部JARを準備する**

作業ディレクトリで、新しい依存用フォルダを作ります。

```sh
mkdir robotcontroller-lib
cd robotcontroller-lib
cp /home/vstone/lib/core-2.2.jar \
   /home/vstone/lib/javase-2.2.jar \
   /home/vstone/lib/jna-4.1.0.jar \
   /home/vstone/lib/sotalib.jar .
```

残り2個はMaven Centralから取得します。CA証明書 `/home/root/git-cacert.pem` が未設定なら、先に[証明書の設定手順](docs/git-certificate-setup.md)を行ってください。

```sh
curl --cacert /home/root/git-cacert.pem \
  --fail --location --show-error \
  -o gson-2.8.5.jar \
  https://repo.maven.apache.org/maven2/com/google/code/gson/gson/2.8.5/gson-2.8.5.jar

curl --cacert /home/root/git-cacert.pem \
  --fail --location --show-error \
  -o json-20180813.jar \
  https://repo.maven.apache.org/maven2/org/json/json/20180813/json-20180813.jar
```

直接取得できない場合は、下のWindows手順で2個をダウンロードし、Windows PowerShellから次のように転送します。`$robotIp` はSotaのIPアドレスです。

```powershell
$robotIp = Read-Host "SotaのIPアドレス"
scp .\gson-2.8.5.jar .\json-20180813.jar "root@${robotIp}:/home/root/robotcontroller-build/robotcontroller-lib/"
if ($LASTEXITCODE -ne 0) { throw "SCP失敗" }
```

必要なのは6個すべてです。Sota標準の `gson-2.6.1.jar` は代用できません。SHA-256はビルドスクリプトが自動照合します。

**3. GitHubからソースコードを取得する**

Edisonのシェルへ戻り、次を実行します。

```sh
cd /home/root/robotcontroller-build
git clone \
  https://github.com/social-robotics-lab/RobotController.git \
  robotcontroller-src
```

**4. Javaプログラムをビルドする**

```sh
cd /home/root/robotcontroller-build/robotcontroller-src
export JAVA_HOME=/home/vstone/java/jdk1.8.0_40
sh tools/build_java.sh \
  --dependency-dir ../robotcontroller-lib \
  --output-dir /home/root/robotcontroller-build/robotcontroller-output
```

この正式ビルドはクリーンなGit作業ツリーと、受入済み基準と同一のproduction入力を要求します。出力先は事前作成しません。再ビルドでは `robotcontroller-output-02` など、新しい名前を使います。成功を次で確認します。

```sh
grep '^Build status: PASS$' /home/root/robotcontroller-build/robotcontroller-output/java-build-report.txt
```

**5. ALSA開発ヘッダを取得する**

```sh
mkdir /home/root/robotcontroller-build/robotcontroller-alsa-dev
cd /home/root/robotcontroller-build/robotcontroller-alsa-dev
opkg download alsa-lib-dev
openssl dgst -sha256 alsa-lib-dev_1.0.28-r0_core2-32.ipk
```

表示されたSHA-256が以下と一致することを確認してください。版・アーキテクチャ・ハッシュが異なる場合は展開せず、対象環境と取得元を確認します。

```text
81de5dfb29144afb0edecb6bfbed80c06fa88634ebee9b49a845496c3853acce
```

一致を確認した後、同じディレクトリで展開します。

```sh
ar p alsa-lib-dev_1.0.28-r0_core2-32.ipk data.tar.gz > data.tar.gz
mkdir unpack
tar -xzf data.tar.gz -C unpack
test -f unpack/usr/include/alsa/asoundlib.h
```

展開先のヘッダだけを使用します。`opkg install` やシステムALSAライブラリの置換は不要です。

**6. JNIライブラリをビルドする**

Javaビルドが成功してから、同じソースフォルダで実行します。

```sh
cd /home/root/robotcontroller-build/robotcontroller-src
make -C native \
  JAVA_HOME=/home/vstone/java/jdk1.8.0_40 \
  ALSA_INCLUDE_DIR=/home/root/robotcontroller-build/robotcontroller-alsa-dev/unpack/usr/include
```

makeが成功したら、生成したライブラリを今回の出力へコピーして確認します。

```sh
test -f native/build/librobotcontroller_alsa.so
cp native/build/librobotcontroller_alsa.so \
  /home/root/robotcontroller-build/robotcontroller-output/RobotController/native/
ls -l /home/root/robotcontroller-build/robotcontroller-output/RobotController/native/librobotcontroller_alsa.so
```

ABI・動的リンク・JNIシンボルの詳しい確認方法は[生成物の静的検証](docs/build-details.md#edison生成物の静的検証起動しない)を参照してください。ビルド成功と実機動作確認は別です。

**7. 配布用ファイルを作る**

```sh
cd /home/root/robotcontroller-build/robotcontroller-output
tar czvf RobotController.tar.gz RobotController
ls -l RobotController.tar.gz
```

アーカイブには次の構成が入ります。外部JARを含むローカル配布用です。第三者ライセンスの確認なしに公開GitHubへアップロードしないでください。

```text
RobotController/
├── RobotController.jar
├── System.properties
├── lib/                         # 外部JAR 6個
└── native/
    └── librobotcontroller_alsa.so
```

### Windows PC上でJavaの実行ファイルをビルドする方法（開発時のみ）

Windows PowerShell、Git、OpenSSHのscp、Java 8 **JDK** が必要です。`JAVA_HOME` を設定するか、Java 8の `java`・`javac`・`jar` をPATHへ追加し、確認します。JREだけではビルドできません。

```powershell
java -version
javac -version
```

両方が `1.8` であることを確認してください。以下はWindows PowerShellで実行します。

**1. 作業フォルダと外部JARを準備する**

```powershell
$ErrorActionPreference = "Stop"
$work = Join-Path $env:USERPROFILE "Workspace\robotcontroller-build"
New-Item -ItemType Directory -Path $work -Force | Out-Null
Set-Location $work
New-Item -ItemType Directory -Path robotcontroller-lib | Out-Null
Set-Location robotcontroller-lib
$robotIp = Read-Host "SotaのIPアドレス"
foreach ($name in @("core-2.2.jar", "javase-2.2.jar", "jna-4.1.0.jar", "sotalib.jar")) {
  scp "root@${robotIp}:/home/vstone/lib/$name" .
  if ($LASTEXITCODE -ne 0) { throw "SCP失敗: $name" }
}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -UseBasicParsing `
  -Uri https://repo.maven.apache.org/maven2/com/google/code/gson/gson/2.8.5/gson-2.8.5.jar `
  -OutFile gson-2.8.5.jar
Invoke-WebRequest -UseBasicParsing `
  -Uri https://repo.maven.apache.org/maven2/org/json/json/20180813/json-20180813.jar `
  -OutFile json-20180813.jar
```

Edisonへ2個のJARを転送する代替手順だけを行う場合は、このディレクトリで前述のscpを実行します。

**2. ソースを取得してJavaプログラムをビルドする**

```powershell
Set-Location $work
git clone https://github.com/social-robotics-lab/RobotController.git robotcontroller-src
if ($LASTEXITCODE -ne 0) { throw "clone失敗" }
Set-Location robotcontroller-src
# Javaを修正した後も、コミットせずこのコマンドでビルドできます。
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\build_java_dev.ps1 `
  -DependencyDirectory ../robotcontroller-lib `
  -OutputDirectory ../robotcontroller-output
if ($LASTEXITCODE -ne 0) { throw "開発用ビルド失敗" }
Get-Content ../robotcontroller-output/java-dev-build-report.txt
```

最後の `Build status: PASS` を確認します。出力先はリポジトリ外の未作成フォルダにしてください。再ビルド時は別名を指定します。

このスクリプトは現在の作業ツリー（未コミットのJava変更を含む）をコンパイルし、依存6JARのSHA-256、Java 8 class形式、Manifestを検証します。受入済みソースとの一致は検証しません。正式ビルドには [build_java.sh](tools/build_java.sh) または [build_phase_g.ps1](tools/build_phase_g.ps1) を使います。[違いと詳細](docs/build-details.md#正式ビルドと開発用ビルド)も参照してください。

**3. 開発用JARだけをEdisonへ転送する**

Edisonの `/home/root/RobotController/` に、外部JAR・設定ファイル・JNIライブラリを含む実行環境が準備済みであることが前提です。次は既存JARを上書きします。開発用機体と転送先を確認した操作者が、必要な退避を行ってから手動で実行してください。

```powershell
Set-Location (Join-Path $work "robotcontroller-output\RobotController")
scp RobotController.jar "root@${robotIp}:/home/root/RobotController/"
if ($LASTEXITCODE -ne 0) { throw "SCP失敗" }
```

JNIをWindowsでビルドする手順や自動デプロイは含みません。

## RobotControllerの起動と動作確認

起動はビルド検証とは別の実機操作です。**起動だけでもサーボやLEDが初期化される可能性があります。** 操作者が[手動受入手順](docs/phase-g-acceptance.md)を読み、安全な場所、設定、停止方法、既存RobotControllerとのポート競合を確認してから実行します。既存サービスを自動停止して回避しないでください。

実行環境が配置済みなら、Edisonのシェルで次を実行します。

```sh
cd /home/root/RobotController
java -Djava.library.path=./native -jar RobotController.jar
```

今回ビルドした出力から直接起動する場合は、代わりに `/home/root/robotcontroller-build/robotcontroller-output/RobotController` へ移動します。JVMは作業ディレクトリの `System.properties` を読みます。Sotaの設定例は以下です。

```properties
ROBOT_TYPE=Sota
PORT=22222
```

接続成功はロボット初期化完了の保証ではありません。実機動作確認は操作者が手動で行い、自動エージェントから接続・配置・起動・音声・サーボ・LED操作は行いません。

## 通信プロトコル

### 通信プロトコルの概要

TCPポートの初期値は`22222`です。TCPの1回の送受信とフレーム境界は一致しないため、受信側は指定バイト数がそろうまで繰り返し読み取る必要があります。

すべてのメッセージを次の形式で送ります。長さは本文のバイト数で、4バイトのヘッダ自身を含みません。

```text
[本文長: 4バイト、big-endian整数][本文: 指定バイト数]
```

長さはJavaのsigned intで解釈されます。負数となる`0x80000000`以上を送らないでください。最初の本文はコマンド名そのものです。改行・NUL終端・引用符は付けません。コマンド名はASCII、JSONもASCIIで表現すれば既存実装のデフォルトcharsetへの依存を避けられます。現行の従来経路はcharsetを明示しておらず、厳密なUTF-8検証を提供しません。

従来型は原則1接続1コマンドです。`audio_stream_v1`だけは最初のコマンド後も接続を保持し、複数の音声を順に処理できます。どちらも同じTCPポートを使用します。

### 従来型通信プロトコル

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

#### 姿勢・モーション・アイドル動作

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

#### 軸の読み取り

`read_axes`を送ると、次のようなJSON本文を4バイト長ヘッダ付きで受信します。キー順・空白は固定ではなく、機種と取得された軸によってキーが変わります。

```json
{"HEAD_Y":0,"HEAD_P":0,"HEAD_R":0,"BODY_Y":0,"L_SHOU":0,"L_ELBO":0,"R_SHOU":0,"R_ELBO":0}
```

値は機種別Converterで変換された整数の角度です。上記は応答書式の例で、実機観測値ではありません。

#### 従来型WAV再生

`play_wav`はWAV全体を受信して作業ディレクトリの固定名`__temp_wav`へ保存し、外部プロセス`aplay`を起動します。再生終了を待つ応答はありません。WAVの対応形式は利用先の`aplay`と音声環境に依存します。

`stop_wav`には`killall aplay`を起動する旧処理があり、他の`aplay`にも影響し得ます。新型の`CANCEL`とは別機能であり、新型ストリームの停止には使用しません。

### 新型音声ストリーミング（audio_stream_v1）

#### 接続とフレーミング

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

#### 音声フォーマットと送信速度

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

#### 送信レコードと状態遷移

ここでの「待機」は接続獲得後または正常な終端後、「再生中」はSTARTが成功したストリームを表します。

| レコード | 本文の先頭 | 本文長 | 許される状態 | 成功時 |
|---|---|---:|---|---|
| START | `0x01` | 1 | 待機 | 新しいwriter・キュー・ALSAデバイスを用意し、STARTED → 再生中 |
| DATA | `0x02` | 3〜961、PCM部分は偶数長 | 再生中 | PCMを投入。成功応答なし |
| END | `0x03` | 1 | 再生中 | 残りのPCMを処理し、drain・close後にENDED → 待機 |
| CANCEL | `0x04` | 1 | 再生中 | 未処理PCMを破棄し、drop・close後にCANCELLED → 待機 |

STARTEDを待ってからDATAを送ります。ENDまたはCANCELを送ったら、対応する応答を待ってから次のSTARTを送ります。サーバーもこれらの終端処理中は次のレコードを読み進めません。STARTの重複、待機中のDATA・END・CANCELはPROTOCOL_ERRORです。CANCELは待機中に繰り返せる操作ではありません。

内部では開始中・終了処理中・失敗・クローズなどの状態も管理します。音声ごとのgenerationと新しいwriter・キュー・デバイスによって古い音声を分離します。切断時は活動中ストリームの中止・リソース解放を試み、正常に解放できた場合に接続枠を返します。切断は正常な再生完了通知の代替にはなりません。

#### サーバー応答と再生完了の意味

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

#### エラーとタイムアウト

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

### 通信シーケンス例

以下の矢印はすべて長さヘッダ付きフレームです。DATAには成功応答がありません。

#### 通常の音声再生

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

#### 再生途中のキャンセルと再開

```text
接続 → audio_stream_v1 → CONNECTION_READY
START → STARTED → DATA → DATA → CANCEL → CANCELLED
START → STARTED → 別の音声のDATA → END → ENDED
```

CANCELLEDを受信するまで新しいSTARTを送りません。CANCELは再生中ストリームを中止し、その続きから再開するpause/resumeではありません。

#### 2文以上の連続再生

```text
接続 → audio_stream_v1 → CONNECTION_READY
START → STARTED → 1文目のDATAを順次送信 → END → ENDEDを確認
START → STARTED → 2文目のDATAを順次送信 → END → ENDEDを確認
START → STARTED → 3文目のDATAを順次送信 → END → ENDEDを確認
接続を閉じる
```

同じTCP接続を維持し、文ごとに新しいSTARTを使います。先のENDEDが確認できなければ次の文に進みません。

#### Pythonでのフレーム処理

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

## 関連ドキュメント

- [ビルドの詳細技術資料・トラブル対処](docs/build-details.md)
- [EdisonのGitHub証明書エラー対処](docs/git-certificate-setup.md)
- [ビルド環境の検証記録（履歴資料）](docs/build-environment-validation-2026-11-02.md)
- [Phase Gの手動受入手順](docs/phase-g-acceptance.md)
- [2026年9月16日の実機受入結果](docs/phase-g-result-2026-09-16.md)
- [Phase G受入結果テンプレート](docs/phase-g-result-template.md)
- [Windows開発用ビルド](tools/build_java_dev.ps1)・[回帰試験](tools/test_build_java_dev.ps1)
- [従来型クライアントの例](https://github.com/social-robotics-lab/robotcontroller_client)
