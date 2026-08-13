#!/bin/bash
# Copy the repo's skill files into the OpenClaw workspace.
#
# The repo is the source of truth; the workspace gets real copies.
#
# Symlinking looks tidier and was tried first -- OpenClaw rejects it:
#
#   Skipping escaped skill path outside its configured root:
#   reason=symlink-escape requested=.../skills/gcalendar resolved=~/Ante/skills/gcalendar
#
# It refuses to follow a symlink that resolves outside the skills root, which is
# a sane sandboxing rule. The failure is a warning on stderr, not an error, so
# the agent simply comes up with no skills at all and nothing obviously wrong.
#
# So: copies, and this script is how they stay in sync. Edit skills/ in the
# repo, run this, restart the gateway.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$HOME/.openclaw/workspace/skills"

mkdir -p "$DEST"

count=0
for dir in "$ROOT"/skills/*/; do
  [ -f "$dir/SKILL.md" ] || continue
  name="$(basename "$dir")"
  # Replace a symlink from the old approach with a real directory.
  [ -L "$DEST/$name" ] && rm "$DEST/$name"
  mkdir -p "$DEST/$name"
  cp -p "$dir/SKILL.md" "$DEST/$name/SKILL.md"
  echo "  synced $name"
  count=$((count + 1))
done

echo "Synced $count skill(s) to $DEST"
echo "Restart the gateway for the agent to pick them up:"
echo "  launchctl kickstart -k gui/\$(id -u)/ai.openclaw.gateway"
