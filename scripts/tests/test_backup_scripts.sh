#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/backups"
export ARG_LOG="$TMP/arguments.log"

cat > "$TMP/bin/pg_dump" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
printf 'pg_dump' >> "$ARG_LOG"
output=''
for arg in "$@"; do
  printf '|%s' "$arg" >> "$ARG_LOG"
  case "$arg" in --file=*) output="${arg#--file=}" ;; esac
done
printf '\n' >> "$ARG_LOG"
[[ -n "$output" ]]
[[ -f "$PGPASSFILE" ]]
[[ "$(stat -c '%a' "$PGPASSFILE")" == "600" ]]
printf 'FAKE_CUSTOM_ARCHIVE' > "$output"
FAKE

cat > "$TMP/bin/pg_restore" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
printf 'pg_restore' >> "$ARG_LOG"
for arg in "$@"; do printf '|%s' "$arg" >> "$ARG_LOG"; done
printf '\n' >> "$ARG_LOG"
FAKE
chmod +x "$TMP/bin/pg_dump" "$TMP/bin/pg_restore"
export PATH="$TMP/bin:$PATH"
export DATABASE_URL='postgresql+psycopg://finsight:do-not-leak-this-password@127.0.0.1:5432/finsight?sslmode=disable'
export BACKUP_DIR="$TMP/backups"

"$ROOT/scripts/backup_postgres.sh" >/dev/null
BACKUP_FILE="$(find "$BACKUP_DIR" -maxdepth 1 -name '*.dump' -print -quit)"
[[ -n "$BACKUP_FILE" ]]
"$ROOT/scripts/verify_backup.sh" "$BACKUP_FILE" >/dev/null
BACKUP_FILE="$BACKUP_FILE" CONFIRM_RESTORE=YES "$ROOT/scripts/restore_postgres.sh" >/dev/null

if grep -Fq 'do-not-leak-this-password' "$ARG_LOG"; then
  echo "Database password leaked into pg_dump/pg_restore process arguments." >&2
  exit 1
fi
if compgen -G "$TMP/finsight-pgpass.*" >/dev/null; then
  echo "Temporary PostgreSQL passfile was not removed." >&2
  exit 1
fi

echo "Backup/verify/restore script contract passed with fake PostgreSQL tools; password absent from process arguments."
