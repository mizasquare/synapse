"""Per-segment GIL-hold probe for the device loop (roadmap ④; decision X 정정).

Decision X measured ``render``'s GIL and read it as *the loop's*. It was not, and
the correction named ``source.poll()`` -- two seesaw encoders over I2C every tick,
outside the blank guard -- as the real holder. But it named it by **elimination**
(the xrun rate was unchanged with the panel dark and nothing drawing), never by
measurement. Elimination is how X went wrong in the first place. This measures it.

**The canary is the meter that isn't there.** A JACK process callback is a cffi
callback: it must take the GIL every 2.67ms (``-p 128 -r 48000`` on this box), and
jackd here is sync (``-S``), so late == the whole graph is late. Rather than attach
a real client and pay the rig another 688 xruns to learn the same fact, a plain
Python thread wakes on that same cadence and records how late it actually got to
run. Lateness *is* GIL wait -- JACK's ``SCHED_FIFO 95`` buys it nothing, because
RT priority does not jump the GIL queue. **No JACK client here, so no audio risk.**

Attribution is post-hoc rather than deduced: the loop timestamps its own segments
(``poll`` / ``draw`` / ``rest`` / ``sleep``) and each canary sample is charged to
whichever segment was running **at the deadline it missed** -- not at the moment it
woke, which would instead credit whoever happened to release the GIL last.

``sleep`` is the built-in control. The loop is asleep (GIL released) for most of
the tick, so lateness charged there is the probe's own floor -- scheduler jitter,
not contention. A segment only accuses itself if it is worse than that floor.

**The probe can fail, so make it.** ``--inject-ms N --inject-seg S`` burns a known
N ms of pure-Python bytecode (i.e. real GIL) inside segment S. If the report does
not charge ~N ms to S, the probe is broken and its zeros mean nothing. Run that
once before believing a quiet result: X's lesson was a probe that measured the
wrong thing, and the lesson before it was a test that could not fail.

Note ``fcntl.ioctl`` (which is what blinka reaches through ``Adafruit_PureIO``)
releases the GIL around the syscall, so I2C **wire** time is not GIL time. What
this can still charge to ``poll`` is the Python between the ioctls -- the seesaw
register protocol and ctypes marshalling. Whether that is 0.1ms or 3ms is the
whole question, and it decides whether a C I2C shim would buy anything at all.

Run (stop ganglion.service first -- it owns /dev/i2c-1):
  venv/bin/python -m ganglion.tools.gil_probe --secs 60
  venv/bin/python -m ganglion.tools.gil_probe --secs 20 --inject-ms 8 --inject-seg poll
"""

import argparse
import bisect
import threading
import time
from collections import defaultdict

PERIOD = 128 / 48000.0          # jackd -p 128 -r 48000 = 2.67ms, the RT deadline


def _burn(ms):
    """Hold the GIL for ~``ms`` of pure bytecode -- the injected fault."""
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        pass


class Probe:
    def __init__(self, period=PERIOD):
        self.period = period
        self.spans = []              # (t0, t1, name) -- written by the loop thread
        self.samples = []            # (deadline, lateness) -- by the canary thread
        self._open = None
        self._stop = threading.Event()
        self._thread = None

    # ------------------------------------------------------------ loop thread
    def mark(self, name):
        """Close the open span and open ``name`` (None just closes)."""
        t = time.perf_counter()
        if self._open is not None:
            self.spans.append((self._open[1], t, self._open[0]))
        self._open = (name, t) if name else None

    # ---------------------------------------------------------- canary thread
    def _canary(self):
        nxt = time.perf_counter() + self.period
        while not self._stop.is_set():
            d = nxt - time.perf_counter()
            if d > 0:
                time.sleep(d)        # releases the GIL; waking must re-take it
            woke = time.perf_counter()
            self.samples.append((nxt, woke - nxt))
            # Re-anchor instead of catching up: a late jackd doesn't run twice.
            nxt = woke + self.period

    def start(self):
        self._thread = threading.Thread(target=self._canary, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.mark(None)

    # ----------------------------------------------------------------- report
    def report(self):
        spans = sorted(self.spans)
        starts = [s[0] for s in spans]
        wall = defaultdict(list)
        for t0, t1, name in spans:
            wall[name].append((t1 - t0) * 1000.0)

        late = defaultdict(list)
        unattributed = 0
        for deadline, lateness in self.samples:
            i = bisect.bisect_right(starts, deadline) - 1
            if i < 0 or deadline > spans[i][1]:
                unattributed += 1      # deadline fell outside the loop (startup)
                continue
            late[spans[i][2]].append(lateness * 1000.0)

        span_s = (spans[-1][1] - spans[0][0]) if spans else 0.0
        misses = [x for xs in late.values() for x in xs if x > self.period * 1000.0]
        print("\n=== GIL probe: %.1fs, %d canary samples @ %.2fms, %d spans ==="
              % (span_s, len(self.samples), self.period * 1000.0, len(spans)))
        print("%-8s %7s %9s %9s %9s | %7s %9s %9s %9s %8s"
              % ("segment", "ticks", "wall_p50", "wall_p95", "wall_max",
                 "canary", "late_p50", "late_p95", "late_max", ">%.2fms" % (self.period * 1000.0)))
        for name in ("poll", "draw", "rest", "sleep"):
            w, l = _stats(wall.get(name)), _stats(late.get(name))
            if w is None and l is None:
                continue
            over = sum(1 for x in late.get(name, []) if x > self.period * 1000.0)
            print("%-8s %7s %9s %9s %9s | %7s %9s %9s %9s %8s"
                  % (name,
                     w["n"] if w else "-", _f(w, "p50"), _f(w, "p95"), _f(w, "max"),
                     l["n"] if l else "-", _f(l, "p50"), _f(l, "p95"), _f(l, "max"),
                     over))
        if unattributed:
            print("(%d samples outside any span -- startup/teardown, ignored)" % unattributed)
        rate = len(misses) / span_s if span_s else 0.0
        print("\nmissed deadlines: %d in %.1fs = **%.2f/s**  (the rig measured 1.23/s"
              " of real xruns with the meter attached; ~0.03/s without)" % (len(misses), span_s, rate))
        print("read `sleep` as the floor: it is the loop with the GIL released.\n")


def _stats(xs):
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return {"n": n, "p50": xs[n // 2], "p95": xs[min(n - 1, int(n * 0.95))], "max": xs[-1]}


def _f(s, k):
    return "-" if s is None else "%.3f" % s[k]


def install(probe, secs, inject_ms=0.0, inject_seg=None):
    """Wrap the loop's seams in place -- the app itself is not edited."""
    from ganglion import runtime as R
    from ganglion.hw.seesaw import SeesawInput

    def _wrap(name, fn):
        def inner(self, *a, **kw):
            probe.mark(name)
            try:
                return fn(self, *a, **kw)
            finally:
                if inject_seg == name and inject_ms:
                    _burn(inject_ms)       # charged to `name`: mark() comes after
                probe.mark("rest")
        return inner

    SeesawInput.poll = _wrap("poll", SeesawInput.poll)
    R.Runtime._draw = _wrap("draw", R.Runtime._draw)

    orig_init = R.Runtime.__init__
    def __init__(self, *a, **kw):
        orig_init(self, *a, **kw)
        real_sleep = self.sleep
        def sleep(d):
            probe.mark("sleep")
            try:
                real_sleep(d)
            finally:
                probe.mark("rest")
        self.sleep = sleep
    R.Runtime.__init__ = __init__

    orig_step = R.Runtime.step
    def step(self):
        probe.mark("rest")
        return orig_step(self)
    R.Runtime.step = step

    orig_run = R.Runtime.run
    def run(self, should_stop=lambda: False):
        end = time.perf_counter() + secs
        probe.start()
        try:
            orig_run(self, should_stop=lambda: time.perf_counter() >= end)
        finally:
            probe.stop()
    R.Runtime.run = run


def _refuse_if_not_alone():
    """Refuse to run beside the service. This is not caution, it is a guard.

    Two readers on one I2C bus is not a contended measurement, it is a phantom
    gesture generator: on 2026-07-17 this probe ran while ``ganglion.service`` was
    still up, both polled the seesaws, the garbage decoded as ENC0+ENC1 -- and
    ``AppController.combo`` is the *global snapshot save*. It fired repeatedly and
    overwrote the live ``Drive_0.pedalboard`` (no data lost, by luck: the board was
    unmodified since load). ``systemctl is-active`` had already answered ``active``
    in the operator's own output and was read past. So the check moves here, where
    it cannot be read past.
    """
    import subprocess
    try:
        out = subprocess.run(["systemctl", "is-active", "ganglion"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        out = "unknown"          # no systemd (dev box): fall through to the pgrep
    if out == "active":
        raise SystemExit(
            "REFUSING: ganglion.service is active and owns /dev/i2c-1.\n"
            "  sudo systemctl stop ganglion\n"
            "Two readers on one bus produce phantom gestures, and combo() persists\n"
            "the snapshot -- this would overwrite the live pedalboard.")
    other = subprocess.run(["pgrep", "-fa", "app.py --device"],
                           capture_output=True, text=True).stdout.strip()
    if other:
        raise SystemExit("REFUSING: another --device instance is already running:\n" + other)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--secs", type=float, default=60.0)
    ap.add_argument("--inject-ms", type=float, default=0.0,
                    help="burn this much known GIL in --inject-seg (probe self-test)")
    ap.add_argument("--inject-seg", default="poll", choices=("poll", "draw"))
    ap.add_argument("--no-live", action="store_true",
                    help="skip the GecoAdapter backend (the service runs --live)")
    args = ap.parse_args(argv)
    _refuse_if_not_alone()

    probe = Probe()
    install(probe, args.secs, args.inject_ms,
            args.inject_seg if args.inject_ms else None)

    from ganglion import app
    app.main(["--device"] + ([] if args.no_live else ["--live"]))
    probe.report()


if __name__ == "__main__":
    main()
