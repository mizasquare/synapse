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

STATUS: the diff/pack half is verified off-metal -- ``python3 -m
ganglion.tools.oled_bench`` replays every span into a fake panel and asserts its
framebuffer equals the drawn frame on every tick. ``LumaWriter``, the half that
actually puts bytes on the wire, is **unverified on hardware** -- see its TODOs.
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

    STUB -- written against the SH1107 datasheet + luma.oled, unverified on metal.
    Three things to pin down when the panel arrives (mirrors hw/seesaw.py):

      1. **Addressing mode.** These are page-addressing commands (0xB0|page, then
         column low/high). luma's sh1107 init may leave the chip in *vertical*
         addressing, in which case the pointer must be reset once here.
      2. **Column offset.** Some 128x128 SH1107 modules map column 0 to an offset
         (commonly 0). If the image comes out shifted horizontally, this is why.
      3. **Row-vs-column pages.** If a full push renders correctly but a partial
         one lands on the wrong band, the page axis is transposed against ours.

    All three fail *visibly* on the first frame (shifted, torn, or wrong-band),
    so ``python3 ganglion/app.py --device`` is the test -- there is nothing
    subtle to catch here, which is why this stayed a stub rather than a guess
    dressed up as a fallback.
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
