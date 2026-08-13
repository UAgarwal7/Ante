#!/bin/bash
# Snapshot the OpenClaw workspace "brain" files into the repo.
#
# These live in ~/.openclaw/workspace/ and are the one part of Ante with no
# redundancy anywhere: hand-written identity, tone, and user context that cannot
# be re-derived from the repo the way the scripts can. `openclaw reset` would
# delete them permanently.
#
# The snapshot lands in workspace/, which is GITIGNORED -- these files can carry
# personal detail and this repo is public. That means this protects against
# losing ~/.openclaw (reset, bad upgrade, fat-fingered rm); it does NOT protect
# against losing the machine. For that, copy workspace/ somewhere off-disk.
#
# Skill files are deliberately not included -- they already live in skills/ and
# are tracked properly.
#
# Re-run any time the workspace files change. It overwrites the snapshot and
# rewrites the manifest, so the manifest date is always the snapshot's real age.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$HOME/.openclaw/workspace"
DEST="$ROOT/workspace"

if [ ! -d "$SRC" ]; then
  echo "No workspace at $SRC — nothing to back up." >&2
  exit 1
fi

mkdir -p "$DEST"

count=0
for f in "$SRC"/*.md; do
  [ -e "$f" ] || continue
  cp -p "$f" "$DEST/"
  count=$((count + 1))
done

{
  echo "# Workspace snapshot"
  echo
  echo "Taken: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Source: $SRC"
  echo
  echo "These are copies. The live files OpenClaw reads are the ones in \$SRC."
  echo "Editing anything here changes nothing -- edit the source, then re-run"
  echo "scripts/backup_workspace.sh."
  echo
  echo "## Files"
  echo
  for f in "$DEST"/*.md; do
    b="$(basename "$f")"
    [ "$b" = "_MANIFEST.md" ] && continue
    printf -- "- %s (%s bytes)\n" "$b" "$(wc -c < "$f" | tr -d ' ')"
  done
  echo
  echo "## Restore"
  echo
  echo '```bash'
  echo "cp \"$DEST\"/*.md \"$SRC\"/"
  echo '```'
} > "$DEST/_MANIFEST.md"

echo "Backed up $count file(s) to $DEST"
echo "Reminder: workspace/ is gitignored — this survives an openclaw reset, not a lost disk."
