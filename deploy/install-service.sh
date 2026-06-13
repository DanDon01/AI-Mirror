#!/usr/bin/env bash
# Generate and install the AI-Mirror systemd unit for THIS user/machine.
# Fills the template placeholders from whoami/pwd so no personal paths
# are ever committed to git. Run from anywhere in the checkout:
#
#   ./deploy/install-service.sh
#
set -euo pipefail

# Resolve the project directory (parent of this script's dir)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

USER_NAME="$(whoami)"
HOME_DIR="$HOME"
UID_NUM="$(id -u)"

# Prefer the project venv python, else the current python3
if [ -x "$PROJECT_DIR/venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/venv/bin/python"
else
    PYTHON="$(command -v python3)"
    echo "WARN: no venv at $PROJECT_DIR/venv - using system $PYTHON"
fi

TEMPLATE="$SCRIPT_DIR/ai-mirror.service"
if [ ! -f "$TEMPLATE" ]; then
    echo "ERROR: template not found at $TEMPLATE" >&2
    exit 1
fi

echo "Installing ai-mirror.service with:"
echo "  User           = $USER_NAME"
echo "  WorkingDir     = $PROJECT_DIR"
echo "  Python         = $PYTHON"
echo "  XDG_RUNTIME_DIR= /run/user/$UID_NUM"

# Substitute placeholders into a temp unit, then install it
TMP_UNIT="$(mktemp)"
sed \
    -e "s|__USER__|$USER_NAME|g" \
    -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__HOME__|$HOME_DIR|g" \
    -e "s|__UID__|$UID_NUM|g" \
    "$TEMPLATE" > "$TMP_UNIT"

sudo cp "$TMP_UNIT" /etc/systemd/system/ai-mirror.service
rm -f "$TMP_UNIT"

sudo systemctl daemon-reload
sudo systemctl enable ai-mirror
sudo systemctl restart ai-mirror

sleep 2
echo
sudo systemctl --no-pager --lines=10 status ai-mirror || true
echo
echo "Follow logs with:  journalctl -u ai-mirror -f"
