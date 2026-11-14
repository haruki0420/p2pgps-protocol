# P2P GPS BLE プロトコル仕様 v1

> **ステータス: 正本（Canonical） / v1.0 / 凍結 2026-11-15**
>
> この文書は P2P GPS の BLE プロトコル **v1 の正本**である。実装（`p2pgps-ios` /
> `p2pgps-android` / `p2pgps-protocol`）とテストベクタはこの文書に従う。変更する場合は
> 3 リポジトリを同時に更新し、本ファイルの変更履歴に記録する。
>
> - 正本ファイル: `p2pgps-protocol/spec/protocol-v1.md`（本ファイル）
> - リファレンス実装: `p2pgps-protocol/p2pgps/`（Python、標準ライブラリのみ）
> - 共有テストベクタ: `p2pgps-protocol/tests/vectors/*.json`
> - ライセンス: MIT（仕様文書とリファレンス実装）

iPhone / Android が取得した GPS 位置情報を、Bluetooth Low Energy (BLE) の GATT を介して iPad に転送し、iPad 側で「その位置にいる」ように位置情報を反映（シミュレート）するための P2P プロトコル。

- **セントラル（受信側）**: iPad。`p2pgps-ios` の Receiver モード。
- **ペリフェラル（送信側）**: iPhone（`p2pgps-ios` Sender モード）または Android（`p2pgps-android`）。
- 通信は 1 対 1。iPad は同時に 1 台の送信側と接続する（v1）。
- ボンディング / ペアリングは行わない（Just Works 相当）。セキュリティ上の注意は §8。

---

## 0. この文書について

### 0.1 変更履歴

| 版 | 日付 | 変更内容 |
| :--- | :--- | :--- |
| 1.0 | 2026-11-15 | 初版（v1 としてフリーズ）。§3.2 の例示 hex（lat / lon / timestamp）をフィールド定義に合わせて修正。§3.3-4 の検証レンジをスケール（度 × 10^7）に合わせて修正（±900_000_000 / ±1_800_000_000） |

### 0.2 用語集

| 用語 | 説明 |
| :--- | :--- |
| セントラル (Central) | BLE の接続を開始する側。本プロジェクトでは iPad（Receiver）。 |
| ペリフェラル (Peripheral) | アドバタイズして接続を待つ側。iPhone / Android（Sender）。 |
| Sender | 位置情報を送信するアプリ。iPhone（`p2pgps-ios`）または Android（`p2pgps-android`）。 |
| Receiver | 位置情報を受信し、iPad 自身の位置として注入するアプリ（`p2pgps-ios`）。 |
| GATT | BLE のサービス / キャラクタリスティック構造。 |
| Characteristic | GATT の値。本仕様では Location / Control / Status / Extended の 4 つ。 |
| notify | ペリフェラルからセントラルへのプッシュ通知。 |
| write / write-without-response | セントラルからペリフェラルへの書き込み。 |
| CCCD | Client Characteristic Configuration Descriptor（`0x2902`）。notify 購読の有効化に使う。 |
| ATT MTU | 属性プロトコルの最大転送単位。BLE 4.0 既定は 23 bytes（ペイロード 20 bytes）。 |
| fix | 測位結果。`VALID_FIX = 1` のとき有効な位置を表す。 |
| Null Island | 緯度経度 `(0, 0)`。測位失敗時の代表値のため、有効 fix としては扱わない。 |
| stale | `timestamp` が現在時刻から ±24 時間を超えた古いデータ。表示時に警告する。 |
| E7（度 × 10^7） | 緯度経度の整数表現。1 unit = 10^-7 度 ≒ 1.1 cm。 |
| sequence | 送信ごとに +1 する uint16。欠番・重複・巻き戻りの検出に使う。 |
| opcode | Control コマンドの先頭 1 byte。 |
| 注入 (injection) | 受信した座標を iPad の位置シミュレーションへ反映すること。 |
| Just Works | パスキー入力を伴わない BLE のペアリング方式。v1 はこれに相当する。 |
| DDI | Developer Disk Image。iPad の位置シミュレーションに必要。 |
| LocalDevVPN | 端末自身の RSD へ接続するためのループバック VPN。 |

### 0.3 規範キーワード

- 「〜しなければならない（MUST）」「〜してはならない」は必須要件。
- 「〜すべき（SHOULD）」「〜を推奨する」は、正当な理由がある場合のみ省略できる。
- 「〜してもよい（MAY）」は任意。
- 表・数値・バイト配置・opcode・flags は**規範**。コード例・図・文章中の例示は
  **非規範**（理解の補助）であり、数値の根拠は本文の表を優先する。

### 0.4 関連リポジトリ

| リポジトリ | 役割 | 言語 / ライセンス |
| :--- | :--- | :--- |
| [`p2pgps-protocol`](https://github.com/haruki0420/p2pgps-protocol) | 本仕様の正本・Python リファレンス実装・テストベクタ | Python / MIT |
| [`p2pgps-ios`](https://github.com/haruki0420/p2pgps-ios) | iPhone = Sender / iPad = Receiver | Swift / AGPL-3.0 |
| [`p2pgps-android`](https://github.com/haruki0420/p2pgps-android) | Android Sender | Kotlin / MIT |

---

## 1. 識別子（UUID）

すべて 128-bit UUID。バイトオーダーは BLE 標準（リトルエンディアン）で送信される。

| 役割 | UUID |
| :--- | :--- |
| P2P GPS Service | `B1E5A000-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Location Packet characteristic | `B1E5A001-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Control characteristic | `B1E5A002-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Status characteristic | `B1E5A003-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Extended Location characteristic | `B1E5A004-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Device Information Service (標準) | `0000180A-0000-1000-8000-00805F9B34FB` |

Device Information Service の任意項目:

| 項目 | UUID | 値の例 |
| :--- | :--- | :--- |
| Manufacturer Name | `00002A29-0000-1000-8000-00805F9B34FB` | `P2PGPS` |
| Model Number | `00002A24-0000-1000-8000-00805F9B34FB` | `iPhone` / `Android` |
| Firmware Revision | `00002A26-0000-1000-8000-00805F9B34FB` | `1.0.0` |

### 1.1 GATT プロファイル

| Characteristic | Properties | 方向 | 長さ |
| :--- | :--- | :--- | :--- |
| Location Packet | `read`, `notify` | 送信側 → 受信側 | 固定 20 bytes |
| Control | `write`, `write-without-response` | 受信側 → 送信側 | 1〜3 bytes |
| Status | `read`, `notify` | 送信側 → 受信側 | 固定 8 bytes |
| Extended Location | `read`, `notify` | 送信側 → 受信側 | 固定 8 bytes |

- Location Packet / Status / Extended は `read` で「最後に送った値」を返す。未送信時はゼロ埋めではなく「無効」を表す値（flags=0 / state=0）を返す。
- CCCD (`0x2902`) を notify 対象に持つ。
- 20 bytes 固定にすることで、ATT MTU 23（BLE 4.0 既定、ペイロード 20 bytes）でもフラグメンテーション不要。MTU 交渉は必須ではない。

### 1.2 アドバタイズ

- 送信側は Service UUID `B1E5A000-...` を Advertise に含める。
- ローカルネーム: `P2PGPS-<PLATFORM>-<XXXX>`（例 `P2PGPS-ANDROID-A1B2`, `P2PGPS-IOS-7F3C`）。`<XXXX>` はランダムな 4 hex。
- Connectable であること。Scan Response にローカルネームを載せてもよい。
- 受信側は Service UUID でスキャンフィルタし、`P2PGPS-` で始まる名前のみ表示する。

---

## 2. バイトオーダー

- すべて **リトルエンディアン**。
- 符号付き整数は 2 の補数。
- 浮動小数点は使わない（決定論的・省サイズのため）。

---

## 3. Location Packet（20 bytes）

| Offset | Size | Field | 型 | 説明 |
| ---: | ---: | :--- | :--- | :--- |
| 0 | 1 | `version` | uint8 | プロトコルバージョン。v1 = `0x01` |
| 1 | 1 | `flags` | uint8 | §3.1 |
| 2 | 2 | `sequence` | uint16 LE | 送信ごとに +1、65535 で 0 に戻る |
| 4 | 4 | `latitude` | int32 LE | 緯度 × 10^7（例 35.6812360 → `356812360`） |
| 8 | 4 | `longitude` | int32 LE | 経度 × 10^7（例 139.7671250 → `1397671250`） |
| 12 | 2 | `altitude_m` | int16 LE | 標高（m、整数、切り捨て）。無効時は 0 |
| 14 | 1 | `accuracy_m` | uint8 | 水平精度（m）。`255` = 不明 / 255 m 以上 |
| 15 | 1 | `speed_mps` | uint8 | 速度（m/s）。`255` = 不明 / 255 m/s 以上 |
| 16 | 4 | `timestamp` | uint32 LE | Unix エポック秒（UTC）。2106 年まで有効 |

### 3.1 flags

| bit | 名称 | 意味 |
| ---: | :--- | :--- |
| 0 | `VALID_FIX` | 1 = 有効な位置。0 = まだ測位できていない（lat/lon は 0） |
| 1 | `ALTITUDE_VALID` | 1 = `altitude_m` 有効 |
| 2 | `SPEED_VALID` | 1 = `speed_mps` 有効 |
| 3 | `SIMULATED` | 1 = 送信側がシミュレート/モック位置を送っている |
| 4 | `CHARGING` | 1 = 充電中 |
| 5 | `LOW_BATTERY` | 1 = バッテリー残量 20% 未満 |
| 6 | `MOVING` | 1 = 移動中（速度 0.5 m/s 以上など送信側の判定） |
| 7 | reserved | 0 固定（受信側は無視する） |

### 3.2 エンコード例（東京駅）

```
lat = 35.6812360 deg → int32 356812360  = 0x15448648 → 48 86 44 15
lon = 139.7671250 deg → int32 1397671250 = 0x534EC552 → 52 C5 4E 53
alt = 3 m             → int16 3          → 03 00
acc = 5 m             → 05
spd = 0               → 00
ts  = 1763136000      → 00 52 17 69
packet = 01 03 2A 00 48 86 44 15 52 C5 4E 53 03 00 05 00 00 52 17 69
         ^v ^f ^seq  ^---- lat ----^ ^---- lon ----^ ^alt ^a ^s ^--- ts ---^
```

（`flags = 0x03` = VALID_FIX | ALTITUDE_VALID）

### 3.3 受信側の検証

受信側は以下をすべて満たさないパケットを破棄する。

1. 長さがちょうど 20 bytes。
2. `version == 0x01`。
3. `flags & 0x80 == 0`。
4. `-900_000_000 <= latitude <= 900_000_000` かつ `-1_800_000_000 <= longitude <= 1_800_000_000`（度 × 10^7。±90° / ±180°）。
5. `VALID_FIX == 1` のとき、上記に加えて `(0,0)` 近傍（±0.0001°）を「無効」として扱う（Null Island 対策）。
6. 連続受信の `sequence` が巻き戻った場合はログに記録するが、パケット自体は受理する（再送・並び替え耐性）。
7. `timestamp` が現在時刻から ±24 時間を超える場合は「stale」として表示に警告を出す（注入はユーザー設定に従う）。

---

## 4. Extended Location Packet（8 bytes、任意）

送信側が対応している場合のみ notify する。受信側は無くても動作する。

| Offset | Size | Field | 型 | 説明 |
| ---: | ---: | :--- | :--- | :--- |
| 0 | 1 | `version` | uint8 | `0x01` |
| 1 | 1 | `provider` | uint8 | 0=unknown, 1=GPS, 2=Network, 3=Fused, 4=Manual/Simulated |
| 2 | 1 | `battery_pct` | uint8 | 0–100、`255` = 不明 |
| 3 | 1 | `satellites` | uint8 | 衛星数、`255` = 不明 |
| 4 | 2 | `course` | uint16 LE | 進行方向 × 100（0–35999 = 0.00°–359.99°）、`65535` = 不明 |
| 6 | 1 | `vertical_accuracy_m` | uint8 | 垂直精度（m）、`255` = 不明 |
| 7 | 1 | reserved | uint8 | 0 |

---

## 5. Control characteristic（受信側 → 送信側）

書き込み専用。1 コマンド = 1 書き込み。応答は Status notify で返す（`write-without-response` でも可）。

| opcode | 名称 | payload | 意味 |
| ---: | :--- | :--- | :--- |
| `0x01` | `START` | uint16 LE `interval_ms`（0 = 既定値 1000） | ストリーミング開始。`100 <= interval_ms <= 60000`。範囲外は既定値にクランプ |
| `0x02` | `STOP` | なし | ストリーミング停止（アドバタイズは継続） |
| `0x03` | `SET_INTERVAL` | uint16 LE `interval_ms` | 送信間隔の変更（ストリーミング中でも可） |
| `0x04` | `REQUEST_FIX` | なし | 次回 notify を即時送信（1 回） |
| `0x05` | `SET_EXTENDED` | uint8 `enabled` (0/1) | Extended Location の notify 有効化 |
| `0x7F` | `RESET` | なし | 既定設定に戻す（interval=1000, extended=off, sequence=0） |

- 未知の opcode は無視し、Status の `last_error = 1 (UNKNOWN_OPCODE)` を設定する。
- 不正長は無視し、`last_error = 2 (BAD_LENGTH)`。
- 受信側は接続直後に Status を read し、`START` を書く。再接続時も同様（冪等）。

---

## 6. Status characteristic（8 bytes）

| Offset | Size | Field | 型 | 説明 |
| ---: | ---: | :--- | :--- | :--- |
| 0 | 1 | `version` | uint8 | `0x01` |
| 1 | 1 | `state` | uint8 | 0=Idle, 1=Streaming, 2=Paused, 3=Error |
| 2 | 2 | `interval_ms` | uint16 LE | 現在の送信間隔 |
| 4 | 1 | `battery_pct` | uint8 | 255 = 不明 |
| 5 | 1 | `status_flags` | uint8 | bit0 = extended enabled, bit1 = fix available, bit2 = charging, bit3 = low battery |
| 6 | 1 | `last_error` | uint8 | 0=none, 1=unknown opcode, 2=bad length, 3=location unavailable, 4=internal |
| 7 | 1 | reserved | uint8 | 0 |

- 状態変化時（START/STOP/エラー/測位状態変化）に notify する。加えて 10 秒ごとのハートビート notify を行う。

---

## 7. シーケンス

```
Sender (peripheral)                     Receiver (central)
  |  advertise(Service UUID, name)          |
  |                                        |  scan(filter: Service UUID)
  |<--------------- connect ---------------|
  |<---------- discover services ----------|
  |<----- discover characteristics --------|
  |<-------- read Status (8B) -------------|
  |<-------- write START(1000) ------------|
  |---------- notify Status --------------->|
  |---------- notify Location (20B) ------->|  1 Hz
  |---------- notify Extended (8B) -------->|  1 Hz（有効時）
  |                                        |  → iPad の位置シミュレーションへ反映
  |<-------- write STOP -------------------|
  |---------- notify Status --------------->|
  |<--------------- disconnect ------------|
```

- 受信側は切断を検知したら 1 秒後から再スキャンし、同じ送信側（名前 + 保存済み ID）へ自動再接続する（ユーザー設定で ON/OFF）。
- 送信側は購読者がいなくなったら `state=Idle` に戻し、アドバタイズを継続する。

---

## 8. セキュリティ / プライバシー

- v1 は認証・暗号化を行わない（BLE の Just Works 相当）。**近距離にいる第三者が偽の位置を送れる**ため、受信側は以下を必須とする。
  - 自動接続はユーザーが明示的に許可した送信側（名前 + 識別子を保存）のみ。
  - 「位置情報の注入」は既定 OFF。ユーザーが画面で ON にしたときだけ注入する。
  - 注入中は画面上部に常時バナー（送信元名・最終受信時刻・座標）を表示する。
- 位置情報は端末外（クラウド）に送らない。P2P のみ。
- ログに座標を残す場合はユーザー設定で丸める（既定: 小数 5 桁 = 約 1 m）。
- 将来 v2 でアプリ層の HMAC / ペアリングコードを追加する余地を残す（Control に `AUTH` opcode を予約: `0x10`）。

---

## 9. バージョニング

- `version` フィールドで互換性を判定する。受信側は未知バージョンを破棄し、Status の `last_error = 4` を立てる。
- 後方互換の追加は「予約ビット」「予約 opcode」「Extended の reserved」を使う。
- 破壊的変更は v2 として UUID を変更せずに `version=0x02` で表現し、受信側は両対応する。

---

## 10. テストベクタ

`p2pgps-protocol/tests/vectors/*.json` に以下を含む。

- 東京駅（有効 fix、altitude/speed 有効）
- 南極（負の緯度・経度、altitude 負）
- Null Island（無効扱い）
- 範囲外緯度（破棄）
- 未知バージョン（破棄）
- sequence 巻き戻り
- バッテリー・プロバイダ・コースの Extended パケット
- Control 各 opcode のエンコード/デコード

各ベクタの形式（`wire` / `hex` / `expect`）と使い方は
[`tests/vectors/README.md`](../tests/vectors/README.md) を参照。
