"""Master-volume control: send MIDI CC7 to the jack_mix_box gain stage ("synapsevol").

The actual gain lives in an independent JACK client (the synapse-mastervol systemd
service inserts jack_mix_box into mod-monitor -> system:playback). synapse only
*controls* it, here, by emitting MIDI CC7 into its "midi in" port. Keeping the audio
path out of this process means a GUI crash never kills the sound -- the mixer holds
its last gain.

MIDI writes must happen inside JACK's process callback, so the GUI thread just parks
a target value (0-127) and the callback emits a CC when it changes. Connecting to the
gain client is retried lazily (set_percent), since the service may come up after us.
"""
import logging
import math

try:
    import jack
except Exception:                       # off-device / no JACK -> no-op controller
    jack = None

log = logging.getLogger(__name__)

_CC = 7                                  # CC7 = Channel Volume
_STATUS = 0xB0                           # Control Change, MIDI channel 1
_DEST = "synapsevol:midi in"            # jack_mix_box "midi in" (name from the service)

# jack_mix_box's fader is linear in dB with CC127 = 0 dB (unity). Measured
# empirically (2026-07, 256/48k): dB ~= 0.5545*CC - 70.4, i.e. ~0.5545 dB per CC
# step, CC0 = mute. We invert that to turn a wanted dB into a CC. Recalibrate
# these two numbers if the jack_mixer build changes its scale.
_DB_PER_CC = 0.5545
_CC_UNITY = 127

# Slider taper: amplitude = (pct/100) ** _TAPER_EXP, then -> dB -> CC. A plain
# linear pct->CC felt far too quiet in the middle (50% landed at ~-35 dB), because
# the CC axis is already dB. Shaping amplitude instead gives a natural volume law:
#   EXP 1.0 = linear amplitude (50% -> -6 dB),  2.0 = square law (50% -> -12 dB).
# Bump toward 1.0 for a louder middle, toward 3.0 for finer low-level control.
_TAPER_EXP = 2.0


def _pct_to_cc(pct):
    """Map a 0-100 slider position to a jack_mix_box CC via an amplitude taper."""
    pct = max(0.0, min(100.0, float(pct)))
    if pct <= 0.0:
        return 0                                   # full mute
    if pct >= 100.0:
        return _CC_UNITY                           # unity (0 dB)
    amp = (pct / 100.0) ** _TAPER_EXP
    db = 20.0 * math.log10(amp)
    return max(0, min(127, round(_CC_UNITY + db / _DB_PER_CC)))


class MasterVolume:
    """Sends CC7 to the gain client. `available()` is False when JACK or the gain
    client isn't there, so the UI can grey the slider out."""

    def __init__(self, name="SynapseMasterVol", dest=_DEST, default_pct=100):
        self._dest = dest
        self._pct = max(0, min(100, int(default_pct)))   # slider truth (0-100)
        self._target = _pct_to_cc(self._pct)             # CC actually driven
        self._last = -1                  # last CC actually emitted (-1 = force send)
        self._client = None
        self._out = None
        self._ok = False
        if jack is None:
            return
        try:
            self._client = jack.Client(name, no_start_server=True)
            self._out = self._client.midi_outports.register("out")

            @self._client.set_process_callback
            def _process(_frames):
                self._out.clear_buffer()
                t = self._target            # atomic read of an int
                if t != self._last:
                    self._out.write_midi_event(0, bytes([_STATUS, _CC, t & 0x7F]))
                    self._last = t

            self._client.activate()
            self._ok = True
            self._try_connect()
        except Exception as exc:
            log.warning("MasterVolume init failed (%s); volume control disabled", exc)
            self._ok = False

    def _try_connect(self):
        """Connect out -> gain client if not already. Returns True when connected.
        Resets _last so the current target is (re)sent on a fresh connection."""
        if not self._ok:
            return False
        try:
            dst = self._client.get_port_by_name(self._dest)
        except Exception:
            return False                 # gain client not up yet
        try:
            if dst in self._out.connections:
                return True
            self._client.connect(self._out, dst)
            self._last = -1              # force a resend onto the new link
            return True
        except Exception as exc:
            log.debug("MasterVolume connect deferred: %s", exc)
            return False

    def available(self):
        return self._try_connect()

    def set_percent(self, pct):
        """Park a 0-100 target (tapered to a CC); the process callback emits CC7."""
        self._pct = max(0, min(100, int(pct)))
        self._target = _pct_to_cc(self._pct)
        self._try_connect()              # (re)establish if the service came up late
        return self._pct

    def get_percent(self):
        """App-side truth: the slider position we're driving (synapse owns the
        master). Returns the pct, not a CC-derived value, so the taper round-trips."""
        return self._pct

    def close(self):
        try:
            if self._client:
                self._client.deactivate()
                self._client.close()
        except Exception:
            pass
