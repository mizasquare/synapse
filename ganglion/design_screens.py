"""Design 2a screens ported to the real 1-bit PIL pipeline (from the mockup).

Replicates the mockup's pixel primitives (T / box / gBar / dots / dashed) and its
Silkscreen(8/16/24/32) + Micro5(6) type tiers in Pillow ``mode "1"``, so we can
see the design at true 128x128 monochrome through ``ganglion.display`` and
measure real I2C update cost with ``ganglion.i2c_cost`` on the moments that
actually redraw (marquee scroll, snapshot switch, knob adjust, tuner needle).

Run:
    python3 ganglion/design_screens.py            # render glance + chain, print costs
    python3 ganglion/design_screens.py --half     # crisper (needs wide terminal)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont

from ganglion import WIDTH, HEIGHT
from ganglion.display import TerminalRenderer
from ganglion import i2c_cost

_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
_SILK = os.path.join(_FONTS, "Silkscreen-Regular.ttf")
_SILKB = os.path.join(_FONTS, "Silkscreen-Bold.ttf")
_MICRO = os.path.join(_FONTS, "Micro5-Regular.ttf")


# --- type tiers (mirror the mockup's FS/FF: Silkscreen body, Micro5 6px floor) ---
def _fs(v):
    return 6 if v <= 7 else 8 if v <= 13 else 16 if v <= 22 else 24 if v <= 34 else 32


class _Face:
    """A pixel font at one size, drawn ink-top-aligned so y == visual top."""
    _cache = {}

    def __init__(self, path, size):
        self.font = ImageFont.truetype(path, size)
        self.top = self.font.getbbox("ABCXYZ0289gjpq")[1]  # min ink top at this size

    @classmethod
    def get(cls, path, size):
        key = (path, size)
        if key not in cls._cache:
            cls._cache[key] = cls(path, size)
        return cls._cache[key]

    def draw(self, d, x, y, s, fill, ls=0):
        if ls <= 0:
            d.text((x, y - self.top), s, font=self.font, fill=fill)
            return
        cx = x
        for ch in s:
            d.text((cx, y - self.top), ch, font=self.font, fill=fill)
            cx += round(self.font.getlength(ch)) + ls

    def width(self, s, ls=0):
        w = self.font.getlength(s)
        return w + ls * max(0, len(s) - 1)


def _face(size):
    # Micro5 is a "5px" font: its glyphs render ~5-6px tall but only rasterize
    # cleanly at ~10pt. The mockup's 6px floor tier maps to Micro5 @10 here
    # (verified: @6/@8 are illegible in 1-bit, @10 is crisp incl. lowercase).
    if size <= 7:
        return _Face.get(_MICRO, 10)
    px = _fs(size)
    path = _SILKB if size >= 23 else _SILK
    return _Face.get(path, px)


class Screen:
    """The mockup's drawing surface, 128x128 mono, ink = white(1) on black(0)."""

    def __init__(self):
        self.img = Image.new("1", (WIDTH, HEIGHT), 0)
        self.d = ImageDraw.Draw(self.img)

    def T(self, s, x, y, size, ls=0, fill=1):
        _face(size).draw(self.d, x, y, s, fill, ls)

    def Tw(self, size, s, ls=0):
        return _face(size).width(s, ls)

    def hline(self, x, y, w):
        self.d.rectangle([x, y, x + w - 1, y], fill=1)

    def box(self, x, y, w, h, fill=False):
        if fill:
            self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=1)
        else:
            self.d.rectangle([x, y, x + w - 1, y + h - 1], outline=1)

    def dashed(self, x, y, w, h, on=2, off=2):
        step = on + off
        for i in range(0, w, step):
            self.d.rectangle([x + i, y, min(x + i + on - 1, x + w - 1), y], fill=1)
            self.d.rectangle([x + i, y + h - 1, min(x + i + on - 1, x + w - 1), y + h - 1], fill=1)
        for i in range(0, h, step):
            self.d.rectangle([x, y + i, x, min(y + i + on - 1, y + h - 1)], fill=1)
            self.d.rectangle([x + w - 1, y + i, x + w - 1, min(y + i + on - 1, y + h - 1)], fill=1)

    def gbar(self, x, y, w, h, n):
        self.box(x, y, w, h)
        fw = int((w - 2) * max(0, min(1, n)))
        if fw > 0:
            self.d.rectangle([x + 1, y + 1, x + fw, y + h - 2], fill=1)

    def dots(self, total, cur, x, y):
        for i in range(total):
            cx = x + i * 6
            if i == cur:
                self.d.ellipse([cx, y, cx + 3, y + 3], fill=1)
            else:
                self.d.ellipse([cx, y, cx + 3, y + 3], outline=1)

    def chip(self, s, x, y, w, h, size, ls=0):
        self.box(x, y, w, h, fill=True)
        self.T(s, x + 3, y + (h - _fs(size)) // 2, size, ls=ls, fill=0)


# ---- sample state (mirrors the mockup's makeBoard / PBS / SNAPS) ----
PBS = ["Lead Joyful", "Clean Verse", "Ambient Cathedral Wash XL"]
SNAPS = ["Default", "Lead Boost", "Ambient"]
BOARD = [
    dict(name="Comp", abbr="CMP", bypass=False,
         knobs=[("Thresh", "-24 dB", .60), ("Ratio", "4:1", .16),
                ("Attack", "12 ms", .11), ("Makeup", "6 dB", .25)]),
    dict(name="Drive", abbr="DRV", bypass=False,
         knobs=[("Gain", "0.62", .62), ("Tone", "0.50", .50),
                ("Level", "0.72", .72), ("Bass", "0.40", .40)]),
    dict(name="NAM", abbr="AMP", bypass=False,
         knobs=[("Input", "-6 dB", .35), ("Output", "-3 dB", .42), ("Model", "Fender Twin", 0)]),
    dict(name="Cab", abbr="CAB", bypass=True, knobs=[("Level", "0.80", .80)]),
    dict(name="Delay", abbr="DLY", bypass=False, knobs=[("Time", "380 ms", .30)]),
    dict(name="Reverb", abbr="RVB", bypass=False, knobs=[("Decay", "2.4 s", .20)]),
]


def glance_frame(pb=0, snap=0, dirty=False, pb_scroll=0):
    """Depth -1 board/snapshot glance (the mockup's default screen)."""
    s = Screen()
    s.T("PEDALBOARD", 6, 5, 8, ls=1)
    _name(s, PBS[pb], 5, 14, 24, band=(0, 14, 108, 24), scroll=pb_scroll)
    s.dots(len(PBS), pb, 6, 47)
    s.hline(0, 56, 128)
    s.T("SNAPSHOT", 6, 62, 8, ls=1)
    s.T(SNAPS[snap], 5, 71, 24)
    s.dots(len(SNAPS), snap, 6, 99)
    s.T("e0 pb·CLK menu  e1 snap·CLK menu", 5, 118, 6)
    s.T("-1", 116, 5, 8)
    if dirty:
        s.d.ellipse([120, 2, 125, 7], fill=1)
    return s.img


def _name(s, text, x, y, size, band, scroll=0):
    """Static name, or clipped+shifted (marquee) when scroll!=0 / too long."""
    if scroll == 0 and s.Tw(size, text) <= band[2]:
        s.T(text, x, y, size)
        return
    bx, by, bw, bh = band
    strip = Image.new("1", (max(1, int(s.Tw(size, text))) + 16, bh), 0)
    _face(size).draw(ImageDraw.Draw(strip), 0, y - by, text, 1)
    s.img.paste(strip.crop((scroll, 0, scroll + bw, bh)), (bx, by))


def chain_frame(node=1, knob=0, locked=False):
    """Depth 0 main: IN/OUT meter row + 5-node strip + bottom knob band."""
    s = Screen()
    s.T("IN", 2, 1, 8)
    s.T("-14.2", 16, 1, 8)
    s.T("OUT", 54, 1, 8)
    s.T("-4.3", 74, 1, 8)
    s.T("%d/%d" % (node + 1, len(BOARD)), 101, 1, 6)
    # node strip, window of 5 centred on selection
    step, cw, ty, ch = 25, 23, 13, 24
    wy = ty + ch // 2  # signal wire runs at the cells' vertical middle
    cells = []
    for j in range(5):
        idx = node - 2 + j
        if idx < 0 or idx >= len(BOARD):
            continue
        n = BOARD[idx]
        x = 2 + j * step
        cells.append((idx, x, x + cw - 1))
        sel = idx == node
        if sel:
            s.box(x, ty, cw, ch, fill=True)
            s.T(n["abbr"], x + 3, ty + 9, 12, fill=0)
        elif n["bypass"]:
            s.dashed(x, ty, cw, ch, on=1, off=2)
            s.T(n["abbr"], x + 3, ty + 9, 12)
        else:
            s.box(x, ty, cw, ch)
            s.T(n["abbr"], x + 3, ty + 9, 12)
    # wire only in the gaps BETWEEN nodes (not through cells); bleed off-screen
    # only where the chain actually continues past the visible window
    for a in range(len(cells) - 1):
        right = cells[a][2]
        left = cells[a + 1][1]
        if left - 1 >= right + 1:
            s.d.rectangle([right + 1, wy, left - 1, wy], fill=1)
    if cells:
        if cells[0][0] > 0:
            s.d.rectangle([0, wy, cells[0][1] - 1, wy], fill=1)
        if cells[-1][0] < len(BOARD) - 1:
            s.d.rectangle([cells[-1][2] + 1, wy, WIDTH - 1, wy], fill=1)
    s.hline(0, 40, 128)
    # bottom band
    n = BOARD[node]
    s.T(n["name"], 4, 43, 16)
    s.T("BYP" if n["bypass"] else n["abbr"], 100, 45, 8)
    kx, base, kh, cw2 = [5, 67], 62, 21, 56
    for i, (kn, kv, nr) in enumerate(n["knobs"][:6]):
        col, row = i % 2, i // 2
        if row >= 3:
            break
        x, yy = kx[col], base + row * kh
        if i == knob:
            if locked:
                s.box(x - 3, yy - 2, cw2, kh - 1)
            else:
                s.dashed(x - 3, yy - 2, cw2, kh - 1, on=2, off=2)
        s.T(kn, x, yy, 8)
        s.T(kv, x, yy + 8, 8)
        s.gbar(x, yy + 17, cw2 - 8, 3, nr)
    return s.img


def tuner_frame(note="A", cents=6):
    s = Screen()
    s.T("TUNER", 6, 4, 8, ls=1)
    s.T("e1 hold ret", 84, 4, 6)
    w = s.Tw(46, note)
    s.T(note, int((128 - w) / 2), 18, 46)
    s.hline(10, 88, 108)
    for i in range(-2, 3):
        s.d.rectangle([64 + i * 24, 84, 64 + i * 24, 92], fill=1)
    nx = 64 + max(-52, min(52, round(cents / 50 * 52)))
    s.box(nx - 1, 76, 3, 20, fill=True)
    s.T("b", 6, 78, 8)
    s.T("#", 118, 78, 8)
    if abs(cents) < 5:
        s.chip("IN TUNE", 40, 104, 48, 16, 8)
    else:
        txt = ("+" if cents > 0 else "") + str(cents) + " cents"
        s.T(txt, int((128 - s.Tw(8, txt)) / 2), 107, 8)
    return s.img


def _show(title, img, renderer):
    print("\n=== %s ===" % title)
    for row in renderer.render(img):
        print(row)


def main(argv):
    mode = "half" if "--half" in argv else "braille"
    r = TerminalRenderer(mode)

    glance = glance_frame(pb=0, snap=0)
    chain = chain_frame(node=1, knob=0)
    tuner = tuner_frame("A", 6)
    _show("GLANCE (depth -1)", glance, r)
    _show("CHAIN (depth 0)", chain, r)
    _show("TUNER", tuner, r)

    print("\n================ I2C UPDATE COST (SH1107, page = 8px x 128) ================")
    print(i2c_cost.fmt(i2c_cost.full_cost(), "FULL redraw            "))
    # snapshot switch: only the snapshot half changes
    print(i2c_cost.fmt(i2c_cost.diff_cost(glance_frame(0, 0), glance_frame(0, 1)),
                       "snapshot switch        "))
    # marquee: long PB name scrolled 4px inside its 24px band
    long_a = glance_frame(pb=2, snap=0, pb_scroll=0)
    long_b = glance_frame(pb=2, snap=0, pb_scroll=4)
    print(i2c_cost.fmt(i2c_cost.diff_cost(long_a, long_b), "marquee step (name band)"))
    # knob adjust: one value + bar in the bottom band
    ka = chain_frame(node=1, knob=0)
    board2 = BOARD[1]["knobs"][0]
    BOARD[1]["knobs"][0] = ("Gain", "0.66", .66)
    kb = chain_frame(node=1, knob=0)
    BOARD[1]["knobs"][0] = board2
    print(i2c_cost.fmt(i2c_cost.diff_cost(ka, kb), "knob adjust (1 value)   "))
    # tuner needle move
    print(i2c_cost.fmt(i2c_cost.diff_cost(tuner_frame("A", 6), tuner_frame("A", -14)),
                       "tuner needle step       "))
    # node scroll: whole strip + band change
    print(i2c_cost.fmt(i2c_cost.diff_cost(chain_frame(1, 0), chain_frame(2, 0)),
                       "node scroll (strip+band)"))
    print("\nRule of thumb @400kHz: ~44 KB/s budget. Static screen = draw freely;")
    print("keep per-frame animation to one page-band and it stays double-digit fps.")


if __name__ == "__main__":
    main(sys.argv[1:])
