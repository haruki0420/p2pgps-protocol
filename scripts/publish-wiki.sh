#!/usr/bin/env bash
# GitHub Wiki へ wiki/*.md を同期する。
#
# 前提: GitHub 上で対象リポジトリの Wiki が作成済みであること。
#
# 使い方:
#   ./scripts/publish-wiki.sh
#
# 必要なもの: git, gh（認証済み）
set -euo pipefail
cd "$(dirname "$0")/.."

repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

if ! git clone --quiet "https://github.com/${repo}.wiki.git" "$tmp" 2>/dev/null; then
  echo "Wiki リポジトリを取得できませんでした。" >&2
  echo "GitHub の https://github.com/${repo}/wiki で最初のページを 1 度作成してください。" >&2
  exit 1
fi

cp wiki/*.md "$tmp"/
# wiki/ から消したページは GitHub Wiki からも消す
for f in "$tmp"/*.md; do
  [ -e "$f" ] || continue
  base="$(basename "$f")"
  [ -f "wiki/$base" ] || rm -f "$f"
done
git -C "$tmp" add -A
if git -C "$tmp" diff --cached --quiet; then
  echo "Wiki は最新です: https://github.com/${repo}/wiki"
  exit 0
fi

login="$(gh api user -q .login)"
git -C "$tmp" -c user.name="$login" -c user.email="${login}@users.noreply.github.com" \
  commit --quiet -m "docs: sync wiki from repository"
git -C "$tmp" push --quiet
echo "Wiki を更新しました: https://github.com/${repo}/wiki"
