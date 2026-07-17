#!/usr/bin/env bash
# Install the Ganglion pedal UI service. Run with sudo:  sudo ./install.sh
# Idempotent — safe to re-run after editing the unit.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

# Fail early with a useful message rather than letting systemd restart-loop on a
# missing interpreter or a bus with nothing on it -- both are what actually goes
# wrong here (venv rebuilt without --system-site-packages; ribbon unseated).
VENV=/home/miza/synapse/venv/bin/python
[ -x "$VENV" ] || { echo "no venv at $VENV — see ganglion/README.md"; exit 1; }
"$VENV" -c 'import luma.oled, adafruit_seesaw' 2>/dev/null \
  || { echo "venv lacks luma.oled / adafruit_seesaw — see ganglion/README.md"; exit 1; }
if command -v i2cdetect >/dev/null; then
  found=$(i2cdetect -y 1 2>/dev/null | grep -oE '\b(36|37|3d)\b' | sort -u | tr '\n' ' ')
  echo "i2c-1: found ${found:-nothing}  (expect: 36 37 3d = enc0 enc1 oled)"
fi

install -m 0644 "$HERE/ganglion.service" /etc/systemd/system/ganglion.service

# SYSTEM > WiFi needs three NetworkManager actions that default to allow_active,
# which a sessionless system service can never satisfy (see the rule's comment,
# and 49-synapse-power.rules for the identical problem in the other app). polkitd
# reads rules.d live, so no reload.
install -m 0644 "$HERE/50-ganglion-radio.rules" /etc/polkit-1/rules.d/50-ganglion-radio.rules

systemctl daemon-reload
systemctl enable --now ganglion.service

echo
echo "installed + started. check with:"
echo "  systemctl status ganglion.service"
echo "  journalctl -u ganglion.service -f"
echo
echo "the service owns the i2c devices while it runs — stop it before using the"
echo "bring-up tools, or they will fight over the bus:"
echo "  sudo systemctl stop ganglion.service"
echo "  venv/bin/python -m ganglion.tools.oled_probe"
echo
echo "uninstall:  sudo systemctl disable --now ganglion.service && sudo rm /etc/systemd/system/ganglion.service && sudo systemctl daemon-reload"
