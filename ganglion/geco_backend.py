"""GECO backend seam — decouples the app (controller / modes / view) from where
the pedalboard, plugin catalog, and persistence actually live.

Same pattern as synapse's ``backend.py``: an abstract surface with documented
contracts that the app depends on exclusively. A dev entry injects ``FakeGeco``
(in-memory fixtures, no host); a live entry will inject an adapter over synapse's
model / modepctrl / pedalboard-editor. The swap is wiring only — the controller
never names a concrete backend.

Data contracts (the shapes the app renders):
  node   = {"name","abbr","bucket","bypass","knobs":[knob]}
  knob   = {"n","v","mn","mx","u","k","scale"}   # k in dial/toggle/enum/file
  bucket = {"key","abbr","plugins":[{"display","name","uri","brand","alias"}]}

Method contracts:
  - Reads return a fresh copy the app may cache and render; the backend stays the
    source of truth (mutations only via the methods below).
  - The chain is a VARIABLE-length list of effects — no slots, no holes (this
    mirrors the live graph: ``remove`` shortens the chain, ``insert`` splices).
    An empty chain (0 nodes) is legal; the app draws its head ``[+]`` cell.
    ``move`` reorders. Reordering/placement is an EDITOR-level concern: the live
    adapter must port synapse's pedalboard-editor routing (out->in re-wire +
    graph refresh), not just call a host primitive.
  - Mutations return ``None`` on success or an error string (mirrors synapse
    backend); ``save_as``/``delete`` return the affected list index.
"""

import copy
import json
import os


# ---- knob + node factories (port of the mockup's K / _node / makeBoard) -----
def K(n, v, mn, mx, u="", k="dial", scale=None):
    return {"n": n, "v": v, "mn": mn, "mx": mx, "u": u, "k": k, "scale": scale}


def _node(name, abbr, bucket, bypass, knobs):
    return {"name": name, "abbr": abbr, "bucket": bucket, "bypass": bypass,
            "knobs": knobs}


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


# ---- plugin whitelist + node factory (port of the mockup's WL / makeNode) ----
# Curated by tools/catalog.py -> geco_whitelist.json (8 GECO buckets). The knob
# templates are placeholders keyed by bucket until the live LV2 param wiring lands
# (decisions.md A/B/E) — a placed node gets its bucket's dials.
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
            "bypass": False, "knobs": tmpl()}


PBS = ["Lead Joyful", "Clean Verse", "Ambient Cathedral Wash"]
SNAPS = ["Default", "Lead Boost", "Ambient"]


# ---- the seam surface -------------------------------------------------------
class GecoBackend:
    """Where the pedalboard / catalog / persistence live. See the module
    docstring for the data + method contracts. The default implementation is
    ``FakeGeco``; a live adapter over synapse mirrors these names/contracts."""

    # -- reads -----------------------------------------------------------------
    def board(self):
        """The chain as ``[node]`` (a fresh copy the app may cache)."""
        raise NotImplementedError

    def boards(self):
        """Pedalboard names as ``[str]``."""
        raise NotImplementedError

    def snapshots(self):
        """Snapshot names as ``[str]``."""
        raise NotImplementedError

    def catalog(self):
        """The plugin catalog as ``[bucket]`` (place/replace picks from this)."""
        raise NotImplementedError

    # -- board / snapshot navigation -------------------------------------------
    def select(self, which, idx):
        """Load ``which``[idx] onto the host and make it current (board ->
        set_pedalboard + conform, snap -> load_snapshot). Return the now-current
        index — ``idx`` on success, else the actual current (a load can fail/clamp)."""
        raise NotImplementedError

    def current(self, which):
        """Index of the currently-loaded board/snapshot in the list (glance's
        'loaded' marker; seeds the app's current-index cache)."""
        raise NotImplementedError

    # -- node / graph mutations (editor-level) ---------------------------------
    def place(self, slot, bucket_i, plug_i):
        """Fill/replace ``slot`` with catalog[bucket_i].plugins[plug_i]."""
        raise NotImplementedError

    def insert(self, at, bucket_i, plug_i):
        """Splice a NEW catalog[bucket_i].plugins[plug_i] into the chain at index
        ``at`` (net-new — grows the chain; distinct from replace-only ``place``)."""
        raise NotImplementedError

    def remove(self, slot):
        """Empty ``slot``."""
        raise NotImplementedError

    def move(self, slot, to):
        """Reorder: pop the node at ``slot`` and insert it at ``to`` (live: this
        re-routes the chain out->in and refreshes the graph)."""
        raise NotImplementedError

    def set_bypass(self, slot, on):
        """Set ``slot``'s bypass to ``on``."""
        raise NotImplementedError

    def set_param(self, slot, knob, value):
        """Set ``slot``'s knob #``knob`` to the (already stepped/clamped) ``value``."""
        raise NotImplementedError

    # -- persist ---------------------------------------------------------------
    def save(self, which):
        """Persist the current board ('board') or snapshot ('snap') in place."""
        raise NotImplementedError

    def save_as(self, which, after_idx, name):
        """Insert a new ``which`` named ``name`` after ``after_idx``; return its
        index (the caller selects it)."""
        raise NotImplementedError

    def rename(self, which, idx, name):
        """Rename ``which``[idx] to ``name``."""
        raise NotImplementedError

    def delete(self, which, idx):
        """Delete ``which``[idx] (keeps at least one); return the index to select."""
        raise NotImplementedError


class FakeGeco(GecoBackend):
    """In-memory backend for dev/--walk: hand-authored fixtures + mutable state,
    no host. Reads hand back copies so the app's cache can't mutate the truth."""

    def __init__(self):
        self._board = make_board()
        self._boards = list(PBS)
        self._snaps = list(SNAPS)
        self._catalog = load_whitelist()
        self._cur = {"board": 0, "snap": 1}    # which entry is "loaded" (glance marker)

    def _lst(self, which):
        return self._boards if which == "board" else self._snaps

    # -- reads --
    def board(self):
        return copy.deepcopy(self._board)

    def boards(self):
        return list(self._boards)

    def snapshots(self):
        return list(self._snaps)

    def catalog(self):
        return self._catalog

    # -- board / snapshot navigation --
    def select(self, which, idx):
        idx = max(0, min(idx, len(self._lst(which)) - 1))
        self._cur[which] = idx                 # no per-board graph in RAM: marker only
        return idx

    def current(self, which):
        return self._cur[which]

    # -- node / graph mutations --
    def place(self, slot, bucket_i, plug_i):
        cat = self._catalog[bucket_i]
        self._board[slot] = make_node(cat, cat["plugins"][plug_i])
        return None

    def insert(self, at, bucket_i, plug_i):
        cat = self._catalog[bucket_i]
        self._board.insert(at, make_node(cat, cat["plugins"][plug_i]))
        return None

    def remove(self, slot):
        self._board.pop(slot)                  # variable length, like the live graph
        return None

    def move(self, slot, to):
        node = self._board.pop(slot)
        self._board.insert(to, node)
        return None

    def set_bypass(self, slot, on):
        self._board[slot]["bypass"] = on
        return None

    def set_param(self, slot, knob, value):
        self._board[slot]["knobs"][knob]["v"] = value
        return None

    # -- persist --
    def save(self, which):
        return None                            # fixtures live in RAM; nothing to flush

    def save_as(self, which, after_idx, name):
        lst = self._lst(which)
        lst.insert(after_idx + 1, name)
        self._cur[which] = after_idx + 1       # the fresh entry is now loaded
        return after_idx + 1

    def rename(self, which, idx, name):
        self._lst(which)[idx] = name
        return None

    def delete(self, which, idx):
        lst = self._lst(which)
        if len(lst) > 1:
            lst.pop(idx)
            self._cur[which] = min(idx, len(lst) - 1)   # land on the neighbour
            return self._cur[which]
        return idx
