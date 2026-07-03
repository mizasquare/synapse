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

import logging
import os
import random
import subprocess

from PyQt6.QtCore import QObject, QTimer, pyqtProperty as Property, pyqtSignal as Signal, pyqtSlot as Slot

# SAVE AS naming (tap a stage term -> "term-quirkysuffix", e.g. "Drive-cupcake").
# The stage terms are the names you actually want (song section / tone); the random
# suffix just keeps them unique so two "Drive"s don't collide. A keyboard escape
# hatch in the modal covers full-custom names.
_SNAPSHOT_TERMS = ["Clean", "Crunch", "Drive", "Lead", "Rhythm", "Solo",
                   "Verse", "Chorus", "Bridge", "Boost", "Ambient", "Heavy"]

# The suffix pool lives in an external, editable text file (one word per line).
_WORDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "resources", "snapshot_words.txt")
# Tiny built-in fallback so SAVE AS still works if the file is missing/unreadable.
_SNAPSHOT_WORDS_FALLBACK = ["chainsaw", "cupcake", "walrus", "thunder", "pickle",
                            "comet", "goblin", "biscuit", "tornado", "noodle"]
_snapshot_words = None   # process-wide cache; loaded once on first SAVE AS


def _load_snapshot_words():
    """Return the suffix word pool, loading the file once and caching it.

    This caching IS the efficiency trick: read+parse the file exactly once,
    lazily (on first SAVE AS, so app startup pays nothing), keep the list in
    memory, and let ``random.choice`` do O(1) picks. ~6k words is ~50KB -- free
    to hold. The "don't load it all" tricks (reservoir sampling, random seek)
    only earn their complexity for corpora too big for RAM, which this isn't.
    """
    global _snapshot_words
    if _snapshot_words is None:
        try:
            with open(_WORDS_PATH, "r", encoding="utf-8") as f:
                _snapshot_words = [w for w in (ln.strip() for ln in f)
                                   if w and not w.startswith("#")]
        except OSError:
            _snapshot_words = []
        if not _snapshot_words:                  # missing/empty file -> fallback
            _snapshot_words = list(_SNAPSHOT_WORDS_FALLBACK)
    return _snapshot_words

# Graph canvas coordinate space. MUST match the QML graph Item size
# (qml/main.qml `graph` is 776x176) -- cable paths are precomputed here in this
# pixel space, so changing one side without the other misaligns cables vs nodes.
_GW, _GH = 776.0, 176.0
# Snake-grid: nodes wrap every _PER_ROW columns, rows stack downward (the graph
# grows past _GH and QML scrolls vertically). Row height includes inter-row gap.
_PER_ROW = 4
_ROW_H = 100.0
_ROW_PAD = 10.0
_LED_BLUE, _LED_GREEN, _LED_RED, _LED_OFF = "#3b6fe0", "#5fd0a0", "#e6402e", "#2a3140"


class QtView(QObject):
    dataChanged = Signal()
    monitorUpdated = Signal(str, float, float, str)  # (symbol, norm, value, display): per-meter live update
    levelUpdated = Signal('QVariant')                # overview IN/OUT JACK level meter (dict payload)
    tunerUpdated = Signal('QVariant')                # tuner reading (dict payload; {} == listening)
    toastRequested = Signal(str)                     # transient on-screen message
    boardsChanged = Signal()                         # overview board-manager list changed
    banksChanged = Signal()                          # bank-manager lists changed
    masterVolumeEchoed = Signal(int)                 # synapse-volume applied-state echo (pct)

    PARAM_THROTTLE_MS = 40   # max ~25 host writes/s during a knob drag

    def __init__(self):
        super().__init__()
        self.presenter = None
        self._board = ""
        self._snap = "—"
        self._bpm = "—"
        self._mode = "NAVIGATE"
        self._nodes = []
        self._cables = []
        self._graph_h = _GH
        self._foot = []
        self._screen = "overview"   # "booting" | "overview" | "focus" | "taptempo" | "tuner" | "edit"
        self._focus = {}            # FOCUS payload for QML
        self._tap = {}              # TAP TEMPO payload for QML ({bpb, klass})
        self._board_list = []       # overview board-manager entries [{bundle,title,current}]
        self._bank_list = []        # bank-manager banks [{title,pedalboards,active}]
        self._board_catalog = []    # bank-manager add-board picker [{bundle,title}]

        # Parameter-write throttle: a knob drag fires setParameter on every
        # positionChanged (~60/s), each a blocking HTTP POST on the GUI thread.
        # Coalesce per (instance,symbol) to the latest value and flush at most
        # every PARAM_THROTTLE_MS — leading edge (first move is immediate) +
        # trailing (the release value always lands). Shared by FOCUS + editor.
        self._pending_params = {}   # (instance, symbol) -> latest value
        self._param_timer = QTimer(self)
        self._param_timer.setInterval(self.PARAM_THROTTLE_MS)
        self._param_timer.timeout.connect(self._flush_params)

        # OVERVIEW level meter: a JACK-tapping source (levelmeter.LevelMeter) is
        # polled on the GUI thread ~30 Hz and pushed to the IN/OUT nodes via
        # levelUpdated. No source -> timer never starts (off-device dev is silent).
        self._level_src = None
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(33)
        self._level_timer.timeout.connect(self._emit_levels)

        # TUNER screen: the cochlea engine (its own JACK client) is polled ~30 Hz
        # while the tuner is up, and each reading pushed to QML via tunerUpdated.
        self._tuner_src = None
        self._tuner_timer = QTimer(self)
        self._tuner_timer.setInterval(33)
        self._tuner_timer.timeout.connect(self._emit_tuner)

    def set_presenter(self, presenter):
        self.presenter = presenter

    def show_toast(self, text):
        """Presenter -> transient on-screen message (QML toast auto-hides)."""
        self.toastRequested.emit(str(text))

    def show_booting(self):
        """Entry-point splash state, shown until the MODEP host is ready (qt_main
        builds the presenter only once it answers). ``goOverview`` flips out of it."""
        self._screen = "booting"
        self.dataChanged.emit()

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

    @Property(float, notify=dataChanged)
    def graphHeight(self):
        return self._graph_h

    @Property("QVariantList", notify=dataChanged)
    def footswitches(self):
        return self._foot

    @Property("QVariantList", notify=boardsChanged)
    def boardList(self):
        return self._board_list

    @Property("QVariantList", notify=banksChanged)
    def bankList(self):
        return self._bank_list

    @Property("QVariantList", notify=banksChanged)
    def boardCatalog(self):
        return self._board_catalog

    # ------------------------------------------ QML -> presenter (slots)
    @Slot(str)
    def selectNode(self, instance):
        """A graph node was tapped -> presenter builds its FOCUS payload."""
        if self.presenter and instance not in ("IN", "OUT"):
            self.presenter.view_render_parameters(instance)

    @Slot()
    def goOverview(self):
        # Re-read the live host graph on entry so the overview always reflects the
        # running JACK graph. A structural edit in the editor (or via the web UI /
        # HMI) leaves the cached pedalboard stale otherwise — any screen that gets
        # redrawn must resync from the host (M4a dump = single source of truth).
        # Mirrors the editor's enterLive refresh.
        if self.presenter:
            try:
                self.presenter.refresh_pedalboard()
            except Exception as e:
                print(f"[view] refresh on overview failed: {e}")
        self._screen = "overview"
        self.dataChanged.emit()

    @Slot()
    def saveSnapshot(self):
        """Overwrite the current snapshot (and persist the pedalboard)."""
        if self.presenter:
            self.presenter.save_snapshot()

    @Property("QVariantList", constant=True)
    def snapshotTerms(self):
        """Stage-vocabulary grid for the SAVE AS modal."""
        return _SNAPSHOT_TERMS

    @Slot(str, result=str)
    def suggestSnapshotName(self, term):
        """A stage term + a random quirky suffix, avoiding existing snapshot names
        ("Drive-cupcake"). Re-tapping a term just re-rolls the suffix."""
        existing = set()
        if self.presenter:
            try:
                lst = self.presenter.backend.get_snapshot_list() or {}
                existing = set(lst.values()) if isinstance(lst, dict) else set(lst)
            except Exception:
                pass
        words = _load_snapshot_words()
        for _ in range(12):
            name = "%s-%s" % (term, random.choice(words))
            if name not in existing:
                return name
        return "%s-%s" % (term, random.choice(words))

    @Slot(str)
    def saveSnapshotNamed(self, name):
        """Save the current state as a NEW snapshot under the given name."""
        name = (name or "").strip()
        if self.presenter and name:
            self.presenter.save_snapshot_as(name)

    @Slot()
    def enterEdit(self):
        """Switch to the pedalboard EDIT screen (loads PedalboardEditorView via the editor bridge)."""
        self._screen = "edit"
        self.dataChanged.emit()

    # ── system power (real; the box is a standalone unit — pulling power risks SD
    #    corruption, so the UI offers a safe shutdown/reboot). Tries the session
    #    path (systemctl, works via logind/polkit) then falls back to sudo. ──
    @Slot()
    def systemShutdown(self):
        """Safely power the device off (confirmed in the UI before this is called)."""
        self._system_power("poweroff", ["shutdown", "-h", "now"], "종료")

    @Slot()
    def systemReboot(self):
        """Safely reboot the device (confirmed in the UI before this is called)."""
        self._system_power("reboot", ["reboot"], "재부팅")

    def _system_power(self, systemctl_verb, shutdown_args, label):
        log = logging.getLogger(__name__)
        log.warning("system %s requested via UI", label)
        for cmd in (["systemctl", systemctl_verb], ["sudo"] + shutdown_args):
            try:
                # A successful command takes the machine down, so this won't return;
                # a permission/availability failure returns non-zero fast -> try next.
                result = subprocess.run(cmd, timeout=15)
                if result.returncode == 0:
                    return
                log.warning("%s exited %s, trying next", cmd, result.returncode)
            except Exception as exc:  # FileNotFoundError, TimeoutExpired, ...
                log.warning("%s failed: %s", cmd, exc)
        self.toastRequested.emit(f"{label} 실패 — 권한 확인 필요 (sudo/polkit)")

    # ------------------------------------- master volume (synapse-volume daemon)
    # Pisound's ALSA PCM control is driver read-only (access=r-------), so software
    # volume can't live there. Volume authority is the synapse-volume control
    # daemon (synapse-mastervol service): it owns the taper and the jack_mix_box
    # gain stage in mod-monitor -> system:playback. This app is just one of its
    # controllers — mastervolume.MasterVolume sends raw CC commands and subscribes
    # to the applied-state echo, so the slider follows the reflex pedal too.
    # Lazily created so app startup never blocks on it.
    def _mastervol(self):
        mv = getattr(self, "_mastervol_ctl", None)
        if mv is None:
            from mastervolume import MasterVolume
            mv = self._mastervol_ctl = MasterVolume()
            # Echo ticker: the JACK RT callback only parks the value; this GUI
            # timer collects it and signals QML (same marshalling discipline as
            # the level meter). Cheap int compare -> fine to run continuously.
            t = self._mastervol_echo_timer = QTimer(self)
            t.setInterval(150)
            t.timeout.connect(self._poll_mastervol_echo)
            t.start()
        return mv

    def _poll_mastervol_echo(self):
        pct = self._mastervol_ctl.poll_echo()
        if pct is not None:
            self.masterVolumeEchoed.emit(pct)

    @Slot(result=int)
    def masterVolume(self):
        """Current master volume 0-100 (daemon echo, else last commanded), or -1
        if the volume daemon isn't reachable (service not running / no JACK)."""
        mv = self._mastervol()
        return mv.get_percent() if mv.available() else -1

    @Slot(int)
    def setMasterVolume(self, pct):
        """Command the volume daemon to pct (0-100) as a raw linear CC."""
        self._mastervol().set_percent(pct)

    @Slot()
    def refreshBoards(self):
        """Populate the overview board-manager list from the live host (call when
        the manager opens so it's fresh, not stale). default.pedalboard excluded."""
        if self.presenter:
            self._board_list = self.presenter.overview_board_entries()
            self.boardsChanged.emit()

    @Slot(str)
    def switchBoard(self, bundle):
        """Overview board manager picked a board -> switch to it (footswitch
        discipline; no-op if it is already current)."""
        if self.presenter:
            self.presenter.overview_switch_board(bundle)

    # ------------------------------------------ bank manager (QML -> presenter)
    def _push_banks(self):
        """Re-read the presenter's draft into the QML-facing lists and notify."""
        if self.presenter:
            self._bank_list = self.presenter.bank_manager_banks()
            self._board_catalog = self.presenter.bank_manager_catalog()
            self.banksChanged.emit()

    @Slot()
    def refreshBanks(self):
        """Load banks + board catalog from the host (call when the manager opens)."""
        if self.presenter:
            self.presenter.bank_manager_open()
            self._push_banks()

    @Slot(result=str)
    def suggestDateName(self):
        """Default bank name = current date-time ("YYYY-MM-DD HH:MM"). Banks are
        mostly edited at a desk (real keyboard) while planning a setlist, so a
        date stamp is a sensible starting name to keep or edit."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    @Slot(str)
    def createBank(self, title):
        if self.presenter:
            self.presenter.create_bank(title)
            self._push_banks()

    @Slot(int, str)
    def renameBank(self, idx, title):
        if self.presenter:
            self.presenter.rename_bank(idx, title)
            self._push_banks()

    @Slot(int)
    def deleteBank(self, idx):
        if self.presenter:
            self.presenter.delete_bank(idx)
            self._push_banks()

    @Slot(int)
    def setActiveBank(self, idx):
        if self.presenter:
            self.presenter.set_active_bank(idx)
            self._push_banks()

    @Slot(int, str)
    def bankAddBoard(self, idx, bundle):
        if self.presenter:
            self.presenter.bank_add_board(idx, bundle)
            self._push_banks()

    @Slot(int, int)
    def bankRemoveBoard(self, idx, boardIdx):
        if self.presenter:
            self.presenter.bank_remove_board(idx, boardIdx)
            self._push_banks()

    @Slot(int, int, int)
    def bankMoveBoard(self, idx, boardIdx, delta):
        if self.presenter:
            self.presenter.bank_move_board(idx, boardIdx, delta)
            self._push_banks()

    @Slot(str, str, float)
    def setParameter(self, instance, symbol, value):
        """Knob drag -> presenter applies it (coalesced/throttled — see _flush_params).
        Keeps only the latest value per (instance,symbol); sends the first move
        immediately, then at most every PARAM_THROTTLE_MS, and the final value on
        release (trailing flush)."""
        self._pending_params[(instance, symbol)] = value
        if not self._param_timer.isActive():
            self._param_timer.start()
            self._flush_params()      # leading edge: first move is immediate

    def _flush_params(self):
        if not self._pending_params:
            self._param_timer.stop()  # idle -> stop ticking until the next drag
            return
        pending = self._pending_params
        self._pending_params = {}
        if not self.presenter:
            return
        for (instance, symbol), value in pending.items():
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

    @Slot(str, str, result="QVariantList")
    def listPatchFiles(self, instance, uri):
        """Picker UI -> list selectable patch files for this URI ([{label,path}]).
        Discrete (not drag) so no throttle. Delegates to the presenter scan."""
        if not self.presenter:
            return []
        return self.presenter.list_patch_files(instance, uri)

    @Slot(str, str, str)
    def setPatch(self, instance, uri, path):
        """Picker chose a file -> load it on the host (NAM model / IR / cabsim).
        Routes through presenter.patch_changed, which writes via EffectPatch and
        calls back update_patch_display on success."""
        if self.presenter:
            self.presenter.patch_changed(instance, uri, path)

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
                k["norm"] = self._norm(value, mn, mx, k.get("kind", "knob"))
                k["display"] = ("%g %s" % (value, k.get("unit", ""))).strip()
                break

    def update_monitor_display(self, instance, symbol, value):
        # Live monitor (output port) value -> update only that meter. High-rate,
        # so NO full rebuild: recompute norm/display in place and emit a targeted
        # signal the matching MonitorWidget listens for (mirrors the no-emit knob
        # discipline, but monitors aren't drag-owned so they need the push).
        if not self._focus or self._focus.get("instance") != instance:
            return
        for m in self._focus.get("monitors", []):
            if m["symbol"] == symbol:
                mn, mx = m["min"], m["max"]
                kind = m.get("kind", "numeric")
                m["value"] = value
                m["norm"] = self._norm(value, mn, mx, kind)
                m["display"] = (self._meter_display(value, mn, mx) if kind == "meter"
                                else ("%g %s" % (value, m.get("unit", ""))).strip())
                self.monitorUpdated.emit(symbol, m["norm"], value, m["display"])
                break

    # ----------------------------------------------- OVERVIEW level meter
    def set_level_source(self, src):
        """Attach a JACK level source (levelmeter.LevelMeter) and start polling.

        Called from qt_main once the host is up. With no source the timer never
        runs, so off-device dev (no JACK) simply shows no level on the IN/OUT nodes.
        """
        self._level_src = src
        if src is not None:
            self._level_timer.start()

    def _emit_levels(self):
        src = self._level_src
        if src is None:
            return
        snap = src.snapshot()
        if not snap:
            return
        # Linear amplitude -> the same -60..0 dB mapping the focus-card meters use.
        def pack(amp, peak):
            return (self._norm(amp, 0.0, 1.0, "meter"),
                    self._norm(peak, 0.0, 1.0, "meter"),
                    self._meter_display(peak, 0.0, 1.0))
        in_n, in_p, in_db = pack(snap["in_amp"], snap["in_peak_amp"])
        out_n, out_p, out_db = pack(snap["out_amp"], snap["out_peak_amp"])
        self.levelUpdated.emit({
            "inNorm": in_n, "inPeak": in_p, "inDb": in_db,
            "outNorm": out_n, "outPeak": out_p, "outDb": out_db,
        })

    # -- tuner screen (cochlea engine polling; mirrors the level-meter feed) ----
    IN_TUNE_CENTS = 3.0    # |cents| under this reads as in-tune (green)

    def show_tuner(self, engine):
        """Presenter entered the tuner -> poll the engine and switch to the screen."""
        self._tuner_src = engine
        self._tuner_timer.start()
        self._screen = "tuner"
        self.dataChanged.emit()

    def hide_tuner(self):
        """Presenter left the tuner -> stop polling, back to overview."""
        self._tuner_timer.stop()
        self._tuner_src = None
        self._screen = "overview"
        self.dataChanged.emit()

    def _emit_tuner(self):
        src = self._tuner_src
        if src is None:
            return
        r = src.get_reading()
        if r is None:
            self.tunerUpdated.emit({})           # nothing detected -> "listening"
            return
        self.tunerUpdated.emit({
            "note": r.note, "cents": r.cents, "freq": r.freq_hz,
            "ideal": r.ideal_hz, "confidence": r.confidence,
            "string": r.string, "inTune": abs(r.cents) < self.IN_TUNE_CENTS,
        })

    def update_patch_display(self, instance, uri, file_path):
        # A patch file was loaded (by us via setPatch, or externally via the
        # reverse channel). Patches aren't drag-owned (discrete pick), so unlike
        # knobs a full focus rebind is safe: mutate the cached value in place and
        # emit dataChanged. NO host re-fetch (we already know the new file).
        if not self._focus or self._focus.get("instance") != instance:
            return
        base = os.path.basename(file_path) if file_path else ""
        for pt in self._focus.get("patches", []):
            if pt.get("uri") == uri:
                pt["value"] = base
                break
        self.dataChanged.emit()

    def update_bpm_display(self, bpm):
        self._bpm = ("%g" % bpm) if isinstance(bpm, (int, float)) else str(bpm)
        self.dataChanged.emit()

    def update_mode_display(self, mode):
        self._mode = {0: "NAVIGATE", 1: "STOMP", 2: "BANK",
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

    # --------------------------------------------------------- FOCUS builder
    @staticmethod
    def _norm(v, mn, mx, kind="knob"):
        if mn is None or mx is None or mx == mn:
            return 0.0
        if kind == "knob_log" and mn > 0 and mx > 0 and v > 0:
            import math
            return max(0.0, min(1.0, math.log(v / mn) / math.log(mx / mn)))
        if kind == "meter":
            # Level meters emit LINEAR amplitude (≈0..1). A plain linear bar makes a
            # -37 dB signal fill ~1% of its height = looks dead. Map to dB like MOD's
            # modmeter skin so quiet signals are visible. Floor -60 dB, ceiling 0 dB.
            import math
            span = (mx - mn) or 1.0
            amp = max(0.0, (v - mn) / span)
            if amp <= 1e-6:
                return 0.0
            return max(0.0, min(1.0, (20.0 * math.log10(amp) + 60.0) / 60.0))
        return max(0.0, min(1.0, (v - mn) / (mx - mn)))

    @staticmethod
    def _meter_display(v, mn, mx):
        """Linear amplitude -> 'NN.N dB' readout (matches the dB-mapped meter bar)."""
        import math
        span = (mx - mn) or 1.0
        amp = max(0.0, (v - mn) / span)
        return "-inf dB" if amp <= 1e-6 else "%.1f dB" % (20.0 * math.log10(amp))

    @staticmethod
    def _enum_options(p):
        """scale_points -> [{value,label}] for enum selectors; [] otherwise.
        Handles both real mod-ui dict form ({value,label}) and tuple form."""
        out = []
        for sp in (p.get("port_scalepoints") or []):
            try:
                if isinstance(sp, dict):
                    out.append({"value": float(sp["value"]), "label": str(sp["label"])})
                else:
                    out.append({"value": float(sp[0]), "label": str(sp[1])})
            except (TypeError, ValueError, IndexError, KeyError):
                pass
        return out

    def _focus_entry(self, p, default_kind):
        rng = p.get("port_range", {}) or {}
        mn = rng.get("min", 0.0)
        mx = rng.get("max", 1.0)
        v = p.get("port_value")
        if v is None:
            v = mn
        unit = p.get("port_unit") or ""
        kind = p.get("port_kind", default_kind)
        opts = self._enum_options(p) if kind == "enum" else []
        display = ("%g %s" % (v, unit)).strip()
        if kind == "enum":  # show the matching option label, not the raw number
            match = next((o for o in opts if abs(o["value"] - v) < 1e-6), None)
            if match:
                display = match["label"]
        elif kind == "meter":
            display = self._meter_display(v, mn, mx)
        return {"symbol": p["port_symbol"], "name": p["port_name"],
                "value": v, "norm": self._norm(v, mn, mx, kind), "min": mn, "max": mx,
                "unit": unit, "kind": kind, "options": opts, "display": display}

    def _build_focus(self, d):
        inst = d.get("effect_instance", "")
        knobs = [self._focus_entry(p, "knob") for p in d.get("effect_ports", [])]
        monitors = [self._focus_entry(p, "numeric") for p in d.get("effect_monitors", [])]
        cat = d.get("effect_category")
        cat = cat[0] if isinstance(cat, (list, tuple)) and cat else (cat or "")
        ins, outs = self._routing_for(inst)
        patches = [{"label": pt.get("patch_label", ""), "value": self._patch_str(pt.get("patch_value")),
                    "uri": pt.get("patch_uri", "")}
                   for pt in d.get("patches", [])]
        return {"instance": inst, "name": d.get("effect_name", inst), "category": cat,
                "bypassed": bool(d.get("effect_bypassed")), "knobs": knobs, "monitors": monitors,
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
            self._graph_h = _GH
            return

        effects = list(pb.effects)
        # Snake-grid: nodes flow L->R on even rows, R->L on odd rows, wrapping
        # every _PER_ROW columns and stacking downward (QML scrolls vertically).
        cell_w = _GW / _PER_ROW
        fx_w, fx_h, io_w, io_h = 170.0, 72.0, 104.0, 72.0

        # (id, label, sub, is_io, on, w, h) in signal order: IN -> effects -> OUT
        order = [("IN", "IN", "GUITAR", True, True, io_w, io_h)]
        for e in effects:
            cat = e.category[0] if isinstance(e.category, (list, tuple)) and e.category else ""
            order.append((e.instance, e.name, cat, False, not e.bypassed, fx_w, fx_h))
        order.append(("OUT", "OUT", "STEREO", True, True, io_w, io_h))

        nodes, idmap = [], {}
        for idx, (nid, label, sub, is_io, on, w, h) in enumerate(order):
            row = idx // _PER_ROW
            col = idx % _PER_ROW
            vcol = col if row % 2 == 0 else (_PER_ROW - 1 - col)  # snake
            cx = cell_w * vcol + cell_w / 2.0
            cy = _ROW_PAD + row * _ROW_H + _ROW_H / 2.0
            box = {"id": nid, "label": label, "sub": sub or "", "isIo": is_io,
                   "on": bool(on), "selected": False, "row": row,
                   "x": cx - w / 2.0, "y": cy - h / 2.0, "w": w, "h": h}
            nodes.append(box)
            idmap[nid] = box

        n_rows = (len(order) + _PER_ROW - 1) // _PER_ROW
        self._graph_h = 2 * _ROW_PAD + n_rows * _ROW_H

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
        # Same row -> horizontal bezier between the facing side-ports; different
        # row -> vertical bezier (the snake's U-turn) between bottom/top ports.
        # Direction a->b is preserved (M starts at a's exit port).
        if a["row"] == b["row"]:
            if a["x"] <= b["x"]:           # a is left of b
                x1, x2 = a["x"] + a["w"], b["x"]
            else:                          # a is right of b
                x1, x2 = a["x"], b["x"] + b["w"]
            y1 = a["y"] + a["h"] / 2.0
            y2 = b["y"] + b["h"] / 2.0
            dx = max(28.0, abs(x2 - x1) * 0.5)
            cx1 = x1 + dx if x2 >= x1 else x1 - dx
            cx2 = x2 - dx if x2 >= x1 else x2 + dx
            return "M%.1f,%.1f C%.1f,%.1f %.1f,%.1f %.1f,%.1f" % (
                x1, y1, cx1, y1, cx2, y2, x2, y2)
        # vertical U-turn between rows
        x1 = a["x"] + a["w"] / 2.0
        x2 = b["x"] + b["w"] / 2.0
        if a["y"] <= b["y"]:               # a above b
            y1, y2 = a["y"] + a["h"], b["y"]
        else:                              # a below b
            y1, y2 = a["y"], b["y"] + b["h"]
        dy = max(24.0, abs(y2 - y1) * 0.5)
        cy1 = y1 + dy if y2 >= y1 else y1 - dy
        cy2 = y2 - dy if y2 >= y1 else y2 + dy
        return "M%.1f,%.1f C%.1f,%.1f %.1f,%.1f %.1f,%.1f" % (
            x1, y1, x1, cy1, x2, cy2, x2, y2)

    # ---------------------------------------------------- footswitch strip
    def _rebuild_footswitches(self):
        mode = getattr(self.presenter, "footswitch_mode", 0) if self.presenter else 0
        pb = getattr(self.presenter, "pedalboard", None) if self.presenter else None
        # STOMP: the presenter binds FS0-3 to a CATEGORY-FILTERED set ([0],[1],[-2],[-1]
        # of effects excluding simulator/amp/cab/utility; none if <4) and exposes those
        # exact 4 as presenter.stomp_effects. Read it here so captions match precisely
        # what a press toggles (same pattern as bank_boards for mode 2). The Effect
        # objects are live, so e.bypassed reflects the current ENGAGED/BYPASS state.
        if mode == 1:  # STOMP: presenter's chosen four effects as toggles
            fx = getattr(self.presenter, "stomp_effects", []) if self.presenter else []
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
        elif mode == 2:  # BANK: the active bank's first 4 boards mapped to FS0-3
            boards = getattr(self.presenter, "bank_boards", []) if self.presenter else []
            cur = getattr(pb, "current_pb_path", None) if pb else None
            cells = []
            for i in range(4):
                if i < len(boards):
                    b = boards[i]
                    name = b.get("title") or b.get("bundle", "").split("/")[-1].replace(".pedalboard", "")
                    is_cur = b.get("bundle") == cur
                    cells.append({"label": name[:12],
                                  "sub": "● 현재" if is_cur else "BOARD",
                                  "led": _LED_GREEN if is_cur else _LED_BLUE})
                else:
                    cells.append({"label": "—", "sub": "OFF", "led": _LED_OFF})
            self._foot = cells
        else:  # NAVIGATE (0): board + snapshot scroll
            self._foot = [
                {"label": "BOARD", "sub": "◄", "led": _LED_BLUE},
                {"label": "BOARD", "sub": "►", "led": _LED_BLUE},
                {"label": "SNAP", "sub": "◄", "led": _LED_GREEN},
                {"label": "SNAP", "sub": "►", "led": _LED_GREEN},
            ]
