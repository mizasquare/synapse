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

from ganglion.input import GestureRecognizer

_SWITCH_PIN = 24   # seesaw GPIO for the encoder push switch (QT Rotary Encoder)
_NEOPIXEL_PIN = 6  # seesaw GPIO for the on-board NeoPixel


class _Module:
    """One seesaw rotary-encoder-switch-RGB board."""

    def __init__(self, i2c, address, invert=False):
        # Lazy imports: only needed on-device, kept out of module import.
        from adafruit_seesaw import seesaw, rotaryio, digitalio, neopixel

        self._ss = seesaw.Seesaw(i2c, addr=address)
        self._invert = invert
        self._enc = rotaryio.IncrementalEncoder(self._ss)
        self._ss.pin_mode(_SWITCH_PIN, self._ss.INPUT_PULLUP)
        self._button = digitalio.DigitalIO(self._ss, _SWITCH_PIN)
        self._pixel = neopixel.NeoPixel(self._ss, _NEOPIXEL_PIN, 1)
        self._last_pos = self._enc.position

    def read_delta(self):
        """Encoder detents since the last read (signed, direction-corrected)."""
        pos = self._enc.position
        raw = pos - self._last_pos
        self._last_pos = pos
        return -raw if self._invert else raw

    def read_pressed(self):
        """True while the switch is held (pull-up: pressed pulls the line low)."""
        return not self._button.value

    def set_rgb(self, color):
        """``color``: (r, g, b) 0-255, or 0 to turn off."""
        self._pixel.fill(color)


class SeesawInput:
    """Poll two seesaw modules and emit the shared input event stream.

    Driven by the app's main loop: call ``poll(now)`` each tick. (The keyboard
    source is event-driven via ``feed(ch)`` instead; the entry point wires
    whichever loop shape fits -- both return the same events.)
    """

    def __init__(self, i2c=None, addresses=(0x36, 0x37), invert=(False, False),
                 recognizer=None):
        if i2c is None:
            import board
            import busio
            i2c = busio.I2C(board.SCL, board.SDA)
        self._i2c = i2c
        self._modules = [_Module(i2c, addr, inv)
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
