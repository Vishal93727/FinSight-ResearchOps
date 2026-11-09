#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?Set DATABASE_URL to the PostgreSQL restore target}"
BACKUP_FILE="${BACKUP_FILE:?Set BACKUP_FILE to a verified custom-format backup}"
[[ "${CONFIRM_RESTORE:-}" == "YES" ]] || { echo "Destructive restore blocked. Set CONFIRM_RESTORE=YES after confirming the target database." >&2; exit 3; }
[[ -f "$BACKUP_FILE" ]] || { echo "Backup file not found." >&2; exit 2; }
[[ -f "${BACKUP_FILE}.sha256" ]] || { echo "A SHA-256 sidecar is required for destructive restore." >&2; exit 4; }
command -v pg_restore >/dev/null 2>&1 || { echo "pg_restore is required." >&2; exit 127; }
"$(dirname "$0")/verify_backup.sh" "$BACKUP_FILE"
source "$(dirname "$0")/postgres_connection.sh"
finsight_load_postgres_connection
trap 'finsight_cleanup_postgres_connection' EXIT
pg_restore --no-password --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
  --dbname="$PGDATABASE" --clean --if-exists --no-owner --no-acl --exit-on-error "$BACKUP_FILE"
echo "Restore command completed. Run Alembic/current checks, readiness checks and application smoke tests before resuming workers."
