# Troubleshooting

`p2pgps-protocol` のセットアップ・テスト・CLI でよくある問題と対処です。

## Python が見つからない / Microsoft Store が開く

**症状**: `python --version` が何も表示しない、または Store が開く。
Windows の `python.exe` が Microsoft Store のスタブ（`WindowsApps` 配下）を
指していることが原因です。

**対処**:

1. python.org または `winget install Python.Python.3.12` で実体のある Python を入れる。
2. `py -3.12 --version` で確認する。
3. `py -3.12 -m pip install -e ".[test]"` のように `py` ランチャーを使う。

## `python -m p2pgps` で `No module named p2pgps`

**原因**: パッケージがインストールされていない、または cwd が `sys.path` にない。

**対処**:

```bash
python -m pip install -e .
# またはリポジトリルートで PYTHONPATH を設定
PYTHONPATH=. python -m p2pgps --help
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m p2pgps --help
```

## `pytest` で `ModuleNotFoundError: No module named 'p2pgps'`

**原因**: editable install をしていない、または別の Python で pytest を実行している。

**対処**:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

リポジトリ直下の `conftest.py` が `sys.path` を補正するため、install なしでも
`python -m pytest` は通ります。`pytest` コマンド（別 Python）ではなく
`python -m pytest` を使うのが確実です。

## `pip install -e ".[test]"` が失敗する

- `setuptools>=77` が必要です。`python -m pip install --upgrade pip setuptools` を実行。
- PowerShell では `.[test]` をクォートしてください: `python -m pip install -e ".[test]"`。
- 社内プロキシ等で PyPI に接続できない場合は、`pytest` だけ手動で入れて
  `python -m pytest` を実行してください（実行時依存はありません）。

## `vectors` コマンドで `tests/vectors not found`

**原因**: カレントディレクトリがリポジトリ外、または `tests/vectors` が無い。

**対処**: リポジトリルートで実行するか、`--dir` で指定します。

```bash
python -m p2pgps vectors --dir tests/vectors
```

## Windows で日本語が文字化けする / `UnicodeEncodeError`

CLI は起動時に stdout / stderr を UTF-8 に再設定しますが、古い環境では
`PYTHONIOENCODING=utf-8` を設定してください。

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m p2pgps decode --hex 01032a004886441552c54e530300050000521769
```

## hex が期待値と一致しない

チェックリスト:

1. **エンディアン**: すべてリトルエンディアン。`struct.pack("<...")` 相当か。
2. **緯度経度のスケール**: 度 × **10^7**（35.6812360 → 356812360）。
   10^6 だと 10 倍ずれます。
3. **符号**: `altitude_m` は int16、`latitude` / `longitude` は int32。
4. **timestamp**: uint32（符号なし）。
5. **flags**: 有効 fix は bit0。例の `flags = 0x03` は
   `VALID_FIX | ALTITUDE_VALID`。
6. 仕様 §3.2 の例と照合する:
   `01 03 2A 00 48 86 44 15 52 C5 4E 53 03 00 05 00 00 52 17 69`

CLI で確認:

```bash
python -m p2pgps encode --lat 35.6812360 --lon 139.7671250 \
  --flags 3 --seq 42 --alt 3 --acc 5 --speed 0 --ts 1763136000
```

## 南極の altitude が巨大な正値になる

`altitude_m` を符号なしで読んでいます。**int16（符号付き）** として読んでください。
例: `-2800 m` → `F5 10`（リトルエンディアン）。

## timestamp が 2106 年以降で負になる

`timestamp` は **uint32**。Kotlin では `Long` で保持し `and 0xFFFFFFFFL`、
Swift では `UInt32` を使ってください。

## Null Island のパケットが有効扱いになる / ならない

仕様 §3.3-5: `VALID_FIX == 1` のときだけ `(0,0)` 近傍（±0.0001° = ±1000 units）を
無効扱いします。`VALID_FIX == 0` の `(0,0)` は「未測位」として受理されます。

## sequence の巻き戻りでパケットが捨てられる

仕様 §3.3-6: 巻き戻りは**ログに記録するだけ**で、パケット自体は受理します。
`SequenceTracker` の `REGRESSION` は拒否理由ではありません。uint16 のラップ
（65535 → 0）も正常です。差分は `(seq - last) & 0xFFFF` で計算してください。

## `serve` が BLE でアドバタイズしない

- `bless` が必要です: `python -m pip install -e ".[ble]"`。
- 未インストール時は自動的に stdout バックエンドへフォールバックします
  （`--backend stdout` で明示も可）。
- OS / Bluetooth アダプタによってはペリフェラルモードが使えない場合があります。
  その場合は stdout 出力を別ツールで流してください。

## `scan` が `bleak is not installed` で終了する

`python -m pip install -e ".[ble]"` を実行してください。CI では意図的に
bleak を入れず、このエラーパスをテストしています。

## CI で Windows だけ落ちる

- 改行コード: `.gitattributes` の `eol=lf` が効いているか確認。
- 文字コード: テストは `encoding="utf-8"` を明示。subprocess テストは
  `PYTHONIOENCODING=utf-8` を設定。
- パス: テストは `pathlib.Path` とリポジトリルート基準の探索を使用。
- ローカルで再現する場合:

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m pytest -q
```

## 実機 BLE で接続できない

このリポジトリの範囲外です。確認事項:

- 送信側が Service UUID `B1E5A000-...` をアドバタイズしているか
- 名前が `P2PGPS-` で始まっているか
- 受信側が Service UUID でスキャンフィルタしているか
- iOS は `NSBluetoothAlwaysUsageDescription`、Android は
  `BLUETOOTH_ADVERTISE` / `BLUETOOTH_CONNECT` 権限があるか

iPad 側の位置注入（Developer Mode・LocalDevVPN・pairing file・DDI）は
`p2pgps-ios` の Wiki / README を参照してください。
