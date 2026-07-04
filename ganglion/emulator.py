"""CLI emulator: watch the 128x128 framebuffer and drive the two encoders.

No hardware. Renders the same Pillow image the real SH1107 would get, to the
terminal (braille by default), and feeds keyboard input through the same event
stream the real seesaw encoders will produce. Lets the whole UI + interaction
model be built before the parts arrive (design.md #8).

Run (from the repo root):
    python3 ganglion/emulator.py            # braille, 64x32 chars
    python3 ganglion/emulator.py --half     # half-block, 128x64 chars (wide term)
    python3 ganglion/emulator.py --selftest # render one frame + quit (no TTY)

Controls:
    enc0:  q <   w toggle-switch   e >          x / Ctrl-C : quit
    enc1:  a <   s toggle-switch   d >
Switch keys TOGGLE (● held / ○ up); release -> click (<0.6s) or LONG (>=0.6s);
both ● at once = COMBO. Resize the terminal to >= ~106x34 for the full view.

``DemoScreen`` below is a throwaway placeholder that just proves every input
path and the render pipeline work -- the real screens (design.md #4) replace it.
"""

import os
import sys
import time

# allow ``python3 ganglion/emulator.py`` from the repo root (not just ``-m``)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont

from ganglion import WIDTH, HEIGHT
from ganglion.display import TerminalRenderer
from ganglion.input import KeyboardInput, Rotate, Press, Combo

_FONT = ImageFont.load_default()
_MENU = ["Clean", "Crunch", "Lead", "Ambient", "Bass Rig"]


class DemoScreen:
    """Placeholder UI: enc0 scrolls a menu, enc1 sets a value; press/long/combo
    are shown as events. Exercises the whole pipeline -- not the real design."""

    def __init__(self):
        self.sel = 0
        self.value = 40
        self.entered = None
        self.last_event = "(waiting)"
        self._combo_until = 0.0

    def handle(self, ev, now):
        if isinstance(ev, Rotate):
            if ev.enc == 0:
                self.sel = (self.sel + ev.delta) % len(_MENU)
                self.last_event = "enc0 rotate %+d -> %s" % (ev.delta, _MENU[self.sel])
            else:
                self.value = max(0, min(100, self.value + ev.delta))
                self.last_event = "enc1 rotate %+d -> vol %d" % (ev.delta, self.value)
        elif isinstance(ev, Press):
            if ev.enc == 0 and ev.kind == "click":
                self.entered = _MENU[self.sel]
                self.last_event = "enc0 CLICK -> enter %s" % self.entered
            elif ev.enc == 0:
                self.entered = None
                self.last_event = "enc0 LONG -> back"
            elif ev.enc == 1 and ev.kind == "click":
                self.value = 0
                self.last_event = "enc1 CLICK -> reset vol"
            else:
                self.last_event = "enc1 LONG"
        elif isinstance(ev, Combo):
            if ev.kind == "press":
                self._combo_until = now + 1.2
                self.last_event = "COMBO press"
            else:
                self.last_event = "COMBO release"

    def render(self, now):
        img = Image.new("1", (WIDTH, HEIGHT), 0)
        d = ImageDraw.Draw(img)

        # title bar (inverted)
        d.rectangle([0, 0, WIDTH - 1, 11], fill=1)
        d.text((3, 2), "GANGLION · GECO1", fill=0, font=_FONT)

        # menu (enc0)
        y = 16
        for i, item in enumerate(_MENU):
            sel = i == self.sel
            if sel:
                d.rectangle([0, y - 1, 92, y + 9], fill=1)
            mark = "> " if sel else "  "
            here = " *" if item == self.entered else ""
            d.text((4, y), mark + item + here, fill=0 if sel else 1, font=_FONT)
            y += 11

        # value column (enc1)
        d.text((99, 16), "VOL", fill=1, font=_FONT)
        d.rectangle([100, 30, 116, 106], outline=1)
        fill_h = int((106 - 30) * self.value / 100)
        d.rectangle([100, 106 - fill_h, 116, 106], fill=1)
        d.text((98, 110), "%3d" % self.value, fill=1, font=_FONT)

        # footer: last event
        d.line([0, 116, WIDTH - 1, 116], fill=1)
        d.text((2, 118), self.last_event[:24], fill=1, font=_FONT)

        # combo banner overlay
        if now < self._combo_until:
            d.rectangle([12, 50, 116, 76], fill=1)
            d.rectangle([14, 52, 114, 74], outline=0)
            d.text((34, 59), "** COMBO **", fill=0, font=_FONT)

        return img


_HUD = [
    "GANGLION emulator — SH1107 128x128 (fake)",
    "",
    "enc0:  q <    w toggle    e >",
    "enc1:  a <    s toggle    d >",
    "",
    "switch keys TOGGLE  (● held / ○ up)",
    "release → click(<0.6s) / LONG(≥0.6s)",
    "both ● at once = COMBO",
    "",
    "x / Ctrl-C : quit",
]


def _compose(disp_rows, hud_lines):
    """Display block on the left, HUD text on the right, one screen high."""
    out = []
    for i, row in enumerate(disp_rows):
        tail = hud_lines[i] if i < len(hud_lines) else ""
        out.append(row + "  " + tail + "\x1b[K")
    return "\r\n".join(out) + "\x1b[J"


def _dynamic_hud(ui, status):
    (d0, h0), (d1, h1) = status
    dot = lambda d: "●" if d else "○"
    return _HUD + [
        "",
        "enc0 sw: %s  held %4.1fs" % (dot(d0), h0),
        "enc1 sw: %s  held %4.1fs" % (dot(d1), h1),
        "sel: %d %-9s vol: %d" % (ui.sel, "(%s)" % _MENU[ui.sel], ui.value),
        "entered: %s" % (ui.entered or "-"),
        "last: %s" % ui.last_event,
    ]


def _selftest(mode):
    """Render one demo frame (after a few synthetic events) and print it. No TTY."""
    renderer = TerminalRenderer(mode)
    kb = KeyboardInput()
    ui = DemoScreen()
    t = 0.0
    for ch in "eeed s".replace(" ", ""):  # scroll menu, bump value
        for ev in kb.feed(ch, t):
            ui.handle(ev, t)
        t += 0.2
    for row in renderer.render(ui.render(t)):
        print(row)
    print("\n".join(_dynamic_hud(ui, kb.switch_status(t))))


def main(argv):
    mode = "half" if "--half" in argv else "braille"
    if "--selftest" in argv:
        _selftest(mode)
        return

    if not sys.stdin.isatty():
        print("emulator needs a TTY (interactive terminal). "
              "Try: python3 ganglion/emulator.py --selftest")
        return

    import termios
    import tty
    import select

    renderer = TerminalRenderer(mode)
    kb = KeyboardInput()
    ui = DemoScreen()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?25l\x1b[?1049h\x1b[2J")  # hide cursor, alt screen
        while True:
            now = time.monotonic()
            while select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.read(1)
                if ch in ("x", "X"):
                    return
                for ev in kb.feed(ch, now):
                    ui.handle(ev, now)
            frame = renderer.render(ui.render(now))
            hud = _dynamic_hud(ui, kb.switch_status(now))
            sys.stdout.write("\x1b[H" + _compose(frame, hud))
            sys.stdout.flush()
            time.sleep(0.03)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[?1049l\x1b[?25h")  # restore screen + cursor
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main(sys.argv[1:])
