"""Ganglion input events + a keyboard source that emulates the two encoders.

The real device has two rotary-encoder-switch modules (seesaw): each gives a
relative rotation delta, a momentary push switch, and an RGB LED. The app layer
consumes a stream of the events below; the real seesaw source and this keyboard
source both produce that same stream, so the app is unchanged between them
(the same fake/real seam Synapse uses for footswitches).

Keyboard mapping (emulator):
    enc0:  q = rotate CCW (<)   w = toggle switch0   e = rotate CW (>)
    enc1:  a = rotate CCW (<)   s = toggle switch1   d = rotate CW (>)

A terminal only delivers key-*down* (no key-up), so switches are modelled as a
**latch**: each switch key toggles that switch down/up. On release we measure
how long it was held and emit ``Press`` with ``kind`` ``"click"`` (< threshold)
or ``"long"`` (>= threshold). Holding both switches down at once emits ``Combo``
and suppresses the individual clicks -- so long-press and chord gestures are
both testable from the keyboard. Auto-repeat toggles are debounced away.
"""

import time
from dataclasses import dataclass

LONG_PRESS_S = 0.6      # hold >= this on release -> "long", else "click"
_ACCEL_WINDOW_S = 0.08  # rotations faster than this accelerate the step
_ACCEL_MAX = 7          # max step from acceleration
_DEBOUNCE_S = 0.05      # ignore switch re-toggles faster than this (key-repeat)


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


class KeyboardInput:
    """Feed single characters in; get a list of input events out."""

    _ROT = {"q": (0, -1), "e": (0, +1), "a": (1, -1), "d": (1, +1)}
    _SW = {"w": 0, "s": 1}

    def __init__(self):
        self._down = [False, False]
        self._since = [0.0, 0.0]
        # -inf so the very first toggle/rotation is never debounced/accelerated
        # against a zero-initialised timestamp (matters at t≈0 in tests).
        self._last_toggle = [float("-inf"), float("-inf")]
        self._combo_consumed = [False, False]  # this switch was part of a combo
        self._combo_active = False
        self._last_rot_t = [float("-inf"), float("-inf")]
        self._rot_run = [0, 0]

    def feed(self, ch, now):
        """Process one input character at time ``now`` (monotonic seconds)."""
        if ch in self._ROT:
            return self._rotate(*self._ROT[ch], now)
        if ch in self._SW:
            return self._toggle(self._SW[ch], now)
        return []

    def _rotate(self, enc, direction, now):
        if now - self._last_rot_t[enc] < _ACCEL_WINDOW_S:
            self._rot_run[enc] += 1
        else:
            self._rot_run[enc] = 0
        self._last_rot_t[enc] = now
        step = 1 + min(self._rot_run[enc] // 2, _ACCEL_MAX - 1)
        return [Rotate(enc, direction * step)]

    def _toggle(self, enc, now):
        if now - self._last_toggle[enc] < _DEBOUNCE_S:
            return []  # auto-repeat storm
        self._last_toggle[enc] = now

        if not self._down[enc]:
            # press down
            self._down[enc] = True
            self._since[enc] = now
            self._combo_consumed[enc] = False
            if all(self._down):
                self._combo_active = True
                self._combo_consumed = [True, True]
                return [Combo("press")]
            return []

        # release
        self._down[enc] = False
        dur = now - self._since[enc]
        suppress = self._combo_consumed[enc]
        self._combo_consumed[enc] = False
        events = []
        if self._combo_active and not any(self._down):
            self._combo_active = False
            events.append(Combo("release"))
            suppress = True
        if not suppress:
            events.append(Press(enc, "long" if dur >= LONG_PRESS_S else "click"))
        return events

    def switch_status(self, now):
        """[(down, held_seconds), ...] for the HUD's live state."""
        return [(self._down[i], (now - self._since[i]) if self._down[i] else 0.0)
                for i in (0, 1)]
