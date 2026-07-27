#!/usr/bin/env bash
set -euo pipefail

repo_url="${PAPER_NOTES_UPSTREAM_URL:-https://github.com/zhaoyang97/Paper-Notes.git}"
repo_branch="${PAPER_NOTES_UPSTREAM_BRANCH:-main}"
repo_dir="${1:-data/Paper-Notes}"
cache_dir="${PAPER_NOTES_CACHE_DIR:-.cache/Paper-Notes-upstream}"
max_file_bytes="${PAPER_NOTES_MAX_FILE_BYTES:-99614720}"

if ! [[ "$max_file_bytes" =~ ^[0-9]+$ ]]; then
  echo "PAPER_NOTES_MAX_FILE_BYTES must be a non-negative integer." >&2
  exit 2
fi

mkdir -p "$(dirname "$cache_dir")" "$(dirname "$repo_dir")"

if [ -d "$cache_dir/.git" ]; then
  git -C "$cache_dir" fetch --depth=1 origin "$repo_branch"
  git -C "$cache_dir" checkout --detach FETCH_HEAD
else
  git clone --depth=1 --filter=blob:none --sparse --branch "$repo_branch" "$repo_url" "$cache_dir"
fi

git -C "$cache_dir" sparse-checkout set docs
git -C "$cache_dir" checkout --detach HEAD

if [ ! -d "$cache_dir/docs" ] || [ ! -f "$cache_dir/LICENSE" ]; then
  echo "Upstream repository must contain docs/ and LICENSE." >&2
  exit 1
fi

while IFS= read -r -d '' file; do
  size="$(wc -c < "$file" | tr -d '[:space:]')"
  if [ "$size" -gt "$max_file_bytes" ]; then
    echo "Refusing to mirror oversized file (${size} bytes): $file" >&2
    exit 1
  fi
done < <(find "$cache_dir/docs" -type f -print0)

revision="$(git -C "$cache_dir" rev-parse HEAD)"
staging_dir="$(mktemp -d "${TMPDIR:-/tmp}/paper-notes-sync.XXXXXX")"
cleanup() {
  rm -rf "$staging_dir"
}
trap cleanup EXIT

mkdir -p "$staging_dir/docs"
rsync -a --delete "$cache_dir/docs/" "$staging_dir/docs/"
cp "$cache_dir/LICENSE" "$staging_dir/LICENSE"

existing_revision=""
if [ -f "$repo_dir/UPSTREAM.md" ]; then
  existing_revision="$(sed -n 's/^upstream_commit: //p' "$repo_dir/UPSTREAM.md" | head -n 1)"
fi

if [ "$existing_revision" = "$revision" ]; then
  cp "$repo_dir/UPSTREAM.md" "$staging_dir/UPSTREAM.md"
else
  synced_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cat > "$staging_dir/UPSTREAM.md" <<EOF
# Paper-Notes provenance

- upstream_repository: $repo_url
- upstream_branch: $repo_branch
- upstream_commit: $revision
- synced_at_utc: $synced_at
- mirrored_scope: docs/ and LICENSE
- license: CC BY-NC-SA 4.0

The mirrored corpus originates from zhaoyang97/Paper-Notes. Retain this file
and LICENSE with the corpus, and comply with the upstream attribution,
non-commercial, and share-alike requirements.
EOF
fi

mkdir -p "$repo_dir"
rsync -a --delete "$staging_dir/" "$repo_dir/"

echo "Synchronized Paper-Notes revision ${revision} into ${repo_dir}"
