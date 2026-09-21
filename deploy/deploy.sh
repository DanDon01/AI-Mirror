#!/usr/bin/env bash
# Pull, verify, and restart AI-Mirror on the Pi.
# Usage (on the Pi):  ./deploy/deploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== Pulling latest =="
git pull --ff-only

echo "== Installing dependencies =="
PIP="pip3"
if [ -x "venv/bin/pip" ]; then
    PIP="venv/bin/pip"
fi
"$PIP" install -q -r requirements.txt

echo "== Smoke test =="
PY="python3"
if [ -x "venv/bin/python" ]; then
    PY="venv/bin/python"
fi
"$PY" smoke_test.py

echo "== Restarting service =="
# Restart whichever mode the mirror is actually in. Hardcoding the
# Pygame unit here meant a deploy in visual mode restarted a unit that
# was not running and left the one that was on the old code.
ACTIVE=""
for UNIT in ai-mirror-visual ai-mirror; do
    if systemctl is-enabled "$UNIT" >/dev/null 2>&1; then ACTIVE="$UNIT"; break; fi
done

if [ -n "$ACTIVE" ]; then
    sudo systemctl restart "$ACTIVE"
    sleep 3
    systemctl --no-pager --lines=5 status "$ACTIVE"
else
    echo "No mirror unit is enabled. Install with:"
    echo "  ./deploy/install-service.sh"
    echo "or start one by hand:"
    echo "  $PY AI-Mirror.py"
    echo "  ./prototype/visual-gate/run.sh"
fi

echo "Deploy complete."
