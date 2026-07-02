# Qt 로드맵 — 완료 아카이브

> [`qt-roadmap.md`](qt-roadmap.md)에서 **완료된 항목**을 옮겨 온 기록. 로드맵은 남은 일만 얇게
> 유지하고, 완료 맥락(커밋·근거·`파일:라인`)이 필요할 때 여기로 포인터를 건다.
> 마일스톤별 최심층 상세는 메모리 `synapse-roadmap`이 권위본. 이주 스택 자체의 결정·검증은
> [`qt-migration-FINISHED.md`](qt-migration-FINISHED.md)에 별도 보존.
>
> ★2026-07-02 재감사: 로드맵이 6-28 이후 머지를 반영 못 해 여럿이 "미완" stale였음. HEAD(코드+커밋)
> 대조로 정정해 아래로 이관. (M7·에디터 트랙 머지·오버뷰 보드매니저·default 제외·STOMP 캡션 등.)

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
