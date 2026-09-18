#!/usr/bin/env bash
# Launch the visual gate on the Pi.
#
# Starts a local server, waits until it actually answers, opens Chromium
# on it, and tears everything down on exit. No URL to mistype, and no
# ambiguity about whether the server came up.
#
#   ./run.sh              full screen on the mirror
#   ./run.sh --fit        scaled to the window, for a normal monitor
#   ./run.sh --windowed   windowed rather than kiosk
#
set -euo pipefail
cd "$(dirname "$0")"

PARAMS="hud=1"
KIOSK="--kiosk"
for arg in "$@"; do
  case "$arg" in
    --fit)      PARAMS="$PARAMS&fit=1" ;;
    --windowed) KIOSK="--window-size=720,1280" ;;
    --plain)    PARAMS="${PARAMS/hud=1/}" ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# An ephemeral port, so a server left running from an earlier attempt
# cannot shadow this one and hand the browser a dead connection.
PORT="$(python3 - <<'PY'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()
PY
)"

BROWSER=""
for candidate in chromium-browser chromium google-chrome; do
  if command -v "$candidate" >/dev/null 2>&1; then BROWSER="$candidate"; break; fi
done
if [ -z "$BROWSER" ]; then
  echo "No Chromium found. sudo apt install chromium-browser" >&2
  exit 1
fi

python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

URL="http://127.0.0.1:$PORT/index.html?$PARAMS"
for _ in $(seq 1 40); do
  if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/index.html" 2>/dev/null; then break; fi
  sleep 0.25
done

echo "serving on $PORT"
echo "opening  $URL"
"$BROWSER" $KIOSK \
  --noerrdialogs --disable-infobars --no-first-run \
  --ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy \
  --user-data-dir=/tmp/visual-gate-profile \
  "$URL"
