#!/usr/bin/env bash
# Undo rewire.sh: restore the direct mod-monitor:out -> system:playback path.
# Run as ExecStopPost (jack_mix_box itself is stopped by systemd killing the main proc).
set -u
CLIENT="${1:-synapsevol}"

jack_disconnect "$CLIENT:MAIN L"    "system:playback_1"   2>/dev/null
jack_disconnect "$CLIENT:MAIN R"    "system:playback_2"   2>/dev/null
jack_disconnect "mod-monitor:out_1" "$CLIENT:Channel 1 L" 2>/dev/null
jack_disconnect "mod-monitor:out_2" "$CLIENT:Channel 1 R" 2>/dev/null

# restore direct output so audio survives the service stopping
jack_connect "mod-monitor:out_1" "system:playback_1" 2>/dev/null
jack_connect "mod-monitor:out_2" "system:playback_2" 2>/dev/null

echo "revert: '$CLIENT' removed, direct mod-monitor -> system:playback restored"
