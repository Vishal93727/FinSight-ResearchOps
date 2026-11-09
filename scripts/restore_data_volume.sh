#!/usr/bin/env bash
set -euo pipefail

BACKUP_FILE="${BACKUP_FILE:?Set BACKUP_FILE to a verified app_data .tar.gz archive}"
[[ -f "$BACKUP_FILE" ]] || { echo "Backup file not found." >&2; exit 2; }
[[ -f "$BACKUP_FILE.sha256" ]] || { echo "A SHA-256 sidecar is required." >&2; exit 4; }
[[ "${CONFIRM_RESTORE:-}" == "YES" ]] || { echo "Destructive volume restore blocked. Set CONFIRM_RESTORE=YES after verifying the target Compose project." >&2; exit 3; }
command -v docker >/dev/null 2>&1 || { echo "Docker is required for app_data volume restore." >&2; exit 127; }
BACKUP_FILE="$(cd "$(dirname "$BACKUP_FILE")" && pwd)/$(basename "$BACKUP_FILE")"
(cd "$(dirname "$BACKUP_FILE")" && sha256sum -c "$(basename "$BACKUP_FILE").sha256")
python3 "$(dirname "$0")/validate_data_archive.py" "$BACKUP_FILE"
# Stop writers first. PostgreSQL restore should be performed separately from its verified dump.
docker compose stop api worker
docker compose run --rm --build --no-deps \
  -v "$(dirname "$BACKUP_FILE"):/backup:ro" --entrypoint sh api \
  -c "tar -tzf '/backup/$(basename "$BACKUP_FILE")' >/dev/null && tar -xzf '/backup/$(basename "$BACKUP_FILE")' -C /app/data --no-same-owner --no-same-permissions"
echo "Application data volume restored. Run DB/schema and file-hash checks before starting api/worker."
