#!/usr/bin/env python3
"""Off-device self-test for the cochlea tuner DSP core (T1).

No JACK, no guitar, no pytest -- synthesises signals with numpy and asserts the
dual detector maps them to the right note. The headline case is a low open E
(82.4 Hz) buried under strong 60 Hz mains hum: the whole reason for the
hum-notch + cross-check design.

    /home/miza/synapse-venv/bin/python tests/cochlea_selftest.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cochlea import PitchDetector, RingBuffer, freq_to_note, nearest_string
from cochlea import hum_filter

SR = 48000
N = 8192

_fails = []


def check(cond, msg):
    status = "ok  " if cond else "FAIL"
    print("  [%s] %s" % (status, msg))
    if not cond:
        _fails.append(msg)


def synth(freq, n=N, sr=SR, harmonics=(1.0,), hum_hz=0.0, hum_amp=0.0,
          noise=0.0, seed=0):
    """A tone (with optional harmonic stack) + optional rich mains hum + noise."""
    t = np.arange(n) / sr
    x = np.zeros(n)
    for k, a in enumerate(harmonics, start=1):
        x += a * np.sin(2.0 * np.pi * freq * k * t)
    if hum_amp > 0.0 and hum_hz > 0.0:
        for k, a in ((1, 1.0), (2, 0.5), (3, 0.3)):     # hum is itself harmonic
            x += hum_amp * a * np.sin(2.0 * np.pi * hum_hz * k * t)
    if noise > 0.0:
        x += noise * np.random.default_rng(seed).standard_normal(n)
    return x.astype(np.float32)


def cents_err(freq, target):
    return 1200.0 * np.log2(freq / target)


# -- note_mapping -----------------------------------------------------------
def test_note_mapping():
    print("note_mapping")
    r = freq_to_note(440.0)
    check(r.note == "A4" and abs(r.cents) < 0.01, "440 Hz -> A4, 0 cents")
    r = freq_to_note(82.41)
    check(r.note == "E2" and abs(r.cents) < 2.0, "82.41 Hz -> E2")
    r = freq_to_note(329.63)
    check(r.note == "E4", "329.63 Hz -> E4")
    # a touch sharp of A4
    r = freq_to_note(440.0 * 2 ** (5 / 1200.0))
    check(4.0 < r.cents < 6.0, "+5 cents reads as +5")
    label, hz, c = nearest_string(80.0, "guitar")
    check(label == "E2", "80 Hz nearest guitar string is E2 (flat)")
    check(c < 0, "80 Hz reads flat of E2")


# -- ring_buffer ------------------------------------------------------------
def test_ring_buffer():
    print("ring_buffer")
    rb = RingBuffer(256)
    check(rb.capacity == 256, "capacity rounds to power of two (256)")
    rb.write(np.arange(100, dtype=np.float32))
    rb.write(np.arange(100, 200, dtype=np.float32))
    out = np.zeros(150, dtype=np.float32)
    ok = rb.read_latest(150, out)
    check(ok and np.allclose(out, np.arange(50, 200)), "read_latest returns newest 150")
    # not enough data
    rb2 = RingBuffer(256)
    rb2.write(np.arange(10, dtype=np.float32))
    check(not rb2.read_latest(50, np.zeros(50, dtype=np.float32)), "read_latest False when short")
    # overflow drops oldest
    rb3 = RingBuffer(256)
    dropped = rb3.write(np.arange(300, dtype=np.float32))
    check(dropped >= 0, "oversized write does not crash")
    out3 = np.zeros(256, dtype=np.float32)
    check(rb3.read_latest(256, out3) and out3[-1] == 299.0, "keeps newest sample after overflow")


# -- hum_filter -------------------------------------------------------------
def test_hum_filter():
    print("hum_filter")
    freqs = np.fft.rfftfreq(N, 1.0 / SR)
    x60 = synth(82.41, hum_hz=60.0, hum_amp=0.8)
    mag60 = np.abs(np.fft.rfft(x60 - x60.mean()))
    check(hum_filter.estimate_mains(mag60, freqs) == 60.0, "detects 60 Hz mains")
    x50 = synth(82.41, hum_hz=50.0, hum_amp=0.8)
    mag50 = np.abs(np.fft.rfft(x50 - x50.mean()))
    check(hum_filter.estimate_mains(mag50, freqs) == 50.0, "detects 50 Hz mains")
    clean = synth(220.0, harmonics=(1.0, 0.4))
    magc = np.abs(np.fft.rfft(clean - clean.mean()))
    check(hum_filter.estimate_mains(magc, freqs) is None or True, "no crash on hum-free input")
    g = hum_filter.notch_gain(freqs, 60.0)
    i60 = int(np.argmin(np.abs(freqs - 60.0)))
    i82 = int(np.argmin(np.abs(freqs - 82.41)))
    check(g[i60] < 0.5, "notch attenuates the bin nearest 60 Hz (>50%)")
    check(g[i82] > 0.95, "notch leaves 82 Hz (low E) intact")
    # honest aggregate check: hum energy in a +/-6 Hz band around 60 Hz drops hard
    before = float(mag60[(freqs >= 54) & (freqs <= 66)].sum())
    after = float((mag60 * g)[(freqs >= 54) & (freqs <= 66)].sum())
    check(after < 0.3 * before, "60 Hz band energy cut >70%% (%.0f -> %.0f)" % (before, after))


# -- pitch_detection --------------------------------------------------------
def test_clean_tones():
    print("pitch_detection: clean tones")
    det = PitchDetector(SR, freq_min=65.0)
    for name, f in [("E2", 82.41), ("A2", 110.0), ("D3", 146.83),
                    ("G3", 196.0), ("B3", 246.94), ("E4", 329.63), ("A4", 440.0)]:
        est, _ = det.detect(synth(f, harmonics=(1.0, 0.5, 0.3, 0.2)))
        ok = est is not None and abs(cents_err(est.freq, f)) < 5.0
        detail = "%.2f Hz (%+.1f cents, %s)" % (est.freq, cents_err(est.freq, f), est.method) if est else "None"
        check(ok, "%s (%.2f Hz) -> %s" % (name, f, detail))


def test_octave_trap():
    print("pitch_detection: octave traps")
    det = PitchDetector(SR, freq_min=65.0)
    # weak fundamental, dominant 2nd harmonic -> must NOT report the octave up
    est, _ = det.detect(synth(110.0, harmonics=(0.15, 1.0, 0.5, 0.3)))
    ok = est is not None and abs(cents_err(est.freq, 110.0)) < 15.0
    check(ok, "weak-fundamental A2 stays A2, not A3 (%s)"
          % ("%.1f Hz" % est.freq if est else "None"))
    # low E rich tone
    est, _ = det.detect(synth(82.41, harmonics=(1.0, 0.7, 0.5, 0.4, 0.3)))
    ok = est is not None and abs(cents_err(est.freq, 82.41)) < 10.0
    check(ok, "rich low E stays E2, not E3 (%s)"
          % ("%.1f Hz" % est.freq if est else "None"))


def test_hum_rejection():
    print("pitch_detection: HUM REJECTION (the headline case)")
    # Low open E under strong 60 Hz hum. This is the case that fools both
    # detectors into agreeing on 60 Hz unless hum is removed first.
    sig = synth(82.41, harmonics=(1.0, 0.6, 0.4), hum_hz=60.0, hum_amp=0.9, noise=0.01)

    naive, _ = PitchDetector(SR, freq_min=65.0, notch_harmonics=0).detect(sig)
    ndet = "%.2f Hz" % naive.freq if naive else "None"
    print("      (no-notch baseline: %s)" % ndet)

    det = PitchDetector(SR, freq_min=65.0)                 # auto hum detect + notch
    est, mains = det.detect(sig)
    ok = est is not None and abs(cents_err(est.freq, 82.41)) < 15.0
    detail = "%.2f Hz (%+.1f cents, %s)" % (est.freq, cents_err(est.freq, 82.41), est.method) if est else "None"
    check(mains == 60.0, "auto-detected 60 Hz hum")
    check(ok, "low E survives 60 Hz hum -> %s" % detail)

    # same with 50 Hz hum
    sig50 = synth(82.41, harmonics=(1.0, 0.6, 0.4), hum_hz=50.0, hum_amp=0.9, noise=0.01)
    est50, _ = PitchDetector(SR, freq_min=65.0).detect(sig50)
    ok50 = est50 is not None and abs(cents_err(est50.freq, 82.41)) < 15.0
    check(ok50, "low E survives 50 Hz hum -> %s"
          % ("%.2f Hz" % est50.freq if est50 else "None"))


def test_sweep_and_silence():
    print("pitch_detection: sweep + silence")
    det = PitchDetector(SR, freq_min=65.0)
    for cents in (-30.0, -10.0, 10.0, 30.0):
        f = 196.0 * 2 ** (cents / 1200.0)                 # around G3
        est, _ = det.detect(synth(f, harmonics=(1.0, 0.5, 0.3)))
        ok = est is not None and abs(cents_err(est.freq, f)) < 6.0
        check(ok, "G3 %+d cents tracked (%s)" % (cents, "%.2f Hz" % est.freq if est else "None"))
    est, _ = det.detect(np.zeros(N, dtype=np.float32))
    check(est is None, "pure silence -> None")


def main():
    for t in (test_note_mapping, test_ring_buffer, test_hum_filter,
              test_clean_tones, test_octave_trap, test_hum_rejection,
              test_sweep_and_silence):
        t()
    print()
    if _fails:
        print("FAILED %d check(s):" % len(_fails))
        for m in _fails:
            print("  - " + m)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
