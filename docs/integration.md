# 他リポジトリとの統合（`p2pgps-protocol` ⇄ iOS / Android）

このドキュメントは `p2pgps-ios`（Swift）と `p2pgps-android`（Kotlin）の実装者が、
このリポジトリの正本仕様・テストベクタに合わせるための実務的なガイドである。

## 1. 3 実装の関係

| 実装 | 場所 | 役割 | 検証 |
| :--- | :--- | :--- | :--- |
| Python（正本） | `p2pgps-protocol/p2pgps/` | 仕様のリファレンス実装。ベクタ検証・CLI・受信側シミュレータ | `pytest`（CI: Ubuntu / Windows） |
| Swift | `p2pgps-ios/Sources/P2PGPSProtocol/` | iPhone Sender の encode、iPad Receiver の decode / validate | XCTest + 共有ベクタ JSON |
| Kotlin | `p2pgps-android/protocol/` | Android Sender の encode、Status / Control の処理 | JUnit + 共有ベクタ JSON |

**正本は `spec/protocol-v1.md`**。実装間で解釈が割れた場合は仕様書の表を優先し、
必要なら 3 リポジトリ同時に修正する。

## 2. 定数対応表

| 定数 | 値 | Swift | Kotlin |
| :--- | :--- | :--- | :--- |
| Protocol version | `0x01` | `protocolVersion: UInt8 = 1` | `const val PROTOCOL_VERSION = 0x01` |
| Service UUID | `B1E5A000-9C3D-4E7A-8F20-1A2B3C4D5E6F` | `CBUUID(string:)` | `UUID.fromString(...)` |
| Location UUID | `B1E5A001-...` | 同上 | 同上 |
| Control UUID | `B1E5A002-...` | 同上 | 同上 |
| Status UUID | `B1E5A003-...` | 同上 | 同上 |
| Extended UUID | `B1E5A004-...` | 同上 | 同上 |
| Location 長 | 20 bytes | `[UInt8](repeating: 0, count: 20)` | `ByteArray(20)` |
| Extended 長 | 8 bytes | 8 | 8 |
| Status 長 | 8 bytes | 8 | 8 |
| 緯度経度スケール | `10_000_000` | `Int32` | `Int` |
| 既定 interval | `1000` ms | `UInt16` | `Int` |
| interval 範囲 | `100...60000` | クランプ | クランプ |

UUID は **文字列表現（正規形）で定義**し、BLE スタックに渡すときに各 OS が
ワイヤ表現（リトルエンディアン）へ変換する。自前でバイト列化する場合は
「128-bit UUID は最下位オクテットから送信される」ことに注意
（Python の `uuid_to_le_bytes()` は正規形 16 bytes の逆順を返す）。

## 3. Location Packet のフィールド対応

| 仕様のフィールド | 型 | 範囲 | Swift | Kotlin |
| :--- | :--- | :--- | :--- | :--- |
| `version` | uint8 | `0x01` | `UInt8` | `Int`（0..255） |
| `flags` | uint8 | §3.1 | `OptionSet` | `Int` ビットフラグ |
| `sequence` | uint16 LE | 0..65535 | `UInt16` | `Int` |
| `latitude` | int32 LE | ±900,000,000 | `Int32` | `Int` |
| `longitude` | int32 LE | ±1,800,000,000 | `Int32` | `Int` |
| `altitude_m` | int16 LE | -32768..32767 | `Int16` | `Short` / `Int` |
| `accuracy_m` | uint8 | 0..255（255=不明） | `UInt8` | `Int` |
| `speed_mps` | uint8 | 0..255（255=不明） | `UInt8` | `Int` |
| `timestamp` | uint32 LE | 0..4294967295 | `UInt32` | `Long`（unsigned 扱い） |

- 緯度経度は **度 × 10^7 の整数**。`35.6812360` → `356812360`。
  丸めは「0.5 を 0 から遠ざかる方向」（Python は `Decimal` + `ROUND_HALF_UP`）。
- `altitude_m` は **符号付き int16**。負の標高（南極など）を忘れない。
- `timestamp` は **符号なし uint32**。2106 年まで有効。Kotlin では `Long` で
  保持して `and 0xFFFFFFFFL` するのが安全。

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
| 7 | reserved | 0 固定（受信側は 1 なら破棄） |

## 4. 実装手順（受信側の検証順序）

仕様 §3.3 の順序で検証する。**パースと検証を分離**すると診断しやすい。

1. 長さがちょうど 20 bytes（でなければ破棄）
2. `version == 0x01`（未知バージョンは破棄し、`Status.last_error = 4`）
3. `flags & 0x80 == 0`
4. `-900_000_000 <= latitude <= 900_000_000`
   かつ `-1_800_000_000 <= longitude <= 1_800_000_000`
5. `VALID_FIX == 1` かつ `(0,0)` 近傍（±0.0001° = ±1000 units）なら無効扱い
6. `sequence` の巻き戻りはログのみ（パケットは受理）
7. `timestamp` が ±24 時間を超えたら stale 警告（注入はユーザー設定）

Python 実装の `LocationPacket.validate()` と `FilterDecision` が同じ順序・
同じ理由コードを返す。

## 5. Control / Status の実装

### Control（受信側 → 送信側、1〜3 bytes）

| opcode | 名称 | バイト列 |
| ---: | :--- | :--- |
| `0x01` | `START` | `01` + uint16 LE interval_ms |
| `0x02` | `STOP` | `02` |
| `0x03` | `SET_INTERVAL` | `03` + uint16 LE interval_ms |
| `0x04` | `REQUEST_FIX` | `04` |
| `0x05` | `SET_EXTENDED` | `05` + uint8 enabled |
| `0x7F` | `RESET` | `7F` |

- `interval_ms` は `0` を既定値 1000 とみなし、`100..60000` の範囲外は
  既定値 1000 にクランプする（送信側で適用）。
- 未知 opcode は無視して `Status.last_error = 1`、長さ不正は無視して
  `Status.last_error = 2`。
- 受信側は接続直後に Status を read し、`START(1000)` を書く（再接続も冪等）。

### Status（送信側 → 受信側、8 bytes）

| offset | field | 値 |
| ---: | :--- | :--- |
| 0 | version | `0x01` |
| 1 | state | 0=Idle, 1=Streaming, 2=Paused, 3=Error |
| 2 | interval_ms | uint16 LE |
| 4 | battery_pct | 255=不明 |
| 5 | status_flags | bit0 extended, bit1 fix, bit2 charging, bit3 low battery |
| 6 | last_error | 0=none, 1=unknown opcode, 2=bad length, 3=location unavailable, 4=internal |
| 7 | reserved | 0 |

- 状態変化時と 10 秒ごとのハートビートで notify する。

## 6. テストベクタの共有

`tests/vectors/*.json` を各リポジトリのテストリソースへコピー（または CI で
`p2pgps-protocol` を checkout）して使う。

- Swift: `Bundle.module` のリソースとして `location.json` 等を追加し、
  `JSONDecoder` で `wire` / `hex` / `expect` を読む。
- Kotlin: `src/test/resources/vectors/` に置き、`kotlinx.serialization` または
  `org.json` で読む。

検証内容（3 実装共通）:

1. `wire` の値で encode し、`hex` と一致する。
2. `hex` を decode し、`wire` と一致する。
3. `expect.valid` / `expect.reason` と validate 結果が一致する。
4. Control は `command` から encode し、`hex` と一致する。
5. sequence シナリオは `SequenceTracker` 相当の状態遷移を検証する。

## 7. バージョニングと互換性

- `version` フィールドで互換性を判定。未知バージョンは破棄し `last_error = 4`。
- 後方互換の追加は「予約ビット」「予約 opcode」「Extended の reserved」を使う。
- 破壊的変更は v2 として UUID を変えず `version = 0x02`。受信側は両対応する。
- Control の `AUTH`（`0x10`）は v2 の HMAC / ペアリングコード用に予約。

## 8. 実装チェックリスト

- [ ] UUID 5 つ（Service / Location / Control / Status / Extended）が仕様と一致
- [ ] Location Packet が 20 bytes 固定、全フィールドのオフセットと型が一致
- [ ] 緯度経度が度 × 10^7 の int32（リトルエンディアン）
- [ ] `altitude_m` が符号付き int16
- [ ] `timestamp` が符号なし uint32
- [ ] flags の bit 割り当てと reserved bit7 の破棄
- [ ] §3.3 の検証順序と Null Island 対策
- [ ] sequence の uint16 ラップと巻き戻りログ
- [ ] stale（±24 時間）の警告
- [ ] Control のクランプ（0 → 1000、範囲外 → 1000）と未知 opcode / 長さ不正
- [ ] Status の 8 bytes レイアウトと 10 秒ハートビート
- [ ] 共有テストベクタ全件が自実装で通る
- [ ] 実機 BLE で iPad（central）⇄ iPhone / Android（peripheral）の接続確認

## 9. よくある落とし穴

| 症状 | 原因 | 対処 |
| :--- | :--- | :--- |
| 緯度経度が 10 倍ずれる | 度 × 10^6 で計算している | × 10^7（`356812360` = 35.6812360°） |
| 南極の標高が巨大な正値になる | `altitude_m` を符号なしで読んでいる | int16 として読む |
| 2106 年以降で timestamp が負になる | uint32 を符号付きで読んでいる | 符号なしで読む |
| iOS / Android で UUID が一致しない | バイトオーダーの変換を自前でやっている | 文字列 UUID を OS の BLE API に渡す。自前変換は 16 bytes 逆順 |
| START の interval が効かない | `0` をそのまま使っている | 0 → 1000、範囲外 → 1000 にクランプ |
| Null Island が表示される | 未測位パケットを有効 fix として扱っている | `VALID_FIX` を確認し、(0,0) ±0.0001° を無効扱い |
| sequence で誤検知する | uint16 ラップを考慮していない | `(seq - last) & 0xFFFF` で差分を計算 |
