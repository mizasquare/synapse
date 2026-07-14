#!/usr/bin/env python3
"""Off-device selftest for the pedal CONFIG layer (the app side of reflex).

Complements tests/reflex_selftest.py (which covers the service itself): this
exercises the new app-side stack the pedal CONFIG leaf sits on — the
FakeReflexClient (real ReflexState/handle_request over a synthetic pedal),
presenter.pedal_status's per-axis normalisation + plugged/unplugged judgement,
the capture->save calibration flow, and CC remapping with channel preserved.

Run:  python tests/pedalconfig_selftest.py
"""
import os
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Isolate persistence before configs is imported (transitively via presenter).
os.environ["SYNAPSE_STATE_DIR"] = tempfile.mkdtemp(prefix="pedalcfg-")

from fakereflex import (FakeReflexClient, _SWEEP_PERIOD,
                        _TRUE_HEEL, _TRUE_TOE)
from presenter import Presenter

FAILURES = []


def check(name, cond, detail=""):
    print("%s %s%s" % ("PASS" if cond else "FAIL", name,
                       "" if cond else "  [%s]" % (detail,)))
    if not cond:
        FAILURES.append(name)


def make_shim(client):
    """The minimal presenter surface pedal_* methods touch — lets the unbound
    Presenter methods run without building the whole app stack."""
    ns = SimpleNamespace(_reflex=client, _reflex_factory=None,
                         PEDAL_UNPLUG_FACTOR=Presenter.PEDAL_UNPLUG_FACTOR,
                         toasts=[])
    ns._notify = lambda t: ns.toasts.append(t)
    ns._reflex_client = lambda: ns._reflex
    return ns


def test_status(ns):
    st = Presenter.pedal_status(ns)
    check("status avail", st["avail"])
    vol, ex = st["axes"][0], st["axes"][1]
    check("volume axis connected", vol["state"] == "ok", vol)
    check("expression axis unplugged (pull-up float)", ex["state"] == "unplugged", ex)
    check("default CCs 102/103", vol["cc"] == 102 and ex["cc"] == 103,
          (vol["cc"], ex["cc"]))
    check("unplugged pins CC 127 (unity)", ex["midi"] == 127, ex["midi"])
    check("no pending before capture", vol["pendHeel"] < 0 and vol["pendToe"] < 0)


def test_calibration_flow(ns):
    c = ns._reflex
    c._t0 = time.monotonic()                      # sweep phase 0 -> heel end
    check("capture heel ok", Presenter.pedal_capture(ns, 0, "heel"))
    c._t0 = time.monotonic() - _SWEEP_PERIOD / 2  # phase 0.5 -> toe end
    check("capture toe ok", Presenter.pedal_capture(ns, 0, "toe"))
    vol = Presenter.pedal_status(ns)["axes"][0]
    check("pending surfaced to the leaf",
          vol["pendHeel"] >= 0 and vol["pendToe"] >= 0, vol)
    check("save ok", Presenter.pedal_save(ns))
    check("save toasted", len(ns.toasts) == 1, ns.toasts)
    vol = Presenter.pedal_status(ns)["axes"][0]
    span = _TRUE_TOE - _TRUE_HEEL
    check("cal tightened to the captured ends (inward margin)",
          _TRUE_HEEL <= vol["lo"] and vol["hi"] <= _TRUE_TOE
          and (vol["hi"] - vol["lo"]) > span * 0.9, (vol["lo"], vol["hi"]))
    st2 = FakeReflexClient().get_status()         # fresh client -> reads the file
    check("cal persisted across clients",
          int(st2["calibration"]["0"]["in_min"]) == vol["lo"], st2["calibration"])


def test_set_cc(ns):
    check("set cc ok", Presenter.pedal_set_cc(ns, "volume", 110))
    st = Presenter.pedal_status(ns)
    check("cc applied", st["axes"][0]["cc"] == 110, st["axes"][0])
    check("midi channel preserved",
          ns._reflex._state.mapping["volume"]["channel"] == 0)
    check("unknown axis rejected + toasted",
          not Presenter.pedal_set_cc(ns, "tremolo", 110) and len(ns.toasts) >= 2)


def test_unreachable():
    class DeadClient:
        def get_status(self):
            return None   # service down: every request times out to None
    ns = make_shim(DeadClient())
    st = Presenter.pedal_status(ns)
    check("unreachable service -> avail False",
          st == {"avail": False, "axes": []}, st)


if __name__ == "__main__":
    shim = make_shim(FakeReflexClient())
    test_status(shim)
    test_calibration_flow(shim)
    test_set_cc(shim)
    test_unreachable()
    print("\n%d failures" % len(FAILURES))
    sys.exit(1 if FAILURES else 0)
