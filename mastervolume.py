"""Master-volume *controller*: a dumb MIDI fader talking to synapse-volume.

Volume authority lives in the synapse-volume control daemon (the box's system
volume device — deploy/volume-service/volumectl.py). It owns the taper and the
private CC7 link into the jack_mix_box gain stage; keeping the audio path and
the volume law out of this process means a GUI crash never kills the sound OR
the pedal's volume control.

This class is therefore just another controller on that device, like the
reflex pedal:
- sends raw linear CC (0-127, no taper) to "synapse-volume:control in" over a
  direct JACK link;
- subscribes to "synapse-volume:state out" for the applied-state echo (the
  motorized-fader feedback idiom), so the slider follows pedal moves and gets
  the current value on (re)connect without asking.

MIDI writes/reads must happen inside JACK's process callback, so the GUI
thread just parks a target and polls the parked echo (poll_echo) — the qtview
ticker marshals it into the QML slider. Connecting is retried lazily
(set_percent/available), since the service may come up after us.
"""
import logging

try:
    import jack
except Exception:                       # off-device / no JACK -> no-op controller
    jack = None

log = logging.getLogger(__name__)

_CC = 102                                # raw volume command (synapse-volume's listen CC)
_STATUS = 0xB0                           # Control Change, MIDI channel 1
_DEST = "synapse-volume:control in"      # commands go here (direct link)
_SRC = "synapse-volume:state out"        # applied-state echo comes from here


def _pct_to_raw(pct):
    """0-100 slider position -> raw linear CC (the daemon applies the taper)."""
    pct = max(0, min(100, int(pct)))
    return round(pct * 127 / 100)


def _raw_to_pct(raw):
    return round(max(0, min(127, int(raw))) * 100 / 127)


class MasterVolume:
    """Raw-CC controller + state subscriber for the synapse-volume daemon.
    `available()` is False when JACK or the daemon isn't there, so the UI can
    grey the slider out."""

    def __init__(self, name="SynapseMasterVol", dest=_DEST, src=_SRC, default_pct=100):
        self._dest = dest
        self._src = src
        self._pct = max(0, min(100, int(default_pct)))   # last commanded/echoed pct
        self._target = _pct_to_raw(self._pct)            # raw CC actually driven
        self._last = -1                  # last CC actually emitted (-1 = force send)
        self._echo = -1                  # last raw echoed by the daemon (RT-parked)
        self._echo_seen = -1             # last echo consumed by poll_echo()
        self._client = None
        self._out = None
        self._in = None
        self._ok = False
        if jack is None:
            return
        try:
            self._client = jack.Client(name, no_start_server=True)
            self._out = self._client.midi_outports.register("out")
            self._in = self._client.midi_inports.register("in")

            @self._client.set_process_callback
            def _process(_frames):
                self._out.clear_buffer()
                t = self._target            # atomic read of an int
                if t != self._last:
                    self._out.write_midi_event(0, bytes([_STATUS, _CC, t & 0x7F]))
                    self._last = t
                for _offset, data in self._in.incoming_midi_events():
                    if len(data) == 3:
                        b = bytes(data)
                        if b[0] & 0xF0 == _STATUS and b[1] == _CC:
                            self._echo = b[2] & 0x7F   # park; GUI ticker collects

            self._client.activate()
            self._ok = True
            self._try_connect()
        except Exception as exc:
            log.warning("MasterVolume init failed (%s); volume control disabled", exc)
            self._ok = False

    def _try_connect(self):
        """Connect out -> daemon and daemon echo -> in, if not already.
        Returns True when the command link is up. Resets _last so the current
        target is (re)sent on a fresh connection."""
        if not self._ok:
            return False
        try:
            dst = self._client.get_port_by_name(self._dest)
        except Exception:
            return False                 # daemon not up yet
        try:
            src = self._client.get_port_by_name(self._src)
            if src not in self._in.connections:
                self._client.connect(src, self._in)
        except Exception:
            pass                         # echo is best-effort; commands still work
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
        """Park a 0-100 target as a raw CC; the process callback emits it."""
        self._pct = max(0, min(100, int(pct)))
        self._target = _pct_to_raw(self._pct)
        self._try_connect()              # (re)establish if the service came up late
        return self._pct

    def get_percent(self):
        """Best current truth: the last daemon echo if one arrived (any
        controller may have moved the volume), else the last commanded pct."""
        if self._echo >= 0:
            return _raw_to_pct(self._echo)
        return self._pct

    def poll_echo(self):
        """Consume a fresh daemon echo: returns the new pct, or None if the
        applied state hasn't changed since the last poll. Called by the GUI
        ticker (the RT callback only parks the int)."""
        e = self._echo
        if e < 0 or e == self._echo_seen:
            return None
        self._echo_seen = e
        self._pct = _raw_to_pct(e)
        return self._pct

    def close(self):
        try:
            if self._client:
                self._client.deactivate()
                self._client.close()
        except Exception:
            pass
