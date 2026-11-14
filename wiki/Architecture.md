# Architecture（このリポジトリの構成）

`p2pgps-protocol` は「仕様の正本」「実行可能なリファレンス実装」「共有テストベクタ」を
1 つのリポジトリにまとめ、iOS / Android 実装の共通契約を提供します。

## 位置づけ

```
p2pgps-protocol（正本）
  spec/protocol-v1.md   ← 数値・バイト配置の規範
  tests/vectors/*.json  ← 3 実装の共通契約データ（現状は手動ミラー）
  p2pgps/               ← Python リファレンス実装
        │
        ├──▶ p2pgps-ios (Swift)     P2PGPSProtocol モジュール
        ├──▶ p2pgps-android (Kotlin) protocol パッケージ
        └──▶ CLI / 受信側シミュレータ
```

## モジュール構成

| モジュール | 役割 |
| :--- | :--- |
| `p2pgps/protocol.py` | 定数（UUID・サイズ・スケール・範囲）、列挙（flags / opcode / state / last_error）、例外、`LocationPacket` / `ExtendedPacket` / `ControlCommand` / `Status`、hex ヘルパ、度変換、汎用デコード |
| `p2pgps/filter.py` | `SequenceTracker`（first / ok / gap / duplicate / regression、uint16 ラップ対応）、`is_stale`（±24h）、`haversine_m`、`FixFilter`（検証 → sequence → no-fix → 精度 → 外れ値 → stale） |
| `p2pgps/vectors.py` | `tests/vectors/*.json` のローダと検証。`p2pgps vectors` の実体 |
| `p2pgps/cli.py` | `encode` / `decode` / `vectors` / `serve` / `scan` |
| `p2pgps/__init__.py` | 公開 API（`from p2pgps import LocationPacket, Flags, FixFilter`） |
| `p2pgps/__main__.py` | `python -m p2pgps` |

依存は一方向です。

```
cli.py ──▶ vectors.py ──▶ protocol.py
   └────────▶ filter.py ─────┘
```

## データフロー

### 送信（encode）

```
物理値（度・m・秒）
  └─ degrees_to_e7()（Decimal で 10 進 → 度×10^7）
       └─ LocationPacket(...)  ── encode() ──▶ 20 bytes ──▶ BLE notify
```

### 受信（decode → validate → filter）

```
20 bytes
  └─ LocationPacket.decode()   パースのみ（長さ検査）
       └─ validate()           仕様 §3.3 の破棄条件
            ├─ NG → ValidationError(reason) → 破棄 / Status.last_error
            └─ OK → FixFilter.feed()
                      ├─ sequence 監視（巻き戻りはログのみ）
                      ├─ 未測位（VALID_FIX=0）→ accepted=False / reason="no_fix"
                      ├─ 精度ゲート / 外れ値除去
                      └─ stale 警告
                           └─ accepted かつ injectable → 地図表示・位置注入
```

パースと検証を分離しているため、不正パケットでもフィールドを診断・ログ・
テストできます。iOS / Android も同じ順序で実装します。

## 設計判断

| 判断 | 理由 |
| :--- | :--- |
| 緯度経度をワイヤ値の int で保持 | 浮動小数点を持ち込まず、バイト列と 1:1 対応。度表記は `from_degrees` / `latitude_degrees` |
| 浮動小数点をワイヤに使わない | 決定論的・省サイズ・実装間の丸め差を排除（仕様 §2） |
| 例外を `ProtocolError` 系に統一 | `ValidationError.reason` を `Status.last_error` にマップ可能 |
| `dataclass(slots=True)` + 仕様と同じフィールド名 | JSON ベクタとそのまま相互変換 |
| `IntEnum` / `IntFlag` | ワイヤ値と直接対応し、名前付きでコードが書ける |
| `RejectReason` は `str` Enum | JSON の `expect.reason` と直接比較できる |
| テストベクタは JSON | 3 実装の共通契約データ。現状は手動ミラー（自動同期は Roadmap）。実装の出力をベクタにしない |
| 仕様書と定数の整合性テスト | UUID・opcode・§3.2 例・§3.3 レンジ・§5.1 interval 正規化のずれを CI で検出 |
| BLE は optional extra | `serve` は bless、`scan` は bleak。未インストール時は stdout / 明確なエラー。CI を BLE 依存にしない |

## Roadmap（未実装・既知の課題）

- **共有ベクタの自動同期**: Android / iOS のテストが `tests/vectors/*.json` を
  直接読む仕組みは未実装。現状は手動ミラーで、実装間の乖離検出は
  `tests/test_spec_consistency.py` とレビューの範囲。
- **`serve` の Control write 受信**: bless シミュレータは Location / Status の
  notify のみ（Control characteristic の write 受信は未実装）。

## エラーマッピング

| 事象 | 例外 | `Status.last_error` |
| :--- | :--- | :--- |
| 未知の Control opcode | `UnknownOpcodeError` | 1 |
| Control の長さ不正 | `ControlLengthError` | 2 |
| Location の長さ不正 | `PacketLengthError` | 2 |
| Location の未知バージョン | `ValidationError(UNKNOWN_VERSION)` | 4（仕様 §9） |
| 範囲外・予約ビット・Null Island | `ValidationError(...)` | 3 |
| 測位不能 | （Status で通知） | 3 |

## 拡張ポイント（v2 以降）

- `version` フィールドで互換性判定（未知バージョンは破棄）。
- Control の `AUTH`（`0x10`）は HMAC / ペアリングコード用に予約。
- flags bit7、Extended の reserved、未使用 opcode は後方互換の追加に使う。
- 破壊的変更は UUID を変えず `version = 0x02`。

## 関連ドキュメント

- [正本仕様](https://github.com/haruki0420/p2pgps-protocol/blob/main/spec/protocol-v1.md)
- [`docs/architecture.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/docs/architecture.md)
- [`docs/integration.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/docs/integration.md)
- [Testing](Testing)
