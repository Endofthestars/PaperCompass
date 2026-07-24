#!/usr/bin/env bash
set -euo pipefail

repo_url="https://github.com/zhaoyang97/Paper-Notes.git"
repo_dir="${1:-data/Paper-Notes}"

mkdir -p "$(dirname "$repo_dir")"

if [ -d "$repo_dir/.git" ]; then
  git -C "$repo_dir" pull --ff-only origin main
else
  git clone --filter=blob:none --sparse --depth=1 "$repo_url" "$repo_dir"
  git -C "$repo_dir" sparse-checkout set docs
fi

git -C "$repo_dir" log -1 --format='同步完成：%h %cs %s'
