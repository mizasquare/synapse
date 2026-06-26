"""Pedalboard Editor mock — Python brain exposed to QML as ``editor``.

A PyQt6 port of the Claude Design "Concept A" (free-canvas auto-routing) pedalboard
maker, plus the five additions we agreed on:

  1. Graph model        — the connection graph (arcs) is the source of truth, not x,y.
  2. layout_from_graph  — on open, positions are DERIVED from the graph (stored x,y ignored).
  3. round-trip guard    — arcs_from_layout(layout_from_graph(g)) == g  decides quick-expressibility.
  4. demo scenarios      — (a) "reopen a web-rearranged board": scramble x,y, keep arcs, re-derive
                            the SAME chain (routing survives);  (b) a parallel split-merge board that
                            is NOT quick-expressible.
  5. advanced viewer     — when the guard fails, jump straight to a read-only ADVANCED view (no
                            auto-routing) that renders the graph with its stored x,y.

Mirrors the repo's qtview.py pattern: one QObject, data + flags as notified properties, QML owns
the visual tokens. Routing math is a faithful port of the design's pb_logic.js (sort-by-x trunk,
vertical taps/sources, 1↔2 channel negotiation chips).
"""

import json
import math
import os
import random

from PyQt6.QtCore import QObject, pyqtProperty as Property, pyqtSignal as Signal, pyqtSlot as Slot

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

NODEW = 124
HALF = 27               # node visual half-height (node box ~54px tall)
CANVAS_W = 734          # 800 - 66 (rail) ; MUST match the QML canvas width
CANVAS_H = 446          # 480 - 34 (header)
IN_X = 36
OUT_X = CANVAS_W - 36
MID_Y = CANVAS_H / 2


def bcol(bucket):
    return BUCKET.get(bucket, ('#9aa3b2', ''))[0]


def abbr(bucket):
    return BUCKET.get(bucket, ('#9aa3b2', bucket[:3].upper()))[1] or bucket[:3].upper()


def pin_lbl(n):
    return '·' if n == 0 else ('M' if n == 1 else '%dch' % n)


def fmt(c, v):
    """Format a control value for display — port of pb_logic.js fmt()."""
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
    wiresChanged = Signal()   # wires + chips only (live during node drag — does not recreate nodes)
    toast = Signal(str)       # transient message for demo feedback

    def __init__(self, catalog_path=None):
        super().__init__()
        path = catalog_path or os.path.join(BASE, 'resources', 'effects-catalog.json')
        with open(path, encoding='utf-8') as fh:
            self.cat = json.load(fh)
        self.by_uri = {p['uri']: p for p in self.cat['plugins']}
        self.by_name = {p['name'].lower(): p['uri'] for p in self.cat['plugins']}

        self._uid = 0
        self.mode = 'quick'           # 'quick' | 'advanced'
        self.in_mode = 'mono'         # 'mono' | 'stereo'
        self.out_adapt = 'auto'
        self.sel = -1
        self.fly_bucket = None
        self.nodes = []               # quick-mode nodes: {id,uri,x,y,bypass,vals,inAdapt,mergeAdapt}
        self.adv_badge = ''
        self.adv_nodes = []           # advanced viewer: read-only general-graph nodes
        self.adv_wires = []

        # seed a small serial chain so the canvas isn't empty on first run
        for nm in ('bluesbreaker', 'GxCompressor', 'Bollie Delay', 'Dragonfly Hall Reverb'):
            uri = self.by_name.get(nm.lower())
            if uri:
                self._add(uri)
        self._relayout_quick()        # canonical layout from the (implicit) chain order

        # view caches (filled by _rebuild)
        self._rail = []
        self._fly = []
        self._wires = []
        self._chips = []
        self._nodes_view = []
        self._knobs = []
        self._status = ''
        self._rebuild()

    # ---------------------------------------------------------------- helpers
    def _new_id(self):
        self._uid += 1
        return self._uid

    def _add(self, uri, x=None, y=None):
        p = self.by_uri[uri]
        node = {
            'id': self._new_id(), 'uri': uri,
            'x': x if x is not None else IN_X + 90, 'y': y if y is not None else MID_Y - HALF,
            'bypass': False, 'vals': {}, 'inAdapt': 'auto', 'mergeAdapt': 'auto',
        }
        self.nodes.append(node)
        return node

    def _node(self, nid):
        for n in self.nodes:
            if n['id'] == nid:
                return n
        return None

    # ---------------------------------------------------- ADDITION 1+2+3: graph
    def _inline(self, nodes):
        """Inline fx = audio-in AND audio-out (form the serial trunk)."""
        return [n for n in nodes if self.by_uri[n['uri']]['ai'] > 0 and self.by_uri[n['uri']]['ao'] > 0]

    def arcs_from_layout(self, nodes):
        """The canonical quick-graph the auto-router PRODUCES from a layout.

        Returns a hashable structure: (trunk_uri_order, frozenset of (branch_uri, seg_index, role)).
        This is exactly what the sort-by-x router derives — so it is what gets persisted as arcs.
        """
        sorted_n = sorted(nodes, key=lambda n: n['x'])
        inline = [n for n in sorted_n if n in self._inline(nodes)]
        trunk = tuple(n['uri'] for n in inline)
        # branch attaches to the trunk segment under its x; seg count = len(inline)+1 (IN..fx..OUT)
        seg_x = [IN_X] + [n['x'] + NODEW for n in inline]  # right edge of each trunk producer
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
        """ADDITION 2: derive positions FROM the graph, ignoring any stored x,y.

        Inline fx spread evenly left->right in trunk order; branches sit above (source)
        or below (tap) the line at their segment. This is what quick-mode shows on open.
        """
        trunk, branches = qgraph
        out = []  # list of (uri, x, y, is_branch)
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

    def round_trip_ok(self, nodes):
        """ADDITION 3: a layout is quick-safe iff re-deriving it from its own graph
        reproduces the same graph. True by construction for quick-built boards."""
        g = self.arcs_from_layout(nodes)
        relaid = self.layout_from_graph(g)
        fake = [{'id': i, 'uri': u, 'x': x, 'y': y} for i, (u, x, y, _b) in enumerate(relaid)]
        return self.arcs_from_layout(fake) == g

    def _apply_layout(self, graph):
        """Position the current nodes from a graph (matching by uri occurrence)."""
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
        """Open behavior: derive canonical positions FROM the graph.

        With graph=None the graph is read off the current (still-valid) coords — a no-op
        re-tidy. The scramble demo passes the SAVED graph so the re-open ignores the
        (web-UI-mangled) coords entirely — that is the whole point of the decoupling."""
        self._apply_layout(graph if graph is not None else self.arcs_from_layout(self.nodes))

    # ------------------------------------------------ ADDITION 4+5: general graph
    @staticmethod
    def _is_quick_expressible(board):
        """Can a general arc-board be expressed as quick-mode's single trunk + pure taps/sources?

        board = {'nodes':[{id,uri,ai,ao,...}], 'arcs':[(fromId,toId)]}  (IN/OUT are terminals).
        Fails if any inline fx branches/merges among fx (the parallel case).
        """
        fx = {n['id'] for n in board['nodes'] if n['ai'] > 0 and n['ao'] > 0}
        succ, pred = {i: 0 for i in fx}, {i: 0 for i in fx}
        for a, b in board['arcs']:
            if a in fx and b in fx:
                succ[a] += 1
                pred[b] += 1
        # single chain: no fx with >1 fx-successor or >1 fx-predecessor
        return all(succ[i] <= 1 for i in fx) and all(pred[i] <= 1 for i in fx)

    # ============================================================ view rebuild
    def _route(self, nodes):
        """Auto-routing — faithful port of pb_logic.js Concept A. Returns (wires, chips, roles)."""
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
        # trunk -> HW OUT (always stereo)
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
            if ao == 0:  # TAP: line -> meter
                wires.append(vwire(mp[0], mp[1], conn_x, conn_y, '#2c3648' if n['bypass'] else '#5a6270'))
                roles[n['id']] = 'tap'
            else:        # SOURCE: meter -> line
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
            })
        return out

    def _build_inspector(self):
        self._knobs = []
        if self.sel < 0:
            return
        n = self._node(self.sel)
        if not n:
            return
        p = self.by_uri[n['uri']]
        for c in [c for c in p.get('ctl', []) if c['w'] != 'bypass'][:8]:
            v = n['vals'].get(c['sym'], c['def'])
            kind = 'toggle' if c['w'] == 'toggle' else ('enum' if c['w'] in ('enum', 'button') else 'dial')
            norm = (v - c['min']) / (c['max'] - c['min']) if c['max'] > c['min'] else 0
            self._knobs.append({
                'label': c.get('short') or c['name'], 'valueText': fmt(c, v), 'kind': kind,
                'norm': max(0.0, min(1.0, norm)), 'on': v >= 0.5, 'sym': c['sym'],
            })

    def _rebuild_wires(self):
        if self.mode != 'quick':
            return
        self._wires, self._chips, self._roles = self._route(self.nodes)
        self.wiresChanged.emit()

    def _rebuild(self):
        # rail (categories)
        self._rail = [{'key': b['key'], 'abbr': abbr(b['key']), 'color': bcol(b['key']),
                       'count': b['count'], 'sel': self.fly_bucket == b['key']} for b in self.cat['buckets']]
        # flyout effects of the chosen category
        self._fly = []
        if self.fly_bucket:
            for p in [p for p in self.cat['plugins'] if p['bucket'] == self.fly_bucket]:
                self._fly.append({'uri': p['uri'], 'name': p['name'], 'brand': p['brand'],
                                  'pins': pin_lbl(p['ai']) + '▸' + pin_lbl(p['ao'])})
        if self.mode == 'quick':
            self._wires, self._chips, self._roles = self._route(self.nodes)
            self._nodes_view = self._build_nodes_view(self._roles)
            self._build_inspector()
            chain = [abbr(self.by_uri[n['uri']]['bucket']) for n in sorted(self.nodes, key=lambda n: n['x'])
                     if self.by_uri[n['uri']]['ai'] > 0 and self.by_uri[n['uri']]['ao'] > 0]
            self._status = 'IN %s  ▸  %s  ▸  OUT STEREO' % (
                'STEREO' if self.in_mode == 'stereo' else 'L-MONO', '▸'.join(chain) if chain else '—')
        self.changed.emit()
        self.wiresChanged.emit()

    # ===================================================== properties for QML
    @Property(bool, notify=changed)
    def advanced(self):
        return self.mode == 'advanced'

    @Property(str, notify=changed)
    def advBadge(self):
        return self.adv_badge

    @Property('QVariantList', notify=changed)
    def advNodes(self):
        return self.adv_nodes

    @Property('QVariantList', notify=changed)
    def advWires(self):
        return self.adv_wires

    @Property(int, notify=changed)
    def effectCount(self):
        return self.cat['count']

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
        return len(self.nodes) == 0

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def inMode(self):
        return self.in_mode

    @Property(bool, notify=changed)
    def roundTripOK(self):
        return self.round_trip_ok(self.nodes)

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

    @Property('QVariantList', notify=changed)
    def knobs(self):
        return self._knobs

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
        # place at the end of the trunk (or off-line for pure source/sink)
        maxx = max([n['x'] for n in self.nodes], default=IN_X)
        x = min(OUT_X - NODEW - 10, maxx + 150)
        is_branch = p['ai'] == 0 or p['ao'] == 0
        y = (MID_Y + HALF) if (is_branch and p['ao'] == 0) else (MID_Y - 3 * HALF if is_branch else MID_Y - HALF)
        node = self._add(uri, x, y)
        self.sel = node['id']
        self.fly_bucket = None
        self._rebuild()

    @Slot(int, float, float)
    def nodeDragMove(self, nid, x, y):
        n = self._node(nid)
        if not n:
            return
        n['x'] = max(40, min(CANVAS_W - NODEW - 4, x))
        n['y'] = max(4, min(CANVAS_H - 58, y))
        self._rebuild_wires()   # live wires; do NOT rebuild nodes (keep the dragged delegate)

    @Slot(int, float, float, bool)
    def nodeDragEnd(self, nid, x, y, over_trash):
        n = self._node(nid)
        if not n:
            return
        if over_trash:
            self.nodes = [m for m in self.nodes if m['id'] != nid]
            if self.sel == nid:
                self.sel = -1
        else:
            n['x'] = max(40, min(CANVAS_W - NODEW - 4, x))
            n['y'] = max(4, min(CANVAS_H - 58, y))
        self._rebuild()

    @Slot(int)
    def selectNode(self, nid):
        self.sel = nid
        self._rebuild()

    @Slot()
    def closeInspector(self):
        self.sel = -1
        self._rebuild()

    @Slot(int)
    def toggleBypass(self, nid):
        n = self._node(nid)
        if n:
            n['bypass'] = not n['bypass']
            self._rebuild()

    @Slot(str, float)
    def setKnobNorm(self, sym, norm):
        n = self._node(self.sel)
        if not n:
            return
        p = self.by_uri[n['uri']]
        c = next((c for c in p['ctl'] if c['sym'] == sym), None)
        if not c:
            return
        v = c['min'] + max(0.0, min(1.0, norm)) * (c['max'] - c['min'])
        if c['w'] in ('step', 'enum'):
            v = round(v)
        n['vals'][sym] = v
        self._build_inspector()
        self.changed.emit()      # inspector only; nodes/wires unaffected by a param change

    @Slot(str)
    def toggleSwitch(self, sym):
        n = self._node(self.sel)
        if not n:
            return
        cur = n['vals'].get(sym, 0)
        n['vals'][sym] = 0 if cur >= 0.5 else 1
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
        self._build_inspector()
        self.changed.emit()

    @Slot()
    def toggleInMode(self):
        self.in_mode = 'stereo' if self.in_mode == 'mono' else 'mono'
        self._rebuild()

    @Slot(int)
    def cycleInAdapter(self, nid):
        n = self._node(nid)
        if n:
            self._cycle_adapt(n, 'inAdapt', '1to2')
            self._rebuild()

    @Slot(int)
    def cycleMergeAdapter(self, nid):
        n = self._node(nid)
        if n:
            self._cycle_adapt(n, 'mergeAdapt', '2to1')
            self._rebuild()

    @Slot()
    def cycleOutAdapter(self):
        order = ['auto', 'dup', 'L', 'R', 'sum']
        self.out_adapt = order[(order.index(self.out_adapt) + 1) % len(order)] if self.out_adapt in order else 'dup'
        self._rebuild()

    def _cycle_adapt(self, n, key, default_kind):
        # cycle among the relevant adapter modes; kind inferred at route time
        o = ['dup', 'L', 'R'] if default_kind == '1to2' else ['sum', 'L', 'R']
        cur = n.get(key, 'auto')
        n[key] = o[(o.index(cur) + 1) % len(o)] if cur in o else o[0]

    # ---------------------------------------------------- mode + demo scenarios
    @Slot(str)
    def switchMode(self, m):
        if m == 'quick':
            self.mode = 'quick'
            self._relayout_quick()   # re-derive canonical layout from the graph on (re)open
            self._rebuild()
        elif m == 'advanced':
            self._enter_advanced(self._board_from_quick(), 'QUICK 호환 — 수동 편집 모드')
            self._rebuild()

    @Slot()
    def demoScramble(self):
        """ADDITION 4a: simulate the web UI rearranging x,y (different plugin sizes), then reopen.
        Routing must survive: the re-derived chain is identical because arcs are the truth."""
        saved = self.arcs_from_layout(self.nodes)  # SAVE: persist the graph (the source of truth)
        for n in self.nodes:                       # web UI rearranges coords (different plugin sizes)
            n['x'] = random.randint(60, CANVAS_W - NODEW - 20)
            n['y'] = random.randint(10, CANVAS_H - 70)
        self._relayout_quick(saved)                # REOPEN: re-derive layout from the SAVED graph, not coords
        after = self.arcs_from_layout(self.nodes)
        before = saved
        self._rebuild()
        self.toast.emit('웹UI 좌표 흩뜨림 → 퀵 재오픈: 라우팅 %s' %
                        ('보존됨 ✓ (체인 동일)' if before == after else '깨짐 ✗'))

    @Slot()
    def demoParallel(self):
        """ADDITION 4b/5: load a board edited into a parallel split-merge topology in the web UI.
        Not quick-expressible -> jump straight to the ADVANCED viewer."""
        board = self._parallel_board()
        if self._is_quick_expressible(board):
            self.toast.emit('이 보드는 퀵 표현 가능 — 퀵 유지')
            return
        self._enter_advanced(board, 'QUICK 표현 불가 (병렬 분기-재결합) → ADVANCED 직행')
        self.toast.emit('병렬 라우팅 감지 → 자동 라우팅 없는 ADVANCED 모드로 전환')
        self._rebuild()

    # --------------------------------------------------- general-graph helpers
    def _board_from_quick(self):
        """Lift the current quick nodes into a general arc-board (for the advanced viewer)."""
        sorted_n = sorted(self.nodes, key=lambda n: n['x'])
        inline = [n for n in sorted_n if self.by_uri[n['uri']]['ai'] > 0 and self.by_uri[n['uri']]['ao'] > 0]
        nodes = [{'id': n['id'], 'uri': n['uri'], 'x': n['x'], 'y': n['y'],
                  'ai': self.by_uri[n['uri']]['ai'], 'ao': self.by_uri[n['uri']]['ao']} for n in self.nodes]
        arcs = []
        prev = 'IN'
        for n in inline:
            arcs.append((prev, n['id']))
            prev = n['id']
        arcs.append((prev, 'OUT'))
        return {'nodes': nodes, 'arcs': arcs}

    def _parallel_board(self):
        """A hand-authored parallel board: IN -> drive -> {delay, reverb} -> OUT (split + merge)."""
        def mk(name, x, y):
            uri = self.by_name.get(name.lower())
            p = self.by_uri[uri]
            return {'id': self._new_id(), 'uri': uri, 'x': x, 'y': y, 'ai': p['ai'], 'ao': p['ao']}
        drive = mk('bluesbreaker', 150, 196)
        delay = mk('Bollie Delay', 380, 96)
        reverb = mk('Dragonfly Hall Reverb', 380, 300)
        nodes = [drive, delay, reverb]
        arcs = [('IN', drive['id']), (drive['id'], delay['id']), (drive['id'], reverb['id']),
                (delay['id'], 'OUT'), (reverb['id'], 'OUT')]
        return {'nodes': nodes, 'arcs': arcs}

    def _enter_advanced(self, board, badge):
        self.mode = 'advanced'
        self.adv_badge = badge
        idx = {n['id']: n for n in board['nodes']}
        term = {'IN': (IN_X, MID_Y), 'OUT': (OUT_X, MID_Y)}
        self.adv_nodes = []
        for n in board['nodes']:
            p = self.by_uri[n['uri']]
            self.adv_nodes.append({'id': n['id'], 'x': n['x'], 'y': n['y'], 'name': p['name'],
                                   'border': bcol(p['bucket']), 'dot': bcol(p['bucket'])})
        self.adv_wires = []
        for a, b in board['arcs']:
            x1, y1 = term['IN'] if a == 'IN' else (idx[a]['x'] + NODEW, idx[a]['y'] + HALF)
            x2, y2 = term['OUT'] if b == 'OUT' else (idx[b]['x'], idx[b]['y'] + HALF)
            dx = max(28, abs(x2 - x1) / 2)
            self.adv_wires.append({'d': 'M %g %g C %g %g, %g %g, %g %g' % (
                x1, y1, x1 + dx, y1, x2 - dx, y2, x2, y2), 'color': '#3b6fe0', 'w': 2.6})
