from collections import defaultdict
import utils
from hardwares import fsledctrl
from modepctrl import ModepController, initialize_modep_pedalboard
import subprocess
import threading
import time

import json
import os
from configs import LOCAL_STORAGE

class Presenter:
    def __init__(self, view, scheduler):
        self.view = view
        # scheduler: event-loop timer abstraction (see scheduler.Scheduler).
        # Keeps the presenter and hardware layer free of any GUI-framework import.
        self.scheduler = scheduler
        self.hwi = fsledctrl.Controller(scheduler)

        # 0: pedalboard nav, 1: parameter assign, 2: pb snapshot assign
        self.footswitch_mode = 0
        self.footswitch_assigns = {0: None, 1: None, 2: None, 3: None}
        self.footswitch_combo_assigns = {}
        self.footswitch_input_que = [0] * 4
        self._poll_thread = None
        self._poll_stop = None
        self.start_footswitch_polling(100)  # background thread @100Hz

        # Load pedalboard model
        self.pedalboard = initialize_modep_pedalboard()
        # pb별 마지막 활성 스냅샷 기억 (세션 한정 인메모리). key=current_pb_path, value=snapshot idx
        self.pb_snapshot_memory = {}
        # Load stored assignments from disk
        # self.fs_mode2_assigns = load_footswitch_assignments()

        # Build or refresh the pedalboard/snapshot assignment dictionary as needed
        # e.g. ensures we have keys 0..3 present
        self.fs_mode2_assigns = defaultdict(dict)
        for i in range(4):
            if str(i) not in self.fs_mode2_assigns:
                self.fs_mode2_assigns[str(i)] = {
                    "pedalboard_path": None,
                    "snapshot_idx": None
                }

        self.assign_footswitches()
        self.boot_lightshow()

    def initiate_view(self):
        self.view_update_effect()
        self.view_update_bpm()

    def set_beat(self, bpb=None, bpm=None):
        if bpb:
            error_msg = ModepController.set_bpb(bpb)
            if error_msg is None:
                self.pedalboard.bpb = bpb
            else:
                print(error_msg)
        if bpm:
            error_msg = ModepController.set_bpm(bpm)
            if error_msg is None:
                self.pedalboard.bpm = bpm
            else:
                print(error_msg)

    def refresh_pedalboard(self):
        self.pedalboard = initialize_modep_pedalboard()
        self.view_update_effect()

    # ── pb별 마지막 스냅샷 기억/복원 (세션 한정, 풋스위치 PB전환에서만 복원) ──
    def _remember_current_snapshot(self):
        """떠나는 페달보드의 '지금' 스냅샷을 host 기준으로 직접 읽어 기억한다.
        self.pedalboard.current_snapshot_idx 는 마지막 refresh 시점 값이라
        HMI/웹 변경이 아직 안 들어와 있을 수 있으므로 host에 직접 물어본다."""
        pb = self.pedalboard.current_pb_path
        idx = ModepController.snapshot_current_idx()   # host = ground truth, 못 맞추면 -1
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
        ModepController.load_snapshot(idx)
        self.refresh_pedalboard()   # current_snapshot_idx 를 host 기준으로 재확정

    def view_update_effect(self, clear_ports=False):
        if clear_ports:
            self.view.populate_port_area(effectData=None)

        plugins = []
        for effect in self.pedalboard.effects:
            bypass_status = "active"
            if effect.bypassed:
                bypass_status = "bypassed"
            plugins.append((effect.instance, effect.name, effect.category[0], [bypass_status, "unassigned"]))

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
            error_msg = ModepController.bypass_effect(effect_instance, port_value)
            if error_msg is None:
                self.pedalboard.get_effect_by_instance(effect_instance).bypassed = port_value
                self.view_update_effect()
            else:
                print(error_msg)

        effect = self.pedalboard.get_effect_by_instance(effect_instance)
        if effect and port_symbol in effect.ports:
            error_msg = effect.ports[port_symbol].set_value(effect_instance, port_value)
            if error_msg is None:
                self.view.update_parameter_display(effect_instance, port_symbol, port_value)  # Instead of full refresh
            else:
                print(error_msg)

    def patch_changed(self, plugin_instance, patch_uri, patch_file):
        effect = self.pedalboard.get_effect_by_instance(plugin_instance)
        if effect and patch_uri in effect.patches:
            error_msg = effect.patches[patch_uri].set_patch(patch_file)
            if error_msg is None:
                self.view.update_patch_display(plugin_instance, patch_uri, patch_file)  # More efficient
            else:
                print(error_msg)

    # ── 역방향 채널 (mod-ui notify_synapsin → /tmp/synapsin.sock → app.py → 여기) ──
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
            elif cmd in ("EffectAdd", "EffectRemove", "PedalboardLoadBundle",
                         "SnapshotName", "SnapshotRemove", "BankLoad"):
                # 구조 변경 → 안전하게 전체 재동기화
                # (웹발 PedalboardLoadBundle 은 복원 안 함: mod-ui 번들 저장 스냅샷 기본동작 유지)
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

    def apply_external_patch(self, instance, patch_uri, patch_file):
        """외부에서 바뀐 패치파일(IR/NAM/cabsim 등)을 모델 캐시 + 화면에 반영(host 되쏨 없음)."""
        effect = self.pedalboard.get_effect_by_instance(instance)
        if not effect:
            return
        patch = effect.patches.get(patch_uri)
        if patch is not None:
            patch.value = patch_file  # 캐시만 갱신 (set_patch는 host로 쓰므로 호출 안 함)
        self.view.update_patch_display(instance, patch_uri, patch_file)

    def prev_pedalboard(self):
        self._remember_current_snapshot()   # /reset 으로 날아가기 전에 떠나는 보드 기록
        ModepController.set_prev_pedalboard()
        self.refresh_pedalboard()
        self._restore_snapshot_for_current_pb()

    def next_pedalboard(self):
        self._remember_current_snapshot()
        ModepController.set_next_pedalboard()
        self.refresh_pedalboard()
        self._restore_snapshot_for_current_pb()

    def prev_snapshot(self):
        if self.pedalboard.current_snapshot_idx > 0:
            self.pedalboard.current_snapshot_idx -= 1
            ModepController.load_snapshot(self.pedalboard.current_snapshot_idx)
            self.refresh_pedalboard()

    def next_snapshot(self):
        if self.pedalboard.current_snapshot_idx < len(self.pedalboard.list_of_snapshots) - 1:
            self.pedalboard.current_snapshot_idx += 1
            ModepController.load_snapshot(self.pedalboard.current_snapshot_idx)
            self.refresh_pedalboard()

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

        print(f"Footswitch {fs_idx} assigned to PB {pedalboard_id}, snapshot {snapshot_idx}")

    def recall_pb_ss(self, fs_idx):
        """Load pedalboard and snapshot as stored in footswitch_assignments.json"""
        assignment = self.fs_assignment_data.get(str(fs_idx))
        if not assignment or assignment["pedalboard"] is None:
            print(f"No assignment for footswitch {fs_idx}.")
            return

        # Actually load the pedalboard / snapshot
        pb_path = assignment["pedalboard"]
        ss_idx = assignment["snapshot_idx"]

        # Implementation detail: you might have a function that sets pedalboard by ID
        # or you have a different approach for indexing
        error = ModepController.set_pedalboard(pb_path)
        if error is None:
            # Re-initialize your pedalboard object
            self.refresh_pedalboard()
            # Then set the snapshot
            self.pedalboard.current_snapshot_idx = ss_idx
            ModepController.set_snapshot(ss_idx)
            self.view_update_effect()
            print(f"Recalled PB {pb_path}, snapshot {ss_idx}.")
        else:
            print(f"Failed to load PB {pb_path}: {error}")

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
        # For each pressed (or released) footswitch, trigger a blink on its corresponding LED.
        for i, s in enumerate(status):
            if s == 1:
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
        if status == [1, 1, 0, 0]:
            pass
        elif status == [0, 1, 1, 0]:
            pass
        elif status == [0, 0, 1, 1]:
            pass
        elif status == [0, 0, 0, 0]:
            print("How is this possible?")
        else:
            print("Invalid footswitch combination")
        pass


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
            print("꺄홀르")
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
                return

            e0 = valid_effects[0]  # first effect
            e1 = valid_effects[1]  # second effect
            e2 = valid_effects[-2]  # second-last effect
            e3 = valid_effects[-1]  # last effect

            # 3) Define a small helper to toggle bypass:
            def toggle_bypass(effect):
                current_val = effect.bypassed
                self.parameter_changed(effect.instance, ':bypass', not current_val)

            # 4) Assign footswitch 0–3 to lambda toggles of the chosen effects
            self.footswitch_assigns = [
                lambda idx, st: toggle_bypass(e0),
                lambda idx, st: toggle_bypass(e1),
                lambda idx, st: toggle_bypass(e2),
                lambda idx, st: toggle_bypass(e3),
            ]

        elif self.footswitch_mode == 2:
            # Mode 2: recall pedalboard/snapshot from JSON
            self.footswitch_assigns = [
                lambda idx, st: self.recall_pb_ss(0),
                lambda idx, st: self.recall_pb_ss(1),
                lambda idx, st: self.recall_pb_ss(2),
                lambda idx, st: self.recall_pb_ss(3),
            ]

        elif self.footswitch_mode == 3: # WebUI mode
            self.footswitch_assigns = [None, None, None, self.close_webui]

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

    def boot_lightshow(self, i=None):
        # for i in range(4):
        #     self.scheduler.schedule_once(lambda dt, i=i: self.hwi.LED.get_led(i).blink(color='red', times=2, interval=0.1),
        #                         i * 0.3)
        pass

    def save_snapshot(self):
        ModepController.snapshot_save()
        self.refresh_pedalboard()
    def  save_snapshot_as(self, name):
        ModepController.snapshot_save_as(new_name=name)
        self.refresh_pedalboard()

    def modechange(self, mode=None):
        if mode is None:
            mode = (self.footswitch_mode + 1) % 3
        self.footswitch_mode = mode
        self.view.update_mode_display(self.footswitch_mode)
        if self.footswitch_mode == 0:
            self.abcd_availability(False)
        else:
            self.abcd_availability(True)
        self.assign_footswitches()

    def abcd_button_state(self,prev,current):
        print(f"prev:{prev},current:{current}") #-1 is released. 0,1,2,3 is pressed for each button

    def _build_view_effect(self, effect):
        bypassed = ModepController.parameter_get(effect.instance, ":bypass")  # Fetch bypass state correctly
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
                    "port_scalepoints": port.scale_points
                }
                for port in effect.ports.values()
                if (port_value := port.get_value()) is not None  # Exclude ports with None value
            ],
            "patches": [
                {
                    "patch_label": patch.label,
                    "effect_instance": effect.instance,
                    "patch_uri": patch.uri,
                    "patch_file_types": patch.file_types,
                    "patch_file_path": patch.file_path,
                    "patch_value": patch.get_patch(),
                } for patch in effect.patches.values()
            ]
        }





