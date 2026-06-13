# RobotController TCPサーバー ドキュメント

対象リポジトリ: `social-robotics-lab/RobotController`  
作成日: 2026-06-13  
対象: VSTONE社製ロボット Sota、CommU、くるみちゃん相当機体（実装上の設定名は `Dog`）をTCP経由で制御するためのJavaサーバー

---

## 1. 概要

`RobotController` は、VSTONE社が提供するロボット制御ライブラリを利用し、Sota、CommU、くるみちゃん相当機体を外部プログラムからTCP経由で操作するためのサーバープログラムである。クライアントはTCPソケットを通じてコマンド名と必要なペイロードを送信し、サーバー側は音声再生、姿勢制御、モーション再生、アイドルモーション、現在角度の取得を実行する。

このサーバーはJavaで実装されており、ロボット本体上で `java -jar RobotController.jar` として実行する想定である。通信プロトコルは非常に単純で、各メッセージを「4バイト長さ + データ本体」の形式で送る。`read_axes` のみサーバーからクライアントへ応答が返る。それ以外のコマンドでは、正常終了時にも明示的な応答は返らない。

---

## 2. 主な機能

このTCPサーバーは、以下の機能を提供する。

| 機能 | 概要 |
|---|---|
| WAV音声再生 | クライアントから送信されたWAVデータをロボット側で一時ファイルに保存し、`aplay` で再生する。 |
| 音声停止 | `killall aplay` により再生中の音声を停止する。 |
| 単一姿勢再生 | JSONで指定されたサーボ角度・LED値・遷移時間に基づいてロボットを制御する。 |
| 姿勢停止 | 現在のサーボ角度を読み取り、短時間で現在姿勢を保持する。 |
| モーション再生 | 姿勢JSONの配列を順に再生する。 |
| モーション停止 | 実行中のモーションスレッドをキャンセルする。 |
| アイドルモーション再生 | ロボット種別ごとに定義された2姿勢を繰り返し再生する。 |
| アイドルモーション停止 | 実行中のアイドルモーションスレッドをキャンセルする。 |
| 現在角度取得 | 現在のサーボ位置を読み取り、JSONとしてクライアントに返す。 |

---

## 3. 対応ロボットと設定名

`System.properties` の `ROBOT_TYPE` により、対象ロボットを指定する。

| ロボット | `ROBOT_TYPE` の値 | 備考 |
|---|---|---|
| Sota | `Sota` | README上の主要対象。 |
| CommU | `CommU` | README上の主要対象。 |
| くるみちゃん相当機体 | `Dog` | 実装上は `Dog` として分岐している。`Kurumi` や `くるみちゃん` ではない。 |

`ROBOT_TYPE` は文字列比較で判定されるため、大文字・小文字を含めて正確に記述する必要がある。

---

## 4. ディレクトリ構成

主要な構成は以下の通りである。

```text
RobotController/
├── README.md
├── System.properties
└── src/
    ├── main/
    │   ├── App.java
    │   ├── Params.java
    │   ├── ServerIO.java
    │   └── TCPServer.java
    ├── servo/
    │   ├── RobotSys.java
    │   ├── ServoConverter.java
    │   ├── ServoConverter_Sota.java
    │   ├── ServoConverter_CommU.java
    │   └── ServoConverter_Dog.java
    ├── led/
    │   ├── LedConverter.java
    │   ├── LedConverter_Sota.java
    │   ├── LedConverter_CommU.java
    │   └── LedConverter_Dog.java
    └── utils/
        ├── AxisReader.java
        ├── SpeechPlayer.java
        ├── PosePlayer.java
        ├── PoseExecutorThread.java
        ├── MotionPlayer.java
        ├── MotionExecutorThread.java
        ├── IdleMotionPlayer.java
        └── IdleMotionExecutorThread.java
```

各ファイルの役割は以下の通りである。

| ファイル | 役割 |
|---|---|
| `App.java` | アプリケーションのエントリポイント。TCPサーバーと姿勢実行スレッドを起動する。 |
| `Params.java` | `System.properties` を読み込み、ロボット種別とポート番号を保持する。 |
| `TCPServer.java` | TCP接続を受け付け、受信したコマンドを各プレイヤー・リーダーへ振り分ける。 |
| `ServerIO.java` | 4バイト長さヘッダ付きメッセージの読み書きを行う。 |
| `RobotSys.java` | VSTONEライブラリの初期化、ロボット種別ごとの初期姿勢・LED・アイドル姿勢の定義を行う。 |
| `ServoConverter_*.java` | JSON上のサーボ名とVSTONEライブラリ上のサーボID・値を相互変換する。 |
| `LedConverter_*.java` | JSON上のLED名とVSTONEライブラリ上のLED ID・値を相互変換する。 |
| `SpeechPlayer.java` | WAVデータの一時保存と `aplay` による再生、音声停止を行う。 |
| `PosePlayer.java` | 単一姿勢JSONをキューへ投入する。 |
| `PoseExecutorThread.java` | 姿勢キューからJSONを取り出し、実際にロボットへ反映する。 |
| `MotionPlayer.java` | 姿勢配列をモーションとして実行するスレッドを管理する。 |
| `MotionExecutorThread.java` | 姿勢配列を順に再生する。 |
| `IdleMotionPlayer.java` | アイドルモーションの開始・停止を管理する。 |
| `IdleMotionExecutorThread.java` | ロボット種別ごとのアイドル姿勢を繰り返し再生する。 |
| `AxisReader.java` | 現在のサーボ位置を取得し、JSON変換可能なMapとして返す。 |

---

## 5. 動作環境と依存ライブラリ

### 5.1 Javaバージョン

READMEでは JavaSE-1.8 が指定されている。

### 5.2 必要ライブラリ

ビルド時には以下のライブラリが必要である。

```text
core-2.2.jar
gson-2.8.5.jar
javase-2.2.jar
jna-4.1.0.jar
json-20180813.jar
sotalib.jar
```

`sotalib.jar` はVSTONE公式の SotaSample から取得する想定である。

### 5.3 実行環境上の外部コマンド

音声再生には `aplay` が使用される。音声停止には `killall aplay` が使用される。そのため、実行環境に `aplay` と `killall` が存在し、Javaプロセスから実行可能である必要がある。

---

## 6. 設定ファイル

`System.properties` でロボット種別とポート番号を指定する。

```properties
#-----------------------------
# Robot type: CommU or Sota or Dog
#-----------------------------
ROBOT_TYPE=Sota

#-----------------------------
# Server port
#-----------------------------
PORT=22222
```

### 6.1 `ROBOT_TYPE`

使用するロボット種別を指定する。指定可能な値は以下である。

```text
Sota
CommU
Dog
```

`Dog` は、くるみちゃん相当機体を扱うための実装上の種別名として使用する。

### 6.2 `PORT`

TCPサーバーが待ち受けるポート番号を指定する。初期値は `22222` である。`Params.java` はこの値を整数として読み込むため、数値以外を指定すると起動時にエラーになる。

---

## 7. ビルドと実行

### 7.1 ビルド

READMEでは、Eclipseを用いてJARファイルを作成する手順が想定されている。必要なライブラリをビルドパスに追加し、実行可能JARとしてエクスポートする。

推奨されるJAR名は以下である。

```text
RobotController.jar
```

### 7.2 配置

作成したJARファイルと `System.properties` をロボット本体上の同一ディレクトリに配置する。`Params.java` は `System.properties` を相対パスで読み込むため、実行時のカレントディレクトリに注意する。

### 7.3 実行

ロボット本体上で以下を実行する。

```bash
java -jar RobotController.jar
```

サーバーが起動すると、`System.properties` の `PORT` でTCP接続を待ち受ける。

---

## 8. サーバーの実行モデル

`App.java` は、固定サイズ2のスレッドプールを作成し、以下の2つを起動する。

```text
TCPServer
PoseExecutorThread
```

`TCPServer` は `ServerSocket` でクライアント接続を受け付ける。接続を受け付けるたびに `RecvThread` を作成し、コマンドを処理する。

重要な点として、このサーバーは「1つのTCP接続で1コマンド」を処理する実装である。`RecvThread` は最初にコマンド名を1つ読み取り、それに対応するペイロードを必要に応じて読み取り、処理後にソケットを閉じる。複数コマンドを同じTCP接続で連続送信する前提にはなっていない。

したがって、クライアント側では、コマンド送信ごとにTCP接続を作成し、送信後に切断する実装にするのが安全である。

---

## 9. TCP通信プロトコル

### 9.1 フレーム形式

すべてのメッセージは以下の形式で送受信される。

```text
+----------------------+------------------+
| 4 bytes              | N bytes          |
+----------------------+------------------+
| payload length, int  | payload body     |
+----------------------+------------------+
```

先頭4バイトは、後続ペイロードのバイト長である。Java側では `ByteBuffer` を `ByteOrder.BIG_ENDIAN` として読み取っているため、クライアント側もbig-endianで整数を送信する必要がある。

### 9.2 文字列エンコーディング

コマンド名はASCII文字列で送る。JSONペイロードはUTF-8で送ることを推奨する。実装では `new String(byte[])` が使われており、Java実行環境のデフォルト文字コードに依存する箇所があるため、JSONのキーはASCIIに限定するのが安全である。

### 9.3 コマンド送信の基本形

ペイロードを持たないコマンドでは、以下の1フレームだけを送信する。

```text
[length of command]
[command string]
```

ペイロードを持つコマンドでは、コマンド名に続けてペイロードをもう1フレーム送信する。

```text
[length of command]
[command string]
[length of payload]
[payload body]
```

`read_axes` では、サーバーから同じフレーム形式でJSON応答が返る。

---

## 10. コマンド一覧

| コマンド | 追加ペイロード | 応答 | 概要 |
|---|---|---|---|
| `play_wav` | WAVバイナリ | なし | WAVデータをロボット側で再生する。 |
| `stop_wav` | なし | なし | 再生中の音声を停止する。 |
| `play_pose` | 姿勢JSONオブジェクト | なし | 単一姿勢を再生する。 |
| `stop_pose` | なし | なし | 現在姿勢を短時間で保持する。 |
| `play_motion` | 姿勢JSONオブジェクトの配列 | なし | 複数姿勢を順に再生する。 |
| `stop_motion` | なし | なし | 実行中のモーションを停止する。 |
| `play_idle_motion` | アイドル設定JSONオブジェクト | なし | アイドルモーションを開始する。 |
| `stop_idle_motion` | なし | なし | アイドルモーションを停止する。 |
| `read_axes` | なし | サーボ角度JSON | 現在のサーボ角度を取得する。 |

---

## 11. コマンド詳細

### 11.1 `play_wav`

WAV音声を再生する。

送信形式は以下である。

```text
frame 1: "play_wav"
frame 2: WAV binary data
```

サーバーは受け取ったWAVデータを `__temp_wav` という一時ファイルに保存し、以下に相当する処理で再生する。

```bash
aplay __temp_wav
```

注意点として、一時ファイル名が固定であるため、複数クライアントから同時に `play_wav` を実行するとファイルの競合が起きる可能性がある。また、`stop_wav` は `killall aplay` を実行するため、このサーバーが起動した音声以外の `aplay` プロセスも停止する可能性がある。

### 11.2 `stop_wav`

音声再生を停止する。

送信形式は以下である。

```text
frame 1: "stop_wav"
```

追加ペイロードはない。

### 11.3 `play_pose`

単一姿勢を再生する。

送信形式は以下である。

```text
frame 1: "play_pose"
frame 2: pose JSON object
```

姿勢JSONは以下の形式である。

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

必須条件は以下である。

| 項目 | 必須 | 説明 |
|---|---:|---|
| `Msec` | 必須 | 姿勢遷移時間。ミリ秒単位。 |
| `ServoMap` | 条件付き | `ServoMap` または `LedMap` の少なくとも一方が必要。 |
| `LedMap` | 条件付き | `ServoMap` または `LedMap` の少なくとも一方が必要。 |

`ServoMap` のキーはロボット種別ごとに異なる。未定義キーを送ると実装上は `map.get(key)` の結果が `null` になり、例外が発生する可能性がある。そのため、後述のサーボキー一覧に含まれるキーのみを送信する。

### 11.4 `stop_pose`

現在姿勢を読み取り、100 msec の姿勢として再投入する。

送信形式は以下である。

```text
frame 1: "stop_pose"
```

このコマンドは、姿勢キューを明示的に空にする処理ではない。現在角度を読み取り、短時間で現在姿勢を保持するための姿勢を `PosePlayer` に送る実装である。すでにキューに入っている姿勢や別スレッドで動作中のモーションとの相互作用には注意する。

### 11.5 `play_motion`

複数の姿勢を順に再生する。

送信形式は以下である。

```text
frame 1: "play_motion"
frame 2: motion JSON array
```

ペイロードは、姿勢JSONオブジェクトの配列である。

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

`MotionExecutorThread` は各要素を `PosePlayer.play()` に渡し、その姿勢の `Msec` だけsleepする。したがって、各要素には `Msec` が必要である。

### 11.6 `stop_motion`

実行中のモーションを停止する。

送信形式は以下である。

```text
frame 1: "stop_motion"
```

実装上は `Future.cancel(true)` によりモーションスレッドへ割り込みを行う。すでに `PoseExecutorThread` のキューに投入済みの姿勢がある場合、それらが完全に破棄されるとは限らない。

### 11.7 `play_idle_motion`

ロボット種別ごとに定義されたアイドルモーションを開始する。

送信形式は以下である。

```text
frame 1: "play_idle_motion"
frame 2: idle setting JSON object
```

ペイロード例は以下である。

```json
{
  "Speed": 1.0,
  "Pause": 1000
}
```

| 項目 | 型 | 既定値 | 説明 |
|---|---|---:|---|
| `Speed` | number | `1.0` | アイドル動作の速度係数。`1000 / Speed` が姿勢遷移時間として使われる。 |
| `Pause` | integer | `1000` | 各アイドル姿勢間の待機時間。ミリ秒単位。 |

`Speed` は正の値を指定する。`0` や負値に対する明示的な検証は実装されていない。

### 11.8 `stop_idle_motion`

アイドルモーションを停止する。

送信形式は以下である。

```text
frame 1: "stop_idle_motion"
```

### 11.9 `read_axes`

現在のサーボ角度を取得する。

送信形式は以下である。

```text
frame 1: "read_axes"
```

サーバーは、現在のサーボ値を読み取り、ロボット種別ごとのサーボ名をキーとするJSONを返す。応答も、4バイトbig-endian長さヘッダ付きフレームで送られる。

応答例は以下である。

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

返却されるキーは `ROBOT_TYPE` によって異なる。

---

## 12. Pythonクライアント例

以下は、Python 3 からコマンドを送信する最小実装である。

```python
import json
import socket
import struct
from pathlib import Path


def send_frame(sock: socket.socket, data):
    """4バイトbig-endian長さヘッダ付きで1フレーム送信する。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    elif isinstance(data, (dict, list)):
        data = json.dumps(data, ensure_ascii=False).encode("utf-8")
    elif not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"unsupported payload type: {type(data)}")

    sock.sendall(struct.pack(">i", len(data)))
    sock.sendall(data)


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    received = 0
    while received < size:
        chunk = sock.recv(size - received)
        if not chunk:
            raise ConnectionError("socket closed while receiving data")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def recv_frame(sock: socket.socket) -> bytes:
    header = recv_exact(sock, 4)
    size = struct.unpack(">i", header)[0]
    return recv_exact(sock, size)


def send_command(host: str, port: int, command: str, payload=None, expect_reply=False):
    with socket.create_connection((host, port), timeout=5) as sock:
        send_frame(sock, command)
        if payload is not None:
            send_frame(sock, payload)
        if expect_reply:
            return recv_frame(sock)
    return None
```

### 12.1 姿勢を送る例

```python
HOST = "192.168.0.10"
PORT = 22222

pose = {
    "Msec": 700,
    "ServoMap": {
        "HEAD_Y": 20,
        "HEAD_P": -5
    },
    "LedMap": {
        "PWR_BTN_R": 0,
        "PWR_BTN_G": 0,
        "PWR_BTN_B": 255
    }
}

send_command(HOST, PORT, "play_pose", pose)
```

### 12.2 現在角度を取得する例

```python
reply = send_command(HOST, PORT, "read_axes", expect_reply=True)
axes = json.loads(reply.decode("utf-8"))
print(axes)
```

### 12.3 WAVを再生する例

```python
wav_data = Path("sample.wav").read_bytes()
send_command(HOST, PORT, "play_wav", wav_data)
```

### 12.4 モーションを再生する例

```python
motion = [
    {
        "Msec": 500,
        "ServoMap": {"HEAD_Y": 20}
    },
    {
        "Msec": 500,
        "ServoMap": {"HEAD_Y": -20}
    },
    {
        "Msec": 500,
        "ServoMap": {"HEAD_Y": 0}
    }
]

send_command(HOST, PORT, "play_motion", motion)
```

### 12.5 アイドルモーションを開始・停止する例

```python
send_command(HOST, PORT, "play_idle_motion", {"Speed": 1.0, "Pause": 1000})

# 停止するとき
send_command(HOST, PORT, "stop_idle_motion")
```

---

## 13. JSON仕様

### 13.1 Pose JSON

```json
{
  "Msec": 700,
  "ServoMap": {
    "SERVO_NAME": 0
  },
  "LedMap": {
    "LED_NAME": 255
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `Msec` | integer | 姿勢遷移時間。ミリ秒。 |
| `ServoMap` | object | サーボ名から角度値へのマップ。 |
| `LedMap` | object | LED名から輝度値へのマップ。 |

`ServoMap` と `LedMap` はどちらか一方だけでもよい。ただし、両方とも省略すると `PosePlayer` は姿勢を受理しない。

### 13.2 Motion JSON

```json
[
  {
    "Msec": 500,
    "ServoMap": {"HEAD_Y": 20}
  },
  {
    "Msec": 500,
    "ServoMap": {"HEAD_Y": 0}
  }
]
```

Motion JSONは、Pose JSONの配列である。

### 13.3 Idle Motion JSON

```json
{
  "Speed": 1.0,
  "Pause": 1000
}
```

| フィールド | 型 | 省略時 | 説明 |
|---|---|---:|---|
| `Speed` | number | `1.0` | アイドル姿勢の遷移速度。 |
| `Pause` | integer | `1000` | 姿勢間の停止時間。ミリ秒。 |

---

## 14. サーボキー仕様

JSONの `ServoMap` で指定できるキーは、ロボット種別ごとに異なる。値は角度に相当する整数として指定する。各コンバータでは、指定値が可動範囲外の場合、最小値・最大値に丸められる。

### 14.1 Sota

| キー | 内部ID | 入力範囲 | 備考 |
|---|---:|---:|---|
| `BODY_Y` | 1 | -61 ～ 61 | 内部変換で比率 2.429 を使用。 |
| `L_SHOU` | 2 | -180 ～ 60 | 左肩。 |
| `L_ELBO` | 3 | -90 ～ 65 | 左肘。 |
| `R_SHOU` | 4 | -60 ～ 180 | 右肩。 |
| `R_ELBO` | 5 | -65 ～ 90 | 右肘。 |
| `HEAD_Y` | 6 | -85 ～ 85 | 内部変換で比率 1.75 を使用。 |
| `HEAD_P` | 7 | -27 ～ 5 | 頭部ピッチ。 |
| `HEAD_R` | 8 | -30 ～ 30 | 内部変換で比率 1.75 を使用。 |

### 14.2 CommU

| キー | 内部ID | 入力範囲 | 備考 |
|---|---:|---:|---|
| `BODY_P` | 1 | -15 ～ 15 | 内部変換で比率 3.833 を使用。 |
| `BODY_Y` | 2 | -67 ～ 67 | 胴体ヨー。 |
| `L_SHOU_P` | 3 | -108 ～ 108 | 内部変換で比率 1.364 を使用。 |
| `L_SHOU_R` | 4 | -45 ～ 30 | 左肩ロール。 |
| `R_SHOU_P` | 5 | -108 ～ 108 | 内部変換で比率 1.364 を使用。 |
| `R_SHOU_R` | 6 | -30 ～ 45 | 右肩ロール。 |
| `HEAD_P` | 7 | -20 ～ 25 | 頭部ピッチ。 |
| `HEAD_R` | 8 | -15 ～ 15 | 内部変換で比率 4.333 を使用。 |
| `HEAD_Y` | 9 | -85 ～ 85 | 頭部ヨー。 |
| `EYES_P` | 10 | -22 ～ 22 | 目ピッチ。 |
| `L_EYE_Y` | 11 | -35 ～ 20 | 左目ヨー。 |
| `R_EYE_Y` | 12 | -20 ～ 35 | 右目ヨー。 |
| `EYELID` | 13 | -65 ～ 3 | まぶた。 |
| `MOUTH` | 14 | -3 ～ 55 | 口。 |

### 14.3 Dog / くるみちゃん相当機体

| キー | 内部ID | 入力範囲 | 備考 |
|---|---:|---:|---|
| `BODY_Y` | 1 | -80 ～ 80 | 胴体ヨー。 |
| `L_ELBO` | 3 | -70 ～ 70 | 左肘相当。 |
| `R_ELBO` | 5 | -70 ～ 70 | 右肘相当。 |
| `HEAD_P` | 7 | -70 ～ 70 | 頭部ピッチ。 |
| `HEAD_R` | 8 | -50 ～ 50 | 頭部ロール。 |

---

## 15. LEDキー仕様

JSONの `LedMap` で指定できるキーは、ロボット種別ごとに異なる。値は `0` から `255` の整数で指定する。各コンバータでは、範囲外の値は `0` または `255` に丸められる。

### 15.1 Sota

| キー | 内部ID | 値範囲 |
|---|---:|---:|
| `PWR_BTN_R` | 0 | 0 ～ 255 |
| `PWR_BTN_G` | 1 | 0 ～ 255 |
| `PWR_BTN_B` | 2 | 0 ～ 255 |
| `R_EYE_R` | 8 | 0 ～ 255 |
| `R_EYE_G` | 9 | 0 ～ 255 |
| `R_EYE_B` | 10 | 0 ～ 255 |
| `L_EYE_R` | 11 | 0 ～ 255 |
| `L_EYE_G` | 12 | 0 ～ 255 |
| `L_EYE_B` | 13 | 0 ～ 255 |
| `MOUTH` | 14 | 0 ～ 255 |

### 15.2 CommU

| キー | 内部ID | 値範囲 |
|---|---:|---:|
| `PWR_BTN_R` | 0 | 0 ～ 255 |
| `PWR_BTN_G` | 1 | 0 ～ 255 |
| `PWR_BTN_B` | 2 | 0 ～ 255 |
| `BODY_R` | 3 | 0 ～ 255 |
| `BODY_G` | 4 | 0 ～ 255 |
| `BODY_B` | 5 | 0 ～ 255 |
| `L_CHEEK` | 6 | 0 ～ 255 |
| `R_CHEEK` | 7 | 0 ～ 255 |

### 15.3 Dog / くるみちゃん相当機体

| キー | 内部ID | 値範囲 |
|---|---:|---:|
| `PWR_BTN_R` | 0 | 0 ～ 255 |
| `PWR_BTN_G` | 1 | 0 ～ 255 |
| `PWR_BTN_B` | 2 | 0 ～ 255 |

---

## 16. `read_axes` の返却キー

`read_axes` では、対象ロボット種別ごとに以下のサーボIDを読み取り、サーボ名をキーとするJSONとして返す。

| `ROBOT_TYPE` | 読み取り対象 |
|---|---|
| `CommU` | ID 1 ～ 14 |
| `Sota` | ID 1 ～ 8 |
| `Dog` | ID 1, 3, 5, 7, 8 |

返却JSONのキーは、各ロボットの `ServoConverter_*` の `mapToJson()` に対応する。

---

## 17. アイドルモーション仕様

アイドルモーションは `RobotSys.idleServoMaps` にロボット種別ごとに2姿勢として定義されている。`IdleMotionExecutorThread` は、2つの姿勢を交互に再生し続ける。

動作周期は以下のように決まる。

```text
msec = 1000 / Speed
sleep time = msec + Pause
```

各姿勢は次のようなJSONとして `PosePlayer` に渡される。

```json
{
  "Msec": 1000,
  "ServoMap": {
    "...": 0
  }
}
```

`Speed` を大きくすると姿勢遷移時間が短くなり、動作が速くなる。`Pause` を大きくすると各姿勢間の待機が長くなる。

---

## 18. 例外・エラー処理に関する注意

このサーバーは研究・実験用の簡潔な実装であり、クライアントへ構造化されたエラー応答を返す設計ではない。以下の点に注意する。

1. 未知のコマンドを送ると、何も実行されず接続が閉じられる。
2. 多くのコマンドは成功時にも応答を返さない。
3. JSONのキーが未定義の場合、`map.get(key)` の結果が `null` になり、例外が発生する可能性がある。
4. `ServerIO.read()` は、接続断やEOFに対する明示的な処理が十分ではない。クライアントは必ず宣言したバイト数と実データ長を一致させる必要がある。
5. `stop_motion` や `stop_idle_motion` は、開始前に呼ぶと `future` が未設定で例外になる可能性がある。
6. `play_wav` は一時ファイル名 `__temp_wav` を固定で使用するため、同時実行に弱い。
7. `stop_wav` は `killall aplay` を実行するため、同じロボット上の他の `aplay` プロセスも停止する可能性がある。
8. 認証、暗号化、アクセス制御は実装されていない。

---

## 19. セキュリティ上の注意

このTCPサーバーには認証機構がない。そのため、同一ネットワーク上の任意のクライアントが接続できる環境では、意図しないロボット操作が発生する可能性がある。

実験環境で使用する場合は、以下を推奨する。

1. ロボットと制御用PCを閉じたネットワークに置く。
2. 不特定多数が接続できるWi-Fiや公開ネットワークでは使用しない。
3. 必要に応じて、OS側のファイアウォールで接続元IPを制限する。
4. TCPサーバー側に認証トークン付きのコマンドを追加することを検討する。
5. 外部公開が必要な場合は、TLS終端やVPNを併用する。

---

## 20. 拡張方法

### 20.1 新しいコマンドを追加する

新しいコマンドを追加する場合は、主に `TCPServer.java` の `RecvThread.run()` に分岐を追加する。

典型的な実装手順は以下である。

1. コマンド名を決める。
2. 追加ペイロードが必要かどうかを決める。
3. `TCPServer.java` で `cmd.equals("new_command")` の分岐を追加する。
4. 必要に応じて `serverIO.read()` で追加ペイロードを読む。
5. 処理結果を返す必要がある場合は `serverIO.write()` で応答を返す。
6. クライアント側の実装と本ドキュメントのコマンド表を更新する。

### 20.2 新しいロボット種別を追加する

新しいロボット種別を追加する場合は、少なくとも以下を更新する必要がある。

| 対象 | 追加内容 |
|---|---|
| `System.properties` | 新しい `ROBOT_TYPE` の値を設定できるようにする。 |
| `RobotSys.java` | VSTONEライブラリの初期化、初期姿勢、トルク、LED、アイドル姿勢を定義する。 |
| `ServoConverter.java` | 新しい `ServoConverter_*` へ分岐する。 |
| `ServoConverter_*.java` | サーボ名、ID、範囲、スケール変換を定義する。 |
| `LedConverter.java` | 新しい `LedConverter_*` へ分岐する。 |
| `LedConverter_*.java` | LED名、ID、値範囲を定義する。 |
| `AxisReader.java` | `read_axes` で読み取るサーボIDを定義する。 |

### 20.3 エラー応答を追加する

現状では、`read_axes` 以外のコマンドは応答を返さない。クライアントからの制御を安定化したい場合は、すべてのコマンドで以下のようなJSON応答を返す設計に変更するとよい。

```json
{
  "ok": true,
  "command": "play_pose"
}
```

エラー時には以下のような応答が考えられる。

```json
{
  "ok": false,
  "command": "play_pose",
  "error": "missing Msec"
}
```

この場合、`TCPServer.java` の各分岐で例外を捕捉し、`serverIO.write()` によりJSON文字列を返す実装にすると扱いやすい。

---

## 21. 運用チェックリスト

実験前には以下を確認する。

1. `System.properties` の `ROBOT_TYPE` が実機に合っている。
2. `System.properties` の `PORT` がクライアント側の接続先ポートと一致している。
3. ロボット本体上で `java -jar RobotController.jar` が正常に起動している。
4. クライアントPCからロボットのIPアドレスとポートにTCP接続できる。
5. `read_axes` が正常に応答する。
6. 小さい角度・短い時間の `play_pose` で動作確認する。
7. WAVファイルの形式がロボット側の `aplay` で再生可能である。
8. 緊急停止や電源遮断の手順を実験者が把握している。
9. 不要なクライアントが同じネットワークから接続できないようにしている。

---

## 22. 最小動作確認シナリオ

### 22.1 接続確認

まず `read_axes` を送信し、JSON応答が返ることを確認する。

```python
reply = send_command(HOST, PORT, "read_axes", expect_reply=True)
print(reply.decode("utf-8"))
```

### 22.2 LED確認

ロボットの電源ボタンLEDを青にする。

```python
pose = {
    "Msec": 300,
    "LedMap": {
        "PWR_BTN_R": 0,
        "PWR_BTN_G": 0,
        "PWR_BTN_B": 255
    }
}
send_command(HOST, PORT, "play_pose", pose)
```

### 22.3 首振り確認（Sota例）

```python
motion = [
    {"Msec": 500, "ServoMap": {"HEAD_Y": 20}},
    {"Msec": 500, "ServoMap": {"HEAD_Y": -20}},
    {"Msec": 500, "ServoMap": {"HEAD_Y": 0}}
]
send_command(HOST, PORT, "play_motion", motion)
```

---

## 23. 実装上の改善候補

今後の保守性・安全性を高める場合、以下の改善が有効である。

| 改善項目 | 内容 |
|---|---|
| 全コマンドへの応答追加 | 成功・失敗をクライアントで判定できるようにする。 |
| EOF処理の強化 | `ServerIO.read()` で `InputStream.read()` が `-1` を返した場合に例外化する。 |
| JSONバリデーション | 未定義キー、型不一致、範囲外値を明示的に検査する。 |
| UTF-8固定化 | `new String(bytes, StandardCharsets.UTF_8)` を使用する。 |
| WAV一時ファイル名の一意化 | 同時再生要求による競合を避ける。 |
| `stop_*` のnull安全化 | 開始前に停止コマンドが来ても例外にならないようにする。 |
| 認証追加 | 実験ネットワーク外からの誤操作を防ぐ。 |
| ログ整備 | 受信コマンド、エラー、実行結果を時刻付きで記録する。 |
| 同時実行制御 | `play_pose`、`play_motion`、`play_idle_motion` の競合を整理する。 |

---

## 24. まとめ

`RobotController` は、VSTONE社製ロボットを外部プログラムから簡潔に制御するためのTCPサーバーである。プロトコルは4バイト長さヘッダ付きのシンプルなフレーム形式であり、Python、Java、Node.jsなど任意のTCPクライアントから容易に利用できる。

一方で、実装は研究・実験用途に近く、認証、エラー応答、同時実行制御、入力検証は限定的である。実験運用では、閉じたネットワークで利用し、`read_axes` と小さな `play_pose` から段階的に動作確認することが望ましい。
