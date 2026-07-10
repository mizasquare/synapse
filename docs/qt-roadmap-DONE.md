# Qt 로드맵 — 완료 아카이브

> [`qt-roadmap.md`](qt-roadmap.md)에서 **완료된 항목**을 옮겨 온 기록. 로드맵은 남은 일만 얇게
> 유지하고, 완료 맥락(커밋·근거·`파일:라인`)이 필요할 때 여기로 포인터를 건다.
> 마일스톤별 최심층 상세는 메모리 `synapse-roadmap`이 권위본. 이주 스택 자체의 결정·검증은
> [`qt-migration-FINISHED.md`](qt-migration-FINISHED.md)에 별도 보존.
>
> ★2026-07-02 재감사: 로드맵이 6-28 이후 머지를 반영 못 해 여럿이 "미완" stale였음. HEAD(코드+커밋)
> 대조로 정정해 아래로 이관. (M7·에디터 트랙 머지·오버뷰 보드매니저·default 제외·STOMP 캡션 등.)

---

## 풋스위치 디바운스·콤보를 HW 추상화로 이관 ✅ (2026-07-11, 로드맵 ④ · 브랜치 TBD)

> pi-stomp §3A의 "의미 유지, 위치만 이동" 리팩터. Presenter 앱레이어에 섞여 있던 디바운스+릴리스엣지
> 콤보 판정을 순수 상태기계로 내려 Presenter를 이벤트 구독자로 슬림화, 그 과정에서 press/release 엣지
> 경로가 생겨 **② 모멘터리(홀드) 모드가 자연히 개통**(소비처만 남음).

- [x] **`FootswitchReader` (신규 `hardwares/footswitches.py`)** — 순수·스레드/I2C 무관 상태기계.
      `poll(raw) -> list[event]`: 틱마다 raw 샘플 하나 먹으면 이번 틱 이벤트 반환. 내부에 `_stable`/`_counts`
      (디바운스)+`_latched`(릴리스엣지 콤보 래치) 소유 — 전부 `_footswitch_poll_loop` 인라인에서 이관.
      이벤트 3종: `('press',i)`/`('release',i)` 디바운스 엣지 + `('commit',status)` 전-릴리스 시 래치 집합 발화.
- [x] **Presenter 슬림화** (`presenter.py`) — `_footswitch_poll_loop`가 `raw 읽기→reader.poll→이벤트 배치 마샬`
      3줄로 축소(부기 24줄 제거), 신규 `_dispatch_fs_events`가 `commit`→기존 `handle_footswitch_event(status)`로 라우팅.
      `handle_footswitch_event`/`handle_multiple_footswitches`/`bypass_all` 등 다운스트림·`footswitch_input_que`
      외 전부 무변경. press/release는 no-op(모멘터리 훅 지점).
- [x] **등가성 증명** — `commit` 이벤트 스트림이 구 인라인 루프와 **2000개 랜덤 시퀀스에서 비트동일**(레퍼런스
      구현 대조 fuzz). +디바운스 임계·단일/오버랩콤보/논오버랩 분리·press/release 엣지 순서 단위테스트.
      풀 시임 통합(실 Presenter offscreen: poll→reader→dispatch→STOMP 토글·A+B 모드사이클) 통과. 기존 focus_pill/prune 회귀 없음.

## LED seam + FOCUS 풋스위치 수동배정 + 부팅 fallback ✅ (2026-07-10~11, 브랜치 `polish/ui-review-fixes`→`fix/pedalboard-boot-fallback`, 머지 `d276ec5`·`2d44999`)

> 로드맵 ③(LED 정상상태 색) 완료 + 폐기 §ABCD의 "재구현 예정"이던 FS 수동배정 구현 +
> 실기 테스트 중 드러난 안정성 버그 일괄 수정. 전 변경 headless/offscreen 자가검증 후 배포,
> 라이브 리그 실기 확인까지 통과. 막판 부팅루프는 **잠재 벽돌 버그**(삭제된 현재보드=크래시)를
> 무대 전에 잡아 fallback으로 영구 방어.

- [x] **③ LED 정상상태 색 + 블링크 후 복원** (`49fa203`) — 흩어져 있던 LED 색·애니 코드를 전부
      **`ledview.py`의 `LedView` seam**으로 이관(QtView에 대칭인 렌더링 표면). surface-owner 상태기계
      (binding/tuner/metronome/boot)로 소유권 조정. `fsledctrl.py`에 `set_resting(state)` 도입 →
      blink 종료 시 OFF가 아니라 **정상상태 색으로 복원**(활성=파랑/바이패스·기타=OFF, 모드별 토큰).
      `_COLOR_BITS`(red 0b10/blue 0b01/purple 0b11). 육안검증 "완벽" 통과.
- [x] **FOCUS 카드 STOMP 풋스위치 수동배정** (`0bb19e6`) — 오버뷰 인스펙터 모니터 패널을 가로 분할
      (monitors│FS-배정 A/B/C/D). 슬롯별 오버라이드(핀/언핀/스틸 토글) + **자동배정**(앞2·뒤2,
      `_STOMP_EXCLUDED`로 sim/amp/cab/utility 제외) 위에 얹힘. **페달보드별 영속**
      (`app_state.json` `fs_assigns`, `utils.load/save_fs_assigns`). `assign_focus_to_fs`/`_resolve_stomp_slots`.
- [x] **실기 테스트 중 안정성 수정 4건** (`0bb19e6`) —
      · **stale-object 토글 버그**: refresh_pedalboard가 모델 재빌드 후 stomp_effects 재해석 안 해
      스트립(stale)↔LED(live) 불일치+역방향 토글 → 클로저가 인스턴스 문자열 캡처+누를 때 live 재조회로 수정.
      · **FOCUS ENGAGED 필 지연**: 풋스위치 bypass가 모델만 갱신·`_focus` 미갱신 → 오버뷰 왕복해야 반영
      → `refresh_plugin_display`에서 focus bypass를 모델서 재동기.
      · **bypass 실패 토스트**: 호스트 무응답 시 "호스트 응답 없음 — 바이패스 실패" 노출(원인=Instrument
      Tuner FSST 로딩 지연으로 mod-ui HTTP 타임아웃, 코드 아닌 호스트 이슈로 판명).
      · **삭제보드 로컬설정 청소**: `_prune_stale_local_state`가 기동 시 디스크에 없는 보드의
      fs_assigns/board_order 항목 제거(빈 호스트 목록이면 보수적으로 미청소).
- [x] **삭제된 현재 페달보드 부팅 크래시 루프 방지** (`37bfa24`) — 현재 보드 삭제 시 호스트가 유령
      포인터 유지→`pedalboard/info` 500→`initialize` None→`view_update_effect` AttributeError→Fatal→
      systemd 무한 재기동(실측 144회). **`_load_pedalboard_with_fallback` 4단계 체인**: 유효 현재보드→
      첫 비-default 보드→default 로드 후 save-as new→인메모리 빈 보드(UI 부팅 보장). +refresh/view_update
      None-가드. 4단계 fallback 테스트 통과, 라이브 리그 BluesBreaker로 자가복구(호스트 dangling 포인터도 해소).

## UI 클렁키니스 리뷰 반영 ✅ (2026-07-10, 브랜치 `polish/ui-review-fixes`, `463d576`)

> Claude Design 점검 문서("Synapse UI 점검") 18주장 코드 대조(일치 15·기각 1·실제가 더 나쁨 2) 후
> 확정분 반영. 헤더 보드명 500px 겹침 주장은 이미 동적 폭으로 수정돼 있어 기각(`main.qml:127`).
> QML 5파일 컴파일 + qt_dev offscreen 샷(오버뷰/에디터/인스펙터/포커스) 자가검증 통과.

- [x] **텍스트 오버플로 6건** — 헤더 스냅샷 폭제한+elide·FOCUS 이펙터명·IN/OUT·모니터명·패치 칩(ElideMiddle)·풋스위치 스트립 py절단(`[:10]/[:12]`)→QML elide.
- [x] **pressed 시각 피드백** — 헤더 버튼 7개+오버뷰 노드 셀(밝은 fill+보더). 낙관적 반영은 의도적으로 안 함(롤백 유령상태 리스크).
- [x] **상시 안내문 제거** — SIGNAL 범례·"노드 탭→포커스"·인스펙터 더블탭 힌트. TAP/TUNER 안내는 풀스크린이라 유지.
- [x] **모달리티 트랩 완화** — 드래그 중 인스펙터 자동 숨김(`win.nodeDragging`)·drag.threshold 4→10·노브 리셋 더블탭→롱프레스(6px 이동가드)·케이블 핸들 26→44px·모드 태그 롱프레스 게이지(홀드 상수 `modeTag.holdMs=1500`).

### 손감각 튜닝 — 1차 확인 OK, 실사용 관찰 계속 (2026-07-10)
> 패널 교체 후 전 항목 1차 체감 양호(사용자 "일단 모두 맘에 든다"). 아래는 계속 써보며
> 미세조정할 후보 상수들 — 문제 느껴지면 해당 상수부터.
- [~] pressed 피드백 체감 (헤더 버튼·노드 셀) — OK
- [~] threshold 10px — 탭 오판정 vs 드래그 둔함 균형 OK (`drag.threshold`)
- [~] 노브 롱프레스 리셋 — 미세조절 중 오발동 없음 (기본 800ms + 6px 가드)
- [~] 모드 태그 게이지 1.5s — `PedalboardEditorView.qml` `modeTag.holdMs`
- [~] 드래그 시 인스펙터 숨김/복원 — 자연스러움 OK
- [~] 케이블 핸들 44px — 인접 변 탭 충돌 없음

## 마일스톤 일괄 폴리싱 ✅ (2026-07-09~10, 브랜치 `polish/remaining-milestones` 9커밋)

> 울트라코드 워크플로우(정찰 8 → 순차구현 7+통합검증 → 7관점 리뷰+3-스켑틱 검증 44에이전트)로
> 로드맵 ②③의 자가테스트 가능 항목을 일괄 완료. 전 항목 fake+offscreen 자가검증 통과,
> 리뷰 확정 결함 11건 후속 수정(`d6256f4`). **실기 육안확인은 터치패널 교체 후** (아래 대기 목록).

- [x] **add_effect/remove 실패사유 surfacing** (`357ca65`) — `_graph_mutation_result` 헬퍼: HTTP status+body를 토스트로 노출, 음수코드를 성공으로 오판하던 것 방지. Fluid* 진단의 앱측 개선분.
- [x] **박자표(bpb) 설정** (`4456482`) — ⚙MENU CONFIG 리프 스텝퍼(2..12), presenter.set_bpb/qtview 슬롯, fakemodep 영속화, qt_dev `--hub` 훅.
- [x] **Bypass-all 패닉 토글** (`73a5cd3`) — A+D 코드([1,0,0,1]), 복원맵(엔게이지 시점 상태로 원상복구), refresh/보드전환 시 리셋, 4 LED red blink.
- [x] **이펙터 타입 구분 model/param** (`9d6d104`) — `Effect.is_model_effect(=bool(patches))`+`loaded_model_name`, 오버뷰 노드 큰 이름+모델 파일명 부제. `--real` 렌더로 실보드(AIDA-X/IR) 확인됨.
- [x] **오버뷰 스냅샷 브라우저 모달** (`80ec447`) — qtview snapList/selectSnapshot, 헤더 SNAP 버튼(보라), 보드매니저 패턴 복제, qt_dev `--snaps`.
- [x] **보드 내비게이션 순서 사용자 제어** (`159bc16`) — `~/.modep/app_state.json` `board_order` 오버레이(연구: mod-ui는 ASCII 정렬 고정, 뱅크는 NAVIGATE 정답 아님), presenter 층 중앙화(_ordered_board_entries), 보드매니저 위/아래.
- [x] **LV2 이펙터 프리셋 적용** (`eb9e655`) — 5계층(preset_load 래퍼/계약/fake/카탈로그 presetList/인스펙터 칩). 로드맵의 "이름 노출까지 완료" 기술은 오류였음 — 카탈로그가 리스트를 버리고 있어 노출부터 신설.
- [x] **에디터 _uid 미동기화 픽스** (`3dbc2b9`) — 시드 후 첫 라이브 add가 시드 노드 id 재사용 → 케이블 오라우팅(QUICK에선 실호스트 오배선 push 위험). 사용자 제보 "중복 게이트 라우팅 버그"의 진범.
- [x] **리뷰 확정 결함 11건 수정** (`d6256f4`) — 프리셋 칩 스크롤 클램프(실기 25프리셋 오버플로)·프리셋 dirty 표시·60s 타임아웃+bg 로드·단일 토스트·EffectPresetLoad notify_synapsin 훅(mod-tweaks)·SNAP 모달 snapsChanged·헤더 타이틀 침범·보드/뱅크매니저 터치룰(48px)·SYNAPSE_STATE_DIR dev 격리·app_state 비-dict 가드·fake add_effect 포트 시드.

### 실기 검증 대기 (터치패널 교체·재조립 후)
- [x] **터치패널 복구 확인** (2026-07-10) — 플렉스 재라우팅 후 `touchtest.py`+`rawtouch.py` 재검증 통과, 구 데드밴드 소멸. 상세 hardware.md.
- [x] **eglfs 메뉴 종료권한 리그레션 해결** (2026-07-10) — 세션리스 시스템서비스라 `systemctl poweroff`가 polkit에 막힘. `deploy/ui-service/49-synapse-power.rules`(miza에게 power-off/reboot 4액션 허용)로 해결, pkcheck 4/4 검증. 상세 qt-migration-FINISHED §5.
- [x] **mod-tweaks 재배포** (2026-07-10) — `sudo mod-tweaks/deploy.sh`로 `EffectPresetLoad notify_synapsin` 훅 라이브 반영(webserver.py, notify 15→16), `--check` 전부 `[동일]`, modep-mod-ui 재시작, 앱 graceful 재접속 확인. ※앱 자체 프리셋칩은 이 훅 없이도 self-refresh로 동작 — 훅은 웹UI발 프리셋 로드 desync 방지용(포크↔라이브 패리티 유지).
- [x] **신기능 육안확인 통과** (2026-07-10) — 스냅샷 모달·보드 위/아래·프리셋 칩(실 mod-ui 왕복)·bpb·bypass-all(풋스위치 A+D)·모델형 노드 부제 전부 확인, 이상 없음.
- [x] **C* Click add 재시도 통과** (2026-07-10) — 진범이던 데드밴드 해소 후 정상 add 확인.
- [x] **탭템포 실검증 통과** (2026-07-11) — 탭→BPM 반영 + LED 메트로놈 동기 실기 확인(로드맵 ① 잔여였음).
- [x] **오버뷰 렌더 육안검증 통과** (2026-07-11) — 노드 라벨 스네이크그리드(`b06dbad`: 실 이펙트명 박스 내 머무름·U턴 케이블 자연스러움) + 플랫 다크 카드(480 화면 클리핑 없음). 오버뷰 노드 부제 확인과 동시에 실화면 확인, 로드맵 ⑤ 잔여였음.

## 데드코드 재수색 2R + 라이브 버그 + 스테일 문서 스윕 ✅ (2026-07-03)

> 대멸종(`07a8115`) **이후** 6렌즈 재수색 + 적대적 검증(60에이전트 워크플로우)으로 스윕이 놓친 잔재를
> 추가 확정. 덤으로 데드코드가 아닌 **라이브 버그 1건** 발견·수정. 세 브랜치로 분리 머지.

- [x] **인스펙터 ACTIVE/BYPASSED 칩 no-op 버그 수정** (브랜치 `fix/inspector-bypass-chip`) — 칩이
      `editor.toggleBypass(editor.sel)`을 호출했으나 `sel`은 pyqtProperty로 노출된 적 없는 평범한 파이썬 속성 →
      QML에선 undefined → `@Slot(int)`가 0으로 강제변환 → 노드 id는 1부터라 `_node(0)=None` → **조용히 no-op**
      (잠복 버그, 대멸종과 무관). 캔버스 전원버튼(438/475)은 `modelData.id`라 정상. 수정: 인자 없는
      `toggleSelectedBypass()` 슬롯 추가(`closeInspector`/`resetParams`와 동일 패턴, 내부 `self.sel`) + QML 교체.
      워크플로우가 오프스크린 PyQt6 재현으로 실증. **★Pi 육안검증: 인스펙터에서 이펙트 선택 후 칩 클릭 시 실제 토글되는지.**
- [x] **데드코드 A버킷** (브랜치 `chore/deadcode-round2`, ~170줄) — 호출자 0을 레포 전체 grep(QML·셸·systemd·
      tools·deploy 포함)으로 확인.
      - `hardwares/MCP23017.py` ~123줄: 인터럽트 API 전체(`configSystemInterrupt`/`configPinInterrupt`/`readInterrupt`/
        `clearInterrupts`/`_readInterruptRegister` + 전용 상수). 풋스위치는 폴링이 확정 정답([[polling-vs-interrupts-decision]]).
        포렌식: 이 경로만 `self._lock` 미적용 + `readInterrupt`는 `mirrorEnabled` 미초기화로 실행 시 AttributeError →
        한 번도 안 돌아본 코드. 칩 안전 기본값 쓰는 `__init__`/`cleanup`의 `GPINTEN*`/`INTCON*`/`DEFVAL*`은 존치.
      - `hardwares/Adafruit_I2C.py` ~45줄: 미사용 벤더 메소드 6개(`reverseByteOrder`/`write16`/`writeRaw8`/`readS8`/
        `readU16`/`readS16`). `readU16`은 유일 호출자가 죽은 `readS16`이라 이행성 데드. ADS1115는 자체 레지스터 처리.
      - `presenter.py`: 미사용 `import json`.
      - **존치(오탐 방지)**: `ADS1115.py` 인터럽트-인접 11개 메소드(차동읽기·컴퍼레이터)는 볼륨페달 Phase 2 자산.
- [x] **스테일 문서 스윕** (브랜치 `docs/stale-sweep-roadmap-rewrite`, 18곳) — 대멸종/후속 머지가 문서에 반영 안 된 것 정정.
      - `README.md`: 온디바이스 웹UI "What it does" 불릿·footswitch `3`=web UI(존재 안 함)·configs.py 설명(삭제 상수)·
        깨진 `app.py` 링크·`mastervolume.py`/`deploy/` 누락·tests `cochlea_selftest` 누락·rough-edges 완료항목·tools obsolete 표기.
      - `REFERENCES.md`: chromium 실행이 presenter.py에 있다는 스테일 → 폐기 완료로.
      - `editor_bridge.py:273` docstring "manual rescan"(삭제됨), `cochlea/__init__.py` T1 미래형 독스트링(튜너 완료),
        `requirements.txt` PIL/pyserial 주석(앱 미사용), `ui-design-rules.md` 키보드 shim `1~4`→`Z/X/C/V`,
        `expression-pedal-handoff.md` "커밋 안 함"(실제 `1abab37`/`27f84e5` 커밋됨), `pedalboard-editor-handoff.md` M7 미래형.
      - **로드맵 우선순위 축 재배열**: 안정성→기능→설계미덕→아키텍처→미관. 이미 완료된 3항목([undefined]→bool·
        플랫카드 좌표계·네이밍 리팩터) 감사 정정 노트로 이관, HTTP 배칭 전제오류 정정.

---

## Tier 3 정리 — 데드코드 스윕 ✅ (2026-07-03, 브랜치 `chore/deadcode-sweep`)

> Kivy→Qt 이주 잔재 + 미배선 고아 일괄 제거. ~319줄 삭제(7파일). 구문·잔존참조·import 스모크 검증. 6에이전트 스윕 교차확인.

- [x] **WebUI 온디바이스 경로** — `open_webui`/`close_webui`/`xdotool` + qtview `minimize`/`restore`/`enable_webui_button` 스텁 + FS mode-3(WEBUI). QML 미호출 죽은 섬. (웹UI는 폰/옆 데스크톱 접속으로 유지, 온디바이스 Chromium만 폐기.)
- [x] **wvkbd 온스크린 키보드 체인** — `qtview.toggleKeyboard`(QML 미호출) → `presenter.toggle_keyboard` → `utils.toggle_wvkbd`. 설계상 텍스트입력=실물 HW 키보드가 정답(`main.qml:628` 주석 확인).
- [x] **ABCD 완전 폐기** — `abcd_button_state`/`abcd_button_state_change`/`abcd_availability` + qtview `set_abcd_availability` 스텁 + modechange 호출. 기능(포커스 이펙터→FS 바인딩)은 **추후 오버뷰-인스펙터 이펙터 배정으로 재구현 예정** — 진짜 기능 심을 때 다시 넣기로. [[abcd-button-intent]].
- [x] **pb_ss RECALL 섬** — 옛 mode-2(RECALL, 현 BANK로 대체) `recall_pb_ss`/`assign_pb_ss_to_footswitch` + `fs_assignment_data` init + `utils.load/save_footswitch_assignments`.
- [x] **미배선 고아 메소드** — `set_beat`(bpm/bpb 래퍼, 미배선 — bpb 설정 신규는 로드맵으로 이관), modepctrl `get_pedalboards_in_bank`/`get_last_pedalboard`/`set_last_pedalboard`/`load_next_snapshot`/`load_prev_snapshot`/`get_snapshot_name`, `view_mode_change`/`view_update_footsw_display` 스텁, `footswitch_combo_assigns` 빈 dict.
- [x] **editor_bridge QML 고아** — `roundTripOK`+`round_trip_ok`(체인), `rescanCatalog`, `effectCount`, 미사용 `QTimer` import.
- [x] **기타** — `utils.optimize_for_newline`(Kivy 트렁케이터, 결과버림 버그), `cochlea/hum_filter.denotch_spectrum`, `configs` Kivy 상수(`SCALE_FACTOR`/`PLG·PRM_MAX_CHARACTERS`/`FONTS`/`FONT_DIR`/`DEFAULT_USER_FILES_DIR`).
- **존치 판단**: `boot_lightshow`(부팅 LED 세리머니 — 라이브·호출됨, 로드맵의 "죽은 스텁" 표기는 오탐), `taptempo.set_meter`·`cochlea/tuner_engine.set_a4`(재사용 엔진 public API), `last_board` 파일/`LAST_PEDALBOARD` 상수(외부 pisound 버튼 스크립트 사용 가능성). `EffectPort.set_value` 잉여인자는 이미 active-record 청산(순수 데이터화) 때 제거됨 — 별도 할 일 없었음.

---

## Tier 1 — 라이브 무대 신뢰성 ✅ (전부 완료)

- [x] **HTTP timeout 추가** (2026-06-25, `1074b5e`) — `_request`에 `setdefault("timeout", 2.0)` + 8개 직접 호출
      전부 `timeout=2.0`. ★노브/토글 드래그 시 앱 프리즈의 **실제 원인**(동기 무타임아웃 `requests.post` → mod-ui wedge에 GUI 영구블록).
- [x] **`_request` None 반환 가드** (2026-06-26) — 9개 메서드 가드. 선재 크래시 3건 수정: `effect_get_information`의
      `logging(...)` 모듈호출 TypeError, `get_current/last_pedalboard` bare-attr NameError.
- [x] **콜드부팅 게이트** (2026-06-26) — `_modep_ready()` non-None 프로브 + "MODEP 대기 중…" QML 스플래시
      (`screen=="booting"`)→무한대기→GUI스레드 presenter 구성→overview.

### Tier 1 후속 — 페달보드 저장 영속성 + ttl 부패 (2026-06-26, 중대)
> 포스트모템 = [`save-corruption-postmortem.md`](save-corruption-postmortem.md).
- [x] **저장 영속성 복구** — full-URL 더블-prefix 404 → 바른 endpoint + `data=`(form).
- [x] **앱측 저장 가드** — `symbolify(title)[:16]`≠번들dir면 저장 중단+로그.
- [x] **서버측 구조적 차단(mod-tweak)** — `host.py:3965` ttl 심볼을 번들 dir명에서 도출 → `dir==ttl==manifest` 보장,
      웹발 stale-title 저장도 부패 불가. `sudo deploy.sh` 배포.

## 페달보드 에디터 트랙 M1~M7 ✅ (가장 무거운 덩어리 — 완료 + **master 머지 `ddf170a`**)

> 진실원 = `presenter.pedalboard`. 목업 본체: `editor_bridge.py` + `qml/PedalboardEditorView.qml` +
> standalone `qt_editor.py`. 각 마일스톤 끝 Pi 육안검증. **브랜치 `pedalboard-editor` → master 머지됨(`ddf170a`).**

- [x] **M1 — 임베드** (`main.qml editScreen` Loader, `editor` 컨텍스트, 라이브 앱 `showFullScreen()`+`Ctrl+Q`).
- [x] **M2 — 읽기전용 라이브 로드** — `enterLive()`→`_seed_from_pedalboard`. **정수 gnode id↔라이브 인스턴스**
      (`_gid_by_inst`/`_inst_by_gid`). Connection→포트키, HW→IN/OUT, `vals`=라이브값.
- [x] **M3 — 파라미터·바이패스 라이브 쓰기** — 인스펙터→`parameter_set`/`bypass_effect`, **FOCUS throttle 재사용**.
      부수: `EffectPort.set_value` `print('wow')` 제거, `qtview.setParameter` 드래그 throttle(40ms).
- [x] **M3.5 — patch_set(NAM·IR·cabsim 파일)** (`e89a458`+`cf0fcfe`) — 공유 `qml/PatchPicker.qml` +
      `presenter.list_patch_files`. mod-ui `fileTypes`→`configs.PATCH_FILE_TYPE_EXTS`. [[param-vs-patch-set]].
- [x] **M4 — 라이브 그래프 read + 그래프변형 4종** (`3b9f163`·`4fba6c3`) — `syn_dump_graph` 포크(stale 디스크 근본해결) +
      `modepctrl` add/remove/connect/disconnect 래퍼 + Backend ABC + fakemodep. [[mod-port-namespaces]].
- [x] **M5 — 구조편집 + 식별자 매핑** (`9779e99`) — 포트심볼 해석층, host-first 낙관반영, 화면진입=호스트재독, 고아보존.
- [x] **M6a/b/c — 보드 로드·저장·스냅샷** (`0e860ae`/`9a28727`/`9074982`).
- [x] **M6d — 라이브 QUICK 모드 + NEW BOARD + 모드 라우팅** (~`e0860ae`) — 생성기=판정기 단일함수 `_quick_wire_keys()`,
      델타 connect-first, evolve/bake 제거. (모드전환 스캔-정류 입자 FX = `49bceb0`.)
- [x] **M7 — 라이브 플러그인 카탈로그** (`cf0ee2c` M7-1 정규화+시임 · `95c5451` M7-2 소스 라이브스왑 ·
      `65e7d61` M7-3 자가치유+수동리스캔 · `90ae6a7` 비동기 추가) — 동결 72-플러그인 JSON → **호스트 전체 설치
      플러그인**. `modepctrl.effect_list()`(`/effect/list`+`/effect/bulk`) + `plugincatalog.normalize()`,
      `editor_bridge._load_live_catalog()` + per-uri 폴백(`_ensure_uri`) self-heal. 16-포트 truncation·프리셋·포트범위
      우회 부수 해소. (동결 JSON은 오프디바이스 dev 폴백으로 잔존.)

### 에디터 후속 — 완료분
- [x] **오버뷰 보드 매니저** — 에디터 안에만 있던 보드 스위처를 오버뷰 헤더로. `qtview.refreshBoards`/`boardList`/
      `boardsChanged`, `presenter.overview_board_entries`(default 제외), `main.qml` BOARDS 버튼→boardsOpen 오버레이.
- [x] **main nav default 보드 제외** — `modepctrl.get_all_pedalboards`가 `default.pedalboard`(빈 스크래치) 필터
      (modepctrl.py:46) → 풋스위치 NAVIGATE가 숨김보드 안 밟음. 에디터와 동일 규칙.
- [x] **뱅크 매니저** (2026-06-29, `feat/bank-manager`) — 오버뷰 헤더 BANK → 풀 CRUD(생성/이름변경/삭제 + 보드
      추가/제거/순서변경 + 활성뱅크). 시임 `modepctrl.get_banks`/`save_banks`, `presenter.bank_manager_*`, `qml bankMgr`.
      폴리싱: 마지막뱅크 삭제금지, 활성뱅크 영속(`~/.modep/app_state.json`). **남은 것: 라이브러리 전체보드 순서정렬 미구현**.
- [x] **UNDO/REDO 제거** (2026-06-29) — 라이브 미배선이라 히스토리 기계 삭제, `_push_hist()`→더티추적 `_touch()`.

## Tier 2 — 완료된 기능

- [x] **FOCUS 컨트롤/모니터 렌더링 개편 + 라이브 미터** (2026-06-25, `1074b5e`) — 컨트롤 6종 분류
      (knob/int/log/toggle/trigger/enum) + 출력포트 신규지원(meter/clip/gauge/numeric), 드로잉 `ControlWidget`·
      `MonitorWidget`, 해석 `model.EffectPort`. 라이브 미터 `monitorfeed.py`(raw WS→`output_set`~30Hz), dB 매핑
      (`20·log10`,-60dB). 설계 [`focus-control-rendering.md`](focus-control-rendering.md).
      **+ enum/toggle 실조작 시각 피드백 수정(`9be8eb2`).**
- [x] **튜너** (2026-07-02, `tuner` 머지 `6cb4357`) — B+C 콤보→풀스크린 QML. 자체 `cochlea/` DSP 클린룸:
      듀얼 NSDF+HPS 교차검증 + 50/60Hz 험 노치 + 스레드엔진(One Euro·노트락·게이팅). 풋스위치 LED 근접도 스트로브.
      순수 numpy. Pi 검증 OK. 후속(선택): 화면 스트로브 폴리싱·A4조정·튜닝중 뮤트·베이스모드.
- [x] **패치/IR 파일 선택기** (M3.5, `e89a458`+`cf0fcfe`) — 위 에디터 M3.5.
- [x] **풋스위치 모드 스펙 재정의** (2026-06-26) — mode0(NAVIGATE)=전체 라이브러리, mode2(BANK)=RECALL 폐기→활성뱅크
      첫4보드를 FS0~3 바인딩. (옛 `recall_pb_ss`/`assign_pb_ss_to_footswitch` 죽은코드 잔존→Tier 3.)
- [x] **STOMP 스트립 캡션 일치** (`5449552`) — 스트립이 첫4개 표시 ≠ presenter 카테고리필터 토글대상 이던 것 정합.
- [x] **페달보드 다른이름 저장** (M6b, `9a28727`) — `save_pedalboard_as`(asNew=1, dir=symbolify=부패면역) + 에디터 SAVE AS.
- [x] **스냅샷 SAVE/SAVE AS/EDIT + 네이밍 모달** (2026-06-26) — 오버뷰 헤더 3버튼. SAVE AS=3+2 네이밍 모달
      (`Drive-cupcake`식, 접미사풀 `resources/snapshot_words.txt` Hunspell 6천 lazy+캐시). 신규 토스트 시스템.
- [x] **토스트 / 온스크린 알림** (2026-06-26) — `show_toast`+`toastRequested`+QML 자동소멸(2.6s).
- [x] **⚙ MENU 허브 오버레이 (뷰 라우터 기반)** — `main.qml` `hubOpen`/`hubLeaf`(menu/config/banks/system) 모달 허브.
      SYSTEM=안전종료/재부팅, CONFIG=마스터 볼륨(아래), BANKS=뱅크매니저. 헤더=연주용만. [[overview-ui-hub-decision]].
- **인앱 키보드 폐기** (2026-06-28) — 이름추천기(스테이지 단어 칩)+HW 무선키보드 폴백. 잔재 `toggle_keyboard` 죽은코드→Tier 3.

## 소프트웨어 마스터 볼륨 ✅ (2026-07-02, master 머지 `727b54f`)

> Tier 2 "볼륨페달" 항목의 게인 인프라를 앞당겨 구축. 상세 =
> [`../deploy/volume-service/README.md`](../deploy/volume-service/README.md), 설계·측정 = 메모리 `soft-master-volume-plan`.

- Pisound ALSA `PCM` 드라이버 read-only(`access=r-------`) → 출력단 `mod-monitor:out → system:playback` 사이에
  `jack_mix_box` 게인 스테이지(**synapsevol**) 삽입, MIDI CC7 제어.
- `deploy/volume-service/`: systemd 서비스(synapse 독립) + rewire/revert/install + tools(재보정·브링업).
- `mastervolume.py`: CC7 송신 + 실측 dB 테이퍼(jack_mix_box=linear-in-dB `0.5545·CC−70.4`, EXP=2 제곱법칙).
- config 마스터 볼륨 슬라이더(`qtview`/`main.qml`) + 연속 스로틀. 지속성: mod-monitor↔playback 재배선은 MOD 튜너
  뮤트 경로만 건드림(synapse는 cochlea 튜너라 안전).
- **Phase 2(남음)=볼륨페달 ADS 통합**(게인토글 감지 + 언플러그 CC7 127홀드 스펙 정의됨) → 로드맵 "볼륨페달".

## Tier 3 — 완료된 정리

- [x] **노드 라벨 겹침** (2026-06-25, `b06dbad`) — 스네이크 그리드(행당 4노드 170×72, 라벨 2줄, 세로스크롤). ★Pi 육안검증만 추후.
- [x] **docstring 'PySide6' 잔존** (2026-06-28) — `fakehardware`·`backend`·`hardware`·`qtscheduler` PyQt6 정정.
- [x] **untracked 파일 커밋** (2026-06-25, `1074b5e`) — `qt_smoke.py`·`requirements.txt` 커밋.
- [x] **죽은 `set_snapshot` 스텁 제거** (`16fbb2c`).

## 라이브 검증 — 완료분

- [x] **FOCUS 실백엔드** (2026-06-25) — 노브 드래그가 실 MODEP 파라미터 바꿈.
- [x] **역방향 싱크** (2026-06-25) — 소켓으로 웹발 PB전환 앱 실시간 반영 + 모니터 피드 `output_set` 수신.
      한계: MIDI/HMI **직접** 변경은 mod-ui가 notify 안 함.

## 해소된 설계 결정

- **이펙터 프리셋 백엔드** ✅ — mod-ui `get_plugin_info` 프리셋 `{uri,label}` + `/effect/preset/load` 존재. 적용 래퍼만 남음(→로드맵).
- **온스크린 키보드** ✅ = 폐기(2026-06-28).
