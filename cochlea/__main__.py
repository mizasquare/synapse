"""Console tuner runner -- watch the readings scroll (T2 verification).

Off-device (no guitar, no JACK) -- a tone sweeping +/- 60 cents around A2:
    /home/miza/synapse-venv/bin/python -m cochlea sweep:110

On the Pi with a real guitar (reads system:capture_1 via JACK):
    /home/miza/synapse-venv/bin/python -m cochlea jack

Options: --guitar (snap to nearest open string), --a4 442, --mains 60.
Ctrl-C to quit.
"""
import argparse
import sys
import time

from .audio_source import build_source
from .tuner_engine import TunerEngine


def _bar(cents, width=21):
    """Centre-anchored deviation bar, e.g. '....|===O    |....'."""
    half = width // 2
    pos = int(round(cents / 50.0 * half))         # +/-50 cents spans the bar
    pos = max(-half, min(half, pos))
    cells = ["-"] * width
    cells[half] = "|"
    cells[half + pos] = "O"
    return "".join(cells)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cochlea")
    ap.add_argument("source", help="'jack', 'tone:<hz>', or 'sweep[:<hz>]'")
    ap.add_argument("--guitar", action="store_true", help="snap to nearest open string")
    ap.add_argument("--bass", action="store_true", help="bass string set")
    ap.add_argument("--a4", type=float, default=440.0)
    ap.add_argument("--mains", type=float, default=None, help="force 50 or 60 (else auto)")
    ap.add_argument("--fmin", type=float, default=65.0)
    args = ap.parse_args(argv)

    string_set = "guitar" if args.guitar else ("bass" if args.bass else None)
    src = build_source(args.source)
    eng = TunerEngine(src, freq_min=args.fmin, mains=args.mains, a4_hz=args.a4,
                      string_set=string_set)
    eng.start()
    print("cochlea tuner on %r (a4=%.1f, mains=%s). Ctrl-C to quit.\n"
          % (args.source, args.a4, args.mains or "auto"))
    try:
        while True:
            r = eng.get_reading()
            if r is None:
                sys.stdout.write("\r%-64s" % "  ...listening...")
            else:
                tag = (" [%s]" % r.string) if r.string else ""
                sys.stdout.write("\r  %-4s %s %+6.1f¢  (%.2f Hz, %s conf %.2f)%-6s"
                                 % (r.note, _bar(r.cents), r.cents, r.freq_hz,
                                    "OK " if abs(r.cents) < 3 else "   ",
                                    r.confidence, tag))
            sys.stdout.flush()
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        eng.stop()
        print("\nbye")


if __name__ == "__main__":
    main()
