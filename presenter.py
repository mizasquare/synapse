from collections import defaultdict
import utils
from modepctrl import get_backend
from model import initialize_modep_pedalboard, Connection, diff_live_graph
from taptempo import TapTempoEngine
import subprocess
import threading
import time

import json
import logging
import os
import configs
from configs import LOCAL_STORAGE

# Footswitch mode ids. 0-2 are the press-driven modes cycled by modechange();
# 3 (WebUI) and 4 (tap tempo) are transient modes entered out-of-band (button /
# chord) and kept out of that cycle.
TAP_TEMPO_MODE = 4

# Tuner LED feedback (the 4 footswitch LEDs strobe while tuning, so you can tune
# eyes-off the screen): off-pitch = a red strobe that speeds up as the note nears
# pitch; the moment it lands = a short blue flourish, then steady blue. Silence
# (engine gates on volume/confidence) = LEDs off.
TUNER_IN_TUNE_CENTS = 3.0
TUNER_FAR_CENTS = 50.0
TUNER_LED_TICK_HZ = 30.0
TUNER_BLINK_SLOW_HZ = 2.0     # far from pitch -> slow red blink
TUNER_BLINK_FAST_HZ = 10.0    # near pitch -> fast, "nervous" red blink
TUNER_CEREMONY_SEC = 0.5      # length of the blue flourish on hitting pitch

class Presenter:
    def __init__(self, view, scheduler, backend=None, hardware=None,
                 tuner_source_factory=None):
        self.view = view
        # scheduler: event-loop timer abstraction (see scheduler.Scheduler).
        # Keeps the presenter and hardware layer free of any GUI-framework import.
        self.scheduler = scheduler
        # backend: MODEP host seam (see modepctrl.get_backend). Defaults to the
        # real ModepController; an off-device entry point injects a fake.
        self.backend = backend if backend is not None else get_backend()
        # hardware: footswitch/LED seam (see hardware.HardwareController).
        # Defaults to the real I2C controller, built lazily so an off-device
        # entry point can inject a fake without importing the Pi-only I2C stack.
        self.hwi = hardware if hardware is not None else self._build_default_hardware(scheduler)

        # 0: pedalboard nav, 1: parameter assign, 2: pb snapshot assign
        self.footswitch_mode = 0
        self.footswitch_assigns = [None, None, None, None]
        self.footswitch_combo_assigns = {}
        self.footswitch_input_que = [0] * 4
        # Tap-tempo engine (the C+D chord enters it; see handle_multiple_footswitches).
        # Framework-agnostic: it only needs the scheduler + the two callbacks below.
        self._mode_before_tap = 0
        self.tap_tempo = TapTempoEngine(
            self.scheduler, on_bpm=self._tap_on_bpm, on_beat=self._tap_on_beat)
        # Guitar tuner (cochlea): the B+C chord enters it; an on-demand audio
        # engine (its own JACK client on capture_1) runs only while the tuner
        # screen is up. An off-device entry point can inject a synthetic audio
        # source via tuner_source_factory (else the real JackSource is used).
        self._tuner_source_factory = tuner_source_factory
        self._tuner_engine = None
        self._in_tuner = False
        # LED-feedback strobe state (see TUNER_* constants + _tuner_led_tick).
        self._tuner_led_handle = None
        self._tuner_led_phase = 0.0
        self._tuner_led_state = None
        self._tuner_was_in_tune = False
        self._tuner_tune_since = 0.0
        self._poll_thread = None
        self._poll_stop = None
        self.start_footswitch_polling(100)  # background thread @100Hz

        # Load pedalboard model
        self.pedalboard = initialize_modep_pedalboard(self.backend)
        # EditorBridge ref (wired by the entry point) so footswitch board nav can
        # surface a non-blocking notice when it discards unsaved live editor edits.
        self.editor = None
        # pb별 마지막 활성 스냅샷 기억 (세션 한정 인메모리). key=current_pb_path, value=snapshot idx
        self.pb_snapshot_memory = {}
        # Footswitch-mode-2 (RECALL) pedalboard+snapshot assignments, keyed "0".."3".
        # Loaded from disk so they persist across runs; defaults guarantee all four
        # keys exist. Key names ("pedalboard"/"snapshot_idx") match the writer
        # (assign_pb_ss_to_footswitch) and reader (recall_pb_ss) below.
        self.fs_assignment_data = utils.load_footswitch_assignments() or {}
        for i in range(4):
            self.fs_assignment_data.setdefault(str(i), {
                "pedalboard": None,
                "snapshot_idx": None,
            })

        # Mode-2 BANK selector: the active bank's first 4 boards map to FS0-3.
        # current_bank is driven by the bank manager (set_active_bank); it picks
        # which bank mode-2 uses. bank_boards is the live [{bundle,title}] strip.
        # Held across restarts (utils.app_state) to mirror MOD's HMI bank hold.
        self.current_bank = utils.load_last_bank()
        self.bank_boards = []

        # Mode-1 STOMP: the 4 category-filtered effects bound to FS0-3. Exposed so
        # the QtView strip captions mirror exactly what a press toggles (kept in
        # sync by assign_footswitches, same lifecycle as bank_boards).
        self.stomp_effects = []

        self.assign_footswitches()
        self.boot_lightshow()

    @staticmethod
    def _build_default_hardware(scheduler):
        """Construct the real I2C footswitch/LED controller.

        Imported lazily (not at module load) so off-device entry points that
        inject a fake never import the Pi-only I2C stack (hardwares.* -> smbus2,
        which needs fcntl + a real /dev/i2c). On the Pi this still fails loud if
        the hardware is absent/faulty -- selection is explicit, never silent.
        """
        from hardwares import fsledctrl
        return fsledctrl.Controller(scheduler)

    def initiate_view(self):
        self.view_update_effect()
        self.view_update_bpm()

    def set_beat(self, bpb=None, bpm=None):
        if bpb:
            error_msg = self.backend.set_bpb(bpb)
            if error_msg is None:
                self.pedalboard.bpb = bpb
            else:
                print(error_msg)
        if bpm:
            error_msg = self.backend.set_bpm(bpm)
            if error_msg is None:
                self.pedalboard.bpm = bpm
            else:
                print(error_msg)

    def refresh_pedalboard(self):
        self.pedalboard = initialize_modep_pedalboard(self.backend)
        self.view_update_effect()

    def _audit_desync(self, context):
        """Detect (don't fix) cached-model vs live-host drift and log it.

        Called at save boundaries: the model is normally kept fresh by the
        synapsin reverse channel, so any drift caught here means that channel
        dropped an event (or died) and we were holding stale state. The save
        itself is safe regardless — the host serializes its OWN live graph — and
        the caller's existing refresh_pedalboard() reconciles the model. This
        only makes the otherwise-silent desync VISIBLE in the logs. Must run
        BEFORE refresh (which rebuilds the model and erases the drift).

        Best-effort: a missing/failed live graph is not drift, and any failure
        here never blocks the save. Returns the drift list (for tests/callers)."""
        try:
            live = self.backend.dump_graph()
        except Exception as e:
            logging.debug("desync audit (%s): dump_graph failed: %s", context, e)
            return []
        drift = diff_live_graph(self.pedalboard, live)
        if drift:
            logging.warning("DESYNC at %s: reverse channel may be stale — %d drift(s): %s",
                            context, len(drift), "; ".join(drift))
        return drift

    # ── pb별 마지막 스냅샷 기억/복원 (세션 한정, 풋스위치 PB전환에서만 복원) ──
    def _remember_current_snapshot(self):
        """떠나는 페달보드의 '지금' 스냅샷을 host 기준으로 직접 읽어 기억한다.
        self.pedalboard.current_snapshot_idx 는 마지막 refresh 시점 값이라
        HMI/웹 변경이 아직 안 들어와 있을 수 있으므로 host에 직접 물어본다."""
        pb = self.pedalboard.current_pb_path
        idx = self.backend.snapshot_current_idx()   # host = ground truth, 못 맞추면 -1
        if pb and idx is not None and idx >= 0:
            self.pb_snapshot_memory[pb] = idx

    def _restore_snapshot_for_current_pb(self):
        """방금 로드된 페달보드에 대해 기억해 둔 스냅샷이 있으면 복원한다.
        번들이 이미 그 스냅샷을 띄웠으면(=같은 idx) 아무것도 안 함 → 불필요한
        load_snapshot/에코/refresh 방지. list_of_snapshots 는 {"0":name,...} dict
        (HTTP실패 시 [])이므로 멤버십(str(idx) in ...)으로 유효성 확인 — 삭제로 인한
        sparse 인덱스에도 안전."""
        pb = self.pedalboard.current_pb_path
        if not pb:
            return
        idx = self.pb_snapshot_memory.get(pb)
        if idx is None:
            return
        if str(idx) not in self.pedalboard.list_of_snapshots:
            return
        if idx == self.pedalboard.current_snapshot_idx:
            return
        self.backend.load_snapshot(idx)
        self.refresh_pedalboard()   # current_snapshot_idx 를 host 기준으로 재확정

    def view_update_effect(self, clear_ports=False):
        if clear_ports:
            self.view.populate_port_area(effectData=None)

        plugins = []
        for effect in self.pedalboard.effects:
            bypass_status = "active"
            if effect.bypassed:
                bypass_status = "bypassed"
            # category can be an empty list (e.g. dragonfly-reverb declares none) —
            # don't assume [0] exists, or the whole overview refresh aborts.
            category = effect.category[0] if isinstance(effect.category, (list, tuple)) and effect.category else "Unknown"
            plugins.append((effect.instance, effect.name, category, [bypass_status, "unassigned"]))

        self.view.refresh_plugin_display(pb_title=self.pedalboard.title, plugins=plugins,
                                         snapshot=[self.pedalboard.current_snapshot_idx, self.pedalboard.list_of_snapshots])

    def view_render_parameters(self, effect_instance):
        effect = self.pedalboard.get_effect_by_instance(effect_instance)
        if not effect:
            return

        effectData = self._build_view_effect(effect)
        self.view.populate_port_area(effectData=effectData)

    def view_mode_change(self, mode):
        pass

    def view_update_footsw_display(self, updated_data):
        pass

    def parameter_changed(self, effect_instance, port_symbol, port_value):
        if port_symbol == ":bypass":
            error_msg = self.backend.bypass_effect(effect_instance, port_value)
            if error_msg is None:
                self.pedalboard.get_effect_by_instance(effect_instance).bypassed = port_value
                self.view_update_effect()
            else:
                print(error_msg)

        effect = self.pedalboard.get_effect_by_instance(effect_instance)
        if effect and port_symbol in effect.ports:
            error_msg = self.backend.parameter_set(effect_instance, port_symbol, port_value)
            if error_msg is None:
                effect.ports[port_symbol].value = port_value  # keep model in sync (was set_value's job)
                self.view.update_parameter_display(effect_instance, port_symbol, port_value)  # Instead of full refresh
            else:
                print(f"⚠️ Failed to update {port_symbol}: {error_msg}")

    def patch_changed(self, plugin_instance, patch_uri, patch_file):
        effect = self.pedalboard.get_effect_by_instance(plugin_instance)
        if effect and patch_uri in effect.patches:
            error_msg = self.backend.patch_set(plugin_instance, patch_uri, patch_file)
            if error_msg is None:
                effect.patches[patch_uri].value = patch_file  # keep model in sync (was set_patch's job)
                self.view.update_patch_display(plugin_instance, patch_uri, patch_file)  # More efficient
            else:
                print(f"⚠️ Failed to load patch for {plugin_instance}: {error_msg}")

    # ── 역방향 채널 (mod-ui notify_synapsin → /tmp/synapsin.sock → qt_main.py → 여기) ──
    # 웹UI/HMI 등 앱 바깥에서 일어난 변화를 desync 없이 앱 화면에 반영한다.
    # 수신 전용: host로 절대 되쏘지 않는다(피드백 루프 방지).
    def handle_reverse_event(self, message):
        try:
            cmd, _, rest = message.partition(" ")
            if cmd == "EffectParameterSet":
                # 포맷: "EffectParameterSet /graph/<instance>/<symbol>, <value>"
                port_part, _, value_str = rest.rpartition(",")
                instance_path, _, symbol = port_part.strip().rpartition("/")
                instance = instance_path.split("/graph/", 1)[-1].lstrip("/")
                self.apply_external_parameter(instance, symbol, float(value_str.strip()))
            elif cmd == "EffectPatchSet":
                # 포맷: "EffectPatchSet <instance> <patch_uri> <file_path>"
                # file_path는 공백/콤마 포함 가능 → 앞 2개만 분리, 뒤는 통째로.
                instance_path, _, rest2 = rest.partition(" ")
                patch_uri, _, patch_file = rest2.partition(" ")
                instance = instance_path.split("/graph/", 1)[-1].lstrip("/")
                self.apply_external_patch(instance, patch_uri, patch_file)
            elif cmd == "SnapshotLoad":
                # 모든 /snapshot/load 가 여기로 에코됨(앱 FS2/FS3, 웹UI, save_as).
                # pb별 마지막 스냅샷을 연속 기록 → 나중에 그 pb로 풋스위치 복귀 시 복원.
                pb_before = self.pedalboard.current_pb_path
                self.refresh_pedalboard()                      # 기존 동작 유지(전체 재동기화)
                # 에코가 PB 전환 경계를 넘어왔으면(현재 pb != 에코 당시 pb) 기록 안 함
                # → A보드 스냅샷이 B보드 키로 잘못 기록되는 비동기 레이스 방지.
                if self.pedalboard.current_pb_path == pb_before:
                    try:
                        idx = int(rest.strip())
                    except (TypeError, ValueError):
                        idx = self.pedalboard.current_snapshot_idx
                    pb = self.pedalboard.current_pb_path
                    if pb and str(idx) in self.pedalboard.list_of_snapshots:
                        self.pb_snapshot_memory[pb] = idx
            elif cmd in ("EffectConnect", "EffectDisconnect"):
                # 배선 변경은 라이브 호스트 그래프에서만 일어남 — /pedalboard/info(=refresh_
                # pedalboard 의 소스)는 디스크 번들 .ttl 을 읽으므로 저장 전엔 새 케이블을 모름.
                # → 디스크 재조회 대신 메시지의 두 포트로 모델 connections 에 델타를 직접 적용
                #   (파라미터/패치의 apply_external_* 와 같은 패턴). 포트는 /graph/ 접두를 떼면
                #   디스크 connection 포맷(예: "Click/out", "playback_2")과 일치한다.
                a, _, b = rest.partition(",")
                src = a.strip().split("/graph/", 1)[-1].lstrip("/")
                tgt = b.strip().split("/graph/", 1)[-1].lstrip("/")
                self.apply_external_connection(cmd == "EffectConnect", src, tgt)
            elif cmd in ("EffectAdd", "EffectRemove", "PedalboardLoadBundle",
                         "SnapshotName", "SnapshotRemove", "BankLoad"):
                # 구조 변경 → 안전하게 전체 재동기화
                # (웹발 PedalboardLoadBundle 은 복원 안 함: mod-ui 번들 저장 스냅샷 기본동작 유지)
                # ★한계: EffectAdd/Remove 도 저장 전엔 디스크에 없어 refresh 가 stale 일 수 있음
                #   (connect/disconnect 처럼 델타 적용하려면 플러그인 메타 조회 필요 — 추후).
                self.refresh_pedalboard()
            else:
                print(f"[reverse] unhandled: {message}")
        except Exception as e:
            print(f"[reverse] parse error on {message!r}: {e}")

    def apply_external_parameter(self, instance, symbol, value):
        """외부에서 바뀐 파라미터를 모델 캐시 + 화면에 반영(네트워크 호출 없음)."""
        effect = self.pedalboard.get_effect_by_instance(instance)
        if not effect:
            return
        if symbol == ":bypass":
            effect.bypassed = value >= 0.5
            self.view_update_effect()                                    # 리스트 O 표시 갱신
            self.view.update_parameter_display(instance, symbol, value)  # 포트영역 Bypass 스위치 갱신
            return
        port = effect.ports.get(symbol)
        if port is not None:
            port.value = value  # 캐시만 갱신
            self.view.update_parameter_display(instance, symbol, value)

    def update_monitor(self, instance, symbol, value):
        """Live monitor (output port) value from the feed — GUI thread only.
        Updates the cached EffectPort + pushes to the view (no host call)."""
        pb = self.pedalboard
        if pb is None:
            return
        effect = pb.get_effect_by_instance(instance)
        if not effect:
            return
        mon = effect.monitors.get(symbol)
        if mon is None:
            return
        mon.value = value
        self.view.update_monitor_display(instance, symbol, value)

    def apply_external_patch(self, instance, patch_uri, patch_file):
        """외부에서 바뀐 패치파일(IR/NAM/cabsim 등)을 모델 캐시 + 화면에 반영(host 되쏨 없음)."""
        effect = self.pedalboard.get_effect_by_instance(instance)
        if not effect:
            return
        patch = effect.patches.get(patch_uri)
        if patch is not None:
            patch.value = patch_file  # 캐시만 갱신 (set_patch는 host로 쓰므로 호출 안 함)
        self.view.update_patch_display(instance, patch_uri, patch_file)

    def list_patch_files(self, instance, patch_uri):
        """패치(NAM/IR/캐비닛) URI에 매핑된 user-files 디렉터리를 재귀 스캔해 선택 가능한
        파일을 [{label, path}]로 반환. label = base_dir 기준 상대경로(중첩 폴더가
        'Marshall JCM2000/foo.nam'처럼 읽힘). 패치가 fileTypes를 선언하면 확장자로
        걸러냄(대소문자 무시). qtview·editor_bridge 공용 단일 소스."""
        base = configs.PATCH_FILE_DIR_MAP.get(
            patch_uri, configs.PATCH_FILE_DIR_MAP.get("defaultpath"))
        if not base or not os.path.isdir(base):
            return []
        # fileTypes는 확장자가 아니라 카테고리명('nammodel'…) → 확장자로 변환.
        # 매핑에 없는 카테고리는 exts에 기여 안 함 → 필터 없이 디렉터리 전체.
        exts = []
        effect = self.pedalboard.get_effect_by_instance(instance) if self.pedalboard else None
        patch = effect.patches.get(patch_uri) if effect else None
        for t in (patch.file_types if patch else []):
            exts += configs.PATCH_FILE_TYPE_EXTS.get(str(t).lower(), [])
        out = []
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if fn.startswith("."):           # skip dotfiles / OS junk
                    continue
                if exts and os.path.splitext(fn)[1].lower() not in exts:
                    continue
                full = os.path.join(root, fn)
                out.append({"label": os.path.relpath(full, base), "path": full})
        out.sort(key=lambda e: e["label"].lower())
        return out

    def apply_external_connection(self, connected, source, target):
        """외부(웹/HMI)에서 바뀐 배선을 모델 connections 에 직접 반영(디스크/host 미조회).
        /pedalboard/info 는 디스크 번들을 읽어 저장 전 라이브 배선을 모르므로, 메시지의 두
        포트로 그래프만 갱신한다. source/target 은 /graph/ 를 뗀 디스크 포맷."""
        conns = self.pedalboard.connections
        existing = next((c for c in conns if c.source == source and c.target == target), None)
        if connected:
            if existing is None:
                conns.append(Connection(source, target))
        elif existing is not None:
            conns.remove(existing)
        self.view_update_effect()   # _rebuild_graph 가 connections 로 케이블 다시 그림

    def _return_to_overview(self):
        """Leave any stale FOCUS card after a footswitch pedalboard change.

        The focused effect may not exist in the new board, and even a same-named
        plugin is a different instance with severed connections -- so the FOCUS
        card would dangle. Guarded (getattr) so a view that doesn't expose
        goOverview is a no-op rather than a crash."""
        go = getattr(self.view, "goOverview", None)
        if callable(go):
            go()

    def _warn_if_editor_dirty(self):
        """Non-blocking notice that a footswitch board change is about to discard
        unsaved live editor edits. The footswitch is a performance control and
        NEVER blocks with a dialog (unlike the editor's own BOARD switcher, which
        confirms) — this just surfaces the loss. The editor re-seeds from the new
        live board on its next entry. (Covers edits-since-last-seed; re-entering
        the editor rebaselines _dirty, so an edit→reenter→footswitch path won't
        warn — a known limitation of the seed-relative dirty model.)"""
        ed = self.editor
        if ed is not None and getattr(ed, '_live_flag', False) and getattr(ed, '_dirty', False):
            self._notify('보드 전환 — 미저장 편집 폐기')

    def _notify(self, text):
        """Transient on-screen message (toast). Guarded so a view without
        show_toast just logs instead of crashing."""
        print(text)
        toast = getattr(self.view, "show_toast", None)
        if callable(toast):
            toast(text)

    def _switch_to_bundle(self, bundle, return_to_overview=True):
        """Shared board-switch discipline for BOTH footswitch nav and the editor
        live switcher, so remember/restore-snapshot can never diverge between the
        two paths. Returns True on success.

        On a failed load (backend.set_pedalboard False) it does NOT refresh /
        restore / change screens: /reset already wiped the live graph, so the
        caller must surface the failure rather than resync to an empty board."""
        self._remember_current_snapshot()
        if not self.backend.set_pedalboard(bundle):
            return False
        self.refresh_pedalboard()
        self._restore_snapshot_for_current_pb()
        if return_to_overview:
            self._return_to_overview()
        return True

    def _go_to_pedalboard(self, bundle):
        """Load a specific pedalboard via the footswitch path (same remember /
        restore-snapshot / return-to-overview discipline as prev/next)."""
        self._switch_to_bundle(bundle, return_to_overview=True)

    def editor_switch_pedalboard(self, bundle):
        """Live board switch from the editor: same discipline but stay on the
        editor canvas (no return-to-overview). Returns the freshly-built
        Pedalboard for the editor to reseed, or None if the load failed — on
        None the caller MUST NOT reseed (the host graph is wiped)."""
        if not self._switch_to_bundle(bundle, return_to_overview=False):
            return None
        return self.pedalboard

    def overview_board_entries(self):
        """Board list for the overview board manager: ``[{bundle,title,current}]``,
        default.pedalboard excluded (modepctrl filters it). Current board flagged."""
        cur = ((self.pedalboard.current_pb_path if self.pedalboard else "") or "").rstrip("/")
        return [{"bundle": e["bundle"], "title": e.get("title", "") or e["bundle"],
                 "current": e["bundle"].rstrip("/") == cur}
                for e in (self.backend.get_all_pedalboard_entries() or [])]

    def overview_switch_board(self, bundle):
        """Switch to ``bundle`` from the overview board manager. No-op if it's
        already current (avoids a needless graph-wiping /reset). Same footswitch
        discipline as prev/next (remember/restore snapshot, return to overview);
        warns on unsaved editor edits since /reset discards them."""
        cur = ((self.pedalboard.current_pb_path if self.pedalboard else "") or "").rstrip("/")
        if bundle.rstrip("/") == cur:
            return
        self._warn_if_editor_dirty()
        self._go_to_pedalboard(bundle)

    def save_current_board(self):
        """Save the current pedalboard in place (asNew=0) for the live editor.
        ALWAYS refresh afterward and adopt the host's current path/title: a
        FACTORY board falls through to save-new on the host (mints a new user
        bundle and changes the current path), so the cached pedalboard would go
        stale otherwise. Returns the backend's success bool."""
        self._audit_desync("save_current_board")
        ok = self.backend.save_current_pedalboard()
        self.refresh_pedalboard()   # adopt any path/title change (factory -> save-new)
        return ok

    def save_board_as(self, title):
        """Save the current live graph as a NEW board named ``title`` (asNew=1).
        The host switches the current board to the new bundle, so refresh to adopt
        the new path/title and carry the remembered snapshot over to the new key.
        Returns the new ``{'bundlepath','title'}`` or None on failure."""
        prev = self.pedalboard.current_pb_path if self.pedalboard else None
        self._audit_desync("save_board_as")
        res = self.backend.save_pedalboard_as(title)
        self.refresh_pedalboard()   # host switched current -> adopt new path/title
        if res:
            # the new bundle starts at whatever snapshot the old board was on
            new_path = res.get('bundlepath')
            if prev in self.pb_snapshot_memory and new_path:
                self.pb_snapshot_memory[new_path] = self.pb_snapshot_memory[prev]
        return res

    def load_bank_pedalboard(self, slot):
        """Mode-2: load the bank board mapped to footswitch ``slot`` (0-3)."""
        if slot >= len(self.bank_boards):
            return
        bundle = self.bank_boards[slot]["bundle"]
        if bundle == self.pedalboard.current_pb_path:
            self._return_to_overview()      # already here -> just leave any FOCUS card
            return
        self._warn_if_editor_dirty()        # the switch /reset discards unsaved editor edits
        self._go_to_pedalboard(bundle)

    # ---- bank manager (touch UI) -------------------------------------------
    # The host owns banks.json; we never touch the file. The manager reads the
    # whole bank list into a draft, mutates it in place, and POSTs the complete
    # list back via save_banks after every edit (the host rewrites wholesale).
    # current_bank picks which bank mode-2 maps to FS0-3.
    def bank_manager_open(self):
        """Load the bank draft + board catalog for the manager. Returns the
        banks in display shape; also caches the draft we mutate."""
        self._bank_draft = self.backend.get_banks() or []
        self._bank_catalog = [
            {"bundle": e["bundle"],
             "title": e.get("title", "") or self._board_label(e["bundle"])}
            for e in (self.backend.get_all_pedalboard_entries() or [])
        ]
        return self.bank_manager_banks()

    @staticmethod
    def _board_label(bundle):
        return bundle.split("/")[-1].replace(".pedalboard", "")

    def bank_manager_banks(self):
        """Banks for the manager: ``[{title, pedalboards:[{bundle,title}], active}]``.
        ``active`` flags the bank mode-2 currently maps to (current_bank)."""
        draft = getattr(self, "_bank_draft", [])
        return [{"title": b.get("title", "") or "(이름 없음)",
                 "pedalboards": [{"bundle": p["bundle"],
                                  "title": p.get("title", "") or self._board_label(p["bundle"])}
                                 for p in b.get("pedalboards", [])],
                 "active": (i == self.current_bank)}
                for i, b in enumerate(draft)]

    def bank_manager_catalog(self):
        """Every available board to add: ``[{bundle,title}]`` (cached on open)."""
        return getattr(self, "_bank_catalog", [])

    def _title_for_bundle(self, bundle):
        for e in getattr(self, "_bank_catalog", []):
            if e["bundle"] == bundle:
                return e["title"]
        return self._board_label(bundle)

    def _commit_banks(self):
        """Persist the draft to the host and re-sync mode-2 if it is live so the
        footswitch strip reflects the edit immediately."""
        self.backend.save_banks(self._bank_draft)
        if self.footswitch_mode == 2:
            self.assign_footswitches()
            self.view.update_mode_display(self.footswitch_mode)

    def suggest_bank_name(self):
        """A unique default name ("뱅크 N") so a bank can be created without typing."""
        existing = {b.get("title", "") for b in getattr(self, "_bank_draft", [])}
        n = 1
        while ("뱅크 %d" % n) in existing:
            n += 1
        return "뱅크 %d" % n

    def create_bank(self, title):
        title = (title or "").strip() or self.suggest_bank_name()
        self._bank_draft.append({"title": title, "pedalboards": []})
        self._commit_banks()

    def rename_bank(self, idx, title):
        title = (title or "").strip()
        if title and 0 <= idx < len(self._bank_draft):
            self._bank_draft[idx]["title"] = title
            self._commit_banks()

    def delete_bank(self, idx):
        if len(self._bank_draft) <= 1:
            # Never strand the user with zero banks (mode-2 would have nothing to
            # map, and the host's banks.json would go empty). Keep the last one.
            self._notify("마지막 뱅크는 삭제할 수 없어요")
            return
        if 0 <= idx < len(self._bank_draft):
            del self._bank_draft[idx]
            # keep current_bank in range (mode-2 reads banks[current_bank])
            if self.current_bank >= len(self._bank_draft):
                self.current_bank = max(0, len(self._bank_draft) - 1)
                utils.save_last_bank(self.current_bank)
            self._commit_banks()

    def bank_add_board(self, idx, bundle):
        if 0 <= idx < len(self._bank_draft):
            self._bank_draft[idx].setdefault("pedalboards", []).append(
                {"bundle": bundle, "title": self._title_for_bundle(bundle)})
            self._commit_banks()

    def bank_remove_board(self, idx, board_idx):
        if 0 <= idx < len(self._bank_draft):
            pbs = self._bank_draft[idx].get("pedalboards", [])
            if 0 <= board_idx < len(pbs):
                del pbs[board_idx]
                self._commit_banks()

    def bank_move_board(self, idx, board_idx, delta):
        """Swap a board with its neighbour (delta -1 up / +1 down). Order matters:
        the first 4 boards map to FS0-3 in mode-2."""
        if 0 <= idx < len(self._bank_draft):
            pbs = self._bank_draft[idx].get("pedalboards", [])
            j = board_idx + delta
            if 0 <= board_idx < len(pbs) and 0 <= j < len(pbs):
                pbs[board_idx], pbs[j] = pbs[j], pbs[board_idx]
                self._commit_banks()

    def set_active_bank(self, idx):
        """Pick the bank mode-2 maps to FS0-3 (and re-sync the strip if live)."""
        if 0 <= idx < len(self._bank_draft):
            self.current_bank = idx
            utils.save_last_bank(idx)
            if self.footswitch_mode == 2:
                self.assign_footswitches()
                self.view.update_mode_display(self.footswitch_mode)

    def prev_pedalboard(self):
        self._warn_if_editor_dirty()         # /reset 이 미저장 에디터 편집을 폐기 (비차단 알림)
        self._remember_current_snapshot()   # /reset 으로 날아가기 전에 떠나는 보드 기록
        self.backend.set_prev_pedalboard()
        self.refresh_pedalboard()
        self._restore_snapshot_for_current_pb()
        self._return_to_overview()

    def next_pedalboard(self):
        self._warn_if_editor_dirty()
        self._remember_current_snapshot()
        self.backend.set_next_pedalboard()
        self.refresh_pedalboard()
        self._restore_snapshot_for_current_pb()
        self._return_to_overview()

    def prev_snapshot(self):
        if self.pedalboard.current_snapshot_idx > 0:
            self.pedalboard.current_snapshot_idx -= 1
            self.backend.load_snapshot(self.pedalboard.current_snapshot_idx)
            self.refresh_pedalboard()

    def next_snapshot(self):
        if self.pedalboard.current_snapshot_idx < len(self.pedalboard.list_of_snapshots) - 1:
            self.pedalboard.current_snapshot_idx += 1
            self.backend.load_snapshot(self.pedalboard.current_snapshot_idx)
            self.refresh_pedalboard()

    def go_to_snapshot(self, idx):
        """Load snapshot ``idx`` directly (the editor's snapshot picker, vs the
        footswitch's prev/next). Applies the snapshot's param/bypass values to the
        live graph, then refreshes. Returns the rebuilt Pedalboard for the editor
        to reseed (so node values update), or None for an out-of-range idx."""
        if str(idx) not in (self.pedalboard.list_of_snapshots or {}):
            return None
        self.pedalboard.current_snapshot_idx = idx
        self.backend.load_snapshot(idx)
        self.refresh_pedalboard()
        return self.pedalboard

    def assign_pb_ss_to_footswitch(self, fs_idx_to_assign):
        """
        FS indices are 0-3. Assigns the current pedalboard and snapshot to the given footswitch.
        """
        # Suppose self.pedalboard keeps track of pedalboard_name, current_snapshot_idx, etc.

        pedalboard = self.pedalboard.current_pb_path
        snapshot_idx = self.pedalboard.current_snapshot_idx

        self.fs_assignment_data[str(fs_idx_to_assign)] = {
            "pedalboard": pedalboard,
            "snapshot_idx": snapshot_idx
        }

        # Persist to JSON
        utils.save_footswitch_assignments(self.fs_assignment_data)

        print(f"Footswitch {fs_idx_to_assign} assigned to PB {pedalboard}, snapshot {snapshot_idx}")

    def recall_pb_ss(self, fs_idx):
        """Load pedalboard and snapshot as stored in footswitch_assignments.json"""
        assignment = self.fs_assignment_data.get(str(fs_idx))
        if not assignment or assignment["pedalboard"] is None:
            print(f"No assignment for footswitch {fs_idx}.")
            return

        # Actually load the pedalboard / snapshot
        pb_path = assignment["pedalboard"]
        ss_idx = assignment["snapshot_idx"]

        # set_pedalboard returns a success BOOL (True == loaded; M6a made the
        # partial-failure case detectable). It used to return None always, so the
        # old `error is None` check is now wrong — branch on the bool.
        self._warn_if_editor_dirty()         # the switch /reset discards unsaved editor edits
        if self.backend.set_pedalboard(pb_path):
            # Re-initialize your pedalboard object
            self.refresh_pedalboard()
            # Then set the snapshot
            self.pedalboard.current_snapshot_idx = ss_idx
            self.backend.load_snapshot(ss_idx)
            self.view_update_effect()
            print(f"Recalled PB {pb_path}, snapshot {ss_idx}.")
        else:
            print(f"Failed to load PB {pb_path}.")

    # Consecutive identical samples required before a switch state change is
    # accepted (software debounce). At 100 Hz, 3 samples == ~30 ms: longer than
    # mechanical bounce (<10 ms) yet imperceptible to the player.
    FOOTSWITCH_POLL_HZ = 100
    DEBOUNCE_SAMPLES = 3

    def start_footswitch_polling(self, rate_hz=None):
        """Run the footswitch poll loop on a dedicated daemon thread.

        Blocking I2C reads happen off the main thread so they never stall the
        UI; detected events are marshalled back to the main thread via
        self.scheduler.schedule_once, so LED blinks and ModepController calls
        still run on the main thread exactly as before.
        """
        if rate_hz:
            self.FOOTSWITCH_POLL_HZ = rate_hz
        if self._poll_thread and self._poll_thread.is_alive():
            return  # already running
        self._poll_stop = threading.Event()
        self._poll_thread = threading.Thread(
            target=self._footswitch_poll_loop, daemon=True, name='footswitch-poll')
        self._poll_thread.start()

    def stop_footswitch_polling(self):
        if self._poll_stop:
            self._poll_stop.set()

    def _footswitch_poll_loop(self):
        interval = 1.0 / self.FOOTSWITCH_POLL_HZ
        n = self.DEBOUNCE_SAMPLES
        stable = [0, 0, 0, 0]   # debounced switch states
        counts = [0, 0, 0, 0]   # consecutive samples disagreeing with `stable`
        while not self._poll_stop.is_set():
            raw = self.hwi.read_footswitches()  # one I2C transaction -> [0/1]*4
            for i in range(4):
                if raw[i] == stable[i]:
                    counts[i] = 0
                else:
                    counts[i] += 1
                    if counts[i] >= n:
                        stable[i] = raw[i]
                        counts[i] = 0
                # Latch any switch that is (debounced) pressed during this cycle,
                # so combos are captured even if released slightly out of sync.
                if stable[i] == 1:
                    self.footswitch_input_que[i] = 1

            # Fire only once every switch is released again — release-edge firing
            # is required to disambiguate single presses from combos (chords).
            if stable == [0, 0, 0, 0] and self.footswitch_input_que != [0, 0, 0, 0]:
                status = list(self.footswitch_input_que)
                self.footswitch_input_que = [0, 0, 0, 0]
                self.scheduler.schedule_once(lambda dt, s=status: self.handle_footswitch_event(s))

            time.sleep(interval)

    def handle_footswitch_event(self, status):
        print(f'Footswitch event: {status}')
        # In the tuner, any footswitch activity exits back to overview
        # (stomp-to-exit, like a hardware tuner pedal).
        if self._in_tuner:
            self.exit_tuner()
            return
        # For each pressed (or released) footswitch, trigger a blink on its corresponding LED.
        for i, s in enumerate(status):
            # In tap-tempo mode the metronome owns the LEDs; skip the per-press
            # blink so it doesn't fight the beat flashes.
            if s == 1 and self.footswitch_mode != TAP_TEMPO_MODE:
                # Blink the red LED on the corresponding LED object. Here, one blink cycle.
                self.hwi.LED.get_led(i).blink(color='red', times=1, interval=0.1)
        if sum(status) == 1:
            idx = status.index(1)
            callback = self.footswitch_assigns[idx]
            if callback:
                return callback()

            else:
                return
        else:
            self.handle_multiple_footswitches(status)

    def handle_multiple_footswitches(self, status):
        # While in tap-tempo mode, ANY chord exits back to the previous mode.
        if self.footswitch_mode == TAP_TEMPO_MODE:
            self.exit_tap_tempo()
            return
        # Adjacent-pair chords select a mode (footswitch-combo convention):
        if status == [1, 1, 0, 0]:        # A+B -> cycle footswitch mode
            self.modechange()
        elif status == [0, 1, 1, 0]:      # B+C -> guitar tuner
            self.enter_tuner()
        elif status == [0, 0, 1, 1]:      # C+D -> tap tempo
            self.enter_tap_tempo()
        elif status == [0, 0, 0, 0]:
            print("How is this possible?")
        else:
            print("Invalid footswitch combination")


    def assign_footswitches(self):
        if self.footswitch_mode == 0:
            # Mode 0: pedalboard navigation
            self.footswitch_assigns = [
                self.prev_pedalboard,
                self.next_pedalboard,
                self.prev_snapshot,
                self.next_snapshot
            ]

        elif self.footswitch_mode == 1:
            # Mode 1: parameter assign mode (bypass toggles)
            # 1) Filter out any effects that are in “simulator” categories
            #    (or keep them, depending on your actual “excluded” vs. “included” logic).
            valid_effects = []
            for effect in self.pedalboard.effects:
                # Example: exclude categories like "Simulator", "Amp", or "Cab"
                # Adjust to match your actual category naming
                if not any(cat.lower() in ["simulator", "amp", "cab", "utility"] for cat in effect.category):
                    valid_effects.append(effect)

            # 2) Grab the first two and last two from this filtered list
            #    If fewer than 4 are available, handle that gracefully
            if len(valid_effects) < 4:
                # If you expect always to have enough “toggle-able” effects,
                # you can just skip or implement partial assignment here.
                print("Warning: Not enough non-simulator effects to assign all four footswitches.")
                self.footswitch_assigns = [None, None, None, None]
                self.stomp_effects = []
                return

            e0 = valid_effects[0]  # first effect
            e1 = valid_effects[1]  # second effect
            e2 = valid_effects[-2]  # second-last effect
            e3 = valid_effects[-1]  # last effect

            # Expose the chosen 4 so the QtView strip captions match the toggles.
            self.stomp_effects = [e0, e1, e2, e3]

            # 3) Define a small helper to toggle bypass:
            def toggle_bypass(effect):
                current_val = effect.bypassed
                self.parameter_changed(effect.instance, ':bypass', not current_val)

            # 4) Assign footswitch 0–3 to lambda toggles of the chosen effects
            self.footswitch_assigns = [
                lambda: toggle_bypass(e0),
                lambda: toggle_bypass(e1),
                lambda: toggle_bypass(e2),
                lambda: toggle_bypass(e3),
            ]

        elif self.footswitch_mode == 2:
            # Mode 2: BANK board selector. The active bank's first 4 boards map to
            # FS0-3 (extra boards ignored); a press loads that board. Future: a
            # touch UI switches self.current_bank / edits banks. No bank -> message
            # + fall back to STOMP (mode 1).
            entries = self.backend.get_bank_pedalboard_entries(self.current_bank)
            if not entries and self.current_bank != 0:
                # held bank index is stale (deleted while app was off) -> clamp to 0
                self.current_bank = 0
                utils.save_last_bank(0)
                entries = self.backend.get_bank_pedalboard_entries(0)
            if not entries:
                self._notify("뱅크 없음 — STOMP 모드로")
                self.bank_boards = []
                self.footswitch_mode = 1
                self.assign_footswitches()
                self.view.update_mode_display(self.footswitch_mode)
                return
            self.bank_boards = entries[:4]
            self.footswitch_assigns = [
                (lambda s=i: self.load_bank_pedalboard(s)) if i < len(self.bank_boards) else None
                for i in range(4)
            ]

        elif self.footswitch_mode == 3: # WebUI mode
            self.footswitch_assigns = [None, None, None, self.close_webui]

        elif self.footswitch_mode == TAP_TEMPO_MODE:
            # Any single press is a beat tap; chords exit (handle_multiple_footswitches).
            self.footswitch_assigns = [self.tap_input] * 4

    def toggle_keyboard(self, *args):
        utils.toggle_wvkbd()


    def open_webui(self, *args):
        self.hwi.LED[3] = 1  # turn 4th red LED on

        # Check if Chromium is already running
        result = subprocess.run(['pgrep', 'chromium'], stdout=subprocess.PIPE)
        if result.stdout:
            print("Chromium is already running.")
        else:
            # Start Chromium in full-screen mode
            self.chromium_process = subprocess.Popen(['chromium-browser', '--start-fullscreen', 'http://localhost/'])
            # Minimize the app window (view owns window control)
            self.view.minimize()
            # Set footswitch mode to 3 and reassign footswitches
            self.footswitch_mode = 3
            self.assign_footswitches()

    def close_webui(self, *args):
        print("close_webui called")
        if hasattr(self, 'chromium_process'):
            print("Terminating Chromium process")
            self.chromium_process.terminate()
            try:
                self.chromium_process.wait(timeout=5)
                print("Chromium process terminated")
            except subprocess.TimeoutExpired:
                print("Chromium did not terminate in time; killing it")
                self.chromium_process.kill()
                print("Chromium process killed")
        else:
            print("Chromium process handle not found; attempting to kill by name")
            subprocess.run(['pkill', '-f', 'chromium-browser'])
        # Rest of the method
        self.footswitch_mode = 0
        self.hwi.LED[3] = 0  # turn 4th red LED off

        self.assign_footswitches()

        self.view.restore()
        os.system("xdotool search --name 'GCaMP6s' windowactivate")

        self.refresh_pedalboard()

        # Re-enable the webui button
        self.view.enable_webui_button()

    def abcd_availability(self, availabilities):
        self.view.set_abcd_availability(availabilities)

    def abcd_button_state_change(self, prev_state, new_state):
        ##do something
        ...
        #relase ABCDbutton
        ...
    def view_update_bpm(self):
        self.view.update_bpm_display(self.pedalboard.bpm)

    # ── Tap tempo (entered via the C+D footswitch chord) ─────────────────
    def enter_tap_tempo(self):
        """Switch into tap-tempo: every footswitch press becomes a beat tap and
        the physical LEDs run a metronome at the current tempo."""
        if self.footswitch_mode == TAP_TEMPO_MODE:
            return
        self._mode_before_tap = self.footswitch_mode
        self.footswitch_mode = TAP_TEMPO_MODE
        self.assign_footswitches()
        self.hwi.LED.stop_all_blinking()   # clear before the metronome owns the LEDs
        self.view.update_mode_display(TAP_TEMPO_MODE)
        self.view.show_tap_tempo(self.pedalboard.bpm, self.pedalboard.bpb)
        self.tap_tempo.start(self.pedalboard.bpm, self.pedalboard.bpb)

    def exit_tap_tempo(self):
        """Leave tap-tempo (any chord) -> stop the metronome, restore the prior mode."""
        self.tap_tempo.stop()
        self.hwi.LED.stop_all_blinking()
        self.footswitch_mode = self._mode_before_tap
        self.assign_footswitches()
        self.view.hide_tap_tempo()
        self.view.update_mode_display(self.footswitch_mode)

    def tap_input(self, *args):
        """A single footswitch press while in tap-tempo mode = one beat tap."""
        self.tap_tempo.tap()

    def enter_tuner(self):
        """B+C chord -> guitar tuner screen. Spins up an on-demand cochlea engine
        (its own JACK client on capture_1) that runs only while tuning; any
        footswitch press then exits (see handle_footswitch_event guard)."""
        if self._in_tuner:
            return
        try:
            from cochlea import TunerEngine, JackSource
            make_source = self._tuner_source_factory or JackSource
            engine = TunerEngine(make_source(), string_set="guitar")
            engine.start()
        except Exception as e:
            logging.error("tuner start failed: %s", e)
            self._notify("튜너: 오디오 입력 없음")
            return
        self._tuner_engine = engine
        self._in_tuner = True
        self.hwi.LED.stop_all_blinking()
        self.view.show_tuner(engine)
        # Drive the footswitch LED strobe from the reading (GUI-thread ticker).
        self._tuner_led_state = None
        self._tuner_led_phase = 0.0
        self._tuner_was_in_tune = False
        self._tuner_led_handle = self.scheduler.schedule_interval(
            self._tuner_led_tick, 1.0 / TUNER_LED_TICK_HZ)

    def exit_tuner(self):
        """Leave the tuner -> stop the audio engine + LED strobe, back to overview."""
        if not self._in_tuner:
            return
        self._in_tuner = False
        if self._tuner_led_handle is not None:
            self.scheduler.unschedule(self._tuner_led_handle)
            self._tuner_led_handle = None
        for i in range(4):
            self.hwi.LED[i] = 0
        self._tuner_led_state = 0
        engine, self._tuner_engine = self._tuner_engine, None
        if engine is not None:
            try:
                engine.stop()
            except Exception as e:
                logging.error("tuner stop failed: %s", e)
        self.view.hide_tuner()

    def _tuner_led_tick(self, dt):
        """~30 Hz while tuning: drive the 4 footswitch LEDs from the latest reading.
        Off-pitch = red strobe that speeds up as the note nears pitch; the moment
        it lands = a short blue flourish, then steady blue; silence = LEDs off."""
        engine = self._tuner_engine
        if engine is None:
            return
        r = engine.get_reading()
        if r is None:                              # engine already gates on volume/confidence
            self._tuner_was_in_tune = False
            self._tuner_led_phase = 0.0
            self._set_all_leds(0)
            return
        if abs(r.cents) < TUNER_IN_TUNE_CENTS:
            now = time.monotonic()
            if not self._tuner_was_in_tune:        # just landed on pitch
                self._tuner_was_in_tune = True
                self._tuner_tune_since = now
                self._tuner_led_phase = 0.0
            if now - self._tuner_tune_since < TUNER_CEREMONY_SEC:
                self._tuner_led_phase = (self._tuner_led_phase + 12.0 / TUNER_LED_TICK_HZ) % 1.0
                self._set_all_leds(0b01 if self._tuner_led_phase < 0.5 else 0)   # quick blue flourish
            else:
                self._set_all_leds(0b01)           # steady blue = in tune
            return
        # off pitch: red strobe, faster the closer to pitch
        self._tuner_was_in_tune = False
        span = TUNER_FAR_CENTS - TUNER_IN_TUNE_CENTS
        closeness = 1.0 - min(1.0, max(0.0, (abs(r.cents) - TUNER_IN_TUNE_CENTS) / span))
        blink_hz = TUNER_BLINK_SLOW_HZ + closeness * (TUNER_BLINK_FAST_HZ - TUNER_BLINK_SLOW_HZ)
        self._tuner_led_phase = (self._tuner_led_phase + blink_hz / TUNER_LED_TICK_HZ) % 1.0
        self._set_all_leds(0b10 if self._tuner_led_phase < 0.5 else 0)

    def _set_all_leds(self, state):
        """Set all 4 footswitch LEDs to `state`, skipping redundant I2C writes."""
        if state == self._tuner_led_state:
            return
        for i in range(4):
            self.hwi.LED[i] = state
        self._tuner_led_state = state

    def _tap_on_bpm(self, bpm):
        """Engine produced a refined BPM -> tell MODEP + update the on-screen widget."""
        error_msg = self.backend.set_bpm(bpm)
        if error_msg is None:
            self.pedalboard.bpm = bpm
        else:
            print(error_msg)
        self.view.update_bpm_display(bpm)

    def _tap_on_beat(self, led_index, is_downbeat, duration):
        """Metronome beat -> flash one LED (red downbeat / blue off-beat)."""
        self.hwi.LED[led_index] = 0b10 if is_downbeat else 0b01
        self.scheduler.schedule_once(
            lambda dt, i=led_index: self._tap_beat_off(i), duration)

    def _tap_beat_off(self, led_index):
        self.hwi.LED[led_index] = 0

    # Boot LED ceremony: a scripted ~3s light show over the 4 footswitch LEDs.
    # Each frame is (delay_seconds, [s0, s1, s2, s3]) where a per-LED state is
    # 0=off 1=blue 2=red 3=purple (see fsledctrl.LED.set_state). Runs on the
    # event loop (non-blocking) so the splash->overview handoff isn't frozen.
    _BOOT_FRAMES = [
        # blue Knight-Rider sweep out and back
        (0.00, [1, 0, 0, 0]), (0.10, [0, 1, 0, 0]), (0.20, [0, 0, 1, 0]),
        (0.30, [0, 0, 0, 1]), (0.40, [0, 0, 1, 0]), (0.50, [0, 1, 0, 0]),
        (0.60, [1, 0, 0, 0]),
        # red sweep back the other way
        (0.70, [0, 0, 0, 2]), (0.80, [0, 0, 2, 0]), (0.90, [0, 2, 0, 0]),
        (1.00, [2, 0, 0, 0]),
        # purple wipe filling left->right
        (1.15, [3, 0, 0, 0]), (1.25, [3, 3, 0, 0]), (1.35, [3, 3, 3, 0]),
        (1.45, [3, 3, 3, 3]),
        # red/blue sparkle alternation
        (1.60, [1, 2, 1, 2]), (1.72, [2, 1, 2, 1]), (1.84, [1, 2, 1, 2]),
        (1.96, [2, 1, 2, 1]),
        # triple purple finale, then dark
        (2.10, [3, 3, 3, 3]), (2.25, [0, 0, 0, 0]), (2.40, [3, 3, 3, 3]),
        (2.55, [0, 0, 0, 0]), (2.70, [3, 3, 3, 3]), (2.85, [0, 0, 0, 0]),
    ]

    def boot_lightshow(self, i=None):
        """Play the boot LED ceremony (see _BOOT_FRAMES). No-op if the hardware
        can't drive LEDs (e.g. a fake injected in tests)."""
        def paint(states):
            try:
                for idx, state in enumerate(states):
                    self.hwi.LED[idx] = state
            except Exception:
                pass  # fake/absent LED backend -> silently skip the show
        for delay, states in self._BOOT_FRAMES:
            self.scheduler.schedule_once(lambda dt, s=states: paint(s), delay)

    def save_snapshot(self):
        self._audit_desync("save_snapshot")
        ok = self.backend.snapshot_save()   # overwrites current snapshot + persists the pedalboard
        self.refresh_pedalboard()
        return bool(ok)
    def  save_snapshot_as(self, name):
        self._audit_desync("save_snapshot_as")
        res = self.backend.snapshot_save_as(new_name=name)
        self.refresh_pedalboard()
        return res

    def modechange(self, mode=None):
        if mode is None:
            mode = (self.footswitch_mode + 1) % 3
        self.footswitch_mode = mode
        if self.footswitch_mode == 0:
            self.abcd_availability(False)
        else:
            self.abcd_availability(True)
        # Assign FIRST (mode 2 fills self.bank_boards and may fall back to mode 1),
        # THEN refresh the mode label + strip so it reflects the final state.
        self.assign_footswitches()
        self.view.update_mode_display(self.footswitch_mode)

    def abcd_button_state(self,prev,current):
        print(f"prev:{prev},current:{current}") #-1 is released. 0,1,2,3 is pressed for each button

    def _build_view_effect(self, effect):
        bypassed = self.backend.parameter_get(effect.instance, ":bypass")  # Fetch bypass state correctly
        return {
            "effect_instance": effect.instance,
            "effect_name": effect.name,
            "effect_bypassed": bypassed,
            "effect_category": effect.category,
            "effect_ports": [
                {
                    "port_name": port.name,
                    "effect_instance": effect.instance,
                    "port_symbol": port.symbol,
                    "port_value": port_value,
                    "port_unit": port.units,
                    "port_range": {
                        "min": port.min_value,
                        "max": port.max_value,
                        "default": port.default_value,
                    },
                    "port_properties": port.port_properties,
                    "port_rangesteps": port.range_steps,
                    "port_scalepoints": port.scale_points,
                    "port_kind": port.widget_kind
                }
                for port in effect.ports.values()
                if (port_value := port.value) is not None  # cached at load; host pushes changes via synapsin reverse channel
            ],
            # Monitor (output) ports: cached/seeded value -- NOT get_value() (output
            # ports aren't readable via parameter_get), and never None-excluded.
            "effect_monitors": [
                {
                    "port_name": mon.name,
                    "effect_instance": effect.instance,
                    "port_symbol": mon.symbol,
                    "port_value": mon.value,
                    "port_unit": mon.units,
                    "port_range": {
                        "min": mon.min_value,
                        "max": mon.max_value,
                        "default": mon.default_value,
                    },
                    "port_kind": mon.widget_kind
                }
                for mon in effect.monitors.values()
            ],
            "patches": [
                {
                    "patch_label": patch.label,
                    "effect_instance": effect.instance,
                    "patch_uri": patch.uri,
                    "patch_file_types": patch.file_types,
                    "patch_file_path": patch.file_path,
                    "patch_value": patch.value,
                } for patch in effect.patches.values()
            ]
        }





