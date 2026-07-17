"""IN/OUT header level (decision H) — synapse's JACK level meter, adapted.

The seam ``Runtime`` drives. Note the direction: ``power``/``settings``/``radio``
push a value from the state **out** to hardware, this pulls a fact from the world
**in** to the state — the same shape as ``st.t``, and the only other inbound seam
besides input itself.

The meter is ``levelmeter.LevelMeter``, imported from synapse and used verbatim
(pure-layer reuse, 0 core edits): it owns a ``jack.Client`` that taps
``system:capture_1/2`` for IN, and — because ``system:playback`` is a SINK and
cannot be read — mirrors whatever feeds playback for OUT, re-tapping when the
graph moves. Verified on GECO: ``in_l <- system:capture_1``,
``out_l <- mod-monitor:out_1`` (MODEP's master monitor sits in front of playback,
so the mirror finds it, not the chain's last effect).

Decision H recorded the source as ``monitorfeed.py``. That was wrong and cost a
detour: monitorfeed carries mod-ui's ``output_set``, i.e. LV2 output ports of
plugins *in the chain*, which is a different thing from the rig's IN/OUT.

**Why the peak and not the live amplitude.** ``snapshot()`` returns both; synapse's
``pack()`` puts the live amp on the *bar* and the 5-second window peak on the *dB
text*, and this is text. The live value wobbles every tick (measured at silence:
-59.2 / -59.9 / -60.2 ...), which would repaint the header band on the wire each
time and flicker the last digit; the peak sits still. Matching synapse is also the
cheap choice.

**Why this lives in-process** — and why the answer took three wrong turns.

Attaching it cost the rig 688 xruns/10min, 97% of its total, and made the rig's
own plugins 3.7x later (jackd waits for every client). Two explanations were
written into this file and both were wrong: first "``render`` holds 8.7ms of GIL"
(decision X fixed that, and the meter still broke), then "``source.poll()`` holds
the GIL every tick" — named by elimination, never measured.

It was neither. The client **could not get real-time scheduling**, because
``LimitRTPRIO`` is a systemd unit setting and ``limits.conf`` only ever reaches PAM
sessions. It ran SCHED_OTHER, the one non-FIFO client in a sync (``-S``) graph. The
journal said so at startup and was read eight hours late. Two lines in the unit
took it to 22/10min — the rig's own baseline — and the callback thread is now
``SCHED_FIFO 90``. See ``deploy/ganglion-service/ganglion.service`` and decisions X.

So the GIL was never the constraint here, and the numbers say why: this callback
costs **0.025ms, 0.9% of the 2.67ms period**, and triggers no GC at all (it frees
what it allocates, so gen0 never trips). ``tools/gil_probe`` puts the loop's GIL
lateness at the idle-sleep floor.

Nothing measurable remains. On an idle rig this meter's cost is indistinguishable
from zero -- 47 minutes clean with it off, two 11-minute stretches clean with it on.
Every xrun we did see clustered on **our own development load** (test suites, hours
of journal scanning, the probe itself); the "22/10min residual" first written here
was a startup transient measured a minute after the service came up, and its
"unexplained floor" was us. See decisions X, methodology (9) — to measure the rig,
only the rig may be running.
"""

import math


def db(amp):
    """Linear amplitude -> dB, or None below the floor (synapse's _meter_display).

    ``20*log10(0)`` is -inf and 1e-6 is -120dB — past any real signal — so both
    read as "nothing", which the view draws as "--" rather than a made-up number.
    """
    return None if amp is None or amp <= 1e-6 else 20.0 * math.log10(amp)


def _attach(name):
    from levelmeter import LevelMeter        # lazy: only entry points put the
    return LevelMeter(name)                  # synapse root on sys.path


class Meter:
    """``observe(st)`` -> writes ``st.inlvl`` / ``st.outlvl`` in dB (or None).

    Never raises: a rig whose display dies because the meter did is a worse rig
    than one showing "--". ``LevelMeter`` already degrades to ``ok=False`` when
    jack/numpy are missing, and ``snapshot()`` then returns None.

    **It attaches late, and keeps trying.** ``LevelMeter`` tries JACK exactly once
    in its constructor; miss, and ``ok`` is False for the life of the process. That
    is fine for synapse (a desktop app a human starts) and wrong here, because this
    is a boot service and the race is real — measured on this box:

        22:27:38.201  Started jack.service            <- systemd calls it started
        22:27:38.490  Started ganglion.service        <- we start
        22:27:38.688  jackdrc: JACK server starting   <- jackd actually comes up

    ``After=`` orders starts, not readiness (the unit file says so about mod-host).
    Ganglion survived that boot only by luck: ``Restart=always`` bounced it twice
    more while mod-host was unready, and the third try landed after jackd was up.
    Correctness that depends on crashing enough times is not correctness, so retry
    here instead. The clock is ``st.t`` — the loop already owns time (decision J),
    and this seam is handed the state anyway.
    """

    RETRY_S = 3.0

    def __init__(self, src=None, name="GangMeter", make=None):
        # No src and no maker => production: attach lazily and retry. An injected
        # src is taken as final (tests pin a specific state and must not have it
        # swapped out underneath them); inject `make` to exercise the retry.
        if src is None and make is None:
            make = lambda: _attach(name)     # noqa: E731 — one line, one use
        self.src = src
        self._make = make
        self._retry_at = 0.0

    @property
    def ok(self):
        return bool(self.src is not None and getattr(self.src, "ok", False))

    def observe(self, st):
        if not self.ok:
            if self._make is None or st.t < self._retry_at:
                return
            self._retry_at = st.t + self.RETRY_S
            try:
                src = self._make()
            except Exception:
                return                       # JACK still absent; try again later
            if getattr(src, "ok", False):
                self.src = src               # only keep a client that attached --
            else:                            # a dead one would just mask the retry
                try:
                    src.stop()
                except Exception:
                    pass
                return
        try:
            snap = self.src.snapshot()
        except Exception:
            snap = None                      # a dead client must not stop the UI
        if not snap:
            return                           # keep the last reading; never lie
        st.inlvl = db(snap.get("in_peak_amp"))
        st.outlvl = db(snap.get("out_peak_amp"))

    def stop(self):
        try:
            if self.src is not None:
                self.src.stop()
        except Exception:
            pass
