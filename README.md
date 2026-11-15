# p2pgps-protocol

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

**P2P GPS BLE プロトコル v1 の正本仕様・Python リファレンス実装・共有テストベクタ**のリポジトリです。

iPhone / Android が取得した GPS 位置情報を Bluetooth Low Energy (BLE) の GATT で
iPad に転送し、iPad 側で「その位置にいる」ように位置情報を反映（シミュレート）する
P2P プロトコルを定義します。位置情報はクラウドを経由せず、端末間の P2P のみで完結します。

## 3 リポジトリのハブ

| リポジトリ | 役割 | 技術 / ライセンス |
| :--- | :--- | :--- |
| **`p2pgps-protocol`（このリポジトリ）** | **プロトコル仕様の正本**、Python リファレンス実装、共有テストベクタ、ドキュメントのハブ | Python / MIT |
| [`p2pgps-ios`](https://github.com/haruki0420/p2pgps-ios) | iPhone = Sender / iPad = Receiver のユニバーサルアプリ。位置注入エンジン（StikDebug 由来） | Swift / AGPL-3.0 |
| [`p2pgps-android`](https://github.com/haruki0420/p2pgps-android) | Android Sender。BLE ペリフェラル + 前景サービス | Kotlin / MIT |

```
┌──────────────────────┐    BLE GATT (20 bytes, 1 Hz)    ┌──────────────────────────┐
│ iPhone / Android     │ ──────────────────────────────▶ │ iPad                     │
│  位置情報を取得       │   Service: B1E5A000-...         │  BLE セントラル           │
│  BLE ペリフェラル     │   Location / Status / Extended  │  MapKit 表示              │
└──────────────────────┘ ◀────────────────────────────── │  位置シミュレーション      │
                          Control (START/STOP/interval)  └──────────────────────────┘
```

## プロトコル概要（v1）

- **Location Packet**: 20 bytes 固定（ATT MTU 23 でも分割不要）。version / flags /
  sequence / 緯度経度（度 × 10^7 の int32）/ 標高 / 精度 / 速度 / Unix 時刻。
- **Extended Location Packet**: 8 bytes（任意）。provider / battery / 衛星数 / 進行方向 / 垂直精度。
- **Control**: 受信側 → 送信側。`START` / `STOP` / `SET_INTERVAL` / `REQUEST_FIX` /
  `SET_EXTENDED` / `RESET`（1〜3 bytes）。
- **Status**: 8 bytes。state / interval / battery / flags / last_error。
- すべてリトルエンディアン、浮動小数点なし。詳細は
  **[正本仕様 `spec/protocol-v1.md`](spec/protocol-v1.md)** を参照。

| 役割 | UUID |
| :--- | :--- |
| P2P GPS Service | `B1E5A000-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Location Packet | `B1E5A001-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Control | `B1E5A002-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Status | `B1E5A003-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Extended Location | `B1E5A004-9C3D-4E7A-8F20-1A2B3C4D5E6F` |

## インストール

Python 3.10 以上。実行時依存はありません（標準ライブラリのみ）。

```bash
git clone https://github.com/haruki0420/p2pgps-protocol.git
cd p2pgps-protocol

# テストも含めて開発する場合
python -m pip install -e ".[test]"

# BLE 実機シミュレータ（任意）
python -m pip install -e ".[ble]"
```

## クイックスタート（CLI）

```bash
# 東京駅の Location Packet をエンコード（仕様 §3.2 の例）
python -m p2pgps encode --lat 35.6812360 --lon 139.7671250 \
  --flags 3 --seq 42 --alt 3 --acc 5 --speed 0 --ts 1763136000
# => 01032a004886441552c54e530300050000521769

# hex をデコードして JSON で表示
python -m p2pgps decode --hex 01032a004886441552c54e530300050000521769

# Control（START, interval 1000ms）
python -m p2pgps encode --kind control --opcode START --interval-ms 1000
# => 01e803

# 全テストベクタを検証
python -m p2pgps vectors

# 送信側シミュレータ（BLE ペリフェラル。bless が無ければ stdout に hex を出力）
python -m p2pgps serve --lat 35.6812360 --lon 139.7671250 --interval 1.0

# 受信側シミュレータ（bleak が必要）
python -m p2pgps scan --connect <ADDRESS>
```

## Python から使う

```python
from p2pgps import Flags, LocationPacket

packet = LocationPacket.from_degrees(
    "35.6812360",
    "139.7671250",
    flags=int(Flags.VALID_FIX | Flags.ALTITUDE_VALID),
    sequence=42,
    altitude_m=3,
    accuracy_m=5,
    speed_mps=0,
    timestamp=1763136000,
)
raw = packet.encode()          # 20 bytes
assert raw.hex() == "01032a004886441552c54e530300050000521769"

decoded = LocationPacket.decode(raw)
decoded.validate()             # 仕様 §3.3 の検証。不正なら ValidationError
print(decoded.latitude_degrees, decoded.longitude_degrees)
```

受信側のフィルタ（範囲検証・stale・外れ値除去・sequence 監視）:

```python
from p2pgps import FixFilter

filter_ = FixFilter()
decision = filter_.feed(decoded)
if decision.injectable:  # accepted かつ VALID_FIX=1
    print("stale:", decision.stale, "sequence:", decision.sequence_status)
```

## テスト

```bash
python -m pytest -q     # 200 passed（CI: Linux / Windows。macOS は未検証）
```

- テストベクタ: [`tests/vectors/*.json`](tests/vectors)（3 実装の共通契約データ。
  現状は手動ミラーで、自動同期は Roadmap）
- テスト構成と CI: [`docs/testing.md`](docs/testing.md)
- CI: ubuntu-latest + windows-latest / Python 3.12 / `pip install -e ".[test]"` + `pytest -q`

## リポジトリ構成

```
p2pgps-protocol/
├── spec/protocol-v1.md      # 正本仕様（v1.0.1）
├── p2pgps/                  # Python リファレンス実装（標準ライブラリのみ）
│   ├── protocol.py          # UUID・パケット encode/decode/validate
│   ├── filter.py            # 範囲検証・no-fix・stale・外れ値除去・sequence 監視
│   ├── vectors.py           # テストベクタのローダ / 検証
│   └── cli.py               # python -m p2pgps
├── tests/
│   ├── vectors/*.json       # 共有テストベクタ（機械可読）
│   └── test_*.py            # pytest（200 tests）
├── docs/                    # architecture / testing / integration
├── wiki/                    # GitHub Wiki 用 Markdown
├── .github/workflows/ci.yml # CI（Ubuntu + Windows）
├── pyproject.toml
├── CHANGELOG.md
└── LICENSE                  # MIT
```

## ドキュメント

- [正本仕様 v1](spec/protocol-v1.md)
- [アーキテクチャ](docs/architecture.md)
- [テスト](docs/testing.md)
- [他リポジトリとの統合](docs/integration.md)
- Wiki: [Home](wiki/Home.md) / [Getting Started](wiki/Getting-Started.md) /
  [Protocol](wiki/Protocol.md) / [Architecture](wiki/Architecture.md) /
  [Testing](wiki/Testing.md) / [Troubleshooting](wiki/Troubleshooting.md) /
  [FAQ](wiki/FAQ.md)

## Wiki

`wiki/` に GitHub Wiki 用の Markdown を用意しています。GitHub の仕様で Wiki の初回ページだけは手動作成が必要です。

1. https://github.com/haruki0420/p2pgps-protocol/wiki を開き「Create the first page」→ そのまま Save。
2. `./scripts/publish-wiki.sh` を実行すると `wiki/*.md` が Wiki に同期されます。

## 既知の制約

- 実機 BLE（CoreBluetooth / Android BLE）での動作検証は未実施です。CI はプロトコル層の
  ユニットテストと CLI までを保証します。
- v1 は認証・暗号化を行いません（Just Works 相当）。近距離の第三者が偽の位置を送れるため、
  受信側は「注入は既定 OFF」「許可した送信側のみ自動接続」「注入中は常時バナー」を必須とします
  （仕様 §8）。
- `serve` の BLE ペリフェラル送信には `bless`、`scan` には `bleak` が必要です
  （`pip install -e ".[ble]"`）。BLE スタックの都合で OS / アダプタによっては動作しない場合があります。

## ライセンス

MIT。詳細は [LICENSE](LICENSE) と [CHANGELOG.md](CHANGELOG.md) を参照してください。
