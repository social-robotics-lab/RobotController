# Sota axis physical correlation evidence (2026-08-03)

## 1. Status

```text
Status: Completed
Phase: 8b2c
Acceptance type: Read-only physical axis/index/sign correlation
Target platform: Intel Edison / Yocto / CPython 3.6.15
Target revision: 96e28f4976993e8d5260bc1cad48938128546843
Execution date: 2026-08-03
VSMD endpoint: 127.0.0.1:6498
VSMD process PID observed throughout: 340
```

本証跡は、`ServoReadPos[32]`のうちraw index 1～8とSotaの8つの公開軸との
対応、および各軸の符号方向を、static mapping根拠とoperator-controlled read-only
実機観測を組み合わせて確認した記録である。

**Live servo write、torque change、automatic pose initialization、device file access、
service操作、process signal、process lock取得は実施していない。**

## 2. Static mapping basis

確認したmapping根拠は次のとおりである。

* active `memdef.conf`のSota servo settingsはID 1～8の順序で構成される。
* Java `AxisReader.read()`は`RobotSys.motion.getReadpos()`の戻り値をdefault ID順に扱う。
* `CRobotMotion.getReadpos()`は32個の`ServoReadPos`を読み、active IDで選択する。
* reviewed Java conversionはIDごとの既存gear ratioを使い、負値を含めJava互換の
  truncation toward zeroを行う。
* Pythonのdegree observerは軸ID 1～8をraw index 1～8へ明示的にmappingする。

static analysisだけではphysical joint correlationを確定せず、以下の実機観測を
追加条件とした。

## 3. Confirmed physical correlation

| Axis | Raw index | Operator movement | Observed raw direction | Main evidence |
| --- | ---: | --- | --- | ---: |
| `BODY_Y` | 1 | 胴体をSotaから見て左へ回す | positive | delta `+423.500`, margin `418.600` |
| `L_SHOU` | 2 | 左上腕を肩から上げる | positive | delta `+602.150`, margin `595.150` |
| `L_ELBO` | 3 | 左肘を曲げる | negative | delta `-317.750`, margin `307.500` |
| `R_SHOU` | 4 | 右上腕を肩から上げる | negative | delta `-591.100`, margin `587.050` |
| `R_ELBO` | 5 | 右肘を曲げる | positive | delta `+585.100`, margin `574.800` |
| `HEAD_Y` | 6 | 頭をSotaから見て左へ回す | positive | range `1213`, margin `1181` |
| `HEAD_P` | 7 | 顔を下へ向ける | positive | delta `+145.500`, margin `137.750` |
| `HEAD_R` | 8 | 左耳を左肩へ近づける | positive | delta `+312.200`, margin `310.750` |

したがって、read pathで使用するmappingは次のとおり確認済みとする。

```text
BODY_Y -> raw_01
L_SHOU -> raw_02
L_ELBO -> raw_03
R_SHOU -> raw_04
R_ELBO -> raw_05
HEAD_Y -> raw_06
HEAD_P -> raw_07
HEAD_R -> raw_08
```

## 4. Runtime safety observations

各operator-controlled testでは、snapshot取得の前後または各sampleの前後で次を
確認した。

* `ServoEN == 0`
* `ServoSendEN == 1`
* VSMD memory write count `0`
* automatic retryなし
* VSMD PID set不変
* bytecode artifact count不変
* repository HEAD、status、保護ファイルSHA-256不変

ここで`ServoEN == 0`は観測時点のVSMD memory stateであり、あらゆる機械的抵抗や
将来の状態を説明する一般的保証ではない。

関節の手動移動はoperatorの明示的判断により実施した。vendor manualが関節を無理に
動かさないよう求めているため、本結果はmanual backdriveをvendor-approved procedure
として認定せず、将来の手動操作の安全性も保証しない。

## 5. Confirmed conclusions

* 8軸すべてについて公開軸名とraw index 1～8の対応を確認した。
* 8軸すべてについて上表の物理方向に対するraw値の符号を確認した。
* mappingはstatic Java/memdef根拠とphysical correlationの両方を満たした。
* degree observerのID 1～8 → raw index 1～8というmappingは実機correlationと一致した。

## 6. Not confirmed

次の事項は本証跡から確認済みへ昇格しない。

* 各軸の絶対的なphysical degree accuracy
* 各軸の機械原点、zero offset、個体差
* 軸定義のminimum／maximum degreeが実機安全可動域であること
* gear ratioが全可動域で物理角度と一致すること
* `ServoReadPos`がactual、target、encoderのどの意味であるか
* 32値が同一control tickのatomic snapshotであること
* servo target write addressおよびwrite protocol
* interpolation、停止、cancel、rollback、safe return
* single-axis live writeの安全性

## 7. Phase consequence

Phase 8の「軸IDと物理軸の対応が確認済み」という前提条件は満たした。
ただし、外部degreeとphysical angleの実機精度、安全な小範囲、write path、停止・復帰
条件が未確認であるため、**この結果だけでsingle-axis live writeへ進んではならない。**
