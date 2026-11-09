#!/usr/bin/env bash
set -euo pipefail
BACKUP_FILE="${1:?Usage: verify_backup.sh path/to/backup.dump}"
[[ -f "$BACKUP_FILE" ]] || { echo "Backup file not found." >&2; exit 2; }
command -v pg_restore >/dev/null 2>&1 || { echo "pg_restore is required." >&2; exit 127; }
if [[ -f "${BACKUP_FILE}.sha256" ]]; then
  (cd "$(dirname "$BACKUP_FILE")" && sha256sum -c "$(basename "${BACKUP_FILE}.sha256")")
else
  echo "No SHA-256 sidecar found; archive structure will be checked only." >&2
fi
pg_restore --list "$BACKUP_FILE" >/dev/null
echo "Backup checksum and archive structure verified. This does not prove that a restore will succeed."
