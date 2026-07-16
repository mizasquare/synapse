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
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field

from PIL import ImageDraw

from ganglion import WIDTH, HEIGHT
from ganglion.render import Screen, fs
from ganglion.input import Rotate, Press, Combo
from ganglion.geco_backend import FakeGeco

BG = 0

# ---- knob-value rendering (norm/fmt) + LED colours ----
# Board/catalog fixtures and their factories (K/make_board/make_node/whitelist)
# now live in geco_backend.py (the seam); the view keeps only what it renders.
# ENC0 LED per effect category (design leds()); ENC1/state colours below.
# Old sample-board bucket names + the live GECO whitelist keys share this map.
BUCKETCOL = {"Drive": "amber", "Comp": "green", "Amp·Cab": "amber",
             "Delay": "purple", "Reverb": "blue", "EQ": "blue", "Mod": "purple",
             "Filter": "blue", "Utility": "grey",
             "Dynamics": "green", "Pedal": "amber", "Amp": "amber", "Cab": "amber",
             "Spatial": "blue", "Utils": "grey"}


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
    sys_focus: bool = False   # parked at the SYS entry (edge detent); E0 click enters
    sys_idx: int = 0
    pick: str = ""            # ""=off, "cat"=category list, "fx"=plugin list
    pick_cat: int = 0
    pick_fx: int = 0
    moving: bool = False      # picked-up node: ENC0 shifts slot, click drops
    move_from: int = 0        # original index (ENC0-hold cancel restores it)
    add: str = ""             # parked on a [+] pseudo-cell: ""=off, "head", "tail"
    ins_at: int = -1          # picker opened to INSERT: splice index (-1 = replace at st.node)
    tuner: bool = False
    tcents: int = 6
    tnote: str = "A"
    pb: int = 0               # highlighted board (glance cursor)
    pb_cur: int = 0           # board actually loaded on the host (glance "loaded" marker)
    snap: int = 1
    snap_cur: int = 1         # snapshot actually loaded on the host
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
    # Display clock (seconds since the loop started), written by Runtime before
    # each draw — the ONLY time in the state. Marquee phase reads it; the
    # controller never does. Stays 0.0 off-loop (--walk, goldens) => static frames.
    t: float = 0.0
    t_mark: float = 0.0       # t at the last input: marquee phase = t - t_mark
    # Render caches mirrored from the backend (the source of truth). Seeded by
    # AppController.__init__ and re-synced after each mutation; the view reads
    # only these, so it never touches the backend. Bare AppState() starts empty.
    board: list = field(default_factory=list)
    wl: list = field(default_factory=list)
    boards: list = field(default_factory=list)
    snaps: list = field(default_factory=list)


# ---- mode selection (the ONE cascade) -------------------------------------
# The active mode is derived from AppState's flags in a single canonical order.
# Every input handler (rot/click/hold) and every view function (_frame/rails/
# leds/_rail_split) dispatches off this — so the priority order lives in exactly
# one place and can't drift between them. Flags stay the source of truth (the
# confirm-over-sub overlay is preserved for free); this only reads them.
def mode_of(st):
    if st.tuner:       return "tuner"
    if st.confirm:     return "confirm"
    if st.naming:      return "naming"
    if st.sub:         return "sub"
    if st.pick:        return "pick"
    if st.sys:         return "sys"
    if st.menu_open:   return "menu"
    if st.depth == -1: return "glance"
    if st.sys_focus:   return "sysfocus"
    if st.moving:      return "moving"
    if st.add or not st.board:               # parked on a [+] cell (an empty chain IS one)
        return "adding"
    return "chain"


# ---- the chain's cursor axis (nodes + the [+] cells) ------------------------
# The chain is variable-length, so "add an effect" needs a place to stand: a [+]
# pseudo-cell at the head and (when the chain is non-empty) one at the tail. They
# are cells you scroll onto, not nodes — st.add parks on one, and only then is
# st.node meaningless. An empty chain is just the head [+], which is what turns
# "0 nodes" from a crash into an ordinary state (it used to index st.board[0]).
def cells(st):
    """The cursor axis left-to-right: "head", 0..n-1, "tail" (head only if empty)."""
    if not st.board:
        return ["head"]
    return ["head"] + list(range(len(st.board))) + ["tail"]


def cpos(st):
    """Index of the focused cell in cells(st)."""
    if st.add == "head" or not st.board:
        return 0
    if st.add == "tail":
        return len(st.board) + 1
    return st.node + 1


def menu_items(st):
    """The slot menu's (icon, label, action) rows for the focused node — a pure
    query of state, shared by the menu mode's dispatch and its view."""
    n = st.board[st.node]
    return [("O" if not n["bypass"] else "*", "Enable" if n["bypass"] else "Bypass", "bypass"),
            ("<>", "Move", "move"), ("~", "Replace", "replace"),
            # [사용자] "뒤에 붙는다"는 절대규칙은 직관적이지 않다 -> 방향을 명시적으로 고른다.
            # 모달로 되묻지 않고 두 항목으로 편 이유: 클릭 수가 늘지 않고 새 상태도 안 생긴다.
            # 어휘는 [+] 셀의 "ADD FX"와 통일("Insert"는 내부 용어로만 남는다).
            ("[+", "Add Before", "ins_before"), ("+]", "Add After", "ins_after"),
            ("X", "Remove", "remove"), ("<", "Back", "back")]


class AppController:
    """Ported 2a state machine. ``feed(event)`` mutates ``self.st``."""

    def __init__(self, state=None, day_provider=None, backend=None):
        # backend: the GECO seam (board / catalog / persistence). Defaults to the
        # in-memory FakeGeco; a live entry point injects an adapter over synapse.
        self.backend = backend or FakeGeco()
        self._rotmag = 1                       # [D] last detent magnitude (value accel)
        self.st = state or AppState()
        self._sync_board()                    # seed the render caches from the backend
        self.st.wl = self.backend.catalog()
        self._sync_lists()
        # Start the glance cursor on whatever board/snap the host has loaded, so the
        # highlight and the "loaded" marker agree until the user scrolls off.
        self.st.pb = self.st.pb_cur = self.backend.current("board")
        self.st.snap = self.st.snap_cur = self.backend.current("snap")
        # Snap naming's weekday comes from the clock (Q3). Injected so --walk/tests
        # stay deterministic; defaults to the real system date on device.
        self._day_provider = day_provider or _system_day_idx

    def _sync_board(self):
        """Refresh the board cache from the backend (call after any board mutation)."""
        self.st.board = self.backend.board()

    def _sync_lists(self):
        """Refresh the board/snapshot name caches (call after any persist mutation)."""
        self.st.boards = self.backend.boards()
        self.st.snaps = self.backend.snapshots()

    # -- event entry ------------------------------------------------------
    def feed(self, ev):
        m = MODES[mode_of(self.st)]        # the active mode owns rotate/click/hold
        if isinstance(ev, Rotate):
            # [DECISION D] nav stays 1:1 (sign); value adjust accelerates with the
            # detent magnitude (fast spin = coarse — traverse long patch/param lists).
            # Keyboard emits |delta|=1 so this is a no-op there; multi-detent comes
            # from the real encoder (pos delta between polls).
            self._rotmag = max(1, abs(ev.delta))
            m.on_rotate(self, ev.enc, 1 if ev.delta > 0 else -1)
        elif isinstance(ev, Press):
            (m.on_hold if ev.kind == "long" else m.on_click)(self, ev.enc)
        elif isinstance(ev, Combo):
            if ev.kind == "press":         # global save; guards on its own
                self.combo()
        # Any input restarts the marquee (decision Q): scrolling past the head of a
        # name the user just landed on is unreadable. Not a clock read — the display
        # clock is already in the state; the controller only anchors to it.
        self.st.t_mark = self.st.t

    def enter(self, name, **kw):
        """Deliberately switch into a mode: the target Mode sets its own flag and
        initial values (each Mode.enter). Kept explicit — NOT auto-fired on a
        mode_of change — so revealing a mode by popping the overlay above it
        (cancel confirm -> sub) does NOT re-initialise the revealed mode."""
        MODES[name].enter(self, **kw)

    def _cur(self):
        return self.st.board[self.st.node]

    def adjust(self, d):
        n = self._cur()
        if not n["knobs"]:
            return
        kb = n["knobs"][self.st.knob]          # read current value from the cache
        mult = d * self._rotmag                # [D] accel: 1 detent=1 step, fast spin=coarse
        if kb["k"] == "toggle":
            v = 0 if kb["v"] >= .5 else 1
        elif kb["k"] in ("enum", "file"):
            v = max(kb["mn"], min(kb["mx"], round(kb["v"]) + mult))
        else:
            step = (kb["mx"] - kb["mn"]) / 40.0
            v = max(kb["mn"], min(kb["mx"], kb["v"] + step * mult))
        self.backend.set_param(self.st.node, self.st.knob, v)   # the detent maps to a value; backend stores it
        self._sync_board()
        self.st.dirty = True

    def _menu_act(self, act):
        st = self.st
        n = self._cur()
        if act == "back":
            st.menu_open = False
        elif act == "bypass":
            self.backend.set_bypass(st.node, not n["bypass"])
            self._sync_board()
            st.menu_open, st.dirty = False, True
        elif act == "remove":
            self.backend.remove(st.node)
            self._sync_board()
            st.menu_open, st.knob, st.dirty = False, 0, True
            st.node = min(st.node, len(st.board) - 1)   # the chain shrank under the cursor
            if not st.board:                            # removed the last one -> park on [+]
                st.add, st.node = "head", 0
        elif act == "replace":
            st.menu_open, st.ins_at = False, -1
            self.enter("pick")
        elif act in ("ins_before", "ins_after"):        # net-new: splice, side chosen explicitly
            st.menu_open = False
            st.ins_at = st.node if act == "ins_before" else st.node + 1
            self.enter("pick")
        elif act == "move":                    # back to chain, pick up this node
            st.menu_open = False
            self.enter("moving")
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

    def _set_cur(self, which, i):
        if which == "board":
            self.st.pb_cur = i
        else:
            self.st.snap_cur = i

    def _rehome_snap(self):
        """After the loaded board changes, the snapshot list + current snapshot
        belong to the NEW board (the host resets it on load) -> re-home the snap
        cursor onto it, else the marker/gesture point at the old board's indices."""
        j = self.backend.current("snap")
        self.st.snap = self.st.snap_cur = j

    def _select(self, which):
        """Load the highlighted board/snapshot onto the host (glance first-click).
        The chain and the 'loaded' marker follow the newly-current entry."""
        _, hi = self._lst(which)
        new = self.backend.select(which, hi)
        self._set_idx(which, new)
        self._set_cur(which, new)
        self._sync_board()                     # chain reflects the loaded board / snap params
        self._sync_lists()
        if which == "board":                   # fresh board carries its own current snapshot
            self._rehome_snap()
        self._toast(("LOADED " if which == "board" else "SNAP ") + self._lst(which)[0][new])

    def _sub_act(self, act):
        st = self.st
        which = st.sub
        lst, idx = self._lst(which)
        if act == "back":
            st.sub = ""
        elif act == "save":                    # overwrite current (persist)
            self.backend.save(which)
            st.sub, st.dirty = "", False
            self._toast("SAVED")
        elif act == "saveas":                  # new entry via the name suggester
            self.enter("naming", which=which, mode="saveas")
        elif act == "rename":
            self.enter("naming", which=which, mode="rename")
        elif act == "delete":
            if len(lst) <= 1:
                st.sub = ""
                self._toast("KEEP 1 MIN")
            else:
                self.enter("confirm", which=which)

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
        _, idx = self._lst(which)
        if mode == "rename":
            self.backend.rename(which, idx, st.nname)
            self._sync_lists()
            j = self.backend.current(which)    # board rename (save_as+remove) may reorder
            self._set_idx(which, j)
            self._set_cur(which, j)
        else:                                  # saveas -> new entry becomes current + selected
            j = self.backend.save_as(which, idx, st.nname)
            self._set_idx(which, j)
            self._set_cur(which, j)
            self._sync_lists()
        if which == "board":                   # board switched under us -> re-home snap cursor
            self._rehome_snap()
        self._sync_board()                     # loaded board/graph may have changed
        st.naming, st.dirty = "", (which == "snap")
        self._toast(("RENAMED " if mode == "rename" else "SAVED ") + st.nname)

    def _confirm_exec(self):
        st = self.st
        if st.confirm.startswith("del:"):
            which = st.confirm.split(":")[1]
            _, idx = self._lst(which)
            j = self.backend.delete(which, idx)   # board delete lands on a neighbour
            self._set_idx(which, j)
            self._set_cur(which, j)
            self._sync_lists()
            if which == "board":                  # delete switched the loaded board
                self._rehome_snap()
            self._sync_board()
            self._toast("DELETED")
        st.confirm, st.sub = "", ""

    def _sys_act(self):
        it = SYSITEMS[self.st.sys_idx]
        if it == "Tuner":
            self.st.sys = False
            self.enter("tuner")
        elif it == "< Back":
            self.st.sys = False
        else:
            self._toast("TODO: " + it)

    def combo(self):
        st = self.st
        if st.moving or st.pick or st.sub or st.naming or st.confirm or st.sys_focus:
            return
        st.dirty = False                       # Q7: keep current depth; splash confirms
        self._toast("SNAPSHOT SAVED")

    def _toast(self, msg):
        self.st.toast = msg


# ---- input modes (state-major dispatch) -------------------------------------
# One class per mode ties its rotate/click/hold together; ``feed`` picks the
# active one via ``MODES[mode_of(st)]``. Two families capture the cross-mode
# regularities so they live once, not per-mode:
#   Mode    — a modal overlay. ENC0-hold backs out (``exit``); ENC1-hold idle.
#             ``op_enc(st)`` = the encoder that operates it (rotate/click).
#   NavMode — the navigation family (chain/glance/sys/menu/sysfocus): ENC0-hold
#             zooms out one level, ENC1-hold opens the tuner. Shared by all five.
# Modes carry no state: AppState stays the single source of truth (so the
# confirm-over-sub overlay is preserved), a Mode just reads/mutates it via ``c``.
class Mode:
    def op_enc(self, st):
        return 0
    def enter(self, c):                    # deliberate entry: set the flag + init
        pass
    def on_rotate(self, c, enc, d):
        pass
    def on_click(self, c, enc):
        pass
    def on_hold(self, c, enc):             # ENC0-hold = back out of this mode
        if enc == 0:
            self.exit(c)
    def exit(self, c):
        pass


class NavMode(Mode):
    def on_hold(self, c, enc):             # ENC0 = zoom out one level, ENC1 = tuner
        st = c.st
        if enc == 0:
            if st.sys_focus:               # leave the SYS edge, up to glance (chain rule)
                st.sys_focus, st.depth = False, -1
            elif st.sys:
                st.sys = False
            elif st.menu_open:
                st.menu_open = False
            elif st.depth == 0:
                st.depth = -1
            elif st.depth == -1:
                st.depth = 0
        else:
            c.enter("tuner")


class TunerMode(Mode):
    def enter(self, c):
        c.st.tuner = True
    def on_click(self, c, enc):            # Q1: any press exits (rotate ignored)
        c.st.tuner = False
    def on_hold(self, c, enc):
        c.st.tuner = False


class ConfirmMode(Mode):
    def op_enc(self, st):                  # the encoder that opened the dialog
        return _op(st.confirm.split(":")[1])
    def enter(self, c, which):             # delete danger, No highlighted
        c.st.confirm, c.st.cyes = "del:" + which, False
    def on_rotate(self, c, enc, d):        # the opening encoder toggles No/Yes
        if enc == self.op_enc(c.st):
            c.st.cyes = not c.st.cyes
    def on_click(self, c, enc):            # opening encoder acts; the other cancels
        st = c.st
        if enc == self.op_enc(st):
            if st.cyes:
                c._confirm_exec()
            else:
                st.confirm = ""
        else:
            st.confirm = ""
    def on_hold(self, c, enc):             # Q3: operating encoder hold = cancel (= No)
        if enc == self.op_enc(c.st):
            self.exit(c)
    def exit(self, c):
        c.st.confirm = ""


class NamingMode(Mode):
    def op_enc(self, st):
        return _op(st.naming.split(":")[0])
    def enter(self, c, which, mode):       # open the name suggester (was _name_open)
        st = c.st
        # Q3: boards dial a stage term (ENC0); snaps take today's weekday from the
        # clock so naming rides ENC1 only (no categorical dial).
        ncat = 0 if which == "board" else c._day_provider() % len(DAYS)
        st.sub, st.naming, st.ncat = "", "%s:%s" % (which, mode), ncat
        c._rebuild_name(reroll=True)
    def on_rotate(self, c, enc, d):        # Q3: category=ENC0 (board only), reroll=ENC1
        st = c.st
        which = st.naming.split(":")[0]
        if which == "board" and enc == 0:  # board: ENC0 dials the stage term
            st.ncat = (st.ncat + d) % len(name_cats(which))
            c._rebuild_name(reroll=False)
        elif enc == 1:                     # ENC1 re-rolls (snap day is auto — no ENC0)
            c._rebuild_name(reroll=True)
    def on_click(self, c, enc):            # Q3: operating encoder accepts (board=E0, snap=E1)
        st = c.st
        if enc == self.op_enc(st):
            c._name_accept()
        elif enc == 1:                     # ENC1 click = re-roll (board's non-op hand)
            c._rebuild_name(reroll=True)
    def on_hold(self, c, enc):             # Q3: operating encoder hold = cancel naming
        if enc == self.op_enc(c.st):
            self.exit(c)
    def exit(self, c):
        c.st.naming = ""


class SubMode(Mode):
    def op_enc(self, st):                  # boards ride ENC0, snaps ENC1 (whoever opened)
        return _op(st.sub)
    def enter(self, c, which):
        c.st.sub, c.st.sub_idx = which, 0
    def on_rotate(self, c, enc, d):
        st = c.st
        if enc == self.op_enc(st):
            st.sub_idx = (st.sub_idx + d) % len(SUB_ACTIONS)
    def on_click(self, c, enc):            # opening encoder picks; the other backs
        st = c.st
        if enc == self.op_enc(st):
            c._sub_act(SUB_ACTIONS[st.sub_idx][1])
        else:
            st.sub = ""
    def exit(self, c):                     # ENC0-hold closes (base on_hold), regardless of op
        c.st.sub = ""


class PickMode(Mode):
    def op_enc(self, st):
        return 1                           # ENC1 operates; ENC0 dead (hold = back)
    def enter(self, c):                    # start on the category strip, top of both
        c.st.pick, c.st.pick_cat, c.st.pick_fx = "cat", 0, 0
    def on_rotate(self, c, enc, d):        # ENC1 turns the active strip
        st = c.st
        if enc == 1:
            if st.pick == "cat":
                st.pick_cat = (st.pick_cat + d) % len(st.wl)
            else:
                st.pick_fx = (st.pick_fx + d) % len(st.wl[st.pick_cat]["plugins"])
    def on_click(self, c, enc):            # ENC1 click = select / place
        st = c.st
        if enc == 1:
            if st.pick == "cat":
                st.pick, st.pick_fx = "fx", 0
            else:
                plug = st.wl[st.pick_cat]["plugins"][st.pick_fx]   # for the toast
                if st.ins_at >= 0:             # net-new: splice at the chosen index
                    at = min(st.ins_at, len(st.board))
                    c.backend.insert(at, st.pick_cat, st.pick_fx)
                    c._sync_board()
                    st.node, st.add = at, ""   # land on the new node (leaves any [+] cell)
                    st.pick, st.knob, st.dirty, st.ins_at = "", 0, True, -1
                    c._toast(plug["display"] + " inserted")
                else:                          # replace the focused node in place
                    c.backend.place(st.node, st.pick_cat, st.pick_fx)
                    c._sync_board()
                    st.pick, st.knob, st.dirty = "", 0, True
                    c._toast(plug["display"] + " placed")
    def exit(self, c):                     # ENC0-hold = back one strip (base on_hold)
        c.st.pick = "cat" if c.st.pick == "fx" else ""
        if not c.st.pick:                  # fully backed out of the picker -> cancel insert
            c.st.ins_at = -1               # (st.add survives: back to the [+] cell we came from)


class MovingMode(Mode):
    def enter(self, c):                    # pick this node up; remember where it was
        c.st.moving, c.st.move_from = True, c.st.node
    def on_rotate(self, c, enc, d):        # ENC0 swaps the picked-up node with a neighbour
        st = c.st
        if enc == 0:
            j = st.node + d
            if 0 <= j < len(st.board):
                c.backend.move(st.node, j)
                c._sync_board()
                st.node = j
    def on_click(self, c, enc):            # ENC0 click = drop here (commit)
        st = c.st
        if enc == 0:
            st.moving, st.dirty = False, True
            c._toast("MOVED")
    def exit(self, c):                     # ENC0-hold = cancel move, restore position
        st = c.st
        c.backend.move(st.node, st.move_from)
        c._sync_board()
        st.node, st.moving = st.move_from, False


class SysMode(NavMode):
    def enter(self, c):
        c.st.sys, c.st.sys_idx = True, 0
    def on_rotate(self, c, enc, d):        # Q4: ENC0-only (matches other modals)
        st = c.st
        if enc == 0:
            st.sys_idx = (st.sys_idx + d) % len(SYSITEMS)
    def on_click(self, c, enc):
        st = c.st
        if enc == 0:
            c._sys_act()
        else:
            st.sys = False


class MenuMode(NavMode):
    def enter(self, c):
        c.st.menu_open, c.st.menu = True, 0
    def on_rotate(self, c, enc, d):        # Q4: ENC0-only (ENC0 also commits)
        st = c.st
        if enc == 0:
            st.menu = (st.menu + d) % len(menu_items(st))
    def on_click(self, c, enc):
        st = c.st
        if enc == 1:
            st.menu_open = False
        else:
            c._menu_act(menu_items(st)[st.menu][2])


class GlanceMode(NavMode):
    def on_rotate(self, c, enc, d):
        st = c.st
        if enc == 0:
            st.pb = (st.pb + d) % len(st.boards)
        elif st.pb == st.pb_cur:           # snap list is the loaded board's -> inert when off it
            st.snap = (st.snap + d) % len(st.snaps)
    def on_click(self, c, enc):            # 2-step: first click loads, re-click manages
        st = c.st
        if enc == 1 and st.pb != st.pb_cur:   # snapshot hand is dead until the board is loaded
            return
        which = "board" if enc == 0 else "snap"
        hi, cur = (st.pb, st.pb_cur) if enc == 0 else (st.snap, st.snap_cur)
        if hi != cur:                      # highlight isn't the loaded one -> load it
            c._select(which)
        else:                              # already loaded -> open its manage submenu
            c.enter("sub", which=which)


class SysFocusMode(NavMode):
    def on_rotate(self, c, enc, d):        # parked at SYS entry: only ENC0-right returns
        st = c.st
        if enc == 0 and d > 0:             # roll back onto the chain (left = wall)
            st.sys_focus, st.node = False, 0
    def on_click(self, c, enc):            # ENC0 click = commit: enter SYSTEM (guard)
        if enc == 0:
            c.st.sys_focus = False
            c.enter("sys")


class ChainMode(NavMode):
    def on_rotate(self, c, enc, d):
        st = c.st
        if enc == 0:
            nn = st.node + d
            if nn < 0:                     # off the left end of the nodes -> the head [+]
                st.add, st.knob = "head", 0
            elif nn >= len(st.board):      # off the right end -> the tail [+] (before OUT)
                st.add, st.knob = "tail", 0
            else:
                st.node, st.knob = nn, 0
        else:
            n = c._cur()
            if st.locked:
                c.adjust(d)
            elif n["knobs"]:
                st.knob = (st.knob + d) % len(n["knobs"])
    def on_click(self, c, enc):
        st = c.st
        if enc == 0:
            c.enter("menu")
        elif c._cur()["knobs"]:
            st.locked = not st.locked


class AddMode(NavMode):
    """Parked on a [+] cell: the chain's add affordance (and the ONLY thing an
    empty chain shows). ENC0 click opens the picker to splice a net-new node at
    this end; rotating rolls back onto the chain — or, past the head, on to the
    SYS park (decision M's edge detent, now one cell further left)."""
    def on_rotate(self, c, enc, d):
        st = c.st
        if enc != 0:
            return
        if st.add == "tail":
            if d < 0:                      # back onto the last node (right = wall)
                st.add, st.node, st.knob = "", len(st.board) - 1, 0
            return
        if d > 0:                          # head: roll right onto node 0 (none if empty)
            if st.board:
                st.add, st.node, st.knob = "", 0, 0
        else:                              # head, further left -> park at SYS (guard, not enter)
            st.sys_focus, st.add = True, ""
    def on_click(self, c, enc):
        st = c.st
        if enc == 0:                       # commit: pick an FX to splice at this end
            st.ins_at = 0 if st.add != "tail" else len(st.board)
            c.enter("pick")


MODES = {
    "tuner": TunerMode(), "confirm": ConfirmMode(), "naming": NamingMode(),
    "sub": SubMode(), "pick": PickMode(), "sys": SysMode(), "menu": MenuMode(),
    "glance": GlanceMode(), "sysfocus": SysFocusMode(), "moving": MovingMode(),
    "adding": AddMode(), "chain": ChainMode(),
}


# ========================= VIEW (state -> frame) =========================
def render(st):
    """Draw the state's frame, then overlay the left-edge encoder rail."""
    img = _frame(st)
    _rail(ImageDraw.Draw(img), *rails(st), _rail_split(st))
    return img


# ---- left-edge encoder rail indicator (design: "Encoder Rail Indicator") ----
# 3px left edge split into ENC0 (top) / ENC1 (bottom), mirroring the physical
# encoder stack so the rail "points back" at the knob. Static per state (redraw
# only on change → 0 refresh cost). Mono: colour is the RGB LED's job; the rail
# carries what colour can't — "which hand is live" + list position.
RAIL_W = 3


def _rail_split(st):
    """The y of the rail's centre gap = the screen's content divider, so each
    zone sits beside the content its encoder drives. Chain maps ENC0->node strip
    (top) / ENC1->knobs (bottom) at ~3:7; glance splits at its own rule; modals
    don't map encoders to top/bottom regions so they stay ~1:1."""
    if mode_of(st) in ("tuner", "confirm", "naming", "sub", "pick", "sys",
                       "menu", "sysfocus"):
        return 64                            # ~1:1: no top/bottom encoder mapping
    if st.depth == -1:
        return 56                            # glance: pedalboard / snapshot divider
    return 40                                # chain / moving: node strip / knobs (~3:7)


def _rail_zone(d, z, zy, zh):
    if not z or z == "off":                  # dead hand: black
        return
    if z == "solid":                         # dedicated (value / single action): full on
        d.rectangle([0, zy, RAIL_W - 1, zy + zh - 1], fill=1)
        return
    for y in range(zy, zy + zh, 3):          # idle/list track: 1:2 horizontal dither
        d.rectangle([0, y, RAIL_W - 1, y], fill=1)
    if isinstance(z, tuple):                 # list: bright thumb at scroll position
        pos, total = z
        th = min(zh, max(8, zh // max(1, total)))
        ty = zy + (round((zh - th) * pos / (total - 1)) if total > 1 else 0)
        d.rectangle([0, ty, RAIL_W - 1, ty + th - 1], fill=1)


def _rail(d, z0, z1, split):
    _rail_zone(d, z0, 2, split - 5)          # top zone: y2 .. split-3
    _rail_zone(d, z1, split + 3, 123 - split)  # bottom zone: split+3 .. y125


def rails(st):
    """(ENC0, ENC1) rail zones. Each: 'off' | 'idle' | 'solid' | (pos, total).
    'solid'=dedicated engagement · tuple=scrollable list (thumb) · 'idle'=usable
    but secondary · 'off'=dead hand. Danger(red) stays the LED's job, not the rail."""
    m = mode_of(st)
    if m == "tuner":
        return ("solid", "off")              # E0 live = E0-hold exits (back rule, Q1)
    if m == "confirm":
        return ("solid", "off") if _op(st.confirm.split(":")[1]) == 0 else ("off", "solid")
    if m == "naming":
        if st.naming.split(":")[0] == "board":
            return ((st.ncat, len(TERMS)), "idle")   # E0 dials term, E1 rerolls
        return ("off", "solid")              # snap: day auto -> E1-only dedicated (Q3)
    if m == "sub":
        z = (st.sub_idx, len(SUB_ACTIONS))
        return (z, "idle") if _op(st.sub) == 0 else ("idle", z)
    if m == "pick":
        z = (st.pick_cat, len(st.wl)) if st.pick == "cat" \
            else (st.pick_fx, len(st.wl[st.pick_cat]["plugins"]))
        return ("off", z)                    # E0 dead (hold=back), E1 operates
    if m == "sys":
        return ((st.sys_idx, len(SYSITEMS)), "idle")
    if m == "menu":
        return ((st.menu, len(menu_items(st))), "idle")
    if m == "glance":                        # E0 boards; E1 snapshots — but the snap list
        # belongs to the LOADED board, so it goes dead while the highlight is off it.
        z1 = (st.snap, len(st.snaps)) if st.pb == st.pb_cur else "off"
        return ((st.pb, len(st.boards)), z1)
    if m == "sysfocus":                      # parked at SYS entry: E0 live (click to enter)
        return ("solid", "off")
    if m == "moving":                        # E0 shifts the picked-up node
        return ("solid", "off")
    if m == "adding":                        # parked on a [+]: E0 still walks the chain axis
        return ((cpos(st), len(cells(st))), "off")   # E1 dead — no node under the cursor
    n = st.board[st.node]                    # chain home
    if st.locked:                            # E1 owns one value: no list to place
        z1 = "solid"
    elif not n["knobs"]:
        z1 = "off"
    else:                                    # browsing knobs IS a list — and once the
        z1 = (st.knob, len(n["knobs"]))      # grid scrolls, the thumb is the only cue
    return ((cpos(st), len(cells(st))), z1)  # E0 axis = the strip: [+] head, nodes, [+] tail


def _frame(st):
    m = mode_of(st)
    if m == "tuner":
        return _tuner(st)
    if m == "confirm":
        return _confirm(st)
    if m == "naming":
        return _naming(st)
    if m == "sub":
        return _sub(st)
    if m == "pick":
        return _pick(st)
    if m == "sys":
        return _sys(st)
    if m == "menu":
        return _menu(st)
    if m == "glance":
        return _glance(st)
    if m == "sysfocus":
        return _sys_focus(st)
    return _chain(st)                         # chain / moving


def _toast_over(s, st):
    if not st.toast:
        return
    s.box(6, 50, 116, 22, fill=True)
    s.T(st.toast, 64 - int(s.Tw(8, st.toast) / 2), 56, 8, fill=0)


def _chain(st):
    s = Screen()
    s.T("IN", 5, 1, 8)                          # +3px: clear the left rail
    s.T("-14.2", 18, 1, 8)
    s.T("OUT", 54, 1, 8)
    s.T("-4.3", 74, 1, 8)
    adding = mode_of(st) == "adding"
    s.T("+/%d" % len(st.board) if adding
        else "%d/%d" % (st.node + 1, len(st.board)), 101, 1, 6)
    if st.dirty:
        s.d.ellipse([121, 2, 126, 7], fill=1)
    step, cw, ty, ch = 25, 23, 13, 24
    wy = ty + ch // 2
    if st.moving:                              # carrying a node: the [+] cells aren't drop
        axis, fp = list(range(len(st.board))), st.node   # targets, so don't show them
    else:
        axis, fp = cells(st), cpos(st)
    start = _window(len(axis), fp, 5)
    drawn = []
    for j in range(min(5, len(axis) - start)):
        p = start + j
        cell = axis[p]
        x = 5 + j * step                       # +3px: node strip clears the left rail
        drawn.append((p, x, x + cw - 1))
        sel = p == fp
        if cell in ("head", "tail"):           # the [+] pseudo-cells: add an FX here
            cy = ty
            if sel:
                s.box(x, cy, cw, ch, fill=True)
                s.T("+", x + 8, cy + 7, 12, fill=0)
            else:
                s.dashed(x, cy, cw, ch, on=2, off=2)
                s.T("+", x + 8, cy + 7, 12)
            continue
        n = st.board[cell]
        cy = ty - 5 if (st.moving and sel) else ty   # lift the picked-up node
        if sel:
            s.box(x, cy, cw, ch, fill=True)
            s.T(n["abbr"], x + 3, cy + 9, 12, fill=0)
        elif n["bypass"]:
            s.dashed(x, cy, cw, ch, on=1, off=2)
            s.T(n["abbr"], x + 3, cy + 9, 12)
        else:
            s.box(x, cy, cw, ch)
            s.T(n["abbr"], x + 3, cy + 9, 12)
    for a in range(len(drawn) - 1):
        if drawn[a + 1][1] - 1 >= drawn[a][2] + 1:
            s.d.rectangle([drawn[a][2] + 1, wy, drawn[a + 1][1] - 1, wy], fill=1)
    if drawn:
        if drawn[0][0] > 0:
            s.d.rectangle([0, wy, drawn[0][1] - 1, wy], fill=1)
        if drawn[-1][0] < len(axis) - 1:
            s.d.rectangle([drawn[-1][2] + 1, wy, WIDTH - 1, wy], fill=1)
    if fp == 0 and not st.moving:              # Q2: SYSTEM is one scroll-left past the head
        s.T("<SYS", 5, 15, 8)
    s.hline(0, 40, 128)
    if adding:                                 # parked on a [+]: no node to show below
        head = st.add != "tail"
        s.T("ADD FX", 4, 45, 16)
        s.T("at the %s of the chain" % ("head" if head else "tail"), 4, 68, 8)
        s.T("(empty chain)" if not st.board else
            ("before %s" % st.board[0]["abbr"] if head else "after %s" % st.board[-1]["abbr"]),
            4, 80, 8)
        s.T("e0 click = pick FX", 4, 100, 8)
        s.T("e0 hold = glance", 4, 112, 8)
        _toast_over(s, st)
        return s.img
    n = st.board[st.node]
    if st.moving:                              # move mode: instructions in place of knobs
        s.T("MOVING", 4, 45, 16)
        s.T(n["name"], 4, 66, 8)
        s.T("SLOT %d/%d" % (st.node + 1, len(st.board)), 4, 78, 8)
        s.T("e0 turn = shift", 4, 96, 8)
        s.T("click drop  hold cancel", 4, 108, 8)
        _toast_over(s, st)
        return s.img
    _marq(s, n["name"], 5, 43, 16, 92, phase(st))     # box stops short of the abbr at x=100
    s.T("BYP" if n["bypass"] else n["abbr"], 100, 45, 8)
    rows = knob_rows(n["knobs"])
    top = _window(len(rows), row_of(rows, st.knob), KROWS)   # scroll by rows, no new state
    for r in range(top, min(len(rows), top + KROWS)):
        yy = KBASE + (r - top) * KH
        wide = _is_patch(n["knobs"], rows[r])
        for col, i in enumerate(rows[r]):
            kb = n["knobs"][i]
            x, w = (KX[0], KWFULL) if wide else (KX[col], KWHALF)
            on = i == st.knob
            if on:
                if st.locked:
                    s.box(x - 3, yy - 2, w, KH - 1)
                else:
                    s.dashed(x - 3, yy - 2, w, KH - 1, on=2, off=2)
            vt = 6 if wide else 8                         # patch values are long: Micro5 tier
            if on:                                        # only the focused cell animates
                _marq(s, kb["n"], x, yy, 8, w - 4, phase(st))
                _marq(s, fmt(kb), x, yy + 8, vt, w - 4, phase(st))
            else:
                s.T(_fit(s, kb["n"], 8, w - 4), x, yy, 8)
                s.T(_fit(s, fmt(kb), vt, w - 4), x, yy + 8, vt)
            if kb["k"] == "dial":
                s.gbar(x, yy + 17, w - 8, 3, norm(kb))
    _toast_over(s, st)
    return s.img


def _sys_focus(st):
    """Parked at the chain's left edge: SYS entry focused but NOT entered (guard).
    A fast spin stops here; only E0 click commits into the SYSTEM menu."""
    s = Screen()
    s.T("CHAIN EDGE", 6, 4, 8, ls=1)
    s.hline(0, 16, 128)
    s.chip("< SYSTEM", 8, 34, 112, 26, 16)     # the pending entry, highlighted
    s.T("e0 click  = enter", 8, 74, 8)
    s.T("e0 turn > = chain", 8, 90, 8)
    s.T("e0 hold   = glance", 8, 106, 8)
    _toast_over(s, st)
    return s.img


def _glance(st):
    s = Screen()
    on_pb = st.pb == st.pb_cur                          # highlight == the loaded board?
    on_snap = on_pb and st.snap == st.snap_cur
    s.T("PEDALBOARD", 8, 5, 8, ls=1)
    _marq(s, st.boards[st.pb], 8, 14, 24, 112, phase(st))    # 24px fits ~6 chars: always scrolls
    if on_pb:
        s.d.rectangle([121, 26, 125, 30], fill=1)       # this board is loaded on the host
    s.hline(0, 56, 128)                                 # position: left rail thumbs (dots removed)
    s.T("SNAPSHOT", 8, 62, 8, ls=1)
    if on_pb:                                           # snap list belongs to the loaded board
        # 16px, not 24: at the board's tier this line marquees too, and *two*
        # 24px names scrolling at once cost more than everything else the app
        # animates put together (7.0ms/tick, a quarter of the bus — measured,
        # tools/oled_bench.py). Dropping a tier fits the common names outright
        # (they stop scrolling), halves the band when a long one doesn't, and
        # says the true thing anyway: the board is the subject, the snapshot
        # its qualifier.
        _marq(s, st.snaps[st.snap], 8, 74, 16, 112, phase(st))
        if on_snap:
            s.d.rectangle([121, 83, 125, 87], fill=1)
    else:                                               # highlight is off the loaded board -> stale
        s.T("— load board first —", 8, 76, 12)
    s.T("e0 %s  e1 %s" % ("manage" if on_pb else "LOAD",
                          ("manage" if on_snap else "LOAD") if on_pb else "--"), 5, 118, 6)
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
    s.box(4, 0, 36, 128)                        # +4px: info panel clears the left rail
    s.T(n["abbr"], 6, 40, 16)
    s.T(n["name"], 6, 62, 8)
    s.T("SLOT %d/%d" % (st.node + 1, len(st.board)), 6, 76, 6)
    s.T("BYP" if n["bypass"] else "ON", 6, 88, 6)
    s.T("ACTION", 46, 5, 8, ls=1)
    items = menu_items(st)
    y0, rh = 13, 16                              # 7 rows now (Add Before/After): 13+7*16 = 125
    for i, (ic, label, _) in enumerate(items):
        y = y0 + i * rh
        row = _fit(s, ic + " " + label, 8, 76)   # the row box is x=44..127
        if i == st.menu:
            s.box(44, y - 1, 84, rh - 2, fill=True)
            s.T(row, 48, y + 1, 8, fill=0)
        else:
            s.T(row, 48, y + 1, 8)
    _toast_over(s, st)
    return s.img


def _fit(s, txt, size, maxw):
    """Truncate txt so it fits maxw px at the given tier."""
    if s.Tw(size, txt) <= maxw:
        return txt
    while txt and s.Tw(size, txt) > maxw:
        txt = txt[:-1]
    return txt


# ---- marquee: the long-name answer (roadmap ③) ------------------------------
# 128px can't hold the names we actually have — board names truncate 100% of the
# time, node names 75% (measured; see roadmap). A name that reads "NAM LOA" or
# "CompAmpCabE" is worse than useless, so the *focused* line scrolls instead.
#
# Purity: the phase is a function of ``st.t``, a clock the runtime loop writes
# into the state before each draw (decision Q). The view stays f(st) and the
# controller stays time-blind; --walk/goldens leave t=0, where offset == 0 and
# the frame is identical to today's head-truncated one.
#
# Discipline (design.md §2): only the line the user is *on* animates — one page
# band, which is exactly what the future diff driver will have to push. Static
# context keeps its plain trunc.
MARQ_DWELL = 1.1      # s held at each end (time to actually read the head/tail)
MARQ_SPEED = 24.0     # px/s scroll — slow enough to read at 8px tiers


def phase(st):
    """Marquee phase: time since the last input, not since boot. Landing on a new
    board mid-scroll and reading it from the middle is worse than not scrolling —
    every gesture rewinds every name to its head (st.t_mark, set in feed())."""
    return st.t - st.t_mark


def _marq(s, txt, x, y, size, maxw, t, fill=1, bg=0):
    """Draw txt in a maxw box: static if it fits, else dwell-scroll-dwell on t."""
    over = s.Tw(size, txt) - maxw
    if over <= 0:
        s.T(txt, x, y, size, fill=fill)
        return
    travel = over / MARQ_SPEED
    p = t % (2 * MARQ_DWELL + travel)                 # t=0 -> p=0 -> off=0 (head)
    off = 0 if p < MARQ_DWELL else \
        over if p >= MARQ_DWELL + travel else (p - MARQ_DWELL) * MARQ_SPEED
    s.Tclip(txt, x, y, size, maxw, off=round(off), fill=fill, bg=bg)


def _window(n, sel, vis):
    return 0 if n <= vis else max(0, min(sel - vis // 2, n - vis))


# ---- knob grid: row packing (a patch takes the full width) -------------------
# The chain's bottom band is a 2-col grid, KROWS rows tall. A patch knob (k="file"
# — a NAM model, a cab IR) carries a *filename*, which no half cell can hold (7
# chars), so it claims a whole row: 2x1, ~30 chars at the Micro5 tier. The adapter
# emits patches first, so they land on top naturally. Rows past KROWS scroll —
# the window is derived from st.knob, so the view stays a pure f(st).
KX, KBASE, KH, KROWS = [8, 67], 62, 21, 3   # col0 +3px so its focus ring clears the rail
KWHALF, KWFULL = 56, 115                    # cell widths (ring-inclusive; both end at x=119)


def knob_rows(knobs):
    """Pack knob indices into rows: a patch owns its row, the rest pair up."""
    rows, pair = [], []
    for i, kb in enumerate(knobs):
        if kb["k"] == "file":
            if pair:
                rows.append(pair)
                pair = []
            rows.append([i])
            continue
        pair.append(i)
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    return rows


def row_of(rows, knob):
    for r, row in enumerate(rows):
        if knob in row:
            return r
    return 0


def _is_patch(knobs, row):
    return len(row) == 1 and knobs[row[0]]["k"] == "file"


def _striplist(s, items, sel, x, w, y0, active, size=8, vis=5, rh=14, t=0.0):
    """Windowed list inside [x, x+w). Focus ring = filled; locked = hollow.
    Scroll carets are drawn by the caller (in the gaps) so text keeps full width.
    The selected row of the *active* strip marquees (inverted); the rest trunc."""
    n = len(items)
    pad = max(1, (rh - 2 - round(fs(size) * 0.72)) // 2)   # center ink in the row
    start = _window(n, sel, vis)
    for r in range(min(vis, n)):
        i = start + r
        y = y0 + r * rh
        if i == sel and active:
            s.box(x, y - 1, w, rh - 2, fill=True)
            _marq(s, items[i], x + 3, y + pad, size, w - 6, t, fill=0, bg=1)
            continue
        lbl = _fit(s, items[i], size, w - 6)
        if i == sel:                            # inactive strip: hollow marker
            s.box(x, y - 1, w, rh - 2)
        s.T(lbl, x + 3, y + pad, size)


def _pick_chain(s, st):
    """Top band: the chain AS IT WILL BE — the pending FX shown in place. Insert
    splices a new cell in (the chain grows under it); replace swaps the focused
    one. Either way the dashed cell is exactly where the plugin will land."""
    ins = st.ins_at >= 0
    s.T("INSERT" if ins else "REPLACE", 4, 1, 8, ls=1)
    s.T(_fit(s, st.wl[st.pick_cat]["key"], 8, 46), 56, 1, 8)
    pend = st.wl[st.pick_cat]["abbr"]
    at = min(st.ins_at, len(st.board)) if ins else st.node
    strip = [n["abbr"] for n in st.board]
    if ins:
        strip.insert(at, pend)
    else:
        strip[at] = pend
    s.T("SL%d" % (at + 1), 106, 2, 6)
    step, cw, ty, ch = 25, 23, 12, 20
    wy = ty + ch // 2
    drawn = []
    start = _window(len(strip), at, 5)
    for j in range(min(5, len(strip) - start)):
        idx = start + j
        x = 2 + j * step
        drawn.append((idx, x, x + cw - 1))
        if idx == at:                           # the pending FX, where it will land
            s.dashed(x, ty, cw, ch, on=2, off=2)
            s.T(pend, x + 3, ty + 7, 12)
        else:
            s.box(x, ty, cw, ch)
            s.T(strip[idx], x + 3, ty + 7, 12)
    for a in range(len(drawn) - 1):
        if drawn[a + 1][1] - 1 >= drawn[a][2] + 1:
            s.d.rectangle([drawn[a][2] + 1, wy, drawn[a + 1][1] - 1, wy], fill=1)
    if drawn:
        if drawn[0][0] > 0:
            s.d.rectangle([0, wy, drawn[0][1] - 1, wy], fill=1)
        if drawn[-1][0] < len(strip) - 1:
            s.d.rectangle([drawn[-1][2] + 1, wy, WIDTH - 1, wy], fill=1)


def _pick(st):
    s = Screen()
    _pick_chain(s, st)
    s.hline(0, 38, 128)
    by = 44
    on_cat = st.pick == "cat"
    # left strip: category abbrs, big font (matches node-strip abbrs), 4 rows
    cats = [b["abbr"] for b in st.wl]
    _striplist(s, cats, st.pick_cat, 5, 44, by, active=on_cat, size=16, vis=4, rh=17, t=phase(st))  # +5px: rail
    s.d.rectangle([49, by - 2, 49, 115], fill=1)
    # right strip: plugins of the hovered/locked category (preview until locked)
    plugs = [p["display"] for p in st.wl[st.pick_cat]["plugins"]]
    _striplist(s, plugs, -1 if on_cat else st.pick_fx, 51, 77, by, active=not on_cat, size=8, t=phase(st))
    # scroll position is carried by the left rail thumb now (carets removed)
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
    m = mode_of(st)
    n = st.board[st.node] if st.board else None   # no node under the cursor on an empty chain
    if m == "tuner":
        return ("purple", "purple")
    if m == "confirm":                        # delete danger on the operating encoder
        return ("red", OFF) if _op(st.confirm.split(":")[1]) == 0 else (OFF, "red")
    if m == "naming":                         # Q3: board=E0 term/accept+E1 reroll; snap=E1-only
        return ("green", "blue") if st.naming.split(":")[0] == "board" else (OFF, "green")
    if m == "sub":                            # manage submenu on the opening encoder
        return ("blue", OFF) if _op(st.sub) == 0 else (OFF, "blue")
    if m == "pick":                           # ENC0=back(grey), ENC1=operate(cat colour)
        return ("grey", BUCKETCOL.get(st.wl[st.pick_cat]["key"], "amber"))
    if m == "moving":                         # ENC0 holds the node; ENC1 idle
        return (BUCKETCOL.get(n["bucket"], "amber"), OFF)
    if m == "sysfocus":                       # parked at SYS entry (edge detent)
        return ("grey", OFF)
    if m == "sys":
        return ("grey", OFF)
    if m == "glance":
        return ("blue", "green")
    if m == "adding":                          # [+] cell: E0 commits (amber = the add action)
        return ("amber", OFF)
    l0 = "red" if n["bypass"] else BUCKETCOL.get(n["bucket"], "grey")   # menu / chain
    l1 = OFF
    if m == "menu":                           # Q5: danger(red) rides ENC0 (the commit hand)
        if menu_items(st)[st.menu][2] == "remove":
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
    do("t", "board>")      # enc0 CW: highlight the next board (now != loaded)
    do("w", "board-load")  # enc0 click: highlight != loaded -> LOAD it onto the host
    print("      loaded  pb=%d(%s) pb_cur=%d" % (c.st.pb, c.st.boards[c.st.pb], c.st.pb_cur))
    do("g", "snap>")       # enc1 CW: snapshot scroll
    do("x", "combo")       # save snapshot (toast)
    do("e", "hold-down")   # back to depth 0
    do("rrr", "to-node0")  # enc0 CCW: node 3 -> 0
    do("r", "add-head")    # one more left -> the head [+] cell (add at the front)
    do("r", "sys-focus")   # one more left past THAT -> PARK at SYS entry (guard, not enter)
    do("w", "sys-enter")   # enc0 click: commit -> SYSTEM menu opens
    do("w", "sys-exec")    # enc0 click: SYSTEM item 0 = Tuner -> tuner
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
    # insert (net-new): the side is chosen explicitly — Insert Before / Insert After
    print("      chain   %s (len %d)" % ([b["abbr"] for b in c.st.board], len(c.st.board)))
    do("w", "menu-ins")    # slot menu on node 0
    do("ttt", "to-insB")   # menu 0 -> 3 (Bypass/Move/Replace/InsBefore/InsAfter/Remove/Back)
    do("w", "insB-pick")   # exec Insert Before -> picker (ins_at = node)
    do("s", "insB-fx")     # enc1 click: cat -> plugin strip
    do("s", "insB-add")    # enc1 click: splice BEFORE node 0 -> lands at index 0
    print("      chain   %s (len %d) focus=%d" % ([b["abbr"] for b in c.st.board], len(c.st.board), c.st.node))
    do("w", "menu-ins2")   # slot menu on the new node 0
    do("tttt", "to-insA")  # menu 0 -> 4 (Insert After)
    do("w", "insA-pick")   # exec Insert After -> picker (ins_at = node + 1)
    do("s", "insA-fx")
    do("s", "insA-add")    # splices at index 1
    print("      chain   %s (len %d) focus=%d" % ([b["abbr"] for b in c.st.board], len(c.st.board), c.st.node))
    # the tail [+]: scroll off the right end of the chain and add there
    do("t" * (len(c.st.board) - c.st.node), "add-tail")   # past the last node -> tail [+]
    do("w", "tail-pick")   # enc0 click: picker (ins_at = len(board) — appends)
    do("s", "tail-fx")
    do("s", "tail-add")    # splices at the end, before OUT
    print("      chain   %s (len %d) focus=%d" % ([b["abbr"] for b in c.st.board], len(c.st.board), c.st.node))
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
    # snapshot manage is operated by ENC1 (the encoder that opened it). The board
    # load above re-homed the snap cursor onto the loaded board, so scroll off it
    # first: then the 2-step shows — first click LOADS, a second click (highlight ==
    # loaded) opens the manage submenu.
    do("g", "snap>")       # enc1 CW: highlight the next snapshot (now != loaded)
    do("s", "snap-load")   # enc1 click: highlight != loaded -> LOAD snapshot
    do("s", "snap-sub")    # enc1 click: now loaded -> open SNAP manage submenu (E1 operates)
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
    n = st.board[st.node] if st.board else None
    kv = fmt(n["knobs"][st.knob]) if n and n["knobs"] else "--"
    return ("d=%d node=%d(%s) k=%d[%s] add=%s ins=%d dirty=%d menu=%d pick=%s mv=%d sub=%s name=%s "
            "conf=%s sysf=%d sys=%d tun=%d pb=%d(%s) snap=%d toast=%r"
            % (st.depth, st.node, (n["abbr"] if n else "--") or "--", st.knob, kv,
               st.add or "-", st.ins_at, st.dirty,
               st.menu_open, st.pick or "-", st.moving, st.sub or "-", st.naming or "-",
               st.confirm or "-", st.sys_focus, st.sys, st.tuner, st.pb, st.boards[st.pb], st.snap, st.toast))


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


class _FakePanel:
    """Records the panel-power commands instead of sending them (for --sleeptest)."""

    def __init__(self):
        self.log = []

    def contrast(self, level):
        self.log.append("contrast(0x%02X)" % level)

    def hide(self):
        self.log.append("hide")

    def show(self):
        self.log.append("show")


def _sleeptest():
    """Burn-in defence under a fake clock — the one thing we can't test by waiting.

    Living through it takes five minutes and a pair of eyes, and eyes cannot see
    "no bytes went out". So run the real PanelPower through the real Runtime with
    time as a variable, and check the four things that matter: it dims on
    schedule, it blanks on schedule, a blank panel stops being drawn into, and
    the first input off a blank panel wakes it *without* editing anything.
    """
    from ganglion.runtime import Runtime
    from ganglion.hw.oled import PanelPower
    from ganglion.input import KeyboardInput
    clk = [0.0]
    panel = _FakePanel()
    c = AppController()
    src = _ScriptSource(KeyboardInput(), [])            # silence: nobody touches it
    rt = Runtime(c, src, _CaptureSink(), render, leds=leds, tick_s=1.0,
                 power=PanelPower(panel, dim_s=30.0, off_s=300.0),
                 clock=lambda: clk[0], sleep=lambda dt: clk.__setitem__(0, clk[0] + dt))
    marks, ok = {}, True
    for _ in range(302):                                # 1s ticks: 0 -> 301
        now, was = clk[0], rt.power.state
        rt.step()
        if rt.power.state != was:
            marks[rt.power.state] = now
    for want, at in (("dim", 30.0), ("off", 300.0)):
        hit = marks.get(want)
        ok &= hit == at
        print("%-4s at %-6s (want %ss)  %s"
              % (want, hit, at, "OK" if hit == at else "FAIL"))

    frames = rt.sink.frames                             # a dark panel gets nothing
    for _ in range(10):
        rt.step()
    ok &= rt.sink.frames == frames
    print("blank: frames %d -> %d over 10 ticks  %s"
          % (frames, rt.sink.frames, "OK" if rt.sink.frames == frames else "FAIL"))

    src.chars, node = ["t"], c.st.node                  # 't' would nav if it landed
    rt.step()
    woke = rt.power.state == "on" and c.st.node == node and rt.sink.frames > frames
    ok &= woke
    print("wake:  state=%s node=%d->%d (swallowed) frames=%d  %s"
          % (rt.power.state, node, c.st.node, rt.sink.frames, "OK" if woke else "FAIL"))

    want = ["contrast(0x01)", "hide", "show", "contrast(0x7F)"]
    ok &= panel.log == want                             # edge-only: 313 ticks, 4 cmds
    print("panel: %s  %s" % (panel.log, "EDGE-ONLY-OK" if panel.log == want else
                             "FAIL want=%s" % want))
    print("SLEEPTEST", "PASS" if ok else "FAIL")


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
    if "--sleeptest" in argv:
        _sleeptest()
        return
    from ganglion.runtime import run_terminal
    if "--live" in argv:                       # inject the live synapse backend
        from ganglion.geco_adapter import GecoAdapter
        c = AppController(backend=GecoAdapter())
    else:
        c = AppController()

    def hud():
        return ["r/t e0  f/g e1", "w/s click  e/d hold  x combo", "Q quit",
                "", _snap(c.st)[:40], "leds " + str(leds(c.st))]

    if "--device" in argv:
        from ganglion.runtime import run_device
        run_device(c, render, leds)
        return
    if "--encoders" in argv:                     # real knobs in, terminal out (no OLED yet)
        from ganglion.runtime import run_encoders_terminal

        def ehud():
            return ["ENC0 turn/click/hold", "ENC1 turn/click/hold", "Ctrl-C quit",
                    "", _snap(c.st)[:40], "leds " + str(leds(c.st))]

        run_encoders_terminal(c, render, leds=leds, hud=ehud)
        return
    run_terminal(c, render, leds=leds, hud=hud)


if __name__ == "__main__":
    main(sys.argv[1:])
