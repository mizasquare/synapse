import utils
from modepctrl import get_backend
from model import initialize_modep_pedalboard, Connection, diff_live_graph, Pedalboard
from taptempo import TapTempoEngine
from ledview import LedView
from hardwares.footswitches import FootswitchReader, FS_COMMIT
import threading
import time

import logging
import os
import configs
import strings

# Footswitch mode ids. 0-2 are the press-driven modes cycled by modechange();
# 4 (tap tempo) is a transient mode entered out-of-band (chord) and kept out of
# that cycle.
TAP_TEMPO_MODE = 4

# STOMP auto-pick excludes these categories (amp/cab/sim/utility are set-and-forget
# tone blocks, not per-song stomps). Manual FOCUS-card assignment can still pin any
# effect regardless of category -- this only bounds the AUTO fill.
_STOMP_EXCLUDED = ("simulator", "amp", "cab", "utility")

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
        # LED rendering surface (the LED-side of `view`; see ledview.LedView).
        # Fed semantic facts, it owns all colour/animation. None container ->
        # no-op (a hardware backend without LEDs).
        self.led = LedView(getattr(self.hwi, "LED", None), scheduler)

        # 0: pedalboard nav, 1: parameter assign, 2: pb snapshot assign
        self.footswitch_mode = 0
        self.footswitch_assigns = [None, None, None, None]
        # Footswitch input state machine (debounce + release-edge combo latch).
        # The poll loop just reads raw samples and feeds this; all the bookkeeping
        # that used to live inline in _footswitch_poll_loop now lives here, and
        # it's the seam that surfaces press/release edges for a future momentary
        # (hold) mode. See hardwares/footswitches.FootswitchReader.
        self._fsreader = FootswitchReader(count=4, debounce_samples=self.DEBOUNCE_SAMPLES)
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
        # (the tuner LED strobe now lives entirely in LedView; the presenter only
        #  owns the engine lifecycle + exit-on-press.)
        self._poll_thread = None
        self._poll_stop = None
        self.start_footswitch_polling(100)  # background thread @100Hz

        # Load pedalboard model. Fallback-guarded: if the host's current board was
        # deleted while the app was off, its info 500s and the plain build returns
        # None -> the UI would crash into a systemd restart loop. Never None now.
        self.pedalboard = self._load_pedalboard_with_fallback()
        # EditorBridge ref (wired by the entry point) so footswitch board nav can
        # surface a non-blocking notice when it discards unsaved live editor edits.
        self.editor = None
        # pb별 마지막 활성 스냅샷 기억 (세션 한정 인메모리). key=current_pb_path, value=snapshot idx
        self.pb_snapshot_memory = {}

        # Mode-2 BANK selector: the active bank's first 4 boards map to FS0-3.
        # current_bank is driven by the bank manager (set_active_bank); it picks
        # which bank mode-2 uses. bank_boards is the live [{bundle,title}] strip.
        # Held across restarts (utils.app_state) to mirror MOD's HMI bank hold.
        self.current_bank = utils.load_last_bank()
        self.bank_boards = []

        # Mode-1 STOMP: the 4 effects bound to FS0-3 (length-4, None where a slot
        # is empty). Exposed so the QtView strip captions mirror exactly what a
        # press toggles (kept in sync by assign_footswitches, same lifecycle as
        # bank_boards). Resolved from manual per-board overrides + the auto pick.
        self.stomp_effects = []
        # Manual STOMP assignments {pb_path: {slot_str: instance}} (utils/app_state).
        # Per-slot overrides on top of the auto front-2/back-2 pick; see
        # _resolve_stomp_slots / assign_focus_to_fs. Held across restarts.
        self._fs_assigns = utils.load_fs_assigns()

        # Global bypass ("panic button", the A+D chord -> bypass_all): toggle
        # state + per-effect restore map ({instance: pre-engage bypassed}).
        # Both reset on refresh_pedalboard so a board/snapshot switch can never
        # resurrect stale states from a previous board.
        self._global_bypass = False
        self._bypass_restore = {}

        # Drop persisted per-board local settings whose pedalboard was deleted
        # while the app was off (or via the web UI), so orphans don't accumulate.
        self._prune_stale_local_state()

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

    def _prune_stale_local_state(self):
        """Drop persisted per-board local settings whose pedalboard no longer
        exists (deleted while the app was off, or from the web UI), so app_state
        doesn't accumulate orphan fs_assigns / board_order entries keyed by a
        dead bundle path.

        Best-effort and conservative: if the host can't be listed (down at boot)
        it returns an empty set, and we skip pruning rather than wipe everything
        on a transient failure. Runs once at startup. (Per-instance staleness --
        an effect removed from a still-existing board -- needs no cleanup here:
        _resolve_stomp_slots already falls back to auto for a missing instance.)"""
        try:
            entries = self.backend.get_all_pedalboard_entries() or []
        except Exception as e:
            logging.debug("prune: could not list pedalboards: %s", e)
            return
        live = {e["bundle"].rstrip("/") for e in entries if e.get("bundle")}
        if not live:
            return  # host returned nothing -> don't nuke on uncertainty

        pruned = {pb: m for pb, m in self._fs_assigns.items()
                  if pb.rstrip("/") in live}
        if pruned != self._fs_assigns:
            self._fs_assigns = pruned
            utils.save_fs_assigns(self._fs_assigns)

        order = utils.load_board_order()
        kept = [b for b in order if b.rstrip("/") in live]
        if kept != order:
            utils.save_board_order(kept)

    def initiate_view(self):
        self.view_update_effect()
        self.view_update_bpm()

    def _try_build_pedalboard(self):
        """Build the live Pedalboard, swallowing any host/parse failure to None
        (initialize_modep_pedalboard returns None when the current board's info
        500s -- e.g. it was deleted -- but can also raise on a wedged host)."""
        try:
            return initialize_modep_pedalboard(self.backend)
        except Exception as e:
            logging.error("pedalboard build failed: %s", e)
            return None

    def _recover_onto(self, bundle):
        """Load ``bundle`` on the host and rebuild the model; None if either step
        fails. Loading also repoints the host's dangling 'current' at a real board."""
        try:
            if self.backend.set_pedalboard(bundle):
                return self._try_build_pedalboard()
        except Exception as e:
            logging.error("recovery load %s failed: %s", bundle, e)
        return None

    def _load_pedalboard_with_fallback(self):
        """Build the live Pedalboard at startup, recovering if the host's current
        board is gone (deleted while the app was off -> pedalboard/info 500 -> None,
        which used to crash the UI into a systemd restart loop). Every step is
        defensive -- a crisis-time recovery must never itself raise. Chain:
          1) host's current board (the normal path; no side effects)
          2) the first existing user board (host list, default.pedalboard excluded)
          3) load default.pedalboard, save-as a fresh board, open that
          4) an empty in-memory board so the UI still boots (never expected)."""
        pb = self._try_build_pedalboard()
        if pb is not None:
            return pb
        logging.error("current pedalboard failed to load (deleted?) -- recovering")

        try:
            entries = self.backend.get_all_pedalboard_entries() or []
        except Exception as e:
            logging.error("recovery: listing boards failed: %s", e)
            entries = []

        def _is_default(b):
            return (b or "").rstrip("/").endswith("default.pedalboard")

        # 2) first existing non-default board
        for e in entries:
            bundle = (e.get("bundle") or "").strip()
            if bundle and not _is_default(bundle):
                pb = self._recover_onto(bundle)
                if pb is not None:
                    logging.warning("recovered onto first board: %s", bundle)
                    return pb

        # 3) default -> save-as a fresh board -> open it
        default_bundle = next((e.get("bundle") for e in entries if _is_default(e.get("bundle"))),
                              "/var/modep/pedalboards/default.pedalboard")
        if self._recover_onto(default_bundle) is not None:
            try:
                self.backend.save_pedalboard_as("Recovered")  # host switches current to the new bundle
                pb = self._try_build_pedalboard()
                if pb is not None:
                    logging.warning("recovered via default -> save-as")
                    return pb
            except Exception as e:
                logging.error("recovery save-as failed: %s", e)

        # 4) last resort: an empty in-memory board so the UI boots and the user can
        #    pick one (practically unreachable -- default.pedalboard always exists).
        logging.error("all pedalboard recovery failed -- booting an empty board")
        return Pedalboard(title=strings.tr('board.empty'), current_pb_path="", width=0, height=0)

    def refresh_pedalboard(self):
        # Never null the model out: a transient host failure (or a board deleted
        # elsewhere mid-session) makes the build return None, which would crash the
        # next view_update_effect. Keep the last-known board on failure instead.
        rebuilt = self._try_build_pedalboard()
        if rebuilt is not None:
            self.pedalboard = rebuilt
        # The rebuilt model may be a different board/snapshot; a stale global-
        # bypass restore map would then restore wrong states, so drop it here.
        # (bypass_all itself never calls refresh, so this can't self-trigger.)
        self._global_bypass = False
        self._bypass_restore = {}
        # STOMP binds effect OBJECTS (self.stomp_effects), which the rebuild above
        # just orphaned -> the strip (reads those objects) would show stale bypass
        # while the LEDs (live-lookup) show fresh, and the two diverge. Re-resolve
        # so stomp_effects holds the live objects again. Only mode 1 binds objects
        # (mode 2 holds bundle dicts, mode 0 holds none), so guard on it.
        if self.footswitch_mode == 1:
            self.assign_footswitches()
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

        # Insurance: the model should never be None (startup fallback + refresh
        # guard keep it set), but a None here once boot-looped the whole app, so
        # never let it become fatal again -- skip the refresh rather than crash.
        if self.pedalboard is None:
            return

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
        # Effect active/bypass (or board/snapshot) state may have changed -> keep
        # the footswitch LEDs' resting colours in step. This is THE hub for such
        # changes (local toggle, external echo, bypass_all, board/snapshot switch).
        self._push_led_bindings()

    def _push_led_bindings(self):
        """Translate the current footswitch binding into per-slot semantic tokens
        and hand them to LedView (which owns the colour mapping). STOMP reflects
        each bound effect's live active/bypass; BANK flags the loaded board;
        NAVIGATE (and any other mode) has no resting state. Effects are re-looked
        up by instance so a refresh_pedalboard rebuild can't leave stale flags."""
        mode = self.footswitch_mode
        if mode == 1:            # STOMP: active(blue) / bypassed(off)
            tokens = []
            for i in range(4):
                bound = self.stomp_effects[i] if i < len(self.stomp_effects) else None
                live = self.pedalboard.get_effect_by_instance(bound.instance) if bound else None
                tokens.append('empty' if live is None else
                              ('bypassed' if live.bypassed else 'active'))
        elif mode == 2:          # BANK: current board(blue) / other(off)
            cur = ((self.pedalboard.current_pb_path if self.pedalboard else "") or "").rstrip("/")
            tokens = []
            for i in range(4):
                bundle = self.bank_boards[i]["bundle"] if i < len(self.bank_boards) else None
                if not bundle:
                    tokens.append('empty')
                else:
                    tokens.append('current' if bundle.rstrip("/") == cur else 'other')
        else:                    # NAVIGATE (0), tap tempo (4), etc. -> no resting state
            tokens = ['nav', 'nav', 'nav', 'nav']
        self.led.set_bindings(tokens)

    def view_render_parameters(self, effect_instance):
        effect = self.pedalboard.get_effect_by_instance(effect_instance)
        if not effect:
            return

        effectData = self._build_view_effect(effect)
        self.view.populate_port_area(effectData=effectData)

    def parameter_changed(self, effect_instance, port_symbol, port_value):
        if port_symbol == ":bypass":
            error_msg = self.backend.bypass_effect(effect_instance, port_value)
            if error_msg is None:
                self.pedalboard.get_effect_by_instance(effect_instance).bypassed = port_value
                self.view_update_effect()
            else:
                # The host didn't answer (e.g. a slow-loading board stalling mod-host):
                # the toggle silently no-op'd and model/host may now disagree. Surface
                # it so a dead-looking footswitch reads as "host busy", not "broken".
                print(error_msg)
                self._notify(strings.tr('toast.hostNoResponse'))

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
            elif cmd in ("EffectAdd", "EffectRemove", "EffectPresetLoad",
                         "PedalboardLoadBundle",
                         "SnapshotName", "SnapshotRename", "SnapshotRemove",
                         "PedalboardRemove", "BankLoad"):
                # (EffectPresetLoad: 프리셋은 여러 포트를 한꺼번에 바꾸고 그 에코는
                #  websocket으로만 나감 → 개별 델타 불가, 전체 재동기화로 수렴.
                #  파라미터 현재값은 syn_dump_graph(라이브)에서 오므로 저장 전에도 정확.)
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
            self._notify(strings.tr('toast.switchDiscard'))

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

    def _ordered_board_entries(self):
        """Board catalog in the user's saved display order (the app_state
        board_order overlay — utils.apply_board_order). Single order authority
        for BOTH the overview board manager and footswitch NAVIGATE, so the
        list on screen is exactly the sequence the footswitch steps through."""
        return utils.apply_board_order(self.backend.get_all_pedalboard_entries() or [])

    def overview_board_entries(self):
        """Board list for the overview board manager: ``[{bundle,title,current}]``,
        default.pedalboard excluded (modepctrl filters it). Current board flagged.
        Rows follow the user's saved order, not the host's ASCII sort."""
        cur = ((self.pedalboard.current_pb_path if self.pedalboard else "") or "").rstrip("/")
        return [{"bundle": e["bundle"], "title": e.get("title", "") or e["bundle"],
                 "current": e["bundle"].rstrip("/") == cur}
                for e in self._ordered_board_entries()]

    def move_board_order(self, bundle, delta):
        """Swap ``bundle`` with its display-order neighbour (delta -1 up / +1
        down) and persist the COMPLETE current display list as the new overlay
        — boards that never had a saved position get one, and NAVIGATE follows
        immediately. Mirrors bank_move_board's neighbour-swap. Returns True if
        the order changed (caller re-renders the list on True)."""
        bundles = [e["bundle"] for e in self._ordered_board_entries()]
        try:
            i = bundles.index(bundle)
        except ValueError:
            return False
        j = i + delta
        if not (0 <= i < len(bundles) and 0 <= j < len(bundles)):
            return False
        bundles[i], bundles[j] = bundles[j], bundles[i]
        utils.save_board_order(bundles)
        return True

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
        return [{"title": b.get("title", "") or strings.tr('bank.untitled'),
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
        while strings.trf('bank.defaultName', n) in existing:
            n += 1
        return strings.trf('bank.defaultName', n)

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
            self._notify(strings.tr('toast.lastBank'))
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

    # NAVIGATE order lives HERE, not in backend.set_next/prev_pedalboard: those
    # walk the host's ASCII-sorted pedalboard/list and can't see the user's
    # board_order overlay. Resolving the target bundle presenter-side keeps the
    # real and fake backends on the identical (user-controlled) sequence while
    # still reaching every board.
    def _nav_neighbor_bundle(self, delta):
        """Resolve the NAVIGATE target ``delta`` (+1 next / -1 prev) steps away
        in the user-ordered board list. Keeps the legacy modepctrl edge cases:
        current board unknown -> first board, prev at the top stays at the top
        (next wraps around). None when there are no boards at all."""
        bundles = [e["bundle"] for e in self._ordered_board_entries()]
        if not bundles:
            print("No banks or pedalboards!")
            return None
        cur = (self.backend.get_current_pedalboard() or "").rstrip("/")
        idx = next((i for i, b in enumerate(bundles) if b.rstrip("/") == cur), None)
        if idx is None:
            logging.error("Current pedalboard not in board list, falling back to 0th pedalboard.")
            return bundles[0]
        if delta < 0 and idx == 0:
            return bundles[0]
        return bundles[(idx + delta) % len(bundles)]

    def prev_pedalboard(self):
        self._warn_if_editor_dirty()         # /reset 이 미저장 에디터 편집을 폐기 (비차단 알림)
        bundle = self._nav_neighbor_bundle(-1)
        if bundle is not None:
            self._go_to_pedalboard(bundle)   # remember/restore-snapshot 규율 포함

    def next_pedalboard(self):
        self._warn_if_editor_dirty()
        bundle = self._nav_neighbor_bundle(+1)
        if bundle is not None:
            self._go_to_pedalboard(bundle)

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

    def load_effect_preset(self, instance, preset_uri):
        """Apply LV2 preset ``preset_uri`` to ``instance`` (the editor's preset
        chips). Blocking host call — preset state restore can take seconds for
        file-property plugins (NAM/IR), so the backend allows a long timeout
        and the editor runs this off the GUI thread (_run_bg), calling
        refresh_pedalboard itself on completion back on the GUI thread. A
        preset rewrites several control ports host-side at once, so skipping
        that refresh desyncs the knobs (same discipline as go_to_snapshot).
        Returns None on success or an error string; user-facing toasts are the
        editor's alone (like go_to_snapshot/save_snapshot — no _notify here)."""
        return self.backend.preset_load(instance, preset_uri)

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
        """Read raw switch samples off-thread and feed the FootswitchReader; any
        events it emits are marshalled to the main thread as a batch so LED
        blinks and ModepController calls still run there. All debounce/combo
        bookkeeping lives in the reader now (hardwares/footswitches)."""
        interval = 1.0 / self.FOOTSWITCH_POLL_HZ
        while not self._poll_stop.is_set():
            raw = self.hwi.read_footswitches()      # one I2C transaction -> [0/1]*4
            events = self._fsreader.poll(raw)
            if events:
                self.scheduler.schedule_once(lambda dt, e=events: self._dispatch_fs_events(e))
            time.sleep(interval)

    def _dispatch_fs_events(self, events):
        """Main-thread fan-out of FootswitchReader events. A 'commit' carries the
        latched set and drives the actual action (single press or chord), so the
        release-edge combo semantics are unchanged. 'press'/'release' edges are
        the momentary (hold) mode hook point — surfaced but not consumed yet."""
        for kind, payload in events:
            if kind == FS_COMMIT:
                self.handle_footswitch_event(payload)
            # press/release: reserved for a future momentary mode; no-op for now.

    def handle_footswitch_event(self, status):
        print(f'Footswitch event: {status}')
        # In the tuner, any footswitch activity exits back to overview
        # (stomp-to-exit, like a hardware tuner pedal).
        if self._in_tuner:
            self.exit_tuner()
            return
        # Ack each press with a red flash on its LED. LedView ignores this while
        # a takeover (tuner/metronome) owns the surface, so no mode guard here.
        for i, s in enumerate(status):
            if s == 1:
                self.led.flash(i)
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
        # Outer-pair chord (the only non-adjacent one): stage panic button.
        elif status == [1, 0, 0, 1]:      # A+D -> global bypass toggle
            self.bypass_all()
        elif status == [0, 0, 0, 0]:
            print("How is this possible?")
        else:
            print("Invalid footswitch combination")

    def bypass_all(self):
        """Stage panic button (A+D chord): toggle a global kill switch.

        ENGAGE: remember each effect's current bypass state, then bypass
        everything (per-effect backend.bypass_effect, same path as the ':bypass'
        branch of parameter_changed). DISENGAGE: restore the remembered map —
        effects added since engage (not in the map) are left untouched. The
        restore map is board-scoped: refresh_pedalboard resets it (stale-restore
        guard), so a board/snapshot switch silently drops the engaged state."""
        if not self._global_bypass:
            self._bypass_restore = {e.instance: e.bypassed
                                    for e in self.pedalboard.effects}
            for effect in self.pedalboard.effects:
                if self.backend.bypass_effect(effect.instance, True) is None:
                    effect.bypassed = True
            self._global_bypass = True
            self.view_update_effect()
            self._notify(strings.tr('toast.globalBypassOn'))
            # All four LEDs blink to confirm the kill switch is engaged.
            self.led.flash_all(times=2)
        else:
            for effect in self.pedalboard.effects:
                if effect.instance not in self._bypass_restore:
                    continue  # added after engage -> leave as-is
                prev = self._bypass_restore[effect.instance]
                if effect.bypassed != prev and \
                        self.backend.bypass_effect(effect.instance, prev) is None:
                    effect.bypassed = prev
            self._global_bypass = False
            self._bypass_restore = {}
            self.view_update_effect()
            self._notify(strings.tr('toast.globalBypassOff'))

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
            # Mode 1: STOMP (per-effect bypass toggles). Resolve the 4 slots from
            # the manual per-board overrides + the auto front-2/back-2 pick
            # (_resolve_stomp_slots); a None slot is left unbound. Each bound slot
            # toggles that effect's bypass. stomp_effects is length-4 so captions,
            # LED bindings and the assigns line up 1:1 by index.
            slots = self._resolve_stomp_slots()
            self.stomp_effects = slots

            def toggle_bypass(instance):
                # Read the LIVE effect at PRESS time and compute the toggle
                # direction from its current bypass -- never from a snapshot
                # captured at bind time, which a model rebuild (refresh_pedalboard)
                # would have left stale (wrong direction / no-op presses).
                live = self.pedalboard.get_effect_by_instance(instance)
                if live is not None:
                    self.parameter_changed(instance, ':bypass', not live.bypassed)

            self.footswitch_assigns = [
                (lambda inst=eff.instance: toggle_bypass(inst)) if eff is not None else None
                for eff in slots
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
                self._notify(strings.tr('toast.noBank'))
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

        elif self.footswitch_mode == TAP_TEMPO_MODE:
            # Any single press is a beat tap; chords exit (handle_multiple_footswitches).
            self.footswitch_assigns = [self.tap_input] * 4

        # Binding changed -> refresh the LEDs' resting colours (mode-2 fallback
        # returns early above, but its recursive assign_footswitches already did).
        self._push_led_bindings()

    def _board_fs_map(self):
        """Manual FS overrides for the CURRENT board as {slot_int: instance}.
        JSON keys are strings (int slots don't survive a round-trip); non-int
        keys are dropped defensively."""
        pb = ((self.pedalboard.current_pb_path if self.pedalboard else "") or "")
        out = {}
        for k, inst in (self._fs_assigns.get(pb, {}) or {}).items():
            try:
                out[int(k)] = inst
            except (TypeError, ValueError):
                pass
        return out

    def _resolve_stomp_slots(self):
        """The 4 effects bound to FS0-3 in STOMP mode, as a length-4 list of
        Effect|None. Manual per-board overrides are placed first (each on its
        slot, if the instance still resolves on this board); the remaining empty
        slots are auto-filled left-to-right from the category-filtered
        front-2/back-2 picks, skipping any effect already placed manually.

        This also fixes the old all-or-nothing auto: a small board (<4 toggleable
        effects) used to bind NOTHING; now manual pins still hold and auto fills
        whatever it can."""
        effects = self.pedalboard.effects if self.pedalboard else []
        filtered = [e for e in effects
                    if not any(str(c).lower() in _STOMP_EXCLUDED for c in (e.category or []))]
        slots = [None, None, None, None]
        placed = set()
        for slot, inst in self._board_fs_map().items():
            if 0 <= slot < 4:
                eff = self.pedalboard.get_effect_by_instance(inst)
                if eff is not None:
                    slots[slot] = eff
                    placed.add(eff.instance)
        auto = []
        if len(filtered) >= 4:
            for e in (filtered[0], filtered[1], filtered[-2], filtered[-1]):
                if e.instance not in placed and e not in auto:
                    auto.append(e)
        ai = 0
        for i in range(4):
            if slots[i] is None and ai < len(auto):
                slots[i] = auto[ai]
                ai += 1
        return slots

    def fs_slot_for(self, instance):
        """The STOMP footswitch slot (0-3) this effect is MANUALLY pinned to on
        the current board, or -1 if unpinned. Drives the FOCUS card's A/B/C/D
        highlight (auto-picked, non-pinned slots read as -1 -- the card only
        reflects explicit user assignment)."""
        for slot, inst in self._board_fs_map().items():
            if inst == instance and 0 <= slot < 4:
                return slot
        return -1

    def assign_focus_to_fs(self, instance, slot):
        """FOCUS card: pin effect ``instance`` to STOMP footswitch ``slot`` (0-3)
        on the current board, or UNPIN if it already holds that slot (toggle).
        An instance occupies at most one slot, so it's cleared from any other
        slot first; pinning a slot another effect held replaces it. Persists the
        overlay and, if STOMP is live, re-resolves the strip + LEDs. Returns the
        slot now holding it, or -1 when unpinned/out of range."""
        if not (0 <= slot < 4) or self.pedalboard is None:
            return -1
        pb = self.pedalboard.current_pb_path or ""
        prior = self._fs_assigns.get(pb, {}) or {}
        board = {str(s): inst for s, inst in prior.items()
                 if inst != instance}                    # drop this instance from every slot
        if prior.get(str(slot)) == instance:
            result = -1                                  # re-tapped its own slot -> unpin (already dropped)
        else:
            board[str(slot)] = instance                  # occupy target (replacing any prior holder)
            result = slot
        if board:
            self._fs_assigns[pb] = board
        else:
            self._fs_assigns.pop(pb, None)
        utils.save_fs_assigns(self._fs_assigns)
        if self.footswitch_mode == 1:
            self.assign_footswitches()          # re-resolve slots -> LED bindings
        self.view_update_effect()               # rebuild the FS strip (mode-1 captions)
        self.view_render_parameters(instance)   # refresh the FOCUS card's A/B/C/D highlight
        return result

    def view_update_bpm(self):
        self.view.update_bpm_display(self.pedalboard.bpm)

    def set_bpb(self, value):
        """CONFIG hub picked a new beats-per-bar -> tell MODEP, keep the model
        in sync (write-through discipline mirrors _tap_on_bpm)."""
        error_msg = self.backend.set_bpb(value)
        if error_msg is None:
            self.pedalboard.bpb = int(value)
        else:
            self._notify(strings.tr('toast.timeSigFail'))

    # ── Tap tempo (entered via the C+D footswitch chord) ─────────────────
    def enter_tap_tempo(self):
        """Switch into tap-tempo: every footswitch press becomes a beat tap and
        the physical LEDs run a metronome at the current tempo."""
        if self.footswitch_mode == TAP_TEMPO_MODE:
            return
        self._mode_before_tap = self.footswitch_mode
        self.footswitch_mode = TAP_TEMPO_MODE
        self.assign_footswitches()
        self.led.metronome_start()   # the metronome takes the LED surface
        self.view.update_mode_display(TAP_TEMPO_MODE)
        self.view.show_tap_tempo(self.pedalboard.bpm, self.pedalboard.bpb)
        self.tap_tempo.start(self.pedalboard.bpm, self.pedalboard.bpb)

    def exit_tap_tempo(self):
        """Leave tap-tempo (any chord) -> stop the metronome, restore the prior mode."""
        self.tap_tempo.stop()
        self.footswitch_mode = self._mode_before_tap
        self.assign_footswitches()
        self.led.metronome_stop()    # release the surface; restores resting colours
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
            self._notify(strings.tr('toast.tunerNoInput'))
            return
        self._tuner_engine = engine
        self._in_tuner = True
        self.view.show_tuner(engine)
        # Hand the LED surface to the tuner strobe. LedView pulls the latest
        # reading each tick and owns the entire visual mapping.
        self.led.tuner_start(lambda: engine.get_reading())

    def exit_tuner(self):
        """Leave the tuner -> stop the audio engine + LED strobe, back to overview."""
        if not self._in_tuner:
            return
        self._in_tuner = False
        self.led.tuner_stop()        # release the surface; restores resting colours
        engine, self._tuner_engine = self._tuner_engine, None
        if engine is not None:
            try:
                engine.stop()
            except Exception as e:
                logging.error("tuner stop failed: %s", e)
        self.view.hide_tuner()

    def _tap_on_bpm(self, bpm):
        """Engine produced a refined BPM -> tell MODEP + update the on-screen widget."""
        error_msg = self.backend.set_bpm(bpm)
        if error_msg is None:
            self.pedalboard.bpm = bpm
        else:
            print(error_msg)
        self.view.update_bpm_display(bpm)

    def _tap_on_beat(self, led_index, is_downbeat, duration):
        """Metronome beat callback -> LedView flashes one LED (red downbeat /
        blue off-beat)."""
        self.led.metronome_beat(led_index, is_downbeat, duration)

    def boot_lightshow(self, i=None):
        """Play the boot LED ceremony (see ledview.LedView.boot_show)."""
        self.led.boot_show()

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
        # Assign FIRST (mode 2 fills self.bank_boards and may fall back to mode 1),
        # THEN refresh the mode label + strip so it reflects the final state.
        self.assign_footswitches()
        self.view.update_mode_display(self.footswitch_mode)

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
            ],
            # Which STOMP footswitch slot this effect is manually pinned to (-1 =
            # none) -> the FOCUS card's A/B/C/D highlight.
            "effect_fs_slot": self.fs_slot_for(effect.instance),
        }





