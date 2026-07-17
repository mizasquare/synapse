"""1-bit drawing primitives + pixel-font tiers for the 128x128 OLED.

Shared by the live app (``ganglion.app``) and the frozen design/cost demo
(``ganglion.design_screens``). Ink = white(1) on black(0) in Pillow ``mode "1"``,
which is exactly what luma pushes to the SH1107. Type tiers mirror the adopted
mockup: Silkscreen(8/16/24/32) for body, Micro5 for the floor tier — rendered at
10pt because Micro5 is a "5px" font whose glyphs only rasterize cleanly there
(verified: @6/@8 are illegible in 1-bit, @10 is crisp incl. lowercase).
"""

import collections
import os

from PIL import Image, ImageDraw, ImageFont

from ganglion import WIDTH, HEIGHT

_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
_SILK = os.path.join(_FONTS, "Silkscreen-Regular.ttf")
_SILKB = os.path.join(_FONTS, "Silkscreen-Bold.ttf")
_MICRO = os.path.join(_FONTS, "Micro5-Regular.ttf")

# Rasterised-text cache bound, per face. The app draws ~20 strings a frame and
# most repeat forever (labels, furniture), but some are values -- knob readouts,
# dB levels -- that never repeat, so an unbounded cache keyed on drawn text would
# creep for as long as the box is up. 256/face holds every static string with room
# to spare; a miss costs one rasterisation (~0.26ms), not a stall.
MASK_CACHE_MAX = 256


def fs(v):
    """Snap a nominal size to a type tier's visual pixel height."""
    return 6 if v <= 7 else 8 if v <= 13 else 16 if v <= 22 else 24 if v <= 34 else 32


class _Face:
    """A pixel font at one size, drawn ink-top-aligned so y == visual top.

    Text is rasterised **once per string** and the glyph run is then blitted
    (``draw``); ``draw_slow`` is the same thing done the obvious way, straight
    through ``ImageDraw.text``. That is not dead code -- it is the oracle
    ``app.py --fonttest`` renders every screen against, because ``draw`` reaches
    past Pillow's public surface (``_getink``, ``draw.draw_bitmap``) to skip the
    re-rasterisation. Those are exactly what ``ImageDraw.text`` itself calls, but
    they are private, so the day Pillow moves them this has to fail loudly rather
    than draw something subtly wrong.

    Why bother: re-rasterising the same strings every tick was **97% of the frame**
    (8.7ms of an 8.7ms render, measured). At 33 ticks/s that is ~29% of a core
    burned redrawing an unchanged screen -- and, because a cffi JACK callback has
    to take the GIL, it was also 40 xruns/s the moment the level meter (decision H)
    tried to share this process. Cached, a frame costs 0.25ms and the xruns are
    gone (measured: 0/s at <=1ms hold, identical to not drawing at all).

    A per-glyph atlas was measured too -- the alphabet is ASCII and the tiers are
    fixed, so the whole set bakes to 5,345 bytes. It was rejected: composing a
    string from glyphs rounds the advance per character, the error accumulates,
    and 9 of 15 test frames came out different. It bought 0.05ms for a silent
    change to settled typography.
    """
    _cache = {}

    def __init__(self, path, size):
        self.font = ImageFont.truetype(path, size)
        b = self.font.getbbox("ABCXYZ0289gjpq")  # the tier's ink band: constant per
        self.top = b[1]                          # face, so measure it once here and
        self.ink_h = b[3] - b[1]                 # not on every Th()/Tclip() call
        self._mask = collections.OrderedDict()   # str -> (glyph run, offset)
        self._len = collections.OrderedDict()    # str -> advance width

    @classmethod
    def get(cls, path, size):
        key = (path, size)
        if key not in cls._cache:
            cls._cache[key] = cls(path, size)
        return cls._cache[key]

    @staticmethod
    def _hit(cache, key, make):
        got = cache.get(key)
        if got is None:
            got = cache[key] = make()
            if len(cache) > MASK_CACHE_MAX:
                cache.popitem(last=False)        # LRU-ish: evict one, never bulk-
        else:                                    # clear (a cold cache is an 8ms
            cache.move_to_end(key)               # frame, i.e. an xrun)
        return got

    def _blit(self, d, x, y, s, fill):
        m, off = self._hit(self._mask, s, lambda: self.font.getmask2(s, mode="1"))
        if m.size[0] and m.size[1]:
            d.draw.draw_bitmap((x + off[0], y + off[1]), m, d._getink(fill)[0])

    def draw(self, d, x, y, s, fill, ls=0):
        if ls <= 0:
            self._blit(d, x, y - self.top, s, fill)
            return
        cx = x
        for ch in s:
            self._blit(d, cx, y - self.top, ch, fill)
            cx += round(self.length(ch)) + ls

    def draw_slow(self, d, x, y, s, fill, ls=0):
        """The uncached path -- kept as ``draw``'s oracle (see the class docstring)."""
        if ls <= 0:
            d.text((x, y - self.top), s, font=self.font, fill=fill)
            return
        cx = x
        for ch in s:
            d.text((cx, y - self.top), ch, font=self.font, fill=fill)
            cx += round(self.font.getlength(ch)) + ls

    def length(self, s):
        return self._hit(self._len, s, lambda: self.font.getlength(s))

    def width(self, s, ls=0):
        return self.length(s) + ls * max(0, len(s) - 1)


def face(size):
    if size <= 7:
        return _Face.get(_MICRO, 10)  # Micro5 floor tier renders at 10pt
    return _Face.get(_SILKB if size >= 23 else _SILK, fs(size))


class Screen:
    """The mockup's drawing surface: 128x128 mono, ink = white(1) on black(0)."""

    def __init__(self):
        self.img = Image.new("1", (WIDTH, HEIGHT), 0)
        self.d = ImageDraw.Draw(self.img)

    def T(self, s, x, y, size, ls=0, fill=1):
        face(size).draw(self.d, x, y, s, fill, ls)

    def Tw(self, size, s, ls=0):
        return face(size).width(s, ls)

    def Th(self, size):
        """Ink height of a tier — the exact band a line of text occupies."""
        return face(size).ink_h

    def Tclip(self, s, x, y, size, maxw, off=0, fill=1, bg=0):
        """Draw text into a maxw-wide band, shifted left by ``off`` px and clipped
        to it. The band is composed off-screen and pasted, so glyphs can never
        bleed past the box — this is what lets a name scroll (app._marq)."""
        band = Image.new("1", (max(1, maxw), self.Th(size)), bg)
        face(size).draw(ImageDraw.Draw(band), -off, 0, s, fill)
        self.img.paste(band, (x, y))

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

    def dots(self, total, cur, x, y, fill=1):
        # fill=0 draws them onto an inverted (filled) row -- SYSTEM's focused item
        for i in range(total):
            cx = x + i * 6
            if i == cur:
                self.d.ellipse([cx, y, cx + 3, y + 3], fill=fill)
            else:
                self.d.ellipse([cx, y, cx + 3, y + 3], outline=fill)

    def chip(self, s, x, y, w, h, size, ls=0, center=True):
        self.box(x, y, w, h, fill=True)
        tx = x + (max(0, (w - int(self.Tw(size, s, ls))) // 2) if center else 3)
        self.T(s, tx, y + (h - fs(size)) // 2, size, ls=ls, fill=0)
