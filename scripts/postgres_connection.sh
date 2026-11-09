#!/usr/bin/env bash
# Shared safe DATABASE_URL parser for pg_dump/pg_restore.
# Passwords go only into a mode-0600 PGPASSFILE, never into process arguments.

finsight_load_postgres_connection() {
  : "${DATABASE_URL:?Set DATABASE_URL to the PostgreSQL target}"
  command -v python3 >/dev/null 2>&1 || { echo "python3 is required to parse DATABASE_URL safely." >&2; return 127; }
  PGPASSFILE="$(mktemp "${TMPDIR:-/tmp}/finsight-pgpass.XXXXXX")"
  chmod 600 "$PGPASSFILE"
  export PGPASSFILE
  local -a parsed=()
  mapfile -t parsed < <(python3 - "$PGPASSFILE" <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

raw, pgpass_path = os.environ["DATABASE_URL"], sys.argv[1]
parsed = urlparse(raw)
if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
    raise SystemExit("DATABASE_URL must use a PostgreSQL URL scheme")
if not parsed.hostname or not parsed.path.strip("/"):
    raise SystemExit("DATABASE_URL must include a host and database name")
host = parsed.hostname
port = str(parsed.port or 5432)
user = unquote(parsed.username or "")
password = unquote(parsed.password or "")
database = unquote(parsed.path.lstrip("/"))
if not user or not database:
    raise SystemExit("DATABASE_URL must include a username and database name")

def pgpass_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("\n", "\\n")

Path(pgpass_path).write_text(f"{pgpass_escape(host)}:{pgpass_escape(port)}:{pgpass_escape(database)}:{pgpass_escape(user)}:{pgpass_escape(password)}\n")
query = parse_qs(parsed.query)
sslmode = query.get("sslmode", [""])[0]
print(host)
print(port)
print(user)
print(database)
print(sslmode)
PY
)
  if [[ ${#parsed[@]} -lt 5 ]]; then
    rm -f "$PGPASSFILE"
    unset PGPASSFILE
    echo "Could not parse DATABASE_URL." >&2
    return 2
  fi
  export PGHOST="${parsed[0]}" PGPORT="${parsed[1]}" PGUSER="${parsed[2]}" PGDATABASE="${parsed[3]}"
  if [[ -n "${parsed[4]}" ]]; then export PGSSLMODE="${parsed[4]}"; fi
}

finsight_cleanup_postgres_connection() {
  if [[ -n "${PGPASSFILE:-}" && -f "$PGPASSFILE" ]]; then rm -f "$PGPASSFILE"; fi
  unset PGPASSFILE PGHOST PGPORT PGUSER PGDATABASE PGSSLMODE
}
