"""Headless self-test for taptempo.TapTempoEngine (no Qt, no hardware).

Run:  .venv\\Scripts\\python tests/taptempo_selftest.py  (or:  py tests/taptempo_selftest.py)

A synchronous fake scheduler (records the single metronome interval) plus a
manually-advanced clock make BPM math, snapping, the stale-gap reset and the
metronome LED plan all deterministic.
"""

import os
import sys

# tests/ live one level below the repo root; put the root on the path so the
# flat live modules (taptempo, ...) import whatever directory we're run from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from taptempo import TapTempoEngine, beat_plan


class FakeScheduler:
    """Records intervals so tests can assert exactly one metronome is live."""

    def __init__(self):
        self._intervals = {}
        self._seq = 0

    def schedule_once(self, cb, timeout=0):
        return None  # flash-off callbacks are irrelevant to these assertions

    def schedule_interval(self, cb, interval):
        self._seq += 1
        self._intervals[self._seq] = (cb, interval)
        return self._seq

    def unschedule(self, handle):
        self._intervals.pop(handle, None)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt
        return self.t


def approx(a, b, tol=0.1):
    return abs(a - b) <= tol


def _engine(sched=None, clk=None, got=None, **kw):
    sched = sched if sched is not None else FakeScheduler()
    clk = clk if clk is not None else Clock()
    got = got if got is not None else []
    eng = TapTempoEngine(sched, on_bpm=got.append, on_beat=lambda *a: None,
                         clock=clk, **kw)
    return eng, sched, clk, got


def test_basic_120():
    eng, _, clk, got = _engine()
    eng.start(120, 4)
    for _ in range(5):              # 5 taps @ 0.5 s -> 120 BPM
        eng.tap(); clk.advance(0.5)
    assert got, "no BPM reported"
    assert approx(got[-1], 120), got[-1]
    print("ok basic_120            ->", got[-1])


def test_snap_to_4():
    eng, _, clk, got = _engine(snap_multiple=4, snap_tolerance=1.5)
    eng.start(120, 4)
    for _ in range(5):              # ~0.503 s -> ~119.3 BPM -> snaps to 120
        eng.tap(); clk.advance(0.503)
    assert approx(got[-1], 120, 0.001), got[-1]
    print("ok snap_to_4            ->", got[-1])


def test_no_snap_outside_tolerance():
    eng, _, clk, got = _engine(snap_multiple=4, snap_tolerance=1.5)
    eng.start(120, 4)
    for _ in range(5):              # 60/0.5882 ~= 102 BPM; nearest mult-4 (104) is >1.5 off
        eng.tap(); clk.advance(0.5882)
    assert approx(got[-1], 102, 0.5), got[-1]
    assert got[-1] % 4 != 0, ("unexpectedly snapped", got[-1])
    print("ok no_snap_outside_tol  ->", got[-1])


def test_reset_after_gap():
    eng, _, clk, got = _engine()
    eng.start(120, 4)
    eng.tap(); clk.advance(0.4); eng.tap()    # fast pair -> ~150 BPM
    assert approx(got[-1], 150), got[-1]
    clk.advance(3.0)                           # stale gap (> reset_timeout)
    eng.tap()                                  # starts a fresh sequence (no report)
    clk.advance(0.5); eng.tap()                # one clean 0.5 s interval -> 120
    assert approx(got[-1], 120), ("contaminated by pre-gap taps", got[-1])
    print("ok reset_after_gap      ->", got[-1])


def test_metronome_single_interval():
    eng, sched, clk, _ = _engine()
    eng.start(120, 4)
    assert len(sched._intervals) == 1, sched._intervals
    for _ in range(5):              # tempo change reschedules, never accumulates
        eng.tap(); clk.advance(0.4)
    assert len(sched._intervals) == 1, sched._intervals
    eng.stop()
    assert len(sched._intervals) == 0, sched._intervals
    print("ok metronome_single_interval")


def test_beat_plan():
    # 4/4 even: chase all four, downbeat on beat 0
    assert beat_plan(0, 4) == (0, True)
    assert beat_plan(1, 4) == (1, False)
    assert beat_plan(3, 4) == (3, False)
    assert beat_plan(4, 4) == (0, True)
    # 3/4 waltz: left three, downbeat on beat 0
    assert beat_plan(0, 3) == (0, True)
    assert beat_plan(2, 3) == (2, False)
    assert beat_plan(3, 3) == (0, True)
    # 6/8 (bpb 6) -> waltz ring of three
    assert beat_plan(0, 6) == (0, True)
    assert beat_plan(3, 6) == (0, False)
    # 7/4 odd: free-running four, downbeat roams (every 7)
    assert beat_plan(0, 7) == (0, True)
    assert beat_plan(4, 7) == (0, False)
    assert beat_plan(7, 7) == (3, True)
    print("ok beat_plan")


def main():
    test_basic_120()
    test_snap_to_4()
    test_no_snap_outside_tolerance()
    test_reset_after_gap()
    test_metronome_single_interval()
    test_beat_plan()
    print("\nALL TAP-TEMPO SELF-TESTS PASSED")


if __name__ == "__main__":
    main()
