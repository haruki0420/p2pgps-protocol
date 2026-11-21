# P2P GPS Protocol

P2P GPS の Bluetooth 通信仕様と、仕様を確認するための Python 実装・テストデータです。実装者は仕様を起点にしてください。

- **これは何**: BLE プロトコル v1.0.1 の正本仕様、Python リファレンス実装、共有テストベクタ。
- **誰向け**: iOS / Android の実装者、プロトコルを検証する QA。
- **制約**: 通信は 1 対 1・近距離。v1 は認証・暗号化なし（仕様 §8）。
- **状態**: 検証状況はハブ Wiki の [Status](https://github.com/haruki0420/p2pgps/wiki/Status) を参照。

## 中身

- 仕様の正式なファイル: [`spec/protocol-v1.md`](spec/protocol-v1.md)
- Python 実装: `p2pgps/`
- テスト: `tests/`
- テストデータ: `tests/vectors/`

## 使い方

```bash
python -m pip install -e ".[test]"
python -m pytest
```

## ドキュメント

- [Wiki の Home](https://github.com/haruki0420/p2pgps-protocol/wiki)
- [Getting Started](https://github.com/haruki0420/p2pgps-protocol/wiki/Getting-Started)
- [Testing](https://github.com/haruki0420/p2pgps-protocol/wiki/Testing)
- [困ったとき](https://github.com/haruki0420/p2pgps-protocol/wiki/Troubleshooting)

## ライセンス

MIT
