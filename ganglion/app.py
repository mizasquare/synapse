"""Ganglion app: the 2a state machine ported from the design mockup.

Consumes the shared input events (``Rotate``/``Press``/``Combo`` from
``ganglion.input`` — keyboard now, seesaw later) and renders 128x128 frames via
``ganglion.render``. This is the live controller with a real knob model; the
mockup's executable spec (GECO OLED 2a) is the reference.

Ported so far (the navigation spine + picker):
  depth 0 (chain nav · knob focus/lock/adjust · ENC0 slot menu · ENC0-hold up) ·
  depth -1 (glance: board/snapshot scroll) · slot menu (bypass/remove/back) ·
  picker (place/replace: split screen — chain on top, category|plugin strips
  below; ENC1 turns/selects, ENC0-hold backs — from the curated
  geco_whitelist.json) · SYSTEM (ENC0 scroll-left-past-start) · TUNER (ENC1 hold) ·
  COMBO (save).

Stubbed with a toast + [DECISION] marker (see docs/decisions.md): move,
board/snapshot manage (rename/save/delete), confirm overlay. The picker's placed
nodes use per-bucket placeholder knobs — wiring to synapse's real
model/modepctrl/plugincatalog params is still pending.

Run (needs a TTY):  python3 ganglion/app.py
Scripted check:      python3 ganglion/app.py --walk
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field

from ganglion import WIDTH, HEIGHT
from ganglion.render import Screen, fs
from ganglion.input import Rotate, Press, Combo

BG = 0

# ---- knob + board model (port of the mockup's K/fmt/norm/makeBoard) ----
BUCKET = {"Drive": "DRV", "Comp": "CMP", "Amp·Cab": "AMP", "Delay": "DLY",
          "Reverb": "RVB", "EQ": "EQ", "Mod": "MOD", "Filter": "FLT"}
# ENC0 LED per effect category (design leds()); ENC1/state colours below.
# Old sample-board bucket names + the live GECO whitelist keys share this map.
BUCKETCOL = {"Drive": "amber", "Comp": "green", "Amp·Cab": "amber",
             "Delay": "purple", "Reverb": "blue", "EQ": "blue", "Mod": "purple",
             "Filter": "blue", "Utility": "grey",
             "Dynamics": "green", "Pedal": "amber", "Amp": "amber", "Cab": "amber",
             "Spatial": "blue", "Utils": "grey"}


def K(n, v, mn, mx, u="", k="dial", scale=None):
    return {"n": n, "v": v, "mn": mn, "mx": mx, "u": u, "k": k, "scale": scale}


def norm(kb):
    return max(0, min(1, (kb["v"] - kb["mn"]) / (kb["mx"] - kb["mn"]))) if kb["mx"] > kb["mn"] else 0


def fmt(kb):
    if kb["k"] == "toggle":
        return "ON" if kb["v"] >= .5 else "OFF"
    if kb["k"] in ("enum", "file"):
        i = round(kb["v"] - kb["mn"])
        return kb["scale"][i] if kb["scale"] and 0 <= i < len(kb["scale"]) else str(round(kb["v"]))
    av = abs(kb["v"])
    s = str(round(kb["v"])) if av >= 100 else ("%.1f" % kb["v"]) if av >= 10 else ("%.2f" % kb["v"])
    return s + ((" " + kb["u"]) if kb["u"] else "")


def _node(name, abbr, bucket, bypass, knobs):
    return {"name": name, "abbr": abbr, "bucket": bucket, "bypass": bypass,
            "empty": False, "knobs": knobs}


def make_board():
    return [
        _node("Comp", "CMP", "Comp", False, [K("Thresh", -24, -60, 0, "dB"), K("Ratio", 4, 1, 20, ":1"),
                                             K("Attack", 12, 1, 100, "ms"), K("Makeup", 6, 0, 24, "dB")]),
        _node("Drive", "DRV", "Drive", False, [K("Gain", .62, 0, 1), K("Tone", .5, 0, 1),
                                               K("Level", .72, 0, 1), K("Bass", .4, 0, 1)]),
        _node("NAM", "AMP", "Amp·Cab", False, [K("Input", -6, -20, 20, "dB"), K("Output", -3, -20, 20, "dB"),
              K("Model", 0, 0, 3, "", "file", ["Fender Twin", "Vox AC30", "JCM800", "Mesa Recto"])]),
        _node("Cab", "CAB", "Amp·Cab", True, [K("Level", .8, 0, 1)]),
        _node("Delay", "DLY", "Delay", False, [K("Time", 380, 20, 1200, "ms"), K("Fdbk", 42, 0, 100, "%"),
                                               K("Mix", 28, 0, 100, "%")]),
        _node("Reverb", "RVB", "Reverb", False, [K("Decay", 2.4, .1, 12, "s"), K("Mix", 22, 0, 100, "%"),
                                                 K("Size", .6, 0, 1)]),
    ]


def _empty():
    return {"name": "", "abbr": "", "bucket": "", "bypass": False, "empty": True, "knobs": []}


# ---- plugin whitelist + node factory (port of the mockup's WL/makeNode) ----
# Curated by tools/catalog.py -> geco_whitelist.json (8 GECO buckets). The knob
# templates below are placeholders keyed by bucket until the synapse model/LV2
# param wiring lands (decisions.md A/B/E) — a placed node gets its bucket's dials.
_WL_FALLBACK = [
    {"key": "Pedal", "abbr": "PDL",
     "plugins": [{"display": "Overdrive", "name": "Overdrive", "uri": "", "brand": "", "alias": None}]},
    {"key": "Amp", "abbr": "AMP",
     "plugins": [{"display": "Amp Sim", "name": "Amp Sim", "uri": "", "brand": "", "alias": None}]},
]

_KNOB_TMPL = {
    "Dynamics": lambda: [K("Thresh", -24, -60, 0, "dB"), K("Ratio", 4, 1, 20, ":1"),
                         K("Attack", 12, 1, 100, "ms"), K("Makeup", 6, 0, 24, "dB")],
    "Filter": lambda: [K("Freq", 800, 20, 12000, "Hz"), K("Q", 1.0, .1, 10), K("Gain", 0, -24, 24, "dB")],
    "Pedal": lambda: [K("Gain", .6, 0, 1), K("Tone", .5, 0, 1), K("Level", .7, 0, 1)],
    "Amp": lambda: [K("Input", -6, -20, 20, "dB"), K("Gain", .5, 0, 1), K("Output", -3, -20, 20, "dB")],
    "Cab": lambda: [K("Level", .8, 0, 1)],
    "Mod": lambda: [K("Rate", 1.2, .1, 10, "Hz"), K("Depth", 50, 0, 100, "%"), K("Mix", 40, 0, 100, "%")],
    "Spatial": lambda: [K("Time", 380, 20, 1200, "ms"), K("Fdbk", 42, 0, 100, "%"), K("Mix", 28, 0, 100, "%")],
    "Utils": lambda: [K("Level", .7, 0, 1)],
}


def load_whitelist():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geco_whitelist.json")
    try:
        with open(path) as f:
            buckets = json.load(f)["buckets"]
        return buckets if buckets else _WL_FALLBACK
    except (OSError, ValueError, KeyError):
        return _WL_FALLBACK


def make_node(cat, plug):
    tmpl = _KNOB_TMPL.get(cat["key"], lambda: [K("Level", .7, 0, 1)])
    return {"name": plug["display"], "abbr": cat["abbr"], "bucket": cat["key"],
            "bypass": False, "empty": False, "knobs": tmpl()}


PBS = ["Lead Joyful", "Clean Verse", "Ambient Cathedral Wash"]
SNAPS = ["Default", "Lead Boost", "Ambient"]
SYSITEMS = ["Tuner", "Brightness", "MIDI Ch", "About", "< Back"]


@dataclass
class AppState:
    depth: int = 0            # 0 = chain, -1 = board/snapshot glance
    node: int = 1
    knob: int = 0
    locked: bool = False      # ENC1: dashed(move) -> solid(lock/adjust)
    menu_open: bool = False
    menu: int = 0
    sys: bool = False
    sys_idx: int = 0
    pick: str = ""            # ""=off, "cat"=category list, "fx"=plugin list
    pick_cat: int = 0
    pick_fx: int = 0
    tuner: bool = False
    tcents: int = 6
    tnote: str = "A"
    pb: int = 0
    snap: int = 1
    dirty: bool = False
    toast: str = ""
    board: list = field(default_factory=make_board)
    wl: list = field(default_factory=load_whitelist)


class AppController:
    """Ported 2a state machine. ``feed(event)`` mutates ``self.st``."""

    def __init__(self, state=None):
        self.st = state or AppState()

    # -- event entry ------------------------------------------------------
    def feed(self, ev):
        if isinstance(ev, Rotate):
            # [DECISION D] rotation accel magnitude is collapsed to sign here —
            # 1 detent = 1 step for nav AND value. Revisit: fast spin = coarse?
            self.rot(ev.enc, 1 if ev.delta > 0 else -1)
        elif isinstance(ev, Press):
            (self.hold if ev.kind == "long" else self.click)(ev.enc)
        elif isinstance(ev, Combo):
            if ev.kind == "press":
                self.combo()

    def _cur(self):
        return self.st.board[self.st.node]

    def menu_items(self):
        n = self._cur()
        if n["empty"]:
            return [("+", "Place FX", "place"), ("<", "Back", "back")]
        return [("O" if not n["bypass"] else "*", "Enable" if n["bypass"] else "Bypass", "bypass"),
                ("<>", "Move", "move"), ("~", "Replace", "replace"),
                ("X", "Remove", "remove"), ("<", "Back", "back")]

    # -- rotate -----------------------------------------------------------
    def rot(self, enc, d):
        st = self.st
        if st.tuner:
            return
        if st.pick:
            if enc == 1:                       # ENC1 turns the active strip
                if st.pick == "cat":
                    st.pick_cat = (st.pick_cat + d) % len(st.wl)
                else:
                    st.pick_fx = (st.pick_fx + d) % len(st.wl[st.pick_cat]["plugins"])
            return
        if st.sys:
            st.sys_idx = (st.sys_idx + d) % len(SYSITEMS)
            return
        if st.menu_open:
            st.menu = (st.menu + d) % len(self.menu_items())
            return
        if st.depth == -1:
            if enc == 0:
                st.pb = (st.pb + d) % len(PBS)
            else:
                st.snap = (st.snap + d) % len(SNAPS)
            return
        # depth 0
        if enc == 0:
            nn = st.node + d
            if nn < 0:                       # scroll left past chain start -> SYSTEM
                st.sys, st.sys_idx = True, 0
                return
            st.node = min(nn, len(st.board) - 1)
            st.knob = 0
        else:
            n = self._cur()
            if st.locked:
                self.adjust(d)
            elif not n["empty"]:
                st.knob = (st.knob + d) % len(n["knobs"])

    def adjust(self, d):
        n = self._cur()
        if n["empty"]:
            return
        kb = n["knobs"][self.st.knob]
        if kb["k"] == "toggle":
            kb["v"] = 0 if kb["v"] >= .5 else 1
        elif kb["k"] in ("enum", "file"):
            kb["v"] = max(kb["mn"], min(kb["mx"], round(kb["v"]) + d))
        else:
            step = (kb["mx"] - kb["mn"]) / 40.0
            kb["v"] = max(kb["mn"], min(kb["mx"], kb["v"] + step * d))
        self.st.dirty = True

    # -- click ------------------------------------------------------------
    def click(self, enc):
        st = self.st
        if st.tuner:
            st.tuner = False
            return
        if st.pick:
            if enc == 1:                       # ENC1 click = select / place
                if st.pick == "cat":
                    st.pick, st.pick_fx = "fx", 0
                else:
                    cat = st.wl[st.pick_cat]
                    plug = cat["plugins"][st.pick_fx]
                    st.board[st.node] = make_node(cat, plug)
                    st.pick, st.knob, st.dirty = "", 0, True
                    self._toast(plug["display"] + " placed")
            return                             # ENC0 click = no-op (hold = back)
        if st.sys:
            if enc == 0:
                self._sys_act()
            else:
                st.sys = False
            return
        if st.menu_open:
            if enc == 1:
                st.menu_open = False
            else:
                self._menu_act(self.menu_items()[st.menu][2])
            return
        if st.depth == -1:
            # [DECISION] board/snapshot manage submenu not ported yet
            self._toast("TODO: manage " + ("board" if enc == 0 else "snap"))
            return
        # depth 0
        if enc == 0:
            st.menu_open, st.menu = True, 0
        elif not self._cur()["empty"]:
            st.locked = not st.locked

    def _menu_act(self, act):
        st = self.st
        n = self._cur()
        if act == "back":
            st.menu_open = False
        elif act == "bypass":
            n["bypass"] = not n["bypass"]
            st.menu_open, st.dirty = False, True
        elif act == "remove":
            st.board[st.node] = _empty()
            st.menu_open, st.knob, st.dirty = False, 0, True
        elif act in ("place", "replace"):
            st.menu_open = False
            st.pick, st.pick_cat, st.pick_fx = "cat", 0, 0
        else:  # move -> [DECISION] move not ported yet
            st.menu_open = False
            self._toast("TODO: " + act)

    def _sys_act(self):
        it = SYSITEMS[self.st.sys_idx]
        if it == "Tuner":
            self.st.sys, self.st.tuner = False, True
        elif it == "< Back":
            self.st.sys = False
        else:
            self._toast("TODO: " + it)

    # -- hold (long press) ------------------------------------------------
    def hold(self, enc):
        st = self.st
        if st.tuner:
            st.tuner = False
            return
        if st.pick:                           # ENC0 hold = back (consistent); ENC1 hold = no-op
            if enc == 0:
                st.pick = "cat" if st.pick == "fx" else ""
            return
        if enc == 0:                          # ENC0 hold = zoom out one level
            if st.sys:
                st.sys = False
            elif st.menu_open:
                st.menu_open = False
            elif st.depth == 0:
                st.depth = -1
            elif st.depth == -1:
                st.depth = 0
        else:                                 # ENC1 hold = tuner
            st.tuner = True

    def combo(self):
        self.st.depth, self.st.dirty = -1, False
        self._toast("SNAPSHOT SAVED")

    def _toast(self, msg):
        self.st.toast = msg


# ========================= VIEW (state -> frame) =========================
def render(st):
    if st.tuner:
        return _tuner(st)
    if st.pick:
        return _pick(st)
    if st.sys:
        return _sys(st)
    if st.menu_open:
        return _menu(st)
    if st.depth == -1:
        return _glance(st)
    return _chain(st)


def _toast_over(s, st):
    if not st.toast:
        return
    s.box(6, 50, 116, 22, fill=True)
    s.T(st.toast, 64 - int(s.Tw(8, st.toast) / 2), 56, 8, fill=0)


def _chain(st):
    s = Screen()
    s.T("IN", 2, 1, 8)
    s.T("-14.2", 16, 1, 8)
    s.T("OUT", 54, 1, 8)
    s.T("-4.3", 74, 1, 8)
    s.T("%d/%d" % (st.node + 1, len(st.board)), 101, 1, 6)
    if st.dirty:
        s.d.ellipse([121, 2, 126, 7], fill=1)
    step, cw, ty, ch = 25, 23, 13, 24
    wy = ty + ch // 2
    cells = []
    for j in range(5):
        idx = st.node - 2 + j
        if idx < 0 or idx >= len(st.board):
            continue
        n = st.board[idx]
        x = 2 + j * step
        cells.append((idx, x, x + cw - 1))
        sel = idx == st.node
        if n["empty"]:
            s.dashed(x, ty, cw, ch, on=2, off=2)
            s.T("+", x + 8, ty + 8, 12, fill=1)
        elif sel:
            s.box(x, ty, cw, ch, fill=True)
            s.T(n["abbr"], x + 3, ty + 9, 12, fill=0)
        elif n["bypass"]:
            s.dashed(x, ty, cw, ch, on=1, off=2)
            s.T(n["abbr"], x + 3, ty + 9, 12)
        else:
            s.box(x, ty, cw, ch)
            s.T(n["abbr"], x + 3, ty + 9, 12)
    for a in range(len(cells) - 1):
        if cells[a + 1][1] - 1 >= cells[a][2] + 1:
            s.d.rectangle([cells[a][2] + 1, wy, cells[a + 1][1] - 1, wy], fill=1)
    if cells:
        if cells[0][0] > 0:
            s.d.rectangle([0, wy, cells[0][1] - 1, wy], fill=1)
        if cells[-1][0] < len(st.board) - 1:
            s.d.rectangle([cells[-1][2] + 1, wy, WIDTH - 1, wy], fill=1)
    s.hline(0, 40, 128)
    n = st.board[st.node]
    if n["empty"]:
        s.T("EMPTY SLOT %d" % (st.node + 1), 6, 66, 12)
        s.T("CLICK e0 -> add FX", 6, 84, 8)
        _toast_over(s, st)
        return s.img
    s.T(n["name"], 4, 43, 16)
    s.T("BYP" if n["bypass"] else n["abbr"], 100, 45, 8)
    kx, base, kh, cw2 = [5, 67], 62, 21, 56
    for i, kb in enumerate(n["knobs"][:6]):
        col, row = i % 2, i // 2
        if row >= 3:
            break
        x, yy = kx[col], base + row * kh
        if i == st.knob:
            if st.locked:
                s.box(x - 3, yy - 2, cw2, kh - 1)
            else:
                s.dashed(x - 3, yy - 2, cw2, kh - 1, on=2, off=2)
        s.T(kb["n"], x, yy, 8)
        s.T(fmt(kb), x, yy + 8, 8)
        if kb["k"] == "dial":
            s.gbar(x, yy + 17, cw2 - 8, 3, norm(kb))
    _toast_over(s, st)
    return s.img


def _glance(st):
    s = Screen()
    s.T("PEDALBOARD", 6, 5, 8, ls=1)
    name = PBS[st.pb]
    s.T(name if s.Tw(24, name) <= 108 else name, 5, 14, 24)  # marquee later
    s.dots(len(PBS), st.pb, 6, 47)
    s.hline(0, 56, 128)
    s.T("SNAPSHOT", 6, 62, 8, ls=1)
    s.T(SNAPS[st.snap], 5, 71, 24)
    s.dots(len(SNAPS), st.snap, 6, 99)
    s.T("e0 pb.CLK manage  e1 snap", 5, 118, 6)
    s.T("-1", 116, 5, 8)
    if st.dirty:
        s.d.ellipse([120, 2, 125, 7], fill=1)
    _toast_over(s, st)
    return s.img


def _menu(st):
    s = Screen()
    n = st.board[st.node]
    s.box(0, 0, 40, 128)
    if n["empty"]:
        s.T("+", 13, 44, 24)
        s.T("EMPTY", 4, 74, 8)
        s.T("SLOT %d" % (st.node + 1), 3, 86, 6)
    else:
        s.T(n["abbr"], 2, 40, 16)
        s.T(n["name"], 3, 62, 8)
        s.T("SLOT %d/6" % (st.node + 1), 3, 76, 6)
        s.T("BYP" if n["bypass"] else "ON", 3, 88, 6)
    s.T("ACTION", 46, 5, 8, ls=1)
    items = AppController(st).menu_items()
    y0, rh = 17, 17
    for i, (ic, label, _) in enumerate(items):
        y = y0 + i * rh
        if i == st.menu:
            s.box(44, y - 1, 84, rh - 2, fill=True)
            s.T(ic + " " + label, 48, y + 1, 8, fill=0)
        else:
            s.T(ic + " " + label, 48, y + 1, 8)
    return s.img


def _fit(s, txt, size, maxw):
    """Truncate txt so it fits maxw px at the given tier."""
    if s.Tw(size, txt) <= maxw:
        return txt
    while txt and s.Tw(size, txt) > maxw:
        txt = txt[:-1]
    return txt


def _striplist(s, items, sel, x, w, y0, active, size=8, vis=5, rh=14):
    """Windowed list inside [x, x+w). Focus ring = filled; locked = hollow."""
    n = len(items)
    start = 0 if n <= vis else max(0, min(sel - vis // 2, n - vis))
    for r in range(min(vis, n)):
        i = start + r
        y = y0 + r * rh
        lbl = _fit(s, items[i], size, w - 7)
        if i == sel and active:
            s.box(x, y - 1, w, rh - 2, fill=True)
            s.T(lbl, x + 3, y + 1, size, fill=0)
        elif i == sel:                          # inactive strip: hollow marker
            s.box(x, y - 1, w, rh - 2)
            s.T(lbl, x + 3, y + 1, size)
        else:
            s.T(lbl, x + 3, y + 1, size)
    if start > 0:
        s.T("^", x + w - 8, y0 - 1, 6)
    if start + vis < n:
        s.T("v", x + w - 8, y0 + (vis - 1) * rh, 6)


def _pick_chain(s, st):
    """Top band: the node chain with the target slot showing the pending FX."""
    s.T("PLACE", 4, 1, 8, ls=1)
    s.T(_fit(s, st.wl[st.pick_cat]["key"], 8, 56), 46, 1, 8)
    s.T("SL%d" % (st.node + 1), 106, 2, 6)
    step, cw, ty, ch = 25, 23, 12, 20
    wy = ty + ch // 2
    cells = []
    pend = st.wl[st.pick_cat]["abbr"]
    for j in range(5):
        idx = st.node - 2 + j
        if idx < 0 or idx >= len(st.board):
            continue
        n = st.board[idx]
        x = 2 + j * step
        cells.append((idx, x, x + cw - 1))
        if idx == st.node:                      # target slot: incoming FX preview
            s.dashed(x, ty, cw, ch, on=2, off=2)
            s.T(pend, x + 3, ty + 7, 12)
        elif n["empty"]:
            s.dashed(x, ty, cw, ch, on=1, off=2)
        else:
            s.box(x, ty, cw, ch)
            s.T(n["abbr"], x + 3, ty + 7, 12)
    for a in range(len(cells) - 1):
        if cells[a + 1][1] - 1 >= cells[a][2] + 1:
            s.d.rectangle([cells[a][2] + 1, wy, cells[a + 1][1] - 1, wy], fill=1)
    if cells:
        if cells[0][0] > 0:
            s.d.rectangle([0, wy, cells[0][1] - 1, wy], fill=1)
        if cells[-1][0] < len(st.board) - 1:
            s.d.rectangle([cells[-1][2] + 1, wy, WIDTH - 1, wy], fill=1)


def _pick(st):
    s = Screen()
    _pick_chain(s, st)
    s.hline(0, 38, 128)
    by = 44
    on_cat = st.pick == "cat"
    # left strip: category abbrs (matches node-strip abbrs)
    _striplist(s, [b["abbr"] for b in st.wl], st.pick_cat, 0, 40, by, active=on_cat, size=12)
    s.d.rectangle([41, by - 2, 41, 115], fill=1)
    # right strip: plugins of the hovered/locked category (preview until locked)
    plugs = [p["display"] for p in st.wl[st.pick_cat]["plugins"]]
    _striplist(s, plugs, -1 if on_cat else st.pick_fx, 45, 83, by, active=not on_cat, size=8)
    s.T("e1 turn/sel   e0hold back", 4, 120, 6)
    _toast_over(s, st)
    return s.img


def _sys(st):
    s = Screen()
    s.T("SYSTEM", 6, 4, 8, ls=1)
    s.hline(0, 16, 128)
    for i, it in enumerate(SYSITEMS):
        y = 24 + i * 18
        if i == st.sys_idx:
            s.box(4, y - 2, 120, 16, fill=True)
            s.T(it, 9, y, 12, fill=0)
        else:
            s.T(it, 9, y, 12)
    s.T("e0 move.click  HOLD back", 5, 120, 6)
    return s.img


def _tuner(st):
    s = Screen()
    s.T("TUNER", 6, 4, 8, ls=1)
    s.T("e1 hold ret", 84, 4, 6)
    s.T(st.tnote, int((128 - s.Tw(46, st.tnote)) / 2), 18, 46)
    s.hline(10, 88, 108)
    for i in range(-2, 3):
        s.d.rectangle([64 + i * 24, 84, 64 + i * 24, 92], fill=1)
    nx = 64 + max(-52, min(52, round(st.tcents / 50 * 52)))
    s.box(nx - 1, 76, 3, 20, fill=True)
    s.T("b", 6, 78, 8)
    s.T("#", 118, 78, 8)
    if abs(st.tcents) < 5:
        s.chip("IN TUNE", 40, 104, 48, 16, 8)
    else:
        t = ("+" if st.tcents > 0 else "") + str(st.tcents) + " cents"
        s.T(t, int((128 - s.Tw(8, t)) / 2), 107, 8)
    return s.img


# ---- LED derivation (port of leds()) -> (enc0, enc1) colour names ----
OFF = "off"


def leds(st):
    n = st.board[st.node]
    if st.tuner:
        return ("purple", "purple")
    if st.pick:                               # ENC0=back(grey), ENC1=operate(cat colour)
        return ("grey", BUCKETCOL.get(st.wl[st.pick_cat]["key"], "amber"))
    if st.sys:
        return ("grey", OFF)
    if st.depth == -1:
        return ("blue", "green")
    l0 = OFF
    if not n["empty"]:
        l0 = "red" if n["bypass"] else BUCKETCOL.get(n["bucket"], "grey")
    l1 = OFF
    if st.menu_open:
        l1 = "red" if AppController(st).menu_items()[st.menu][2] == "remove" else "amber"
    elif st.locked:
        l1 = "green"
    return (l0, l1)


# ============================== runners ==============================
def _walk():
    """Scripted walkthrough — drives events and prints state (no TTY)."""
    from ganglion.input import KeyboardInput
    kb = KeyboardInput()
    c = AppController()
    t = [0.0]

    def do(chars, note):
        for ch in chars:
            for ev in kb.feed(ch, t[0]):
                c.feed(ev)
            t[0] += 0.1
        print("%-5s %-9s %s" % (chars, note, _snap(c.st)))

    print("init  %-9s %s" % ("", _snap(c.st)))
    do("tt", "nav>")       # enc0 CW x2: node 1 -> 3 (NAM -> Delay via AMP/Cab)
    do("s", "lock")        # enc1 click: focus-lock knob
    do("gg", "adjust")     # enc1 CW x2: adjust locked value
    do("s", "unlock")
    do("w", "slot-menu")   # enc0 click: open slot menu
    do("t", "menu>")       # move menu selection
    do("w", "exec")        # enc0 click: execute (bypass)
    do("e", "hold-up")     # enc0 hold: depth 0 -> -1 (glance)
    do("g", "snap>")       # enc1 CW: snapshot scroll
    do("x", "combo")       # save snapshot (toast)
    do("e", "hold-down")   # back to depth 0
    do("rrr", "to-node0")  # enc0 CCW: node 3 -> 0
    do("r", "sys")         # one more left past start -> SYSTEM
    do("w", "sys-exec")    # SYSTEM item 0 = Tuner -> tuner
    do("w", "tuner-exit")  # click exits tuner
    # picker (ENC1 operates, ENC0-hold backs): replace node 0
    do("w", "menu")        # enc0 click: slot menu on node 0
    do("tt", "to-replace") # enc0 turn: menu 0 -> 2 (Replace)
    do("w", "pick-cat")    # enc0 click: exec -> picker (cat strip)
    do("gg", "cat>")       # enc1 turn: scroll categories (Dynamics -> Pedal)
    do("s", "pick-fx")     # enc1 click: lock category -> plugin strip
    do("e", "back-cat")    # enc0 hold: back to category strip
    do("s", "pick-fx2")    # enc1 click: into plugins again
    do("g", "fx>")         # enc1 turn: scroll plugins
    do("s", "place")       # enc1 click: place node -> board[0] replaced
    do("w", "menu2")       # reopen menu on the freshly placed node
    do("w", "bypass2")     # bypass it (sanity: node model intact)


def _snap(st):
    n = st.board[st.node]
    kv = fmt(n["knobs"][st.knob]) if not n["empty"] and n["knobs"] else "--"
    return ("d=%d node=%d(%s) k=%d[%s] lock=%d dirty=%d menu=%d pick=%s sys=%d tun=%d pb=%d snap=%d toast=%r"
            % (st.depth, st.node, n["abbr"] or "--", st.knob, kv, st.locked, st.dirty,
               st.menu_open, st.pick or "-", st.sys, st.tuner, st.pb, st.snap, st.toast))


def main(argv):
    if "--walk" in argv:
        _walk()
        return
    if not sys.stdin.isatty():
        print("app needs a TTY. Try: python3 ganglion/app.py --walk")
        return
    import termios
    import tty
    import select
    import time
    from ganglion.display import TerminalRenderer
    from ganglion.input import KeyboardInput
    r = TerminalRenderer("braille")
    kb = KeyboardInput()
    c = AppController()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?25l\x1b[?1049h\x1b[2J")
        while True:
            now = time.monotonic()
            while select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.read(1)
                if ch in ("Q",):
                    return
                for ev in kb.feed(ch, now):
                    c.feed(ev)
            rows = r.render(render(c.st))
            hud = ["r/t e0  f/g e1", "w/s click  e/d hold  x combo", "Q quit",
                   "", _snap(c.st).replace(" ", "\n ", 0)[:40], "leds " + str(leds(c.st))]
            out = []
            for i, row in enumerate(rows):
                out.append(row + "  " + (hud[i] if i < len(hud) else "") + "\x1b[K")
            sys.stdout.write("\x1b[H" + "\r\n".join(out) + "\x1b[J")
            sys.stdout.flush()
            time.sleep(0.03)
    finally:
        sys.stdout.write("\x1b[?1049l\x1b[?25h")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main(sys.argv[1:])
