# AGENTS.md — P2P GPS

このリポジトリで作業する人・エージェント向けのルールです。作業前に読んでください。

## 1. 作業前に読むもの

- `README.md`
- `PRODUCT.md` / `DESIGN.md`（ある場合）
- `wiki/` の該当ページ

仕様の正式な場所は `p2pgps-protocol/spec/protocol-v1.md` です。

## 2. 公開・PR・リリース前の確認（必須）

現在のファイルだけでなく、**Git の履歴全体**に次が含まれていないか確認してください。

- pairing file（`*.mobiledevicepairing` / `*.mobiledevicepair` / `pairingFile.plist`）
- 証明書・秘密鍵・プロビジョニングプロファイル（`*.p12` / `*.p8` / `*.mobileprovision`）
- UDID・シリアル番号・デバイス名・MAC アドレス
- 個人のメールアドレス・ユーザー名・ローカルパス
- トークン・API キー・パスワード
- 個人情報を含むログ・スクリーンショット・設定ファイル
- ローカルの作業フォルダ・参考資料・レビュー報告

確認例:

```bash
git grep -n -I -E 'C:\\Users|/Users/|@gmail|@icloud|ghp_|github_pat_|BEGIN .*PRIVATE KEY'
git log --all --pretty=format: --name-only | sort -u | grep -Ei 'pairing|udid|\.p12|\.p8|\.mobileprovision|\.env|\.ipa|\.dmg'
git log --all -S'<key>DeviceCertificate</key>' --oneline
git log --all -S'<key>public_key</key>' --oneline
```

問題が見つかった場合は、公開・PR 送信を中止して報告してください。履歴の書き換えは、必ずユーザーの承認を得てから行います。

## 3. 第三者リポジトリへの PR

- ユーザーの明示的な承認なしに、第三者のリポジトリへ PR を送らない。
- 送る場合は、個人データ確認と上流の `CONTRIBUTING` / AI ポリシーの確認を行う。
- PR 本文には AI 利用の有無を開示する（上流が求める場合）。

## 4. 公開範囲

- このプロジェクトのリポジトリは public です。
- 公開前に、上記の個人データ確認を必ず行う。
- Release の IPA / APK にも個人データが含まれないことを確認する。

## 5. 作業フォルダ

- 作業はこのリポジトリの中だけで行う。
- ローカルの参考資料・レビュー報告・作業用ツールはコミットしない。
- pairing file・証明書・IPA / APK・ビルド成果物はコミットしない（`.gitignore` 済み）。
