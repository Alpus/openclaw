#!/usr/bin/env bash
# verify-identity.sh — Verify a sender's identity against 1Password stored owner data
#
# Usage:
#   verify-identity.sh --channel telegram --id 119111425
#   verify-identity.sh --channel telegram --id 119111425 --field "Telegram ID Sasha"
#   verify-identity.sh --channel telegram --id 119111425 --vault Rynn --item Contacts
#
# Environment variables (override defaults):
#   OP_VAULT  — 1Password vault name (default: Rynn)
#   OP_ITEM   — 1Password item name (default: Contacts)
#
# Returns:
#   exit 0 + "MATCH"    — sender matches verified owner
#   exit 1 + "MISMATCH" — sender does NOT match (do NOT reveal why)
#   exit 2 + "ERROR"    — could not verify (1Password unavailable, etc.)
#
# Requires: op CLI authenticated (via OP_SERVICE_ACCOUNT_TOKEN or interactive session)

set -euo pipefail

CHANNEL=""
SENDER_ID=""
VAULT="${OP_VAULT:-}"
ITEM="${OP_ITEM:-}"
FIELD=""

usage() {
  echo "Usage: $0 --channel <channel> --id <sender_id> [--vault <vault>] [--item <item>] [--field <field>]"
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --channel) CHANNEL="$2"; shift 2 ;;
    --id)      SENDER_ID="$2"; shift 2 ;;
    --vault)   VAULT="$2"; shift 2 ;;
    --item)    ITEM="$2"; shift 2 ;;
    --field)   FIELD="$2"; shift 2 ;;
    *)         usage ;;
  esac
done

[[ -z "$CHANNEL" || -z "$SENDER_ID" ]] && usage
[[ -z "$VAULT" ]] && { echo "ERROR: vault not specified (use --vault or OP_VAULT)"; exit 2; }
[[ -z "$ITEM" ]] && { echo "ERROR: item not specified (use --item or OP_ITEM)"; exit 2; }

# Map channel to 1Password field name if not specified
# The exact field name depends on how the user stored it — pass --field for custom names
if [[ -z "$FIELD" ]]; then
  case "$CHANNEL" in
    telegram)  FIELD="Telegram ID" ;;
    whatsapp)  FIELD="WhatsApp ID" ;;
    discord)   FIELD="Discord ID" ;;
    signal)    FIELD="Signal ID" ;;
    imessage)  FIELD="iMessage ID" ;;
    *)         echo "ERROR: unknown channel '$CHANNEL', specify --field"; exit 2 ;;
  esac
fi

# Fetch the verified ID from 1Password
VERIFIED_ID=$(op item get "$ITEM" --vault "$VAULT" --fields label="$FIELD" --reveal 2>/dev/null) || {
  echo "ERROR: cannot read field '$FIELD' from 1Password (vault: $VAULT, item: $ITEM)"
  exit 2
}

if [[ -z "$VERIFIED_ID" ]]; then
  echo "ERROR: field '$FIELD' is empty in 1Password"
  exit 2
fi

# Compare (case-insensitive, trimmed)
VERIFIED_ID=$(echo "$VERIFIED_ID" | tr -d '[:space:]')
SENDER_ID=$(echo "$SENDER_ID" | tr -d '[:space:]')

if [[ "$(echo "$VERIFIED_ID" | tr '[:upper:]' '[:lower:]')" == "$(echo "$SENDER_ID" | tr '[:upper:]' '[:lower:]')" ]]; then
  echo "MATCH"
  exit 0
else
  echo "MISMATCH"
  exit 1
fi
