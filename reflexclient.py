"""App-side client for the reflex pedal service's management socket.

The reflex service (reflex.py, deploy/reflex-service/) is an independent MIDI
pedal device living in the box; this is the app's handle on its "firmware
editor" channel — the JSON-line Unix socket that owns calibration and per-axis
MIDI mapping. The performance path (CC on the shared MIDI bus) never passes
through here.

One request per connection (the nc idiom the service was validated with): a
short-lived socket keeps this trivially robust against a restarted service and
needs no reader thread. get_status is cheap, so the pedal CONFIG leaf just
polls it while visible.

Injected via ``presenter.Presenter(reflex_factory=...)`` — the default is this
real client; ``qt_dev.py`` injects ``fakereflex.FakeReflexClient`` (same
protocol handler over a synthetic pedal).
"""

import json
import socket

from reflex import SOCKET_PATH


class ReflexClient:
    """JSON-line client for ``~/.modep/reflex.sock``. Every method returns the
    service's response dict, or None when the service is unreachable — the
    caller treats None as "no pedal service" (leaf shows its missing state)."""

    def __init__(self, sock_path=None, timeout=0.4):
        self._path = sock_path or SOCKET_PATH
        self._timeout = timeout

    def _request(self, payload):
        if not hasattr(socket, "AF_UNIX"):
            return None   # non-POSIX dev box without the fake injected
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(self._timeout)
                s.connect(self._path)
                s.sendall((json.dumps(payload) + "\n").encode())
                buf = b""
                while not buf.endswith(b"\n"):
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
            return json.loads(buf.decode()) if buf.strip() else None
        except (OSError, ValueError):
            return None

    # -- protocol surface (mirrors reflex.handle_request commands) ------------
    def get_status(self):
        return self._request({"cmd": "get_status"})

    def capture(self, channel, end):
        """``end`` is "heel" or "toe" — records the current raw as pending."""
        return self._request({"cmd": "capture_%s" % end, "channel": int(channel)})

    def save(self):
        return self._request({"cmd": "save"})

    def set_mapping(self, axis, channel, cc):
        return self._request({"cmd": "set_mapping", "axis": axis,
                              "channel": int(channel), "cc": int(cc)})
