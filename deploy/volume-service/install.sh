#!/usr/bin/env bash
# Install the Synapse master-volume service. Run with sudo:  sudo ./install.sh
# Idempotent — safe to re-run after editing the scripts/unit.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

install -m 0755 "$HERE/rewire.sh"  /usr/local/bin/synapse-mastervol-rewire.sh
install -m 0755 "$HERE/revert.sh"  /usr/local/bin/synapse-mastervol-revert.sh
install -m 0755 "$HERE/volumectl.py" /usr/local/bin/synapse-volumectl.py
install -m 0644 "$HERE/synapse-mastervol.service" /etc/systemd/system/synapse-mastervol.service

# the control daemon needs the JACK-Client python package under system python
/usr/bin/python3 -c 'import jack' 2>/dev/null || {
    echo "WARNING: python3 'jack' module missing (pip install JACK-Client," >&2
    echo "         or point the unit's ExecStart at a venv python that has it)" >&2
}

systemctl daemon-reload
systemctl enable --now synapse-mastervol.service

echo
echo "installed + started. check with:"
echo "  systemctl status synapse-mastervol.service"
echo "  jack_lsp -c | grep -E 'synapsevol|playback'"
echo
echo "uninstall:  sudo systemctl disable --now synapse-mastervol.service && sudo rm /etc/systemd/system/synapse-mastervol.service /usr/local/bin/synapse-mastervol-*.sh /usr/local/bin/synapse-volumectl.py && sudo systemctl daemon-reload"
