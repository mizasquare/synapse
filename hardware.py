"""Footswitch + LED hardware abstraction (the on-device control seam).

Decouples the presenter from the Pi-only I2C stack (MCP23017 over smbus2). The
presenter depends only on the small ``HardwareController`` surface below; the
on-device implementation is ``hardwares.fsledctrl.Controller`` (real I2C), wired
in by default. Running off device (the Windows PyQt6 mock) means injecting a
``FakeController`` -- see ``fakehardware`` and ``presenter.Presenter(hardware=...)``.

Selection is **explicit at the entry point**, not auto-detected: ``qt_main.py``
(the Pi entry) builds the real controller and fails loud if the hardware is
faulty, while ``qt_app.py`` injects the fake. We deliberately do NOT silently fall back
to a dummy on I2C errors -- on a live stage box a dead footswitch must surface,
not pass silently. (Missing I2C *libraries* off-device is a separate, import-time
condition handled by simply injecting the fake there.)

The presenter uses exactly:
- ``read_footswitches() -> [s0, s1, s2, s3]`` (``1`` == pressed), one cheap poll.
- ``LED[i] = value`` (0..3; bit0 blue, bit1 red) to set an LED pair's state.
- ``LED.get_led(i).blink(color='red', times=1, interval=0.1)`` for blinks.

So a controller must expose ``read_footswitches()`` and an ``LED`` attribute --
a container supporting ``__setitem__(i, value)`` and ``get_led(i)`` returning an
object with ``blink(color, times, interval)``. The real ``fsledctrl.Controller``
(with its ``LEDContainer``/``LED``) satisfies this structurally and need not
subclass, the same way ``ModepController`` is a structural ``backend.Backend``.
"""


class HardwareController:
    """Footswitch/LED controller surface the presenter depends on. Default
    implementation is ``hardwares.fsledctrl.Controller``.

    Concrete controllers also expose an ``LED`` attribute (an LED container);
    see the module docstring for that nested contract. It is an instance
    attribute, not declared here, so implementations are free to build it in
    ``__init__``.
    """

    def read_footswitches(self):
        """Return ``[s0, s1, s2, s3]`` (``1`` == pressed) from one cheap poll."""
        raise NotImplementedError

    def cleanup(self):
        """Release the hardware. No-op for fakes."""
        raise NotImplementedError
