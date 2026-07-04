"""SH1107 128x128 I2C update-cost model — how many bytes a redraw actually sends.

The panel's framebuffer is organized in **pages**: 8 pixels tall x 128 wide, so
128/8 = 16 page-rows, each column of a page = 1 byte (8 vertical pixels). A full
frame is 16 x 128 = 2048 data bytes. Partial-update granularity is therefore
**8px vertically (page) x 1px horizontally (column)** — you cannot push fewer
than a whole page-row's worth of a column.

Given a dirty region (or a diff between two frames), this computes the bytes that
must go over I2C and the resulting time / max fps at 100k / 400k / 1M Hz. Wire
time only (9 bits per byte incl. ack); real throughput is ~0.6-0.8x this ceiling
once Python + library per-call overhead and the SH1107 orientation penalty are
counted (measured: full frame ~10 fps @0/180deg, ~16 fps @90/270deg at 400kHz).
"""

WIDTH = 128
HEIGHT = 128
PAGE_H = 8
PAGES = HEIGHT // PAGE_H          # 16
BYTES_PER_PAGE = WIDTH           # 128
FULL_FRAME_BYTES = PAGES * BYTES_PER_PAGE  # 2048

# Per page-row overhead when addressing a partial update (conservative):
#   set-page-addr + col-low + col-high commands, each with a control byte, plus
#   one 0x40 data-control byte and I2C start/addr/stop framing for the chunk.
_PAGE_CMD_OVERHEAD = 6
_DATA_CONTROL = 1
_TXN_OVERHEAD = 2
_PER_PAGEROW_OVERHEAD = _PAGE_CMD_OVERHEAD + _DATA_CONTROL + _TXN_OVERHEAD  # 9

FREQS = {"100kHz": 100_000, "400kHz": 400_000, "1MHz": 1_000_000}


def _byte_us(freq_hz):
    return 9.0 / freq_hz * 1e6  # 8 data bits + 1 ack


def _summary(data_bytes, overhead_bytes, extra=None):
    total = data_bytes + overhead_bytes
    out = {
        "data_bytes": data_bytes,
        "overhead_bytes": overhead_bytes,
        "total_bytes": total,
        "ms": {k: round(total * _byte_us(f) / 1000.0, 2) for k, f in FREQS.items()},
        "max_fps": {k: round(1e6 / (total * _byte_us(f)), 1) for k, f in FREQS.items()},
    }
    if extra:
        out.update(extra)
    return out


def page_span(y, h):
    """Page-rows a vertical band [y, y+h) touches, as inclusive (p0, p1)."""
    p0 = max(0, y // PAGE_H)
    p1 = min(PAGES - 1, (y + h - 1) // PAGE_H)
    return p0, p1


def rect_cost(x, y, w, h):
    """A-priori cost of pushing a dirty rectangle (rounds up to whole page-rows)."""
    p0, p1 = page_span(y, h)
    nrows = p1 - p0 + 1
    data = nrows * w
    overhead = nrows * _PER_PAGEROW_OVERHEAD
    return _summary(data, overhead, {
        "region": (x, y, w, h), "page_rows": nrows, "cols": w,
    })


def full_cost():
    """Cost of a whole-screen redraw."""
    return rect_cost(0, 0, WIDTH, HEIGHT)


def frame_pages(img):
    """Pack a PIL image into 16 page-rows of 128 bytes (as the panel stores it)."""
    px = img.convert("1").load()
    pages = []
    for p in range(PAGES):
        row = bytearray(WIDTH)
        for x in range(WIDTH):
            b = 0
            for bit in range(PAGE_H):
                if px[x, p * PAGE_H + bit]:
                    b |= (1 << bit)
            row[x] = b
        pages.append(row)
    return pages


def diff_cost(prev_img, cur_img):
    """Exact cost of a smart driver pushing only the changed page-columns.

    Per changed page-row, sends the contiguous column span from the first to the
    last differing column (what a real dirty-rect driver does)."""
    pp = frame_pages(prev_img)
    cp = frame_pages(cur_img)
    data = 0
    overhead = 0
    spans = []
    for p in range(PAGES):
        cols = [x for x in range(WIDTH) if pp[p][x] != cp[p][x]]
        if not cols:
            continue
        span = cols[-1] - cols[0] + 1
        data += span
        overhead += _PER_PAGEROW_OVERHEAD
        spans.append((p, cols[0], cols[-1]))
    return _summary(data, overhead, {
        "page_rows_touched": len(spans), "spans": spans,
    })


def fmt(cost, label=""):
    """One-line human summary of a cost dict."""
    ms = cost["ms"]
    fps = cost["max_fps"]
    head = (label + ": ") if label else ""
    return ("%s%d B (%d data + %d ovh)  |  400kHz %.1fms→%.0ffps  "
            "100kHz %.1fms→%.0ffps  1MHz %.1fms→%.0ffps"
            % (head, cost["total_bytes"], cost["data_bytes"], cost["overhead_bytes"],
               ms["400kHz"], fps["400kHz"], ms["100kHz"], fps["100kHz"],
               ms["1MHz"], fps["1MHz"]))
