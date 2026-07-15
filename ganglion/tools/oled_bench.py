"""What the diff driver actually costs on the frames the app really draws.

``design_screens.py`` priced *mockup* screens on hand-picked before/after pairs.
This prices the shipping view (``app.render``) over **frame sequences at the real
tick rate** (33 Hz), pushed through the real ``hw.oled.DiffSink`` -- so what comes
out is what the panel would see: bytes per tick, wire ms at 400kHz, how much of
the bus we hold (the encoders share it), and how often we send nothing at all.

Run: python3 -m ganglion.tools.oled_bench

Two design questions were settled here and are worth not re-litigating (both
recorded in design.md §2): the tuner meter stays *horizontal* -- a vertical one
measured 30 vs 34 bytes/tick, i.e. the same nothing -- and the glance snapshot
name dropped a type tier, because two 24px names marqueeing at once cost more
than everything else the app animates put together.
"""

import statistics
import sys

from ganglion import i2c_cost
from ganglion.app import AppController, render
from ganglion.hw.oled import CountingWriter, DiffSink

TICK = 0.03                       # runtime.Runtime default: ~33 Hz
FULL = i2c_cost.full_cost()["total_bytes"]


# ---- scenarios: each yields (label, states, view) ----------------------------
def _cents_track(n, settle=60):
    """A plausible readout: swings in from -34c, settles, then hovers with the
    +-1..2c jitter a real pitch detector never stops producing."""
    out, rng = [], _Rng(7)
    for k in range(n):
        base = -34 * max(0.0, 1 - k / settle) ** 2      # swing in, then ~0
        out.append(int(round(base + rng.jitter(1.6))))
    return out


class _Rng:
    """Tiny deterministic LCG -- the bench must give the same answer every run."""

    def __init__(self, seed):
        self.s = seed

    def jitter(self, amp):
        self.s = (self.s * 1103515245 + 12345) & 0x7FFFFFFF
        return ((self.s >> 8) % 2001 / 1000.0 - 1.0) * amp


def _hold(c, n, mutate=None):
    """n ticks of the clock advancing with no input -- what the device does while
    the user is just looking at it (the marquee, and nothing else, moves)."""
    states = []
    for k in range(n):
        c.st.t = k * TICK
        if mutate:
            mutate(c.st, k)
        states.append(_clone(c.st))
    return states


def _clone(st):
    import copy
    return copy.copy(st)


def scenarios(n=200):
    out = []

    # The demo board's names ("Comp", "Drive") all *fit* -- so it never marquees
    # and would flatter us with a 0-byte score. The real catalog overflows the
    # 92px box in 53 of 71 names, so the focused node is scrolling essentially
    # whenever the user is in the chain. Bench the state we ship into.
    c = AppController()
    c.st.depth = 0
    c.st.board[c.st.node]["name"] = "GxColorSoundTonebender"   # a median overflow
    out.append(("chain, idle (16px node marquee)", _hold(c, n), render))

    # Glance is the busiest screen: the 24px board name always overflows, so it
    # always scrolls. Its snapshot name rides the 16px tier and mostly fits, so
    # it mostly doesn't -- bench both, because a generated name ("formerly-
    # thursday") still overflows and puts a second marquee on the bus.
    g = AppController()
    g.st.depth = -1
    out.append(("glance, resting (board marquee)", _hold(g, n), render))

    g2 = AppController()
    g2.st.depth = -1
    g2.st.snaps[g2.st.snap] = "formerly-thursday"        # a generated name: overflows 16px
    out.append(("glance, both names scrolling", _hold(g2, n), render))

    track = _cents_track(n)

    def tune(st, k):
        st.tcents = track[k]

    t = AppController()
    t.st.tuner = True
    t.st.tnote = "A"
    out.append(("tuner (needle + cents readout)", _hold(t, n, tune), render))

    return out


# ---- run --------------------------------------------------------------------
def measure(states, view):
    """Push a frame sequence through the real diff sink; bill each tick."""
    w = CountingWriter()
    sink = DiffSink(w)
    sink.show(view(states[0]))                           # first frame = full push,
    per = []                                             # not part of the steady state
    for st in states[1:]:
        before = len(w.spans)
        data = sink.show(view(st))
        spans = len(w.spans) - before
        per.append(data + spans * i2c_cost.PER_PAGEROW_OVERHEAD)
    return per, sink.stats


def report(label, per):
    silent = sum(1 for b in per if b == 0)
    hot = [b for b in per if b] or [0]
    mean, worst = statistics.mean(per), max(per)
    print("\n%s" % label)
    print("  silent ticks : %3d/%d (%.0f%%)  <- zero bytes on the bus"
          % (silent, len(per), 100.0 * silent / len(per)))
    print("  bytes/tick   : mean %6.1f   median(active) %5.0f   worst %5d   (full frame = %d)"
          % (mean, statistics.median(hot), worst, FULL))
    print("  wire @400kHz : mean %5.2f ms  worst %5.2f ms   (full frame = %.0f ms)"
          % (i2c_cost.wire_ms(mean), i2c_cost.wire_ms(worst), i2c_cost.wire_ms(FULL)))
    print("  bus duty     : %4.1f%% of the 30ms tick   -> worst tick still %.0f fps-capable"
          % (100.0 * i2c_cost.wire_ms(mean) / (TICK * 1000),
             1000.0 / max(i2c_cost.wire_ms(worst), 0.001)))
    return mean, worst


class ReplayWriter:
    """A fake panel: applies the spans to its own framebuffer, exactly as the
    SH1107 would. Lets us prove the diff driver is *lossless* -- a driver that
    skips a page-row doesn't crash, it just quietly leaves a stale strip on the
    glass, which is the one bug we can't see from the dev box."""

    def __init__(self):
        self.fb = [bytearray(i2c_cost.WIDTH) for _ in range(i2c_cost.PAGES)]

    def write(self, page, col, data):
        self.fb[page][col:col + len(data)] = data


def verify(states, view):
    """Replay every scenario through the fake panel; the glass must equal the
    frame the app drew, on every single tick."""
    panel = ReplayWriter()
    sink = DiffSink(panel)
    for k, st in enumerate(states):
        img = view(st)
        sink.show(img)
        if panel.fb != i2c_cost.frame_pages(img):
            return k
    return -1


def main(argv):
    n = 200
    print("diff driver on real app frames -- %d ticks @ %.0f Hz, SH1107 @400kHz"
          % (n, 1 / TICK))
    print("(the full-frame sink this replaces: %d B -> %.0f ms per tick, i.e. LONGER than the\n"
          " %.0f ms tick itself -- it would hold the bus the encoders are polled on)"
          % (FULL, i2c_cost.wire_ms(FULL), TICK * 1000))
    for label, states, view in scenarios(n):
        bad = verify(states, view)
        if bad >= 0:
            print("\n%s\n  LOSSY: panel != frame at tick %d -- driver bug" % (label, bad))
            continue
        per, _ = measure(states, view)
        report(label, per)
        print("  lossless     : panel framebuffer == drawn frame on all %d ticks" % n)


if __name__ == "__main__":
    main(sys.argv[1:])
