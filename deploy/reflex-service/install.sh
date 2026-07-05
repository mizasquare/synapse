#!/usr/bin/env bash
# Install the Synapse reflex pedal service. Run with sudo:  sudo ./install.sh
# Idempotent — safe to re-run after editing the unit.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

install -m 0644 "$HERE/synapse-reflex.service" /etc/systemd/system/synapse-reflex.service

systemctl daemon-reload
systemctl enable --now synapse-reflex.service

echo
echo "installed + started. check with:"
echo "  systemctl status synapse-reflex.service"
echo "  journalctl -u synapse-reflex.service -f"
echo "  echo '{\"cmd\":\"get_status\"}' | nc -U ~miza/.modep/reflex.sock"
echo
echo "uninstall:  sudo systemctl disable --now synapse-reflex.service && sudo rm /etc/systemd/system/synapse-reflex.service && sudo systemctl daemon-reload"
