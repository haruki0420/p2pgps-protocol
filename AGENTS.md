# AGENTS.md — P2P GPS

このファイルは、このリポジトリで作業するコーディングエージェント向けのルールです。
**セッション開始時に必ず読み、作業前に確認してください。**

## 1. 作業前に読むファイル（必須）

- `AGENTS.md`（このファイル）
- `README.md`
- `PRODUCT.md` / `DESIGN.md`（存在する場合）
- `docs/` 配下の該当ドキュメント（アーキテクチャ・設計・セットアップなど）

### リポジトリ別の追加ファイル

| リポジトリ | 読むファイル |
| :--- | :--- |
| `p2pgps-ios` | `docs/architecture.md`, `docs/receiver-setup.md`, `docs/source.md`, `docs/design.md` |
| `p2pgps-android` | `docs/architecture.md`, `docs/design.md`, `docs/protocol.md`, `docs/testing.md` |
| `p2pgps-protocol` | `spec/protocol-v1.md` |
| `p2pgps-hub` | `docs/architecture.md`, `docs/networking.md`, `docs/glossary.md`, `docs/licensing.md`, `docs/plan.md`, `docs/verification.md` |

### 優先順位

ユーザーの直接指示 > この `AGENTS.md` > `PRODUCT.md` / `DESIGN.md` > 各 `docs/`。
矛盾を見つけたら、独断で決めずにユーザーに報告する。

### 編集時の基本

- 既存ファイルを編集・上書きする前に、必ず読む。
- 変更後は関連するテスト / CI（`swift test`, `./gradlew test`, pytest など）を確認する。
- 仕様に関わる変更は、`p2pgps-protocol` の仕様とテストベクタも更新対象か確認する。

## 2. 個人データ・秘密情報の確認（必須）

**PR を送る前 / リポジトリを public にする前 / Release アセットを公開する前**に、
コミット内容（現在のツリーだけでなく **全 git 履歴**）に以下が含まれていないことを確認する。

- pairing file（`*.mobiledevicepairing` / `*.mobiledevicepair` / `pairingFile.plist`）とその内容
- 証明書・秘密鍵・プロビジョニングプロファイル（`*.p12` / `*.p8` / `*.mobileprovision` / `BEGIN ... PRIVATE KEY`）
- UDID・シリアル番号・デバイス名・MAC アドレス
- 個人のメールアドレス・ユーザー名・ローカルパス（`C:\Users\...` / `/Users/...`）
- トークン・API キー・パスワード（`ghp_` / `github_pat_` / `AKIA` など）
- 個人情報を含むログ・スクリーンショット・設定ファイル
- ローカルの作業ディレクトリ・参考資料・レビュー報告

確認コマンド例:

```bash
# 現在のツリー
git grep -n -I -E 'C:\\Users|/Users/|@gmail|@icloud|ghp_|github_pat_|BEGIN .*PRIVATE KEY'

# 全履歴のファイル名
git log --all --pretty=format: --name-only | sort -u \
  | grep -Ei 'pairing|udid|\.p12|\.p8|\.mobileprovision|\.env|\.ipa|\.dmg'

# 全履歴の内容（pairing file のシグネチャ）
git log --all -S'<key>DeviceCertificate</key>' --oneline
git log --all -S'<key>public_key</key>' --oneline
```

問題が見つかった場合は、**公開・PR 送信を中止**し、ユーザーに報告する。
履歴からの削除（`git filter-repo` 等）はユーザーの承認を得てから行う。

## 3. 第三者リポジトリへの PR

- ユーザーの**明示的な承認**なしに、第三者のリポジトリへ PR を送らない。
- 送る場合は、上記の個人データ確認と、上流の `CONTRIBUTING` / AI ポリシーの確認を行う。
- PR 本文には AI 利用の有無を開示する（上流が求める場合）。
- 過去にユーザー承認なしで第三者 PR を送ってクローズされた経緯があるため、必ず承認を得る。

## 4. 公開範囲

- `p2pgps-ios` は **public**（SideStore / AltStore ソース用）。他のリポジトリは private。
- public 化する場合は、上記の個人データ確認を必須とする。
- Release アセット（IPA / APK）にも個人データが含まれないことを確認する。

## 5. 作業ディレクトリ

- 作業は `p2pgps/` 配下のみ。
- ローカルの作業ディレクトリ・参考資料・レビュー報告はコミットしない。
- pairing file・証明書・IPA / APK・ビルド成果物はコミットしない（`.gitignore` 済み）。
