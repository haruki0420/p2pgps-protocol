# P2P GPS Protocol

P2P GPS の Bluetooth 通信仕様です。仕様の正式なファイルは [`spec/protocol-v1.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/spec/protocol-v1.md)。実装者はここを起点に、仕様 → テストベクタ → 実装の順に読んでください。

## このリポジトリの中身

| 場所 | 内容 |
| :--- | :--- |
| `spec/protocol-v1.md` | 通信仕様（正式なファイル） |
| `p2pgps/` | 仕様を確認するための Python 実装 |
| `tests/` | テスト |
| `tests/vectors/` | テスト用データ |

## 使い方

```bash
git clone https://github.com/haruki0420/p2pgps-protocol.git
cd p2pgps-protocol
python -m pip install -e ".[test]"
python -m pytest -q
```

## 読む順

### 仕様を読む

- [Protocol](Protocol) — 仕様の要点
- [`spec/protocol-v1.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/spec/protocol-v1.md) — 正本

### 実装する

- [Getting Started](Getting-Started)
- [Integration](Integration) — 他のアプリとの合わせ方
- [Architecture](Architecture)

### テストする

- [Testing](Testing) — テストベクタと実行方法

### 共通

- [FAQ](FAQ)
- [Troubleshooting](Troubleshooting)
- [License](License)
- [Status](https://github.com/haruki0420/p2pgps/wiki/Status) — 検証状況の正本
- [Compatibility](https://github.com/haruki0420/p2pgps/wiki/Compatibility)

## 注意

- 通信は 1 対 1・近距離です。
- 認証や暗号化はありません。
- 実機 BLE の確認範囲は [Status](https://github.com/haruki0420/p2pgps/wiki/Status) を参照してください。
