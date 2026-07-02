#!/usr/bin/env bash
# Bring-up / diagnostics: manually launch a gain client and splice it into the
# output path WITHOUT installing the service. Reversible via manual-revert.sh.
# Use this to prove the routing works on a new machine before enabling the unit.
#
# Arg1 = test gain in dB (default -20 => audibly quieter, so you can hear the stage).
#        0 = unity (should sound identical -> proves transparent insertion).
set -u
GAIN="${1:--20}"
NAME=synapsevol-test
PIDF="$(dirname "$0")/.$NAME.pid"

echo "== BEFORE =="; jack_lsp -c 2>/dev/null | grep -A1 -E "mod-monitor:out_[12]$" | grep -E "mod-monitor|playback"

[ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null; sleep 0.3
jack_mix_box --name="$NAME" --stereo --volume="$GAIN" 7 >/dev/null 2>&1 &
echo $! > "$PIDF"
for _ in $(seq 1 20); do jack_lsp 2>/dev/null | grep -qxF "$NAME:MAIN L" && break; sleep 0.1; done

jack_disconnect "mod-monitor:out_1" "system:playback_1" 2>/dev/null
jack_disconnect "mod-monitor:out_2" "system:playback_2" 2>/dev/null
jack_connect    "mod-monitor:out_1" "$NAME:Channel 1 L"
jack_connect    "mod-monitor:out_2" "$NAME:Channel 1 R"
jack_connect    "$NAME:MAIN L"      "system:playback_1"
jack_connect    "$NAME:MAIN R"      "system:playback_2"

echo "== AFTER (gain=${GAIN}dB) =="
jack_lsp -c 2>/dev/null | grep -A1 -E "system:playback_[12]$" | grep -E "playback|MAIN"
echo "control:  send MIDI CC7 into '$NAME:midi in' (see cc-sweep.py)"
echo "revert:   $(dirname "$0")/manual-revert.sh"
