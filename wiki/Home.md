# P2P GPS Protocol Wiki — Home

P2P GPS の **BLE プロトコル v1 の正本**・Python リファレンス実装・共有テストベクタの
ドキュメントハブです。iPhone / Android で取得した GPS 位置を BLE GATT で iPad に送り、
iPad 上で「その位置にいる」ように位置情報を反映（シミュレート）するための仕様を定義します。

## 3 リポジトリ

| リポジトリ | 役割 | 技術 / ライセンス |
| :--- | :--- | :--- |
| **p2pgps-protocol**（ここ） | プロトコル仕様の正本・Python リファレンス実装・共有テストベクタ・ドキュメントハブ | Python / MIT |
| [p2pgps-ios](https://github.com/haruki0420/p2pgps-ios) | iPhone = Sender / iPad = Receiver のユニバーサルアプリ（位置注入は StikDebug 由来） | Swift / AGPL-3.0 |
| [p2pgps-android](https://github.com/haruki0420/p2pgps-android) | Android Sender（BLE ペリフェラル + 前景サービス） | Kotlin / MIT |

## この Wiki のページ

| ページ | 内容 |
| :--- | :--- |
| [Getting Started](Getting-Started) | インストール、テスト実行、CLI の使い方 |
| [Protocol](Protocol) | プロトコル v1 の要約（UUID・パケット・flags・Control・Status・シーケンス） |
| [Architecture](Architecture) | モジュール構成、データフロー、設計判断 |
| [Testing](Testing) | テストベクタの見方、CI、ベクタ追加手順 |
| [Troubleshooting](Troubleshooting) | よくあるトラブルと対処 |
| [FAQ](FAQ) | よくある質問 |

正本仕様は [`spec/protocol-v1.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/spec/protocol-v1.md)、
テストベクタは
[`tests/vectors/`](https://github.com/haruki0420/p2pgps-protocol/tree/main/tests/vectors) にあります。

## プロトコル v1 の要点

| パケット | 長さ | 方向 | 主な内容 |
| :--- | ---: | :--- | :--- |
| Location Packet | 20 bytes 固定 | 送信側 → 受信側（notify） | version, flags, sequence, lat/lon（度×10^7）, alt, acc, speed, timestamp |
| Extended Location | 8 bytes | 送信側 → 受信側（任意） | provider, battery, satellites, course, vertical accuracy |
| Control | 1〜3 bytes | 受信側 → 送信側（write） | START / STOP / SET_INTERVAL / REQUEST_FIX / SET_EXTENDED / RESET |
| Status | 8 bytes | 送信側 → 受信側（notify） | state, interval, battery, status_flags, last_error |

- すべて **リトルエンディアン**、浮動小数点なし。
- 20 bytes 固定なので ATT MTU 23（BLE 4.0 既定）でも分割不要。
- 1 対 1 通信。iPad は同時に 1 台の送信側と接続（v1）。
- 認証・暗号化なし（Just Works 相当）。注入は既定 OFF（[Protocol](Protocol) のセキュリティ参照）。

| 役割 | UUID |
| :--- | :--- |
| P2P GPS Service | `B1E5A000-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Location Packet | `B1E5A001-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Control | `B1E5A002-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Status | `B1E5A003-9C3D-4E7A-8F20-1A2B3C4D5E6F` |
| Extended Location | `B1E5A004-9C3D-4E7A-8F20-1A2B3C4D5E6F` |

## 30 秒クイックスタート

```bash
git clone https://github.com/haruki0420/p2pgps-protocol.git
cd p2pgps-protocol
python -m pip install -e ".[test]"
python -m pytest -q
python -m p2pgps encode --lat 35.6812360 --lon 139.7671250 \
  --flags 3 --seq 42 --alt 3 --acc 5 --speed 0 --ts 1763136000
# => 01032a004886441552c54e530300050000521769
```

## ステータス

- プロトコル v1.0.1: **2026-11-15 更新**（§5.1 interval 正規化の明確化。変更は 3 リポジトリ同時更新）
- CI: Ubuntu / Windows + Python 3.12 で `pytest` と CLI スモークテスト
- 実機 BLE の動作検証は未実施（プロトコル層のユニットテストまでを保証）
- テストベクタは 3 実装の共通契約データ（現状は手動ミラー。自動同期は Roadmap）

## 既知の制約

- iPad 側の位置注入には Developer Mode・LocalDevVPN・pairing file・DDI が必要
  （StikDebug と同じ前提）。手順は `p2pgps-ios` の Wiki を参照。
- v1 は近距離の第三者が偽の位置を送れる。受信側の必須要件は仕様 §8 を参照。
- `serve` の BLE ペリフェラル送信には `bless`、`scan` には `bleak` が必要
  （`pip install -e ".[ble]"`）。
- `serve` の bless シミュレータは Control write を受信しない（Location / Status の
  notify のみ）。
