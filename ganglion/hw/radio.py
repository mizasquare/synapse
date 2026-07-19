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


def _read_net(dev="wlan0"):
    """``(ssid, ip)`` for the client radio *right now*, via nmcli, or None each.

    Two reads: the active SSID (``active,ssid`` — the one row nmcli marks ``yes``)
    and the interface's IPv4 (stripped of its ``/24``). Either can be None — not
    associated yet, no lease, or nmcli absent on a dev box — and None is honest:
    About shows "--", the same as a meter with no JACK, never a stale guess."""
    ssid = ip = None
    try:
        r = subprocess.run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                           capture_output=True, text=True, timeout=8)
        for line in r.stdout.splitlines():
            if line.startswith("yes:"):          # the associated network's row
                ssid = line[4:].strip() or None
                break
    except (OSError, subprocess.TimeoutExpired) as e:
        logging.warning("ganglion radio: ssid read: %s", e)
    try:
        r = subprocess.run(["nmcli", "-t", "-f", "IP4.ADDRESS", "dev", "show", dev],
                           capture_output=True, text=True, timeout=8)
        for line in r.stdout.splitlines():
            if ":" in line:                      # IP4.ADDRESS[1]:192.168.0.64/24
                ip = line.split(":", 1)[1].split("/")[0].strip() or None
                if ip:
                    break
    except (OSError, subprocess.TimeoutExpired) as e:
        logging.warning("ganglion radio: ip read: %s", e)
    return ssid, ip


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
    """Apply the chosen radio states. Edge-only; the runner is injectable.

    ``status`` is a **deliberate read**, and the one exception to the write-only
    contract in this module's header. That contract is about the *control* path:
    the tri-state on/hotspot/off never reads back, because the UI shows what you
    chose. ``status`` is a different path with a different reason to exist — About
    wants the client's actual SSID and lease, which no ``set_wifi`` knows: the
    ``on`` case never runs ``con up`` (autoconnect associates *after* the worker
    exits), and the rig roams rooms and renews leases with **no radio edge at
    all** (config.py's autoconnect note). So a cache off the last write would be
    stale exactly where it matters; ``status`` reads the world when About opens."""

    def __init__(self, run=_spawn, read_net=_read_net, spawn=None):
        self.run = run
        self._read_net = read_net
        # How the status read runs off-thread. Default: a daemon like _spawn's, so
        # a slow nmcli never stalls the 33Hz encoder poll. Tests inject a
        # synchronous runner to read the result without joining a thread.
        self._spawn = spawn or (lambda fn: threading.Thread(
            target=fn, name="ganglion-netstat", daemon=True).start())
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

    def status(self, st):
        """Client SSID/IP -> st.net_ssid / st.net_ip, once, off-thread.

        Only in ``on``: ``hotspot`` shows the profile's constants (config) and
        ``off`` has nothing, so neither pays for an nmcli read. The Runtime fires
        this on the About-open edge, not per tick."""
        if st.wifi != "on":
            return
        self._spawn(lambda: self._write_net(st))

    def _write_net(self, st):
        st.net_ssid, st.net_ip = self._read_net()   # atomic attr writes (GIL); the
        #                                             render thread reads them next tick
