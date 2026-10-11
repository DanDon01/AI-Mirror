#!/usr/bin/env bash
# Choose what the mirror boots into.
#
#   ./deploy/mirror-mode.sh            report the current mode
#   ./deploy/mirror-mode.sh visual     the Chromium visual gate
#   ./deploy/mirror-mode.sh pygame     AI-Mirror.py
#
# Exactly one is ever enabled. Both drive the same display, so leaving
# both enabled means whichever lost the race sits behind the other
# holding a screen it cannot draw on - and on the next boot which one
# you get is a coin toss. The units carry Conflicts= as well, but this
# script is what makes the intent explicit.
#
# Both units must be installed first, by ./deploy/install-service.sh
set -euo pipefail

PYGAME_UNIT=ai-mirror
VISUAL_UNIT=ai-mirror-visual

installed() {
    [ -f "/etc/systemd/system/$1.service" ]
}

enabled_unit() {
    for u in "$VISUAL_UNIT" "$PYGAME_UNIT"; do
        if systemctl is-enabled "$u" >/dev/null 2>&1; then
            echo "$u"
            return
        fi
    done
    echo ""
}

report() {
    local active
    active="$(enabled_unit)"
    if [ -z "$active" ]; then
        echo "No mirror unit is enabled."
        echo "Install them with: ./deploy/install-service.sh"
        return
    fi
    case "$active" in
        "$VISUAL_UNIT") echo "Mode: visual  (Chromium, prototype/visual-gate)" ;;
        "$PYGAME_UNIT") echo "Mode: pygame  (AI-Mirror.py)" ;;
    esac
    systemctl --no-pager --lines=0 status "$active" | head -3 || true
}

switch_to() {
    local want="$1" other="$2" label="$3"

    if ! installed "$want"; then
        echo "ERROR: $want.service is not installed." >&2
        echo "Run ./deploy/install-service.sh first." >&2
        exit 1
    fi

    # Stop and disable the other one before enabling this one, so there
    # is never a moment where both are enabled.
    if installed "$other"; then
        sudo systemctl disable --now "$other" >/dev/null 2>&1 || true
    fi
    sudo systemctl enable --now "$want"

    sleep 2
    echo
    echo "Mirror is now in $label mode."
    systemctl --no-pager --lines=8 status "$want" || true
    echo
    echo "Logs: journalctl -u $want -f"
}

case "${1:-}" in
    "")       report ;;
    visual)   switch_to "$VISUAL_UNIT" "$PYGAME_UNIT" "visual" ;;
    pygame)   switch_to "$PYGAME_UNIT" "$VISUAL_UNIT" "pygame" ;;
    -h|--help)
        echo "usage: ./deploy/mirror-mode.sh [visual|pygame]"
        ;;
    *)
        echo "unknown mode: $1  (expected visual or pygame)" >&2
        exit 2
        ;;
esac
