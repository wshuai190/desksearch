#!/bin/sh
# Docker entrypoint for DeskSearch.
# Writes a minimal config using environment variables, then delegates to the CLI.

set -e

DATA_DIR="${DESKSEARCH_DATA_DIR:-/data}"
HOST="${DESKSEARCH_HOST:-0.0.0.0}"
PORT="${DESKSEARCH_PORT:-3777}"

mkdir -p "$DATA_DIR"

# Write config if it doesn't already exist
CONFIG_FILE="$DATA_DIR/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
  cat > "$CONFIG_FILE" <<EOF
{
  "data_dir": "$DATA_DIR",
  "host": "$HOST",
  "port": $PORT,
  "index_paths": []
}
EOF
  echo "[desksearch] Created config at $CONFIG_FILE"
fi

echo "[desksearch] Data dir : $DATA_DIR"
echo "[desksearch] Server   : http://$HOST:$PORT"

# If first argument is 'serve', launch in no-browser mode
if [ "$1" = "serve" ]; then
  exec desksearch serve --host "$HOST" --port "$PORT" --no-browser
else
  exec desksearch "$@"
fi
