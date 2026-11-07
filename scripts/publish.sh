#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
REPO="${GITHUB_REPO_URL:-https://github.com/Pandaman-8/freedom-cqa-datathon.git}"
if [ ! -d .git ]; then git init -b main; fi
if ! git config user.name >/dev/null; then git config user.name "Pandaman-8"; fi
if ! git config user.email >/dev/null; then git config user.email "321914796+Pandaman-8@users.noreply.github.com"; fi
git branch -M main
if git remote get-url origin >/dev/null 2>&1; then git remote set-url origin "$REPO"; else git remote add origin "$REPO"; fi
git add .
if ! git diff --cached --quiet; then git commit -m "feat: establish validated CQA foundation"; fi
printf 'Pushing main to %s (no force)\n' "$REPO"
git push -u origin main
