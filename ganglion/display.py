"""128x128 monochrome framebuffer + a CLI renderer that draws it to the terminal.

The production path (later) pushes a Pillow ``Image`` (mode ``"1"``, 128x128) to
the real SH1107 over I2C via luma.oled. This module keeps the *same* image
contract but renders to the terminal instead, so the whole UI can be built and
watched with no hardware -- the display half of the emulator (see
``ganglion/emulator.py`` and design.md #8).

Two packings, both faithful (1 terminal dot == 1 OLED pixel):

- ``"braille"`` (default): 2x4 pixels per glyph (U+2800 block) -> 64x32 chars.
  Compact; fits a normal-width terminal. Best for the full 128x128.
- ``"half"``: 2 pixels per glyph vertically (upper/lower half block) -> 128x64
  chars. Crisper but needs a >=128-column terminal.
"""

from ganglion import WIDTH, HEIGHT

# Braille dot -> bit within a 2(w)x4(h) cell (Unicode U+2800 + bits).
_BRAILLE = [
    (0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08),
    (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80),
]
# (top, bottom) -> half-block glyph.
_HALF = {(0, 0): " ", (1, 0): "▀", (0, 1): "▄", (1, 1): "█"}


class TerminalRenderer:
    """Turn a 128x128 mono ``Image`` into a list of terminal row strings."""

    def __init__(self, mode="braille"):
        if mode not in ("braille", "half"):
            raise ValueError("mode must be 'braille' or 'half'")
        self.mode = mode

    @property
    def cols(self):
        return WIDTH // 2 if self.mode == "braille" else WIDTH

    @property
    def rows(self):
        return HEIGHT // 4 if self.mode == "braille" else HEIGHT // 2

    def render(self, image):
        """``image``: PIL Image (any mode). Returns a list of row strings."""
        data = list(image.convert("1").getdata())  # 0 / 255, len == W*H

        def on(x, y):
            return x < WIDTH and y < HEIGHT and data[y * WIDTH + x]

        if self.mode == "braille":
            out = []
            for cy in range(0, HEIGHT, 4):
                line = []
                for cx in range(0, WIDTH, 2):
                    bits = 0
                    for dx, dy, bit in _BRAILLE:
                        if on(cx + dx, cy + dy):
                            bits |= bit
                    line.append(chr(0x2800 + bits))
                out.append("".join(line))
            return out

        out = []
        for cy in range(0, HEIGHT, 2):
            line = [_HALF[(1 if on(x, cy) else 0, 1 if on(x, cy + 1) else 0)]
                    for x in range(WIDTH)]
            out.append("".join(line))
        return out
