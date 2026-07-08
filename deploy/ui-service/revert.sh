#!/usr/bin/env bash
# Undo install.sh: back to the lightdm -> labwc (Wayland) boot.
# Run with sudo:  sudo ./revert.sh
# NOTE: the labwc autostart no longer launches the app (removed when the
# service took over) -- under labwc, start it by hand: ~/run_synapsepy.sh
set -euo pipefail

systemctl disable --now synapse-ui.service
systemctl set-default graphical.target
systemctl enable lightdm.service

echo "reverted. reboot, or bring the desktop up now:  sudo systemctl start lightdm"
