#!/usr/bin/env python3
"""Measure jack_mix_box's MIDI-CC -> gain curve, to (re)calibrate the volume taper.

Why: the synapse-volume control daemon (volumectl.py) inverts jack_mix_box's fader
law to turn a raw volume command into a mixer CC. That law (CC127 = 0 dB unity,
~0.5545 dB per CC step, CC0 = mute -- a linear-in-dB fader) was measured on this
Pi. On another machine / a different jack_mixer build the scale may differ, so run
this and copy the reported constants into volumectl.py (DB_PER_CC, CC_UNITY).

How: spawns its own jack_mix_box, feeds a 440 Hz sine into it via JACK, reads the
output RMS at each CC, and fits dB = m*CC + b. Self-contained -- touches no other
audio (its client isn't connected to the pedalboard). Needs: jackd running,
python-jack, numpy.  Usage:  python3 measure-cc-gain.py
"""
import math
import subprocess
import time

import jack
import numpy as np

NAME = "ccmeas"
AMP = 0.25
FREQ = 440.0

proc = subprocess.Popen(["jack_mix_box", "--name", NAME, "--stereo", "--volume=0", "7"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(1.5)
    c = jack.Client("ccmeas_probe", no_start_server=True)
    ao = c.outports.register("ao")
    ai = c.inports.register("ai")
    mo = c.midi_outports.register("mo")
    st = {"phase": 0, "cc": None, "last": -1, "rms": 0.0}

    @c.set_process_callback
    def _process(n):
        mo.clear_buffer()
        if st["cc"] is not None and st["cc"] != st["last"]:
            mo.write_midi_event(0, bytes([0xB0, 7, st["cc"]]))
            st["last"] = st["cc"]
        t = np.arange(st["phase"], st["phase"] + n)
        ao.get_array()[:] = (AMP * np.sin(2 * np.pi * FREQ * t / c.samplerate)).astype("float32")
        st["phase"] += n
        buf = ai.get_array()
        st["rms"] = float(np.sqrt(np.mean(buf * buf)))

    with c:
        c.connect(ao, f"{NAME}:Channel 1 L")
        c.connect(f"{NAME}:MAIN L", ai)
        c.connect(mo, f"{NAME}:midi in")
        in_rms = AMP / math.sqrt(2)
        print(f"{'CC':>4} {'gain':>8} {'dB':>8}")
        pts = []
        for cc in list(range(8, 128, 8)) + [127]:
            st["cc"] = cc
            time.sleep(0.35)
            acc = []
            for _ in range(15):
                time.sleep(0.02)
                acc.append(st["rms"])
            g = float(np.median(acc)) / in_rms
            db = 20 * math.log10(g) if g > 1e-6 else -120.0
            print(f"{cc:>4} {g:>8.4f} {db:>8.1f}")
            if g > 1e-5:
                pts.append((cc, db))
        # least-squares fit dB = m*CC + b  ->  CC_unity = -b/m at 0 dB
        xs = np.array([p[0] for p in pts], float)
        ys = np.array([p[1] for p in pts], float)
        m, b = np.polyfit(xs, ys, 1)
        print("\nfit: dB = %.4f*CC %+.2f" % (m, b))
        print("=> volumectl.py:  DB_PER_CC = %.4f   CC_UNITY = %d"
              % (m, round((0.0 - b) / m)))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()
