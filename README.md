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

## 必要なライブラリ

次の6つのJARを用意します。受入時のSHA-256は[受入結果](docs/phase-g-result-2026-09-16.md)および[ビルドスクリプト](tools/build_phase_g.ps1)に記載されています。

| ファイル | 用途・入手上の注意 |
|---|---|
| `core-2.2.jar` | 既存Java実装の依存ライブラリ |
| `gson-2.8.5.jar` | 既存Java実装の依存ライブラリ |
| `javase-2.2.jar` | 既存Java実装の依存ライブラリ |
| `jna-4.1.0.jar` | 既存Java実装の依存ライブラリ |
| `json-20180813.jar` | JSON処理 |
| `sotalib.jar` | VSTONE公式Java API。[公式サンプル](https://github.com/vstoneofficial/SotaSample)を参照 |

未確認の別バージョンや既存実機のJARを自動的に置き換えないでください。[RobotController_bin](https://github.com/social-robotics-lab/RobotController_bin)の配布JARが新型ストリーミング対応版かは確認できていません。

## ビルド方法

Windows上のクリーンなチェックアウトとJava 8 JDKを使用します。リポジトリ直下で次を実行します。パスは利用環境に合わせて指定し、出力先にはリポジトリ外の新しい未作成フォルダを選びます。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\build_phase_g.ps1 `
  -DependencyDirectory C:\Users\tiio\Workspace\lib `
  -OutputDirectory C:\Users\tiio\Workspace\RobotController-docs-build-01
```

スクリプトはJava・javacがJava 8であること、6依存JARのハッシュ、production baseline `bd299ae1bbc0d0514d5b60a0ca2d45125a01f1d6`との入力同一性、作業ツリー、コンパイルとmanifestを検査します。READMEを編集中の未コミット状態は許可されません。成功時はビルド報告・コンパイラログと次の構成を生成します。再ビルドしたJARのハッシュはビルドごとに記録します。

```text
RobotController/
  RobotController.jar
  System.properties
  lib/
    core-2.2.jar
    gson-2.8.5.jar
    javase-2.2.jar
    jna-4.1.0.jar
    json-20180813.jar
    sotalib.jar
  native/                       （PCビルド直後は空）
```

JNIライブラリはこのスクリプトではビルド・コピーしません。[native/Makefile](native/Makefile)はJava 8 JDKの`javac`・`javah`、ALSAヘッダ、Cコンパイラ、`libasound.so.2`を必要とし、`native/build/librobotcontroller_alsa.so`を生成する別のビルド手順です。Phase Gの再現では新たに実機でビルドせず、出所とハッシュを確認した既存のPhase F.2ライブラリを人間が配置します。

## Sotaへの配置と起動（人間による手動操作のみ）

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
