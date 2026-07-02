#!/usr/bin/env python3
"""Diagnostics: drive a gain client's volume live via MIDI CC7 to confirm control
works. Sweeps full -> silence -> medium. Connects to the port named by arg1
(default 'synapsevol:midi in' -- the installed service; use 'synapsevol-test:midi in'
with manual-insert.sh). Needs python-jack.  Usage:  python3 cc-sweep.py [dest]"""
import sys
import time

import jack

dest = sys.argv[1] if len(sys.argv) > 1 else "synapsevol:midi in"
client = jack.Client("cc_sweep", no_start_server=True)
outp = client.midi_outports.register("out")

seq = [127] + list(range(127, -1, -3)) + list(range(0, 101, 3))
it = iter(seq)
st = {"n": 0, "done": False, "last": None}
CYCLES = 8

@client.set_process_callback
def _process(_frames):
    outp.clear_buffer()
    st["n"] += 1
    if st["n"] % CYCLES:
        return
    try:
        v = next(it)
    except StopIteration:
        st["done"] = True
        return
    outp.write_midi_event(0, bytes([0xB0, 0x07, v]))
    st["last"] = v

with client:
    try:
        client.connect(outp, dest)
        print("connected ->", dest)
    except Exception as e:
        print("connect error:", e)
        sys.exit(1)
    t0 = time.time()
    while not st["done"] and time.time() - t0 < 25:
        time.sleep(0.05)
    time.sleep(0.2)
    print("sweep done. last CC7 =", st["last"])
