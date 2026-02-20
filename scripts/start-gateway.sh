#!/bin/bash
# OpenClaw Gateway launcher with optional 1Password secret injection.
#
# Setup:
#   1. Store your OP Service Account token in macOS Keychain:
#      security add-generic-password -s "op-service-account" -a "openclaw" -w "<token>" -U
#   2. Create ~/.openclaw/env with secret references (see 1Password docs)
#   3. Run this script directly or via LaunchAgent
#
# The script gracefully degrades:
#   - No Keychain token → tries $OP_SERVICE_ACCOUNT_TOKEN from environment
#   - No OP token at all → starts without 1Password (secrets must be in env)
#   - No env file → starts without op run wrapper

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# --- 1Password token ---
OP_TOKEN="$(security find-generic-password -s 'op-service-account' -a 'openclaw' -w 2>/dev/null || true)"
if [ -n "$OP_TOKEN" ]; then
  export OP_SERVICE_ACCOUNT_TOKEN="$OP_TOKEN"
  echo "[start-gateway] 🔑 OP token loaded from Keychain"
elif [ -n "${OP_SERVICE_ACCOUNT_TOKEN:-}" ]; then
  echo "[start-gateway] 🔑 OP token from environment"
else
  echo "[start-gateway] ⚠️  No OP_SERVICE_ACCOUNT_TOKEN found. 1Password secrets won't resolve."
fi

# --- PATH ---
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# --- Launch ---
ENV_FILE="$HOME/.openclaw/env"
if [ -f "$ENV_FILE" ] && command -v op &>/dev/null && [ -n "${OP_SERVICE_ACCOUNT_TOKEN:-}" ]; then
  echo "[start-gateway] 🚀 Starting with op run (env: $ENV_FILE)"
  exec op run --env-file="$ENV_FILE" -- \
    node "$REPO_DIR/dist/index.js" gateway --port "${OPENCLAW_GATEWAY_PORT:-18789}"
else
  [ ! -f "$ENV_FILE" ] && echo "[start-gateway] ⚠️  No env file at $ENV_FILE"
  [ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" ] && echo "[start-gateway] ⚠️  No OP token, skipping op run"
  echo "[start-gateway] 🚀 Starting without op run"
  exec node "$REPO_DIR/dist/index.js" gateway --port "${OPENCLAW_GATEWAY_PORT:-18789}"
fi
