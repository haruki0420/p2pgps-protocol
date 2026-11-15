# テストベクタ（共通契約データ）

`tests/vectors/*.json` は **P2P GPS BLE プロトコル v1 のテストベクタ**です。
Python / Swift / Kotlin の 3 実装が共有する**契約データ**ですが、現状は各実装が
同じカテゴリ・同じ値を手動でミラーしており、JSON を直接読む自動同期は未実装です
（自動同期は未実装）。仕様の正本は [`spec/protocol-v1.md`](../../spec/protocol-v1.md)、
仕様 §10 が要求するベクタをすべて含みます。

## ファイル一覧

| ファイル | `kind` | 内容 |
| :--- | :--- | :--- |
| `location.json` | `location` | Location Packet（20 bytes）の正常系・異常系 |
| `extended.json` | `extended` | Extended Location Packet（8 bytes） |
| `control.json` | `control` | Control characteristic（1〜3 bytes、全 opcode + 異常系） |
| `status.json` | `status` | Status characteristic（8 bytes） |
| `sequences.json` | `sequence` | 複数パケットの sequence シナリオ（巻き戻り / 重複 / 欠番 / ラップ） |

## 共通フォーマット

各ファイルは次のトップレベル構造を持ちます。

```json
{
  "schema": "p2pgps-protocol/test-vectors/<kind>@1",
  "kind": "location",
  "source": "spec/protocol-v1.md §3, §3.3, §10",
  "vectors": []
}
```

- `schema` は `p2pgps-protocol/test-vectors/` で始まること（ローダが検証）。
- `kind` は `location` / `extended` / `control` / `status` / `sequence` のいずれか。
- `sequence` のみ `vectors` ではなく `scenarios` を使います。

### Location ベクタ

```json
{
  "id": "tokyo-station",
  "description": "東京駅（有効 fix、altitude/speed 有効、flags=0x07）",
  "wire": {
    "version": 1, "flags": 7, "sequence": 42,
    "latitude": 356812360, "longitude": 1397671250,
    "altitude_m": 3, "accuracy_m": 5, "speed_mps": 12,
    "timestamp": 1763136000
  },
  "degrees": { "latitude": "35.6812360", "longitude": "139.7671250" },
  "hex": "01072a004886441552c54e530300050c00521769",
  "expect": { "valid": true, "reason": null, "valid_fix": true }
}
```

- `wire`: ワイヤ値。`latitude` / `longitude` は **度 × 10^7 の整数**（int32）。
- `degrees`: 度表記（10 進文字列）。`wire` への変換チェックに使う（任意）。
- `hex`: 期待する 20 bytes（小文字・区切りなし）。
- `expect.valid`: 受信側が受理すべきか（仕様 §3.3）。
- `expect.reason`: 破棄理由。`null` なら受理。値は
  `bad_length` / `unknown_version` / `reserved_flag_set` /
  `latitude_out_of_range` / `longitude_out_of_range` / `null_island`。
- `expect.valid_fix`: `VALID_FIX` ビットの期待値。
- `no-fix`（`VALID_FIX=0`）は仕様 §3.3 上は**パケットとして受理**されます
  （`expect.valid=true`）が、受信側フィルタでは `accepted=False` /
  `reason="no_fix"` として**注入しません**（`FilterDecision.injectable=false`）。

### Extended / Status ベクタ

`wire`（フィールド名は仕様の表と同じ）、`hex`、`expect.valid` / `expect.reason`。

### Control ベクタ

正常系:

```json
{
  "id": "control-start-1000",
  "command": { "opcode": "START", "interval_ms": 1000 },
  "hex": "01e803",
  "expect": {
    "valid": true,
    "decoded": { "opcode": "START", "interval_ms": 1000, "normalized_interval_ms": 1000 }
  }
}
```

- `command`: 受信側が書き込むコマンド。`opcode` は名前（`START` など）または整数。
- `hex`: **生値**の 1〜3 bytes（受信側が書くバイト列そのもの）。
  例: `interval_ms = 0` なら `010000`、`50` なら `013200`、`60001` なら `0161ea`。
- `expect.decoded.interval_ms`: デコードした生値。
- `expect.decoded.normalized_interval_ms`: 送信側が適用する正規化後の値
  （仕様 §5.1 の境界クランプ: 0→1000、1–99→100、100–60000→そのまま、
  60001–65535→60000）。

異常系:

```json
{
  "id": "control-unknown-opcode-auth",
  "hex": "10",
  "expect": { "valid": false, "error": "unknown_opcode", "last_error": 1 }
}
```

`error` は `unknown_opcode`（→ `last_error=1`）または `bad_length`（→ `last_error=2`）。

### sequence シナリオ

```json
{
  "id": "sequence-regression",
  "description": "sequence 巻き戻り（100 → 99）。ログ対象だがパケットは受理",
  "packets": [
    { "wire": { "...": "..." }, "hex": "..." },
    { "wire": { "...": "..." }, "hex": "..." }
  ],
  "expect": {
    "accepted": [true, true],
    "sequence_status": ["first", "regression"]
  }
}
```

`sequence_status` は `first` / `ok` / `gap` / `duplicate` / `regression`。
仕様 §3.3-6 のとおり、巻き戻りでもパケット自体は受理されます。

## 使い方

### Python（このリポジトリ）

```bash
python -m p2pgps vectors          # 全ベクタを検証
python -m pytest                  # テストスイート（ベクタ検証を含む）
```

### Swift / Kotlin から読む場合

> 現状、Swift / Kotlin のテストはこの JSON を直接読んでおらず、同じ値を手動で
> ミラーしています（自動同期は未実装）。更新する場合の手順は次のとおりです。

1. このディレクトリの JSON をテストリソースとしてコピーする（サブモジュール / CI で取得）。
2. `hex` をバイト列に変換し、実装の `decode()` と比較する。
3. `wire` の値で `encode()` し、`hex` と一致することを確認する。
4. `expect.valid` / `expect.reason` で検証結果を比較する。
5. Control は `command` から encode し `hex`（生値）と一致すること、
   `normalized_interval_ms` が仕様 §5.1 の適用値であることを確認する。

実装間のフィールド名対応は
[`wiki/Integration.md`](../../wiki/Integration.md) を参照してください。

## ベクタを追加するとき

1. 仕様のどの節に対応するかを `description` と `source` に書く。
2. **期待 hex は手計算または独立実装（Node.js 等）で検算する**。実装の出力を
   そのままコピーしない（実装のバグをベクタが追認してしまうため）。
3. `python -m p2pgps vectors` と `python -m pytest` を通す。
4. 仕様 §10 のカテゴリを削らない。
