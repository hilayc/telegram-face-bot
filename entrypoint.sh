#!/bin/sh
set -e

# If TELEGRAM_BOT_API_TOKEN is not set, try to read it from HA add-on options
if [ -z "${TELEGRAM_BOT_API_TOKEN:-}" ]; then
  if [ -f /data/options.json ]; then
    TOKEN=$(jq -r '(.TELEGRAM_BOT_API_TOKEN // .bot_token // empty)' /data/options.json 2>/dev/null || true)
    if [ -n "$TOKEN" ]; then
      export TELEGRAM_BOT_API_TOKEN="$TOKEN"
      echo "[entrypoint] Token loaded from /data/options.json"
    else
      echo "[entrypoint] No token found in /data/options.json"
    fi
  else
    echo "[entrypoint] /data/options.json not found"
  fi
fi

if [ -z "${TELEGRAM_BOT_API_TOKEN:-}" ]; then
  echo "[entrypoint] ERROR: TELEGRAM_BOT_API_TOKEN is not set. Exiting." >&2
  exit 1
fi

exec python /app/main.py


