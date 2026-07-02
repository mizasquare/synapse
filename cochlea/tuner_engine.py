"""Threaded tuner engine: audio -> pitch -> a stable, display-ready reading.

Wraps the RingBuffer + PitchDetector in a daemon DSP thread (the monitorfeed /
footswitch idiom) and layers on the "feel" that a raw per-frame frequency lacks:

* RMS silence gate        -- no signal, no reading.
* Onset detection         -- a fresh pluck resets smoothing so the needle snaps
                             to the new note instead of drifting from the old one.
* One Euro filter          -- adaptive low-pass on log-frequency: low lag when the
                             pitch moves, low jitter when it is held. (Neither
                             pi-stomp nor the old code did this -- it is the single
                             biggest needle-feel win.)
* Note-lock hysteresis     -- holds the displayed note until a *different* note
                             persists for a few frames, killing boundary flicker
                             and stray octave jumps without an HMM.
* Confidence gating        -- low-confidence / stale frames report nothing so the
                             UI can fade to "listening" rather than show garbage.

The pure pieces (OneEuroFilter, NoteTracker) are plain classes with no threads or
audio, so they unit-test deterministically; TunerEngine is the live wrapper.
"""
import math
import threading
import time
from dataclasses import dataclass

import numpy as np

from .pitch_detection import PitchDetector
from .ring_buffer import RingBuffer
from . import note_mapping


@dataclass(frozen=True)
class TunerReading:
    note: str          # "E2"
    pitch_class: int
    octave: int
    cents: float       # smoothed deviation from the locked note, -50..+50
    freq_hz: float     # smoothed frequency
    ideal_hz: float
    confidence: float
    string: str        # nearest open string in instrument mode, else ""
    ts: float          # monotonic timestamp of this reading


# -- pure helpers (no threads / no audio) ----------------------------------
class OneEuroFilter:
    """1-euro filter (Casiez et al. 2012). Adaptive low-pass: the cutoff rises
    with the signal's speed, so it tracks fast changes yet smooths steady input.
    Applied here to log2(frequency) so smoothing is perceptually linear."""

    def __init__(self, min_cutoff=0.8, beta=0.03, dcutoff=1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.dcutoff = float(dcutoff)
        self.reset()

    def reset(self):
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self._x_prev is None:
            self._x_prev, self._t_prev, self._dx_prev = x, t, 0.0
            return x
        dt = t - self._t_prev
        if dt <= 0.0:
            dt = 1e-3
        dx = (x - self._x_prev) / dt
        a_d = self._alpha(self.dcutoff, dt)
        edx = a_d * dx + (1.0 - a_d) * self._dx_prev
        cutoff = self.min_cutoff + self.beta * abs(edx)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._x_prev
        self._x_prev, self._dx_prev, self._t_prev = x_hat, edx, t
        return x_hat


class NoteTracker:
    """Note-lock hysteresis. Reports a locked MIDI note that only changes once a
    *different* note has persisted for `switch_hold` consecutive updates -- a
    single-frame octave outlier can't move it."""

    def __init__(self, switch_hold=3, a4_hz=note_mapping.DEFAULT_A4_HZ):
        self.switch_hold = int(switch_hold)
        self.a4 = float(a4_hz)
        self.reset()

    def reset(self):
        self._locked = None
        self._pending = None
        self._pending_n = 0

    def update(self, freq):
        midi = int(round(12.0 * math.log2(freq / self.a4) + note_mapping.A4_MIDI))
        if self._locked is None or midi == self._locked:
            self._pending, self._pending_n = None, 0
            self._locked = midi
            return self._locked
        if midi == self._pending:
            self._pending_n += 1
        else:
            self._pending, self._pending_n = midi, 1
        if self._pending_n >= self.switch_hold:
            self._locked, self._pending, self._pending_n = midi, None, 0
        return self._locked

    def ideal_hz(self, midi):
        return self.a4 * 2.0 ** ((midi - note_mapping.A4_MIDI) / 12.0)


# -- live engine ------------------------------------------------------------
class TunerEngine:
    FRAME_SIZE = 8192      # ~171 ms @ 48 kHz: several periods of low E, still snappy
    RING_CAPACITY = 16384
    DSP_RATE_HZ = 20

    SILENCE_RMS = 0.003    # below this: no reading
    ONSET_RATIO = 3.0      # RMS jump factor that means "new note plucked"
    ONSET_HOLDOFF = 1      # frames skipped after an onset (drop the attack transient)
    CONF_MIN = 0.30        # below this cross-check confidence: don't publish
    HOLD_SEC = 0.40        # a reading older than this is considered stale (-> None)

    def __init__(self, source, freq_min=65.0, freq_max=1300.0, mains=None,
                 a4_hz=note_mapping.DEFAULT_A4_HZ, string_set=None,
                 one_euro=None, switch_hold=3):
        self._source = source
        self._freq_min = freq_min
        self._freq_max = freq_max
        self._mains = mains
        self._a4 = float(a4_hz)
        self._string_set = string_set          # None -> chromatic; else e.g. "guitar"

        self._ring = RingBuffer(self.RING_CAPACITY)
        self._frame = np.zeros(self.FRAME_SIZE, dtype=np.float32)
        self._detector = None                  # built in start() once sr is known
        self._euro = one_euro or OneEuroFilter()
        self._notes = NoteTracker(switch_hold, a4_hz)

        self._running = False
        self._worker = None
        self._lock = threading.Lock()
        self._latest = None
        self._prev_rms = 0.0
        self._holdoff = 0

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        self._running = True
        self._source.start(on_samples=self._ring.write)
        self._detector = PitchDetector(
            self._source.sample_rate, freq_min=self._freq_min,
            freq_max=self._freq_max, mains=self._mains)
        self._worker = threading.Thread(target=self._loop, daemon=True, name="tuner-dsp")
        self._worker.start()

    def stop(self):
        self._running = False
        self._source.stop()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None

    def set_a4(self, a4_hz):
        self._a4 = float(a4_hz)
        self._notes.a4 = float(a4_hz)

    # -- consumer API -------------------------------------------------------
    def get_reading(self):
        """Latest stable reading, or None (silence / low confidence / stale)."""
        with self._lock:
            r = self._latest
        if r is None or (time.monotonic() - r.ts) > self.HOLD_SEC:
            return None
        return r

    # -- DSP thread ---------------------------------------------------------
    def _loop(self):
        interval = 1.0 / self.DSP_RATE_HZ
        while self._running:
            t0 = time.monotonic()
            try:
                self._process()
            except Exception:
                pass                            # never let the DSP thread die
            sleep = interval - (time.monotonic() - t0)
            if sleep > 0:
                time.sleep(sleep)

    def _publish(self, reading):
        with self._lock:
            self._latest = reading

    def _process(self):
        if not self._ring.read_latest(self.FRAME_SIZE, self._frame):
            return
        rms = float(np.sqrt(np.mean(self._frame ** 2)))

        if rms < self.SILENCE_RMS:
            self._euro.reset()
            self._notes.reset()
            self._holdoff = 0
            self._prev_rms = rms
            self._publish(None)
            return

        # Onset: a sudden loudness jump means a new pluck -> re-lock from scratch.
        if rms > self._prev_rms * self.ONSET_RATIO:
            self._euro.reset()
            self._notes.reset()
            self._holdoff = self.ONSET_HOLDOFF
        self._prev_rms = rms
        if self._holdoff > 0:
            self._holdoff -= 1
            return

        est, _ = self._detector.detect(self._frame)
        if est is None or est.confidence < self.CONF_MIN:
            return                              # keep last reading; it will age out

        now = time.monotonic()
        log_f = self._euro(math.log2(est.freq), now)
        freq = 2.0 ** log_f

        locked = self._notes.update(freq)
        ideal = self._notes.ideal_hz(locked)
        cents = 1200.0 * math.log2(freq / ideal)
        pc = locked % 12
        octave = locked // 12 - 1
        string = ""
        if self._string_set:
            string, _, _ = note_mapping.nearest_string(freq, self._string_set)

        self._publish(TunerReading(
            note="%s%d" % (note_mapping.NOTE_NAMES[pc], octave),
            pitch_class=pc, octave=octave, cents=cents,
            freq_hz=freq, ideal_hz=ideal, confidence=est.confidence,
            string=string, ts=now))
