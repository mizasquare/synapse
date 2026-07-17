"""WiFi and Bluetooth — the app's first radios, driven from the pure state.

Shaped exactly like ``hw.oled.PanelPower``: the Runtime hands it the user's
choice every tick, and it does nothing at all unless that choice moved. The pure
controller never learns that ``nmcli`` exists.

**Nothing here blocks the loop.** ``nmcli con up`` can take many seconds to
associate, and the loop it would block polls the encoders at 33Hz on the bus the
panel shares — a freeze there is a dead UI *and* dead knobs for the whole
association. So a change fires a worker thread and returns immediately. Nothing
waits for the result and nothing reads the radio back: the UI shows what you
**chose**, which is the same contract brightness has (we never read the panel's
contrast back either). Failures go to the log.

Two different mechanisms, each for a reason:

  - **Bluetooth = rfkill.** on/off is all it has and rfkill does exactly that.
    `miza` is in `netdev`, and a *group* grant survives the sessionless service
    context that defeats polkit's ``allow_active`` — so this needs no rule.
  - **WiFi = nmcli.** rfkill cannot make an access point, and ``hotspot`` is one
    of the three states, so NetworkManager is unavoidable — and with it polkit.
    See ``deploy/ganglion-service/50-ganglion-radio.rules``, which grants the
    three actions this module needs and nothing more.
"""

import logging
import subprocess
import threading

from ganglion.config import HOTSPOT_CON


def _wifi_cmds(state):
    """``(argv, must_succeed)`` for each step of reaching ``state``.

    Going to ``on`` downs the hotspot **tolerantly**: coming from ``off`` it was
    never up, and nmcli calls that an error. What it does *not* do is name a
    client SSID — autoconnect picks one, so this works in a room the code has
    never heard of.
    """
    if state == "off":
        return [(["nmcli", "radio", "wifi", "off"], True)]
    if state == "hotspot":
        return [(["nmcli", "radio", "wifi", "on"], True),
                (["nmcli", "con", "up", HOTSPOT_CON], True)]
    return [(["nmcli", "radio", "wifi", "on"], True),
            (["nmcli", "con", "down", HOTSPOT_CON], False)]


def _bt_cmds(state):
    return [(["rfkill", "unblock" if state == "on" else "block", "bluetooth"], True)]


def _spawn(steps, what):
    """Run the steps on a worker thread; never make the caller wait."""

    def work():
        for argv, must in steps:
            try:
                r = subprocess.run(argv, capture_output=True, text=True, timeout=45)
            except (OSError, subprocess.TimeoutExpired) as e:
                logging.warning("ganglion radio: %s: %s (%s)", what, argv[0], e)
                return
            if r.returncode and must:
                logging.warning("ganglion radio: %s: %s -> rc=%d %s", what,
                                " ".join(argv), r.returncode, r.stderr.strip()[:160])
                return                      # a failed step makes the next moot

    threading.Thread(target=work, name="ganglion-radio", daemon=True).start()


class Radio:
    """Apply the chosen radio states. Edge-only; the runner is injectable."""

    def __init__(self, run=_spawn):
        self.run = run
        self._last = {}

    def set_wifi(self, state):
        return self._set("wifi", state, _wifi_cmds)

    def set_bt(self, state):
        return self._set("bt", state, _bt_cmds)

    def _set(self, key, state, cmds):
        # The first call of each always fires: that is the boot-time apply, and
        # it costs nothing when the radio is already in the stored state.
        if self._last.get(key) == state:
            return False
        self._last[key] = state
        self.run(cmds(state), "%s=%s" % (key, state))
        return True
