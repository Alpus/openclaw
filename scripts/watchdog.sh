#!/bin/bash
# OpenClaw Watchdog — checks gateway health, auto-rollback config if broken.
# Designed to run every 60s via LaunchAgent.
#
# Setup: Create a LaunchAgent with StartInterval=60 pointing to this script.

OPENCLAW_DIR="$HOME/.openclaw"
LOG="$OPENCLAW_DIR/logs/watchdog.log"
LABEL="${OPENCLAW_LAUNCHD_LABEL:-ai.openclaw.gateway}"
PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
MAX_LOG_LINES=500
CONFIG="$OPENCLAW_DIR/openclaw.json"
BACKUP="$CONFIG.bak"
FAIL_COUNT_FILE="$OPENCLAW_DIR/logs/watchdog-fails"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"
}

# Ensure log dir exists
mkdir -p "$(dirname "$LOG")"

# Trim log if too long
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt "$MAX_LOG_LINES" ]; then
  tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

# Health check
if curl -sf --max-time 5 "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then
  rm -f "$FAIL_COUNT_FILE"
  exit 0
fi

# Track consecutive failures
FAILS=0
if [ -f "$FAIL_COUNT_FILE" ]; then
  FAILS=$(cat "$FAIL_COUNT_FILE" 2>/dev/null || echo 0)
fi
FAILS=$((FAILS + 1))
echo "$FAILS" > "$FAIL_COUNT_FILE"

log "⚠️  Gateway not responding on port $PORT (fail #$FAILS)"

# After 2 consecutive failures: try config rollback
if [ "$FAILS" -ge 2 ] && [ -f "$BACKUP" ]; then
  log "🔄 Config rollback: restoring $BACKUP → $CONFIG"
  cp "$BACKUP" "$CONFIG"
fi

# Check if process exists at all
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
if ! launchctl list "$LABEL" > /dev/null 2>&1; then
  log "Process not found in launchctl. Bootstrapping..."
  launchctl load "$PLIST" 2>> "$LOG"
  sleep 5
fi

# Kickstart the service
log "Kickstarting $LABEL..."
launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>> "$LOG"

# Wait and verify
sleep 10
if curl -sf --max-time 5 "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then
  log "✅ Gateway recovered!"
  rm -f "$FAIL_COUNT_FILE"
else
  log "❌ Gateway still not responding after recovery attempt (fail #$FAILS)"
fi
