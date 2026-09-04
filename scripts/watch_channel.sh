#!/bin/bash
# Restart the OpenClaw gateway when the Discord channel has given up.
#
# Why this is needed
# ------------------
# Discord's client retries a lost connection with backoff, but the budget is
# finite (10 auto-restart attempts) and it does NOT refill when connectivity
# returns. So any network interruption longer than the backoff window -- wifi
# dropping, switching to a hotspot, a sleeping laptop -- leaves the channel
# permanently `stopped` on a machine whose internet is now fine. Observed
# 2026-09-04: wifi went down at 00:32, retries exhausted by 00:38, and Ante was
# still offline at 10:15 with a working connection.
#
# What it does NOT do
# -------------------
# It never restarts while the network is actually down. Kickstarting then would
# burn a fresh retry budget against a nameserver that cannot answer, which is
# how you turn one outage into a loop. Network first, gateway second.
set -euo pipefail

LABEL="ai.openclaw.gateway"
LOG="$HOME/.openclaw/logs/channel-watchdog.log"
STAMP="$HOME/.openclaw/logs/.watchdog-last-restart"
MIN_GAP=600          # seconds between restarts; a restart needs ~30s to settle

log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >> "$LOG"; }

status="$(openclaw channels status 2>&1 | grep -i '^- Discord' || true)"

if [ -z "$status" ]; then
  log "no discord line in channel status — gateway may be down"
  exit 0
fi

# Healthy: nothing to do. Keep the log quiet so real events stay visible.
if grep -q 'running, connected' <<<"$status"; then
  exit 0
fi

# Network first. If DNS or Discord is unreachable, a restart cannot help.
if ! curl -sf -o /dev/null --max-time 8 https://discord.com/api/v10/gateway; then
  log "channel unhealthy but Discord unreachable — network is down, not restarting"
  log "  status: $status"
  exit 0
fi

# Rate limit, so a channel that is failing for some other reason does not get
# kickstarted every interval forever.
now=$(date +%s)
if [ -f "$STAMP" ]; then
  last=$(cat "$STAMP" 2>/dev/null || echo 0)
  if [ $(( now - last )) -lt "$MIN_GAP" ]; then
    log "unhealthy but restarted $(( now - last ))s ago — waiting"
    exit 0
  fi
fi

log "unhealthy with working network — restarting gateway"
log "  status: $status"
echo "$now" > "$STAMP"

launchctl kickstart -k "gui/$(id -u)/$LABEL"
sleep 25

after="$(openclaw channels status 2>&1 | grep -i '^- Discord' || true)"
if grep -q 'running, connected' <<<"$after"; then
  log "recovered: $after"
else
  log "STILL UNHEALTHY after restart: $after"
fi
