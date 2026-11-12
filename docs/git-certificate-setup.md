# EdisonのGitHub証明書エラー対処

Edisonで次のエラーが確認されています。

```text
server certificate verification failed
```

報告された環境では、Edison標準のCA証明書ストアでGitHubのサーバー証明書チェーンを検証できませんでした。Windows PCで取得したCAバンドルを指定して対処します。以下は操作者向けの手順で、自動エージェントから実機への接続・設定変更は行いません。

## 1. Windows PCでCA証明書を取得する

Windows PowerShellで実行します。Git、OpenSSHのscpと、正しい時刻・HTTPS証明書検証が機能するPCが必要です。以下の保存先が既存なら別名を使い、後続のパスも読み替えてください。

```powershell
$ErrorActionPreference = "Stop"
$caFile = Join-Path $env:USERPROFILE "Downloads\cacert.pem"
if (Test-Path -LiteralPath $caFile) { throw "保存先が既存です。別名を指定してください" }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -UseBasicParsing `
  -Uri "https://curl.se/ca/cacert.pem" `
  -OutFile $caFile
Get-FileHash -LiteralPath $caFile -Algorithm SHA256
```

表示されたSHA-256を記録します。これはPCとEdison間の転送内容を照合する値です。配布元の真正性は、PC側で検証されるHTTPS接続を前提にしています。CAバンドルは更新されるため、ここに固定ハッシュは掲載しません。

## 2. Edisonへ転送する

同じWindows PowerShellから実行します。転送先 `/home/root/git-cacert.pem` が既存なら、その取得元・設定・ハッシュを確認し、必要なら別名を使ってください。既存のCA設定を無条件に上書きしません。

```powershell
$robotIp = Read-Host "SotaのIPアドレス"
scp $caFile "root@${robotIp}:/home/root/git-cacert.pem"
if ($LASTEXITCODE -ne 0) { throw "SCP失敗" }
```

## 3. Edisonでハッシュと一時指定を確認する

ここからはEdisonのsh/bashで実行します。

```sh
openssl dgst -sha256 /home/root/git-cacert.pem
```

末尾の64桁のSHA-256が、PCで記録した値と一致することを確認します（大文字・小文字は区別しません）。一致しない場合は次へ進まず、転送を確認してください。

一致したら、一時的な環境変数を使ってGitHubへの読み取り接続を試験します。

```sh
GIT_SSL_CAINFO=/home/root/git-cacert.pem \
  git ls-remote \
  https://github.com/social-robotics-lab/RobotController.git HEAD
```

終了コード0で `HEAD` のコミットIDが表示されることを確認します。失敗する場合は、実機の時刻、証明書ファイル、ネットワーク、Git/TLSの対応状況を確認します。CAストア以外の障害をこの手順で解消できるとは限りません。

## 4. 成功後にGitへ設定する

まず既存設定を確認します。未設定なら値が表示されないことがあります。

```sh
git config --global --get http.sslCAInfo
```

既存設定がある場合は値を控え、他のGit接続への影響を確認してから変更します。この設定は実行ユーザーのGit全体に適用されます。

```sh
git config --global \
  http.sslCAInfo /home/root/git-cacert.pem
```

最後に `GIT_SSL_CAINFO` の一時指定をせず、通常のコマンドで再確認します。シェル起動設定などに同変数を常設している場合は、Git設定を隠さないようその設定も確認してください。

```sh
git ls-remote \
  https://github.com/social-robotics-lab/RobotController.git HEAD
```

## curlでも同じCAを使用する

Gitの `http.sslCAInfo` 設定はcurlコマンドには適用されません。JAR取得時はREADMEにある `curl --cacert /home/root/git-cacert.pem` を使用します。

証明書検証を無効にする `--no-check-certificate`、`curl -k`、`http.sslVerify false` は使用しません。古いTLS環境で接続できない場合は、[PCから転送する手順](../README.md#edison上でjavaの実行ファイルとjniライブラリをビルドする方法)を使用します。

設定の根拠は [curl公式のCA証明書資料](https://curl.se/docs/sslcerts.html) と [Git公式のhttp.sslCAInfo設定](https://git-scm.com/docs/git-config#Documentation/git-config.txt-httpsslCAInfo)です。この文書のコマンドを今回のPC検証から実機で実行したものではありません。
