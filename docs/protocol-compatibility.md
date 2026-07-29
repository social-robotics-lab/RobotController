# docs/protocol-compatibility.md

## 1. 文書の目的

本書は、既存Java版RobotControllerおよび既存クライアントとPython版RobotControllerとの通信互換性を定義する。

本書の「必須」「禁止」「推奨」は規範的な意味を持つ。

## 2. 互換性の基本方針

Python版は、正常に構成された既存クライアントの正常系動作を維持する。

本書で互換性があるとは、正常な既存クライアントが送るバイト列を受理し、同じコマンド効果を発生させ、v1では`read_axes`だけが応答を返すことをいう。

以下は互換性の対象とする。

* コマンド名
* コマンドごとのフレーム数
* 4バイトbig-endian長さヘッダ
* JSONペイロードの意味
* WAVバイナリ送信
* `read_axes`の応答形式
* 原則1接続1コマンドという利用方法
* 既存クライアントがACKを期待しないこと

以下は互換性の対象としない。

* 処理タイミングの完全一致
* JSONキーの出力順序
* JSON文字列の空白
* 不正入力時のJava固有挙動
* Java版のクラッシュ
* Java版のハングと競合
* Java版のnull参照
* Javaの暗黙的な数値変換
* EOF時の不定動作
* 無制限スレッド生成
* 固定一時ファイルの競合
* `killall aplay`
* キュー競合
* 例外メッセージの一致

## 3. 用語

### フレーム

4バイトの長さヘッダと、その長さのデータ本体で構成される単位。

### コマンドフレーム

コマンド名を格納した第1フレーム。

### ペイロードフレーム

JSONまたはWAVバイナリを格納した第2フレーム。

### v1

既存Java版および既存クライアントと互換性を持つレガシープロトコル。

### v2

将来追加する、構造化応答、エラーコード、要求ID等を持つ拡張プロトコル。

## 4. フレーム形式

フレームは次の形式とする。

```text
+----------------------+------------------------+
| Length: 4 bytes      | Payload: Length bytes  |
+----------------------+------------------------+
```

### 4.1 Length

* 4バイト
* big-endian
* ペイロードのバイト数
* 文字数ではなくバイト数
* 正常系v1で有効な範囲は `0 <= length <= min(command-specific configured limit, 2147483647)`
* `0x80000000`以上の値は既存Java版では負数になるため拒否する

Pythonでは概念的に次と等価である。

```python
length = int.from_bytes(header, byteorder="big", signed=False)
```

送信時は次と等価である。

```python
header = len(payload).to_bytes(4, byteorder="big", signed=False)
```

### 4.2 Payload

ペイロードはコマンドに応じて次のいずれかとする。

* ASCII互換のUTF-8コマンド名
* UTF-8 JSON
* WAVバイナリ
* UTF-8 JSON応答

### 4.3 最大長

Frame Codecは固定最大値を内部に持たず、各フレームを読む呼び出し側から`max_length`を受け取る。

最大長を超えるフレームは本文を確保する前に拒否する。

初期既定値は次のとおりとし、設定で変更可能とする。

| フレーム種別 | 初期既定値 |
| --- | ---: |
| command frame maximum | 64 bytes |
| JSON frame maximum | 1 MiB（1,048,576 bytes） |
| WAV frame maximum | 20 MiB（20,971,520 bytes） |

Frame Codecは長さ0を`b""`として正常に返す。空のコマンド、空JSON、空WAV等を拒否するかはコマンド層で判断する。

## 5. 接続モデル

v1では、原則として1つのTCP接続につき1つのコマンドを処理する。

基本手順は次のとおり。

```text
Client                         Server
  |                               |
  | TCP connect                   |
  |------------------------------>|
  | command frame                 |
  |------------------------------>|
  | optional payload frame        |
  |------------------------------>|
  | optional response frame       |
  |<------------------------------|
  | close                         |
  |------------------------------>|
```

Python版は、v1の1接続1コマンドを正式な利用方法としてサポートする。

1接続で複数コマンドを扱う機能は、v1互換性の必須要件とはしない。

初期版は同期ソケットと上限付き`ThreadPoolExecutor`を使用し、同時接続ハンドラー数の初期既定値を16とする。初期版では`asyncio`を使用しない。

## 6. コマンド一覧

| コマンド               | 第2フレーム           | v1応答      |
| ------------------ | ---------------- | --------- |
| `play_wav`         | WAVバイナリ          | なし        |
| `stop_wav`         | なし               | なし        |
| `play_pose`        | Pose JSON        | なし        |
| `stop_pose`        | なし               | なし        |
| `play_motion`      | Motion JSON      | なし        |
| `stop_motion`      | なし               | なし        |
| `play_idle_motion` | Idle Motion JSON | なし        |
| `stop_idle_motion` | なし               | なし        |
| `read_axes`        | なし               | Axes JSON |

## 7. コマンド名

* UTF-8でデコードする。
* 現行コマンドはASCII文字だけで構成される。
* 前後の空白を自動的に除去しない。
* 大文字と小文字を区別する。
* NUL終端を必要としない。
* 未知のコマンドは実行しない。

v1では未知のコマンドに構造化応答を返すことを必須としない。サーバーはログへ記録し、安全に接続を閉じる。

## 8. Pose JSON

### 8.1 形式

```json
{
  "Msec": 700,
  "ServoMap": {
    "HEAD_Y": 20,
    "HEAD_P": -5
  },
  "LedMap": {
    "PWR_BTN_R": 255,
    "PWR_BTN_G": 0,
    "PWR_BTN_B": 0
  }
}
```

### 8.2 必須条件

* トップレベルはJSONオブジェクト
* `Msec`は必須
* `ServoMap`または`LedMap`の少なくとも一方が必要
* `ServoMap`はオブジェクト
* `LedMap`はオブジェクト

### 8.3 `Msec`

* 単位はミリ秒
* `bool`ではない整数
* 設定された最小値以上、最大値以下
* 小数を暗黙的に整数化しない
* 負数を拒否する

### 8.4 `ServoMap`

* キーはロボット種別で定義された軸名
* 値は`bool`ではない整数
* 未知キーを拒否する
* 範囲外値の扱いはロボットプロファイルに従う
* Python版ではJavaの暗黙キャストを再現しない

### 8.5 `LedMap`

* キーはロボット種別で定義されたLED名
* 値は`bool`ではない0～255の整数
* 未知キーを拒否する

## 9. Motion JSON

MotionはPose JSONの配列である。

```json
[
  {
    "Msec": 500,
    "ServoMap": {
      "HEAD_Y": 20
    }
  },
  {
    "Msec": 500,
    "ServoMap": {
      "HEAD_Y": -20
    }
  },
  {
    "Msec": 500,
    "ServoMap": {
      "HEAD_Y": 0
    }
  }
]
```

要件は次のとおり。

* トップレベルは配列
* 空配列を拒否する
* 各要素は有効なPose
* 要素数に上限を設ける
* 合計実行時間に上限を設けてもよい
* 1要素でも不正なら、原則としてモーション全体を実行しない

## 10. Idle Motion JSON

```json
{
  "Speed": 1.0,
  "Pause": 1000
}
```

### `Speed`

* 整数または浮動小数点数
* `bool`ではない
* 有限値
* 0より大きい
* 設定された最大値以下

### `Pause`

* `bool`ではない整数
* 単位はミリ秒
* 0以上
* 設定された最大値以下

フィールド省略時の既定値は、既存仕様との互換性を考慮し次とする。

```json
{
  "Speed": 1.0,
  "Pause": 1000
}
```

## 11. WAVペイロード

`play_wav`の第2フレームはWAVファイル全体のバイナリである。

サーバーは少なくとも次を確認する。

* 長さが0ではない
* 最大WAVサイズ以下
* RIFF/WAVEとして最低限妥当
* 一時ファイルへ安全に保存可能
* ディスク空き容量または保存失敗を処理可能

v1では再生成功を示すACKは返さない。

## 12. `read_axes`応答

`read_axes`の正常応答は、1つのフレームで返すUTF-8 JSONオブジェクトである。

例:

```json
{
  "BODY_Y": 0,
  "L_SHOU": 30,
  "L_ELBO": 10,
  "R_SHOU": -30,
  "R_ELBO": -10,
  "HEAD_Y": 0,
  "HEAD_P": 0,
  "HEAD_R": 0
}
```

要件は次のとおり。

* キーはロボット種別の軸名
* 値はJSON数値
* JSONキー順序は規定しない
* 空白や改行は規定しない
* クライアントはJSONとして解析する
* Python版はUTF-8で送信する

バックエンドが角度を取得できない場合のv1動作は、実装前に確定する。候補は以下である。

* 接続を安全に閉じる
* 最後に確認された値を返す
* 特定のエラー表現を返す

既存クライアント互換性を優先し、v1で通常のAxes JSON以外の構造を返す変更は慎重に扱う。

## 13. v1のエラー処理

v1では、多くのコマンドでクライアントが応答を読み取らない。

そのため、Python版は、以下のコマンドに無条件でエラー応答を送信しない。

* play_wav
* stop_wav
* play_pose
* stop_pose
* play_motion
* stop_motion
* play_idle_motion
* stop_idle_motion

エラー時は次を行う。

1. ハードウェア操作を実行しない、または安全に中断する
2. サーバーログへ記録する
3. 当該接続を閉じる
4. 他の接続やサーバープロセスを継続する

## 14. EOFと部分受信

TCPの1回の `recv()` が、要求した全バイトを返すと仮定してはならない。

実装は次を区別する。

* ヘッダ受信前の正常な接続終了
* ヘッダ途中のEOF
* 本文途中のEOF
* 読み取りタイムアウト
* 長さ超過
* ソケットエラー

本文途中のEOFを無限ループまたは空データとして扱わない。

読み取りタイムアウトの初期既定値は次のとおりとし、設定で変更可能とする。

| 対象 | 初期既定値 |
| --- | ---: |
| command frame header/body | 5 seconds |
| JSON frame header/body | 5 seconds |
| WAV payload frame header/body | 30 seconds |
| `read_axes` response frame header/body | 5 seconds |

Session層はコマンド種別に応じてペイロードのタイムアウトを選択し、応答送信時も対応するタイムアウトを適用する。Frame Codecはコマンド種別を認識しない。各値は絶対期限ではなく、各ブロッキングsocket操作の無通信タイムアウトであり、処理後は呼び出し前のsocket timeoutへ復元する。

## 15. 互換性テスト

### 15.1 バイト列互換

既存クライアントと同じ処理で生成した次のバイト列を受理する。

* コマンド長
* コマンド本文
* JSON長
* JSON本文
* WAV長
* WAV本文

### 15.2 JSON互換

次を同値として扱う。

```json
{"Msec":500,"ServoMap":{"HEAD_Y":20}}
```

```json
{
  "ServoMap": {
    "HEAD_Y": 20
  },
  "Msec": 500
}
```

### 15.3 クライアント互換

少なくとも `robo-tutorial/tutorial_01/robottools.py` 相当のクライアントから全コマンドを試験する。

### 15.4 Java版比較

同じ正常入力をJava版とPython版へ送り、次を比較する。

* 受理または拒否
* バックエンドへ渡される正規化済み値
* `read_axes`の意味
* コマンド完了後の状態

バグ、不定動作、JSON文字列の完全一致は比較対象にしない。

## 16. プロトコルv2の方針

v2では、少なくとも以下を検討する。

* 明示的なバージョンネゴシエーション
* request ID
* 全コマンドへの応答
* 構造化エラーコード
* サーバー状態取得
* ロボット能力取得
* 長時間処理の受理と完了の区別
* 認証
* 1接続複数コマンド
* イベント通知

v2は、既存v1クライアントが誤ってv2応答を受け取らない方式で導入する。

候補は以下である。

* 別ポート
* 最初のフレームによる明示的なネゴシエーション
* 別サービス
* v2専用コマンドプレフィックス

## 17. 変更管理

プロトコルに影響する変更では、必ず以下を更新する。

* 本書
* サーバー実装
* クライアント実装
* 互換性テスト
* リリースノート
* 必要に応じて `robo-tutorial`

## 18. Reference baselines

### 18.0 確認済み`vsmd_edison` protocol

この節はRobotControllerの外部legacy v1ではなく、Sota Backend内部で利用する
localhost protocolを記録する。実機probe、Java bytecode/PCAP解析、未確認事項を
小節内で区別する。

#### 18.0.1 read-only probeによる実機確認

Windows 11 / Python 3.14.3からSSH local port forwardingを経由し、Intel Edison上の
`127.0.0.1:6498`で待ち受ける`vsmd_edison`へ接続した。接続直後の改行終端bannerは
次のとおりで、Python実装はSSH tunnel越しにも正常に読み取った。

```text
#vs-rc020 (Oct 31 2018 14:44:11)
```

read requestのsizeはPython API上ではbyte数を表す整数だが、wire上ではlower-case
hexadecimalである。実機で次を確認した。

```text
R 0124 2   → 2 bytes
R 0e80 40  → 64 bytes
R 0e80 64  → 100 bytes
```

したがって64 bytesの要求は`R 0e80 40\r\n`であり、`R 0e80 64\r\n`ではない。
実機responseでは`#0124 8a 00 \r\n`のように最後のbyteとCRLFの間へASCII spaceが
入った。確認済みの互換範囲としてCodecは末尾space 0個または1個を許容するが、
行頭space、byte間の連続space、tab、末尾space 2個以上、byte不足・過剰、
address不一致、2桁でないhex tokenは拒否する。全responseに末尾spaceが必ず付くかは
未確認である。

同じread-only probeで確認したaddressとその時点の値は次のとおりである。

| 項目 | address | 実測値 |
| --- | ---: | ---: |
| `MOUTH_LED_SELECTOR_ADDRESS` | 292 | 138 |
| `AUDIO_DIFF_VALUE_ADDRESS` | 138 | 0 |
| `InterpLEDTarget[14]` | 2716 | 0 |
| `InterpLEDOutput[14]` | 3228 | 0 |

address計算`2688 + 14 * 2 = 2716`および`3200 + 14 * 2 = 3228`も、probeが
読み取ったTarget/Output addressと一致した。`ServoReadPos`はbase address 3712から
32個のsigned little-endian S16として正常に取得・復号した。wire上のread sizeは
64 bytes、つまり`40`である。個々の値は姿勢や時刻で変わるため、固定仕様や
golden vectorにはしない。

この項の接続、banner、read wire、addressおよびread値は「実機で確認済み」である。
後述のwrite列はJava版`sotalib.jar`のPCAP解析で確認済みであり、根拠を区別する。

#### 18.0.2 Java版`sotalib.jar`のPCAP解析で確認済み

```text
write:    w {address:04x} {byte0:02x} {byte1:02x} ...\r\n
```

write形式は実機上の`sotalib.jar`通信をPCAPで確認した。先頭はlower-case `w`、
command、4桁lower-case hexadecimal address、各2桁lower-case hexadecimal
payload byteの間はASCII spaceちょうど1個、終端はCRLFである。write responseは
待たない。typed値はlittle-endianである。

PCAPで確認したwriteとmemory操作は次のとおり。

| 確認済みwire line | 確認された操作 |
| --- | --- |
| `w 0124 9c 0c` | `MOUTH_LED_SELECTOR_ADDRESS` (`0x0124`)へlittle-endian 3228を書込む |
| `w 0124 8a 00` | selectorをAudioDiff address 138へ復元する |
| `w 0a9c 10 00` | `InterpLEDTarget[14]`へ16を書込む |
| `w 0a9c 00 00` | `InterpLEDTarget[14]`へ0を書込む |
| `w 0b9c f6 01` | `InterpLEDTriggerPointer[14]`へ`0x01f6`を書込む |
| `w 01f6 0b 00` | 補間timer address `0x01f6`へ11を書込む |
| `w 0b9c f4 01` | `InterpLEDTriggerPointer[14]`を`0x01f4`へ復元する |

上表は観測byte列とその対応についての実測済み仕様である。一方、
TriggerPointerの割当規則、timer addressの所有権、lock wire protocol、
競合・切断時の挙動はこのcaptureだけでは未確認である。これらを静的解析だけで
推定してproduction lockを実装しない。

静的解析で、このリポジトリのJava版が`CRobotMem`/`CSotaMotion`を使用すること、
公開口LED IDが14であることを確認した。`CRobotSock`本体と
`InterpLockerClient` sourceはリポジトリに含まれない。

#### 18.0.3 SotaAppManager補間lock protocol

Java bytecodeおよび通信解析で、補間lockは`vsmd_edison`の6498番とは別に、
`SotaAppManager.jar`がlistenするTCP `127.0.0.1:6495`を使用すると確認した。
1 requestごとに新しいconnectionを使用し、順序は次のとおりである。

```text
connect
server → client: ac ed 00 05
client → server: compact ASCII JSON + LF
server → client: Java serialized object
server closes connection
```

server-first headerを4 bytes exact readして検証する前にrequestを送ってはならない。
request送信後のtimeoutまたは切断は処理結果が不明なため自動retryしない。responseは
headerを含め4096 bytes以下に制限する。

requestは`cmd`、続いて`subjson`の順のcompact JSONである。`subjson`の値はobject
ではなく、inner JSONを格納したStringである。確認済みgolden vectorsは次のとおり。
各行のwire末尾にはLF `0a`を1個だけ付け、CRLFは使用しない。

```text
{"cmd":"INTERP_LOCK","subjson":"{\"key\":\"fixture-key\",\"ids\":[14],\"isServo\":false}"}
{"cmd":"INTERP_CNV_KEY_2_ADDR","subjson":"{\"key\":\"fixture-key\"}"}
{"cmd":"INTERP_UNLOCK","subjson":"{\"key\":\"fixture-key\",\"ids\":[14],\"isServo\":false}"}
```

response decoderは汎用Java deserializerではなく、次の確認済みsubsetだけを受理する。

```text
OK:   ac ed 00 05 74 00 02 4f 4b
NG:   ac ed 00 05 74 00 02 4e 47
null: ac ed 00 05 70
```

`java.lang.Short`は77 bytesであり、先頭75 bytesが次のprefixと完全一致する場合だけ、
最後の2 bytesをsigned big-endian S16としてdecodeする。

```text
ac ed 00 05 73 72 00 0f 6a 61 76 61 2e 6c 61 6e 67 2e 53 68 6f 72 74 68 4d 37 13 34 60 da 52 02 00 01 53 00 05 76 61 6c 75 65 78 72 00 10 6a 61 76 61 2e 6c 61 6e 67 2e 4e 75 6d 62 65 72 86 ac 95 1d 0b 94 e0 8b 02 00 00 78 70
```

| Short値 | 最後の2 bytes | full length |
| ---: | --- | ---: |
| 0 | `00 00` | 77 |
| 496 | `01 f0` | 77 |
| 502 | `01 f6` | 77 |
| 558 | `02 2e` | 77 |

未知token、未知class descriptor、切れたobject、余分なbyte、`OK`/`NG`以外のStringは
拒否する。convertの`null`はkey未登録であり、496へのfallbackを行わない。

timer addressは`496..558`、step 2の32 slotsである。lock成功後は必ず同じkeyで
convertし、範囲とalignmentを検証する。convert失敗後は同じkey/IDsでUNLOCKを
best-effortに1回だけ試みる。cleanup結果も不明ならoutcome unknownとし、retryしない。

SotaAppManagerのlockは排他的mutexではなく、対象LEDのTriggerPointer stack操作で
ある。unlockはrequest内のIDsをそのまま使うため、leaseは取得時のkeyとIDsを不変に
保持する。同じLEDを複数keyで重ねてlockせず、同じLEDへ重複leaseを作らない。
他processとの重複lockを安全に検出できず、non-LIFO unlockにはJava側stack破損の
可能性があり、process異常終了時の自動解放もない。生成keyは識別子であり、機密情報を
含めない。

明示的な診断用`app_manager_probe`はPython自身から設定されたTCP 6495 endpoint
だけへ接続し、1回のLOCK、最大1秒の保持、1回のUNLOCKだけを実行する。
VSMD TransportやMemory Clientを生成せず、Pythonから6498番へ接続またはwrite
しない。ただし、SotaAppManager自身のLOCK/UNLOCK処理は内部で6498番へtimer初期化と
TriggerPointer変更を書き込む。これはLED Target/Output値の変更ではないが、補間経路の
一時変更であるため、実行時は6495番と6498番の両方をcaptureして照合する。
このprobeは明示的に起動する診断機能であり、Composition Root、既定Backend、
production起動経路には含めない。

WindowsからSSH local port `16495`をEdisonの6495番へ転送した場合の実行例は
次のとおり。

```powershell
python -m robot_controller.hardware.vsmd.app_manager_probe `
  --host 127.0.0.1 `
  --port 16495 `
  --led-id 14 `
  --hold-seconds 0.2
```

既存`AppManagerTcpTransport`は1つのtimeoutを全段階へ使用するため、probeの
`--connect-timeout`、`--read-timeout`、`--write-timeout`は異なる値を指定すると
fail-closedで拒否する。値を黙って丸めたり自動retryしたりしない。

#### 18.0.4 2026-07-29 AppManager LED lock-only probe

Windows上のPythonからSSH local forwardingを経由してSotaAppManager TCP 6495へ
接続し、LED ID 14を0.2秒保持するlock-only probeを1回実行した。Python自身が送った
requestは同一keyによる`INTERP_LOCK`、`INTERP_CNV_KEY_2_ADDR`、
`INTERP_UNLOCK`の3件である。取得したtimer addressは502 (`0x01f6`)で、
probeは`lock_acquired=true`、`lock_released=true`、`result=success`を返した。

同時captureで、SotaAppManagerが6498番を通じて送ったwriteは次の3件だけだった。

```text
w 01f6 00 00
w 0b9c f6 01
w 0b9c f4 01
```

順に、timer `0x01f6`への0、LED 14 TriggerPointerへの`0x01f6`、以前の
`0x01f4`が書き込まれた。TriggerPointerは
`0x01f4 → 0x01f6 → 0x01f4`と遷移した。mouth LED selector
`0x0124`、`InterpLEDTarget[14]` `0x0a9c`、`InterpLEDOutput[14]` `0x0c9c`
へのwriteはcapture内になかった。Python probe自身は6498番へ接続しておらず、
上記writeはlock requestを処理したSotaAppManagerの内部処理である。

この結果はlock-only経路の確認であり、actual mouth LED output testは実施して
いない。probeはproduction Composition Rootへ未接続である。PCAPおよびcaptureから
生成したtextはローカル検証証拠としてリポジトリへ収録していない。

#### 18.0.5 未確認または今後の課題

lock競合時の全応答、他processとの重複を安全に検出する方法、異常終了後の運用上の
回復手順、Pythonからの安全なproduction LED write、`VsmdSotaCommandTarget`の
完全統合、VSMDが許容する最大read size、および全responseで末尾spaceが必ず付くか
どうかは未確認である。

外部実装を互換性または低レベル仕様の根拠として参照するときは、リポジトリURL、検証済みの完全なcommit SHA、確認日、ライセンス、コピーしたコードか仕様だけを参考にした再実装か、およびレジスタ・ID・パケット・可動範囲ごとの検証状態を記録する。完全なcommit SHAを確認できない場合は推測せずTODOとする。

### 18.1 通信互換性の基準

| 対象 | リポジトリURL | 完全なcommit SHA | 確認日 | ライセンス | 利用方法 |
| --- | --- | --- | --- | --- | --- |
| Java版RobotController | https://github.com/social-robotics-lab/RobotController | `31ce13ada9792a30691304663d3e36719a845d4f` | 2026-07-17 | MIT | 通信仕様と正常系動作の参照。コードコピーではない |
| robo-tutorial | https://github.com/social-robotics-lab/robo-tutorial | `196a2cdd9fe926ee3647fbbc1b83fc510fafc0d2` | 2026-07-17 | MIT | 既存クライアントが生成するバイト列と利用方法の参照。コードコピーではない |
| robot-controller-client | https://github.com/social-robotics-lab/robot-controller-client | `d74f357c32e35e88fa278f0e3c5c6f040d241b91` | 2026-07-17 | MIT | クライアント実装の比較。コードコピーではない |
| 旧robotcontroller_client | https://github.com/social-robotics-lab/robotcontroller_client | TODO: 完全なcommit SHAを確認 | 2026-07-17 | MIT | 旧クライアントの送受信挙動の比較。コードコピーではない |

### 18.2 非公式低レベル実装

現時点では具体的な基準実装を確定していない。採用候補ごとに、以下を埋めるまでレジスタ、ID、パケット、可動範囲を実装根拠として使用しない。

| 項目 | 状態 |
| --- | --- |
| リポジトリURL | TODO |
| 完全なcommit SHA | TODO |
| 確認日 | TODO |
| ライセンス | TODO |
| コピーまたは仕様参考による再実装 | TODO |
| レジスタの検証状態 | TODO |
| IDの検証状態 | TODO |
| パケットの検証状態 | TODO |
| 可動範囲の検証状態 | TODO |
