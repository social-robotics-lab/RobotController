# ビルド環境整備の検証記録（2026年11月2日・日本時間）

## 初期状態と作業範囲

- 開始時ブランチ: `main`、HEAD `94f885961d458fa5ea1e9415c17695f86a0518cb`。追跡ファイルの変更なし。未追跡の `java_server/`・`python_server/` は既存の作業として保持した。
- `git fetch origin` 後の最新main: `a0799d6e3a9f5d298d8cde25704ca0d6be76ca92`（README更新）。
- 最新mainから `codex/portable-java-build` を作成。mainへの統合はしない。
- 変更対象: `README.md`、新規 `tools/build_java.sh`、新規 `tools/test_build_java.sh`、本記録。
- `src/`、`native/`（MakefileとJNIソースを含む）、`test/`、`tools/build_phase_g.ps1`、`System.properties` は変更しない。production baselineは `bd299ae1bbc0d0514d5b60a0ca2d45125a01f1d6`。
- 自動エージェントからSotaへの接続・操作は一切実施していない。

## 実装と手順

READMEのビルド方法を再構成した。依存JARの取得・配置・SHA-256照合、Windows/macOS/EdisonでのJavaビルド、EdisonのJNI環境準備・make・静的検証、Git/TLS制約下の転送代替策を記載した。Windows例のclone後の作業ディレクトリ、依存用フォルダと出力先の位置、出力先を事前作成しない条件を修正した。

Sotaの `/home/vstone/lib` から取得するのは `core-2.2.jar`、`javase-2.2.jar`、`jna-4.1.0.jar`、`sotalib.jar`。不足する `gson-2.8.5.jar` と `json-20180813.jar` はMaven Centralから取得する。Sotaの `gson-2.6.1.jar` を改名・代用しない。4つの標準JARも含め、既存Windowsスクリプトの6ハッシュを固定して照合する。

シェル版はPOSIX構文で、Java/Javac 8、Git履歴と保護入力、クリーンな作業ツリー、依存ハッシュを検証する。出力先を新規作成し、コンパイル、Manifest・JAR生成、依存と設定のコピー、全クラスのmajor version 52・格納内容・Manifestの静的検証、ログとハッシュの記録を行う。JNIのビルド・コピー・ロードは行わない。

JNIは既存Makefileを使用する。必要条件はEdisonのYocto Linux、適合するJava 8 JDK（javac・javah・JNIヘッダ）、GCC、make、ALSA開発ヘッダ、既存 `/usr/lib/libasound.so.2`。JDK・GCC・makeは同じイメージの配布元/BSP/SDK等でCPU・libcの互換性を確認して準備する。ALSAは互換 `alsa-lib-dev` を隔離フォルダへ展開してヘッダを参照し、システムライブラリを置換しない。初回整備時点では取得URLが未確認だったが、後述の2026年11月4日の追補でALSA開発パッケージの取得元と実ビルド結果を記録した。

## PC上のオフライン検証

環境はWindows、Git for Windowsのシェル、Temurin OpenJDK/Javac 1.8.0_502。実機操作なし。受入済みPC成果物の6依存JARを読み取り参照し、新規一時フォルダのローカルcloneでビルドした。試験用cloneではビルドスクリプトだけを試験用コミットに記録し、保護対象入力の同一性とクリーン条件を維持した。

| 項目 | 結果 |
|---|---|
| `sh -n` と `dash -n` による構文確認 | 成功 |
| 不明オプション、値不足、必須引数不足、重複オプション | 想定したエラーで停止 |
| 依存JAR不足 | 停止、出力先未作成 |
| 依存JARのSHA-256不一致 | 停止、出力先未作成 |
| Java 8以外のjava / javac | それぞれ模擬コマンドで拒否を確認（実JDK 17での試験ではない） |
| 既存出力先・シンボリックリンク・リポジトリ内出力先 | 拒否、既存確認用ファイルを保持 |
| 保護入力の未追跡ファイル・baselineとの差分 | 試験用cloneのみで作成し、拒否を確認 |
| 異なる作業ディレクトリからの呼び出し、空白を含む出力パス | 成功 |
| 実際のJava 8コンパイルとJAR生成 | 23ソース、49クラス、コンパイルエラー0 |
| 全49クラスのmajor version 52、JARとコンパイラ出力の一致 | 成功 |
| Main-Class / Class-Path / コピー後6依存ハッシュ / 設定コピー | 成功 |
| 成功後に同じ出力先を再指定 | 拒否 |
| 未変更Windowsスクリプトで同じ入力をビルド | 成功、23ソース・49クラス |
| Windows版とシェル版の49クラスの一覧と全クラス内容 | 完全一致（SHA-256で比較） |
| Windows版とシェル版の展開したMain-ClassとClass-Path | 一致 |
| READMEの実行用9コードブロック | PowerShellパーサー / `dash -n` で構文確認成功（実機コマンドは実行せず） |
| README・新スクリプトと既存Windowsスクリプトの6ハッシュ | 一致 |
| 変更禁止対象とorigin/mainの差分 | なし |
| `git diff --check` | 成功 |

既存コードのコンパイラ警告47件（serial 6件、cast 41件）が両ビルドに存在する。今回の整備ではソースを修正していない。JAR全体のハッシュは記録するが、ZIP日時等による差異は許容する。

再実行する場合は、依存6JARのあるフォルダを指定して次を実行する。スクリプトは実機へ接続せず、ローカルcloneとログ・生成物を新規一時フォルダへ残す。

```sh
sh tools/test_build_java.sh /path/to/accepted-deps
```

## Edisonで操作者が実行する内容と未検証事項

[READMEのEdison手順](../README.md#edisonでjavaとjniをビルドする手順操作者用)で、依存6JAR・開発環境を確認し、新しい作業フォルダで今回のブランチを取得する。Javaをビルドしてから、未ビルドの `native/` に対して次を手動実行する（パスは実機で確認したものを使用）。

```sh
sh tools/build_java.sh \
  --dependency-dir /home/root/robotcontroller-deps \
  --output-dir /home/root/robotcontroller-build-YYYYMMDD-01/java-output
make -C native \
  JAVA_HOME=/home/vstone/java/jdk1.8.0_40 \
  ALSA_INCLUDE_DIR=/home/root/robotcontroller-alsa-headers-YYYYMMDD-01/unpack/usr/include
```

この抜粋のみで既存作業フォルダを再利用せず、READMEにある未作成パスの検査・失敗時停止・ログ保存を含む一連の手順を使う。生成物のJAR・Manifest・全Java 8クラス・依存ハッシュ、`.so` のELF32/x86等の対象ABI、JNIの7エントリポイント、ALSA参照と依存関係、make終了値を静的に確認し、ログとハッシュを報告する。

初回記録時点ではmacOSとEdisonでの実際のビルド、Edisonの開発環境の入手可能性と互換性、JNIの実コンパイル・ABI検証は未確認だった。JNIについては後述の2026年11月4日の操作者報告で成功を確認した。Java本体のEdisonビルドとmacOSビルドは引き続き未検証。実機でのJVM起動・音声・サーボ・LED・稼働JNI置換・サービス停止は今回の対象外。ビルド成功と実機動作確認を区別し、main統合は別作業とする。

## 追補：EdisonのOpenSSL対応

操作者からの今回の実機確認報告では、Edisonに `sha256sum` と `shasum` は存在せず、`openssl dgst -sha256` は正常動作した。また、Sota標準の `/home/vstone/lib` にある次の4つのJARは、すべてPhase Gの固定SHA-256と一致したとの報告を受けた。この情報は操作者による確認結果であり、自動エージェントによる実機検証ではない。

| JAR | 操作者の照合結果 |
|---|---|
| `core-2.2.jar` | Phase G固定ハッシュと一致 |
| `javase-2.2.jar` | Phase G固定ハッシュと一致 |
| `jna-4.1.0.jar` | Phase G固定ハッシュと一致 |
| `sotalib.jar` | Phase G固定ハッシュと一致 |

`build_java.sh` の計算ツール選択を `sha256sum` → `shasum` → `openssl` に拡張した。計算コマンドの終了値を解析前に確認し、出力が1行かつ取得した値が64桁の16進数の場合だけ大文字に正規化して使用する。計算失敗時は別ツールへ切り替えず停止する。最終報告用のJAR・設定ファイルのハッシュも代入時に失敗を検出し、失敗を隠してPASSを記録しない。

PC上のオフライン試験では、通常のハッシュ経路による既存試験・Java 8ビルドに加え、PATHから `sha256sum`・`shasum` を除いた環境で実OpenSSLによるJava 8ビルドが成功した（23ソース・49クラス、Manifest・全クラスmajor version 52・依存ハッシュの検証成功）。OpenSSLが正常値に見える出力と非ゼロ終了値を返す場合、空・短すぎる値・長すぎる値・非16進文字・複数行の出力を返す場合も拒否し、出力先を作成しないことを確認した。生成JARと設定ファイルの記録ハッシュは、独立したPowerShellのSHA-256計算とも一致した。両スクリプトの `dash -n`、READMEの7シェルブロックの構文確認、`git diff --check` も成功した。

READMEのEdison向け依存JAR照合・生成物ハッシュ記録例をOpenSSLで実行できるように更新した。Java/JNIソース、Makefile、既存Windowsビルドスクリプトは未変更。このOpenSSL対応時点ではEdison上でのJava/JNIビルド・ABI検証は操作者の実行結果待ちだった。自動エージェントは実機へ接続・操作せず、mainへ統合していない。

## 追補：EdisonでのJNI実ビルド成功（2026年11月4日報告）

以下は操作者から提供された実機確認結果であり、自動エージェントによる実機操作や再検証ではない。日付は報告を受けた日本時間の日付で、実際のビルド実行日時は提示されていない。

| 確認項目 | 操作者の報告結果 |
|---|---|
| 出荷時ALSA | `alsa-lib` 1.0.28-r0、`core2-32` |
| 開発パッケージ | `alsa-lib-dev_1.0.28-r0_core2-32.ipk` |
| 取得元 | `http://repo.opkg.net/edison/repo/core2-32/` |
| 取得コマンド | `opkg download alsa-lib-dev` |
| パッケージSHA-256 | `81de5dfb29144afb0edecb6bfbed80c06fa88634ebee9b49a845496c3853acce` |
| ヘッダ準備 | `ar` で `data.tar.gz` を取り出し、作業フォルダへ展開して使用 |
| JDK / GCC | Java 8 JDK 1.8.0_40 / GCC 4.9.1 |
| JNIビルド | 既存Makefileの `make -C native` で成功 |
| ELF | ELF32、little-endian、Intel 80386、Type DYN |
| ALSA依存 | `libasound.so.2` への動的リンクを確認 |
| JNI公開シンボル | エントリポイント7つを確認 |
| 生成 `.so` のSHA-256 | `1119b2666681885caa03c22c8f16118a2a849aa14b3b7158d1962500e716306b` |
| Phase G受入済みバイナリとの比較 | SHA-256が完全一致 |

READMEには新しいSotaでも準備できるよう、新規の `robotcontroller-alsa-headers-YYYYMMDD-01` 作業フォルダで取得・ハッシュ照合・展開を行い、`unpack/usr/include` を `ALSA_INCLUDE_DIR` に指定する手順を記載した。以前の開発用フォルダへの依存を取り除いた。`opkg download` は取得のみで、パッケージのインストールやシステムALSAの更新・置換は行わず、展開したヘッダだけを使用して既存 `/usr/lib/libasound.so.2` をリンクする。

**Java本体のEdisonビルドは、成功ログが提示されていないため未検証のまま。** JNI用Makefileによる `utils/AlsaPcm.java` のコンパイル成功を、RobotController全体のJavaビルド成功とは扱わない。今回の報告はJNIビルドと静的検証の成功であり、実機でのJVM起動や音声・サーボ・LEDの動作検証を新たに行った記録ではない。

今回の変更対象はREADMEと本記録のみ。Java/JNIソース、Makefile、通信プロトコル、各ビルドスクリプトは未変更。両文書のシェル例10件を `dash -n` で確認し、パス・パッケージ名・取得元・ハッシュ・検証範囲の整合性、旧ヘッダパスの不存在、`git diff --check` と変更対象の差分確認が成功した。記載した取得・展開・ビルドコマンドは自動エージェントから実行していない。mainへの統合とブランチ削除は行わない。
