#!/usr/bin/env python3
"""Off-device selftest for the reflex pedal device + synapse-volume taper.

No hardware, JACK, or MIDI needed — exercises exactly the parts that are
importable off-device: calibration/mapping persistence, the raw->CC mapping,
the management-socket protocol (both the pure handler and a real Unix-socket
round trip), and the volume taper that moved from mastervolume.py into the
synapse-volume control daemon.

Run:  python3 tests/reflex_selftest.py
"""
import json
import math
import os
import socket
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "deploy", "volume-service"))

import reflex
import volumectl

FAILURES = []


def check(name, cond, detail=""):
    tag = "ok  " if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


# ------------------------------------------------------------- map_value
def test_map_value():
    check("map_value clamps below", reflex.map_value(0, 150, 17700) == 0)
    check("map_value clamps above", reflex.map_value(60000, 150, 17700) == 127)
    check("map_value endpoints", reflex.map_value(150, 150, 17700) == 0
          and reflex.map_value(17700, 150, 17700) == 127)
    mids = [reflex.map_value(v, 150, 17700) for v in range(150, 17701, 500)]
    check("map_value monotonic", all(a <= b for a, b in zip(mids, mids[1:])))


# ------------------------------------------- calibration/mapping persistence
def test_persistence():
    with tempfile.TemporaryDirectory() as d:
        cal_path = os.path.join(d, "pedal_calibration.json")
        # defaults when missing
        cal = reflex.load_calibration(cal_path)
        check("cal defaults", cal == reflex.DEFAULT_CAL)
        # round trip, preserving unrelated keys
        with open(cal_path, "w") as f:
            json.dump({"other": 42}, f)
        cal[0] = {"in_min": 500, "in_max": 16000}
        reflex.save_calibration(cal, cal_path)
        again = reflex.load_calibration(cal_path)
        check("cal round trip", again[0] == {"in_min": 500, "in_max": 16000})
        with open(cal_path) as f:
            check("cal preserves other keys", json.load(f).get("other") == 42)
        # corrupt file falls back
        with open(cal_path, "w") as f:
            f.write("{broken")
        check("cal corrupt fallback", reflex.load_calibration(cal_path) == reflex.DEFAULT_CAL)

        map_path = os.path.join(d, "reflex.json")
        m = reflex.load_mapping(map_path)
        check("mapping defaults", m == reflex.DEFAULT_MAPPING)
        m["volume"] = {"channel": 2, "cc": 110}
        reflex.save_mapping(m, map_path)
        check("mapping round trip",
              reflex.load_mapping(map_path)["volume"] == {"channel": 2, "cc": 110})


# ----------------------------------------------------------- protocol logic
def test_protocol():
    with tempfile.TemporaryDirectory() as d:
        cal_path = os.path.join(d, "pedal_calibration.json")
        map_path = os.path.join(d, "reflex.json")
        state = reflex.ReflexState(cal_path=cal_path, mapping_path=map_path)

        r = reflex.handle_request(state, {"cmd": "get_status"})
        check("status ok+version", r["ok"] and r["version"] == reflex.PROTOCOL_VERSION)
        check("status raw None before reads", r["raw"]["0"] is None)

        check("capture before reading fails",
              not reflex.handle_request(state, {"cmd": "capture_heel", "channel": 0})["ok"])
        check("save with nothing pending fails",
              not reflex.handle_request(state, {"cmd": "save"})["ok"])

        # simulate the read loop having measured both ends of ch0
        state.raw[0] = 200
        r = reflex.handle_request(state, {"cmd": "capture_heel", "channel": 0})
        check("capture heel", r["ok"] and r["raw"] == 200)
        state.raw[0] = 17900
        check("capture toe",
              reflex.handle_request(state, {"cmd": "capture_toe", "channel": 0})["ok"])
        r = reflex.handle_request(state, {"cmd": "save"})
        got = r["calibration"]["0"]
        span = 17900 - 200
        margin = int(span * reflex.CAPTURE_MARGIN)
        check("save applies inward margin",
              r["ok"] and got == {"in_min": 200 + margin, "in_max": 17900 - margin},
              f"got {got}")
        check("save persists", reflex.load_calibration(cal_path)[0] == got)
        check("save clears pending", state.pending == {})

        r = reflex.handle_request(state, {"cmd": "set_mapping", "axis": "volume",
                                          "channel": 1, "cc": 105})
        check("set_mapping", r["ok"] and r["mapping"]["volume"] == {"channel": 1, "cc": 105})
        check("set_mapping persists",
              reflex.load_mapping(map_path)["volume"] == {"channel": 1, "cc": 105})
        check("set_mapping rejects bad cc",
              not reflex.handle_request(state, {"cmd": "set_mapping", "axis": "volume",
                                                "channel": 0, "cc": 200})["ok"])
        check("set_mapping rejects bad axis",
              not reflex.handle_request(state, {"cmd": "set_mapping", "axis": "nope",
                                                "channel": 0, "cc": 102})["ok"])
        check("unknown cmd rejected",
              not reflex.handle_request(state, {"cmd": "frobnicate"})["ok"])


# ------------------------------------------------------ socket round trip
def test_socket_roundtrip():
    if not hasattr(socket, "AF_UNIX"):
        print("SKIP socket round trip (no AF_UNIX on this platform; protocol "
              "itself is covered above, the wire is Pi-only)")
        return
    with tempfile.TemporaryDirectory() as d:
        sock_path = os.path.join(d, "reflex.sock")
        state = reflex.ReflexState(cal_path=os.path.join(d, "cal.json"),
                                   mapping_path=os.path.join(d, "reflex.json"))
        state.raw[0] = 1234
        srv = reflex.start_socket_server(state, sock_path)
        try:
            c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c.settimeout(5)
            c.connect(sock_path)
            # two requests over one connection, incl. a bad-JSON line
            c.sendall(b'{"cmd":"get_status"}\n' + b'not json\n')
            f = c.makefile()
            r1 = json.loads(f.readline())
            r2 = json.loads(f.readline())
            check("socket status round trip", r1["ok"] and r1["raw"]["0"] == 1234)
            check("socket bad json -> error, connection survives", not r2["ok"])
            c.sendall(b'{"cmd":"get_mapping"}\n')
            r3 = json.loads(f.readline())
            check("socket still serving after error", r3["ok"] and "mapping" in r3)
            c.close()
        finally:
            srv.close()


# ------------------------------------------------- volume taper (volumectl)
def _legacy_ratio_to_cc(ratio):
    """The taper law as it lived in mastervolume.py before moving to volumectl,
    parameterized by travel ratio (was pct/100; volumectl uses raw/127)."""
    if ratio <= 0.0:
        return 0
    if ratio >= 1.0:
        return 127
    amp = ratio ** 2.0
    db = 20.0 * math.log10(amp)
    return max(0, min(127, round(127 + db / 0.5545)))


def test_taper():
    t = volumectl.TAPER_TABLE
    check("taper endpoints", t[0] == 0 and t[127] == 127)
    check("taper monotonic", all(a <= b for a, b in zip(t, t[1:])))
    # Identical law to the old app-side taper at every travel ratio the new
    # domain can express (raw/127 replaces pct/100).
    check("taper matches legacy app law",
          all(t[raw] == _legacy_ratio_to_cc(raw / 127.0) for raw in range(128)))
    # pct<->raw plumbing in the app stays linear and clamps
    import mastervolume
    check("pct->raw linear", mastervolume._pct_to_raw(0) == 0
          and mastervolume._pct_to_raw(100) == 127
          and mastervolume._raw_to_pct(64) == 50)
    check("pct clamps", mastervolume._pct_to_raw(150) == 127
          and mastervolume._pct_to_raw(-5) == 0)


def main():
    test_map_value()
    test_persistence()
    test_protocol()
    test_socket_roundtrip()
    test_taper()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
