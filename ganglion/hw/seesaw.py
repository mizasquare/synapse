"""Real input source: two Adafruit I2C QT Rotary Encoders (seesaw + NeoPixel).

Each module is one seesaw board carrying a rotary encoder, its push switch, and
one NeoPixel RGB LED. This source polls both, feeds the raw (pressed, delta)
sample into the shared ``GestureRecognizer``, and returns the very same
``Rotate``/``Press``/``Combo`` events the keyboard emulator produces -- so the
app layer is identical on the emulator and on hardware (the fake/real seam).

STATUS: **stub — written against the Adafruit seesaw API, unverified on metal.**
Three things can only be pinned down once the modules are wired (see design.md):

  1. **I2C addresses** — default 0x36; the 2nd module needs an address jumper
     (0x37 here). Confirm with ``i2cdetect -y 1`` after wiring.
  2. **Rotation sign** — ``IncrementalEncoder.position`` direction vs. physical
     CW is orientation/wiring dependent. ``invert=`` flips it per module.
  3. **Button / NeoPixel pins** — the QT Rotary Encoder uses seesaw pin 24 for
     the switch (INPUT_PULLUP, pressed == low) and pin 6 for the NeoPixel. These
     are the documented defaults; verify against the exact board revision.

The Adafruit libraries (``adafruit_seesaw``, ``adafruit_blinka``) are imported
lazily in ``__init__`` so importing this module off-device (no I2C, no libs)
does not fail -- only *instantiating* ``SeesawInput`` touches hardware.
"""

import time

from ganglion.input import GestureRecognizer

_SWITCH_PIN = 24   # seesaw GPIO for the encoder push switch (QT Rotary Encoder)
_NEOPIXEL_PIN = 6  # seesaw GPIO for the on-board NeoPixel

# These NeoPixels are uncomfortably bright at full scale on a device you sit in
# front of -- 0.5 was still too bright on metal, hence 0.1. Dim here rather than
# by editing ``runtime.LED_RGB``: that map encodes what a colour *means*
# (decision I — category/state), and folding brightness into it would tangle the
# two, so every future palette edit would have to re-derive the dimming. This
# scales on the way to the wire and leaves the palette's hues intact. (Power was
# never the reason — 2 LEDs full white = ~58mA with ~340mA of budget spare —
# this is purely comfort.)
#
# CAVEAT: a WS2812 has no global current control, so ``brightness`` can only
# scale the 8-bit values before they go out. At 0.1 the palette lands on 2..26
# per channel — grey (60,60,60) becomes (6,6,6) — and down there the channels no
# longer track each other, so hues drift and the dimmer colours start to
# converge. If two categories stop being tellable apart, that is this line's
# fault, not the palette's: raise the floor here before retuning LED_RGB.
_LED_BRIGHTNESS = 0.1

_IO_RETRIES = 6       # seesaw NACKs a transfer now and then (Errno 121), esp. on
_IO_BACKOFF_S = 0.002 # a Pi 5 with reads + NeoPixel writes racing -- retry, don't crash.
_IO_BACKOFF_CAP_S = 0.02


def _retry_io(fn):
    """Call ``fn`` (a bus read or write), retrying transient I2C NACKs a few times.

    The seesaw firmware occasionally fails to ACK a transfer when it is mid-op (a
    NeoPixel ``show`` in particular leaves it busy for a few ms). Measured clean
    over 300 back-to-back reads, but it *does* fire when reads and writes
    interleave on the shared bus -- and the app touches both every tick -- so all
    per-tick I/O goes through here. Backoff **escalates** (2,4,8,16,20 ms): a flat
    few-ms window was too short to outlast the busy patch after a paint and still
    crashed (seen on metal). ~50ms worst case is invisible at 33Hz and only paid
    on the rare blip. Re-raises if it never recovers -- a real wiring/address
    fault, not a transient.
    """
    for attempt in range(_IO_RETRIES):
        try:
            return fn()
        except OSError:
            if attempt == _IO_RETRIES - 1:
                raise
            time.sleep(min(_IO_BACKOFF_S * (2 ** attempt), _IO_BACKOFF_CAP_S))


class _Module:
    """One seesaw rotary-encoder-switch-RGB board."""

    def __init__(self, i2c, address, invert=False, brightness=_LED_BRIGHTNESS):
        # Lazy imports: only needed on-device, kept out of module import.
        from adafruit_seesaw import seesaw, rotaryio, digitalio, neopixel

        self._ss = seesaw.Seesaw(i2c, addr=address)
        self._invert = invert
        self._enc = rotaryio.IncrementalEncoder(self._ss)
        self._ss.pin_mode(_SWITCH_PIN, self._ss.INPUT_PULLUP)
        self._button = digitalio.DigitalIO(self._ss, _SWITCH_PIN)
        self._pixel = neopixel.NeoPixel(self._ss, _NEOPIXEL_PIN, 1,
                                        brightness=brightness)
        self._last_pos = self._enc.position
        self._last_rgb = None

    def read_delta(self):
        """Encoder detents since the last read (signed, direction-corrected)."""
        pos = _retry_io(lambda: self._enc.position)
        raw = pos - self._last_pos
        self._last_pos = pos
        return -raw if self._invert else raw

    def read_pressed(self):
        """True while the switch is held (pull-up: pressed pulls the line low)."""
        return not _retry_io(lambda: self._button.value)

    def set_rgb(self, color):
        """``color``: (r, g, b) 0-255, or 0 to turn off.

        The caller (Runtime) repaints every tick, so skip the write when the
        colour is unchanged -- a NeoPixel ``show`` is a heavy transfer to spend
        33x/s for nothing, and every needless one is another chance to collide
        with the encoder reads sharing the bus (the write NACK we retry below)."""
        rgb = (0, 0, 0) if color == 0 else tuple(color)
        if rgb == self._last_rgb:
            return
        _retry_io(lambda: self._pixel.fill(rgb))
        self._last_rgb = rgb


class SeesawInput:
    """Poll two seesaw modules and emit the shared input event stream.

    Driven by the app's main loop: call ``poll(now)`` each tick. (The keyboard
    source is event-driven via ``feed(ch)`` instead; the entry point wires
    whichever loop shape fits -- both return the same events.)
    """

    def __init__(self, i2c=None, addresses=(0x36, 0x37), invert=(True, True),
                 recognizer=None, brightness=_LED_BRIGHTNESS):
        # invert default = True: on this build CW read as negative (cursor moved
        # the wrong way) -- flip both so CW = forward/down. Per-module override
        # stays available if the two ever get wired opposite.
        if i2c is None:
            import board
            import busio
            i2c = busio.I2C(board.SCL, board.SDA)
        self._i2c = i2c
        self._modules = [_Module(i2c, addr, inv, brightness=brightness)
                         for addr, inv in zip(addresses, invert)]
        self.gestures = recognizer or GestureRecognizer()

    def poll(self, now):
        """Sample both encoders at time ``now`` (monotonic seconds) -> events."""
        rotations = [m.read_delta() for m in self._modules]
        pressed = [m.read_pressed() for m in self._modules]
        return self.gestures.update(now, pressed, rotations)

    def set_rgb(self, index, color):
        """Set module ``index``'s NeoPixel (output side; RGB semantics = design.md)."""
        self._modules[index].set_rgb(color)

    def switch_status(self, now):
        return self.gestures.switch_status(now)
