#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/safe/subdir" "$TMP/unsafe"
printf 'safe archive content\n' > "$TMP/safe/subdir/file.txt"
tar -czf "$TMP/safe.tar.gz" -C "$TMP/safe" .
python3 "$ROOT/scripts/validate_data_archive.py" "$TMP/safe.tar.gz" >/dev/null

# A path traversal member must be rejected before extraction.
printf 'sensitive\n' > "$TMP/unsafe/marker"
tar -czf "$TMP/traversal.tar.gz" -C "$TMP/unsafe" --transform='s|marker|../escaped.txt|' marker
if python3 "$ROOT/scripts/validate_data_archive.py" "$TMP/traversal.tar.gz" >/dev/null 2>&1; then
  echo "Unsafe path traversal archive unexpectedly accepted." >&2
  exit 1
fi

# A symlink member can redirect a later archive member outside the restore root.
ln -s /tmp "$TMP/unsafe/redirect"
tar -czf "$TMP/symlink.tar.gz" -C "$TMP/unsafe" redirect
if python3 "$ROOT/scripts/validate_data_archive.py" "$TMP/symlink.tar.gz" >/dev/null 2>&1; then
  echo "Symlink archive member unexpectedly accepted." >&2
  exit 1
fi

echo "Data archive validator accepts safe archives and rejects traversal/symlink members."
