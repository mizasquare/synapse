"""Off-device reflex pedal service: the real protocol over a synthetic pedal.

Instead of re-implementing the management protocol, this drives the actual
``reflex.ReflexState`` + ``handle_request`` (both pure stdlib) in-process, so
the pedal CONFIG leaf exercises the exact same capture/save/mapping semantics
the on-device service runs — only the ADS1115 read loop is replaced:

- ch0 (volume): a triangle sweep between simulated *true* pedal endpoints that
  sit inside the default calibration, as if someone were slowly rocking the
  pedal heel<->toe. Capturing at the sweep's ends therefore lands a tighter
  calibration than the default — the wizard's effect is visible.
- ch1 (expression): pinned at the pull-up ceiling, i.e. an unplugged jack
  (measured behaviour: open input floats above any calibrated toe), so the
  detached-state UI is always on display in the mock.

Calibration/mapping persist under ``configs.LOCAL_STORAGE`` (qt_dev points that
at ~/.modep-dev/), mirroring the service's own file layout without touching a
real box's files.
"""

import math
import os
import time

import configs
from reflex import ReflexState, handle_request, map_value
from reflexclient import ReflexClient

_SWEEP_PERIOD = 4.0     # seconds per heel->toe->heel round trip
_TRUE_HEEL = 900        # the synthetic pedal's real endpoints (inside the
_TRUE_TOE = 16400       # default cal 150/17700, so re-calibration tightens)
_PULLUP_RAW = 26100     # open-jack float, above any calibrated toe


class FakeReflexClient(ReflexClient):
    """Same call surface as ReflexClient; requests go to an in-process
    ReflexState fed by the synthetic sweep instead of over a socket."""

    def __init__(self):
        base = configs.LOCAL_STORAGE
        os.makedirs(base, exist_ok=True)
        self._state = ReflexState(
            cal_path=os.path.join(base, "pedal_calibration.json"),
            mapping_path=os.path.join(base, "reflex.json"))
        self._t0 = time.monotonic()

    def _tick(self):
        """What the service's read loop would have written since last request:
        current raw per channel + the CC each axis is emitting under the
        current calibration."""
        t = (time.monotonic() - self._t0) / _SWEEP_PERIOD
        frac = 1.0 - abs(2.0 * (t - math.floor(t)) - 1.0)   # triangle 0..1..0
        with self._state.lock:
            self._state.raw[0] = int(_TRUE_HEEL + frac * (_TRUE_TOE - _TRUE_HEEL))
            self._state.raw[1] = _PULLUP_RAW
            for ch, axis in ((0, "volume"), (1, "expression")):
                cal = self._state.cal[ch]
                self._state.midi[axis] = map_value(
                    self._state.raw[ch], cal["in_min"], cal["in_max"])
            self._state.midi_port = "GAAD67 (fake)"

    def _request(self, payload):
        self._tick()
        return handle_request(self._state, payload)
