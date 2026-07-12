"""Headless main loop (decision J) — ties input, view, splash, LEDs together.

The device has no event interrupts wired, and gesture recognition (long-press,
combo window) already needs a clock, so a plain poll loop is unavoidable — this
is that loop, not a scheduler. One ``step()`` = poll the input source, feed the
controller, draw the frame, and — per decision F — if an action left a
confirmation message, hold it as a ~0.5s **blocking splash** (input intentionally
swallowed) then clear it. No time-based toast expiry, no timer object.

Everything is injected (source, sink, clock, sleep) so the loop runs fully
headless under a fake clock in tests (see ``app.py --looptest``); the pure
``AppController`` never learns about I/O or time. Two drivers are provided:
``run_terminal`` (keyboard + terminal renderer, dev) and ``run_device`` (seesaw +
luma OLED, on metal — stub-level like ``hw/seesaw.py``).

Seams:
  source.poll(now) -> [events]         (KeyboardSource / hw.seesaw.SeesawInput)
  sink.show(frame)                     (TerminalSink / luma device)
  led_out((name0, name1)) -> None      (optional; device NeoPixels)
"""

import time as _time


class Runtime:
    """One poll loop over an injected input source and display sink."""

    def __init__(self, controller, source, sink, view, *, leds=None, led_out=None,
                 splash_s=0.5, tick_s=0.03, clock=_time.monotonic, sleep=_time.sleep):
        self.c = controller
        self.source = source
        self.sink = sink
        self.view = view
        self.leds = leds
        self.led_out = led_out
        self.splash_s = splash_s
        self.tick_s = tick_s
        self.clock = clock
        self.sleep = sleep
        self._t0 = None

    def _draw(self):
        self.sink.show(self.view(self.c.st))
        if self.leds and self.led_out:
            self.led_out(self.leds(self.c.st))

    def step(self):
        now = self.clock()
        if self._t0 is None:
            self._t0 = now
        self.c.st.t = now - self._t0        # display clock for the marquee phase;
        for ev in self.source.poll(now):    # the controller stays time-blind
            self.c.feed(ev)
        self._draw()
        if self.c.st.toast:                     # confirmation splash: hold, then clear
            self.sleep(self.splash_s)
            self.c.st.toast = ""
            self._draw()
        self.sleep(self.tick_s)

    def run(self, should_stop=lambda: False):
        while not should_stop():
            self.step()


class KeyboardSource:
    """Adapt the keyboard emulator to the source seam.

    ``read_chars()`` returns the characters available this tick (non-blocking).
    A terminal has no key-up, so each char is one complete gesture (see
    ``input.KeyboardInput``). The quit char sets ``stopped`` for the driver.
    """

    def __init__(self, kb, read_chars, quit_ch="Q"):
        self.kb = kb
        self.read_chars = read_chars
        self.quit_ch = quit_ch
        self.stopped = False

    def poll(self, now):
        events = []
        for ch in self.read_chars():
            if ch == self.quit_ch:
                self.stopped = True
                break
            events += self.kb.feed(ch, now)
        return events


class TerminalSink:
    """Render a frame (+ optional HUD lines) to a terminal, in place."""

    def __init__(self, renderer, out, hud=None):
        self.r = renderer
        self.out = out
        self.hud = hud

    def show(self, frame):
        rows = self.r.render(frame)
        lines = self.hud() if self.hud else []
        buf = []
        for i, row in enumerate(rows):
            buf.append(row + ("  " + lines[i] if i < len(lines) else "") + "\x1b[K")
        self.out.write("\x1b[H" + "\r\n".join(buf) + "\x1b[J")
        self.out.flush()


def run_terminal(controller, view, leds=None, hud=None, mode="braille"):
    """Dev driver: keyboard in, terminal out. Needs a TTY."""
    import sys
    import select
    import termios
    import tty
    from ganglion.display import TerminalRenderer
    from ganglion.input import KeyboardInput

    if not sys.stdin.isatty():
        print("app needs a TTY. Try: python3 ganglion/app.py --walk")
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    kb = KeyboardInput()

    def read_chars():
        chs = []
        while select.select([sys.stdin], [], [], 0)[0]:
            chs.append(sys.stdin.read(1))
        return chs

    source = KeyboardSource(kb, read_chars)
    sink = TerminalSink(TerminalRenderer(mode), sys.stdout, hud)
    rt = Runtime(controller, source, sink, view, leds=leds)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?25l\x1b[?1049h\x1b[2J")
        rt.run(should_stop=lambda: source.stopped)
    finally:
        sys.stdout.write("\x1b[?1049l\x1b[?25h")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# RGB palette for the NeoPixels (decision I — provisional values, tune on metal).
LED_RGB = {"amber": (255, 120, 0), "green": (0, 200, 60), "blue": (0, 90, 255),
           "purple": (150, 0, 255), "red": (255, 0, 0), "grey": (60, 60, 60),
           "off": (0, 0, 0)}


def run_device(controller, view, leds):
    """On-metal driver: seesaw encoders in, luma SH1107 out. Stub-level.

    Untested off-hardware; imports are lazy so this module still loads on a dev
    box. NeoPixel colours use the provisional ``LED_RGB`` map (decision I).
    """
    import board
    import busio
    from luma.core.interface.serial import i2c
    from luma.oled.device import sh1107
    from ganglion.hw.seesaw import SeesawInput

    i2c_bus = busio.I2C(board.SCL, board.SDA)
    source = SeesawInput(i2c=i2c_bus)
    device = sh1107(i2c(port=1, address=0x3C), width=128, height=128, rotate=0)

    class _LumaSink:
        def show(self, frame):
            device.display(frame.convert("1"))

    def led_out(colors):
        for idx, name in enumerate(colors):
            source.set_rgb(idx, LED_RGB.get(name, (0, 0, 0)))

    rt = Runtime(controller, source, _LumaSink(), view, leds=leds, led_out=led_out)
    rt.run()
