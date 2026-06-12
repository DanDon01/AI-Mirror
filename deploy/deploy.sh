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
if systemctl is-enabled ai-mirror >/dev/null 2>&1; then
    sudo systemctl restart ai-mirror
    sleep 3
    systemctl --no-pager --lines=5 status ai-mirror
else
    echo "ai-mirror service not installed; start manually with:"
    echo "  $PY AI-Mirror.py"
fi

echo "Deploy complete."
