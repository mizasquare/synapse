"""QML <-> presenter bridge (the Qt "view").

A single QObject exposed to QML as the ``view`` context property. It implements
the same method surface the presenter calls on its view (so presenter logic is
unchanged), translating those calls into QML-readable properties + a change
signal, and exposes Slots for QML->presenter events.

Stage 1 (OVERVIEW): board/snapshot/BPM/mode, the routing graph (nodes + cables)
and the footswitch status strip, all derived from the live presenter.pedalboard.
Stage 2 (FOCUS): node tap -> per-effect knobs (vertical-drag = local parameter
change), bypass toggle, IN/OUT routing. Knob drags update silently (no rebuild)
so the QML knob owns its visual during interaction without flicker.

Visual tokens (colors/fonts) live in QML; this bridge passes data + flags only.
"""

import os

from PyQt6.QtCore import QObject, pyqtProperty as Property, pyqtSignal as Signal, pyqtSlot as Slot

# Graph canvas coordinate space. MUST match the QML graph Item size
# (qml/main.qml `graph` is 776x176) -- cable paths are precomputed here in this
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
        self._screen = "overview"   # "overview" | "focus" | "taptempo"
        self._focus = {}            # FOCUS payload for QML
        self._tap = {}              # TAP TEMPO payload for QML ({bpb, klass})

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

    @Property(str, notify=dataChanged)
    def screen(self):
        return self._screen

    @Property("QVariantMap", notify=dataChanged)
    def focus(self):
        return self._focus

    @Property("QVariantMap", notify=dataChanged)
    def tap(self):
        return self._tap

    @Property("QVariantList", notify=dataChanged)
    def nodes(self):
        return self._nodes

    @Property("QVariantList", notify=dataChanged)
    def cables(self):
        return self._cables

    @Property("QVariantList", notify=dataChanged)
    def footswitches(self):
        return self._foot

    # ------------------------------------------ QML -> presenter (slots)
    @Slot(str)
    def selectNode(self, instance):
        """A graph node was tapped -> presenter builds its FOCUS payload."""
        if self.presenter and instance not in ("IN", "OUT"):
            self.presenter.view_render_parameters(instance)

    @Slot()
    def goOverview(self):
        self._screen = "overview"
        self.dataChanged.emit()

    @Slot(str, str, float)
    def setParameter(self, instance, symbol, value):
        """Knob drag -> presenter applies it (fake backend = local state)."""
        if self.presenter:
            self.presenter.parameter_changed(instance, symbol, value)

    @Slot(str, bool)
    def toggleBypass(self, instance, on):
        # presenter.parameter_changed(:bypass) refreshes the overview (node dim)
        # but does NOT touch _focus, so sync the FOCUS card's toggle here — else
        # it wouldn't flip until the effect is re-focused.
        if self._focus.get("instance") == instance:
            self._focus["bypassed"] = bool(on)
        if self.presenter:
            self.presenter.parameter_changed(instance, ":bypass", on)

    @Slot()
    def focusPrev(self):
        self._focus_step(-1)

    @Slot()
    def focusNext(self):
        self._focus_step(1)

    @Slot(int, bool)
    def footswitchKey(self, index, down):
        """Dev: keyboard (Z/X/C/V in QML) -> a fake footswitch press/release.

        Routed into the fake controller's ``set_switch`` so the poll loop turns
        it into a real debounced/chorded event. No-op on real hardware (no
        ``set_switch``), so it can stay wired without affecting the Pi build.
        """
        hwi = getattr(self.presenter, "hwi", None) if self.presenter else None
        setter = getattr(hwi, "set_switch", None)
        if setter is not None:
            setter(index, down)

    def _focus_step(self, d):
        pb = getattr(self.presenter, "pedalboard", None) if self.presenter else None
        cur = self._focus.get("instance")
        if pb is None or not cur:
            return
        fx = list(pb.effects)
        ids = [e.instance for e in fx]
        if cur not in ids:
            return
        nxt = fx[(ids.index(cur) + d) % len(fx)]
        self.presenter.view_render_parameters(nxt.instance)

    # ----------------------------------------- presenter view-method surface
    def refresh_plugin_display(self, pb_title=None, plugins=None, snapshot=None):
        # NOTE: `plugins` (presenter's pre-built (instance,name,cat,[status]) tuples)
        # is intentionally ignored -- QtView renders the graph/strip from the live
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
        # presenter.view_render_parameters -> here with effectData; build the
        # FOCUS payload and switch screens. (None == clear, not used in phase 1.)
        if effectData is None:
            self._focus = {}
        else:
            self._focus = self._build_focus(effectData)
            self._screen = "focus"
        self.dataChanged.emit()

    def update_parameter_display(self, instance, symbol, value):
        # Silent model sync (NO emit): a live knob drag must not trigger a full
        # focus rebuild/flicker. QML owns the knob visual during the drag; this
        # just keeps _focus consistent for the next full rebuild.
        if self._focus.get("instance") != instance:
            return
        for k in self._focus.get("knobs", []):
            if k["symbol"] == symbol:
                mn, mx = k["min"], k["max"]
                k["value"] = value
                k["norm"] = 0.0 if mx == mn else max(0.0, min(1.0, (value - mn) / (mx - mn)))
                k["display"] = ("%g %s" % (value, k.get("unit", ""))).strip()
                break

    def update_patch_display(self, instance, uri, file_path):
        pass  # IR/NAM file picker -- deferred (phase-1 비목표)

    def update_bpm_display(self, bpm):
        self._bpm = ("%g" % bpm) if isinstance(bpm, (int, float)) else str(bpm)
        self.dataChanged.emit()

    def update_mode_display(self, mode):
        self._mode = {0: "NAVIGATE", 1: "STOMP", 2: "RECALL", 3: "WEBUI",
                      4: "TAP TEMPO"}.get(mode, str(mode))
        self._rebuild_footswitches()
        self.dataChanged.emit()

    def show_tap_tempo(self, bpm, bpb):
        """Presenter entered tap-tempo -> switch QML to the TAP TEMPO screen."""
        self._bpm = ("%g" % bpm) if isinstance(bpm, (int, float)) else str(bpm)
        self._tap = self._build_tap(bpm, bpb)
        self._screen = "taptempo"
        self.dataChanged.emit()

    def hide_tap_tempo(self):
        """Presenter left tap-tempo -> back to the overview screen."""
        self._screen = "overview"
        self._tap = {}
        self.dataChanged.emit()

    @staticmethod
    def _build_tap(bpm, bpb):
        n = max(1, int(bpb or 4))
        klass = "WALTZ" if n % 3 == 0 else ("EVEN" if n % 2 == 0 else "ODD")
        return {"bpb": n, "klass": klass}

    # presenter also calls these; no Qt UI for them in phase 1.
    def set_abcd_availability(self, availabilities):
        pass

    def minimize(self):
        pass

    def restore(self):
        pass

    def enable_webui_button(self):
        pass

    # --------------------------------------------------------- FOCUS builder
    def _build_focus(self, d):
        inst = d.get("effect_instance", "")
        knobs = []
        for p in d.get("effect_ports", []):
            rng = p.get("port_range", {}) or {}
            mn = rng.get("min", 0.0)
            mx = rng.get("max", 1.0)
            v = p.get("port_value")
            if v is None:
                v = mn
            unit = p.get("port_unit") or ""
            norm = 0.0 if mx == mn else max(0.0, min(1.0, (v - mn) / (mx - mn)))
            knobs.append({"symbol": p["port_symbol"], "name": p["port_name"],
                          "value": v, "norm": norm, "min": mn, "max": mx, "unit": unit,
                          "display": ("%g %s" % (v, unit)).strip()})
        cat = d.get("effect_category")
        cat = cat[0] if isinstance(cat, (list, tuple)) and cat else (cat or "")
        ins, outs = self._routing_for(inst)
        patches = [{"label": pt.get("patch_label", ""), "value": self._patch_str(pt.get("patch_value"))}
                   for pt in d.get("patches", [])]
        return {"instance": inst, "name": d.get("effect_name", inst), "category": cat,
                "bypassed": bool(d.get("effect_bypassed")), "knobs": knobs,
                "inputs": ins, "outputs": outs, "patches": patches}

    @staticmethod
    def _patch_str(value):
        if isinstance(value, (list, tuple)) and value:
            return os.path.basename(str(value[0]))
        return os.path.basename(str(value)) if value else ""

    def _routing_for(self, instance):
        pb = getattr(self.presenter, "pedalboard", None) if self.presenter else None
        ins, outs = [], []
        if pb is None:
            return ["—"], ["—"]

        def label(nid):
            if nid in ("IN", "OUT"):
                return nid
            e = pb.get_effect_by_instance(nid)
            return e.name if e else nid

        seen_in, seen_out = set(), set()
        for conn in pb.connections:
            s, t = self._norm_ep(conn.source), self._norm_ep(conn.target)
            if t == instance and s != instance and s not in seen_in:
                seen_in.add(s)
                ins.append(label(s))
            if s == instance and t != instance and t not in seen_out:
                seen_out.add(t)
                outs.append(label(t))
        return (ins or ["—"]), (outs or ["—"])

    # --------------------------------------------------------- graph builder
    @staticmethod
    def _norm_ep(endpoint):
        base = endpoint.split("/")[0]
        if base.startswith("capture"):
            return "IN"
        if base.startswith("playback"):
            return "OUT"
        return base

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

        # One cable per (source-effect, target-effect) pair: stereo L/R links
        # collapse to a single schematic line, and connections whose endpoint
        # isn't a built node (e.g. a plugin skipped during the build) are dropped.
        # Intentional for the phase-1 read-only schematic; revisit for Step F.
        cables, seen = [], set()
        for conn in pb.connections:
            a, b = self._norm_ep(conn.source), self._norm_ep(conn.target)
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
        # input) must mirror presenter.assign_footswitches' selection here -- ideally
        # by having the presenter expose the 4 chosen effects -- so captions match
        # what a press toggles. Not exercised in Stage 1/2 (boots in NAVIGATE mode).
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
