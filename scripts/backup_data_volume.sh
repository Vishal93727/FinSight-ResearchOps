#!/usr/bin/env bash
set -euo pipefail

# Archive the shared Compose app_data volume through the API service mount.
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd)"
chmod 700 "$BACKUP_DIR"
umask 077
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="finsight_app_data_${STAMP}.tar.gz"
command -v docker >/dev/null 2>&1 || { echo "Docker is required for app_data volume backup." >&2; exit 127; }
docker compose run --rm --build --no-deps \
  -v "$BACKUP_DIR:/backup" --entrypoint sh api \
  -c "tar -czf '/backup/$NAME' -C /app/data . && tar -tzf '/backup/$NAME' >/dev/null"
python3 "$(dirname "$0")/validate_data_archive.py" "$BACKUP_DIR/$NAME"
(cd "$BACKUP_DIR" && sha256sum "$NAME" > "$NAME.sha256")
chmod 600 "$BACKUP_DIR/$NAME" "$BACKUP_DIR/$NAME.sha256"
echo "Shared application data volume archived: $BACKUP_DIR/$NAME"
echo "Verify: (cd '$BACKUP_DIR' && sha256sum -c '$NAME.sha256')"
