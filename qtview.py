"""QML <-> presenter bridge (the Qt "view").

A single QObject exposed to QML as the ``view`` context property. It implements
the same method surface the presenter calls on its view (so the presenter logic
is unchanged), translating those calls into QML-readable properties + a change
signal. Read-only for Stage 1 (OVERVIEW): board name, snapshot, BPM, the routing
graph (nodes + cables) and the footswitch status strip, all derived from the
presenter's live ``pedalboard`` model (fixtures via the fake backend).

Stage 2+ adds the FOCUS screen (populate_port_area) and QML->presenter slots
(node tap, knob drag, footswitch). Visual tokens (colors/fonts) live in QML;
this bridge passes data + semantic flags only.
"""

from PySide6.QtCore import QObject, Property, Signal

# Graph canvas coordinate space. MUST match the QML graph Item size
# (qml/main.qml `graph` is 776x176) — cable paths are precomputed here in this
# pixel space, so changing one side without the other misaligns cables vs nodes.
_GW, _GH = 776.0, 176.0
_LED_BLUE, _LED_GREEN, _LED_RED, _LED_OFF = "#3b6fe0", "#5fd0a0", "#e6402e", "#2a3140"


class QtView(QObject):
    dataChanged = Signal()

    def __init__(self):
        super().__init__()
        self.presenter = None
        self._board = ""
        self._snap = "—"
        self._bpm = "—"
        self._mode = "NAVIGATE"
        self._nodes = []
        self._cables = []
        self._foot = []

    def set_presenter(self, presenter):
        self.presenter = presenter

    # ------------------------------------------------------------------ QML
    @Property(str, notify=dataChanged)
    def boardName(self):
        return self._board

    @Property(str, notify=dataChanged)
    def snapshotLabel(self):
        return self._snap

    @Property(str, notify=dataChanged)
    def bpm(self):
        return self._bpm

    @Property(str, notify=dataChanged)
    def modeLabel(self):
        return self._mode

    @Property("QVariantList", notify=dataChanged)
    def nodes(self):
        return self._nodes

    @Property("QVariantList", notify=dataChanged)
    def cables(self):
        return self._cables

    @Property("QVariantList", notify=dataChanged)
    def footswitches(self):
        return self._foot

    # ----------------------------------------- presenter view-method surface
    def refresh_plugin_display(self, pb_title=None, plugins=None, snapshot=None):
        # NOTE: `plugins` (presenter's pre-built (instance,name,cat,[status]) tuples)
        # is intentionally ignored — QtView renders the graph/strip from the live
        # presenter.pedalboard model instead. Keep bypass/assignment a single source
        # of truth (the model); don't start consuming `plugins` without retiring that.
        self._board = pb_title or ""
        if snapshot:
            idx, lst = snapshot
            name = lst.get(str(idx), "") if isinstance(lst, dict) else ""
            if idx is not None and idx >= 0:
                self._snap = ("%s · %s" % (idx, name)).strip(" ·")
            else:
                self._snap = name or "—"
        self._rebuild_graph()
        self._rebuild_footswitches()
        self.dataChanged.emit()

    def populate_port_area(self, effectData=None):
        pass  # FOCUS screen — Stage 2

    def update_parameter_display(self, instance, symbol, value):
        pass  # Stage 2

    def update_patch_display(self, instance, uri, file_path):
        pass  # Stage 2

    def update_bpm_display(self, bpm):
        self._bpm = ("%g" % bpm) if isinstance(bpm, (int, float)) else str(bpm)
        self.dataChanged.emit()

    def update_mode_display(self, mode):
        self._mode = {0: "NAVIGATE", 1: "STOMP", 2: "RECALL", 3: "WEBUI"}.get(mode, str(mode))
        self._rebuild_footswitches()
        self.dataChanged.emit()

    # presenter also calls these; no Qt UI for them in phase 1.
    def set_abcd_availability(self, availabilities):
        pass

    def minimize(self):
        pass

    def restore(self):
        pass

    def enable_webui_button(self):
        pass

    # --------------------------------------------------------- graph builder
    def _rebuild_graph(self):
        pb = getattr(self.presenter, "pedalboard", None) if self.presenter else None
        if pb is None:
            self._nodes, self._cables = [], []
            return

        effects = list(pb.effects)
        cols = len(effects) + 2  # IN + effects + OUT
        slot = _GW / cols
        center_x = lambda i: slot * i + slot / 2.0
        fx_w, fx_h, io_w, io_h = 112.0, 58.0, 60.0, 58.0

        nodes, idmap = [], {}

        def add(nid, label, sub, is_io, on, cx, w, h):
            box = {"id": nid, "label": label, "sub": sub or "", "isIo": is_io,
                   "on": bool(on), "selected": False,
                   "x": cx - w / 2.0, "y": (_GH - h) / 2.0, "w": w, "h": h}
            nodes.append(box)
            idmap[nid] = box

        add("IN", "IN", "GUITAR", True, True, center_x(0), io_w, io_h)
        for i, e in enumerate(effects):
            cat = e.category[0] if isinstance(e.category, (list, tuple)) and e.category else ""
            add(e.instance, e.name, cat, False, not e.bypassed, center_x(i + 1), fx_w, fx_h)
        add("OUT", "OUT", "STEREO", True, True, center_x(cols - 1), io_w, io_h)

        def norm(endpoint):
            base = endpoint.split("/")[0]
            if base.startswith("capture"):
                return "IN"
            if base.startswith("playback"):
                return "OUT"
            return base

        # One cable per (source-effect, target-effect) pair: stereo L/R links
        # collapse to a single schematic line, and connections whose endpoint
        # isn't a built node (e.g. a plugin skipped during the build) are dropped.
        # Intentional for the phase-1 read-only schematic; revisit for Step F.
        cables, seen = [], set()
        for conn in pb.connections:
            a, b = norm(conn.source), norm(conn.target)
            if a == b or a not in idmap or b not in idmap or (a, b) in seen:
                continue
            seen.add((a, b))
            cables.append({"path": self._cable_path(idmap[a], idmap[b]), "color": _LED_GREEN})

        self._nodes, self._cables = nodes, cables

    @staticmethod
    def _cable_path(a, b):
        x1, y1 = a["x"] + a["w"], a["y"] + a["h"] / 2.0
        x2, y2 = b["x"], b["y"] + b["h"] / 2.0
        dx = max(28.0, (x2 - x1) * 0.5)
        return "M%.1f,%.1f C%.1f,%.1f %.1f,%.1f %.1f,%.1f" % (
            x1, y1, x1 + dx, y1, x2 - dx, y2, x2, y2)

    # ---------------------------------------------------- footswitch strip
    def _rebuild_footswitches(self):
        mode = getattr(self.presenter, "footswitch_mode", 0) if self.presenter else 0
        pb = getattr(self.presenter, "pedalboard", None) if self.presenter else None
        # STOMP placeholder: shows the first four effects. The presenter actually
        # assigns toggles to a CATEGORY-FILTERED set ([0],[1],[-2],[-1] of effects
        # excluding simulator/amp/cab/utility; none if <4). Stage 3 (footswitch
        # input) must mirror presenter.assign_footswitches' selection here — ideally
        # by having the presenter expose the 4 chosen effects — so captions match
        # what a press toggles. Not exercised in Stage 1 (boots in NAVIGATE mode).
        if mode == 1 and pb is not None:  # STOMP: first four effects as toggles
            fx = list(pb.effects)
            cells = []
            for i in range(4):
                if i < len(fx):
                    e = fx[i]
                    cells.append({"label": e.name[:10],
                                  "sub": "BYPASS" if e.bypassed else "ENGAGED",
                                  "led": _LED_RED if e.bypassed else _LED_BLUE})
                else:
                    cells.append({"label": "—", "sub": "OFF", "led": _LED_OFF})
            self._foot = cells
        else:  # NAVIGATE (0) / RECALL (2): board + snapshot scroll
            self._foot = [
                {"label": "BOARD", "sub": "◄", "led": _LED_BLUE},
                {"label": "BOARD", "sub": "►", "led": _LED_BLUE},
                {"label": "SNAP", "sub": "◄", "led": _LED_GREEN},
                {"label": "SNAP", "sub": "►", "led": _LED_GREEN},
            ]
