#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?Set DATABASE_URL to the PostgreSQL target (do not put it on the command line)}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
umask 077
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FINAL="$BACKUP_DIR/finsight_${STAMP}.dump"
TEMP="${FINAL}.partial"
trap 'rm -f "$TEMP"' EXIT

command -v pg_dump >/dev/null 2>&1 || { echo "pg_dump is required (install PostgreSQL client tools)." >&2; exit 127; }
command -v pg_restore >/dev/null 2>&1 || { echo "pg_restore is required (install PostgreSQL client tools)." >&2; exit 127; }
# Put credentials in a private passfile, not a process argument visible in ps output.
source "$(dirname "$0")/postgres_connection.sh"
finsight_load_postgres_connection
trap 'rm -f "$TEMP"; finsight_cleanup_postgres_connection' EXIT
pg_dump --no-password --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
  --dbname="$PGDATABASE" --format=custom --no-owner --no-acl --file="$TEMP"
pg_restore --list "$TEMP" >/dev/null
mv "$TEMP" "$FINAL"
(cd "$BACKUP_DIR" && sha256sum "$(basename "$FINAL")" > "$(basename "${FINAL}.sha256")")
BYTES="$(wc -c < "$FINAL" | tr -d ' ')"
printf '{"file":"%s","created_at_utc":"%s","bytes":%s,"sha256":"%s","format":"pg_dump_custom"}\n' \
  "$(basename "$FINAL")" "$STAMP" "$BYTES" "$(sha256sum "$FINAL" | awk '{print $1}')" > "${FINAL}.manifest.json"
chmod 600 "$FINAL" "${FINAL}.sha256" "${FINAL}.manifest.json"
echo "Backup created: $FINAL ($BYTES bytes). Store it outside the application host and test restore regularly."
