# Testing（テストとテストベクタ）

このリポジトリのテストは「仕様のバイト列と 1 バイト単位で一致すること」を
保証することを目的としています。CI は Ubuntu / Windows + Python 3.12 で実行します。

## 実行方法

```bash
python -m pip install -e ".[test]"
python -m pytest -q

# ベクタだけを CLI で検証
python -m p2pgps vectors
```

現在: **200 tests / 50 vectors**（CI は Linux / Windows。macOS は未検証）。

## テストの構成

| ファイル | 内容 |
| :--- | :--- |
| `tests/test_protocol.py` | 定数・UUID・オフセット・エンディアン・境界値・roundtrip・例外・度変換・Control 全 opcode・Status・Extended |
| `tests/test_vectors.py` | 全ベクタの encode / decode / validate / 度変換、sequence シナリオ、仕様 §10 の網羅性 |
| `tests/test_filter.py` | sequence の状態遷移、stale、haversine、no-fix の棄却、外れ値除去、精度ゲート |
| `tests/test_cli.py` | `python -m p2pgps` を subprocess で起動し、終了コードと出力を検証 |
| `tests/test_spec_consistency.py` | 正本仕様と実装定数の整合性（UUID・opcode・§3.2 例・§3.3 レンジ・§5.1 interval 正規化・シーケンス図） |
| `tests/conftest.py` | ベクタ読み込みフィクスチャ（UTF-8） |
| `conftest.py` | `sys.path` 補正（editable install なしでも pytest が通る） |

## テストベクタの見方

`tests/vectors/` に 5 つの JSON があります。

| ファイル | kind | 内容 |
| :--- | :--- | :--- |
| `location.json` | location | Location Packet（正常系 7 + 異常系 6） |
| `extended.json` | extended | Extended Location Packet |
| `control.json` | control | Control 全 opcode + interval 境界（§5.1）+ 異常系（22 件） |
| `status.json` | status | Status |
| `sequences.json` | sequence | sequence の巻き戻り / 重複 / 欠番 / ラップ |

> これらの JSON は 3 実装の共通契約データですが、現状は各実装が同じカテゴリ・
> 同じ値を手動でミラーしており、JSON を直接読む自動同期は未実装（Roadmap）。

Location ベクタの例:

```json
{
  "id": "tokyo-station",
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

- `wire` = ワイヤ値（緯度経度は度 × 10^7 の整数）
- `hex` = 期待するバイト列（20 bytes、小文字・区切りなし）
- `expect.valid` / `expect.reason` = 受信側の受理 / 破棄理由
  （`null_island` / `latitude_out_of_range` / `longitude_out_of_range` /
  `unknown_version` / `reserved_flag_set` / `bad_length`）

詳細なスキーマは
[`tests/vectors/README.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/tests/vectors/README.md)
を参照してください。

### 仕様 §10 との対応

| 仕様 §10 | ベクタ |
| :--- | :--- |
| 東京駅 | `tokyo-station`, `tokyo-station-spec-3-2` |
| 南極 | `antarctic` |
| Null Island | `null-island`, `null-island-near-boundary` |
| 範囲外緯度 | `out-of-range-latitude`（+ 経度） |
| 未知バージョン | `unknown-version` |
| sequence 巻き戻り | `sequence-regression`（重複・欠番・ラップも） |
| Extended | `extended-gps` など 5 件 |
| Control 各 opcode | `control-*` 22 件（interval 境界 0/1/99/100/60000/60001/65535 を含む） |

## CI

`.github/workflows/ci.yml`:

| 項目 | 内容 |
| :--- | :--- |
| OS | `ubuntu-latest`, `windows-latest` |
| Python | 3.12 |
| インストール | `python -m pip install -e ".[test]"` |
| テスト | `python -m pytest -q` |
| スモーク | `encode` / `decode` / `vectors` の CLI 実行 |

BLE の optional extra（`bleak` / `bless`）は CI では入れません。`serve` は stdout
バックエンド、`scan` は「bleak 未インストール」エラーのテストのみを行います。

## ベクタを追加する手順

1. 仕様の該当節を確認し、`description` / `source` に節番号を書く。
2. `wire` と `hex` を**独立に**計算する（実装の出力をコピーしない）。
   - 度 × 10^7、リトルエンディアン、負数は 2 の補数
3. `python -m p2pgps vectors` と `python -m pytest -q` を通す。
4. 仕様 §10 のカテゴリを削らない。異常系は `expect.valid=false` と `reason` を書く。

## クロスプラットフォームの注意

- エンディアンは `struct` の `<` 指定で固定（ネイティブ依存なし）。
- `.gitattributes` で改行を LF に統一。
- ファイル入出力はすべて `encoding="utf-8"`。CLI は stdout / stderr を UTF-8 に再設定。
- パスは `pathlib.Path`。ベクタ探索はリポジトリルート基準。
- `requires-python >= 3.10`（`dataclass(slots=True)` / `X | None` を使用）。

## 関連

- [`docs/testing.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/docs/testing.md)
- [Troubleshooting](Troubleshooting)
