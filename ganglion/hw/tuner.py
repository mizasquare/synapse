"""Guitar tuner (① 기능) — synapse's cochlea engine, driven on demand.

The same **inbound** seam shape as ``hw/meter.py``: ``power``/``settings``/
``radio`` push a value from the state out to hardware, this and the meter pull a
fact from the world in. The difference from the meter is lifetime — the meter
runs for the life of the process, this one only while ``st.tuner`` is up:

    enter tuner  -> st.tuner True  -> observe() builds + starts the engine
    leave tuner  -> st.tuner False -> observe() stops + drops it

so the JACK client and its DSP thread exist only during tuning. That is not a
micro-optimization but the safety of the thing: the engine opens its own
``jack.Client`` on ``system:capture_1``, and the one moment we can be sure the
rig is **not** carrying a live performance is while its player is tuning. (This
is also why decision H's "monitorfeed is a prerequisite" was wrong — the tuner
never touched monitorfeed; it taps capture directly, same as the meter.)

The engine is ``cochlea.TunerEngine`` (RingBuffer + NSDF/HPS pitch + a One-Euro
filter and note-lock hysteresis for needle feel), imported from synapse and used
verbatim — pure-layer reuse, 0 core edits, the app's whole reason to share the
repo. Its consumer API is one call, ``get_reading()``, returning a stable
``TunerReading`` or **None** when there is nothing to show (silence, low
confidence, or a stale frame). That None is not an error: it is the "listening"
state, and the view has to say so rather than freeze on the last note — a tuner
that shows "E2 / +3" at a silent input is lying exactly the way a meter that
invents -14.2 dB is (see ``hw/meter.py``). So None -> ``st.tlisten = True``.

**Attach is lazy and retried**, for the same reason the meter's is: this is a
boot service and jackd came up ~198ms after ganglion at the last boot (the race
is documented in ``hw/meter.py``). ``TunerEngine.start()`` raises if JACK is
absent, so a dev box or a too-early entry just leaves ``tlisten`` on and tries
again ``RETRY_S`` later — the loop already owns the clock (``st.t``).

Never raises: a tuner that takes the UI down with it is worse than one stuck on
"listening". Every JACK edge is wrapped, and a dead engine degrades to None.
"""


def _attach(string_set):
    from cochlea import TunerEngine, JackSource   # lazy: entry points put the
    return TunerEngine(JackSource(), string_set=string_set)  # synapse root on path


class Tuner:
    """``observe(st)`` — while ``st.tuner``, writes ``st.tnote`` / ``st.tcents``
    from live pitch, or sets ``st.tlisten`` when there is nothing to read.

    Injection: ``make`` returns a started-on-``.start()`` engine exposing
    ``get_reading()`` / ``start()`` / ``stop()``. Production leaves it None and
    attaches ``cochlea`` lazily; tests pass a fake to exercise the edges without
    JACK. ``string_set`` picks the open-string reference set (guitar here).
    """

    RETRY_S = 3.0

    def __init__(self, make=None, string_set="guitar"):
        if make is None:
            make = lambda: _attach(string_set)   # noqa: E731 — one line, one use
        self._make = make
        self.engine = None
        self._retry_at = 0.0

    @property
    def ok(self):
        return self.engine is not None

    def observe(self, st):
        if not st.tuner:                 # not tuning (or just left) -> engine idle
            self.stop()
            return
        if self.engine is None:
            if st.t < self._retry_at:    # jackd/dev box: don't hammer the attach
                st.tlisten = True
                return
            self._retry_at = st.t + self.RETRY_S
            try:
                eng = self._make()
                eng.start()
            except Exception:
                st.tlisten = True        # JACK absent; the header says "listening"
                return
            self.engine = eng
        try:
            r = self.engine.get_reading()
        except Exception:
            r = None                     # a dead engine must not stop the UI
        if r is None:
            st.tlisten = True            # silence / low confidence / stale frame;
            return                       # leave the last note frozen (it's hidden)
        st.tlisten = False
        st.tnote = r.note                # "E2" — pitch class + octave (two E's)
        st.tcents = int(round(r.cents))  # -50..+50, the needle reads this

    def stop(self):
        eng, self.engine = self.engine, None
        if eng is not None:
            try:
                eng.stop()
            except Exception:
                pass
