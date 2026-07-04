"""1-bit drawing primitives + pixel-font tiers for the 128x128 OLED.

Shared by the live app (``ganglion.app``) and the frozen design/cost demo
(``ganglion.design_screens``). Ink = white(1) on black(0) in Pillow ``mode "1"``,
which is exactly what luma pushes to the SH1107. Type tiers mirror the adopted
mockup: Silkscreen(8/16/24/32) for body, Micro5 for the floor tier — rendered at
10pt because Micro5 is a "5px" font whose glyphs only rasterize cleanly there
(verified: @6/@8 are illegible in 1-bit, @10 is crisp incl. lowercase).
"""

import os

from PIL import Image, ImageDraw, ImageFont

from ganglion import WIDTH, HEIGHT

_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
_SILK = os.path.join(_FONTS, "Silkscreen-Regular.ttf")
_SILKB = os.path.join(_FONTS, "Silkscreen-Bold.ttf")
_MICRO = os.path.join(_FONTS, "Micro5-Regular.ttf")


def fs(v):
    """Snap a nominal size to a type tier's visual pixel height."""
    return 6 if v <= 7 else 8 if v <= 13 else 16 if v <= 22 else 24 if v <= 34 else 32


class _Face:
    """A pixel font at one size, drawn ink-top-aligned so y == visual top."""
    _cache = {}

    def __init__(self, path, size):
        self.font = ImageFont.truetype(path, size)
        self.top = self.font.getbbox("ABCXYZ0289gjpq")[1]

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
        return self.font.getlength(s) + ls * max(0, len(s) - 1)


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

    def chip(self, s, x, y, w, h, size, ls=0, center=True):
        self.box(x, y, w, h, fill=True)
        tx = x + (max(0, (w - int(self.Tw(size, s, ls))) // 2) if center else 3)
        self.T(s, tx, y + (h - fs(size)) // 2, size, ls=ls, fill=0)
