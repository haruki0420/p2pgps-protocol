# Getting Started

`p2pgps-protocol` をローカルで動かし、プロトコルのエンコード / デコードと
テストベクタ検証を試すまでの手順です。

## 1. 前提

- Python **3.10 以上**（CI は 3.12）
- git
- 実行時依存はありません（標準ライブラリのみ）
- BLE シミュレータを使う場合のみ `bleak` / `bless`（任意）

> Windows で `python` が Microsoft Store のスタブを指している場合は、
> 実体のある Python（python.org / winget / pyenv など）をインストールしてください。
> 詳細は [Troubleshooting](Troubleshooting) を参照。

## 2. 取得とインストール

```bash
git clone https://github.com/haruki0420/p2pgps-protocol.git
cd p2pgps-protocol

# テストも含めて開発する場合（推奨）
python -m pip install -e ".[test]"

# BLE 実機シミュレータも使う場合
python -m pip install -e ".[ble]"
```

editable install をしない場合は、リポジトリ直下から `python -m pytest` を実行すれば
`conftest.py` が `sys.path` を補正します。

## 3. テストを実行する

```bash
python -m pytest -q
# 200 passed
```

テストベクタだけを CLI で検証することもできます。

```bash
python -m p2pgps vectors
# vectors: .../tests/vectors
#   control.json: 22/22 passed
#   extended.json: 5/5 passed
#   location.json: 13/13 passed
#   sequences.json: 5/5 passed
#   status.json: 5/5 passed
# total: 50/50 passed
```

## 4. CLI の使い方

### encode — パケットを hex にする

```bash
# Location Packet（仕様 §3.2 の東京駅の例）
python -m p2pgps encode --lat 35.6812360 --lon 139.7671250 \
  --flags 3 --seq 42 --alt 3 --acc 5 --speed 0 --ts 1763136000
# => 01032a004886441552c54e530300050000521769

# JSON で詳細を表示
python -m p2pgps encode --lat 35.6812360 --lon 139.7671250 --flags 7 --json

# Extended Location Packet
python -m p2pgps encode --kind extended --provider gps --battery 87 \
  --satellites 12 --course 12345 --vacc 5
# => 0101570c39300500

# Control（START interval 1000ms。hex は生値）
python -m p2pgps encode --kind control --opcode START --interval-ms 1000
# => 01e803
python -m p2pgps encode --kind control --opcode START --interval-ms 0
# => 010000（送信側は既定値 1000 を適用。仕様 §5.1）

# Status（Streaming / battery 80% / extended + fix）
python -m p2pgps encode --kind status --state streaming --interval-ms 1000 \
  --battery 80 --status-flags 3
# => 0101e80350030000
```

### decode — hex を JSON にする

```bash
python -m p2pgps decode --hex 01032a004886441552c54e530300050000521769
```

```json
{
  "kind": "location",
  "length": 20,
  "valid": true,
  "reason": null,
  "fields": {
    "version": 1, "flags": 3, "sequence": 42,
    "latitude": 356812360, "longitude": 1397671250,
    "altitude_m": 3, "accuracy_m": 5, "speed_mps": 0,
    "timestamp": 1763136000
  },
  "decoded": { "latitude_deg": "35.681236", "longitude_deg": "139.767125", "...": "..." }
}
```

- `--kind auto`（既定）は 20 bytes → Location、8 bytes → Status、1〜3 bytes → Control。
  Extended（8 bytes）は `--kind extended` を明示してください。
- 終了コード: `0` = 正常、`1` = デコードできたが検証 NG、`2` = デコード不能。

### serve — 送信側シミュレータ

```bash
# stdout に 20 bytes の hex を 1 秒ごとに出力（依存なし）
python -m p2pgps serve --stdout --interval 1.0

# bless があれば BLE ペリフェラルとしてアドバタイズ
python -m p2pgps serve --lat 35.6812360 --lon 139.7671250 --interval 1.0
```

> `serve` の bless バックエンドは Location / Status の notify のみで、Control
> characteristic の write 受信は未実装です（`scan --connect` は実機向け）。

### scan — 受信側シミュレータ（bleak が必要）

```bash
python -m p2pgps scan --timeout 5
python -m p2pgps scan --connect <ADDRESS> --duration 30
```

## 5. Python API

```python
from p2pgps import Flags, LocationPacket, FixFilter

packet = LocationPacket.from_degrees(
    "35.6812360", "139.7671250",
    flags=int(Flags.VALID_FIX | Flags.ALTITUDE_VALID),
    sequence=42, altitude_m=3, accuracy_m=5, speed_mps=0,
    timestamp=1763136000,
)
raw = packet.encode()
assert raw.hex() == "01032a004886441552c54e530300050000521769"

decoded = LocationPacket.decode(raw)
decoded.validate()

filter_ = FixFilter()
decision = filter_.feed(decoded)
print(decision.accepted, decision.injectable, decision.stale)
```

## 6. 次に読む

- [Protocol](Protocol) — プロトコル v1 の全体像
- [Testing](Testing) — テストベクタの見方と追加方法
- [Architecture](Architecture) — 実装の構成
- 正本仕様: [`spec/protocol-v1.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/spec/protocol-v1.md)
