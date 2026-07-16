"""On-metal OLED bring-up: the half ``tools/oled_bench`` structurally cannot test.

``oled_bench`` replays real ``app.render`` sequences into a *fake* panel and
asserts the framebuffer matches byte-for-byte, so the diff/pack half of
``hw/oled.py`` is already proven lossless. What it cannot prove is that the bytes
land correctly on a real SH1107 -- that was ``LumaWriter``'s standing TODO list.
This is the counterpart that answers it, the way ``encoder_bench`` did for the
seesaw modules: it drives the *same* ``DiffSink``/``LumaWriter`` the app uses, so
a good run here is a good run for the real display path.

Every question it answers fails **visibly**, which is why these are screens and
not assertions:

  1. **Which ``rotate`` renders upright.** design.md #2 fixed the mount FFC-down
     and left the exact luma value to be settled on metal. ``orient`` draws the
     same card at rotate 0..3 -- the upright one is the answer.
  2. **Column offset.** Every card's border touches all four edges. A missing
     edge or wrapped content means the module maps column 0 somewhere else
     (``LumaWriter(col_offset=)``).
  3. **Page axis.** ``grid``'s 16 numbered bands are horizontal 8px page-rows.
     If they come out vertical, our page axis is transposed against the panel's.
  4. **Does our writer agree with luma?** ``ab`` alternates the *same* frame
     through luma's own full-frame ``display()`` -- the reference implementation
     -- and through ``DiffSink``+``LumaWriter``. Agreement looks like a **still
     image**; any flicker is our writer disagreeing with the reference, and the
     stage says which half you are looking at as it goes.

``app`` is the payoff: the real UI, animating its marquee through the real diff
driver at the real tick rate, left on the panel when the tool exits.

Run (on the Pi):
    venv/bin/python -m ganglion.tools.oled_probe             # all stages, app left up
    venv/bin/python -m ganglion.tools.oled_probe --stage ab
    venv/bin/python -m ganglion.tools.oled_probe --stage orient
"""

import argparse
import statistics
import subprocess
import time

from PIL import Image

from ganglion import WIDTH, HEIGHT
from ganglion.i2c_cost import PAGE_H, PAGES, PER_PAGEROW_OVERHEAD, wire_ms
from ganglion.hw.oled import DiffSink, LumaWriter
from ganglion.render import Screen

# The panel answers at 0x3D, not the 0x3C that is every SH1107 tutorial's default
# -- Adafruit ship the 128x128 module strapped to 0x3D (confirmed: i2cdetect -y 1
# shows 36 37 3d, the two encoders and this). ``runtime.run_device`` uses the same
# value; if a future module is strapped to 0x3C, --address covers it.
ADDRESS = 0x3D
# rotate=0, read off the glass by the ``orient`` stage. design.md #2 deduced
# rotate=2 from the FFC-down mount and flagged it 잠정; the panel says otherwise.
ROTATE = 0
TICK = 0.03                      # runtime.Runtime default: ~33 Hz

# The bus shipped at **100kHz** -- the Pi's default, and config.txt set no
# dtparam=i2c_arm_baudrate -- while design.md's whole cost model assumes 400kHz,
# so every published figure was 4x optimistic. config.txt now asks for 400kHz;
# this reads the rate actually in force rather than trusting either, so the
# numbers printed are always the ones the panel really sees.
def _bus():
    try:
        with open("/sys/bus/i2c/devices/i2c-1/of_node/clock-frequency", "rb") as f:
            hz = int.from_bytes(f.read(4), "big")
    except OSError:
        return "100kHz"
    return "1MHz" if hz >= 1_000_000 else "400kHz" if hz >= 400_000 else "100kHz"


BUS = _bus()


def _device(rotate=ROTATE, address=ADDRESS):
    """The panel, configured exactly as ``runtime.run_device`` configures it."""
    from luma.core.interface.serial import i2c
    from luma.oled.device import sh1107

    dev = sh1107(i2c(port=1, address=address), width=WIDTH, height=HEIGHT,
                 rotate=rotate)
    # luma registers an atexit hook that blanks and powers the panel off. That is
    # right for an app and wrong for a test screen -- it would wipe the thing we
    # came here to look at the instant the process ends. ``persist`` is luma's own
    # opt-out.
    dev.persist = True
    return dev


def _sink(dev):
    return DiffSink(LumaWriter(dev), preprocess=dev.preprocess)


def _report(label, sink, ticks, elapsed):
    """Bytes/ms per tick at the real bus speed. The encoders share this bus, so
    the number that matters is not fps but how much of the tick we hold it.

    Billed like ``oled_bench.measure``: data + per-span addressing overhead, so
    the two tools' numbers mean the same thing and can be compared directly."""
    st = sink.stats
    total = st["bytes"] + st["spans"] * PER_PAGEROW_OVERHEAD
    per = total / max(1, ticks)
    ms = wire_ms(per, BUS)
    print("  %-22s %6.0f B/tick  %5.1f ms wire @%s  bus %4.1f%%  "
          "silent %d/%d ticks  %.1f fps"
          % (label, per, ms, BUS, 100 * ms / (TICK * 1000),
             st["skipped"], ticks, ticks / max(1e-6, elapsed)))


# ---- cards -----------------------------------------------------------------
def _card_orient(rotate):
    """Which way is up? The wedge marks the true top-left, so the card is only
    self-consistent at one rotation -- read the R-number off the upright one."""
    s = Screen()
    s.box(0, 0, WIDTH, HEIGHT)
    s.d.polygon([(2, 2), (26, 2), (2, 26)], fill=1)      # the TRUE top-left corner
    s.T("TOP", 32, 6, 8)
    lbl = "R%d" % rotate
    s.T("ROTATE", (WIDTH - int(s.Tw(8, "ROTATE"))) // 2, 30, 8)
    s.T(lbl, (WIDTH - int(s.Tw(32, lbl))) // 2, 42, 32)
    s.d.polygon([(64, 78), (54, 92), (74, 92)], fill=1)  # arrow: points at TOP
    s.d.rectangle([61, 92, 67, 106], fill=1)
    s.T("UP", (WIDTH - int(s.Tw(8, "UP"))) // 2, 108, 8)
    s.T("BOTTOM", WIDTH - int(s.Tw(8, "BOTTOM")) - 6, 118, 8)
    return s.img


def _card_grid():
    """The panel's own geometry, drawn: 16 horizontal 8px page-rows numbered 0..F
    down the left, a column ruler ticked every 16px, and a border on all four
    edges. Bands vertical => page axis transposed. Border clipped => col offset."""
    s = Screen()
    s.box(0, 0, WIDTH, HEIGHT)
    for p in range(PAGES):
        y = p * PAGE_H
        s.T("%X" % p, 3, y + 1, 6)                       # one glyph per page-row
        if p % 2 == 0:
            s.d.rectangle([13, y + 1, 34, y + PAGE_H - 2], fill=1)
    s.d.rectangle([40, 1, 40, HEIGHT - 2], fill=1)       # ruler baseline
    for x in range(40, WIDTH, 16):                       # ticks every 16 columns
        s.d.rectangle([x, 60, x, 67], fill=1)
    s.T("PAGE", 46, 8, 8)
    s.T("0-F", 46, 20, 8)
    s.T("COL x16", 46, 72, 8)
    s.T("BORDER=EDGE", 46, 110, 6)
    return s.img


def _card_detail():
    """The ``ab`` subject: every type tier plus fine 1px texture, so a packing or
    offset disagreement between the two writers has somewhere to show itself."""
    s = Screen()
    s.box(0, 0, WIDTH, HEIGHT)
    s.T("SH1107", 6, 5, 16)
    s.T("DIFF vs LUMA", 6, 24, 8)
    s.hline(0, 36, WIDTH)
    for y in range(40, 60, 2):                           # 1px horizontal comb
        s.d.rectangle([4, y, 123, y], fill=1)
    for x in range(4, 124, 2):                           # 1px vertical comb
        s.d.rectangle([x, 62, x, 80], fill=1)
    s.d.line([4, 84, 123, 108], fill=1)                  # a diagonal crosses pages
    s.T("agree = still", 6, 112, 8)
    return s.img


# ---- stages ----------------------------------------------------------------
def stage_orient(args):
    """Cycle the same card through rotate 0..3. Read the R-number that is upright."""
    print("orient: which R-number reads upright + wedge in the top-left?")
    for r in (0, 1, 2, 3):
        dev = _device(rotate=r, address=args.address)
        print("  showing R%d ..." % r)
        dev.display(_card_orient(r))                     # luma's own path: no diff here
        time.sleep(args.hold)
    print("  -> that R value is design.md #2's 'confirm on metal'; put it in run_device.")


def stage_grid(args):
    dev = _device(rotate=args.rotate, address=args.address)
    sink = _sink(dev)
    sink.show(_card_grid())
    print("grid: bands horizontal + numbered 0..F down the left = page axis OK.")
    print("      border visible on all 4 edges = col_offset 0 OK.")
    time.sleep(args.hold)


def stage_ab(args):
    """The reference check. luma's ``display()`` is known-good and pushes the whole
    frame; ours pushes spans. Same image through both => the panel must not change.
    """
    dev = _device(rotate=args.rotate, address=args.address)
    sink = _sink(dev)
    img = _card_detail()
    print("ab: alternating luma display() and DiffSink on ONE image.")
    print("    a still panel = our writer agrees. ANY flicker = LumaWriter bug.")
    for i in range(args.rounds):
        t = time.monotonic()
        dev.display(img)                                 # reference: full frame
        ref_ms = (time.monotonic() - t) * 1000
        time.sleep(args.hold)
        sink.prev = sink.pages = None                    # force ours to push it all too
        t = time.monotonic()
        sent = sink.show(img)
        ours_ms = (time.monotonic() - t) * 1000
        print("    round %d: luma %6.1f ms (2048 B)   ours %6.1f ms (%d B)"
              % (i + 1, ref_ms, ours_ms, sent))
        time.sleep(args.hold)


def stage_diff(args):
    """The diff path's whole point, isolated: a block moving inside one page band.
    Only that band may go out -- and an unchanged tick must send nothing at all."""
    dev = _device(rotate=args.rotate, address=args.address)
    sink = _sink(dev)

    def frame(n):
        s = Screen()
        s.box(0, 0, WIDTH, HEIGHT)
        s.T("DIFF BAND", 6, 5, 16)
        s.hline(0, 26, WIDTH)
        s.box(20, 40 + (n % 24), 88, 16, fill=True)
        s.T("one band moves", 6, 110, 8)
        return s.img

    sink.show(frame(0))                                  # first frame is a full push
    sink.stats.update(frames=0, skipped=0, bytes=0, spans=0)
    ticks = int(args.hold * 4 / TICK)
    t0 = time.monotonic()
    for n in range(ticks):
        sink.show(frame(n))
        time.sleep(TICK)
    for _ in range(10):                                  # now hold still: must be silent
        sink.show(frame(ticks - 1))
        time.sleep(TICK)
    print("diff: moving block, then 10 still ticks")
    _report("moving band", sink, ticks + 10, time.monotonic() - t0)


def stage_app(args):
    """The real UI, animating through the real driver, left up when we exit."""
    from ganglion.app import AppController, render

    dev = _device(rotate=args.rotate, address=args.address)
    sink = _sink(dev)
    c = AppController()
    # The demo board's names ("Comp", "Drive") all fit their box, so nothing
    # marquees and the panel would sit at a flattering 0 B/tick -- a test that
    # proves only that a still screen is still. oled_bench hits the same trap and
    # solves it the same way: force the median *overflowing* name from the real
    # catalog, which is what the focused node looks like most of the time in use.
    # Same string as the bench, so the two tools' numbers line up.
    c.st.board[c.st.node]["name"] = "GxColorSoundTonebender"
    sink.show(render(c.st))                              # full push once, then diffs
    sink.stats.update(frames=0, skipped=0, bytes=0, spans=0)
    t0 = time.monotonic()
    ticks = 0
    while time.monotonic() - t0 < args.hold * 4:
        c.st.t = time.monotonic() - t0                   # display clock: drives the marquee
        sink.show(render(c.st))
        ticks += 1
        time.sleep(TICK)
    print("app: live chain screen, marquee running through DiffSink")
    _report("app idle (marquee)", sink, ticks, time.monotonic() - t0)
    print("  frame left on the panel (dev.persist = True)")


# ---- power / flicker -------------------------------------------------------
# The panel has no telemetry and there is no shunt on the module, so its current
# is not directly observable. But it hangs off the Pi 5's 3V3 rail, and that rail
# has a PMIC ADC -- so the panel's draw is the *delta* on 3V3_SYS between panel
# states. Single samples are useless (stdev ~20mA, it powers half the board); the
# median of ~60 is stable to ~2mA, which is plenty for a part that swings 70.
#
# Every state is measured against a baseline taken with the panel blanked
# moments earlier, so slow rail drift cancels rather than landing in the answer.
RAIL = "3V3_SYS_A"
_SAMPLES = 60


def _rail_a(n=_SAMPLES):
    out = []
    for _ in range(n):
        s = subprocess.run(["vcgencmd", "pmic_read_adc", RAIL],
                           capture_output=True, text=True).stdout
        out.append(float(s.split("=")[1].rstrip("A\n")))
        time.sleep(0.02)
    return statistics.median(out)


def _draw_ma(dev, img, contrast=0x7F):
    """Milliamps this image costs, panel-off subtracted."""
    dev.hide()
    time.sleep(0.35)
    base = _rail_a()
    dev.contrast(contrast)
    dev.display(img)
    dev.show()
    time.sleep(0.35)
    return 1000 * (_rail_a() - base)


def _fill(frac):
    img = Image.new("1", (WIDTH, HEIGHT), 0)
    rows = int(round(HEIGHT * frac))
    if rows:
        img.paste(Image.new("1", (WIDTH, rows), 1), (0, 0))
    return img


def stage_power(args):
    """Current draw per lit area, and the flicker ceiling that comes with it.

    Read the numbers with your eyes on the glass, because they are not what they
    look like: current does **not** track lit pixels here. A quarter-lit screen
    measured 85mA while a fully lit one measured 77mA -- reproducibly, spread
    ~2mA. That inversion is the panel browning out. Past some lit area the
    driver cannot hold every pixel up, emission goes intermittent (visible as
    flicker), and *average* current falls even as demand rises. So a lower
    reading above the knee means it is failing, not saving.

    Contrast is the lever: it sets drive current, so it moves the knee. The sweep
    ends on all-white at each contrast so you can see where flicker stops --
    that value is the ceiling the SYSTEM > Brightness item should respect.
    """
    from ganglion.app import AppController, render

    dev = _device(rotate=args.rotate, address=args.address)
    c = AppController()
    c.st.board[c.st.node]["name"] = "GxColorSoundTonebender"
    app_frame = render(c.st)
    ink = sum(app_frame.convert("L").point(lambda v: 1 if v else 0).getdata())

    print("power: draw on %s, panel-off subtracted, median of %d samples"
          % (RAIL, _SAMPLES))
    print("  the real UI lights %d/%d px (%.1f%%)" % (ink, WIDTH * HEIGHT,
                                                      100.0 * ink / (WIDTH * HEIGHT)))
    print("  -- lit area @ contrast 0x7F " + "-" * 30)
    for label, img in (("blank (panel on)", _fill(0)), ("the real UI", app_frame),
                       ("25% lit", _fill(0.25)), ("50% lit", _fill(0.50)),
                       ("100% lit", _fill(1.0))):
        print("  %-22s %+6.1f mA" % (label, _draw_ma(dev, img)))
    print("  -- all-white vs contrast (watch for flicker) " + "-" * 14)
    for ct in (0x01, 0x40, 0x7F, 0xFF):
        ma = _draw_ma(dev, _fill(1.0), contrast=ct)
        print("  contrast 0x%02X           %+6.1f mA   <- flickering?" % (ct, ma))
    dev.contrast(0x7F)


def stage_refresh(args):
    """Sweep the panel's frame rate against a large white field. Watch it flicker.

    luma's sh1107 init sends ``0xD5 0x80`` and never revisits it. Per the SH1107
    datasheet that is oscillator=0x8, divide=1, which at 128-mux lands around
    **59-60 Hz** -- and a 60Hz full-white field is exactly the CRT flicker
    everyone remembers, because two psychophysical laws stack against us here:

      * **Granit-Harper**: flicker fusion threshold rises with the *log of the
        lit area*. A small patch at 60Hz fuses; a full screen at 60Hz does not.
      * **Ferry-Porter**: it also rises with luminance -- but only logarithmically,
        and our whole contrast range is a mere 1.8x of current, so dimming cannot
        buy back enough. Which is precisely why flicker persisted at *every*
        contrast, and why contrast was never the lever.

    So this sweeps the oscillator 0x0..0xF at divide=1. If the flicker dies as
    the frame rate climbs, the cause was refresh, not power, and the fix is one
    command in ``run_device`` -- no UI concessions, no supply work.
    """
    dev = _device(rotate=args.rotate, address=args.address)
    dev.contrast(0x7F)
    dev.display(_fill(1.0))                              # worst case: the whole field
    dev.show()
    print("refresh: all-white, sweeping the display clock (0xD5).")
    print("  luma's default is osc=0x8 (~60Hz). Say where the flicker stops.")
    for osc in (0x0, 0x4, 0x8, 0xC, 0xF):
        dev.command(0xD5, (osc << 4) | 0x0)              # bits7:4 osc, bits3:0 divide
        note = "  <- luma default (~60Hz)" if osc == 0x8 else ""
        print("  0xD5 = 0x%02X   osc=0x%X, divide=1%s" % ((osc << 4), osc, note))
        time.sleep(args.hold * 2)
    dev.command(0xD5, 0x80)                              # leave it as luma had it
    print("  (restored to luma's 0x80)")


def stage_scanline(args):
    """The NES-sprite-limit test: identical ink, different per-scanline load.

    A passive matrix lights one scan line at a time, and every lit segment on
    that line draws from the charge pump *simultaneously*. So the ceiling is
    plausibly "lit pixels **per line**" -- exactly the 8-sprites-per-scanline
    limit that made NES sprites flicker. That model explains what nothing else
    did: raising the frame rate changed nothing (per-line load is untouched),
    contrast barely moved it (1.8x), and current stopped tracking total ink.

    All three frames below light **exactly 4096 pixels**. Only the geometry
    differs:

        hbar  128 lit per row    ×  32 rows   (32 per column)
        vbar   32 lit per row    × 128 rows   (128 per column)
        diag   32 lit per row    × 128 rows   (32 per column)  <- maximally spread

    Read it like a truth table. hbar flickers alone => the scan axis is our rows,
    and long *horizontal* runs are the enemy. vbar alone => it is our columns.
    Both => the limit is per line on either axis. **diag flickering is the one
    result that kills the model** -- same ink, no line loaded, nothing to blame.

    And if diag stays clean while the bars flicker, dithering a large fill buys
    back the area for free, which is a far cheaper UI rule than "no big blocks".
    """
    dev = _device(rotate=args.rotate, address=args.address)
    dev.contrast(0x7F)

    def build(fn):
        img = Image.new("1", (WIDTH, HEIGHT), 0)
        px = img.load()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if fn(x, y):
                    px[x, y] = 1
        return img

    frames = [
        ("hbar  (128/row,  32/col)", build(lambda x, y: y < 32)),
        ("vbar  ( 32/row, 128/col)", build(lambda x, y: x < 32)),
        ("diag  ( 32/row,  32/col)", build(lambda x, y: (x + y) % 4 == 0)),
    ]
    for label, img in frames:                            # each must be 4096 lit
        n = sum(img.convert("L").point(lambda v: 1 if v else 0).getdata())
        assert n == 4096, "%s lit %d px, not 4096 -- not a fair comparison" % (label, n)

    print("scanline: three frames, ALL exactly 4096 lit px. Which flicker?")
    for label, img in frames:
        ma = _draw_ma(dev, img)
        print("  %-26s %+6.1f mA   <- flickering?" % (label, ma))
        time.sleep(args.hold * 2)
    print("  hbar only  -> scan axis = rows; long horizontal runs are the limit")
    print("  vbar only  -> scan axis = columns")
    print("  diag clean -> dithering large fills buys the area back")


STAGES = {"orient": stage_orient, "grid": stage_grid, "ab": stage_ab,
          "diff": stage_diff, "app": stage_app, "power": stage_power,
          "refresh": stage_refresh, "scanline": stage_scanline}
ORDER = ["grid", "ab", "diff", "app"]      # orient re-inits 4x, power/refresh slow: opt-in


def main():
    ap = argparse.ArgumentParser(description="SH1107 on-metal bring-up screens")
    ap.add_argument("--stage", choices=sorted(STAGES), help="one stage (default: all)")
    ap.add_argument("--rotate", type=int, default=ROTATE, choices=[0, 1, 2, 3])
    ap.add_argument("--address", type=lambda s: int(s, 0), default=ADDRESS)
    ap.add_argument("--hold", type=float, default=1.5, help="seconds per screen")
    ap.add_argument("--rounds", type=int, default=3, help="ab: A/B alternations")
    args = ap.parse_args()

    names = [args.stage] if args.stage else ORDER
    print("SH1107 @ 0x%02X  rotate=%d  bus=%s" % (args.address, args.rotate, BUS))
    for n in names:
        STAGES[n](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
