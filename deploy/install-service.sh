#!/usr/bin/env bash
# Generate and install the AI-Mirror systemd units for THIS user/machine.
# Fills the template placeholders from whoami/pwd so no personal paths
# are ever committed to git. Run from anywhere in the checkout:
#
#   ./deploy/install-service.sh            install both, boot into visual
#   ./deploy/install-service.sh pygame     install both, boot into pygame
#
# Both units are always installed; exactly one is enabled. Switch later
# without reinstalling:  ./deploy/mirror-mode.sh visual|pygame
#
set -euo pipefail

MODE="${1:-visual}"
case "$MODE" in
    visual|pygame) ;;
    *) echo "unknown mode: $MODE  (expected visual or pygame)" >&2; exit 2 ;;
esac

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

echo "Installing both mirror units with:"
echo "  User           = $USER_NAME"
echo "  WorkingDir     = $PROJECT_DIR"
echo "  Python         = $PYTHON"
echo "  XDG_RUNTIME_DIR= /run/user/$UID_NUM"
echo "  Boot mode      = $MODE"

install_unit() {
    local name="$1"
    local template="$SCRIPT_DIR/$name.service"
    if [ ! -f "$template" ]; then
        echo "ERROR: template not found at $template" >&2
        exit 1
    fi
    # Substitute placeholders into a temp unit, then install it
    local tmp
    tmp="$(mktemp)"
    sed \
        -e "s|__USER__|$USER_NAME|g" \
        -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
        -e "s|__PYTHON__|$PYTHON|g" \
        -e "s|__HOME__|$HOME_DIR|g" \
        -e "s|__UID__|$UID_NUM|g" \
        "$template" > "$tmp"
    sudo cp "$tmp" "/etc/systemd/system/$name.service"
    rm -f "$tmp"
    echo "  installed /etc/systemd/system/$name.service"
}

install_unit ai-mirror
install_unit ai-mirror-visual

# The visual unit runs run.sh directly, so it has to be executable in
# the checkout. A clone onto a filesystem that drops the mode bit would
# otherwise fail with a bare 203/EXEC and no clue why.
chmod +x "$PROJECT_DIR/prototype/visual-gate/run.sh" \
         "$SCRIPT_DIR/mirror-mode.sh" 2>/dev/null || true

sudo systemctl daemon-reload

# One place decides which unit is enabled, so the two scripts cannot
# disagree about what "installed and enabled" means.
exec "$SCRIPT_DIR/mirror-mode.sh" "$MODE"
