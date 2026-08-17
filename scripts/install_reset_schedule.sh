#!/bin/bash
# Install (or update) a launchd job that resets Ante's Discord session nightly.
#
#   ./scripts/install_reset_schedule.sh [HOUR] [MINUTE]      default: 04:00
#   ./scripts/install_reset_schedule.sh --uninstall
#
# Why launchd rather than OpenClaw's own scheduler:
#
#   * `openclaw cron` needs operator.write scope on the Gateway; this CLI is
#     paired read-only, so every cron.* RPC is refused. launchd needs nothing.
#   * A cron job's --message "/new" would not reset anything anyway -- /new is
#     interpreted by the chat surface, not by the agent, so it arrives as plain
#     text (verified: the agent replies that it cannot do that).
#   * launchd's StartCalendarInterval uses *system local time*, so this follows
#     the machine across a move. An OpenClaw cron job pins an IANA zone and
#     would fire three hours off after relocating -- the same trap that put
#     every created calendar event in the wrong hour.
#
# If the machine is asleep at the scheduled time launchd runs the job on wake,
# which is fine: the goal is "reset once a day while idle", not a precise hour.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="ai.ante.session-reset"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/.openclaw/logs/session-reset.log"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed $LABEL"
  exit 0
fi

HOUR="${1:-4}"
MINUTE="${2:-0}"

mkdir -p "$(dirname "$LOG")" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
      <string>$ROOT/scripts/run_reset_session.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key><integer>$HOUR</integer>
      <key>Minute</key><integer>$MINUTE</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG</string>
    <key>StandardErrorPath</key>
    <string>$LOG</string>
    <key>RunAtLoad</key>
    <false/>
  </dict>
</plist>
EOF

plutil -lint "$PLIST" >/dev/null

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

printf 'Installed %s — runs daily at %02d:%02d local time.\n' "$LABEL" "$HOUR" "$MINUTE"
echo "Log:     $LOG"
echo "Check:   launchctl list | grep ${LABEL}"
echo "Run now: launchctl kickstart -k gui/\$(id -u)/$LABEL"
echo "Remove:  ./scripts/install_reset_schedule.sh --uninstall"
