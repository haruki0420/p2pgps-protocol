# Changelog

このリポジトリの主な変更を記録します。形式は
[Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に準拠し、
バージョンは [Semantic Versioning](https://semver.org/lang/ja/) に従います。

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
