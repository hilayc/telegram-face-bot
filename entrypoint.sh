#!/bin/sh
set -e

# Generic loader: set an env var from /data/options.json using one or more keys
load_env_from_options() {
  var_name="$1"; shift
  # If already set, respect existing value
  eval "__cur_val=\${$var_name:-}"
  if [ -n "$__cur_val" ]; then
    return 0
  fi
  if [ ! -f /data/options.json ]; then
    echo "[entrypoint] /data/options.json not found"
    return 0
  fi
  # Build a jq expression like (.KEY1 // .KEY2 // empty)
  # If no keys provided, default to the same name as the env var
  if [ "$#" -eq 0 ]; then
    keys="$var_name"
  else
    keys="$*"
  fi
  jq_expr=""
  for key in $keys; do
    if [ -z "$jq_expr" ]; then
      jq_expr="(.${key}"
    else
      jq_expr="${jq_expr} // .${key}"
    fi
  done
  jq_expr="${jq_expr} // empty)"
  val=$(jq -r "$jq_expr" /data/options.json 2>/dev/null || true)
  if [ -n "$val" ] && [ "$val" != "null" ]; then
    # POSIX-safe assignment/export for dynamic var name
    eval "$var_name=\"\$val\""
    export "$var_name"
    echo "[entrypoint] Loaded $var_name from /data/options.json"
  fi
}

# Load commonly used variables from options.json if not already set
load_env_from_options TELEGRAM_BOT_API_TOKEN
load_env_from_options FACE_MATCH_TOLERANCE
load_env_from_options FACE_DETECTION_MODEL
load_env_from_options FACE_TRAIN_JITTERS
load_env_from_options FACE_FIND_JITTERS
load_env_from_options FACE_MIN_CONFIDENCE_MARGIN
load_env_from_options FACE_USE_MEAN_ENCODING

exec python /app/main.py


