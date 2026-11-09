#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/backups" "$TMP/source_data" "$TMP/restored_data"
printf 'phase5-artifact-content\n' > "$TMP/source_data/demo-artifact.txt"
export FAKE_SOURCE_DIR="$TMP/source_data" FAKE_RESTORED_DIR="$TMP/restored_data"
export DOCKER_LOG="$TMP/docker.log"

cat > "$TMP/bin/docker" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$DOCKER_LOG"
[[ "$1" == "compose" ]] || exit 2
if [[ "$2" == "stop" ]]; then
  [[ "$3" == "api" && "$4" == "worker" ]]
  exit 0
fi
[[ "$2" == "run" ]]
volume=''
command_text=''
while (($#)); do
  case "$1" in
    -v) volume="$2"; shift 2 ;;
    -c) command_text="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[[ -n "$volume" && -n "$command_text" ]]
host_dir="${volume%%:/backup*}"
if [[ "$command_text" == *"tar -czf '/backup/"* ]]; then
  name="$(printf '%s' "$command_text" | sed -n "s/.*tar -czf '\/backup\/\([^']*\)'.*/\1/p")"
  [[ -n "$name" ]]
  tar -czf "$host_dir/$name" -C "$FAKE_SOURCE_DIR" .
elif [[ "$command_text" == *"tar -xzf '/backup/"* ]]; then
  name="$(printf '%s' "$command_text" | sed -n "s/.*tar -tzf '\/backup\/\([^']*\)'.*/\1/p")"
  [[ -n "$name" ]]
  tar -tzf "$host_dir/$name" >/dev/null
  tar -xzf "$host_dir/$name" -C "$FAKE_RESTORED_DIR"
else
  echo "Unexpected docker compose run command: $command_text" >&2
  exit 3
fi
FAKE
chmod +x "$TMP/bin/docker"
export PATH="$TMP/bin:$PATH" BACKUP_DIR="$TMP/backups"

# The restore command must refuse to run without explicit confirmation.
if BACKUP_FILE="$TMP/backups/not-created.tar.gz" "$ROOT/scripts/restore_data_volume.sh" >/dev/null 2>&1; then
  echo "Restore unexpectedly accepted without confirmation." >&2
  exit 1
fi

"$ROOT/scripts/backup_data_volume.sh" >/dev/null
BACKUP_FILE="$(find "$BACKUP_DIR" -maxdepth 1 -name '*.tar.gz' -print -quit)"
[[ -n "$BACKUP_FILE" ]]
BACKUP_FILE="$BACKUP_FILE" CONFIRM_RESTORE=YES "$ROOT/scripts/restore_data_volume.sh" >/dev/null
cmp "$TMP/source_data/demo-artifact.txt" "$TMP/restored_data/demo-artifact.txt"
grep -q 'compose stop api worker' "$DOCKER_LOG"
echo "app_data volume backup/restore archive round-trip passed with real tar and a mocked Docker volume mount."
