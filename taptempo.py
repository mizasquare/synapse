"""Tap-tempo engine: timing math + LED metronome, free of any GUI/hardware import.

Entered via the C+D footswitch chord (see the footswitch-combo convention and
``presenter.handle_multiple_footswitches``). Each footswitch press feeds ``tap()``;
the engine keeps a short sliding window of tap intervals, derives a BPM (moving
average), optionally snaps it to a nice grid, and reports it through ``on_bpm``.
Independently it runs a beat metronome on the injected scheduler, calling
``on_beat(led_index, is_downbeat, duration)`` once per beat so the caller can flash
a physical LED. Which LED lights (and where the accent falls) is derived from the
time signature's beats-per-bar (``bpb``) -- MODEP transport tracks no denominator,
so the meter class keys off the beat count alone.

Pure logic + an injected ``scheduler.Scheduler`` and clock => unit-testable
headless (see ``taptempo_selftest.py``): pass a fake scheduler that records the
interval and a controllable clock to assert BPM/snap/reset deterministically.
"""

import time


def beat_plan(beat_counter, bpb):
    """Map a running beat index to ``(led_index, is_downbeat)`` for a ``bpb`` meter.

    Meter classes (denominator isn't tracked by MODEP transport, so this keys off
    beats-per-bar only):
      * waltz (bpb % 3 == 0): chase the LEFT THREE LEDs [0,1,2]
      * even  (bpb % 2 == 0): chase ALL FOUR LEDs [0,1,2,3]
      * odd   (else)        : free-run all four LEDs; the downbeat roams across
                              bars, which reads as "irregular meter" at a glance
    Downbeat = first beat of the bar (accent); other beats are off-beats.
    """
    bpb = max(1, int(bpb))
    if bpb % 3 == 0:
        ring = (0, 1, 2)
        pos = beat_counter % bpb
        return ring[pos % len(ring)], pos == 0
    if bpb % 2 == 0:
        ring = (0, 1, 2, 3)
        pos = beat_counter % bpb
        return ring[pos % len(ring)], pos == 0
    # odd / irregular: free-running 4-LED cycle, downbeat every bpb beats
    return beat_counter % 4, (beat_counter % bpb) == 0


class TapTempoEngine:
    """Tap-tempo timing + metronome over an injected scheduler.

    Callbacks (wired by the presenter):
      ``on_bpm(bpm: float)``                           -> push tempo to host + UI
      ``on_beat(led_index, is_downbeat, duration)``    -> flash one LED for ``duration`` s
    """

    def __init__(self, scheduler, on_bpm, on_beat,
                 clock=time.monotonic,
                 window=4, reset_timeout=2.0,
                 snap_multiple=4, snap_tolerance=1.5, snap_enabled=True,
                 min_bpm=40.0, max_bpm=300.0,
                 flash_max=0.08):
        self.scheduler = scheduler
        self._on_bpm = on_bpm
        self._on_beat = on_beat
        self._clock = clock
        # window = number of intervals averaged (so taps kept = window + 1).
        self.window = window
        self.reset_timeout = reset_timeout      # gap (s) that starts a fresh tap run
        self.snap_multiple = snap_multiple      # default grid: multiples of 4 (config later)
        self.snap_tolerance = snap_tolerance    # snap only within +/- this many BPM
        self.snap_enabled = snap_enabled
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm
        self.flash_max = flash_max              # beat-flash cap (s); shorter at fast tempi

        self._taps = []              # recent tap timestamps (<= window + 1)
        self._bpm = None             # last reported BPM
        self._bpb = 4
        self._beat = 0               # running beat counter (drives the metronome)
        self._interval_handle = None
        self._beat_interval = None   # current metronome period (s)
        self._running = False

    # -- lifecycle ---------------------------------------------------------
    def start(self, bpm, bpb):
        """Enter tap-tempo: seed the metronome at the current bpm/bpb."""
        self._running = True
        self._taps = []
        self._beat = 0
        self._bpb = max(1, int(bpb or 4))
        self._bpm = self._clamp(bpm or 120.0)
        self._schedule_metronome(self._beat_period(self._bpm))

    def stop(self):
        """Exit tap-tempo: stop the metronome (the caller clears the LEDs)."""
        self._running = False
        self._unschedule_metronome()
        self._taps = []

    def set_meter(self, bpb):
        """Update the time signature live (re-derives the LED plan next beat)."""
        self._bpb = max(1, int(bpb or 4))

    @property
    def bpm(self):
        return self._bpm

    # -- tap input ---------------------------------------------------------
    def tap(self):
        """Register one footswitch tap; refine + report BPM once 2+ taps land."""
        now = self._clock()
        if self._taps and (now - self._taps[-1]) > self.reset_timeout:
            self._taps = []          # stale gap -> start a fresh sequence
        self._taps.append(now)
        if len(self._taps) > self.window + 1:
            self._taps = self._taps[-(self.window + 1):]

        if len(self._taps) < 2:
            return                   # need at least one interval to estimate

        intervals = [b - a for a, b in zip(self._taps, self._taps[1:])]
        avg = sum(intervals) / len(intervals)
        if avg <= 0:
            return
        bpm = self._snap(self._clamp(60.0 / avg))
        self._bpm = bpm
        # Re-time the metronome only on a meaningful change, so a locked-in tempo
        # doesn't get phase-jittered by every extra tap.
        period = self._beat_period(bpm)
        if self._beat_interval is None or abs(period - self._beat_interval) > 0.005:
            self._schedule_metronome(period)
        self._on_bpm(bpm)

    # -- metronome ---------------------------------------------------------
    def _beat_period(self, bpm):
        return 60.0 / self._clamp(bpm)

    def _schedule_metronome(self, period):
        self._unschedule_metronome()
        self._beat_interval = period
        if self._running:
            self._interval_handle = self.scheduler.schedule_interval(self._tick, period)

    def _unschedule_metronome(self):
        if self._interval_handle is not None:
            self.scheduler.unschedule(self._interval_handle)
            self._interval_handle = None

    def _tick(self, dt):
        led, downbeat = beat_plan(self._beat, self._bpb)
        self._beat += 1
        dur = min(self.flash_max, (self._beat_interval or 0.2) * 0.5)
        self._on_beat(led, downbeat, dur)

    # -- helpers -----------------------------------------------------------
    def _clamp(self, bpm):
        return max(self.min_bpm, min(self.max_bpm, float(bpm)))

    def _snap(self, bpm):
        """Snap to the nearest multiple of ``snap_multiple`` when within tolerance.

        Default grid is multiples of 4; other grids (5, 10, priorities) are a
        config TODO -- see docs/config-todo.md.
        """
        if not self.snap_enabled or self.snap_multiple <= 0:
            return round(bpm, 1)
        nearest = round(bpm / self.snap_multiple) * self.snap_multiple
        if abs(bpm - nearest) <= self.snap_tolerance:
            return float(nearest)
        return round(bpm, 1)
