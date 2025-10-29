#!/bin/sh
set -e

# Generic loader: set an env var from /data/options.json using one or more keys
load_env_from_options() {
  var_name="$1"; shift
  # If already set, respect existing value
  if [ -n "${!var_name:-}" ]; then
    return 0
  fi
  if [ ! -f /data/options.json ]; then
    echo "[entrypoint] /data/options.json not found"
    return 0
  fi
  # Build a jq expression like (.KEY1 // .KEY2 // empty)
  # If no keys provided, default to the same name as the env var
  if [ "$#" -eq 0 ]; then
    set -- "$var_name"
  fi
  jq_expr=""
  for key in "$@"; do
    if [ -z "$jq_expr" ]; then
      jq_expr="(.${key}"
    else
      jq_expr="${jq_expr} // .${key}"
    fi
  done
  jq_expr="${jq_expr} // empty)"
  val=$(jq -r "$jq_expr" /data/options.json 2>/dev/null || true)
  if [ -n "$val" ] && [ "$val" != "null" ]; then
    export "$var_name"="$val"
    echo "[entrypoint] Loaded $var_name from /data/options.json"
  fi
}

# Load commonly used variables from options.json if not already set
load_env_from_options TELEGRAM_BOT_API_TOKEN
load_env_from_options FACE_MATCH_TOLERANCE
load_env_from_options FACE_DETECTION_MODEL

if [ -z "${TELEGRAM_BOT_API_TOKEN:-}" ]; then
  echo "[entrypoint] ERROR: TELEGRAM_BOT_API_TOKEN is not set. Exiting." >&2
  exit 1
fi

if [ -z "${FACE_MATCH_TOLERANCE:-}" ]; then
  echo "[entrypoint] ERROR: FACE_MATCH_TOLERANCE is not set. Exiting." >&2
  exit 1
fi

if [ -z "${FACE_DETECTION_MODEL:-}" ]; then
  echo "[entrypoint] ERROR: FACE_DETECTION_MODEL is not set. Exiting." >&2
  exit 1
fi

exec python /app/main.py


