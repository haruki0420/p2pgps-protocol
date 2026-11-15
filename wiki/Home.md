# P2P GPS Protocol

P2P GPS の Bluetooth 通信仕様です。仕様の正式なファイルは [`spec/protocol-v1.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/spec/protocol-v1.md) です。

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

## ページ

- [Getting Started](Getting-Started)
- [Protocol](Protocol) — 仕様の要点
- [Testing](Testing)
- [Integration](Integration) — 他のアプリとの合わせ方
- [Architecture](Architecture) — 開発者向け
- [困ったとき](Troubleshooting)
- [よくある質問](FAQ)
- [License](License)

## 注意

- 通信は 1 対 1・近距離です。
- 認証や暗号化はありません。
- 実機 BLE は Android 実機 + iPad で確認済みです。プロトコル層はテスト済みです。
