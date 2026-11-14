# Changelog

このリポジトリの主な変更を記録します。形式は
[Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に準拠し、
バージョンは [Semantic Versioning](https://semver.org/lang/ja/) に従います。

## [1.0.1] - 2026-11-15

レビュー指摘（C-1 / C-2 / C-3d / C-4 / L-19〜L-25）への対応。仕様は v1.0.1。

### Changed

- **C-1**: 仕様 §5.1 を追加し、Control `interval_ms` の正規化を**境界クランプ方式**に
  明確化（`0` → 1000、`1`–`99` → 100、`100`–`60000` → そのまま、
  `60001`–`65535` → 60000）。`ControlCommand.encode()` は**生値**を書き、
  `normalize_interval_ms()` を明示的に呼ぶ形に変更。Status の `interval_ms` は
  正規化後の値。
- **C-1**: `tests/vectors/control.json` を生値 `hex` + `normalized_interval_ms` に
  更新（22 ベクタ。0/1/50/99/100/1000/60000/60001/65535 の境界を網羅）。
- **C-2**: `FixFilter` は未測位（`VALID_FIX=0`）を `accepted=False` /
  `reason="no_fix"` とし、外れ値判定の基準点（`last_fix`）を更新しない。
  `FilterDecision.injectable` を追加（表示可・注入不可を表現）。
- **C-4 / L-25**: テストベクタの説明を実態に合わせて訂正
  （3 実装が同じ JSON を読むのではなく、同じカテゴリ・値を手動でミラー。
  自動同期は Roadmap）。
- **L-19**: macOS は未検証であることを明記（CI は Linux / Windows）。
- **L-23**: `docs/integration.md` の Kotlin パスを実際の構成に修正。
- **L-22**: `serve` の bless シミュレータが Control write を受信しないことを明記。
- **R-4**: `RESET` は既定設定に戻すが、**ストリーミング状態は変更しない**ことを仕様 §5 に明記（iOS / Android の挙動を統一）。
- テストを 179 → 200 に拡充（§5.1 境界値、no-fix、NaN/inf、CLI 異常系）。

### Fixed

- **C-3d**: `protocol.py` の docstring から存在しない「付録 B」への参照を削除。
- **L-20**: `START` / `SET_INTERVAL` の `interval_ms=None` は例外（必須 payload）。
- **L-21**: `degrees_to_e7()` が NaN / inf を `ProtocolError` にする
  （CLI の traceback を解消）。
- ドキュメント内の「範囲外 → 1000」記述を §5.1 の境界クランプに統一
  （`docs/integration.md` / `wiki/FAQ.md` / `wiki/Protocol.md` ほか）。

## [1.0.0] - 2026-11-15

プロトコル v1 の正本仕様・Python リファレンス実装・共有テストベクタの初回リリース。

### Added

- `spec/protocol-v1.md`: BLE プロトコル v1 の**正本仕様**。変更履歴・用語集・
  UUID / GATT 表・パケットレイアウト・シーケンス図・セキュリティ・バージョニング・
  テストベクタ要件を収録。
- `p2pgps/protocol.py`: 標準ライブラリのみのリファレンス実装。
  UUID 定数、`LocationPacket`（20 bytes）、`ExtendedPacket`（8 bytes）、
  `ControlCommand`（START / STOP / SET_INTERVAL / REQUEST_FIX / SET_EXTENDED / RESET）、
  `Status`（8 bytes）、encode / decode / validate、型ヒント。
- `p2pgps/filter.py`: 受信側フィルタ。範囲検証、sequence の巻き戻り / 重複 / 欠番検出、
  stale 判定（±24 時間）、外れ値除去（移動速度ゲート）、精度ゲート。
- `p2pgps/cli.py` + `python -m p2pgps`: `encode` / `decode` / `vectors` / `serve` / `scan`。
  `serve` は bless（BLE ペリフェラル）または stdout、`scan` は bleak（BLE セントラル）。
- `tests/vectors/*.json`: 仕様 §10 の全カテゴリを網羅する機械可読テストベクタ
  （東京駅・南極・Null Island・範囲外・未知バージョン・sequence 巻き戻り・
  Extended・Control 全 opcode・Status）。iOS / Android と共有可能。
- `tests/`: pytest 179 テスト。ベクタのラウンドトリップ、境界値、異常系、
  CLI 統合、仕様書と実装定数の整合性チェック。
- `docs/architecture.md` / `docs/testing.md` / `docs/integration.md`。
- `wiki/`: GitHub Wiki 用 Markdown（Home / Getting-Started / Protocol /
  Architecture / Testing / Troubleshooting / FAQ）。
- `.github/workflows/ci.yml`: ubuntu-latest + windows-latest、Python 3.12、
  `pip install -e ".[test]"` + `pytest -q` + CLI スモークテスト。

### Fixed

- 仕様 §3.2 の例示 hex（lat / lon / timestamp）をフィールド定義（度 × 10^7、
  int32 / uint32 リトルエンディアン）に合わせて修正。
- 仕様 §3.3-4 の検証レンジをスケール（度 × 10^7）に合わせて修正
  （`±900_000_000` / `±1_800_000_000`。旧記載は 10 倍小さかった）。

### Notes

- v1 仕様は 2026-11-15 にフリーズ。変更する場合は 3 リポジトリ
  （`p2pgps-protocol` / `p2pgps-ios` / `p2pgps-android`）を同時に更新し、
  本 CHANGELOG と `spec/protocol-v1.md` の変更履歴に記録すること。
- 実機 BLE の動作検証は未実施（CI はプロトコル層のユニットテストまで）。
