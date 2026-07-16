"""Real display sink: SH1107 over I2C, pushing only what changed.

The stub sink shipped a whole 2048-byte frame every tick. On this panel that is
the worst thing we can do: the mount is fixed at 180deg (design.md §2), which
lands on the SH1107's slow axis, so a full frame caps out around 10 fps -- and
it hogs the bus the encoders are polled on. Almost every frame we draw, though,
differs from the last one in a single 8px page band (a marquee step, a tuner
needle, one knob value) or not at all.

So this sink diffs. Three levels of doing less:

  1. **Nothing changed** -> not a single byte goes out. Static screens are free,
     which is most of the time the device is on.
  2. **Something changed** -> PIL's ``ImageChops.difference().getbbox()`` bounds
     it at C speed, and only the page-rows that box touches get packed.
  3. **Within each page-row** -> only the column span from the first to the last
     differing byte is written.

``ganglion.i2c_cost`` is the model this implements (and ``tools/oled_bench.py``
measures against real frame sequences); ``frame_pages`` there is the packer, so
the driver and the cost model can't drift apart.

Seam: ``DiffSink.show(frame)`` is the sink the Runtime already calls. The bytes
leave through an injected *writer* -- ``LumaWriter`` on metal, a counting fake in
the bench -- so all the diff logic above is testable with no hardware present.

STATUS: verified end to end. The diff/pack half is proven off-metal -- ``python3
-m ganglion.tools.oled_bench`` replays every span into a fake panel and asserts
its framebuffer equals the drawn frame on every tick. ``LumaWriter``, the half
that puts bytes on the wire, is now proven **on the panel** -- ``python3 -m
ganglion.tools.oled_probe`` renders the same frame through luma's own
``display()`` and through this driver and they agree.
"""

from PIL import ImageChops

from ganglion.i2c_cost import PAGE_H, WIDTH, frame_pages, page_span


class DiffSink:
    """Sink seam: push only the page-row column spans that changed."""

    def __init__(self, writer, preprocess=None, width=WIDTH):
        self.writer = writer
        # luma applies the mount rotation in ``device.preprocess``. We diff in
        # *panel* space (post-rotation), because that is the space the panel's
        # pages are defined in -- diffing the upright UI image would map its rows
        # onto the wrong pages.
        self.preprocess = preprocess or (lambda im: im)
        self.width = width
        self.prev = None          # last image pushed, panel space, mode "1"
        self.pages = None         # its packed page-rows (so we never re-pack it)
        self.stats = {"frames": 0, "skipped": 0, "bytes": 0, "spans": 0}

    def show(self, frame):
        img = self.preprocess(frame).convert("1")
        if self.prev is None:
            box = (0, 0, self.width, img.size[1])      # first frame: full push
        else:
            box = ImageChops.difference(img, self.prev).getbbox()
        self.stats["frames"] += 1
        if box is None:                                # (1) identical -> silence
            self.stats["skipped"] += 1
            return 0
        x0, y0, x1, y1 = box
        p0, p1 = page_span(y0, y1 - y0)                # (2) pack only these rows
        band = frame_pages(img.crop((0, p0 * PAGE_H, self.width, (p1 + 1) * PAGE_H)))
        sent = 0
        for i, row in enumerate(band):
            p = p0 + i
            if self.pages is None:
                cols = [x0, x1 - 1]                    # first frame: whole width
            else:
                old = self.pages[p]
                cols = [x for x in range(x0, x1) if old[x] != row[x]]
                if not cols:                           # bbox is a rectangle; a row
                    continue                           # inside it can still be clean
            c0, c1 = cols[0], cols[-1]                 # (3) one contiguous span
            self.writer.write(p, c0, bytes(row[c0:c1 + 1]))
            sent += c1 - c0 + 1
            self.stats["spans"] += 1
        if self.pages is None:
            self.pages = frame_pages(img)
        else:
            for i, row in enumerate(band):
                self.pages[p0 + i] = row
        self.prev = img
        self.stats["bytes"] += sent
        return sent


class LumaWriter:
    """Write one page-row span to a real SH1107 through luma's command/data seam.

    Verified on metal (``tools/oled_probe``, panel at 0x3D). The three unknowns
    this class carried as TODOs while it was a stub all resolved in its favour --
    recorded here because each was a real fork, not a formality:

      1. **Addressing mode.** luma's ``sh1107`` init pumps a bare ``0x20``. That
         is SSD1306's *two-byte* MEMORYMODE opcode, and luma reuses the SSD1306
         constant table for this chip -- but on an SH1107 ``0x20`` is a complete
         one-byte command meaning **page addressing** (``0x21`` would be
         vertical). So the chip is already in the mode these commands assume and
         the pointer needs no reset. The feared case was the opposite.
      2. **Column offset.** 0. luma's own ``display()`` writes column 0 for the
         128x128 variant (``displayoffset=0x00``), and our border lands on the
         edge, so this module does not shift its columns.
      3. **Row-vs-column pages.** Not transposed: partial pushes land in the band
         they were packed for (``oled_probe --stage diff``).

    We address the page and column exactly as luma's ``display()`` does, only
    with a span instead of the full 128 -- same registers, and their order does
    not matter as each command sets an independent one.

    The stakes are the whole reason the app can run: a full frame measures
    **220ms** here (luma packs pixels in a per-pixel Python loop, on a 100kHz
    bus), which is 7 ticks long and would starve the encoders sharing the bus.
    A diffed tick is ~10ms, and an unchanged one 0.4ms.
    """

    def __init__(self, device, col_offset=0):
        self.device = device
        self.col_offset = col_offset

    def write(self, page, col, data):
        c = col + self.col_offset
        self.device.command(0xB0 | page, 0x00 | (c & 0x0F), 0x10 | ((c >> 4) & 0x0F))
        self.device.data(list(data))


class CountingWriter:
    """Fake writer: records spans instead of sending them (bench + tests)."""

    def __init__(self):
        self.spans = []

    def write(self, page, col, data):
        self.spans.append((page, col, len(data)))

    @property
    def data_bytes(self):
        return sum(n for _, _, n in self.spans)
