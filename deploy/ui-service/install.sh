#!/usr/bin/env bash
# Install the Synapse UI eglfs service and switch boot away from the compositor.
# Run with sudo:  sudo ./install.sh     (idempotent -- safe to re-run)
#
# After this, a reboot lands on: multi-user.target -> synapse-ui.service ->
# qt_main.py fullscreen on the DSI panel. No lightdm, no labwc, no wayvnc.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

install -m 0644 "$HERE/synapse-ui.service" /etc/systemd/system/synapse-ui.service
systemctl daemon-reload
systemctl enable synapse-ui.service

# Boot straight to the app: no display manager, no compositor.
systemctl disable lightdm.service
systemctl set-default multi-user.target

echo
echo "installed + enabled (not started -- lightdm may still hold the DRM master)."
echo "switch over NOW without a reboot:"
echo "  sudo systemctl stop lightdm && sudo systemctl start synapse-ui.service"
echo "check with:"
echo "  systemctl status synapse-ui.service"
echo "  journalctl -u synapse-ui.service -f"
echo "  touch /tmp/synapse-shot.trigger   # -> /tmp/synapse-shot.png (remote eyeball)"
echo
echo "revert to labwc/wayland boot:  sudo ./revert.sh"
