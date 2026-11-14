# Protocol（v1 要約）

このページはプロトコル v1 の要約です。**正本は
[`spec/protocol-v1.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/spec/protocol-v1.md)**
であり、数値・バイト配置は正本の表が優先です。

## 全体像

```
Sender (peripheral)                     Receiver (central)
iPhone / Android                        iPad
  |  advertise(Service UUID, name)          |
  |                                        |  scan(filter: Service UUID)
  |<--------------- connect ---------------|
  |<-------- read Status, write START -----|
  |---------- notify Status --------------->|
  |---------- notify Location (20B) ------->|  1 Hz
  |---------- notify Extended (8B) -------->|  1 Hz（有効時）
  |                                        |  → 位置シミュレーションへ反映
  |<-------- write STOP -------------------|
  |<--------------- disconnect ------------|
```

## UUID（§1）

| 役割 | UUID |
| :--- | :--- |
| P2P GPS Service | `B1E5A000-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Location Packet characteristic | `B1E5A001-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Control characteristic | `B1E5A002-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Status characteristic | `B1E5A003-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Extended Location characteristic | `B1E5A004-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Device Information Service | `0000180A-0000-1000-8000-00805F9B34FB` |

アドバタイズ名: `P2PGPS-<PLATFORM>-<XXXX>`（例 `P2PGPS-ANDROID-A1B2`）。
受信側は Service UUID でスキャンし、`P2PGPS-` で始まる名前のみ表示します。

## GATT プロファイル（§1.1）

| Characteristic | Properties | 方向 | 長さ |
| :--- | :--- | :--- | :--- |
| Location Packet | `read`, `notify` | 送信側 → 受信側 | 固定 20 bytes |
| Control | `write`, `write-without-response` | 受信側 → 送信側 | 1〜3 bytes |
| Status | `read`, `notify` | 送信側 → 受信側 | 固定 8 bytes |
| Extended Location | `read`, `notify` | 送信側 → 受信側 | 固定 8 bytes |

## Location Packet（20 bytes、§3）

```
 0        1        2        3        4        8       12       14  15  16       20
 +--------+--------+--------+--------+--------+--------+--------+---+---+--------+
 |version | flags  | sequence(uint16)| latitude (int32) | longitude (int32)   |
 +--------+--------+--------+--------+--------+--------+--------+---+---+--------+
 | altitude(int16) |accuracy| speed  | timestamp (uint32)                      |
 +--------+--------+--------+--------+--------+--------+--------+---+---+--------+
```

| Offset | Size | Field | 型 | 説明 |
| ---: | ---: | :--- | :--- | :--- |
| 0 | 1 | `version` | uint8 | v1 = `0x01` |
| 1 | 1 | `flags` | uint8 | 下記 |
| 2 | 2 | `sequence` | uint16 LE | +1、65535 で 0 |
| 4 | 4 | `latitude` | int32 LE | 緯度 × 10^7（35.6812360 → 356812360） |
| 8 | 4 | `longitude` | int32 LE | 経度 × 10^7 |
| 12 | 2 | `altitude_m` | int16 LE | 標高 m（負可）。無効時 0 |
| 14 | 1 | `accuracy_m` | uint8 | 255 = 不明 |
| 15 | 1 | `speed_mps` | uint8 | 255 = 不明 |
| 16 | 4 | `timestamp` | uint32 LE | Unix 秒（UTC）。2106 年まで |

### flags（§3.1）

| bit | 名称 | 意味 |
| ---: | :--- | :--- |
| 0 | `VALID_FIX` | 有効な位置 |
| 1 | `ALTITUDE_VALID` | `altitude_m` 有効 |
| 2 | `SPEED_VALID` | `speed_mps` 有効 |
| 3 | `SIMULATED` | シミュレート / モック位置 |
| 4 | `CHARGING` | 充電中 |
| 5 | `LOW_BATTERY` | 残量 20% 未満 |
| 6 | `MOVING` | 移動中 |
| 7 | reserved | 0 固定（1 なら破棄） |

### 東京駅の例（§3.2）

```
lat = 35.6812360° → 356812360 = 0x15448648 → 48 86 44 15
lon = 139.7671250° → 1397671250 = 0x534EC552 → 52 C5 4E 53
alt = 3 m → 03 00 / acc = 5 → 05 / spd = 0 → 00
ts  = 1763136000 → 00 52 17 69
packet = 01 03 2A 00 48 86 44 15 52 C5 4E 53 03 00 05 00 00 52 17 69
```

## Extended Location Packet（8 bytes、任意、§4）

| Offset | Size | Field | 説明 |
| ---: | ---: | :--- | :--- |
| 0 | 1 | `version` | `0x01` |
| 1 | 1 | `provider` | 0=unknown, 1=GPS, 2=Network, 3=Fused, 4=Manual/Simulated |
| 2 | 1 | `battery_pct` | 0–100、255 = 不明 |
| 3 | 1 | `satellites` | 255 = 不明 |
| 4 | 2 | `course` | 進行方向 × 100（0–35999）、65535 = 不明 |
| 6 | 1 | `vertical_accuracy_m` | 255 = 不明 |
| 7 | 1 | reserved | 0 |

## Control（受信側 → 送信側、1〜3 bytes、§5）

| opcode | 名称 | payload |
| ---: | :--- | :--- |
| `0x01` | `START` | uint16 LE `interval_ms`（0 = 既定 1000） |
| `0x02` | `STOP` | なし |
| `0x03` | `SET_INTERVAL` | uint16 LE `interval_ms` |
| `0x04` | `REQUEST_FIX` | なし |
| `0x05` | `SET_EXTENDED` | uint8 `enabled` (0/1) |
| `0x7F` | `RESET` | なし |

- `interval_ms` は受信側が**生値**を書き、送信側が仕様 §5.1 で正規化して適用します。
  - `0` → `1000`（既定値）
  - `1`–`99` → `100`（下限にクランプ）
  - `100`–`60000` → そのまま
  - `60001`–`65535` → `60000`（上限にクランプ）
  - Status の `interval_ms` は正規化後の値。
- 未知 opcode → 無視して `last_error = 1`。長さ不正 → 無視して `last_error = 2`。
- 接続直後に Status を read し、`START` を書く（再接続も冪等）。

## Status（8 bytes、§6）

| Offset | Size | Field | 説明 |
| ---: | ---: | :--- | :--- |
| 0 | 1 | `version` | `0x01` |
| 1 | 1 | `state` | 0=Idle, 1=Streaming, 2=Paused, 3=Error |
| 2 | 2 | `interval_ms` | uint16 LE |
| 4 | 1 | `battery_pct` | 255 = 不明 |
| 5 | 1 | `status_flags` | bit0 extended, bit1 fix, bit2 charging, bit3 low battery |
| 6 | 1 | `last_error` | 0=none, 1=unknown opcode, 2=bad length, 3=location unavailable, 4=internal |
| 7 | 1 | reserved | 0 |

状態変化時と 10 秒ごとのハートビートで notify します。

## 受信側の検証（§3.3）

以下をすべて満たさないパケットは破棄します。

1. 長さがちょうど 20 bytes
2. `version == 0x01`
3. `flags & 0x80 == 0`
4. `-900_000_000 <= latitude <= 900_000_000` かつ
   `-1_800_000_000 <= longitude <= 1_800_000_000`（度 × 10^7）
5. `VALID_FIX == 1` のとき `(0,0)` 近傍（±0.0001°）は無効扱い（Null Island）
6. `sequence` の巻き戻りはログのみ（パケットは受理）
7. `timestamp` が ±24 時間を超えたら stale 警告（注入はユーザー設定）

補足: `VALID_FIX == 0`（未測位）のパケットは §3.3 上は受理されますが、受信側の
フィルタでは `accepted=False` / `reason="no_fix"` として**注入しません**。
外れ値判定の基準点も更新しません。

## セキュリティ / プライバシー（§8）

- v1 は認証・暗号化なし（Just Works 相当）。近距離の第三者が偽の位置を送れます。
- 受信側の必須要件:
  - 自動接続はユーザーが明示的に許可した送信側のみ
  - 位置注入は既定 OFF
  - 注入中は画面上部に常時バナー（送信元名・最終受信時刻・座標）
- 位置情報はクラウドに送らない（P2P のみ）。
- ログの座標はユーザー設定で丸める（既定: 小数 5 桁）。
- v2 で HMAC / ペアリングコードを追加する余地（Control `AUTH` = `0x10` 予約）。

## バージョニング（§9）

- 未知バージョンは破棄し `last_error = 4`。
- 後方互換の追加は予約ビット・予約 opcode・Extended の reserved を使う。
- 破壊的変更は v2 として UUID を変えず `version = 0x02`。受信側は両対応。
