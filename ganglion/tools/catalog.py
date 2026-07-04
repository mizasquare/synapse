#!/usr/bin/env python3
"""GECO plugin-catalog curation tool (standalone CLI).

Fetches the installed plugin list (live mod-ui, or a fixture), diffs it against
the curated catalog, and reflects only the delta — **existing category
assignments are preserved**, so after installing more plugins you re-run and only
the newcomers need attention.

Categories are GECO's custom, guitar-signal-chain taxonomy (NOT LV2's), 8 shown
+ Unused(hidden):
    Dynamics · Filter · Pedal · Amp · Cab · Mod(+pitch) · Spatial · Utils · Unused

Source of truth: ganglion/geco_catalog.json  (per-plugin bucket, keyed by URI).
Auto-suggestion for a *new* plugin maps its LV2 category into a GECO bucket
(``geco_bucket``); curation confirms/overrides it. A plugin in "Unused" is hidden
from GECO.

Commands:
    sync      fetch source, apply add/remove delta, keep existing curation
    curate    interactively bucket the plugins that still need it (new by default)
    list      show the catalog grouped by bucket
    status    counts: total / by bucket / uncurated / removed
    export    write the human doc (--md) and/or the app whitelist (--app)

Examples:
    python3 ganglion/tools/catalog.py sync                 # from live localhost
    python3 ganglion/tools/catalog.py sync --fixture fixtures/installed-effects.json
    python3 ganglion/tools/catalog.py curate               # bucket the new ones
    python3 ganglion/tools/catalog.py export --app ganglion/geco_whitelist.json
"""

import argparse
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG = os.path.join(ROOT, "ganglion", "geco_catalog.json")

# GECO buckets — display order + node abbreviation. "Unused" is hidden.
BUCKETS = [("Dynamics", "DYN"), ("Filter", "FLT"), ("Pedal", "PDL"), ("Amp", "AMP"),
           ("Cab", "CAB"), ("Mod", "MOD"), ("Spatial", "SPC"), ("Utils", "UTL"),
           ("Unused", "--")]
ORDER = [k for k, _ in BUCKETS]
ABBR = dict(BUCKETS)
HIDDEN = "Unused"


def geco_bucket(name, lv2):
    """Auto-suggest a GECO bucket from a plugin's LV2 category + name."""
    s = set(lv2 or [])
    low = (name or "").lower()
    ir = ("ir convolver", "convolution loader", "ir loader", "cabsim", "cabinet")
    if "Distortion" in s:
        return "Pedal"
    if s & {"Compressor", "Gate", "Expander", "Dynamics"}:
        return "Dynamics"
    if s & {"Filter", "Equaliser"}:
        return "Filter"
    if "Simulator" in s:
        return "Cab" if any(k in low for k in ("cab", "ir ", "ir_", "cabinet", "convol", "loader")) else "Amp"
    if s & {"Modulator", "Phaser", "Flanger", "Chorus", "Tremolo", "Vibrato",
            "Spectral", "Pitch Shifter"}:   # pitch folded into Mod
        return "Mod"
    if s & {"Delay", "Reverb"}:
        return "Cab" if any(k in low for k in ir) else "Spatial"   # IR convolvers are Cab
    if "Spatial" in s:                       # LV2 Spatial = stereo widener
        return "Utils"
    if s & {"Generator", "Instrument", "MIDI", "ControlVoltage"}:
        return "Unused"
    if s & {"Utility", "Analyser"}:
        return "Utils"
    return "Unused"


# ------------------------------------------------------------------ storage
def load_catalog():
    if os.path.exists(CATALOG):
        with open(CATALOG, encoding="utf-8") as f:
            return json.load(f)
    return {"buckets": [{"key": k, "abbr": a} for k, a in BUCKETS], "plugins": {}}


def save_catalog(cat):
    os.makedirs(os.path.dirname(CATALOG), exist_ok=True)
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


# ------------------------------------------------------------------ sources
def _shape(p):
    return {"uri": p["uri"], "name": (p.get("name") or p["uri"]),
            "brand": (p.get("brand") or "").strip(), "lv2": p.get("category") or []}


def fetch_live(base):
    url = base.rstrip("/") + "/effect/list"
    with urllib.request.urlopen(url, timeout=15) as r:
        return [_shape(p) for p in json.load(r)]


def fetch_fixture(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return [_shape(p) for p in (d["plugins"] if isinstance(d, dict) else d)]


def source_plugins(args):
    if args.fixture:
        return fetch_fixture(args.fixture)
    return fetch_live(args.url)


# ------------------------------------------------------------------ commands
def cmd_sync(args):
    cat = load_catalog()
    pl = cat["plugins"]
    try:
        src = source_plugins(args)
    except Exception as e:
        sys.exit("source fetch failed (%s). live host down? try --fixture <path>." % e)
    src_by = {p["uri"]: p for p in src}

    added, removed = [], []
    for uri, p in src_by.items():
        if uri in pl:
            e = pl[uri]
            e.update(name=p["name"], brand=p["brand"], lv2=p["lv2"], present=True)
            if not e.get("curated"):
                e["bucket"] = geco_bucket(p["name"], p["lv2"])   # refresh suggestion
        else:
            pl[uri] = {"name": p["name"], "brand": p["brand"], "lv2": p["lv2"],
                       "bucket": geco_bucket(p["name"], p["lv2"]),
                       "curated": False, "present": True}
            added.append(uri)
    for uri, e in pl.items():
        if uri not in src_by:
            if e.get("present", True):
                removed.append(uri)
            e["present"] = False
    if args.prune:
        for uri in [u for u, e in pl.items() if not e.get("present")]:
            del pl[uri]

    save_catalog(cat)
    present = [e for e in pl.values() if e.get("present")]
    uncur = [e for e in present if not e.get("curated")]
    src_label = args.fixture or (args.url + "/effect/list")
    print("sync from %s" % src_label)
    print("  +%d new   -%d removed   =%d present total" % (len(added), len(removed), len(present)))
    if added:
        print("  NEW (auto-suggested bucket, run `curate`):")
        for uri in added:
            e = pl[uri]
            print("    %-34s -> %-8s [%s]" % (e["name"][:34], e["bucket"], "/".join(e["lv2"]) or "-"))
    if removed:
        print("  REMOVED (kept, marked absent; --prune to delete):")
        for uri in removed:
            print("    %s" % pl[uri]["name"])
    if uncur:
        print("  -> %d plugin(s) need curation: run `catalog.py curate`" % len(uncur))


def _targets(pl, all_):
    return [(u, e) for u, e in pl.items()
            if e.get("present") and (all_ or not e.get("curated"))]


def cmd_curate(args):
    cat = load_catalog()
    pl = cat["plugins"]
    targets = _targets(pl, args.all)
    if not targets:
        print("nothing to curate (all present plugins are curated). --all to review everything.")
        return
    targets.sort(key=lambda t: (t[1]["name"].lower()))
    menu = "  ".join("%d=%s" % (i + 1, k) for i, k in enumerate(ORDER))
    print("%d plugin(s) to curate.  buckets: %s" % (len(targets), menu))
    print("keys: [Enter]=accept suggested  1-%d=set bucket  s=skip  q=save&quit\n" % len(ORDER))
    changed = False
    try:
        for i, (uri, e) in enumerate(targets):
            sug = e["bucket"]
            print("[%d/%d] %s  %s" % (i + 1, len(targets), e["name"],
                                      ("· " + e["brand"]) if e["brand"] else ""))
            print("       LV2:%s   suggested -> %s" % ("/".join(e["lv2"]) or "-", sug))
            while True:
                raw = input("       > ").strip()
                if raw == "":
                    e["curated"] = True
                    changed = True
                    break
                if raw in ("s", "S"):
                    break
                if raw in ("q", "Q"):
                    if changed:
                        save_catalog(cat)
                    print("saved." if changed else "no changes.")
                    return
                if raw.isdigit() and 1 <= int(raw) <= len(ORDER):
                    e["bucket"] = ORDER[int(raw) - 1]
                    e["curated"] = True
                    changed = True
                    print("       -> %s" % e["bucket"])
                    break
                print("       ? enter a number 1-%d, Enter, s, or q" % len(ORDER))
            print()
    except (EOFError, KeyboardInterrupt):
        print()
    if changed:
        save_catalog(cat)
    print("done. curated %d." % sum(1 for _, e in targets if e.get("curated")))


def _group(pl):
    g = {k: [] for k in ORDER}
    extra = {}
    for e in pl.values():
        if not e.get("present"):
            continue
        b = e["bucket"]
        (g if b in g else extra).setdefault(b, []).append(e)
    for b in extra:
        g[b] = extra[b]
    return g


def cmd_list(args):
    cat = load_catalog()
    g = _group(cat["plugins"])
    keys = ORDER + [k for k in g if k not in ORDER]
    for b in keys:
        items = g.get(b, [])
        if not items:
            continue
        print("## %s — %s (%d)" % (ABBR.get(b, "?"), b, len(items)))
        for e in sorted(items, key=lambda x: x["name"].lower()):
            mark = " " if e.get("curated") else "~"
            print("  %s %-34s %s" % (mark, e["name"][:34], ("· " + e["brand"]) if e["brand"] else ""))
    absent = [e for e in cat["plugins"].values() if not e.get("present")]
    if absent:
        print("\n(absent, kept: %s)" % ", ".join(e["name"] for e in absent))


def cmd_status(args):
    cat = load_catalog()
    pl = cat["plugins"]
    present = [e for e in pl.values() if e.get("present")]
    g = _group(pl)
    print("catalog: %s" % CATALOG)
    print("present: %d   uncurated(new): %d   absent(kept): %d"
          % (len(present), sum(1 for e in present if not e.get("curated")),
             sum(1 for e in pl.values() if not e.get("present"))))
    for b in ORDER:
        n = len(g.get(b, []))
        if n:
            tag = "  (hidden)" if b == HIDDEN else ""
            print("  %-9s %2d%s" % (b, n, tag))


def cmd_export(args):
    cat = load_catalog()
    pl = cat["plugins"]
    if args.md:
        g = _group(pl)
        lines = ["# GECO 플러그인 카탈로그 (자동 생성 — geco_catalog.json에서)", "",
                 "`~`=미큐레이션(신규). 편집은 `catalog.py curate`로.", ""]
        for b in ORDER:
            items = g.get(b, [])
            if not items:
                continue
            lines.append("## %s — %s (%d)%s" % (ABBR.get(b, "?"), b, len(items),
                                                "  [hidden]" if b == HIDDEN else ""))
            for e in sorted(items, key=lambda x: x["name"].lower()):
                m = " " if e.get("curated") else "~"
                lines.append("- %s **%s**%s · LV2:%s" % (m, e["name"],
                             (" · " + e["brand"]) if e["brand"] else "", "/".join(e["lv2"]) or "-"))
            lines.append("")
        with open(args.md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("wrote %s" % args.md)
    if args.app:
        out = {"buckets": []}
        g = _group(pl)
        for b in ORDER:
            if b == HIDDEN:
                continue
            items = [e for e in g.get(b, []) if e.get("curated")]
            if not items:
                continue
            out["buckets"].append({"key": b, "abbr": ABBR[b],
                "plugins": [{"name": e["name"], "uri": u, "brand": e["brand"]}
                            for u, e in cat["plugins"].items()
                            if e.get("present") and e.get("curated")
                            and e["bucket"] == b]})
        with open(args.app, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write("\n")
        skipped = sum(1 for e in pl.values() if e.get("present") and not e.get("curated"))
        print("wrote %s (%d buckets; %d uncurated skipped)"
              % (args.app, len(out["buckets"]), skipped))
    if not args.md and not args.app:
        sys.exit("nothing to export: pass --md FILE and/or --app FILE")


def main():
    ap = argparse.ArgumentParser(description="GECO plugin-catalog curation tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def src_args(p):
        p.add_argument("--url", default="http://localhost", help="mod-ui base URL (live source)")
        p.add_argument("--fixture", help="use a JSON dump instead of the live host")

    s = sub.add_parser("sync", help="fetch source, apply add/remove delta")
    src_args(s)
    s.add_argument("--prune", action="store_true", help="delete absent plugins instead of keeping them")
    s.set_defaults(fn=cmd_sync)

    c = sub.add_parser("curate", help="interactively bucket plugins")
    c.add_argument("--all", action="store_true", help="review every plugin, not just uncurated")
    c.set_defaults(fn=cmd_curate)

    sub.add_parser("list", help="show catalog grouped by bucket").set_defaults(fn=cmd_list)
    sub.add_parser("status", help="counts").set_defaults(fn=cmd_status)

    e = sub.add_parser("export", help="write human doc and/or app whitelist")
    e.add_argument("--md", help="write the human-readable markdown here")
    e.add_argument("--app", help="write the app whitelist JSON here")
    e.set_defaults(fn=cmd_export)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
