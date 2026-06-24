"""Off-device footswitch/LED controller: a console-logging no-op.

Implements ``hardware.HardwareController`` with no I2C, for the Windows PySide6
mock. Phase 1 = footswitches disabled (always read released); LED operations log
to the console so you can see what the box would light. Injected explicitly via
``presenter.Presenter(hardware=FakeController())`` -- selection is never
auto-detected (see hardware.py).

Mirrors the real ``fsledctrl`` object shape (a ``Controller`` exposing
``read_footswitches()`` and an ``LED`` container of LED objects) so the presenter
talks to it unchanged.
"""

from hardware import HardwareController


class _FakeLED:
    """Stand-in for fsledctrl.LED: stores state, logs instead of toggling pins."""

    def __init__(self, index):
        self._index = index
        self._state = 0

    def set_state(self, state):
        self._state = state
        print("[fakehw] LED[%d] set_state %d" % (self._index, state))

    def blink(self, color="red", times=3, interval=0.2):
        print("[fakehw] LED[%d] blink %s x%d (interval=%s)"
              % (self._index, color, times, interval))

    def stop_blink(self):
        pass

    def turnOff(self):
        self._state = 0


class _FakeLEDContainer:
    """Stand-in for fsledctrl.LEDContainer (``LED[i] = v`` / ``get_led(i)``)."""

    def __init__(self, count=4):
        self._leds = [_FakeLED(i) for i in range(count)]

    def __getitem__(self, index):
        return self._leds[index]._state

    def __setitem__(self, index, value):
        if not (0 <= value <= 3):
            raise ValueError("LED value must be between 0 and 3 (inclusive).")
        self._leds[index].set_state(value)

    def get_led(self, index):
        return self._leds[index]

    def stop_all_blinking(self):
        for led in self._leds:
            led.stop_blink()
            led.turnOff()


class FakeController(HardwareController):
    """No-op, console-logging stand-in for ``fsledctrl.Controller``."""

    def __init__(self, scheduler=None, num_footswitches=4):
        # ``scheduler`` is accepted for signature parity with the real
        # Controller; the fake schedules nothing (blink just logs).
        self._n = num_footswitches
        self.LED = _FakeLEDContainer(num_footswitches)

    def read_footswitches(self):
        # Phase 1: footswitches disabled -> always released.
        return [0] * self._n

    def cleanup(self):
        pass
