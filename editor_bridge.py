"""Pedalboard Editor — Python brain exposed to QML as ``editor``.

A PyQt6 port of the Claude Design "Pedalboard Editor" mock. Two modes share one canvas:

  QUICK    — free-canvas auto-routing (Concept A): drop effects, the sort-by-x router
             builds a serial trunk with vertical taps/sources and 1↔2 channel adapter chips.
  ADVANCED — manual port-level routing: every node exposes its real ports (audio L/R,
             MIDI, CV); connect by touching a node EDGE → radial port menu → touching the
             target edge. Supports fan/merge (⊕), feedback (z⁻¹, DFS back-edge), per-cable
             delete, MIDI/CV cables.

MODE: QUICK (serial chain, geometry=routing) vs ADVANCED (free graph) is a VIEW of the
same board, determined by routing shape — a representable board opens QUICK, else ADVANCED
(M6d). toggleLiveMode flips the view (bidirectional); a transient modeFlash effect plays
(→ADVANCED "powerful", →QUICK "smart"). There is no one-way bake/evolve.

Mirrors the repo's qtview.py pattern: one QObject, data + flags as notified properties, QML
owns the visual tokens. Routing math is a faithful port of the design's pb_logic.

Wired to live MODEP through the Presenter seam (source of truth = presenter.pedalboard);
the plugin catalog is currently fed by resources/effects-catalog.json (M7 swaps this for
the live host catalog).
"""

import json
import math
import os
import random
import re
import threading
import unicodedata

import configs
import plugincatalog

from PyQt6.QtCore import (QObject, pyqtProperty as Property,
                          pyqtSignal as Signal, pyqtSlot as Slot)

BASE = os.path.dirname(os.path.abspath(__file__))

# bucket -> (color, 3-letter abbreviation) — verbatim from the design's BUCKET map
BUCKET = {
    'Drive': ('#d99a4e', 'DRV'), 'Comp': ('#5fd0a0', 'CMP'), 'Gate': ('#5fd0a0', 'GTE'),
    'Dynamics': ('#5fd0a0', 'DYN'), 'EQ': ('#3b6fe0', 'EQ'), 'Filter': ('#3b6fe0', 'FLT'),
    'Mod': ('#b58af0', 'MOD'), 'Delay': ('#b58af0', 'DLY'), 'Reverb': ('#3b6fe0', 'RVB'),
    'Pitch': ('#b58af0', 'PIT'), 'Amp·Cab': ('#d99a4e', 'AMP'), 'Synth': ('#5fd0a0', 'SYN'),
    'Spatial': ('#3b6fe0', 'SPT'), 'Utility': ('#9aa3b2', 'UTL'), 'CV': ('#5a6270', 'CV'),
    'MIDI': ('#e8694a', 'MID'),
}

PORTCOL = {'audio': '#3b6fe0', 'midi': '#e8694a', 'cv': '#b58af0'}


def _symbolify(name):
    """Fold a plugin label to a jack-safe instance symbol (mirrors mod-ui's
    symbolify). Used to mint new instance names for live add."""
    name = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode('ascii')
    name = re.sub('[^_a-zA-Z0-9]+', '_', name).strip('_')
    if not name:
        name = 'fx'
    if name[0].isdigit():
        name = '_' + name
    return name

# SAVE AS naming — mirrors qtview's snapshot suggester: a guitarist stage term +
# '-' + a random quirky suffix (e.g. "Drive-cupcake"). Same word pool file.
_BOARD_TERMS = ["Clean", "Crunch", "Drive", "Lead", "Rhythm", "Solo",
                "Verse", "Chorus", "Bridge", "Boost", "Ambient", "Heavy"]
_WORDS_PATH = os.path.join(BASE, "resources", "snapshot_words.txt")
_WORDS_FALLBACK = ["chainsaw", "cupcake", "walrus", "thunder", "pickle",
                   "comet", "goblin", "biscuit", "tornado", "noodle"]
_words_cache = None


def _load_words():
    global _words_cache
    if _words_cache is None:
        try:
            with open(_WORDS_PATH, encoding='utf-8') as fh:
                _words_cache = [w.strip() for w in fh
                                if w.strip() and not w.lstrip().startswith('#')] or _WORDS_FALLBACK
        except OSError:
            _words_cache = _WORDS_FALLBACK
    return _words_cache

NODEW = 124
HALF = 27               # quick node visual half-height (node box ~54px tall)
CANVAS_W = 734          # 800 - 66 (rail) ; MUST match the QML canvas width
CANVAS_H = 446          # 480 - 34 (header)
IN_X = 36
OUT_X = CANVAS_W - 36
MID_Y = CANVAS_H / 2

# advanced port-card geometry (port dots stack down the card edges)
HH = 24                 # card header height before ports start
PTOP = 8                # padding above/below the port stack
PR = 18                 # per-port row height
PH = 13                 # port dot diameter
RR = 74                 # radial menu radius
IN_PX = 54              # HW IN port column x
OUT_PX = CANVAS_W - 54  # HW OUT port column x


def bcol(bucket):
    return BUCKET.get(bucket, ('#9aa3b2', ''))[0]


def abbr(bucket):
    return BUCKET.get(bucket, ('#9aa3b2', bucket[:3].upper()))[1] or bucket[:3].upper()


def pin_lbl(n):
    return '·' if n == 0 else ('M' if n == 1 else '%dch' % n)


def fmt(c, v):
    """Format a control value for display — port of pb_logic fmt()."""
    if v is None:
        v = c['def']
    if c['w'] == 'enum':
        i = int(round(v - (c.get('min') or 0)))
        scale = c.get('scale') or []
        return scale[i] if 0 <= i < len(scale) else str(int(round(v)))
    if c['w'] == 'toggle':
        return 'ON' if v >= 0.5 else 'OFF'
    av = abs(v)
    if av >= 100:
        num = str(int(round(v)))
    elif av >= 10:
        num = '%.1f' % v
    else:
        num = '%.2f' % v
    return num + ((' ' + c['unit']) if c.get('unit') else '')


class EditorBridge(QObject):
    changed = Signal()        # full rebuild (rail / fly / nodes / inspector / status / mode / advanced)
    wiresChanged = Signal()   # wires + chips/ports only (live during node drag — no node recreate)
    toast = Signal(str)       # transient message for demo feedback
    modeFlash = Signal(str)   # transient mode-transition effect ('advanced'=powerful / 'quick'=smart)
    spawnFly = Signal(str, str, float, float, float, float)  # name,color,fromX,fromY,toX,toY
    boardsChanged = Signal()  # saved-board list / current name / dirty changed
    confirmBoardSwitch = Signal(str, str)  # (bundle, title) — dirty live switch needs confirm
    boardSwitched = Signal()  # a live board switch actually completed -> close the switcher overlay
    snapsChanged = Signal()   # snapshot list / current snapshot changed (M6c)

    def __init__(self, catalog_path=None):
        super().__init__()
        # Bootstrap from the frozen dump; set_presenter() then swaps in the live
        # host catalog (full installed plugins, un-truncated). Frozen stays as the
        # offline fallback if the live fetch ever fails.
        path = catalog_path or os.path.join(BASE, 'resources', 'effects-catalog.json')
        with open(path, encoding='utf-8') as fh:
            self._apply_catalog(json.load(fh))

        self._uid = 0
        self._wid = 0
        self.mode = 'quick'           # 'quick' | 'advanced'
        self.in_mode = 'mono'         # 'mono' | 'stereo'
        self.out_adapt = 'auto'
        self.sel = -1
        self.fly_bucket = None
        self.nodes = []               # quick nodes: {id,uri,x,y,bypass,vals,inAdapt,mergeAdapt}
        self.gnodes = []              # advanced nodes: {id,uri,x,y,bypass,vals}
        self.gwires = []              # advanced cables: {id, frm, to}  port keys "nid:side:type:idx"
        self.gwire_sel = None         # selected cable id
        self.conn = None              # radial connection state
        self._fly_id = -1             # node currently flying in (hidden until it lands)
        self.board_name = 'Untitled'
        self._dirty = False
        self._live_boards = []        # cached live host board list [{bundle,title,current}]
        self._scratch_default = False # NEW BOARD loaded the shared default -> SAVE must save-as
        self._pending_new = False     # a NEW request is awaiting the dirty-confirm dialog
        self._lq_wires = set()        # live-quick: tracked host wiring (port-key pairs) for reconcile
        self._live_quick_enabled = True   # gate for live QUICK entry (manual toggle / M6d-4 routing)

        # live wiring (None/False in the standalone mock; set when embedded in the app)
        self.presenter = None         # Presenter seam — source of truth is presenter.pedalboard
        self._live_flag = False       # True once seeded from a live MODEP board (Property: live)
        self._gid_by_inst = {}        # live instance string -> integer gnode id
        self._inst_by_gid = {}        # integer gnode id -> live instance string

        # view caches
        self._rail = []
        self._fly = []
        self._wires = []
        self._chips = []
        self._nodes_view = []
        self._knobs = []
        self._status = ''
        # advanced caches
        self._g_nodes = []
        self._g_ports = []
        self._g_wires = []
        self._g_merges = []
        self._g_fbtags = []
        self._g_hw = []
        self._hw_edges = []
        self._rad_items = []
        self._g_pos = {}
        self._rebuild()

    # ---------------------------------------------------------------- helpers
    def _new_id(self):
        self._uid += 1
        return self._uid

    def _new_wid(self):
        self._wid += 1
        return 'w%d' % self._wid

    def _add(self, uri, x=None, y=None):
        p = self.by_uri[uri]
        vals = {}
        for c in p.get('ctl', []):
            if c['w'] != 'bypass':
                vals[c['sym']] = c['def']
        node = {
            'id': self._new_id(), 'uri': uri,
            'x': x if x is not None else IN_X + 90, 'y': y if y is not None else MID_Y - HALF,
            'bypass': False, 'vals': vals, 'inAdapt': 'auto', 'mergeAdapt': 'auto',
        }
        self.nodes.append(node)
        return node

    def _node(self, nid):
        # str-normalized (QML may pass a string nid) and the unified lookup for
        # the live working set: exactly ONE of nodes/gnodes is non-empty in live
        # (advanced uses gnodes, M6d live-quick uses nodes), so nodes-first then
        # gnodes resolves correctly without the id-collision that _gnode dodged.
        for n in self.nodes:
            if str(n['id']) == str(nid):
                return n
        for n in self.gnodes:
            if str(n['id']) == str(nid):
                return n
        return None

    def _gnode(self, nid):
        for n in self.gnodes:
            if str(n['id']) == str(nid):
                return n
        return None

    def _assert_single_ws(self):
        """In live, exactly one working set (self.nodes OR self.gnodes) is
        non-empty — they share _new_id(), so coexistence reintroduces the id
        collision _node() now relies on being absent. Logs rather than crashes
        (defensive; should never fire). Most valuable once M6d live-quick
        populates self.nodes alongside the gid↔inst maps."""
        if self._live_flag and self.nodes and self.gnodes:
            print('⚠️ live working-set invariant violated: nodes=%d gnodes=%d both non-empty'
                  % (len(self.nodes), len(self.gnodes)))

    # ===================================================== live wiring (app embed)
    def set_presenter(self, presenter):
        """Inject the app's Presenter. The live MODEP board (presenter.pedalboard)
        becomes the source of truth; enterLive() seeds the advanced graph from it.
        Also swaps the bootstrap catalog for the live host's full plugin set."""
        self.presenter = presenter
        self._load_live_catalog()

    def _apply_catalog(self, cat):
        """Install a catalog ({count, buckets, plugins}) and rebuild the uri/name
        indices plugins are looked up by."""
        self.cat = cat
        self.by_uri = {p['uri']: p for p in cat['plugins']}
        self.by_name = {p['name'].lower(): p['uri'] for p in cat['plugins']}

    def _load_live_catalog(self):
        """Swap the bootstrap (frozen) catalog for the live host's full installed
        plugin set: backend.effect_list() -> plugincatalog.normalize(). Held for the
        session (plugin install is rare; per-uri self-heal covers stragglers).
        Keeps the frozen fallback if the host returns nothing or errors."""
        be = self._backend()
        if not be:
            return
        try:
            native = be.effect_list()
        except Exception as e:
            print(f"[editor] live catalog fetch failed: {e}")
            return
        cat = plugincatalog.normalize(native or [])
        if not cat['plugins']:
            return                      # nothing usable -> keep the frozen fallback
        self._apply_catalog(cat)
        self._rebuild()                 # rail / browser / count reflect the live catalog

    def _heal_plugin(self, uri):
        """Self-heal a uri the live catalog is missing (a plugin installed after
        startup, or a partial load): fetch its full info on demand and fold it into
        the catalog. Returns the condensed plugin dict, or None if the host doesn't
        know it either. (Browser rail counts refresh on the next rescan/rebuild.)"""
        if uri in self.by_uri:
            return self.by_uri[uri]
        be = self._backend()
        if not be:
            return None
        try:
            info = be.effect_get_information(uri)
        except Exception:
            info = None
        p = plugincatalog.normalize_plugin(info) if info else None
        if not p:
            return None
        self.by_uri[uri] = p
        self.by_name[p['name'].lower()] = uri
        self.cat['plugins'].append(p)
        self.cat['count'] = len(self.cat['plugins'])
        return p

    @Slot()
    def enterLive(self):
        """Called when the app opens the EDIT screen: refresh from the LIVE host
        graph, then (re)seed the advanced graph. Refreshing first means every
        editor entry reflects the running JACK graph -- the editor's own edits
        (already pushed to the host) AND anything changed via the web UI / HMI
        while in the overview -- instead of a stale cached pedalboard. Without
        this, re-entering after an add/connect would re-seed from the old cache
        and the live (host-present) node would vanish from the canvas. No-op in
        the standalone mock."""
        if self.presenter is None:
            return
        try:
            self.presenter.refresh_pedalboard()
        except Exception as e:
            print(f"[editor] refresh on enter failed: {e}")
        pb = getattr(self.presenter, 'pedalboard', None)
        if pb is None:
            return
        self._seed_from_pedalboard(pb)

    # ---- live host writes (no-op in the standalone mock) ----------------------
    def _inst_of(self, nid):
        """Live MODEP instance string for a gnode id (None in mock / unknown)."""
        if not self._live_flag:
            return None
        n = self._node(nid)
        return n.get('inst') if n else None

    def _live_view(self):
        """The QtView write surface (reuses its throttle). None in the mock."""
        return getattr(self.presenter, 'view', None) if self.presenter else None

    def _live_param(self, nid, sym, value):
        """Push a control-port write to the host via QtView.setParameter (throttled)."""
        inst, view = self._inst_of(nid), self._live_view()
        if inst and view:
            view.setParameter(inst, sym, float(value))
            self._touch()   # a live param edit is unsaved state (dirty-confirm honesty)

    def _live_bypass(self, nid, bypassed):
        inst, view = self._inst_of(nid), self._live_view()
        if inst and view:
            view.toggleBypass(inst, bool(bypassed))
            self._touch()

    def _live_effect(self):
        """The presenter-side Effect for the selected live node (None in the mock).
        Lets the inspector read the node's patch params from the live model — the
        editor catalog carries no patch info, only the host-derived model does."""
        inst = self._inst_of(self.sel)
        pb = getattr(self.presenter, 'pedalboard', None) if self.presenter else None
        if not inst or pb is None:
            return None
        return pb.get_effect_by_instance(inst)

    @staticmethod
    def _audio_idx_from_symbol(sym, count):
        """Map a real audio port symbol to its 0-based channel index. Single-port
        sides are always 0; for stereo, prefer a trailing digit in the symbol
        (mod convention in0/in1, out0/out1), else 0. Clamped to < count."""
        if count <= 1:
            return 0
        m = ''.join(ch for ch in sym[::-1] if ch.isdigit())
        if m:
            idx = int(m[::-1])
            if 0 <= idx < count:
                return idx
        return 0

    @staticmethod
    def _norm_inst(s):
        """Strip a mod-host '/graph/' prefix (and stray leading '/') so disk-format
        ('bluesbreaker/out0') and jack-format ('/graph/bluesbreaker/out0') endpoints
        compare equal to bare instance names."""
        s = (s or '').strip()
        if s.startswith('/graph/'):
            s = s[len('/graph/'):]
        return s.lstrip('/')

    def _port_key_from_endpoint(self, ep, side):
        """Turn a live Connection endpoint ("capture_1", "playback_2",
        "bluesbreaker/out0", "nam/input") into a mock port key "nid:side:type:idx".
        Returns None if the effect isn't a seeded node."""
        ep = self._norm_inst(ep)
        base = ep.split('/', 1)[0]
        sym = ep.split('/', 1)[1] if '/' in ep else ''
        if base.startswith('capture'):                    # HW input -> IN node output
            tail = base.rsplit('_', 1)
            idx = int(tail[1]) - 1 if len(tail) == 2 and tail[1].isdigit() else 0
            return 'IN:out:audio:%d' % max(0, idx)
        if base.startswith('playback'):                   # HW output -> OUT node input
            tail = base.rsplit('_', 1)
            idx = int(tail[1]) - 1 if len(tail) == 2 and tail[1].isdigit() else 0
            return 'OUT:in:audio:%d' % max(0, idx)
        gid = self._gid_by_inst.get(base)
        if gid is None:
            return None
        n = self._node(gid)
        # ClaudeCanEdit is audio-only; MIDI/CV symbol typing is a later milestone.
        return '%d:%s:audio:%d' % (gid, side, self._audio_idx(n, side, sym))

    def _audio_idx(self, n, side, sym):
        """0-based channel index of audio port ``sym`` on node ``n``. Prefer the
        node's stored ordered symbol list (exact, symmetric with
        _endpoint_from_port_key); fall back to the trailing-digit heuristic when
        the symbols aren't known (e.g. a node added before symbol fetch)."""
        syms = (n.get('aout') if side == 'out' else n.get('ain')) if n else None
        if syms and sym in syms:
            return syms.index(sym)
        p = self.by_uri.get(n['uri']) if n else None
        count = (p['ao'] if side == 'out' else p['ai']) if p else 1
        return self._audio_idx_from_symbol(sym, count)

    def _endpoint_from_port_key(self, key):
        """Inverse of _port_key_from_endpoint: mock port key "nid:side:type:idx"
        -> graph-namespace endpoint "/graph/<inst>/<symbol>" (or "/graph/capture_N"
        / "/graph/playback_N" for the HW IN/OUT nodes). None if unresolvable or
        non-audio (M5 wires audio only). Pairs with the stored ordered symbol
        lists so seed and edit are perfectly symmetric."""
        parts = key.split(':')
        if len(parts) != 4 or parts[2] != 'audio':
            return None
        nid, side, _typ, idx_s = parts
        idx = int(idx_s)
        if nid == 'IN':
            return '/graph/capture_%d' % (idx + 1)
        if nid == 'OUT':
            return '/graph/playback_%d' % (idx + 1)
        n = self._node(int(nid)) if nid.lstrip('-').isdigit() else None
        if not n or not n.get('inst'):
            return None
        syms = n.get('aout') if side == 'out' else n.get('ain')
        if not syms or idx >= len(syms):
            return None
        return '/graph/%s/%s' % (n['inst'], syms[idx])

    # ------------------------------------------------ live graph-edit helpers
    def _backend(self):
        """The MODEP backend (host seam) when embedded in the app; None in mock."""
        return getattr(self.presenter, 'backend', None) if self.presenter else None


    def _mint_instance(self, uri):
        """Pick a fresh bare instance name for a new live node. web_add adopts the
        name we send, so it only needs to be a valid symbol unique among the
        instances we know about (seeded + added this session)."""
        p = self.by_uri.get(uri, {})
        base = _symbolify(p.get('label') or p.get('name') or 'fx')
        if base not in self._gid_by_inst:
            return base
        n = 1
        while '%s_%d' % (base, n) in self._gid_by_inst:
            n += 1
        return '%s_%d' % (base, n)

    def _seed_from_pedalboard(self, pb, auto_quick=True):
        """Build the advanced graph (gnodes + gwires) from a live Pedalboard.
        Integer gnode ids (the feedback DFS does int()) are mapped to live instance
        strings so structural edits can later address the real MODEP graph."""
        self._live_flag = True
        self.mode = 'advanced'
        self.board_name = pb.title or 'Untitled'
        self._dirty = False
        # Scratch = the loaded board IS the shared default, regardless of HOW it
        # became current (NEW BOARD, footswitch, or just open at startup). This is
        # the real guard: any save on the default is forced to save-as so the
        # shared template is never overwritten in place. (NEW BOARD also loads the
        # default, so this covers it without relying on requestNewLiveBoard.)
        self._scratch_default = (self._norm_bundle(getattr(pb, 'current_pb_path', '')) ==
                                 self._norm_bundle(configs.DEFAULT_PEDALBOARD))
        self.in_mode = 'stereo' if (getattr(pb, 'audio_ins', 2) or 2) >= 2 else 'mono'
        self.sel = -1
        self.gwire_sel = None
        self.conn = None
        self._fly_id = -1
        # Drop the standalone-mock quick chain (bluesbreaker/GxCompressor/…). Those
        # nodes get ids 1..N that COLLIDE with the live gnode ids, and _node()
        # searches self.nodes first — so without this the inspector for live gnode
        # id=2 (e.g. NAM) would resolve to the mock node id=2 (GxCompressor) and
        # edits would read the wrong plugin's controls while writing to the live one.
        self.nodes = []

        effects = list(pb.effects)
        self._gid_by_inst = {}
        self._inst_by_gid = {}
        xs = [e.x for e in effects] or [0.0]
        ys = [e.y for e in effects] or [0.0]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)

        def _norm(v, lo, hi, out_lo, out_hi, center):
            # Don't stretch a near-degenerate axis (a serial chain's y differs by a few
            # px in mod-ui coords) into the whole canvas — center it instead.
            if hi - lo < 60:
                return center
            return out_lo + (v - lo) / (hi - lo) * (out_hi - out_lo)

        def sx(x):
            return _norm(x, minx, maxx, 120, CANVAS_W - 220, CANVAS_W / 2 - NODEW / 2)

        def sy(y):
            return _norm(y, miny, maxy, 44, CANVAS_H - 130, CANVAS_H / 2 - 50)

        gnodes, missing = [], []
        for i, e in enumerate(effects):
            if e.uri not in self.by_uri and not self._heal_plugin(e.uri):
                # the host doesn't know this uri either — skip so the editor renders
                # the rest rather than crashing on geometry lookups.
                missing.append(e.name or e.uri)
                continue
            gid = i + 1
            inst = self._norm_inst(e.instance)
            self._gid_by_inst[inst] = gid
            self._inst_by_gid[gid] = inst
            vals = {sym: port.value for sym, port in (e.ports or {}).items()}
            gnodes.append({'id': gid, 'uri': e.uri, 'inst': inst,
                           'x': sx(e.x), 'y': sy(e.y),
                           'bypass': bool(e.bypassed), 'vals': vals,
                           # ordered audio port symbols — jack names for live wiring
                           'ain': list(e.audio_inputs or []),
                           'aout': list(e.audio_outputs or [])})
        self.gnodes = gnodes
        if missing:
            self.toast.emit('카탈로그 누락 %d개 생략: %s' % (len(missing), ', '.join(missing[:3])))

        wires, have = [], set()
        for c in pb.connections:
            frm = self._port_key_from_endpoint(c.source, 'out')
            to = self._port_key_from_endpoint(c.target, 'in')
            if frm and to and (frm, to) not in have:
                have.add((frm, to))
                wires.append({'id': self._new_wid(), 'frm': frm, 'to': to})
        self.gwires = wires

        self._assert_single_ws()
        # M6d-4: mode follows shape — a quick-representable board auto-opens in
        # QUICK (unless auto_quick is suppressed, e.g. the manual toggle to
        # ADVANCED, which must not bounce straight back to quick). The advanced
        # gnodes/gwires above are built regardless (cheap, shared seed work);
        # _project_to_quick swaps the working set when it wins.
        rep = False
        try:
            rep, _why = self._quick_representable(pb)
        except Exception as e:
            print('[editor] quick-representable check failed: %s' % e)
        if auto_quick and self._live_quick_enabled and rep:
            self._project_to_quick()     # rebuilds + emits boardsChanged
            return
        self._rebuild()
        self.boardsChanged.emit()

    # ---------------------------------------------------- quick graph (round-trip)
    def _inline(self, nodes):
        return [n for n in nodes if self.by_uri[n['uri']]['ai'] > 0 and self.by_uri[n['uri']]['ao'] > 0]

    def arcs_from_layout(self, nodes):
        sorted_n = sorted(nodes, key=lambda n: n['x'])
        inline = [n for n in sorted_n if n in self._inline(nodes)]
        trunk = tuple(n['uri'] for n in inline)
        seg_x = [IN_X] + [n['x'] + NODEW for n in inline]
        branches = []
        for n in sorted_n:
            if n in inline:
                continue
            p = self.by_uri[n['uri']]
            cx = n['x'] + NODEW / 2
            seg = 0
            for i, sx in enumerate(seg_x):
                if cx >= sx:
                    seg = i
            role = 'tap' if p['ao'] == 0 else 'source'
            branches.append((n['uri'], seg, role))
        return (trunk, frozenset(branches))

    def layout_from_graph(self, qgraph):
        trunk, branches = qgraph
        out = []
        n = len(trunk)
        gap = (OUT_X - IN_X) / (n + 1) if n else (OUT_X - IN_X)
        seg_mid_x = []
        for i in range(n + 1):
            lo = IN_X if i == 0 else IN_X + gap * i
            seg_mid_x.append(lo + gap / 2 if n else (IN_X + OUT_X) / 2)
        for i, uri in enumerate(trunk):
            x = IN_X + gap * (i + 1) - NODEW / 2
            out.append((uri, x, MID_Y - HALF, False))
        for uri, seg, role in sorted(branches, key=lambda b: b[1]):
            x = seg_mid_x[min(seg, len(seg_mid_x) - 1)] - NODEW / 2
            y = (MID_Y - 3 * HALF) if role == 'source' else (MID_Y + HALF)
            out.append((uri, max(IN_X + 8, min(OUT_X - NODEW - 8, x)), y, True))
        return out

    def _apply_layout(self, graph):
        relaid = self.layout_from_graph(graph)
        by_uri_q = {}
        for n in self.nodes:
            by_uri_q.setdefault(n['uri'], []).append(n)
        used = {}
        for uri, x, y, _b in relaid:
            q = used.get(uri, 0)
            lst = by_uri_q.get(uri, [])
            if q < len(lst):
                lst[q]['x'], lst[q]['y'] = x, y
                used[uri] = q + 1

    def _relayout_quick(self, graph=None):
        self._apply_layout(graph if graph is not None else self.arcs_from_layout(self.nodes))

    # ============================================================ QUICK routing
    def _route(self, nodes):
        """Auto-routing — faithful port of the design. Returns (wires, chips, roles)."""
        sorted_n = sorted(nodes, key=lambda n: n['x'])
        in_ch = 2 if self.in_mode == 'stereo' else 1

        def adapt(src, dst, override):
            if not src or not dst or src == dst:
                return None
            if src == 1 and dst == 2:
                o = ['dup', 'L', 'R']
                m = override if override in o else 'dup'
                return {'kind': '1to2', 'mode': m, 'label': '1▸2 ' + m.upper()}
            if src == 2 and dst == 1:
                o = ['sum', 'L', 'R']
                m = override if override in o else 'sum'
                return {'kind': '2to1', 'mode': m, 'label': '2▸1 ' + m.upper()}
            return None

        def mkwire(x1, y1, x2, y2, color, stereo, dash=False):
            dx = max(28, abs(x2 - x1) / 2)
            return {'d': 'M %g %g C %g %g, %g %g, %g %g' % (x1, y1, x1 + dx, y1, x2 - dx, y2, x2, y2),
                    'color': color, 'w': 5.0 if stereo else 2.6, 'dash': '7 5' if dash else '', 'stereo': stereo}

        def vwire(x1, y1, x2, y2, color, stereo=False):
            dy = y2 - y1
            sgn = 1 if dy >= 0 else -1
            off = max(18, abs(dy) / 2)
            return {'d': 'M %g %g C %g %g, %g %g, %g %g' % (x1, y1, x1, y1 + sgn * off, x2, y2 - sgn * off, x2, y2),
                    'color': color, 'w': 5.0 if stereo else 2.6, 'dash': '6 5', 'stereo': stereo}

        wires, chips, roles = [], [], {}
        inline = self._inline(nodes)
        inline_sorted = [n for n in sorted_n if n in inline]
        branch = [n for n in sorted_n if n not in inline]

        trunk_ch, trunk_x, trunk_y = in_ch, IN_X, MID_Y
        segments = []
        for n in inline_sorted:
            p = self.by_uri[n['uri']]
            ai, ao = p['ai'], p['ao']
            in_p = (n['x'], n['y'] + HALF)
            out_p = (n['x'] + NODEW, n['y'] + HALF)
            a = adapt(trunk_ch, ai, n.get('inAdapt', 'auto'))
            wires.append(mkwire(trunk_x, trunk_y, in_p[0], in_p[1],
                                '#2c3648' if n['bypass'] else '#3b6fe0', trunk_ch == 2))
            if a:
                chips.append({'label': a['label'], 'x': (trunk_x + in_p[0]) / 2, 'y': (trunk_y + in_p[1]) / 2,
                              'bg': '#1f2636', 'accent': '#d99a4e', 'fg': '#e8b06a', 'nid': n['id'], 'kind': 'in'})
            segments.append({'x1': trunk_x, 'y1': trunk_y, 'x2': in_p[0], 'y2': in_p[1], 'ch': trunk_ch})
            roles[n['id']] = 'fx'
            trunk_ch, trunk_x, trunk_y = ao, out_p[0], out_p[1]
        oa = adapt(trunk_ch, 2, self.out_adapt)
        wires.append(mkwire(trunk_x, trunk_y, OUT_X, MID_Y, '#d99a4e', trunk_ch == 2))
        if oa:
            chips.append({'label': oa['label'], 'x': (trunk_x + OUT_X) / 2, 'y': (trunk_y + MID_Y) / 2,
                          'bg': '#2a221a', 'accent': '#d99a4e', 'fg': '#e8b06a', 'nid': -1, 'kind': 'out'})
        segments.append({'x1': trunk_x, 'y1': trunk_y, 'x2': OUT_X, 'y2': MID_Y, 'ch': trunk_ch})

        def seg_at(x):
            for sg in segments:
                lo, hi = min(sg['x1'], sg['x2']), max(sg['x1'], sg['x2'])
                if lo <= x <= hi:
                    return sg
            return segments[0] if x < segments[0]['x1'] else segments[-1]

        def pt_on(sg, x):
            dx = sg['x2'] - sg['x1']
            t = 0 if dx == 0 else max(0, min(1, (x - sg['x1']) / dx))
            return (sg['x1'] + t * dx, sg['y1'] + t * (sg['y2'] - sg['y1']), sg['ch'])

        for n in branch:
            p = self.by_uri[n['uri']]
            ai, ao = p['ai'], p['ao']
            cx = n['x'] + NODEW / 2
            sg = seg_at(cx)
            mp = pt_on(sg, cx)
            line_above = mp[1] <= n['y'] + HALF
            conn_y = n['y'] if line_above else n['y'] + 2 * HALF
            conn_x = cx
            if ao == 0:
                wires.append(vwire(mp[0], mp[1], conn_x, conn_y, '#2c3648' if n['bypass'] else '#5a6270'))
                roles[n['id']] = 'tap'
            else:
                a = adapt(ao, mp[2], n.get('mergeAdapt', 'auto'))
                wires.append(vwire(conn_x, conn_y, mp[0], mp[1], '#2c3648' if n['bypass'] else '#5fd0a0', ao == 2))
                if a:
                    chips.append({'label': a['label'], 'x': (conn_x + mp[0]) / 2, 'y': (conn_y + mp[1]) / 2,
                                  'bg': '#16241c', 'accent': '#5fd0a0', 'fg': '#8fe0bd', 'nid': n['id'], 'kind': 'merge'})
                roles[n['id']] = 'source'
        return wires, chips, roles

    def _build_nodes_view(self, roles):
        out = []
        for n in self.nodes:
            p = self.by_uri[n['uri']]
            b = p['bucket']
            role = roles.get(n['id'], 'fx')
            sel = self.sel == n['id']
            is_branch = role in ('tap', 'source')
            badge, badge_color = '', '#5a6270'
            if role == 'tap':
                badge, badge_color = 'TAP', '#9aa3b2'
            elif role == 'source':
                badge, badge_color = 'MIX▸', '#5fd0a0'
            if sel:
                bord = '#3b6fe0'
            elif n['bypass']:
                bord = '#2c3648'
            elif role == 'tap':
                bord = '#5a6270'
            elif role == 'source':
                bord = '#5fd0a0'
            else:
                bord = bcol(b)
            out.append({
                'id': n['id'], 'x': n['x'], 'y': n['y'], 'name': p['name'], 'bucket': abbr(b),
                'border': bord, 'dot': '#5a6270' if n['bypass'] else bcol(b),
                'glow': 'transparent' if n['bypass'] else bcol(b), 'bypass': n['bypass'], 'sel': sel,
                'inPins': 0 if is_branch else p['ai'], 'outPins': 0 if is_branch else p['ao'],
                'badge': badge, 'badgeColor': badge_color, 'hasBadge': bool(badge),
                'flying': n['id'] == self._fly_id,
                'pending': bool(n.get('pending')),
            })
        return out

    # ===================================================== ADVANCED port graph
    def _audio_outs(self, nid):
        if nid == 'IN':
            return ['IN:out:audio:%d' % i for i in range(2 if self.in_mode == 'stereo' else 1)]
        if nid == 'OUT':
            return []
        n = self._node(nid)
        if not n:
            return []
        # Prefer the node's real host audio-out symbols (live); fall back to the
        # catalog count when symbols aren't loaded (mock gnodes). Using catalog
        # counts when host symbols exist risks idx >= len(syms) -> endpoint None
        # -> dropped wires (shared with the advanced wiring path).
        syms = n.get('aout')
        count = len(syms) if syms is not None else self.by_uri[n['uri']]['ao']
        return ['%s:out:audio:%d' % (nid, i) for i in range(count)]

    def _audio_ins(self, nid):
        if nid == 'OUT':
            return ['OUT:in:audio:0', 'OUT:in:audio:1']
        if nid == 'IN':
            return []
        n = self._node(nid)
        if not n:
            return []
        syms = n.get('ain')
        count = len(syms) if syms is not None else self.by_uri[n['uri']]['ai']
        return ['%s:in:audio:%d' % (nid, i) for i in range(count)]

    def _connect_audio(self, from_id, to_id, out):
        fo, ti = self._audio_outs(from_id), self._audio_ins(to_id)
        if not fo or not ti:
            return
        if len(fo) == 1 and len(ti) > 1:
            for t in ti:
                out.append({'id': self._new_wid(), 'frm': fo[0], 'to': t})
        elif len(fo) > 1 and len(ti) == 1:
            for f in fo:
                out.append({'id': self._new_wid(), 'frm': f, 'to': ti[0]})
        else:
            for i in range(min(len(fo), len(ti))):
                out.append({'id': self._new_wid(), 'frm': fo[i], 'to': ti[i]})

    # ---- quick serial-chain wiring: THE single source of truth (M6d-2) ----
    # _quick_wire_keys() generates the desired audio wiring for the current quick
    # working set (self.nodes). Bake, (M6d-3) live reconcile, and (M6d-2)
    # representability classification all derive from THIS one function, so the
    # edit-time wires and the classifier can never diverge (the desync that would
    # otherwise cut a user's real cables on the first edit after entering quick).
    def _n_ao(self, n):
        syms = n.get('aout')
        return len(syms) if syms is not None else self.by_uri[n['uri']]['ao']

    def _n_ai(self, n):
        syms = n.get('ain')
        return len(syms) if syms is not None else self.by_uri[n['uri']]['ai']

    def _quick_wire_keys(self):
        """Desired audio wiring for self.nodes as a set of (frm_key, to_key) port
        keys. Mirrors the bake topology: a serial trunk of inline fx (ai>0 & ao>0)
        ordered by x (IN -> fx -> ... -> OUT), taps (ao==0) fed from the nearest
        prior trunk fx, sources (ai==0) into OUT."""
        wires = []
        src = sorted(self.nodes, key=lambda n: n['x'])
        fx = [n for n in src if self._n_ai(n) > 0 and self._n_ao(n) > 0]
        prev = 'IN'
        for n in fx:
            self._connect_audio(prev, n['id'], wires)
            prev = n['id']
        if fx:
            self._connect_audio(prev, 'OUT', wires)
        for n in src:
            if self._n_ai(n) > 0 and self._n_ao(n) > 0:
                continue
            if self._n_ao(n) == 0 and self._n_ai(n) > 0:        # tap
                prior = [f for f in fx if f['x'] < n['x']]
                self._connect_audio(prior[-1]['id'] if prior else 'IN', n['id'], wires)
            elif self._n_ai(n) == 0 and self._n_ao(n) > 0:      # source
                self._connect_audio(n['id'], 'OUT', wires)
        return {(w['frm'], w['to']) for w in wires}

    def _quick_representable(self, pb):
        """Can pb be shown as a quick serial chain? Returns (ok, in_mode_or_reason)
        — on success the second value is the matching 'mono'/'stereo' (callers seed
        in_mode with it).

        GENERATOR=CLASSIFIER: project pb's effects to candidate quick nodes,
        generate the desired wiring with _quick_wire_keys, and require
        instance+channel set-equality with the host's actual audio connections.
        That single comparison auto-rejects fan-out/fan-in/feedback/L-R-swap with
        no separate hand-coded topology rule. The board's actual input usage is
        mono (capture_1 only) or stereo (capture_1+2) regardless of the hardware
        audio_ins, so we try BOTH in_modes and accept the one that matches.
        Catalog-filtered (missing plugin -> advanced); MIDI/CV-only -> advanced;
        empty/passthrough -> advanced (M6d-3 전 무음 회피). Instance-keyed."""
        effects = list(pb.effects)
        if not effects:
            return (False, '빈 보드')
        if any(e.uri not in self.by_uri for e in effects):
            return (False, '카탈로그 누락')
        proj = []
        for i, e in enumerate(effects):
            ain, aout = list(e.audio_inputs or []), list(e.audio_outputs or [])
            if not ain and not aout:
                return (False, 'MIDI/CV 전용')
            proj.append({'id': i + 1, 'uri': e.uri, 'inst': e.instance,
                         'x': i, 'y': 0, 'ain': ain, 'aout': aout})
        host = {(self._norm_inst(c.source), self._norm_inst(c.target)) for c in pb.connections}
        saved_nodes, saved_in = self.nodes, self.in_mode
        self.nodes = proj
        try:
            for im in ('mono', 'stereo'):
                self.in_mode = im
                desired, bad = set(), False
                for f, t in self._quick_wire_keys():
                    ef, et = self._endpoint_from_port_key(f), self._endpoint_from_port_key(t)
                    if not ef or not et:
                        bad = True
                        break
                    desired.add((self._norm_inst(ef), self._norm_inst(et)))
                if not bad and desired == host:
                    return (True, im)
        finally:
            self.nodes, self.in_mode = saved_nodes, saved_in
        return (False, '직렬체인 아님')

    def _port_counts(self, nid, side):
        if nid == 'IN':
            return {'a': (2 if self.in_mode == 'stereo' else 1), 'm': 1, 'cv': 0} if side == 'out' else {'a': 0, 'm': 0, 'cv': 0}
        if nid == 'OUT':
            return {'a': 2, 'm': 1, 'cv': 0} if side == 'in' else {'a': 0, 'm': 0, 'cv': 0}
        n = self._gnode(nid)
        if not n:
            return {'a': 0, 'm': 0, 'cv': 0}
        p = self.by_uri[n['uri']]
        outs = side == 'out'
        cv = p['cv'] if (p['cv'] and ((outs and p['bucket'] == 'CV') or (not outs and p['bucket'] != 'CV'))) else 0
        return {'a': p['ao'] if outs else p['ai'], 'm': p['mo'] if outs else p['mi'], 'cv': cv}

    def _opts_for(self, nid, side):
        c = self._port_counts(nid, side)
        o = []
        if c['a'] == 1:
            o.append({'label': 'AUDIO', 'type': 'audio', 'idx': [0]})
        elif c['a'] >= 2:
            o += [{'label': 'L', 'type': 'audio', 'idx': [0]},
                  {'label': 'R', 'type': 'audio', 'idx': [1]},
                  {'label': 'BOTH', 'type': 'audio', 'idx': [0, 1]}]
        if c['m'] > 0:
            o.append({'label': 'MIDI', 'type': 'midi', 'idx': [0]})
        if c['cv'] > 0:
            o.append({'label': 'CV', 'type': 'cv', 'idx': [0]})
        return o

    def _opt_angle(self, side, i, n):
        base = 0.0 if side == 'out' else math.pi
        spread = math.pi * 0.62
        off = 0.0 if n <= 1 else (i - (n - 1) / 2) * (spread / (n - 1))
        return base + off

    def _clamp_c(self, cx, cy):
        return (max(86, min(CANVAS_W - 86, cx)), max(76, min(CANVAS_H - 76, cy)))

    def _ports_of(self, gnode):
        p = self.by_uri[gnode['uri']]
        ins, outs = [], []
        for i in range(p['ai']):
            ins.append({'type': 'audio', 'ti': i, 'ch': ('R' if i else 'L') if p['ai'] > 1 else ''})
        for i in range(p['mi']):
            ins.append({'type': 'midi', 'ti': i, 'ch': ''})
        if p['cv'] and p['bucket'] != 'CV':
            for i in range(p['cv']):
                ins.append({'type': 'cv', 'ti': i, 'ch': ''})
        for i in range(p['ao']):
            outs.append({'type': 'audio', 'ti': i, 'ch': ('R' if i else 'L') if p['ao'] > 1 else ''})
        for i in range(p['mo']):
            outs.append({'type': 'midi', 'ti': i, 'ch': ''})
        if p['cv'] and p['bucket'] == 'CV':
            for i in range(p['cv']):
                outs.append({'type': 'cv', 'ti': i, 'ch': ''})
        return ins, outs

    def _card_h(self, gnode):
        ins, outs = self._ports_of(gnode)
        rows = max(len(ins), len(outs), 1)
        return HH + PTOP + rows * PR + PTOP

    def _free_spot(self, mode, uri):
        """Top-left position for a new node: the empty grid slot nearest the canvas
        center that does not overlap an existing node (so spawns are obvious)."""
        w = NODEW
        h = self._card_h({'uri': uri}) if mode == 'advanced' else 54
        nodes = self.gnodes if mode == 'advanced' else self.nodes
        cx, cy = CANVAS_W / 2, CANVAS_H / 2
        minx, maxx = 72, CANVAS_W - w - 60
        miny, maxy = 8, CANVAS_H - h - 8

        def overlaps(x, y):
            for n in nodes:
                nh = (self._card_h(n) if mode == 'advanced' else 54)
                if (abs((x + w / 2) - (n['x'] + w / 2)) < w + 16
                        and abs((y + h / 2) - (n['y'] + nh / 2)) < (h + nh) / 2 + 16):
                    return True
            return False

        step = 24
        cands = []
        gy = miny
        while gy <= maxy:
            gx = minx
            while gx <= maxx:
                cands.append((gx, gy))
                gx += step
            gy += step
        cands.sort(key=lambda p: (p[0] + w / 2 - cx) ** 2 + (p[1] + h / 2 - cy) ** 2)
        for gx, gy in cands:
            if not overlaps(gx, gy):
                return (float(gx), float(gy))
        return (float(cx - w / 2), float(cy - h / 2))

    # ============================================================ inspector
    def _build_inspector(self):
        self._knobs = []
        if self.sel < 0:
            return
        n = self._node(self.sel)
        if not n:
            return
        p = self.by_uri[n['uri']]
        for c in [c for c in p.get('ctl', []) if c['w'] != 'bypass']:   # all params (scrollable)
            v = n['vals'].get(c['sym'], c['def'])
            kind = 'toggle' if c['w'] == 'toggle' else ('enum' if c['w'] in ('enum', 'button') else 'dial')
            norm = (v - c['min']) / (c['max'] - c['min']) if c['max'] > c['min'] else 0
            self._knobs.append({
                'label': c.get('short') or c['name'], 'valueText': fmt(c, v), 'kind': kind,
                'norm': max(0.0, min(1.0, norm)), 'on': v >= 0.5, 'sym': c['sym'],
            })

    # ============================================================ view rebuild
    def _rebuild_wires(self):
        if self.mode == 'quick':
            self._wires, self._chips, self._roles = self._route(self.nodes)
        else:
            self._rebuild_adv_geometry()
        self.wiresChanged.emit()

    def _rebuild_adv_geometry(self):
        """Compute ports/wires/merges/feedback/radial for advanced mode. Cheap enough to
        recompute on every node-drag move (ports/wires must follow the node)."""
        gw, gh, g_mid = CANVAS_W, CANVAS_H, CANVAS_H / 2
        pos = {}
        ports = []

        def port_dot(x, y, col, ch, dim):
            return {'x': x, 'y': y, 'color': '#3a4252' if dim else col, 'ch': ch}

        for node in self.gnodes:
            ins, outs = self._ports_of(node)

            def place(arr, side):
                for li, pt in enumerate(arr):
                    x = node['x'] if side == 'in' else node['x'] + NODEW
                    y = node['y'] + HH + PTOP + li * PR + PH / 2
                    pos['%s:%s:%s:%d' % (node['id'], side, pt['type'], pt['ti'])] = (x, y, pt['type'])
                    ports.append(port_dot(x, y, PORTCOL[pt['type']], pt['ch'], node['bypass']))
            place(ins, 'in')
            place(outs, 'out')

        # HW IN / OUT port columns
        in_p = ([{'type': 'audio', 'ti': 0, 'ch': 'L'}, {'type': 'audio', 'ti': 1, 'ch': 'R'}]
                if self.in_mode == 'stereo' else [{'type': 'audio', 'ti': 0, 'ch': ''}])
        in_p.append({'type': 'midi', 'ti': 0, 'ch': ''})
        out_p = [{'type': 'audio', 'ti': 0, 'ch': 'L'}, {'type': 'audio', 'ti': 1, 'ch': 'R'},
                 {'type': 'midi', 'ti': 0, 'ch': ''}]

        def stack(arr, x, node):
            total = len(arr) * PR
            start_y = g_mid - total / 2 + PH / 2
            for li, pt in enumerate(arr):
                y = start_y + li * PR
                pos['%s:%s:%s:%d' % (node, 'out' if node == 'IN' else 'in', pt['type'], pt['ti'])] = (x, y, pt['type'])
                ports.append(port_dot(x, y, PORTCOL[pt['type']], pt['ch'], False))
        stack(in_p, IN_PX, 'IN')
        stack(out_p, OUT_PX, 'OUT')
        in_tot, out_tot = len(in_p) * PR, len(out_p) * PR
        self._g_hw = [
            {'x': 18, 'y': g_mid - in_tot / 2 - 6, 'w': 30, 'h': in_tot + 12,
             'label': 'IN', 'sub': 'ST' if self.in_mode == 'stereo' else 'M', 'color': '#5fd0a0'},
            {'x': gw - 48, 'y': g_mid - out_tot / 2 - 6, 'w': 30, 'h': out_tot + 12,
             'label': 'OUT', 'sub': 'ST', 'color': '#d99a4e'},
        ]

        # candidate-edge highlighting while choosing a target
        cn = self.conn
        need_side = (cn['srcSide'] == 'out' and 'in' or 'out') if (cn and cn.get('stage') == 'target') else None
        cand_type = cn['srcType'] if (cn and cn.get('stage') == 'target') else None

        def edge_glow(nid, side):
            if need_side != side:
                return False
            if str(nid) == str(cn.get('srcNode')):
                return False
            return any(o['type'] == cand_type for o in self._opts_for(nid, side))

        self._hw_edges = [
            {'node': 'IN', 'side': 'out', 'x': 46, 'y': g_mid - in_tot / 2 - 8, 'w': 18, 'h': in_tot + 16,
             'glow': edge_glow('IN', 'out')},
            {'node': 'OUT', 'side': 'in', 'x': gw - 66, 'y': g_mid - out_tot / 2 - 8, 'w': 18, 'h': out_tot + 16,
             'glow': edge_glow('OUT', 'in')},
        ]

        # feedback detection: DFS back-edge among fx nodes (HW excluded)
        adj = {n['id']: [] for n in self.gnodes}
        for w in self.gwires:
            f, t = w['frm'].split(':')[0], w['to'].split(':')[0]
            if f not in ('IN', 'OUT') and t not in ('IN', 'OUT') and int(f) in adj:
                adj[int(f)].append(int(t))
        fb_pairs, col = set(), {}

        def dfs(u):
            col[u] = 1
            for v in adj.get(u, []):
                if col.get(v) == 1:
                    fb_pairs.add('%d>%d' % (u, v))
                elif not col.get(v):
                    dfs(v)
            col[u] = 2
        for n in self.gnodes:
            if not col.get(n['id']):
                dfs(n['id'])

        wires, merges, fbtags = [], [], set()
        mid_of, in_count = {}, {}
        out_fbtags = []
        for w in self.gwires:
            a, b = pos.get(w['frm']), pos.get(w['to'])
            if not a or not b:
                continue
            in_count[w['to']] = in_count.get(w['to'], 0) + 1
            from_id, to_id = w['frm'].split(':')[0], w['to'].split(':')[0]
            fb = ('%s>%s' % (from_id, to_id)) in fb_pairs
            fn = self._gnode(from_id)
            dim = fn['bypass'] if fn else False
            is_sel = self.gwire_sel == w['id']
            if fb:
                d = 'M %g %g C %g %g, %g %g, %g %g' % (a[0], a[1], a[0] + 70, a[1] + 90, b[0] - 70, b[1] + 90, b[0], b[1])
            else:
                dx = max(40, (b[0] - a[0]) / 2)
                d = 'M %g %g C %g %g, %g %g, %g %g' % (a[0], a[1], a[0] + dx, a[1], b[0] - dx, b[1], b[0], b[1])
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + (64 if fb else 0)
            mid_of[w['id']] = (mx, my)
            dash = '7 5' if fb else ('2 4' if a[2] == 'midi' else ('1 5' if a[2] == 'cv' else ''))
            color = '#eaf2ff' if is_sel else ('#2c3648' if dim else ('#e0a458' if fb else PORTCOL[a[2]]))
            wires.append({'id': w['id'], 'd': d, 'w': (2.6 if a[2] == 'audio' else 2.0) + (2.2 if is_sel else 0),
                          'dash': dash, 'color': color, 'mx': mx, 'my': my})
            if fb and ('%s>%s' % (from_id, to_id)) not in fbtags:
                fbtags.add('%s>%s' % (from_id, to_id))
                out_fbtags.append({'x': (a[0] + b[0]) / 2, 'y': (a[1] + b[1]) / 2 + 72, 'label': 'z⁻¹'})
        for k, cnt in in_count.items():
            if cnt >= 2 and k in pos:
                pp = pos[k]
                merges.append({'x': pp[0], 'y': pp[1]})

        self._g_pos = pos
        self._g_ports = ports
        self._g_wires = wires
        self._g_merges = merges
        self._g_fbtags = out_fbtags
        self._mid_of = mid_of

        # radial menu items
        rad = []
        if cn and cn.get('stage') in ('srcPick', 'dstPick'):
            cx, cy = cn['cx'], cn['cy']
            for i, o in enumerate(cn['opts']):
                ang = self._opt_angle(cn['side'], i, len(cn['opts']))
                rad.append({'label': o['label'], 'idx': i,
                            'x': cx + RR * math.cos(ang), 'y': cy + RR * math.sin(ang),
                            'color': PORTCOL[o['type']]})
        self._rad_items = rad

    def _build_g_nodes(self):
        cn = self.conn
        need_side = (cn['srcSide'] == 'out' and 'in' or 'out') if (cn and cn.get('stage') == 'target') else None
        cand_type = cn['srcType'] if (cn and cn.get('stage') == 'target') else None
        out = []
        for node in self.gnodes:
            p = self.by_uri[node['uri']]
            b = p['bucket']
            sel = self.sel == node['id']
            bord = '#3b6fe0' if sel else ('#2c3648' if node['bypass'] else bcol(b))
            ci = self._port_counts(node['id'], 'in')
            co = self._port_counts(node['id'], 'out')
            has_in = (ci['a'] + ci['m'] + ci['cv']) > 0
            has_out = (co['a'] + co['m'] + co['cv']) > 0

            def cand(side, has):
                if need_side != side or not has:
                    return False
                if str(node['id']) == str(cn.get('srcNode')):
                    return False
                return any(o['type'] == cand_type for o in self._opts_for(node['id'], side))
            out.append({
                'id': node['id'], 'x': node['x'], 'y': node['y'], 'h': self._card_h(node),
                'name': p['name'], 'bucket': abbr(b), 'bypass': node['bypass'], 'sel': sel,
                'border': bord, 'dot': '#5a6270' if node['bypass'] else bcol(b),
                'glow': 'transparent' if node['bypass'] else bcol(b),
                'hasIn': has_in, 'hasOut': has_out,
                'edgeInGlow': cand('in', has_in), 'edgeOutGlow': cand('out', has_out),
                'flying': node['id'] == self._fly_id,
                'pending': bool(node.get('pending')),
            })
        return out

    def _rebuild(self):
        self._rail = [{'key': b['key'], 'abbr': abbr(b['key']), 'color': bcol(b['key']),
                       'count': b['count'], 'sel': self.fly_bucket == b['key']} for b in self.cat['buckets']]
        self._fly = []
        if self.fly_bucket:
            for p in [p for p in self.cat['plugins'] if p['bucket'] == self.fly_bucket]:
                self._fly.append({'uri': p['uri'], 'name': p['name'], 'brand': p['brand'],
                                  'pins': pin_lbl(p['ai']) + '▸' + pin_lbl(p['ao'])})
        if self.mode == 'quick':
            self._wires, self._chips, self._roles = self._route(self.nodes)
            self._nodes_view = self._build_nodes_view(self._roles)
            chain = [abbr(self.by_uri[n['uri']]['bucket']) for n in sorted(self.nodes, key=lambda n: n['x'])
                     if self.by_uri[n['uri']]['ai'] > 0 and self.by_uri[n['uri']]['ao'] > 0]
            self._status = 'IN %s  ▸  %s  ▸  OUT STEREO' % (
                'STEREO' if self.in_mode == 'stereo' else 'L-MONO', '▸'.join(chain) if chain else '—')
        else:
            self._rebuild_adv_geometry()
            self._g_nodes = self._build_g_nodes()
            cn = self.conn
            if cn:
                self._status = '연결 대상 선택 중…' if cn.get('stage') == 'target' else '포트 선택 중…'
            else:
                self._status = '%d nodes · %d cables · MANUAL · type-matched' % (len(self.gnodes), len(self.gwires))
        self._build_inspector()
        self.changed.emit()
        self.wiresChanged.emit()

    # ===================================================== properties for QML
    @Property(bool, notify=changed)
    def advanced(self):
        return self.mode == 'advanced'

    @Property(bool, notify=changed)
    def live(self):
        """True when seeded from a live MODEP board (vs the standalone mock).
        QML hides mock-only chrome (QUICK/evolve/mock board manager) when live."""
        return self._live_flag

    @Property('QVariantList', notify=changed)
    def rail(self):
        return self._rail

    @Property(bool, notify=changed)
    def flyOpen(self):
        return self.fly_bucket is not None

    @Property(str, notify=changed)
    def flyTitle(self):
        return (self.fly_bucket or '').upper()

    @Property(str, notify=changed)
    def flyColor(self):
        return bcol(self.fly_bucket) if self.fly_bucket else '#9aa3b2'

    @Property('QVariantList', notify=changed)
    def flyItems(self):
        return self._fly

    @Property('QVariantList', notify=wiresChanged)
    def wires(self):
        return self._wires

    @Property('QVariantList', notify=wiresChanged)
    def chips(self):
        return self._chips

    @Property('QVariantList', notify=changed)
    def nodesView(self):
        return self._nodes_view

    @Property(bool, notify=changed)
    def empty(self):
        return len(self.nodes) == 0 if self.mode == 'quick' else len(self.gnodes) == 0

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def inMode(self):
        return self.in_mode

    # advanced
    @Property('QVariantList', notify=changed)
    def gNodes(self):
        return self._g_nodes

    @Property('QVariantList', notify=wiresChanged)
    def gPorts(self):
        return self._g_ports

    @Property('QVariantList', notify=wiresChanged)
    def gWires(self):
        return self._g_wires

    @Property('QVariantList', notify=wiresChanged)
    def gMerges(self):
        return self._g_merges

    @Property('QVariantList', notify=wiresChanged)
    def gFbTags(self):
        return self._g_fbtags

    @Property('QVariantList', notify=wiresChanged)
    def gHw(self):
        return self._g_hw

    @Property('QVariantList', notify=wiresChanged)
    def hwEdges(self):
        return self._hw_edges

    @Property('QVariantList', notify=changed)
    def radItems(self):
        return self._rad_items

    @Property(bool, notify=changed)
    def radActive(self):
        return bool(self.conn and self.conn.get('stage') in ('srcPick', 'dstPick'))

    @Property(float, notify=changed)
    def radCx(self):
        return float(self.conn['cx']) if self.radActive else 0.0

    @Property(float, notify=changed)
    def radCy(self):
        return float(self.conn['cy']) if self.radActive else 0.0

    @Property(str, notify=changed)
    def radTitle(self):
        if not self.radActive:
            return ''
        return '보낼 포트' if self.conn.get('stage') == 'srcPick' else '받을 포트'

    @Property(bool, notify=changed)
    def targeting(self):
        return bool(self.conn and self.conn.get('stage') == 'target')

    @Property(str, notify=changed)
    def targetHint(self):
        if not self.targeting:
            return ''
        return ('▸ 신호를 받을 노드의 입력(좌변)을 터치' if self.conn['srcSide'] == 'out'
                else '◂ 신호를 보낼 노드의 출력(우변)을 터치')

    @Property(bool, notify=wiresChanged)
    def gWireDel(self):
        return bool(self.gwire_sel and self.gwire_sel in getattr(self, '_mid_of', {}))

    @Property(float, notify=wiresChanged)
    def gWireDelX(self):
        return float(self._mid_of[self.gwire_sel][0]) if self.gWireDel else 0.0

    @Property(float, notify=wiresChanged)
    def gWireDelY(self):
        return float(self._mid_of[self.gwire_sel][1]) if self.gWireDel else 0.0

    # board lifecycle
    @Property(str, notify=boardsChanged)
    def boardName(self):
        return self.board_name

    @Property(bool, notify=boardsChanged)
    def dirty(self):
        return self._dirty

    @Property(bool, notify=boardsChanged)
    def boardSaved(self):
        # A current host bundle always exists, so SAVE is an in-place overwrite —
        # EXCEPT a freshly NEW'd scratch board (the shared default), where SAVE must
        # open the naming panel (save-as) so we never overwrite default.pedalboard.
        return not self._scratch_default

    # ----------------------------------------------- live board switch (M6a)
    @staticmethod
    def _norm_bundle(p):
        """Canonical bundle path for comparison (host paths may carry a trailing
        slash). One shared normalizer for BOTH the current-highlight and the
        no-op guard so clicking the current board can never trigger a needless
        /reset that wipes dirty edits."""
        return (p or '').rstrip('/')

    @Property('QVariantList', notify=boardsChanged)
    def liveBoardList(self):
        """Host's full pedalboard list for the editor switcher: each entry
        {bundle,title,current}. Populated by refreshBoards() (fresh, not stale)."""
        return self._live_boards

    @Slot()
    def refreshBoards(self):
        """(Re)fetch the live host board list — call when the BOARD overlay opens
        so it's fresh, not a stale bank cache. Marks the current board via the
        shared normalizer. No-op (and clears) in the mock."""
        be = self._backend()
        if not (self._live_flag and be):
            self._live_boards = []
            self.boardsChanged.emit()
            return
        cur = self._norm_bundle(be.get_current_pedalboard())
        default = self._norm_bundle(configs.DEFAULT_PEDALBOARD)
        entries = be.get_all_pedalboard_entries() or []
        # Hide the shared default.pedalboard from the switcher — it's the empty
        # scratch template (NEW BOARD loads it), not a user-selectable board.
        self._live_boards = [{'bundle': e['bundle'],
                              'title': e.get('title', '') or e['bundle'],
                              'current': self._norm_bundle(e['bundle']) == cur}
                             for e in entries
                             if self._norm_bundle(e['bundle']) != default]
        self.boardsChanged.emit()

    @Slot(str, str, result=bool)
    def requestLiveBoardSwitch(self, bundle, title):
        """Editor asked to switch to ``bundle``. No-op if it's already current
        (avoids a needless graph-wiping /reset). If there are unsaved live edits,
        raise confirmBoardSwitch for a dialog; else switch immediately.

        Returns True ONLY when the switch happened right now (clean path), so the
        caller can close the overlay. False when it no-op'd (current) or deferred
        to the confirm dialog — in the dialog case the confirm action closes the
        overlay, so both paths end consistently (overlay closed, on the editor)."""
        if not self._live_flag:
            return False
        be = self._backend()
        cur = self._norm_bundle(be.get_current_pedalboard()) if be else ''
        if self._norm_bundle(bundle) == cur:
            self.toast.emit('이미 현재 보드')
            return False
        if self._dirty:
            self.confirmBoardSwitch.emit(bundle, title or bundle)
            return False
        return self._doLiveBoardSwitch(bundle)

    @Slot(str)
    def confirmedLiveBoardSwitch(self, bundle):
        """Dialog confirmed 'discard & switch' — routes to NEW BOARD when the
        pending request was a NEW (the dialog is shared). _pending_new carries the
        kind ('quick'/'advanced') or False."""
        if not self._live_flag:
            return
        if self._pending_new:
            kind = self._pending_new if isinstance(self._pending_new, str) else 'advanced'
            self._pending_new = False
            self._do_new_live_board(kind)
        else:
            self._doLiveBoardSwitch(bundle)

    @Slot(str)
    def requestNewLiveBoard(self, kind='advanced'):
        """NEW BOARD: start fresh on the empty default bundle in ``kind``
        ('quick'/'advanced'). Goes through the dirty-confirm (reusing
        confirmBoardSwitch) and BYPASSES requestLiveBoardSwitch's 'already current'
        no-op (default may already be current — NEW must still reload it)."""
        if not self._live_flag:
            return
        if self._dirty:
            self._pending_new = kind or 'advanced'
            self.confirmBoardSwitch.emit(configs.DEFAULT_PEDALBOARD, '새 빈 보드')
        else:
            self._do_new_live_board(kind)

    def _do_new_live_board(self, kind='advanced'):
        """Load the empty default bundle as a SCRATCH board (SAVE forced to
        save-as). The default is empty + not representable, so it seeds ADVANCED;
        if the user chose QUICK, force the empty quick canvas (no wires — adding
        the first fx reconciles IN->fx->OUT)."""
        if not self._doLiveBoardSwitch(configs.DEFAULT_PEDALBOARD):
            return
        self._scratch_default = True
        if kind == 'quick':
            self.mode = 'quick'
            self.nodes = []
            self.gnodes = []
            self.gwires = []
            self._lq_wires = set()
            self._rebuild()
        self.boardsChanged.emit()    # boardSaved flipped -> SAVE becomes save-as
        self.toast.emit('새 %s 보드 — 빌드 후 SAVE로 이름 저장'
                        % ('퀵' if kind == 'quick' else '어드밴스드'))

    def _doLiveBoardSwitch(self, bundle):
        """Perform the live switch through the presenter. On failure (host graph
        wiped by /reset, load_bundle failed) DO NOT reseed — surface it instead,
        so we never paint a blank/stale canvas over a destroyed graph. Returns
        True on a successful switch."""
        if not (self._live_flag and self.presenter):
            return False
        pb = self.presenter.editor_switch_pedalboard(bundle)
        if pb is None:
            self.toast.emit('전환 실패 — 보드 유지됨')
            return False
        self._seed_from_pedalboard(pb)   # reseeds gnodes/gwires, clears _dirty
        self.refreshBoards()             # refresh current-board highlight
        self.toast.emit('보드 전환됨')
        self.boardSwitched.emit()        # tell QML to close the switcher overlay (both paths)
        return True

    @Property('QVariantList', constant=True)
    def boardTerms(self):
        return _BOARD_TERMS

    @Slot(str, result=str)
    def suggestName(self, term):
        """A stage term + random quirky suffix, avoiding the current board name."""
        existing = {self.board_name}
        words = _load_words()
        for _ in range(12):
            name = '%s-%s' % (term, random.choice(words))
            if name not in existing:
                return name
        return '%s-%s' % (term, random.choice(words))

    # ------------------------------------------------ live snapshot mgmt (M6c)
    def _live_pb(self):
        """The presenter's live Pedalboard (snapshots live on it). None in mock."""
        if not self._live_flag or not self.presenter:
            return None
        return getattr(self.presenter, 'pedalboard', None)

    @Property('QVariantList', notify=snapsChanged)
    def snapList(self):
        """The current board's snapshots as [{idx,name,current}] for the editor
        picker. list_of_snapshots is a {"0":name,...} dict; current_snapshot_idx
        marks the active one."""
        pb = self._live_pb()
        if pb is None:
            return []
        snaps = pb.list_of_snapshots or {}
        cur = pb.current_snapshot_idx
        return [{'idx': int(k), 'name': snaps[k], 'current': int(k) == cur}
                for k in sorted(snaps, key=lambda s: int(s))]

    @Property(str, notify=snapsChanged)
    def currentSnapshotName(self):
        pb = self._live_pb()
        if pb is None:
            return ''
        return (pb.list_of_snapshots or {}).get(str(pb.current_snapshot_idx), '')

    @Slot(int)
    def selectSnapshot(self, idx):
        """Load snapshot ``idx`` (applies its param/bypass to the live graph) and
        re-seed so node values + inspector reflect it. Snapshots don't change
        graph structure, so nodes/wires are unchanged — only values."""
        if not (self._live_flag and self.presenter):
            return
        pb = self.presenter.go_to_snapshot(idx)
        if pb is None:
            return
        self._seed_from_pedalboard(pb)   # refresh node vals (also clears _dirty baseline)
        self.snapsChanged.emit()
        self.toast.emit('스냅샷 · %s' % self.currentSnapshotName)

    @Slot()
    def saveSnapshot(self):
        """Overwrite the current snapshot. NOTE this also persists the pedalboard
        to disk (mod-ui couples the two: snapshot_save save_pb_also=True) — it
        therefore inherits the M6b 3-layer corruption defense."""
        if not (self._live_flag and self.presenter):
            return
        ok = self.presenter.save_snapshot()
        if ok:
            self._dirty = False          # the board was persisted too
            self.snapsChanged.emit()
            self.boardsChanged.emit()
            self.toast.emit('스냅샷 저장됨 · %s' % self.currentSnapshotName)
        else:
            self.toast.emit('스냅샷 저장 실패')

    @Slot(str)
    def saveSnapshotNamed(self, name):
        """Save the current state as a NEW snapshot (also persists the board)."""
        if not (self._live_flag and self.presenter):
            return
        name = (name or '').strip()
        if not name:
            return
        self.presenter.save_snapshot_as(name)
        self._dirty = False
        self.snapsChanged.emit()
        self.boardsChanged.emit()
        self.toast.emit('새 스냅샷 · %s' % name)

    @Slot(str, result=str)
    def suggestSnapshotName(self, term):
        """A stage term + quirky suffix, avoiding existing snapshot names."""
        pb = self._live_pb()
        existing = set((pb.list_of_snapshots or {}).values()) if pb else set()
        words = _load_words()
        for _ in range(12):
            name = '%s-%s' % (term, random.choice(words))
            if name not in existing:
                return name
        return '%s-%s' % (term, random.choice(words))

    # inspector
    @Property(bool, notify=changed)
    def inspOpen(self):
        return self.sel >= 0 and self._node(self.sel) is not None

    @Property(str, notify=changed)
    def inspName(self):
        n = self._node(self.sel)
        return self.by_uri[n['uri']]['name'] if n else ''

    @Property(str, notify=changed)
    def inspSub(self):
        n = self._node(self.sel)
        if not n:
            return ''
        p = self.by_uri[n['uri']]
        return p['brand'] + ((' · %d presets' % p['presets']) if p['presets'] else '')

    @Property(str, notify=changed)
    def inspMeta(self):
        n = self._node(self.sel)
        if not n:
            return ''
        p = self.by_uri[n['uri']]
        return '%d params · %s▸%s' % (p['ctlTotal'], pin_lbl(p['ai']), pin_lbl(p['ao']))

    @Property(bool, notify=changed)
    def inspBypassed(self):
        n = self._node(self.sel)
        return bool(n and n['bypass'])

    @Property(bool, notify=changed)
    def inspCanConnect(self):
        if self.mode != 'advanced':
            return False
        n = self._gnode(self.sel)
        if not n:
            return False
        c = self._port_counts(n['id'], 'out')
        return (c['a'] + c['m'] + c['cv']) > 0

    @Property('QVariantList', notify=changed)
    def knobs(self):
        return self._knobs

    @Property('QVariantList', notify=changed)
    def inspPatches(self):
        """Patch params (NAM model / IR / cabsim) of the selected live node, for the
        inspector file picker. [] in the mock (catalog carries no patch info)."""
        eff = self._live_effect()
        if not eff:
            return []
        return [{'label': p.label, 'uri': p.uri,
                 'value': os.path.basename(p.value) if p.value else ''}
                for p in eff.patches.values()]

    # ============================================================ slots (QML->py)
    @Slot(str)
    def pickCategory(self, key):
        self.fly_bucket = None if self.fly_bucket == key else key
        self._rebuild()

    @Slot()
    def closeFly(self):
        self.fly_bucket = None
        self._rebuild()

    @Slot(str)
    def addEffect(self, uri):
        if uri not in self.by_uri:
            return
        p = self.by_uri[uri]
        tx, ty = self._free_spot(self.mode, uri)
        if self._live_flag:
            # Live: add asynchronously. Plugin instantiation can be slow (FFT/spectral
            # plugins take seconds), so a synchronous host call would freeze the UI.
            # A dimmed ghost node lands immediately; _on_add_done confirms it — or
            # drops it on a host rejection — when the background add returns.
            self._begin_live_add(uri, tx, ty)
            return
        if self.mode == 'advanced':
            self._touch()
            node = {'id': self._new_id(), 'uri': uri, 'x': tx, 'y': ty,
                    'bypass': False, 'vals': {c['sym']: c['def'] for c in p.get('ctl', []) if c['w'] != 'bypass'}}
            self.gnodes.append(node)
        else:
            self._touch()
            node = self._add(uri, tx, ty)
        self.sel = node['id']
        self._fly_id = node['id']
        self.fly_bucket = None
        self._rebuild()
        # fly in from off-screen (palette side) to the chosen slot
        self.spawnFly.emit(p['name'], bcol(p['bucket']), -NODEW - 16.0, ty, tx, ty)

    def _run_bg(self, work, done):
        """Run work() off the GUI thread; deliver done(result) back on the GUI
        thread (via the presenter's scheduler — same marshalling the reverse-socket
        loop uses). Keeps slow host mutations from freezing the UI. Falls back to a
        synchronous call when no scheduler is wired (off-device unit tests)."""
        sched = getattr(self.presenter, 'scheduler', None)
        if sched is None:
            done(work())
            return

        def runner():
            try:
                res = work()
            except Exception as e:                       # noqa: BLE001
                res = 'An error occurred: %s' % e
            sched.schedule_once(lambda dt: done(res))
        threading.Thread(target=runner, daemon=True, name='editor-add').start()

    def _begin_live_add(self, uri, tx, ty):
        """Drop a dimmed PENDING ghost node immediately and fire the host add in the
        background. Audio port symbols come from the catalog (ains/aouts) — no extra
        host fetch. _on_add_done confirms or removes the ghost when the add returns."""
        be = self._backend()
        if not be:
            self.toast.emit('백엔드 없음 — 추가 불가')
            return
        p = self.by_uri[uri]
        inst = self._mint_instance(uri)
        gid = self._new_id()
        quick = (self.mode == 'quick')
        if quick:
            x, y = max([n['x'] for n in self.nodes], default=80) + 150, CANVAS_H / 2 - 30
        else:
            x, y = tx, ty
        node = {'id': gid, 'uri': uri, 'inst': inst, 'x': x, 'y': y, 'bypass': False,
                'pending': True, 'inAdapt': 'auto', 'mergeAdapt': 'auto',
                'ain': list(p.get('ains') or []), 'aout': list(p.get('aouts') or []),
                'vals': {c['sym']: c['def'] for c in p.get('ctl', []) if c['w'] != 'bypass'}}
        (self.nodes if quick else self.gnodes).append(node)
        self._gid_by_inst[inst] = gid
        self._inst_by_gid[gid] = inst
        self.sel = gid
        self._fly_id = gid
        self.fly_bucket = None
        self._touch()
        self._rebuild()
        self.spawnFly.emit(p['name'], bcol(p['bucket']), -NODEW - 16.0, y, x, y)
        self._run_bg(lambda: be.add_effect(inst, uri, x, y),
                     lambda err: self._on_add_done(gid, inst, quick, err))

    def _on_add_done(self, gid, inst, quick, err):
        """Background add returned. err is None => the host has the instance: confirm
        the ghost (and, in quick mode, wire it into the chain now that it really
        exists). Otherwise drop the ghost and surface the reason."""
        bucket = self.nodes if quick else self.gnodes
        node = next((n for n in bucket if n['id'] == gid), None)
        if err is not None:
            bucket[:] = [n for n in bucket if n['id'] != gid]
            self._gid_by_inst.pop(inst, None)
            self._inst_by_gid.pop(gid, None)
            if self.sel == gid:
                self.sel = -1
            self.toast.emit('추가 실패: %s' % err)
            self._rebuild()
            return
        if node is not None:
            node.pop('pending', None)
        if quick:
            self._reconcile_live_quick()
        self._rebuild()

    # ------------------------------------------------ live QUICK mode (M6d-3)
    @Slot()
    def toggleLiveMode(self):
        """Live ADV<->QUICK toggle. To QUICK only if the board is quick-
        representable AND live-quick is enabled (host-first reconcile makes quick
        edits safe). To ADVANCED re-seeds from the live host (authoritative)."""
        if not (self._live_flag and self.presenter):
            return
        if self.mode == 'advanced':
            if not self._live_quick_enabled:
                self.toast.emit('라이브 퀵 비활성')
                return
            if self._project_to_quick():
                self.modeFlash.emit('quick')        # -> QUICK: "smart"
            else:
                self.toast.emit('이 보드는 QUICK 표현 불가 — 어드밴스드 유지')
        else:
            pb = self._live_pb()
            if pb is not None:
                # auto_quick=False so the re-seed STAYS advanced (don't auto-route
                # straight back to quick — this is an explicit transient override).
                self._seed_from_pedalboard(pb, auto_quick=False)
                self.modeFlash.emit('advanced')      # -> ADVANCED: "powerful"

    def _project_to_quick(self):
        """Inverse of bake: build the quick working set (self.nodes) from the live
        pedalboard in serial order, clear the advanced set, and seed _lq_wires with
        the current host wiring (== _quick_wire_keys for a representable board, so
        the first reconcile is a no-op). Returns False if not representable."""
        pb = self._live_pb()
        if pb is None:
            return False
        rep, im = self._quick_representable(pb)
        if not rep:
            return False
        nodes = []
        self._gid_by_inst = {}
        self._inst_by_gid = {}
        for i, e in enumerate(pb.effects):
            gid = i + 1
            ai, ao = len(e.audio_inputs or []), len(e.audio_outputs or [])
            y = CANVAS_H / 2 - 30
            if ao == 0 and ai > 0:
                y = CANVAS_H / 2 + 70          # tap -> below the trunk
            elif ai == 0 and ao > 0:
                y = CANVAS_H / 2 - 130         # source -> above the trunk
            nodes.append({'id': gid, 'uri': e.uri, 'inst': e.instance,
                          'x': 120 + i * 150, 'y': y, 'bypass': bool(e.bypassed),
                          'vals': {sym: pt.value for sym, pt in (e.ports or {}).items()},
                          'ain': list(e.audio_inputs or []), 'aout': list(e.audio_outputs or []),
                          'inAdapt': 'auto', 'mergeAdapt': 'auto'})
            self._gid_by_inst[e.instance] = gid
            self._inst_by_gid[gid] = e.instance
        self.nodes = nodes
        self.gnodes = []
        self.gwires = []
        self.mode = 'quick'
        self.in_mode = im   # the in_mode the classifier matched (mono/stereo)
        self.sel = -1
        self._lq_wires = self._quick_wire_keys()   # current host wiring (representable)
        self._assert_single_ws()
        self._rebuild()
        self.boardsChanged.emit()
        return True   # silent: auto-seed gives no feedback; the manual toggle flashes

    def _reconcile_live_quick(self):
        """Bring the host wiring to match the quick layout: diff desired
        (_quick_wire_keys) against the tracked _lq_wires and push only the delta.
        Dry-run resolves all new endpoints first; then CONNECT new cables BEFORE
        disconnecting old ones (minimize the silence window — never teardown-first).
        Only host-acked changes update _lq_wires (M5 host-first discipline)."""
        if not (self._live_flag and self.mode == 'quick' and self.presenter):
            return
        be = self._backend()
        if not be:
            return
        desired = self._quick_wire_keys()
        to_add = desired - self._lq_wires
        to_remove = self._lq_wires - desired
        # dry-run: resolve endpoints for all adds up front
        adds = []
        for (f, t) in to_add:
            ef, et = self._endpoint_from_port_key(f), self._endpoint_from_port_key(t)
            if not ef or not et:
                self.toast.emit('포트 해석 실패 — 일부 배선 보류')
                continue
            adds.append((f, t, ef, et))
        for (f, t, ef, et) in adds:                     # connect-first
            if be.connect(ef, et) is None:
                self._lq_wires.add((f, t))
        for (f, t) in list(to_remove):                  # then disconnect
            ef, et = self._endpoint_from_port_key(f), self._endpoint_from_port_key(t)
            if ef and et:
                be.disconnect(ef, et)                    # failure == already gone
            self._lq_wires.discard((f, t))
        self._touch()
        self._rebuild()


    @Slot()
    def clearFly(self):
        self._fly_id = -1
        self._rebuild()

    # ---- quick node drag
    @Slot(int, float, float)
    def nodeDragMove(self, nid, x, y):
        n = self._node(nid)
        if not n:
            return
        n['x'] = max(40, min(CANVAS_W - NODEW - 4, x))
        n['y'] = max(4, min(CANVAS_H - 58, y))
        self._rebuild_wires()

    @Slot(int, float, float, bool)
    def nodeDragEnd(self, nid, x, y, over_trash):
        n = self._node(nid)
        if not n:
            return
        if over_trash and self._live_flag:
            # Live quick: host-first remove (host severs its cables), drop the node
            # + its tracked wires, then reconcile to bridge the neighbours.
            inst = n.get('inst')
            be = self._backend()
            if be and inst:
                err = be.remove_effect(inst)
                if err is not None:
                    self.toast.emit('삭제 실패: %s' % err)
                    self._rebuild()
                    return
                self._gid_by_inst.pop(inst, None)
                self._inst_by_gid.pop(nid, None)
                sid = str(nid)
                self._lq_wires = {(f, t) for (f, t) in self._lq_wires
                                  if f.split(':')[0] != sid and t.split(':')[0] != sid}
            self.nodes = [m for m in self.nodes if m['id'] != nid]
            if self.sel == nid:
                self.sel = -1
            self._reconcile_live_quick()     # reconnect the neighbours
            self._touch()
            return
        if over_trash:
            self._touch()
            self.nodes = [m for m in self.nodes if m['id'] != nid]
            if self.sel == nid:
                self.sel = -1
        else:
            n['x'] = max(40, min(CANVAS_W - NODEW - 4, x))
            n['y'] = max(4, min(CANVAS_H - 58, y))
            if self._live_flag:
                self._reconcile_live_quick()  # reorder -> re-wire to the new x-order
                self._touch()
                return
        self._touch()
        self._rebuild()

    # ---- advanced node drag
    @Slot(int, float, float)
    def gNodeDragMove(self, nid, x, y):
        n = self._gnode(nid)
        if not n:
            return
        n['x'] = max(2, min(CANVAS_W - NODEW - 4, x))
        n['y'] = max(2, min(CANVAS_H - 58, y))
        self._rebuild_wires()

    @Slot(int, float, float, bool)
    def gNodeDragEnd(self, nid, x, y, over_trash):
        n = self._gnode(nid)
        if not n:
            return
        if over_trash:
            if self._live_flag:
                # Host-first: remove the instance (the host severs its cables too).
                # Keep the node on canvas if the host rejects it.
                inst = n.get('inst')
                be = self._backend()
                if be and inst:
                    err = be.remove_effect(inst)
                    if err is not None:
                        self.toast.emit('삭제 실패: %s' % err)
                        self._rebuild()
                        return
                    self._gid_by_inst.pop(inst, None)
                    self._inst_by_gid.pop(nid, None)
            else:
                self._touch()
            sid = str(nid)
            self.gnodes = [m for m in self.gnodes if str(m['id']) != sid]
            self.gwires = [w for w in self.gwires
                           if w['frm'].split(':')[0] != sid and w['to'].split(':')[0] != sid]
            if self.sel == nid:
                self.sel = -1
        else:
            # Position is editor-local in live mode (cosmetic until M6 save).
            n['x'] = max(2, min(CANVAS_W - NODEW - 4, x))
            n['y'] = max(2, min(CANVAS_H - 58, y))
        self._touch()
        self._rebuild()

    @Slot(int)
    def selectNode(self, nid):
        self.sel = nid
        self.gwire_sel = None
        self.conn = None
        self._rebuild()

    @Slot()
    def resetParams(self):
        """Reset every parameter of the selected node to its default."""
        n = self._node(self.sel)
        if not n:
            return
        p = self.by_uri[n['uri']]
        n['vals'] = {c['sym']: c['def'] for c in p.get('ctl', []) if c['w'] != 'bypass'}
        self._touch()
        for c in p.get('ctl', []):
            if c['w'] != 'bypass':
                self._live_param(self.sel, c['sym'], c['def'])
        self._build_inspector()
        self.changed.emit()

    @Slot(str)
    def resetKnob(self, sym):
        """Reset a single parameter to its default (double-tap)."""
        n = self._node(self.sel)
        if not n:
            return
        c = next((c for c in self.by_uri[n['uri']].get('ctl', []) if c['sym'] == sym), None)
        if not c:
            return
        n['vals'][sym] = c['def']
        self._touch()
        self._live_param(self.sel, sym, c['def'])
        self._build_inspector()
        self.changed.emit()

    @Slot(str, result='QVariantList')
    def patchFiles(self, uri):
        """Selectable files for a patch URI on the selected live node ([{label,path}]).
        Delegates to the same presenter scan the FOCUS picker uses."""
        inst = self._inst_of(self.sel)
        if not inst or not self.presenter:
            return []
        return self.presenter.list_patch_files(inst, uri)

    @Slot(str, str)
    def setPatch(self, uri, path):
        """Inspector picked a file -> load it on the selected live node (NAM/IR/cabsim),
        then refresh so the chip label updates. No-op in the mock."""
        inst = self._inst_of(self.sel)
        if not (inst and self.presenter):
            return
        self.presenter.patch_changed(inst, uri, path)
        self._touch()
        self._build_inspector()
        self.changed.emit()

    @Slot()
    def connectFromSelected(self):
        """ADVANCED: start a radial connection from the selected node's output edge."""
        if self.mode != 'advanced':
            return
        n = self._gnode(self.sel)
        if not n:
            return
        self._begin_source(str(n['id']), 'out', n['x'] + NODEW, n['y'] + self._card_h(n) / 2)

    @Slot()
    def closeInspector(self):
        self.sel = -1
        self._rebuild()

    @Slot(int)
    def toggleBypass(self, nid):
        n = self._node(nid)
        if n:
            n['bypass'] = not n['bypass']
            self._touch()
            self._live_bypass(nid, n['bypass'])
            self._rebuild()

    @Slot()
    def toggleSelectedBypass(self):
        # Inspector ACTIVE/BYPASSED chip: operate on the current selection.
        # (sel is a plain attr, not a QML-visible Property — QML must not read it.)
        self.toggleBypass(self.sel)

    @Slot(str, float, result=str)
    def setKnobNorm(self, sym, norm):
        """Live during a dial drag — update the value and return its formatted text.
        Does NOT emit changed (that would recreate the knob delegate mid-gesture and
        make rotation stutter). QML rotates locally; syncInspector() finalizes on release."""
        n = self._node(self.sel)
        if not n:
            return ''
        p = self.by_uri[n['uri']]
        c = next((c for c in p['ctl'] if c['sym'] == sym), None)
        if not c:
            return ''
        v = c['min'] + max(0.0, min(1.0, norm)) * (c['max'] - c['min'])
        if c['w'] in ('step', 'enum'):
            v = round(v)
        n['vals'][sym] = v
        self._touch()
        self._live_param(self.sel, sym, v)   # throttled host write (live mode only)
        return fmt(c, v)

    @Slot()
    def syncInspector(self):
        """Rebuild the inspector model once (e.g. when a dial drag ends)."""
        self._build_inspector()
        self.changed.emit()

    @Slot(str)
    def toggleSwitch(self, sym):
        n = self._node(self.sel)
        if not n:
            return
        cur = n['vals'].get(sym, 0)
        n['vals'][sym] = 0 if cur >= 0.5 else 1
        self._touch()
        self._live_param(self.sel, sym, n['vals'][sym])
        self._build_inspector()
        self.changed.emit()

    @Slot(str)
    def cycleEnum(self, sym):
        n = self._node(self.sel)
        if not n:
            return
        p = self.by_uri[n['uri']]
        c = next((c for c in p['ctl'] if c['sym'] == sym), None)
        if not c:
            return
        cnt = max(1, len(c.get('scale') or []) or int(c['max'] - c['min'] + 1))
        i = int(round(n['vals'].get(sym, c['def']) - (c['min'] or 0)))
        i = (i + 1) % cnt
        n['vals'][sym] = (c['min'] or 0) + i
        self._touch()
        self._live_param(self.sel, sym, n['vals'][sym])
        self._build_inspector()
        self.changed.emit()

    @Slot()
    def toggleInMode(self):
        self.in_mode = 'stereo' if self.in_mode == 'mono' else 'mono'
        self._touch()
        self._rebuild()

    @Slot(int)
    def cycleInAdapter(self, nid):
        n = self._node(nid)
        if n:
            self._cycle_adapt(n, 'inAdapt', '1to2')
            self._touch()
            self._rebuild()

    @Slot(int)
    def cycleMergeAdapter(self, nid):
        n = self._node(nid)
        if n:
            self._cycle_adapt(n, 'mergeAdapt', '2to1')
            self._touch()
            self._rebuild()

    @Slot()
    def cycleOutAdapter(self):
        order = ['auto', 'dup', 'L', 'R', 'sum']
        self.out_adapt = order[(order.index(self.out_adapt) + 1) % len(order)] if self.out_adapt in order else 'dup'
        self._touch()
        self._rebuild()

    def _cycle_adapt(self, n, key, default_kind):
        o = ['dup', 'L', 'R'] if default_kind == '1to2' else ['sum', 'L', 'R']
        cur = n.get(key, 'auto')
        n[key] = o[(o.index(cur) + 1) % len(o)] if cur in o else o[0]

    # ---------------------------------------------------- advanced radial connect
    @Slot(str, str, float, float)
    def edgeTap(self, node, side, cx, cy):
        """Touch a node/HW edge. Routes to source-pick or dest-pick by current state."""
        if self.conn and self.conn.get('stage') == 'target':
            self._begin_dest(node, side, cx, cy)
        elif not self.conn:
            self._begin_source(node, side, cx, cy)
        else:
            # mid radial-pick: ignore stray edge taps
            return

    def _begin_source(self, node, side, cx, cy):
        opts = self._opts_for(node, side)
        if not opts:
            return
        cx, cy = self._clamp_c(cx, cy)
        self.conn = {'stage': 'srcPick', 'node': node, 'side': side, 'cx': cx, 'cy': cy,
                     'opts': opts, 'hover': None}
        self.sel = -1
        self.gwire_sel = None
        self._rebuild()

    def _begin_dest(self, node, side, cx, cy):
        c = self.conn
        need = 'in' if c['srcSide'] == 'out' else 'out'
        if side != need or str(node) == str(c['srcNode']):
            return
        opts = [o for o in self._opts_for(node, side) if o['type'] == c['srcType']]
        if not opts:
            return
        cx, cy = self._clamp_c(cx, cy)
        self.conn = dict(c, stage='dstPick', node=node, side=side, cx=cx, cy=cy, opts=opts, hover=None)
        self._rebuild()

    @Slot(int)
    def commitRadialOpt(self, i):
        c = self.conn
        if not c or i < 0 or i >= len(c['opts']):
            return
        opt = c['opts'][i]
        if c['stage'] == 'srcPick':
            self.conn = {'stage': 'target', 'srcNode': c['node'], 'srcSide': c['side'],
                         'srcType': opt['type'], 'srcIdx': opt['idx']}
        elif c['stage'] == 'dstPick':
            self._create_cables({'node': c['srcNode'], 'side': c['srcSide'], 'type': c['srcType'], 'idx': c['srcIdx']},
                                 {'node': c['node'], 'side': c['side'], 'type': opt['type'], 'idx': opt['idx']})
            self.conn = None
        self._rebuild()

    @Slot()
    def cancelConn(self):
        self.conn = None
        self._rebuild()

    def _create_cables(self, src_sel, dst_sel):
        out_sel = src_sel if src_sel['side'] == 'out' else dst_sel
        in_sel = dst_sel if src_sel['side'] == 'out' else src_sel
        O, I = out_sel['idx'], in_sel['idx']
        if len(O) == len(I):
            pairs = list(zip(O, I))
        elif len(O) == 1:
            pairs = [(O[0], i) for i in I]
        elif len(I) == 1:
            pairs = [(o, I[0]) for o in O]
        else:
            pairs = list(zip(O, I))
        fid, tid, typ = str(out_sel['node']), str(in_sel['node']), src_sel['type']
        be = self._backend() if self._live_flag else None
        if not be:
            self._touch()
        have = {(w['frm'], w['to']) for w in self.gwires}
        added = False
        for o, i in pairs:
            frm = '%s:out:%s:%d' % (fid, typ, o)
            to = '%s:in:%s:%d' % (tid, typ, i)
            if (frm, to) in have:
                continue
            if be:
                # Host-first per cable: resolve port keys to graph endpoints and
                # connect; only mirror the wire on success (M5 = audio only).
                ep_f = self._endpoint_from_port_key(frm)
                ep_t = self._endpoint_from_port_key(to)
                if not ep_f or not ep_t:
                    self.toast.emit('포트 해석 실패 (오디오만 지원)')
                    continue
                err = be.connect(ep_f, ep_t)
                if err is not None:
                    self.toast.emit('연결 실패: %s' % err)
                    continue
            self.gwires.append({'id': self._new_wid(), 'frm': frm, 'to': to})
            added = True
        if be and added:
            self._touch()

    @Slot(str)
    def selectWire(self, wid):
        self.gwire_sel = None if self.gwire_sel == wid else wid
        self.sel = -1
        self._rebuild()

    @Slot()
    def removeSelectedWire(self):
        if not self.gwire_sel:
            return
        w = next((x for x in self.gwires if x['id'] == self.gwire_sel), None)
        if not w:
            return
        if self._live_flag:
            be = self._backend()
            ep_f = self._endpoint_from_port_key(w['frm'])
            ep_t = self._endpoint_from_port_key(w['to'])
            if be and ep_f and ep_t:
                err = be.disconnect(ep_f, ep_t)
                if err is not None:
                    self.toast.emit('해제 실패: %s' % err)
                    return
            self._touch()
        else:
            self._touch()
        self.gwires = [x for x in self.gwires if x['id'] != self.gwire_sel]
        self.gwire_sel = None
        self._rebuild()

    # ---------------------------------------------------- board lifecycle (Phase 2)
    def _touch(self):
        if not self._dirty:
            self._dirty = True
            self.boardsChanged.emit()

    @Slot()
    def saveBoard(self):
        """Overwrite the current board in place: re-capture the CURRENT snapshot AND
        persist the board to its .ttl bundle in one shot via presenter.save_snapshot
        (snapshot_make + save_pb_also=True). Capturing the snapshot is essential —
        board-only save leaves param/bypass/NAM edits out of the snapshot, so a
        snapshot round-trip would revert them. Inherits the app+host 3-layer
        corruption defense (the save_pb path)."""
        if not self._live_flag:
            return
        if self._scratch_default:
            # defense-in-depth: never in-place save over the shared default — QML
            # routes here via doSave() which opens the naming panel; guard the
            # direct path too.
            self.toast.emit('새 보드 — 다른 이름으로 저장하세요')
            return
        ok = self.presenter.save_snapshot() if self.presenter else False
        if ok:
            self._dirty = False
            # adopt any host-side title change (factory board -> save-new)
            pb = getattr(self.presenter, 'pedalboard', None)
            if pb is not None and pb.title:
                self.board_name = pb.title
            self.refreshBoards()
            self.snapsChanged.emit()
            self.boardsChanged.emit()
            self.toast.emit('저장됨 · %s' % self.board_name)
        else:
            self.toast.emit('저장 실패')

    @Slot(str)
    def saveBoardNamed(self, name):
        """SAVE AS = a NEW host bundle (asNew=1, corruption-immune — dir derived
        from title) that becomes the current board; adopt its title."""
        if not self._live_flag:
            return
        res = self.presenter.save_board_as(name) if self.presenter else None
        if res:
            self.board_name = res.get('title') or name
            self._dirty = False
            self._scratch_default = False   # now a real named bundle, not scratch
            self.refreshBoards()         # the new bundle is now current
            self.boardsChanged.emit()
            self.toast.emit('새 보드로 저장됨 · %s' % self.board_name)
        else:
            self.toast.emit('저장 실패')

    # ------------------------------------------------------------- demo (dev)
    @Slot()
    def demoScramble(self):
        if self.mode != 'quick':
            return
        saved = self.arcs_from_layout(self.nodes)
        for n in self.nodes:
            n['x'] = random.randint(60, CANVAS_W - NODEW - 20)
            n['y'] = random.randint(10, CANVAS_H - 70)
        self._relayout_quick(saved)
        after = self.arcs_from_layout(self.nodes)
        self._rebuild()
        self.toast.emit('웹UI 좌표 흩뜨림 → 퀵 재오픈: 라우팅 %s' %
                        ('보존됨 ✓ (체인 동일)' if saved == after else '깨짐 ✗'))
