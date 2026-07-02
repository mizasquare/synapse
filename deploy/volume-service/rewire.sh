#!/usr/bin/env bash
# Insert the master-volume gain client (jack_mix_box, "synapsevol") into the output
# path:  mod-monitor:out -> synapsevol:Channel 1 -> synapsevol:MAIN -> system:playback
# Run as ExecStartPost of synapse-mastervol.service (jack_mix_box is the main proc).
# Idempotent + waits for the ports to exist (handles boot ordering vs mod-host/jackd).
set -u
CLIENT="${1:-synapsevol}"

wait_port() {  # $1 = exact jack port name; wait up to ~15s
    for _ in $(seq 1 150); do
        jack_lsp 2>/dev/null | grep -qxF "$1" && return 0
        sleep 0.1
    done
    echo "rewire: timeout waiting for port '$1'" >&2
    return 1
}

wait_port "mod-monitor:out_1"      || exit 1
wait_port "system:playback_1"      || exit 1
wait_port "$CLIENT:MAIN L"         || exit 1

# 1) drop the C-level auto-connect (mod-monitor straight to hardware)
jack_disconnect "mod-monitor:out_1" "system:playback_1" 2>/dev/null
jack_disconnect "mod-monitor:out_2" "system:playback_2" 2>/dev/null

# 2) route pedalboard tail THROUGH the gain client
jack_connect "mod-monitor:out_1" "$CLIENT:Channel 1 L" 2>/dev/null
jack_connect "mod-monitor:out_2" "$CLIENT:Channel 1 R" 2>/dev/null
jack_connect "$CLIENT:MAIN L"    "system:playback_1"   2>/dev/null
jack_connect "$CLIENT:MAIN R"    "system:playback_2"   2>/dev/null

echo "rewire: '$CLIENT' inserted (mod-monitor -> $CLIENT -> system:playback)"
