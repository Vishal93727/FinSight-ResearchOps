#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Workspace: $ROOT"
echo "Backend files:"
find "$ROOT/backend" -maxdepth 3 -type f | sort
echo
echo "Cloned references:"
if [[ -d "$ROOT/references/cloned" ]]; then find "$ROOT/references/cloned" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort; else echo "None cloned yet"; fi
echo
echo "Progress checkpoint:"
sed -n '1,100p' "$ROOT/PROJECT_PROGRESS.md"
