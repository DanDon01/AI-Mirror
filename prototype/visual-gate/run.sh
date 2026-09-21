#!/usr/bin/env bash
# Launch the visual gate on the Pi.
#
# Starts a local server, waits until it actually answers, opens Chromium
# on it, and tears everything down on exit. No URL to mistype, and no
# ambiguity about whether the server came up.
#
#   ./run.sh              full screen on the mirror, backed by live data
#   ./run.sh --fit        scaled to the window, for a normal monitor
#   ./run.sh --windowed   windowed rather than kiosk
#
set -euo pipefail
cd "$(dirname "$0")"

HUD=1
FIXTURE=0
# Fit by default: the plate is authored at 1440x2560 and the display may
# not be. At native size this is a no-op; anywhere else it removes the
# need to reach for the browser zoom.
FIT=1
KIOSK="--kiosk"
for arg in "$@"; do
  case "$arg" in
    --fit)      FIT=1 ;;
    --native)   FIT=0 ;;
    # A window is never 1440x2560, so windowed implies fit; without it
    # you get the top-left corner of the plate and nothing else.
    --windowed) KIOSK="--window-size=760,1350"; FIT=1 ;;
    --plain)    HUD=0 ;;
    --fixture)  FIXTURE=1 ;;
    -h|--help)
      echo "usage: ./run.sh [--native] [--windowed] [--plain] [--fixture]"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# Assembled from parts so --plain cannot leave a bare "?" or a stray "&".
QUERY=""
[ "$HUD" = "1" ] && QUERY="hud=1"
[ "$FIT" = "1" ] && QUERY="${QUERY:+$QUERY&}fit=1"

# Check the browser first: it is the likelier thing to be missing, and
# failing here saves starting a server nothing will connect to.
BROWSER=""
for candidate in chromium-browser chromium google-chrome; do
  if command -v "$candidate" >/dev/null 2>&1; then BROWSER="$candidate"; break; fi
done
if [ -z "$BROWSER" ]; then
  echo "No Chromium found. sudo apt install chromium-browser" >&2
  exit 1
fi
PYTHON=""
for candidate in "../../venv/bin/python" "../../.venv/bin/python" python3; do
  if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$candidate"; break
  fi
done
[ -n "$PYTHON" ] || { echo "Python not found; it serves the prototype" >&2; exit 1; }

# Keep the visual gate on the same stable LAN port as the old web panel,
# so phones and other browsers can reach it without an SSH tunnel.
PORT=8780
BIND=0.0.0.0

SERVER_ARGS=(serve.py --port "$PORT" --bind "$BIND")
[ "$FIXTURE" = "1" ] && SERVER_ARGS+=(--fixture)
"$PYTHON" "${SERVER_ARGS[@]}" &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

URL="http://127.0.0.1:$PORT/index.html${QUERY:+?$QUERY}"
# Wait on the server with python3 rather than curl: python3 is already a
# hard requirement here, and if curl were missing this loop would fail
# silently forty times and then open the browser on nothing anyway.
"$PYTHON" - "$PORT" <<'PY' || { echo "server did not come up" >&2; exit 1; }
import sys, time, urllib.request
url = f"http://127.0.0.1:{sys.argv[1]}/index.html"
for _ in range(40):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            if r.status == 200:
                sys.exit(0)
    except Exception:
        time.sleep(0.25)
sys.exit(1)
PY

echo "serving on $PORT"
echo "opening  $URL"
"$BROWSER" $KIOSK \
  --noerrdialogs --disable-infobars --no-first-run \
  --ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy \
  --user-data-dir=/tmp/visual-gate-profile \
  "$URL"
