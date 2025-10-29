#!/bin/sh
set -e

# If TELEGRAM_BOT_API_TOKEN is not set, try to read it from HA add-on options
if [ -z "${TELEGRAM_BOT_API_TOKEN:-}" ] && [ -f /data/options.json ]; then
  TOKEN=$(jq -r '(.TELEGRAM_BOT_API_TOKEN // .bot_token // empty)' /data/options.json 2>/dev/null || true)
  if [ -n "$TOKEN" ]; then
    export TELEGRAM_BOT_API_TOKEN="$TOKEN"
  fi
fi

exec python /app/main.py


