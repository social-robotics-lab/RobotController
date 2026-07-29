# docs/migration-plan.md

## 1. 文書の目的

本書は、既存Java版RobotControllerからPython版へ、安全かつ段階的に移行するための作業順序、判定基準、実機試験およびロールバック方針を定義する。

## 2. 移行原則

* Java版を直ちに廃止しない。
* Python版は小さい機能単位で実装する。
* Windows上の自動テストを先に完成させる。
* 実機試験は読み取り中心から開始する。
* サーボ動作は1軸、小角度、低速から開始する。
* Java版とPython版を同時に実機制御へ接続しない。
* 実機試験ごとにロールバック方法を準備する。
* 互換性と安全性を、機能追加より優先する。
* 各フェーズの完了条件を満たすまで次へ進まない。
* 本番コードはCPython 3.6.15で構文解析・実行可能に保つ。
* Codexを含む自動エージェントは、許可の有無にかかわらず実機デバイス、`systemctl`、サーボ、LEDおよびトルクを操作しない。
* 実機試験はエージェントが手順を作成し、人間が内容を確認して手動実行する。

## 3. フェーズ0：環境調査と仕様固定

### 作業

* Edison版Sotaの本番PythonをCPython 3.6.15として記録する。
* CommUとDogのOSおよびPython環境を確認する。
* 現行Java版のコマンドと変換処理を整理する。
* `robo-tutorial`の全クライアント利用例を検索する。
* 実験用プログラムが独自のコマンド利用をしていないか確認する。
* 各ロボットの軸、範囲、LED、初期姿勢を記録する。
* プロトコルv1の仕様を固定する。
* 非公式低レベル実装のURL、完全なcommit SHA、確認日、ライセンス、利用方法および検証状態をReference baselinesへ記録する。

### 成果物

* 本docs一式
* 実行環境一覧
* 軸・LEDプロファイル
* 互換性テスト一覧
* 未解決事項一覧

### 完了条件

* 正常系互換性の定義が合意されている。
* 実機対応Pythonバージョンが判明している。
* 本番コードのCPython 3.6.15制約が合意されている。
* Java版を参照実装として実行できる。

## 4. フェーズ1：プロジェクト基盤

### 作業

* `python_server/`を作成する。
* パッケージ構造を作成する。
* テスト環境を作成する。
* 型検査、静的解析、フォーマッタを設定する。
* 設定読み込みとログを実装する。
* CIを構成する。
* pytestをPython 3.6対応版へ固定する。初期候補は`pytest==6.2.5`とする。

### 実装しないもの

* TCPサーバー
* 実機制御
* 音声再生
* モーション

### 完了条件

* Windowsでテストが実行できる。
* CPython 3.6.15でもテストまたは同等の構文・互換性検査を実行できる。
* 本番コードがCPython 3.6.15で構文解析できる。
* 禁止されたPython 3.7以降の構文・標準ライブラリAPIが本番コードに含まれない。
* 空のアプリケーションが起動・終了できる。

## 5. フェーズ2：フレーム処理

### 作業

* 4バイトbig-endianフレームの読み書きを実装する。
* EOF、部分受信、タイムアウトを実装する。
* Frame Codecが呼び出し側から`max_length`を受け取るようにする。固定最大値をCodec内部へ持たせない。
* 正常系v1の有効長を`0 <= length <= min(max_length, 2147483647)`とする。
* `0x80000000`以上を本文確保前に拒否する。
* 長さ0をCodecでは`b""`として処理する。
* バイト列単位のテストを作成する。

### 必須テスト

* 正常な短いフレーム
* 日本語を含むUTF-8 JSON
* 1バイトずつの部分受信
* ヘッダ途中のEOF
* 本文途中のEOF
* 長さ0
* 最大長ちょうど
* 最大長超過
* `0x7fffffff`と`0x80000000`の境界
* タイムアウト
* 複数回のsendに分割されたフレーム

### 完了条件

* すべての単体テストが成功する。
* ハードウェア関連コードが存在しない。
* `robottools.py`と同じフレームを読み取れる。
* command 64 bytes、JSON 1 MiB、WAV 20 MiBの各上限を呼び出し側から適用できる。

## 6. フェーズ3：v1 TCPサーバーとMock

### 作業

* TCPサーバーを実装する。
* 同期ソケットと上限付き`ThreadPoolExecutor`を使用する。
* 実行中と投入待ちを合わせた接続ハンドラー数を初期既定値16に制限する。
* 初期版では`asyncio`を使用しない。
* コマンドルーターを実装する。
* JSON検証を実装する。
* Mock Backendを実装する。
* 全9コマンドをMockで処理する。
* `read_axes`応答を実装する。
* コマンド・JSON読み取りを初期既定値5秒、WAVペイロード読み取りを30秒に制限する。
* 状態を`starting`、`initializing`、`ready`、`degraded`、`stopping`、`stopped`、`failed`で管理する。
* バックエンド初期化成功後に`ready`へ遷移してからTCP listenを開始する。
* ネットワークスレッドからハードウェアを直接呼ばず、別の単一Hardware Workerへ渡す。

### 完了条件

* `robo-tutorial`のクライアントから全コマンドを送信できる。
* Mockの状態が期待どおり更新される。
* 不正クライアントによってサーバー全体が停止しない。
* v1の非応答コマンドにACKを返していない。
* `ready`前にTCP listenもハードウェアコマンド実行も開始しない。

## 7. フェーズ4：Motion Scheduler

### 作業

* Poseモデルを実装する。
* Motionモデルを実装する。
* Schedulerを実装する。
* Pose、Motion、Idle Motionへgenerationまたはキャンセルトークンを実装する。
* stop系コマンドを冪等にする。
* Idle Motionを実装する。
* 仮想時計を用いたテストを作成する。

### 競合テスト

* motion中のdirect pose
* idle中のmotion
* motion中の新しいmotion
* stop直後の新しいmotion
* キャンセルされたタスクのsleep復帰
* stopを連続で送信
* 開始前にstopを送信
* サーバー終了中のコマンド

### 完了条件

* 古いタスクがキャンセル後にMockへ指令しない。
* 停止または置換された古い世代がHardware Workerキューに残っていても指令を送らない。
* 動作所有者が常に一つである。
* stop系コマンドが例外を発生させない。

## 8. フェーズ5：Audio Manager

### 作業

* WAV検証を実装する。
* 一意な一時ファイルを使用する。
* 再生プロセスを個別管理する。
* `stop_wav`で管理対象だけを停止する。
* 終了時の一時ファイル削除を実装する。
* Windowsではダミー音声プレイヤーを使用可能にする。

### 完了条件

* 固定名一時ファイルを使用していない。
* `killall`を使用していない。
* 連続する再生要求の動作が定義されている。
* 再生失敗でサーバー全体が停止しない。

## 9. フェーズ6：Sota低レベル読み取り

Sota標準Backend候補は、UARTやI2Cへ直接アクセスせず、既存の
`vsmd_edison`へTCP `127.0.0.1:6498`で接続する。確認済みprotocolのcodec、
buffer付きTCP Transport、byte/typed memory、Sota memory mapおよび
read-only probeを先に独立完成させる。2026-07-28にWindows 11 /
Python 3.14.3からSSH local port forwarding経由でread-only probeの実機確認を
完了した。この完了は`VsmdSotaCommandTarget`統合またはproduction writeの完了を
意味しない。

### 現在の検証状態

* [x] Codec、buffer付きTCP Transport、byte/typed memory、確認済みmemory mapを実装
* [x] read-only probeでbanner、selector、AudioDiff、Target/Output、ServoReadPosを実機確認
* [x] probeがVSMD writeを送信せず、servo/LED状態を変更しないことを試験時に確認
* [ ] VSMDの最大read sizeを確認
* [ ] `InterpLockerClient` protocolと異常時を含むlock lifecycleを確認
* [ ] Pythonからのproduction LED writeを安全に検証
* [ ] `VsmdSotaCommandTarget`をComposition Rootへ統合

### 事前条件

* 実機を物理的に安定させる。
* Java版へ戻す手順を確認する。
* `vsmd_edison`の現在状態を記録する。
* 実機試験担当者が緊急停止方法を把握する。

### 作業

* banner、read request/response、write requestのcodecを分離する。
* fragmented/coalesced receive、timeout、EOF、最大行長を検証する。
* little-endian typed memoryとaddress/index検証を実装する。
* 人間がread-only probeで確認済みrangeだけを読む。

### 禁止

* このフェーズでサーボ目標位置を送らない。
* 自動的に`vsmd_edison`を停止しない。
* `/dev/ttyMFD1`または`/dev/i2c-1`を直接開かない。
* Codexを含む自動エージェントは、許可の有無にかかわらず実機デバイス、`systemctl`、サーボ、LEDおよびトルクを操作しない。

### 完了条件

* bannerと確認済みmemory rangeをread-onlyで取得できる。
* タイムアウト時にサーバーが復帰可能である。
* TCP socketが確実にcloseされる。
* Java版へ戻せる。

## 10. フェーズ7：Sota LED

最初に口LEDのドメイン状態遷移をFake memory、Fake timer、Fake lockで完成させる。
TCP 6495のSotaAppManager protocolについては、strict Codec、1 request /
1 connection Transport、key/IDs/timer addressを所有するlease候補をFakeだけで
実装する。productionでは安全な実機write手順と競合・異常終了時の運用が確定するまで
lock取得を`VsmdLedLockUnavailableError`で拒否し、memory writeを行わない。

### 現在の実装状態

* [x] compact ASCII JSON + LFのLOCK、CONVERT、UNLOCK Codec
* [x] `OK`、`NG`、`null`、確認済み`java.lang.Short`だけのresponse decoder
* [x] server-first header、4096-byte上限、自動retryなしのTCP Transport
* [x] unique key、immutable IDs、single-releaseの`AppManagerLedLockLease`
* [x] convert失敗時のbest-effort UNLOCKをFake transportで検証
* [x] 2026-07-29に実機6495でLED 14 lock-only取得・変換・解放を確認
* [x] `VsmdLedLock` adapter、lease-aware timer、socketなしdry-runをFakeで検証
* [x] 明示確認必須のLED 14単発live probe候補をFakeで検証
* [x] `MasterCtrlPeriod`によるcontrol ticks変換を実装しFakeで検証
* [x] TCP 6498 read-only mouth LED observerをFakeで検証
* [ ] lock競合、non-LIFO、異常終了時の安全な回復手順
* [ ] `UnavailableVsmdLedLock`からproduction candidateへの切替
* [ ] live probeによるactual LED pulse試験
* [ ] Composition Root統合とproduction実機LED write

2026-07-29の旧timer実装によるlive試験はlock、write、cleanup、restorationに成功
したが、Outputは1までで物理LEDは点灯しなかったため、actual LED pulse試験は未完了
のままである。修正したcontrol ticks変換とread-only observerはFake検証までで、
修正版の実機writeは実施していない。

### 試験順序

1. 口LEDを低輝度で点灯
2. 口LEDを消灯
3. 片目を低輝度で点灯
4. 左右の対応を確認
5. RGB各チャンネルを確認
6. 複数LEDを確認

### 作業

* 口LED global ID 14、selector 292、Target/Outputの差を固定する。
* `3200 + 14 * 2 = 3228`をコードとテストで固定する。
* 0～255の範囲を検証する。
* selectorとTargetの保存・復元、例外時releaseを検証する。
* `InterpLEDOutput[14]`へ直接writeしない。
* 追加の競合・異常系golden vectorと安全な回復手順を確定する。

### 完了条件

* lock失敗時には一切writeしない。
* 通常、例外、割込みでselectorとTargetが復元される。
* productionにlock迂回経路が存在しない。
* 人間による低輝度・短時間試験でgolden behaviorを再確認している。

## 11. フェーズ8：Sota単一軸制御

### 事前条件

* 軸IDと物理軸の対応が確認済み。
* 外部角度から内部値への変換が確認済み。
* 安全な小範囲が定義済み。
* 人間がロボットを支えられる状態である。

### 試験順序

1. 現在角度を読む
2. トルク状態を確認する
3. 1軸へごく小さい変位を送る
4. 元の位置へ戻す
5. 正負方向を確認する
6. 低速補間を確認する
7. stopを確認する
8. 通信切断時の挙動を確認する

### 完了条件

* 軸方向が文書化されている。
* 安全範囲が確定している。
* stop後に古い動作が再開しない。
* 例外時の安全動作が確認されている。

## 12. フェーズ9：Sota PoseとMotion

### 作業

* 複数軸の同時指令を実装する。
* 補間を実装する。
* Poseを確認する。
* Motionを確認する。
* Idle Motionを確認する。
* 音声と動作の同時実行を確認する。

### Java版との比較

同じPoseとMotionを別々の時間にJava版とPython版へ送る。

比較項目:

* 開始姿勢
* 終了姿勢
* 遷移時間
* 動きの滑らかさ
* 軸方向
* stop応答
* LED
* 異常時挙動

### 完了条件

* 主要な既存モーションが再生できる。
* 既存クライアントの変更を必要としない。
* 実験用途に必要な再現性が得られる。

## 13. フェーズ10：口LEDと音声連動

この機能は基本移行とは分離する。

### 作業

* WAV振幅またはRMSを解析する。
* LED更新周期を設定する。
* 平滑化を実装する。
* 音声停止時に消灯する。
* 手動LED制御との競合規則を定義する。

### 完了条件

* 音声再生を妨げない。
* LED更新がサーボ制御を妨げない。
* `stop_wav`で確実に終了する。

## 14. フェーズ11：CommU

Sotaで確立した共通層を再利用する。

### 作業

* 公式Java実装から軸変換を確認する。
* 低レベル通信を調査する。
* CommU Backendを実装する。
* 軸、LED、口、まぶたを段階的に試験する。
* Idle Motionを確認する。

### 完了条件

* Sota固有コードを共通層へ流出させず実装できる。
* 既存CommUクライアントが利用できる。
* 全公開軸とLEDが確認されている。

## 15. フェーズ12：Dog

CommUと同様に、専用バックエンドとプロファイルを実装する。

### 完了条件

* 既存Dogクライアントが利用できる。
* 読み出し対象軸が一致する。
* LEDとMotionが確認されている。

## 16. フェーズ13：並行運用

### 方針

Java版とPython版を同じ実機上で同時にハードウェア制御させない。

比較期間中は、次のいずれかで切り替える。

* 起動するサービスを明示的に選択
* 別イメージまたは別起動スクリプト
* 実験日単位で切り替え
* 物理的なロックファイル

### 収集する情報

* 起動成功率
* コマンド成功率
* 異常終了
* 通信エラー
* 音声失敗
* stop失敗
* 学生からの利用上の問題
* Java版へ戻した回数と理由

## 17. フェーズ14：正式移行

### 移行条件

* Sota、CommU、Dogの必要機能が完成している。
* 既存クライアント互換テストに合格している。
* 実機回帰テストに合格している。
* 運用マニュアルがある。
* 障害時の復旧手順がある。
* Java版の実行可能JARが保存されている。
* バージョン付きリリースが作成されている。

### 移行後

Java版は削除せず、次を付けてアーカイブする。

* 最終ソース
* 実行可能JAR
* 依存JAR
* ビルド手順
* 設定例
* 最終対応機種
* 既知の問題

## 18. ロールバック

各実機には、Python版からJava版へ戻す手順を用意する。

最低限、以下を含める。

1. Python版を停止する
2. デバイスファイルを使用するプロセスが残っていないことを確認する
3. 必要な公式サービスを再起動する
4. Java版RobotControllerを起動する
5. `read_axes`を確認する
6. 小さいPoseを確認する
7. ログを保存する

設定ファイルと起動スクリプトを上書きせず、Python版とJava版で分離する。

## 19. リスク管理表

| リスク              | 対策                      |
| ---------------- | ----------------------- |
| EdisonのPythonが古い | CPython 3.6.15互換を必須とし、CIまたは構文検査対象にする |
| 低レベル仕様が不完全       | 読み取りから段階試験し、応答を検証する     |
| サーボ破損            | 小変位、低速、1軸、物理支持で試験する     |
| 公式サービスとの競合       | 同時実行を禁止し、起動ロックを設ける      |
| 古いタスクの再開         | generationによる無効化を実装する   |
| 不正フレームによる枯渇      | 長さと接続数を事前制限する           |
| WAV競合            | 一意ファイルと個別プロセス管理を使用する    |
| 機種固有処理の混入        | BackendとProfileに隔離する    |
| 既存クライアント破壊       | v1互換テストを継続実行する          |
| Java版へ戻せない       | JAR、依存、設定、手順を保存する       |
| 学生が実機試験を誤実行      | hardwareテストを既定無効にする     |
| Codexが実機操作する     | 許可の有無にかかわらず禁止し、人間が確認して手動実行する |

## 20. マイルストーン

推奨するマイルストーンは次のとおり。

```text
M1: Documentation and environment
M2: Frame codec
M3: Mock-compatible v1 server
M4: Motion scheduler
M5: Audio manager
M6: Sota read-only backend
M7: Sota LED
M8: Sota servo and motion
M9: CommU backend
M10: Dog backend
M11: Operational release
```

各マイルストーンは、独立したレビュー可能なPull Requestへ分割する。

## 21. 完了の定義

移行は、単にPythonコードが実機を動かした時点では完了としない。

次をすべて満たした時点で完了とする。

* 正常系通信互換性がある
* 入力検証がある
* 動作排他がある
* stopが確実に機能する
* 音声プロセスを安全に管理する
* Windows上の自動テストがある
* 全対象ロボットの実機確認がある
* ログと設定が整備されている
* 学生向け手順がある
* Java版へのロールバックが可能である
