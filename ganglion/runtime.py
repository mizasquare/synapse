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
  power.idle(elapsed) / .wake() / .set_on(level)   (optional; hw.oled.PanelPower)
  settings.apply(st) / .observe(st)    (optional; settings.Settings)
  radio.set_wifi(state) / .set_bt(state)   (optional; hw.radio.Radio)
  meter.observe(st)                    (optional; hw.meter.Meter — INBOUND)
  tuner.observe(st)                    (optional; hw.tuner.Tuner — INBOUND, on-demand)
"""

import time as _time

from ganglion.config import BRIGHT_LEVELS, I2C_ADDR, ROTATE


class Runtime:
    """One poll loop over an injected input source and display sink.

    It also owns **idle panel power** (``power``, optional): dim then blank the
    display once the knobs have gone quiet, so a static UI does not burn itself
    into the glass. That lives here and not in the controller because it is a
    hardware state (contrast, 0xAE) and not a pixel -- putting it in the pure app
    would break ``view = f(st)`` and contaminate the golden frames. The loop
    already holds the clock, so it costs no new state in ``AppState``.

    Note it tracks its own ``_t_input`` rather than reading ``st.t_mark``, which
    is also "time of last input". ``t_mark`` is the *marquee phase anchor*
    (decision Q) -- a rendering concern -- and hanging panel lifetime off it
    would silently break the day someone re-anchors the marquee. It could not be
    used anyway: waking swallows the input, so ``feed()`` never runs to set it.
    """

    def __init__(self, controller, source, sink, view, *, leds=None, led_out=None,
                 power=None, settings=None, radio=None, meter=None, tuner=None,
                 splash_s=0.5, tick_s=0.03, clock=_time.monotonic, sleep=_time.sleep):
        self.c = controller
        self.source = source
        self.sink = sink
        self.view = view
        self.leds = leds
        self.led_out = led_out
        self.power = power
        self.settings = settings
        self.radio = radio
        self.meter = meter
        self.tuner = tuner
        self.splash_s = splash_s
        self.tick_s = tick_s
        self.clock = clock
        self.sleep = sleep
        self._t0 = None
        self._t_input = None

    def _draw(self):
        self.sink.show(self.view(self.c.st))
        if self.leds and self.led_out:
            self.led_out(self.leds(self.c.st))

    def step(self):
        now = self.clock()
        if self._t0 is None:
            self._t0 = self._t_input = now
        self.c.st.t = now - self._t0        # display clock for the marquee phase;
        events = self.source.poll(now)      # the controller stays time-blind
        if events:
            self._t_input = now
        if self.power:
            if events and self.power.blanked:
                self.power.wake()               # off a dark panel the first input
                events = []                     # only wakes it: never edit what
            # SYSTEM > Brightness. Same shape as led_out: a pure value out of the
            # state, pushed to hardware by the loop, so the controller never
            # learns what a contrast byte is. Both calls no-op when nothing moved.
            self.power.set_on(BRIGHT_LEVELS[self.c.st.bright])
            self.power.idle(now - self._t_input)  # the user cannot see (cf. F)
        if self.radio:                      # same shape again; both are edge-only,
            self.radio.set_wifi(self.c.st.wifi)     # and the first call is the
            self.radio.set_bt(self.c.st.bt)         # boot-time apply
        for ev in events:
            self.c.feed(ev)
        if self.settings:
            self.settings.observe(self.c.st)    # writes only when a choice moved
        # Not under the blank guard below: unlike the meter, this seam owns a JACK
        # client's whole lifetime and must start/stop it on the st.tuner edge even
        # if the panel is dark. It self-gates (does nothing unless tuning) cheaply.
        if self.tuner:
            self.tuner.observe(self.c.st)
        # A blank panel keeps its GDDRAM, so drawing into it is pure bus waste --
        # and a level nobody can read is not worth a JACK snapshot either, which is
        # why the meter sits inside the guard and not with the three seams above.
        # It is also the one that runs the other way: world -> state (cf. st.t).
        if not (self.power and self.power.blanked):
            if self.meter:
                self.meter.observe(self.c.st)
            self._draw()
            if self.c.st.toast:                 # confirmation splash: hold, then clear
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


def run_encoders_terminal(controller, view, leds=None, hud=None, mode="braille"):
    """Bring-up driver: real seesaw encoders in, **terminal** out (no OLED yet).

    The hardware seam is half-populated -- the two encoders are wired and verified
    (``tools/encoder_bench``) but the SH1107 hasn't arrived. This runs the live
    app on the real knobs while the frame still renders to the terminal, so the
    whole state machine gets exercised on metal input before the panel exists.
    It is ``run_device`` with the luma sink swapped for ``run_terminal``'s: same
    ``SeesawInput`` source and NeoPixel ``led_out``, ``TerminalSink`` for display.

    No keyboard is read (the encoders are the input), so there is no quit char --
    Ctrl-C stops it, and the terminal is always restored on the way out.
    """
    import sys
    from ganglion.display import TerminalRenderer
    from ganglion.hw.seesaw import SeesawInput

    import board
    import busio

    source = SeesawInput(i2c=busio.I2C(board.SCL, board.SDA))
    sink = TerminalSink(TerminalRenderer(mode), sys.stdout, hud)

    def led_out(colors):
        for idx, name in enumerate(colors):
            source.set_rgb(idx, LED_RGB.get(name, (0, 0, 0)))

    rt = Runtime(controller, source, sink, view, leds=leds, led_out=led_out)
    try:
        sys.stdout.write("\x1b[?25l\x1b[?1049h\x1b[2J")
        rt.run()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            led_out(("off", "off"))             # don't leave the NeoPixels lit
        except OSError:
            pass                                # but never let that strand the terminal
        sys.stdout.write("\x1b[?1049l\x1b[?25h")
        sys.stdout.flush()


def run_device(controller, view, leds):
    """On-metal driver: seesaw encoders in, luma SH1107 out (diff-pushed).

    Both halves of the hardware seam are now verified on metal — the encoders by
    ``tools/encoder_bench``, the panel by ``tools/oled_probe``. Imports stay lazy
    so this module still loads on a dev box. NeoPixel colours use the provisional
    ``LED_RGB`` map (decision I).

    Note this does *not* set ``device.persist``: luma's atexit hook blanking and
    powering the panel down is the right behaviour for the app (it is wrong only
    for a test screen, which is why ``oled_probe`` opts out of it).
    """
    import board
    import busio
    from luma.core.interface.serial import i2c
    from luma.oled.device import sh1107
    from ganglion.hw.meter import Meter
    from ganglion.hw.oled import DiffSink, LumaWriter, PanelPower
    from ganglion.hw.radio import Radio
    from ganglion.hw.seesaw import SeesawInput
    from ganglion.hw.tuner import Tuner
    from ganglion.settings import Settings

    i2c_bus = busio.I2C(board.SCL, board.SDA)
    source = SeesawInput(i2c=i2c_bus)
    # Address and rotation are config.py's (they were duplicated here and in
    # tools/oled_probe, each with its own copy of why -- see that module).
    #
    # A full frame measures ~220ms here (184ms of it wire time at the 100kHz the
    # bus shipped at; the rest is luma's per-pixel Python packing loop). At the
    # 400kHz config.txt now asks for it is still ~80ms — nearly 3 ticks, and the
    # encoders poll on this bus. The diff sink below is not an optimization.
    device = sh1107(i2c(port=1, address=I2C_ADDR), width=128, height=128,
                    rotate=ROTATE)

    # So we never send one. DiffSink pushes only the page-row spans that changed
    # (typically one 8px band, often nothing at all) and diffs in panel space,
    # after luma's rotation. Measured on real frame sequences by
    # ``python3 -m ganglion.tools.oled_bench``; confirmed on the panel itself by
    # ``python3 -m ganglion.tools.oled_probe`` (10ms/tick vs 220ms full, and 0.4ms
    # when nothing moved).
    sink = DiffSink(LumaWriter(device), preprocess=device.preprocess)

    # Idle burn-in defence: the UI is mostly static furniture and the device sits
    # on a desk for hours, so quiet knobs have to reach the glass (config.py).
    power = PanelPower(device)

    def led_out(colors):
        for idx, name in enumerate(colors):
            source.set_rgb(idx, LED_RGB.get(name, (0, 0, 0)))

    # Only the on-metal driver persists: a terminal/fake run must not write over
    # the device's real choices (the reason synapse's configs.py grew
    # SYNAPSE_STATE_DIR in the first place). Applied before the first draw so the
    # panel never flashes the default brightness on the way to the stored one.
    settings = Settings()
    settings.apply(controller.st)

    # IN/OUT header (decision H) — re-attached, now that the service can actually
    # take RT scheduling. The why lives in the unit (deploy/ganglion-service/).
    #
    # The 688 xruns/10min that pulled this were never about the GIL, and both
    # earlier explanations were wrong. Measured since:
    #
    #   * the callback costs 0.025ms — 0.9% of the 2.67ms period, tail max 0.51ms,
    #     and it triggers no GC at all (alloc/free balance, so gen0 never trips);
    #   * `tools/gil_probe` puts the loop's GIL lateness at the *sleep floor*
    #     (0.058ms p50, identical to an idle tick). `source.poll()`, which the
    #     first correction blamed by elimination, is 34ms of `time.sleep(0.008)`
    #     inside adafruit_seesaw's `read()` — wall time that holds no GIL at all.
    #
    # The client just never got scheduled: `AcquireSelfRealTime` failed, so it ran
    # SCHED_OTHER as the one non-FIFO client in a sync (-S) graph, and jackd waits
    # for everybody. `LimitRTPRIO` is a unit setting; limits.conf only ever reaches
    # PAM sessions, which a system service is not.
    meter = Meter()

    # Guitar tuner (① 기능) — an on-demand cochlea engine, live only while the
    # ENC1-hold tuner screen is up (hw/tuner.py). Its own JACK client on
    # capture_1, spun up and torn down on the mode edge, so it costs nothing the
    # rest of the time.
    tuner = Tuner()

    rt = Runtime(controller, source, sink, view, leds=leds, led_out=led_out,
                 power=power, settings=settings, radio=Radio(), meter=meter,
                 tuner=tuner)
    try:
        rt.run()                       # Ctrl-C is the only way out: no quit gesture
    except KeyboardInterrupt:
        pass
    finally:
        # The panel takes care of itself — ``persist`` is left unset, so luma's
        # atexit hook blanks and powers it down. The NeoPixels have no such hook
        # and would simply stay lit, so put them out by hand; the JACK client is
        # the same story — leave it and it lingers in the graph until the process
        # actually dies, so a restart would race its own stale ports.
        try:
            led_out(("off", "off"))
        except OSError:
            pass                       # a dead bus must not mask the real error
        if meter is not None:
            meter.stop()               # never raises (hw/meter.py)
        if tuner is not None:
            tuner.stop()               # drops the engine's JACK client + DSP thread
