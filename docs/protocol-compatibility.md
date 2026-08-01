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

#### 18.0.5 LED補間timer単位の静的解析と未成功のlive試験

Vstone `CRobotMotion.play(CRobotPose, int msec, ...)`の静的解析で、公開APIの
ミリ秒は実行時の`CRobotMem.MasterCtrlPeriod`を使って次のcontrol ticksへ変換
されることを確認した。`MasterCtrlPeriod`はU32、単位µs、address `0x0040`である。

```text
timer_ticks = floor(msec * 1000.0 / masterCtrlPeriod)
timer_ticks = min(timer_ticks, 65535)
```

旧Python実装は`duration_ms`をtimerへ直接書いていた。2026-07-29にlevel 16、
duration 200 msで実行したlive probeでは200 ticksを書き、`InterpLEDOutput[14]`
は1までしか進まず、物理mouth LEDは目視で点灯しなかった。一方、AppManager lock、
VSMD write、cleanup、release、selector・Target・TriggerPointerの復元は成功した。
selector `0x0c9c`と音声同期source `0x008a`はJava実装と一致していた。

修正版は実機の`MasterCtrlPeriod`をpreflightで1回readし、同じprobe中の変換に
再利用する。整数除算によるfloor、65535 clamp、正durationから0 ticksになる場合の
fail-closedをFakeで検証した。このtimer換算修正直後の時点では、修正版による
実機writeとphysical illuminationは未確認であり、actual LED pulse試験を
完了扱いにしなかった。後述の同日試験で段階的に確認した。

通常の`aplay`中のAudioDiff、selector、Target、Output、TriggerPointer、そのpointer
先timer、RemainingTimeを観測する`mouth_led_observer`はTCP 6498のreadだけを使用する。
TCP 6495、LOCK、write、selector変更は行わず、CSVをstdoutへ出力する。

2026-07-29の実機observerでは`MasterCtrlPeriod=16667 µs`、selector `0x008a`、
Target 0、Output 1、TriggerPointer `0x01f4`、pointer先`0xffff`、RemainingTime 0を
確認した。通常の`aplay`中にはAudioDiffが3816、935、11146、166などへ変化した。
capture上、observer自身はTCP 6498のreadだけを送り、VSMD writeとTCP 6495接続は
なかった。実機periodでは200 msは11 ticks (`0b00`)となる。Fake dry-runの
16666 µsでは12 ticks (`0c00`)であり、period差による正常な相違である。

full observerは8 addressを逐次readするため、指定intervalはbest-effortである。
SSH tunnel経由では20 ms指定に対して実測約350 msであり、CSV 1行は原子的snapshot
ではない。将来、AudioDiffだけを高頻度readするfocused modeを別途検討する。

上記observerで、timer値0は`InterpLEDOutput[14]`を0へ戻す操作ではないことも
実機確認した。このためlive probe候補は、上昇補間の完了後に100～1000 ms
（既定500 ms）保持し、selectorをAudioDiffへ復元する前に既存controllerの
`turn_off()`を使ってTarget 0と正のcontrol ticksを書き、下降補間の完了を確認する。
transition duration（50～200 ms）とhold durationは別のCLI値として扱う。

上昇・下降とも、指定transition durationを待ってからOutput、RemainingTime、
TriggerPointer、lease timerの4 readを1つの完結snapshotとして取得する。成功条件は
Outputが各phaseのTarget、RemainingTimeが0、TriggerPointerがlease timer addressに
一致することであり、timer slot値は記録だけを行う。次の再確認を開始できるのは
deadline内かつ最大3回までである。各snapshotには取得時間とpoll attemptを記録する。
下降失敗時も既存cleanupでselector復元を優先し、UNLOCKは1回だけ試みる。

2026-07-29のrise/hold/fall修正版live試験では、operatorが物理的なmouth LED点灯を
確認し、PythonからのLOCK、selector、Target、control-tick timer write経路が物理LEDへ
到達することを実証した。ただし最初の逐次readはOutput 13を取得した後に
RemainingTime 0を取得し、旧判定がrise失敗と誤認した。試験後のread-only observer
ではOutput 16への到達、selector `0x008a`、Target 0、TriggerPointer `0x01f4`を
確認した。逐次readの値は原子的snapshotではない。

誤判定により正のtimerを使うfade-downへ進まず、cleanupのtimer 0だけが書かれたため
Output 16が残った。selectorはAudioDiffへ正常に復元された。次回実行候補では
`pointer → remaining_before → output → remaining_after → timer`を1 observationとして
記録し、両RemainingTimeが0、OutputがTarget、pointerがlease timerに一致する場合だけ
成功とする。不一致は即時確定失敗にせず、有限deadline内で最大3回再確認する。

また、次回開始時にpreflight Outputが非0なら、selectorを`0x008a`に保ったまま
Target 0と正のtimer ticksでOutput 0へ正規化し、その完了後だけselectorを
`0x0c9c`へ切り替える。selector切替後の失敗では、可能なら正のtimerによる
emergency fade-downを試み、その成否にかかわらずselector復元と単一UNLOCKを優先する。

同じ実機では補間完了後のlease timer slotが`0xffff`へ変化した。timer slot値は
診断用に記録するが補間完了条件には含めない。観測firmwareにおける`0xffff`の
正確な意味論は未確認である。CLI自身は物理点灯を検出できないため
`physical_illumination=not_verified`を維持する。

> On the observed firmware, the interpolation timer slot changed to
> `0xffff` after completion. Its exact firmware semantics remain unverified.

上記失敗を修正した後の同日再試験では、事前Output 16をselector切替前に正の
11 ticksで0へ正規化し、rise、500 ms hold、正の11 ticksによるfade-down、
cleanup、単一UNLOCK、postflightの全段階が成功した。CLIは終了code 0を返し、
operatorは物理的なmouth LED点灯を確認した。試験後のread-only observer 3 samplesも
selector `0x008a`、Target 0、Output 0、TriggerPointer `0x01f4`、
RemainingTime 0で一致した。

実測値、逐次observation時間および外部証拠ファイル一覧は
[`evidence/mouth-led-live-test-2026-07-29.md`](evidence/mouth-led-live-test-2026-07-29.md)
へ集約する。CLI自身には物理発光を検出できないため、
`physical_illumination=not_verified`は維持し、文書上のoperator確認と区別する。

現在のgateは次のとおりである。

```text
physical_illumination_observed = complete
bounded_rise_hold_fall_sequence = complete
safe_output_zero_after_probe = complete
```

#### 18.0.6 2026-07-29 normalized pulse成功試験

実機条件はMasterCtrlPeriod `16667 us`、LED ID 14、level 16、transition
200 ms、hold 500 ms、timer address `0x01f6`である。
`floor(200000 / 16667) = 11 ticks`により期待どおり動作した。補間完了後の
timer slotはnormalization、rise、fallの各観測で`0xffff`だったが、その正確な
firmware意味論は引き続き未確認である。逐次read時間はnormalization
`286.932 ms`、rise `222.331 ms`、fall `242.134 ms`だった。

`hold_ms=500`はrise確認完了後の最低保持時間であり、物理的な最大輝度維持時間が
厳密に500 msであることを意味しない。試験はWindowsからSSH forwarding経由で行い、
Sota上で直接実行する場合はread latencyが小さくなる可能性がある。

```text
operator_observed_physical_illumination = true
```

#### 18.0.7 未確認または今後の課題

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

## mouth LED pulseの再利用Backend境界

2026-07-29の実機検証済みpulse処理は
`SotaMouthLedPulseOperation`へ抽出し、診断CLIと`SotaVsmdBackend`から同じ実装を
利用する。CLI互換の`--duration-ms`は`rise_ms`と`fall_ms`の両方へ渡すため、
既存のwire動作と安全範囲は変わらない。

Backendの公開引数はlevel、rise_ms、hold_ms、fall_msだけである。確認済みの
LED ID 14、VSMD address、AppManager lock key、変換後timer addressは内部へ
閉じ込める。成功判定は、期待timer pointer、前後のRemainingTime 0、期待Output
の逐次readを最大3回再確認する既存規則を維持し、timer slot値`0xffff`は成功条件に
含めない。結果中のtimer値は診断情報であり、物理発光の証明ではない。

この抽出はRobotController legacy protocol v1のwire形式、応答有無、コマンド効果を
変更しない。Composition Rootは未接続で、既定BackendはUnavailableのままである。

抽出済みmouth LED operationは2026-07-30に物理Sota上で回帰確認され、rise、
hold、fade-down、Output 0、routing復元、UNLOCK、物理発光が成功した。現在のprobe
CLIはoperationを直接生成するため、この結果は`SotaVsmdBackend` wrapper自体の
実機証跡ではない。詳細は
[`evidence/mouth-led-pulse-operation-regression-2026-07-30.md`](evidence/mouth-led-pulse-operation-regression-2026-07-30.md)
を参照する。
## AppManager lease取得後のTriggerPointer可視化遅延

Edison-local Python 3.6からComposition Root smoke CLIを実行した際、
`INTERP_LOCK`と`INTERP_CNV_KEY_2_ADDR`は成功し、lease timer addressとして
`0x01f6`を取得したが、直後のVSMD TriggerPointer readはLOCK前の`0x01f4`を返した。
この時点でpulseは`VsmdMouthLedStateError`により安全に中止され、物理LEDは点灯
しなかった。

この観測から、AppManagerのLOCK／CONVERT成功応答と、`vsmd_edison`側
TriggerPointer更新のread可視化は原子的ではないことが分かった。Edison-local実行は
SSH転送経由よりreadが速いため、この短い反映遅延を観測しやすい。

wire format、command、response、timer address計算に新しい変更はない。LOCK、
CONVERT、UNLOCKを再送せず、取得済みleaseに対するTriggerPointer readだけを
bounded pollingする。

```text
expected pointer: lease timer address
timeout: 1.0 second
poll interval: 0.01 second
```

期待pointerへ収束するまでselector、Target、rise/fade-down timerなどのmouth LED
制御writeは行わない。timeoutまたはread失敗時は既存のtyped errorとcleanup経路を
使用し、UNLOCKは最大1回である。

### Edison-local CPython 3.6.15での収束確認

修正後のComposition Root smoke CLIをEdison上のCPython 3.6.15から直接実行した。
SSH port forwardingは使用していない。最初のTriggerPointer readは旧値`0x01f4`を
返し、約13 ms後のpoll attempt 1でlease pointer `0x01f6`へ収束した。

PCAPでは`INTERP_LOCK`、`INTERP_CNV_KEY_2_ADDR`、`INTERP_UNLOCK`がそれぞれ1回で
あり、LOCKとCONVERTの再試行はなかった。pointer収束後に既存のselector、Target、
timer writeが行われ、物理pulseとcleanupが成功した。

この結果はAppManager成功応答とVSMD pointer可視化が非原子的であるという観測と、
同一leaseに対するbounded read pollingの有効性を確認する。wire format、
AppManager command、VSMD command、timer計算に変更はない。

詳細:
[`evidence/mouth-led-edison-python36-regression-2026-07-30.md`](evidence/mouth-led-edison-python36-regression-2026-07-30.md)

## 2026-07-30 production mouth LED command extension

The repository previously implemented only legacy protocol v1. Because v1
must not gain a command or a response, the production mouth LED command uses
the already documented v2 command-prefix migration option on the same TCP
server. It does not introduce a second server, port, frame codec, connection
lifetime, or worker.

The request uses the existing four-byte big-endian frame format:

1. command frame: `v2/mouth_led_pulse`
2. JSON payload frame:

```json
{
  "request_id": "client-generated-correlation-id",
  "payload": {
    "level": 16,
    "rise_ms": 200,
    "hold_ms": 500,
    "fall_ms": 200
  }
}
```

`request_id` is a non-empty string of at most 128 characters. Unknown fields
are ignored, matching the existing v1 JSON-command policy. All four required
pulse values must
be JSON integers; booleans, null, strings, floats, negative values,
non-standard `NaN`/`Infinity`, missing fields, unknown fields, and values
outside the `MouthLedBackend` contract are rejected before Backend dispatch.

Every recognized v2 command returns one JSON response frame. A success has
this form:

```json
{
  "version": 2,
  "request_id": "client-generated-correlation-id",
  "status": "success",
  "command": "mouth_led_pulse",
  "result": {
    "pulse_completed": true,
    "lock_pointer_converged": true
  }
}
```

`lock_pointer_converged` is present only when supplied by the Backend result.
Responses do not expose memory addresses, lock keys, endpoints, packet data,
or stack traces. Errors use `status=error` and an `error` object with `code`
and a sanitized `message`. Codes used by this path are
`PROTOCOL_DECODE_ERROR`, `VALIDATION_ERROR`, `UNKNOWN_COMMAND`,
`MOUTH_LED_BACKEND_UNAVAILABLE`, `MOUTH_LED_OPERATION_FAILED`, and
`INTERNAL_ERROR`.

Legacy v1 remains byte-for-byte unchanged: its command table, frame limits,
timeouts, response rules, and nine commands are unchanged. In particular,
the unprefixed `mouth_led_pulse` name remains an unknown v1 command. Existing
v1 clients never receive a new response.

The production command code, Fake/localhost regression, and the separately
recorded Edison production-command validation are complete:

```text
production_command_integration_in_code = complete
production_command_fake_regression = complete
production_command_integration = complete
phase7_mouth_led_golden_path = complete
```

#### 18.0.10 Phase 7 fault-recovery compatibility boundary

Fault recovery does not change the AppManager wire format or the production
v1/v2 protocol. Within one `AppManagerVsmdLedLock` instance, overlapping LED
IDs fail before a second LOCK is sent. Independent adapters do not share
local state. Their arbitration was previously delegated to AppManager based on
a shared Fake AppManager that rejected Client B with `NG`. The 2026-07-31 live
test refuted that hypothesis: while A held LED 14, B used a different key to
LOCK the same LED and converted to a different timer address. A LOCK `NG`
remains a typed rejection and causes no CONVERT, UNLOCK, or Python VSMD
read/write, but AppManager does not provide that rejection as LED-ID-exclusive
cross-process arbitration.

After LOCK succeeds, every CONVERT failure attempts at most one best-effort
UNLOCK using the exact generated key and immutable IDs. There is no automatic
LOCK, CONVERT, socket, or pulse retry. If CONVERT and UNLOCK both fail,
`AppManagerAcquireCleanupError` retains both typed errors without exposing the
key, endpoint, memory address, or stack trace through the production error
response.

Normal exceptions, `KeyboardInterrupt`, and `SystemExit` enter best-effort
pulse cleanup. Hard termination such as `kill -9`, kernel panic, or power
loss cannot run Python `finally` and therefore has no code-level cleanup
guarantee. Unknown-key UNLOCK, blind/global UNLOCK, inferred VSMD writes, and
automatic AppManager or `vsmd_edison` service control are prohibited.

The live request/response sequence, known-lease cleanup, PCAP attribution
limitation, read-only post-state, and external evidence hashes are recorded in
[`evidence/app-manager-lock-competition-20260731.md`](evidence/app-manager-lock-competition-20260731.md).
The remote test did not observe physical illumination. `INTERP_LOCK` must be
treated as an interpolation timer lease/slot allocation mechanism, not a
cross-process mutex. The observed timer addresses 502 and 504 show only that
the two keys received different valid slots in that run; they are not fixed
addresses or a guarantee about AppManager's allocator or slot reuse policy.

OS process coordination is separate from legacy v1 TCP framing, AppManager
command compatibility, and VSMD memory-access compatibility. Cooperating
RobotController processes use the whole-Sota
`robot_controller.posix_process_lock.FcntlProcessLock`, with default path
`/run/lock/robot-controller-sota.lock`. It uses nonblocking kernel `flock` and
does not add a TCP field, command, response, or connection to either v1 or v2.
The compatibility API names `AppManagerLedLock` and `AppManagerVsmdLedLock`
remain unchanged, but the word `Lock` in those names is not evidence of
cross-process arbitration.

The production server acquires the process lock only for the live Sota double
opt-in and does so before constructing the application, Backend, listen socket,
or AppManager/VSMD transport. Direct-live diagnostics use the same guard;
read-only and Fake-only paths do not. Contention fails immediately without
retry. This advisory lock coordinates only participants using the same
pathname and cannot exclude direct TCP 6495/6498 clients or other
non-cooperating programs.

```text
phase7_fault_recovery_in_code = complete
phase7_fault_recovery_fake_regression = complete
lock-only competition probe = completed_with_observed_slot_allocation
cross-process LED exclusion = provided for cooperating RobotController processes by whole-Sota FcntlProcessLock
SotaAppManager LED-ID-exclusive arbitration = not provided
phase7_fault_recovery = complete
Phase 8 = allowed after this documentation correction is committed and pushed
full_sota_command_target_integration = pending
```

The probe need not be rerun to establish the observed semantics. The separate
whole-Sota design correction has unit, production-startup, diagnostic, Edison
preflight, and Linux subprocess evidence. It does not claim enforcement over
non-cooperating processes or alter the verified production mouth LED normal
path. Phase 8 may begin after this documentation correction is committed and
pushed.

## 19. Sota raw-axis read-only runtime acceptance

2026-08-01、revision
`9008d062847d46ed0f85c7cb5c942c74ff7411e9`のread-only axis observerを
Intel Edison / CPython 3.6.15上でruntime acceptanceした。VSMD memory readにより
32個のsigned S16値を1 sampleおよび100 ms指定の10 samplesとして取得し、CSVの
exact header、37 columns、row count、sample sequence、timing field、signed S16範囲を
検証した。

この結果はraw storage observation pathだけを対象とする。`ServoReadPos[32]`のraw index
mappingはunknownのままであり、degree-level protocol compatibilityおよびwrite-path
compatibilityは主張しない。read requestはTCP 6498へ送信されるが、reviewed observer pathは
VSMD memory-write operationを含まない。network captureによるwrite非発生の証明ではない。
詳細な実行結果、証跡範囲、未確認事項は
[`edison-read-only-axis-observer-acceptance.md`](edison-read-only-axis-observer-acceptance.md)
に記録する。

```text
read-only axis observer runtime acceptance = completed
accepted revision = 9008d062847d46ed0f85c7cb5c942c74ff7411e9
raw values read per sample = 32 signed S16
raw index mapping = unknown
degree-level compatibility = not claimed
write-path compatibility = not claimed
live servo write = prohibited
```
