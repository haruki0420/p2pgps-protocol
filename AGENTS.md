# AGENTS.md — P2P GPS

このファイルは、`p2pgps` 配下のリポジトリで作業するコーディングエージェント向けのルールです。
**セッション開始時に必ず読み、作業前に確認してください。**

## 1. 個人データ・秘密情報の確認（必須）

**PR を送る前 / リポジトリを public にする前 / Release アセットを公開する前**に、
コミット内容（現在のツリーだけでなく **全 git 履歴**）に以下が含まれていないことを確認する。

- pairing file（`*.mobiledevicepairing` / `*.mobiledevicepair` / `pairingFile.plist`）とその内容
- 証明書・秘密鍵・プロビジョニングプロファイル（`*.p12` / `*.p8` / `*.mobileprovision` / `BEGIN ... PRIVATE KEY`）
- UDID・シリアル番号・デバイス名・MAC アドレス
- 個人のメールアドレス・ユーザー名・ローカルパス（`C:\Users\...` / `/Users/...`）
- トークン・API キー・パスワード（`ghp_` / `github_pat_` / `AKIA` など）
- 個人情報を含むログ・スクリーンショット・設定ファイル
- `.tools/` / `_research/` / `review/` / `_ref/` などの作業ディレクトリ

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

## 2. 第三者リポジトリへの PR

- ユーザーの**明示的な承認**なしに、第三者のリポジトリへ PR を送らない。
- 送る場合は、上記の個人データ確認と、上流の `CONTRIBUTING` / AI ポリシーの確認を行う。
- PR 本文には AI 利用の有無を開示する（上流が求める場合）。
- 2026-11-15 に iloader へ PR #1161 をユーザー承認なしで送ってクローズされた経緯がある。同じことを繰り返さない。

## 3. 公開範囲

- `p2pgps-ios` は **public**（SideStore / AltStore ソース用）。他のリポジトリは private。
- public 化する場合は、上記の個人データ確認を必須とする。
- Release アセット（IPA / APK）にも個人データが含まれないことを確認する。

## 4. 作業ディレクトリ

- 作業は `p2pgps/` 配下のみ。
- `.tools/`・`_research/`・`_ref/`・`review/` はコミットしない。
- pairing file・証明書・IPA / APK・ビルド成果物はコミットしない（`.gitignore` 済み）。
