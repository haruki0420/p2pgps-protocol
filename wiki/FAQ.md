# FAQ

## P2P GPS とは何ですか？

iPhone / Android が取得した GPS 位置情報を BLE で iPad に送り、iPad 上で
「その位置にいる」ように位置情報を反映（シミュレート）するアプリケーション群です。
位置情報はクラウドを経由せず、端末間の P2P のみで完結します。iPad 側の位置固定は
StikDebug 由来の GPS シミュレーション機能（最小フォーク TLocation）を流用しています。

## なぜ 4 つのリポジトリに分かれているのですか？

3 つの実装リポジトリ（iOS / Android / protocol）＋ハブ（p2pgps）に分かれています。役割とライセンスが異なるためです。

| リポジトリ | 理由 |
| :--- | :--- |
| `p2pgps` | 全体の説明・セットアップ手順を置くハブ。MIT |
| `p2pgps-protocol` | 仕様・テストベクタは 3 つの実装の共通契約。MIT |
| `p2pgps-ios` | StikDebug / TLocation 由来コードを含むため AGPL-3.0 |
| `p2pgps-android` | 独自実装。MIT |

`p2pgps-protocol` が通信仕様の正本です。全体の説明は [p2pgps の Wiki](https://github.com/haruki0420/p2pgps/wiki) を参照してください。

## なぜ Location Packet は 20 bytes 固定なのですか？

BLE 4.0 の既定 ATT MTU は 23 bytes で、そのうちペイロードは 20 bytes です。
20 bytes 固定にすることで MTU 交渉なしでもフラグメンテーションが不要になり、
実装が単純になります（仕様 §1.1）。

## なぜ浮動小数点を使わないのですか？

決定論的で省サイズ、かつ実装間（Swift / Kotlin / Python）で丸め差が出ないためです。
緯度経度は「度 × 10^7」の int32 で送ります（1 unit ≒ 1.1 cm）。仕様 §2。

## なぜ 1 Hz なのですか？

位置シミュレーションの追従性と、BLE の省電力・帯域のバランスです。送信間隔は
Control の `START` / `SET_INTERVAL` で 100〜60000 ms の範囲で変更できます。

## なぜペアリング / 暗号化をしないのですか？

v1 は実装の単純さと「近距離の 1 対 1」を優先し、Just Works 相当（認証・暗号化なし）
です。その代わり、受信側に次の必須要件を課しています（仕様 §8）。

- 自動接続はユーザーが明示的に許可した送信側のみ
- 位置注入は既定 OFF（ユーザーが ON にしたときだけ）
- 注入中は画面上部に常時バナー（送信元名・最終受信時刻・座標）を表示
- 位置情報をクラウドに送らない
- ログの座標は丸める（既定: 小数 5 桁）

v2 で HMAC / ペアリングコードを追加する余地として、Control に `AUTH` opcode
（`0x10`）を予約しています。

## Null Island とは何ですか？

緯度経度 `(0, 0)` のことです。GPS が測位に失敗したときに `(0,0)` を返す実装があり、
そのまま地図に出すとアフリカ西沖の海上にピンが立ちます。仕様 §3.3-5 では
`VALID_FIX == 1` かつ `(0,0)` 近傍（±0.0001°）のパケットを「無効」として扱います。

## sequence はなぜ uint16 なのですか？

20 bytes に収めるための省サイズと、欠番・重複・巻き戻りの検出に十分な桁数の
バランスです。65535 の次は 0 に戻ります（uint16 ラップ）。巻き戻りはログに記録する
だけで、パケット自体は受理します（再送・並び替え耐性。仕様 §3.3-6）。

## Extended Location Packet は必須ですか？

任意です。送信側が対応している場合のみ notify し、受信側は無くても動作します
（仕様 §4）。バッテリー・プロバイダ・衛星数・進行方向・垂直精度を運びます。

## Python 実装は本番で使えますか？

このリポジトリの Python 実装は**リファレンス実装**です。仕様の実行可能な解釈、
テストベクタの検証、受信側シミュレータ（`serve` / `scan`）が主な用途です。
iOS / Android アプリのプロトコル層は Swift / Kotlin で実装します。

## iOS / Android と仕様の整合はどう保っていますか？

1. 正本仕様 `spec/protocol-v1.md` を 3 つの実装リポジトリ（iOS / Android / protocol）で共有
2. 共通テストベクタ `tests/vectors/*.json` と同じカテゴリ・値を各実装のテストで
   手動ミラー（JSON を直接読む自動同期は未実装・Roadmap）
3. このリポジトリの CI で「仕様書と実装定数の整合性」を検証

仕様を変更する場合は 3 つの実装リポジトリを同時に更新し、CHANGELOG と仕様の変更履歴に
記録します。

## テストベクタはどう使えばいいですか？

`tests/vectors/*.json` をテストリソースとしてコピーし、次の 3 点を検証します
（現状は各実装が同じ値を手動でミラーしています）。

1. `wire` の値で encode した結果が `hex` と一致する
2. `hex` を decode した結果が `wire` と一致する
3. `expect.valid` / `expect.reason` が validate 結果と一致する

詳細は [Testing](Testing) と
[`tests/vectors/README.md`](https://github.com/haruki0420/p2pgps-protocol/blob/main/tests/vectors/README.md)
を参照してください。

## Control の `interval_ms` はどう正規化しますか？

受信側は生値を書き、送信側が仕様 §5.1 の**境界クランプ**で適用します。

| 生値 | 適用値 |
| ---: | ---: |
| `0` | `1000`（既定値） |
| `1`–`99` | `100` |
| `100`–`60000` | そのまま |
| `60001`–`65535` | `60000` |

Status の `interval_ms` は正規化後の値です。旧仕様（v1.0）の「範囲外は既定値
1000」は v1.0.1 で置き換えられました。

## ライセンスは何ですか？ 商用利用できますか？

`p2pgps-protocol` は **MIT** です。商用利用・改変・再配布が可能です（著作権表示を
保持してください）。ただし `p2pgps-ios` は AGPL-3.0（StikDebug / TLocation 由来）です。
詳細は
[`https://github.com/haruki0420/p2pgps/wiki/License`](https://github.com/haruki0420/p2pgps/wiki/License)
（プロジェクトルート）と各リポジトリの LICENSE を参照してください。

## 実機での動作検証はしていますか？

実機 BLE の確認範囲はハブ Wiki の [Status](https://github.com/haruki0420/p2pgps/wiki/Status) を参照してください。CI ではプロトコル層の
ユニットテスト・CLI・仕様整合までを保証しています。実機手順は `p2pgps-ios` の
Wiki を参照してください。

## v2 の予定はありますか？

現時点では未定です。拡張の余地として次を確保しています。

- Control の `AUTH`（`0x10`）: アプリ層 HMAC / ペアリングコード
- flags の予約ビット（bit7）
- Extended の `reserved`
- `version` フィールドによる互換性判定（破壊的変更は `version = 0x02`）

## コントリビュートするには？

1. 仕様変更を伴う場合は、まず Issue で 3 つの実装リポジトリへの影響を相談してください。
2. テストベクタを追加する場合は、期待 hex を独立実装で検算してください。
3. `python -m pytest -q` と `python -m p2pgps vectors` を通してください。
4. CI（Ubuntu / Windows）が緑になることを確認してください。
