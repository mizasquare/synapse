#!/usr/bin/env bash
# eglfs launcher: Synapse UI straight onto the DSI panel, no compositor.
# Used by synapse-ui.service; also runnable by hand over SSH for testing
# (stop lightdm first -- only one DRM master at a time).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

export QT_QPA_PLATFORM=eglfs
export QT_QPA_EGLFS_INTEGRATION=eglfs_kms
# Pins the panel by stable by-path name: both DSI connectors report "connected"
# (DSI-2 is a phantom), so autodetection is ambiguous. See eglfs_kms.json.
export QT_QPA_EGLFS_KMS_CONFIG="$HERE/eglfs_kms.json"
# Touch-only box; also the GBM hw-cursor plane fails on this stack (migration
# archive §5), so never ask for one.
export QT_QPA_EGLFS_HIDECURSOR=1
# LevelMeter must reach modep's jackd across users (same env labwc sessions had).
export JACK_PROMISCUOUS_SERVER=jack
# Under the service this is preset to /run/synapse-ui; manual SSH runs fall
# back to the login session's own dir.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

cd /home/miza/synapse
exec /home/miza/synapse-venv/bin/python qt_main.py
