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
  geco_whitelist.json) · move (Move picks the node up at depth 0 — lifted 5px;
  ENC0 shifts slots, click drops, hold cancels) · board/snapshot manage (glance
  click → submenu: Save/Save As/Rename/Delete; naming reuses synapse's word bank
  "Term-suffix" via ENC1=term/ENC0=reroll; delete → confirm overlay) · SYSTEM
  (ENC0 scroll-left-past-start) · TUNER (ENC1 hold) · COMBO (save).

The mockup's 2a interactions are all ported now. Still pending: wiring to
synapse's real model/modepctrl/plugincatalog (placed nodes use per-bucket
placeholder knobs; board/snap lists + level meters are self-contained samples).

Run (needs a TTY):  python3 ganglion/app.py
Scripted check:      python3 ganglion/app.py --walk
"""

import datetime
import json
import os
import random
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

# ---- SAVE AS naming (reuses synapse's word bank; 0 core edits) --------------
# Reuses synapse's SAVE AS word pool (qtview/editor_bridge), the SAME shared
# resource file (resources/snapshot_words.txt, ~6k words). On 2 encoders this
# beats char entry: ENC0 dials the categorical part, ENC1 re-rolls the random
# part, ENC0 click accepts. Boards and snapshots use DIFFERENT schemes so their
# names read as a hierarchy at a glance:
#   board = stage term + '-' + random word   ("Drive-cupcake")
#   snap  = random word + '-' + weekday       ("hospital-sunday")
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERMS = ["Clean", "Crunch", "Drive", "Lead", "Rhythm", "Solo",
         "Verse", "Chorus", "Bridge", "Boost", "Ambient", "Heavy"]
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WORDS_PATH = os.path.join(_REPO, "resources", "snapshot_words.txt")
_WORDS_FALLBACK = ["chainsaw", "cupcake", "walrus", "thunder", "pickle",
                   "comet", "goblin", "biscuit", "tornado", "noodle"]
_words = None
_rng = random.Random()


def _load_words():
    global _words
    if _words is None:
        try:
            with open(_WORDS_PATH, encoding="utf-8") as f:
                _words = [w for w in (ln.strip() for ln in f) if w and not w.startswith("#")]
        except OSError:
            _words = []
        if not _words:
            _words = list(_WORDS_FALLBACK)
    return _words


def _rand_word(rng=None):
    return (rng or _rng).choice(_load_words())


def name_cats(which):
    """The categorical (ENC0) options: stage terms for boards, weekdays for snaps."""
    return TERMS if which == "board" else DAYS


def name_build(which, ncat, rand):
    """Assemble a name from its categorical index + random word (per-scheme order)."""
    return "%s-%s" % (TERMS[ncat], rand) if which == "board" else "%s-%s" % (rand, DAYS[ncat])


def _system_day_idx():
    """Today's weekday as an index into DAYS (0=monday). Snap naming derives its
    day part from the clock so it needs no encoder (Q3) — injected for tests."""
    return datetime.date.today().weekday()


# Board/snapshot manage submenu (decision C: sub). Same set for both.
SUB_ACTIONS = [("Save", "save"), ("Save As", "saveas"), ("Rename", "rename"),
               ("Delete", "delete"), ("Back", "back")]


def _op(which):
    """The operating encoder for a manage context: boards ride ENC0 (top band),
    snapshots ride ENC1 (bottom band) — matching which encoder opened it."""
    return 0 if which == "board" else 1


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
    moving: bool = False      # picked-up node: ENC0 shifts slot, click drops
    move_from: int = 0        # original index (ENC0-hold cancel restores it)
    tuner: bool = False
    tcents: int = 6
    tnote: str = "A"
    pb: int = 0
    snap: int = 1
    sub: str = ""             # ""=off, "board"/"snap": manage submenu open
    sub_idx: int = 0
    naming: str = ""          # ""=off, "<which>:<mode>" e.g. "board:saveas"
    ncat: int = 0             # ENC0 categorical index (TERMS for board, DAYS for snap)
    nrand: str = ""           # ENC1 random word (kept across term/day changes)
    nname: str = ""           # the assembled name (name_build)
    confirm: str = ""         # ""=off, or pending action e.g. "del:board"
    cyes: bool = False        # confirm overlay highlight (No/Yes)
    dirty: bool = False
    toast: str = ""
    board: list = field(default_factory=make_board)
    wl: list = field(default_factory=load_whitelist)
    boards: list = field(default_factory=lambda: list(PBS))
    snaps: list = field(default_factory=lambda: list(SNAPS))


class AppController:
    """Ported 2a state machine. ``feed(event)`` mutates ``self.st``."""

    def __init__(self, state=None, day_provider=None):
        self.st = state or AppState()
        # Snap naming's weekday comes from the clock (Q3). Injected so --walk/tests
        # stay deterministic; defaults to the real system date on device.
        self._day_provider = day_provider or _system_day_idx

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
        if st.confirm:                         # the opening encoder toggles No/Yes
            if enc == _op(st.confirm.split(":")[1]):
                st.cyes = not st.cyes
            return
        if st.naming:                          # Q3: category=ENC0 (board only), reroll=ENC1
            which = st.naming.split(":")[0]
            if which == "board" and enc == 0:  # board: ENC0 dials the stage term
                st.ncat = (st.ncat + d) % len(name_cats(which))
                self._rebuild_name(reroll=False)
            elif enc == 1:                     # ENC1 re-rolls (snap day is auto — no ENC0)
                self._rebuild_name(reroll=True)
            return
        if st.sub:                             # the encoder that opened it operates it
            if enc == _op(st.sub):
                st.sub_idx = (st.sub_idx + d) % len(SUB_ACTIONS)
            return
        if st.pick:
            if enc == 1:                       # ENC1 turns the active strip
                if st.pick == "cat":
                    st.pick_cat = (st.pick_cat + d) % len(st.wl)
                else:
                    st.pick_fx = (st.pick_fx + d) % len(st.wl[st.pick_cat]["plugins"])
            return
        if st.sys:                             # Q4: ENC0-only (matches other modals)
            if enc == 0:
                st.sys_idx = (st.sys_idx + d) % len(SYSITEMS)
            return
        if st.menu_open:                       # Q4: ENC0-only (ENC0 also commits)
            if enc == 0:
                st.menu = (st.menu + d) % len(self.menu_items())
            return
        if st.depth == -1:
            if enc == 0:
                st.pb = (st.pb + d) % len(st.boards)
            else:
                st.snap = (st.snap + d) % len(st.snaps)
            return
        # depth 0
        if st.moving:                        # picked-up node: ENC0 swaps with neighbour
            if enc == 0:
                j = st.node + d
                if 0 <= j < len(st.board):
                    st.board[st.node], st.board[j] = st.board[j], st.board[st.node]
                    st.node = j
            return
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
        if st.confirm:                         # opening encoder acts; the other cancels
            if enc == _op(st.confirm.split(":")[1]):
                if st.cyes:
                    self._confirm_exec()
                else:
                    st.confirm = ""
            else:
                st.confirm = ""
            return
        if st.naming:                          # Q3: operating encoder accepts (board=E0, snap=E1)
            which = st.naming.split(":")[0]
            if enc == _op(which):
                self._name_accept()
            elif enc == 1:                     # ENC1 click = re-roll (board's non-op hand)
                self._rebuild_name(reroll=True)
            return
        if st.sub:                             # opening encoder picks; the other backs
            if enc == _op(st.sub):
                self._sub_act(SUB_ACTIONS[st.sub_idx][1])
            else:
                st.sub = ""
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
        if st.depth == -1:                     # open board (e0) / snapshot (e1) manage
            st.sub, st.sub_idx = ("board" if enc == 0 else "snap"), 0
            return
        # depth 0
        if st.moving:                          # ENC0 click = drop here (commit)
            if enc == 0:
                st.moving, st.dirty = False, True
                self._toast("MOVED")
            return
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
        elif act == "move":                    # back to chain, pick up this node
            st.menu_open, st.moving, st.move_from = False, True, st.node
        else:
            st.menu_open = False
            self._toast("TODO: " + act)

    # -- board / snapshot manage (decision C: sub / naming / confirm) ------
    def _lst(self, which):
        """(list, active-index) for 'board' or 'snap'."""
        st = self.st
        return (st.boards, st.pb) if which == "board" else (st.snaps, st.snap)

    def _set_idx(self, which, i):
        if which == "board":
            self.st.pb = i
        else:
            self.st.snap = i

    def _sub_act(self, act):
        st = self.st
        which = st.sub
        lst, idx = self._lst(which)
        if act == "back":
            st.sub = ""
        elif act == "save":                    # overwrite current (persist)
            st.sub, st.dirty = "", False
            self._toast("SAVED")
        elif act == "saveas":                  # new entry via the name suggester
            self._name_open(which, "saveas")
        elif act == "rename":
            self._name_open(which, "rename")
        elif act == "delete":
            if len(lst) <= 1:
                st.sub = ""
                self._toast("KEEP 1 MIN")
            else:
                st.confirm, st.cyes = "del:" + which, False

    def _name_open(self, which, mode):
        st = self.st
        # Q3: boards dial a stage term (ENC0); snaps take today's weekday from the
        # clock so naming rides ENC1 only (no categorical dial).
        ncat = 0 if which == "board" else self._day_provider() % len(DAYS)
        st.sub, st.naming, st.ncat = "", "%s:%s" % (which, mode), ncat
        self._rebuild_name(reroll=True)

    def _rebuild_name(self, reroll):
        """Re-assemble nname from ncat + nrand; reroll the random word if asked or
        on a name collision. Boards read Term-word, snaps read word-day."""
        st = self.st
        which, mode = st.naming.split(":")
        lst, idx = self._lst(which)
        taken = set(lst)
        if mode == "rename":
            taken.discard(lst[idx])
        for _ in range(12):
            if reroll or not st.nrand:
                st.nrand = _rand_word(_rng)
            cand = name_build(which, st.ncat, st.nrand)
            if cand not in taken:
                st.nname = cand
                return
            reroll = True                      # collision -> force a fresh word
        st.nname = cand

    def _name_accept(self):
        st = self.st
        which, mode = st.naming.split(":")
        lst, idx = self._lst(which)
        if mode == "rename":
            lst[idx] = st.nname
        else:                                  # saveas -> insert after current, select it
            lst.insert(idx + 1, st.nname)
            self._set_idx(which, idx + 1)
        st.naming, st.dirty = "", (which == "snap")
        self._toast(("RENAMED " if mode == "rename" else "SAVED ") + st.nname)

    def _confirm_exec(self):
        st = self.st
        if st.confirm.startswith("del:"):
            which = st.confirm.split(":")[1]
            lst, idx = self._lst(which)
            if len(lst) > 1:
                lst.pop(idx)
                self._set_idx(which, min(idx, len(lst) - 1))
            self._toast("DELETED")
        st.confirm, st.sub = "", ""

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
        if st.confirm:                        # Q3: operating encoder hold = cancel (= No)
            if enc == _op(st.confirm.split(":")[1]):
                st.confirm = ""
            return
        if st.naming:                         # Q3: operating encoder hold = cancel naming
            if enc == _op(st.naming.split(":")[0]):
                st.naming = ""
            return
        if st.sub:                            # ENC0 hold = close submenu
            if enc == 0:
                st.sub = ""
            return
        if st.pick:                           # ENC0 hold = back (consistent); ENC1 hold = no-op
            if enc == 0:
                st.pick = "cat" if st.pick == "fx" else ""
            return
        if st.moving:                         # ENC0 hold = cancel move, restore position
            if enc == 0:
                node = st.board.pop(st.node)
                st.board.insert(st.move_from, node)
                st.node, st.moving = st.move_from, False
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
        st = self.st
        if st.moving or st.pick or st.sub or st.naming or st.confirm:
            return
        st.dirty = False                       # Q7: keep current depth; splash confirms
        self._toast("SNAPSHOT SAVED")

    def _toast(self, msg):
        self.st.toast = msg


# ========================= VIEW (state -> frame) =========================
def render(st):
    if st.tuner:
        return _tuner(st)
    if st.confirm:
        return _confirm(st)
    if st.naming:
        return _naming(st)
    if st.sub:
        return _sub(st)
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
        cy = ty - 5 if (st.moving and sel) else ty   # lift the picked-up node
        if n["empty"]:
            s.dashed(x, cy, cw, ch, on=2, off=2)
            s.T("+", x + 8, cy + 8, 12, fill=1)
        elif sel:
            s.box(x, cy, cw, ch, fill=True)
            s.T(n["abbr"], x + 3, cy + 9, 12, fill=0)
        elif n["bypass"]:
            s.dashed(x, cy, cw, ch, on=1, off=2)
            s.T(n["abbr"], x + 3, cy + 9, 12)
        else:
            s.box(x, cy, cw, ch)
            s.T(n["abbr"], x + 3, cy + 9, 12)
    for a in range(len(cells) - 1):
        if cells[a + 1][1] - 1 >= cells[a][2] + 1:
            s.d.rectangle([cells[a][2] + 1, wy, cells[a + 1][1] - 1, wy], fill=1)
    if cells:
        if cells[0][0] > 0:
            s.d.rectangle([0, wy, cells[0][1] - 1, wy], fill=1)
        if cells[-1][0] < len(st.board) - 1:
            s.d.rectangle([cells[-1][2] + 1, wy, WIDTH - 1, wy], fill=1)
    if st.node == 0 and not st.moving:         # Q2: SYSTEM is one scroll-left past start
        s.T("<SYS", 2, 15, 8)
    s.hline(0, 40, 128)
    n = st.board[st.node]
    if st.moving:                              # move mode: instructions in place of knobs
        s.T("MOVING", 4, 45, 16)
        s.T(n["name"], 4, 66, 8)
        s.T("SLOT %d/%d" % (st.node + 1, len(st.board)), 4, 78, 8)
        s.T("e0 turn = shift", 4, 96, 8)
        s.T("click drop  hold cancel", 4, 108, 8)
        _toast_over(s, st)
        return s.img
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
    s.T(_fit(s, st.boards[st.pb], 24, 122), 5, 14, 24)  # marquee later
    s.dots(len(st.boards), st.pb, 6, 47)
    s.hline(0, 56, 128)
    s.T("SNAPSHOT", 6, 62, 8, ls=1)
    s.T(_fit(s, st.snaps[st.snap], 24, 122), 5, 71, 24)
    s.dots(len(st.snaps), st.snap, 6, 99)
    s.T("e0 pb.CLK manage  e1 snap", 5, 118, 6)
    s.T("-1", 116, 5, 8)
    if st.dirty:
        s.d.ellipse([120, 2, 125, 7], fill=1)
    _toast_over(s, st)
    return s.img


def _sub(st):
    s = Screen()
    which = st.sub
    lst, idx = (st.boards, st.pb) if which == "board" else (st.snaps, st.snap)
    s.T("BOARD" if which == "board" else "SNAPSHOT", 6, 4, 8, ls=1)
    s.T(_fit(s, lst[idx], 12, 118), 6, 16, 12)
    s.hline(0, 30, 128)
    y0, rh = 36, 16
    for i, (label, _) in enumerate(SUB_ACTIONS):
        y = y0 + i * rh
        if i == st.sub_idx:
            s.box(4, y - 2, 120, rh - 2, fill=True)
            s.T(label, 9, y, 12, fill=0)
        else:
            s.T(label, 9, y, 12)
    opn = "e0" if which == "board" else "e1"
    s.T("%s turn/click   e0hold back" % opn, 5, 120, 6)
    _toast_over(s, st)
    return s.img


def _naming(st):
    s = Screen()
    which, mode = st.naming.split(":")
    head = ("RENAME " if mode == "rename" else "SAVE AS ") + ("BOARD" if which == "board" else "SNAP")
    s.T(head, 6, 4, 8, ls=1)
    s.hline(0, 16, 128)
    if which == "board":                        # board: ENC0 dials the stage term
        s.T("TERM  (e0)", 6, 22, 6)
        s.chip(TERMS[st.ncat], 6, 30, 90, 16, 8)
        foot1, foot2 = "e0 term   e1 reroll", "e0 click OK   hold X"
    else:                                       # snap: day is auto (from clock) — E1 only
        s.T("DAY  (auto)", 6, 22, 6)
        s.chip(DAYS[st.ncat], 6, 30, 90, 16, 8)
        foot1, foot2 = "e1 reroll", "e1 click OK   e1 hold X"
    s.T("NAME", 6, 52, 6)
    s.T(_fit(s, st.nname, 12, 122), 6, 62, 12)  # 12px so the full name fits
    s.hline(0, 84, 128)
    s.T(foot1, 5, 104, 6)
    s.T(foot2, 5, 114, 6)
    _toast_over(s, st)
    return s.img


def _confirm(st):
    s = Screen()
    which = st.confirm.split(":")[1]
    lst, idx = (st.boards, st.pb) if which == "board" else (st.snaps, st.snap)
    s.box(6, 22, 116, 84)
    s.T("DELETE", 38, 30, 16)
    s.T("BOARD?" if which == "board" else "SNAPSHOT?", 12, 50, 8)
    s.T(_fit(s, lst[idx], 12, 104), 12, 62, 12)
    for i, label in enumerate(["No", "Yes"]):
        x = 22 + i * 54
        if ((i == 1) == st.cyes):
            s.chip(label, x, 84, 44, 16, 8)
        else:
            s.box(x, 84, 44, 16)
            s.T(label, x + (44 - int(s.Tw(8, label))) // 2, 88, 8)
    opn = "e0" if which == "board" else "e1"   # Q3: operating encoder toggles/commits/cancels
    s.T("%s turn/click   %shold No" % (opn, opn), 8, 110, 6)
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
    _toast_over(s, st)
    return s.img


def _fit(s, txt, size, maxw):
    """Truncate txt so it fits maxw px at the given tier."""
    if s.Tw(size, txt) <= maxw:
        return txt
    while txt and s.Tw(size, txt) > maxw:
        txt = txt[:-1]
    return txt


def _window(n, sel, vis):
    return 0 if n <= vis else max(0, min(sel - vis // 2, n - vis))


def _caret(s, cx, y, up):
    """A 5x3 scroll triangle centred on cx (points up if ``up``)."""
    for k in range(3):
        half = k if up else 2 - k
        s.d.rectangle([cx - half, y + k, cx + half, y + k], fill=1)


def _striplist(s, items, sel, x, w, y0, active, size=8, vis=5, rh=14):
    """Windowed list inside [x, x+w). Focus ring = filled; locked = hollow.
    Scroll carets are drawn by the caller (in the gaps) so text keeps full width."""
    n = len(items)
    pad = max(1, (rh - 2 - round(fs(size) * 0.72)) // 2)   # center ink in the row
    start = _window(n, sel, vis)
    for r in range(min(vis, n)):
        i = start + r
        y = y0 + r * rh
        lbl = _fit(s, items[i], size, w - 6)
        if i == sel and active:
            s.box(x, y - 1, w, rh - 2, fill=True)
            s.T(lbl, x + 3, y + pad, size, fill=0)
        elif i == sel:                          # inactive strip: hollow marker
            s.box(x, y - 1, w, rh - 2)
            s.T(lbl, x + 3, y + pad, size)
        else:
            s.T(lbl, x + 3, y + pad, size)


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
    # left strip: category abbrs, big font (matches node-strip abbrs), 4 rows
    cats = [b["abbr"] for b in st.wl]
    _striplist(s, cats, st.pick_cat, 0, 48, by, active=on_cat, size=16, vis=4, rh=17)
    s.d.rectangle([49, by - 2, 49, 115], fill=1)
    # right strip: plugins of the hovered/locked category (preview until locked)
    plugs = [p["display"] for p in st.wl[st.pick_cat]["plugins"]]
    _striplist(s, plugs, -1 if on_cat else st.pick_fx, 51, 77, by, active=not on_cat, size=8)
    # scroll carets in the gaps above/below each strip (no per-row text collision)
    lstart = _window(len(cats), st.pick_cat, 4)
    rstart = _window(len(plugs), 0 if on_cat else st.pick_fx, 5)
    if lstart > 0:
        _caret(s, 24, 40, True)
    if lstart + 4 < len(cats):
        _caret(s, 24, 114, False)
    if rstart > 0:
        _caret(s, 89, 40, True)
    if rstart + 5 < len(plugs):
        _caret(s, 89, 114, False)
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
    _toast_over(s, st)
    return s.img


def _tuner(st):
    s = Screen()
    s.T("TUNER", 6, 4, 8, ls=1)
    s.T("press exit", 84, 4, 6)               # Q1: any press exits (rotate ignored)
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
    if st.confirm:                            # delete danger on the operating encoder
        return ("red", OFF) if _op(st.confirm.split(":")[1]) == 0 else (OFF, "red")
    if st.naming:                             # Q3: board=E0 term/accept+E1 reroll; snap=E1-only
        return ("green", "blue") if st.naming.split(":")[0] == "board" else (OFF, "green")
    if st.sub:                                # manage submenu on the opening encoder
        return ("blue", OFF) if _op(st.sub) == 0 else (OFF, "blue")
    if st.pick:                               # ENC0=back(grey), ENC1=operate(cat colour)
        return ("grey", BUCKETCOL.get(st.wl[st.pick_cat]["key"], "amber"))
    if st.moving:                             # ENC0 holds the node; ENC1 idle
        return (BUCKETCOL.get(n["bucket"], "amber"), OFF)
    if st.sys:
        return ("grey", OFF)
    if st.depth == -1:
        return ("blue", "green")
    l0 = OFF
    if not n["empty"]:
        l0 = "red" if n["bypass"] else BUCKETCOL.get(n["bucket"], "grey")
    l1 = OFF
    if st.menu_open:                          # Q5: danger(red) rides ENC0 (the commit hand)
        if AppController(st).menu_items()[st.menu][2] == "remove":
            l0 = "red"
        l1 = "amber"
    elif st.locked:
        l1 = "green"
    return (l0, l1)


# ============================== runners ==============================
def _walk():
    """Scripted walkthrough — drives events and prints state (no TTY)."""
    from ganglion.input import KeyboardInput
    _rng.seed(1)                     # deterministic suffix suggestions for the walk
    kb = KeyboardInput()
    c = AppController(day_provider=lambda: 3)   # fixed weekday (thursday) for determinism
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
    do("w", "slot-menu")   # enc0 click: open slot menu (menu 0 = Bypass/Enable)
    do("w", "exec")        # enc0 click: execute bypass/enable (menu closes)
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
    # move: pick up node 0, shift right two slots, drop
    do("w", "menu3")       # slot menu on node 0
    do("t", "to-move")     # menu 0 -> 1 (Move)
    do("w", "pickup")      # exec -> moving (back at chain, node lifted)
    print("      order   %s" % [b["abbr"] or "--" for b in c.st.board])
    do("tt", "shift>>")    # enc0 turn x2: swap node 0 -> 2
    print("      order   %s" % [b["abbr"] or "--" for b in c.st.board])
    do("w", "drop")        # enc0 click: commit landing at slot 2
    # board Save As (board scheme = Term-word): ENC0 dials term, ENC1 rerolls word
    do("e", "glance")      # enc0 hold: depth 0 -> -1
    do("w", "board-sub")   # enc0 click: open BOARD manage submenu
    do("t", "sub>")        # enc0 turn: Save -> Save As
    do("w", "saveas")      # enc0 click: -> name suggester
    do("tt", "term>>")     # enc0 turn x2: cycle stage term (word kept)
    do("g", "reroll")      # enc1 turn: re-roll the random word
    print("      board-name %r  (%d boards)" % (c.st.nname, len(c.st.boards)))
    do("w", "accept")      # enc0 click: insert new board, select it
    print("      boards  %s pb=%d" % (c.st.boards, c.st.pb))
    # snapshot manage is operated by ENC1 (the encoder that opened it)
    do("s", "snap-sub")    # enc1 click: open SNAP manage submenu (E1 operates)
    do("g", "sub>")        # enc1 turn: Save -> Save As
    do("s", "snap-saveas") # enc1 click: -> name suggester (word-day; day auto = thursday)
    do("g", "reroll")      # enc1 turn: re-roll the random word
    print("      snap-name  %r  (%d snaps)" % (c.st.nname, len(c.st.snaps)))
    do("s", "accept-snap") # enc1 click: accept (Q3: snap naming is E1-only)
    print("      snaps   %s snap=%d" % (c.st.snaps, c.st.snap))
    # delete the new board (confirm overlay)
    do("w", "board-sub2")  # open submenu on the new board
    do("ttt", "to-del")    # Save -> SaveAs -> Rename -> Delete
    do("w", "del?")        # enc0 click: -> confirm overlay (No highlighted)
    do("t", "yes")         # enc0 turn: highlight Yes
    do("w", "confirm")     # enc0 click: execute delete
    print("      boards  %s pb=%d" % (c.st.boards, c.st.pb))


def _snap(st):
    n = st.board[st.node]
    kv = fmt(n["knobs"][st.knob]) if not n["empty"] and n["knobs"] else "--"
    return ("d=%d node=%d(%s) k=%d[%s] dirty=%d menu=%d pick=%s mv=%d sub=%s name=%s conf=%s "
            "sys=%d tun=%d pb=%d(%s) snap=%d toast=%r"
            % (st.depth, st.node, n["abbr"] or "--", st.knob, kv, st.dirty,
               st.menu_open, st.pick or "-", st.moving, st.sub or "-", st.naming or "-",
               st.confirm or "-", st.sys, st.tuner, st.pb, st.boards[st.pb], st.snap, st.toast))


class _ScriptSource:
    """Headless input source: replays keyboard chars, one per poll (for tests)."""

    def __init__(self, kb, chars):
        self.kb = kb
        self.chars = list(chars)

    def poll(self, now):
        return self.kb.feed(self.chars.pop(0), now) if self.chars else []


class _CaptureSink:
    def __init__(self):
        self.frames, self.last = 0, None

    def show(self, frame):
        self.frames, self.last = self.frames + 1, frame


def _looptest():
    """Drive the Runtime under a fake clock (no TTY) — proves loop + splash (F)."""
    from ganglion.runtime import Runtime
    from ganglion.input import KeyboardInput
    clk = [0.0]
    c = AppController()
    src = _ScriptSource(KeyboardInput(), ["t", "x", "t"])   # nav, combo(save), nav
    rt = Runtime(c, src, _CaptureSink(), render, leds=leds, splash_s=0.5, tick_s=0.03,
                 clock=lambda: clk[0], sleep=lambda dt: clk.__setitem__(0, clk[0] + dt))
    rt.step()
    print("t (nav)   node=%d toast=%r  clk=%.2f" % (c.st.node, c.st.toast, clk[0]))
    t0 = clk[0]
    rt.step()                                               # 'x' sets toast -> splash
    dt = clk[0] - t0
    ok = c.st.toast == "" and dt >= 0.5
    print("x (combo) depth=%d toast=%r  splash_dt=%.2f  %s"
          % (c.st.depth, c.st.toast, dt, "SPLASH-OK" if ok else "SPLASH-FAIL"))
    rt.step()
    print("t (nav)   pb=%d  frames=%d" % (c.st.pb, rt.sink.frames))


def main(argv):
    if "--walk" in argv:
        _walk()
        return
    if "--looptest" in argv:
        _looptest()
        return
    from ganglion.runtime import run_terminal
    c = AppController()

    def hud():
        return ["r/t e0  f/g e1", "w/s click  e/d hold  x combo", "Q quit",
                "", _snap(c.st)[:40], "leds " + str(leds(c.st))]

    if "--device" in argv:
        from ganglion.runtime import run_device
        run_device(c, render, leds)
        return
    run_terminal(c, render, leds=leds, hud=hud)


if __name__ == "__main__":
    main(sys.argv[1:])
