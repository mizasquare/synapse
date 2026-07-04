"""Ganglion input events + gesture recognition, shared by every input source.

The real device has two rotary-encoder-switch modules (seesaw): each gives a
relative rotation delta, a momentary push switch, and an RGB LED. The app layer
consumes the event stream below; both the keyboard emulator (this file) and the
real seesaw source (``ganglion/hw/seesaw.py``) feed *raw samples* into the one
``GestureRecognizer``, so click/long/combo semantics and rotation acceleration
live in a single place and behave identically on the emulator and on hardware.

Raw sample = (per-encoder ``pressed`` boolean, per-encoder rotation ``delta``).
- Real seesaw: ``pressed`` is the actual button read; ``delta`` is the encoder
  position change since the last poll.
- Keyboard emulator: a terminal has no key-*up*, so each key is one complete
  gesture (see ``KeyboardInput``); only rotation is sampled through the
  recognizer, for shared acceleration.

Keyboard mapping:
    enc0:  r = rotate CCW (<)   t = rotate CW (>)   w = click   e = long
    enc1:  f = rotate CCW (<)   g = rotate CW (>)   s = click   d = long
    combo: x
"""

from dataclasses import dataclass

LONG_PRESS_S = 0.6       # hold >= this on release -> "long", else "click"
_ACCEL_WINDOW_S = 0.08   # rotations closer than this in time accelerate the step
_ACCEL_MAX = 7           # cap on the acceleration momentum


@dataclass
class Rotate:
    """Relative encoder rotation. ``delta`` sign = direction, magnitude = accel."""
    enc: int
    delta: int


@dataclass
class Press:
    """A completed switch press. ``kind`` is ``"click"`` or ``"long"``."""
    enc: int
    kind: str


@dataclass
class Combo:
    """Both switches held at once. ``kind`` is ``"press"`` or ``"release"``."""
    kind: str


class GestureRecognizer:
    """Turn a stream of raw samples into ``Rotate``/``Press``/``Combo`` events.

    Stateful across calls (tracks edges, hold times, rotation momentum). One
    instance per input source. All press/combo timing tuning lives here, so the
    emulator and the real encoders share exactly one behaviour.
    """

    def __init__(self, long_press_s=LONG_PRESS_S):
        self.long_press_s = long_press_s
        self._down = [False, False]
        self._since = [0.0, 0.0]
        self._consumed = [False, False]  # this switch was folded into a combo
        self._combo_active = False
        self._last_rot_t = [float("-inf"), float("-inf")]
        self._rot_run = [0, 0]

    def update(self, now, pressed, rotations):
        """Sample the two encoders at time ``now``.

        ``pressed``: ``[bool, bool]`` current switch states.
        ``rotations``: ``[int, int]`` rotation delta since the last update.
        Returns the events produced by this sample (possibly empty).
        """
        events = []
        for enc in (0, 1):
            if rotations[enc]:
                events.append(self._rotate(enc, rotations[enc], now))
        for enc in (0, 1):
            events += self._switch(enc, bool(pressed[enc]), now)
        return events

    def _rotate(self, enc, delta, now):
        step = abs(delta)
        if now - self._last_rot_t[enc] < _ACCEL_WINDOW_S:
            step += self._rot_run[enc]  # carry recent momentum
            self._rot_run[enc] = min(self._rot_run[enc] + abs(delta), _ACCEL_MAX)
        else:
            self._rot_run[enc] = abs(delta)
        self._last_rot_t[enc] = now
        return Rotate(enc, step if delta > 0 else -step)

    def _switch(self, enc, is_down, now):
        was = self._down[enc]
        if is_down and not was:  # press edge
            self._down[enc] = True
            self._since[enc] = now
            self._consumed[enc] = False
            if all(self._down):
                self._combo_active = True
                self._consumed = [True, True]
                return [Combo("press")]
            return []
        if was and not is_down:  # release edge
            self._down[enc] = False
            dur = now - self._since[enc]
            suppress = self._consumed[enc]
            self._consumed[enc] = False
            out = []
            if self._combo_active and not any(self._down):
                self._combo_active = False
                out.append(Combo("release"))
                suppress = True
            if not suppress:
                out.append(Press(enc, "long" if dur >= self.long_press_s else "click"))
            return out
        return []

    def switch_status(self, now):
        """[(down, held_seconds), ...] for a HUD's live state."""
        return [(self._down[i], (now - self._since[i]) if self._down[i] else 0.0)
                for i in (0, 1)]


class KeyboardInput:
    """Emulator input source: characters in, events out.

    Each key is one *complete* gesture -- a terminal gives no key-up, so instead
    of latching a switch and timing its release we just declare the gesture
    outright: a click key emits ``Press("click")``, a long key emits
    ``Press("long")``, the combo key emits a ``Combo`` press+release. Only
    rotation goes through the recognizer (for shared acceleration). The real
    seesaw source, which *does* have down/up edges, uses the recognizer's full
    press/combo timing instead -- see ``GestureRecognizer``.

        enc0:  r <   t >    w click   e long
        enc1:  f <   g >    s click   d long
        combo: x
    """

    _ROT = {"r": (0, -1), "t": (0, +1), "f": (1, -1), "g": (1, +1)}
    _CLICK = {"w": 0, "s": 1}
    _LONG = {"e": 0, "d": 1}
    _COMBO = "x"

    def __init__(self, recognizer=None):
        self.gestures = recognizer or GestureRecognizer()

    def feed(self, ch, now):
        """Process one input character at time ``now`` (monotonic seconds)."""
        if ch in self._ROT:
            enc, direction = self._ROT[ch]
            rot = [0, 0]
            rot[enc] = direction
            return self.gestures.update(now, [False, False], rot)
        if ch in self._CLICK:
            return [Press(self._CLICK[ch], "click")]
        if ch in self._LONG:
            return [Press(self._LONG[ch], "long")]
        if ch == self._COMBO:
            return [Combo("press"), Combo("release")]
        return []
