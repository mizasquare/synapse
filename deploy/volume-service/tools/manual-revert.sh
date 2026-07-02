#!/usr/bin/env bash
# Undo manual-insert.sh: restore direct mod-monitor:out -> system:playback, kill the
# test gain client.
set -u
NAME=synapsevol-test
PIDF="$(dirname "$0")/.$NAME.pid"

jack_disconnect "$NAME:MAIN L"      "system:playback_1"   2>/dev/null
jack_disconnect "$NAME:MAIN R"      "system:playback_2"   2>/dev/null
jack_disconnect "mod-monitor:out_1" "$NAME:Channel 1 L"   2>/dev/null
jack_disconnect "mod-monitor:out_2" "$NAME:Channel 1 R"   2>/dev/null
jack_connect    "mod-monitor:out_1" "system:playback_1"   2>/dev/null
jack_connect    "mod-monitor:out_2" "system:playback_2"   2>/dev/null
[ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null && rm -f "$PIDF"

echo "== RESTORED =="
jack_lsp -c 2>/dev/null | grep -A1 -E "system:playback_[12]$" | grep -E "playback|mod-monitor|MAIN"
