#!/bin/bash
# Resolve the repo root from this script's own location -- no hardcoded paths,
# so the repo works from any checkout directory.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/venv/bin/python3" "scripts/gcalendar.py" "$@"
