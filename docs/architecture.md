# アーキテクチャ（`p2pgps-protocol`）

このリポジトリは P2P GPS の **プロトコル正本・リファレンス実装・共有テストベクタ**を
提供する。実アプリ（`p2pgps-ios` / `p2pgps-android`）の BLE 実装はここで定義した
バイト列と検証規則に従う。

## 1. 位置づけ

```
                    ┌─────────────────────────────────────────────┐
                    │ p2pgps-protocol（このリポジトリ）             │
                    │  spec/protocol-v1.md  ← 正本（フリーズ）      │
                    │  tests/vectors/*.json ← 共有契約データ        │
                    │  p2pgps/              ← Python リファレンス   │
                    └───────────────┬─────────────────────────────┘
                                    │ 同じ仕様・同じベクタ
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
      p2pgps-ios (Swift)     p2pgps-android (Kotlin)   CLI / 検証ツール
      P2PGPSProtocol         protocol/ パッケージ       python -m p2pgps
```

- **正本（single source of truth）** は `spec/protocol-v1.md`。数値・バイト配置・
  opcode・flags はこの文書の表が規範。
- **共有テストベクタ** は `tests/vectors/*.json`。3 実装の**共通契約データ**だが、
  現状は各実装が同じカテゴリ・同じ値を手動でミラーしている（JSON を直接読む
  自動同期は未実装。Roadmap 参照）。
- Python 実装は「仕様の実行可能な解釈」であり、ベクタ生成・検証・受信側
  シミュレータの基盤でもある。

## 2. モジュール構成

```
p2pgps/
├── __init__.py    # 公開 API（バージョン、定数、パケットクラス、フィルタ）
├── __main__.py    # python -m p2pgps のエントリポイント
├── protocol.py    # プロトコル本体（標準ライブラリのみ）
│   ├── 定数: PROTOCOL_VERSION, 各 UUID, パケット長, スケール, 範囲, interval
│   ├── 列挙: Flags, Provider, Opcode, State, StatusFlags, LastError, RejectReason
│   ├── 例外: ProtocolError / PacketLengthError / WireRangeError /
│   │         ValidationError / UnknownOpcodeError / ControlLengthError
│   ├── LocationPacket   (20 bytes, encode/decode/validate)
│   ├── ExtendedPacket   (8 bytes)
│   ├── ControlCommand   (1〜3 bytes)
│   ├── Status           (8 bytes)
│   └── ヘルパ: to_hex/from_hex, degrees_to_e7/e7_to_degrees,
│               normalize_interval_ms, uuid_to_le_bytes, decode_packet
├── filter.py      # 受信側の状態付きフィルタ
│   ├── SequenceTracker  (first/ok/gap/duplicate/regression、uint16 ラップ対応)
│   ├── is_stale         (±24 時間)
│   ├── haversine_m      (外れ値判定用の距離)
│   └── FixFilter        (検証 → sequence → no-fix → 精度 → 外れ値 → stale)
├── vectors.py     # tests/vectors/*.json のローダと検証（CLI `vectors` の実体）
└── cli.py         # encode / decode / vectors / serve / scan
```

### 依存関係

```
cli.py ──▶ vectors.py ──▶ protocol.py
   │                         ▲
   └────────▶ filter.py ─────┘
```

- 実行時依存は **Python 標準ライブラリのみ**（`struct`, `dataclasses`, `enum`,
  `decimal`, `uuid`, `math`, `json`, `argparse`, `asyncio`）。
- `bleak` / `bless` は **optional extra**（`pip install -e ".[ble]"`）。
  import は `serve` / `scan` の実行時まで遅延するため、未インストールでも
  コア機能とテストは動作する。

## 3. データフロー

### 送信側（encode）

```
物理値（度・m・秒）
   │ degrees_to_e7()（Decimal で 10 進 → 度×10^7、0.5 は 0 から遠ざかる方向）
   ▼
LocationPacket（ワイヤ値の int）
   │ encode()（struct.pack("<BBHiihBBI")）
   ▼
20 bytes ──▶ BLE notify
```

### 受信側（decode → validate → filter）

```
20 bytes
   │ LocationPacket.decode()   ← 長さのみ検証（パースと検証を分離）
   ▼
LocationPacket
   │ validate()                ← 仕様 §3.3: version / reserved / 範囲 / Null Island
   │   └─ 不正 → ValidationError(reason)
   ▼
FixFilter.feed()               ← sequence 監視 / no-fix / 精度ゲート / 外れ値 / stale
   │
   ├─ accepted=False → 破棄（reason をログ / Status.last_error へ）
   │    - 未測位（VALID_FIX=0）は reason="no_fix"（注入不可・基準点を更新しない）
   └─ accepted=True かつ injectable=True → 地図表示・位置注入（stale は警告のみ）
```

**パースと検証を分離**している理由:

1. 不正パケットでもフィールド値を診断・ログ・テストできる。
2. 仕様 §3.3 の検証順序を 1 か所（`validate()`）に集約できる。
3. iOS / Android 実装が同じ順序で検証しやすい。

## 4. 設計判断

| 判断 | 理由 |
| :--- | :--- |
| 緯度経度を **ワイヤ値の int（度 × 10^7）** で保持 | 浮動小数点を持ち込まず、仕様のバイト列と 1:1 対応させる。度表記は `from_degrees` / `latitude_degrees` で変換 |
| 浮動小数点をワイヤに使わない | 決定論的・省サイズ・実装間の丸め差を排除（仕様 §2） |
| 例外を `ProtocolError` 系に統一 | 受信側は `ValidationError.reason` → `Status.last_error` にマップ可能。Control は `UnknownOpcodeError.last_error=1` / `ControlLengthError.last_error=2` を保持 |
| dataclass + `slots=True` | フィールド名を仕様の表と一致させ、JSON ベクタとそのまま相互変換 |
| `Enum` は int 値（`IntEnum` / `IntFlag`） | ワイヤ値と直接対応。`Flags.VALID_FIX` などの名前をコードで使える |
| `RejectReason` は `str` Enum + `__str__` | JSON の `expect.reason` とそのまま比較できる |
| テストベクタを JSON で管理 | 3 実装の共通契約データ。現状は手動ミラーで、自動同期は Roadmap。実装の出力をベクタにしない（独立検算を必須とする） |
| 仕様書と定数の整合性テスト | `spec/protocol-v1.md` の UUID・opcode・§3.2 例・§3.3 レンジ・§5.1 interval 正規化が実装からずれたら CI で検出 |
| BLE バックエンドを差し替え可能に | `serve` は bless、`scan` は bleak。未インストール時は stdout / 明確なエラーにフォールバックし、CI を BLE 依存にしない |

## 5. エラーマッピング

| 事象 | 例外 | `Status.last_error` |
| :--- | :--- | :--- |
| 未知の Control opcode | `UnknownOpcodeError` | 1 (`UNKNOWN_OPCODE`) |
| Control の長さ不正 | `ControlLengthError` | 2 (`BAD_LENGTH`) |
| Location の長さ不正 | `PacketLengthError` | 2 (`BAD_LENGTH`) |
| Location の未知バージョン | `ValidationError(UNKNOWN_VERSION)` | 4 (`INTERNAL`) ※仕様 §9 |
| 範囲外・予約ビット・Null Island | `ValidationError(...)` | 3 (`LOCATION_UNAVAILABLE`) |
| 測位不能 | （送信側が Status で通知） | 3 (`LOCATION_UNAVAILABLE`) |

`last_error_for_reason()` がこのマッピングを提供する（参考実装）。

## 6. 拡張ポイント（v2 以降）

- `version` フィールドで互換性を判定（未知バージョンは破棄）。
- Control の `AUTH` opcode（`0x10`）は v2 の HMAC / ペアリングコード用に予約済み。
- Location flags の bit7、Extended の `reserved`、未使用 opcode は後方互換の追加に使う。
- 破壊的変更は UUID を変えず `version=0x02` で表現し、受信側は両対応する。

## 6.1 Roadmap（未実装・既知の課題）

- **共有ベクタの自動同期**: Android / iOS のテストが `tests/vectors/*.json` を
  直接読む仕組みは未実装。現状は手動ミラーのため、実装間の乖離検出は
  `tests/test_spec_consistency.py` とレビューの範囲。CI で `p2pgps-protocol` を
  checkout して JSON を読む方式を検討中。
- **`serve` の Control write 受信**: bless シミュレータは Location / Status の
  notify のみ。Control characteristic の write 受信は未実装（`scan --connect` は
  実機向け）。

## 7. 既知の制約

- BLE の実送受信はこのリポジトリの CI では検証しない（OS / アダプタ依存）。
- `serve` の bless バックエンド、`scan` の bleak バックエンドは実機環境でのみ動作確認可能。
- 仕様 v1 は認証・暗号化なし（Just Works 相当）。セキュリティ要件は仕様 §8 を参照。
