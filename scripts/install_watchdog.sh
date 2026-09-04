#!/bin/bash
# Install (or remove) the Discord channel watchdog.
#
#   ./scripts/install_watchdog.sh [INTERVAL_SECONDS]   default: 900 (15 min)
#   ./scripts/install_watchdog.sh --uninstall
#
# StartInterval rather than StartCalendarInterval: this is a poll, not an
# appointment. launchd runs it on wake if the machine slept through one, which
# is exactly when the channel is most likely to be dead.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="ai.ante.channel-watchdog"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/.openclaw/logs/channel-watchdog.err.log"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed $LABEL"
  exit 0
fi

INTERVAL="${1:-900}"
mkdir -p "$(dirname "$LOG")" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
      <string>$ROOT/scripts/watch_channel.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>$INTERVAL</integer>
    <key>StandardOutPath</key>
    <string>$LOG</string>
    <key>StandardErrorPath</key>
    <string>$LOG</string>
    <key>RunAtLoad</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
  </dict>
</plist>
PLIST_EOF

plutil -lint "$PLIST" >/dev/null
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Installed $LABEL — checks every ${INTERVAL}s."
echo "Log:      \$HOME/.openclaw/logs/channel-watchdog.log   (quiet when healthy)"
echo "Check:    launchctl list | grep $LABEL"
echo "Run now:  launchctl kickstart -k gui/\$(id -u)/$LABEL"
echo "Remove:   ./scripts/install_watchdog.sh --uninstall"
