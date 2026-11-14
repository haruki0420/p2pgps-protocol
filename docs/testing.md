# テスト（`p2pgps-protocol`）

プロトコル実装の正しさを **仕様のバイト列と 1 バイト単位で一致すること** で保証する。
テストは GitHub Actions（ubuntu-latest / windows-latest、Python 3.12）で実行する。

## 1. 実行方法

```bash
# 推奨（editable install + test extra）
python -m pip install -e ".[test]"
python -m pytest -q

# install せずにリポジトリ直下から実行する場合
python -m pytest -q          # conftest.py が sys.path を補正する

# テストベクタだけを CLI で検証
python -m p2pgps vectors
```

現在のテスト数: **179**（Linux / macOS / Windows で同一結果）。

## 2. テスト構成

| ファイル | 内容 |
| :--- | :--- |
| `tests/test_protocol.py` | 定数・UUID・フィールドオフセット・エンディアン・境界値・roundtrip・例外・度変換・Control 全 opcode・Status・Extended |
| `tests/test_vectors.py` | `tests/vectors/*.json` の全ベクタ（encode / decode / validate / 度変換 / sequence シナリオ）と仕様 §10 の網羅性 |
| `tests/test_filter.py` | sequence の first/ok/gap/duplicate/regression/ラップ、stale（±24h）、haversine、外れ値除去、精度ゲート |
| `tests/test_cli.py` | `python -m p2pgps` を subprocess で起動し、encode / decode / vectors / serve / scan の挙動と終了コードを検証 |
| `tests/test_spec_consistency.py` | 正本仕様（`spec/protocol-v1.md`）と実装定数の整合性。UUID・opcode・flags・§3.2 の例・§3.3 レンジ・シーケンス図 |
| `tests/conftest.py` | ベクタ読み込みフィクスチャ（UTF-8 固定） |
| `conftest.py`（ルート） | `sys.path` 補正（editable install なしでも pytest が通るように） |

## 3. テストベクタ

`tests/vectors/*.json` が共有契約データ。スキーマ・各ファイルの内容・
Swift / Kotlin からの読み方は [`tests/vectors/README.md`](../tests/vectors/README.md) を参照。

仕様 §10 の要求との対応:

| 仕様 §10 の項目 | ベクタ ID（例） | ファイル |
| :--- | :--- | :--- |
| 東京駅（有効 fix、altitude/speed 有効） | `tokyo-station` | `location.json` |
| 仕様 §3.2 のエンコード例 | `tokyo-station-spec-3-2` | `location.json` |
| 南極（負の緯度・経度、altitude 負） | `antarctic` | `location.json` |
| Null Island（無効扱い） | `null-island`, `null-island-near-boundary` | `location.json` |
| 範囲外緯度（破棄） | `out-of-range-latitude` | `location.json` |
| 範囲外経度（破棄） | `out-of-range-longitude` | `location.json` |
| 未知バージョン（破棄） | `unknown-version` | `location.json` |
| 予約ビット（破棄） | `reserved-flag-set` | `location.json` |
| 未測位 | `no-fix` | `location.json` |
| 境界値（±90°, ±180°, int16/uint32 端） | `boundary-max`, `boundary-min` | `location.json` |
| sequence 巻き戻り | `sequence-regression` | `sequences.json` |
| sequence 重複・欠番・ラップ | `sequence-duplicate`, `sequence-gap`, `sequence-wrap` | `sequences.json` |
| Extended（battery/provider/course） | `extended-gps`, `extended-unknown`, `extended-manual-simulated`, `extended-network-low-battery` | `extended.json` |
| Control 各 opcode | `control-start-*`, `control-stop`, `control-set-interval`, `control-request-fix`, `control-set-extended-*`, `control-reset` | `control.json` |
| Control 異常系 | `control-unknown-opcode-*`, `control-bad-length-*` | `control.json` |
| Status | `status-idle`, `status-streaming`, `status-error-*`, `status-charging-heartbeat` | `status.json` |

### 期待 hex の検算

ベクタの `hex` は実装の出力をそのままコピーせず、**独立実装で検算**する。
開発時は Node.js の `DataView` による独立エンコーダで全 61 アサーションを照合した
（`tools/` の一時スクリプト。リポジトリには含めない）。CI では
`tests/test_spec_consistency.py` が仕様書の例示 hex と実装の一致を検査する。

## 4. CI

`.github/workflows/ci.yml`:

| 項目 | 内容 |
| :--- | :--- |
| OS | `ubuntu-latest`, `windows-latest` |
| Python | 3.12（`actions/setup-python`） |
| インストール | `python -m pip install -e ".[test]"` |
| テスト | `python -m pytest -q` |
| スモーク | `python -m p2pgps encode ...` / `decode --hex ...` / `vectors` |

BLE の optional extra（`bleak` / `bless`）は CI ではインストールしない。
`serve` は stdout バックエンド、`scan` は「bleak 未インストール」エラーの
テストのみを行う（実機依存を CI から排除）。

## 5. クロスプラットフォームの注意

- **エンディアン**: すべて `struct` の明示的なリトルエンディアン指定（`<`）。
  プラットフォームのネイティブエンディアンに依存しない。
- **改行コード**: `.gitattributes` で `eol=lf` に統一。仕様書を読むテストは
  空白・改行を正規化して比較する。
- **文字コード**: ファイル読み書きはすべて `encoding="utf-8"` を明示。
  CLI は起動時に stdout / stderr を UTF-8 に再設定（Windows の cp932 対策）。
  subprocess テストは `PYTHONIOENCODING=utf-8` を設定する。
- **パス**: `pathlib.Path` を使用。ベクタ探索はリポジトリルート基準
  （`p2pgps/vectors.py:find_vectors_dir`）で、editable install でも動作する。
- **Python バージョン**: `requires-python = ">=3.10"`。`dataclass(slots=True)` や
  `X | None` 構文を使用（3.10 以降）。

## 6. ベクタを追加する手順

1. 仕様の該当節を確認し、`description` / `source` に節番号を書く。
2. `wire`（整数のワイヤ値）と `hex`（期待バイト列）を**独立に**計算する。
   - 緯度経度: 度 × 10^7（例 `35.6812360` → `356812360`）
   - リトルエンディアン、符号付きは 2 の補数
3. `python -m p2pgps vectors` と `python -m pytest -q` を通す。
4. 仕様 §10 のカテゴリを削らない。異常系は `expect.valid=false` と `reason` を書く。
5. 必要なら `tests/test_vectors.py` の網羅性テスト（`test_vectors_cover_spec_section_10`）を更新する。

## 7. 仕様節とテストの対応

| 仕様 | 主なテスト |
| :--- | :--- |
| §1 UUID / GATT | `test_uuids_are_canonical_128bit`, `test_uuid_wire_order_is_little_endian`, `test_spec_contains_all_uuids` |
| §2 バイトオーダー | `test_location_encode_places_each_field_at_spec_offset`, `test_location_boundary_values_roundtrip` |
| §3 Location Packet | `test_protocol.py` の Location 系一式、`location.json` |
| §3.1 flags | `test_location_readable_dict`, `test_reserved_flag_bit_is_rejected` |
| §3.2 例 | `test_spec_3_2_example_vector`, `test_spec_3_2_example_matches_implementation` |
| §3.3 検証 | `test_valid_packet_passes_validation`, Null Island / 範囲外 / 未知バージョン / 予約ビット |
| §4 Extended | `test_extended_*`, `extended.json` |
| §5 Control | `test_control_*`, `control.json` |
| §6 Status | `test_status_*`, `status.json` |
| §7 シーケンス | `test_spec_contains_sequence_diagram`, CLI `serve` / `scan` |
| §8 セキュリティ | 仕様整合テスト（`test_spec_contains_*`）とドキュメント |
| §9 バージョニング | `test_unknown_version_is_rejected`, `test_last_error_for_reason` |
| §10 テストベクタ | `test_vectors_cover_spec_section_10`, `test_run_vectors_all_pass` |
