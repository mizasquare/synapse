# Qt 앱 로드맵

> 🛠 **통합 로드맵 (원 문서).** Kivy→PyQt6+QML+eglfs **이주 스택 자체는 완료**
> (검증 내역 = [`qt-migration-FINISHED.md`](qt-migration-FINISHED.md) 아카이브).
> 이 문서는 그 위의 **남은 기능·신뢰성·정리·부팅·설계결정·검증**을 모은 살아있는 로드맵이다.
> 구 `qt-migration-handoff`(후속작업) + `ui-migration-review`(시안↔현행 갭 분석)를 **흡수·통합**했다.
> 마지막 갱신: 2026-06-25 (FOCUS 컨트롤/모니터 렌더링 + 라이브 미터 피드 세션 — 완료분 `[x]` 반영).

**현재 사실관계:** PyQt6+QML+eglfs 앱이 Pi에서 라이브 동작하고 autostart도 전환됨(`dfd42c6`).
FOCUS 컨트롤/모니터 렌더링 + 라이브 레벨미터 피드까지 라이브 검증됨(커밋 `1074b5e`).
"못 뜨는" 하드 블로커는 없다. 남은 일 = ① 라이브 신뢰성 ② 기능 패리티/신규 ③ 정리/폴리시
④ 무컴포지터 부팅 ⑤ 검증 ⑥ 열린 설계결정 ⑦ 미래. 우선순위 = Tier 1 → 부팅 → Tier 2 → Tier 3.

각 항목은 `파일:라인` 근거로 검증됨. 작업은 한 번에 하나씩, 변경 전 사용자 승인.

---

## Tier 1 — 라이브 무대 신뢰성 (작지만 먼저)

앱은 잘 뜨지만, 호스트가 죽거나 느릴 때 **무대에서 얼어붙지 않게** 만드는 게 핵심.

- [x] **HTTP timeout 추가 ✅(2026-06-25, 커밋 `1074b5e`)** — `_request`에 `setdefault("timeout", 2.0)` +
      8개 직접 get/post 호출 전부 `timeout=2.0`. `parameter_set`/`parameter_get`는 예외처리로 감쌈.
      ★이게 노브/토글 드래그 시 앱 프리즈의 **실제 원인**이었음(동기 `requests.post` 무타임아웃 → mod-ui 핸들러
      wedge에 GUI 스레드 영구블록). 남은 안전화는 아래 None 가드.
- [ ] **`_request` None 반환 가드** — `_request`는 실패 시 None 반환([`modepctrl.py:30`](../modepctrl.py)).
      호출부 `get_snapshot_list`([:170](../modepctrl.py)) · `effect_get_information`([:289](../modepctrl.py)) ·
      `parameter_get` 등이 None 체크 없이 `.json()`/`.content` 호출 → 호스트 500/거부 시 **크래시**. 각 호출부에 None 가드.
- [ ] **콜드부팅 게이트 차단화** — [`qt_main.py:96`](../qt_main.py) `_wait_for_modep`가 타임아웃돼도 그냥 진행 →
      MODEP가 30s 넘게 안 뜨면 **빈/깨진 첫 화면**. 차단 유지 또는 "MODEP 대기" 스플래시.

## 부팅 — 무컴포지터 (남은 이주 항목)

- [ ] **eglfs 풀스크린 부팅으로 전환** — 현재는 labwc 위에서 `qt_main`을 **창모드로** 띄우는 잠정상태
      (`~/run_synapsepy.sh` → `synapse-venv` + `qt_main.py`, autostart=labwc, 커밋 `dfd42c6`).
      목표: lightdm/labwc 제거 후 **eglfs 직행**(systemd 서비스 또는 autologin→eglfs 런처).
      스택 검증은 끝남(FINISHED §4) — 남은 건 부팅 체인 배선. 롤백본 `run_synapsepy.sh.kivy-bak`.
- [ ] **eglfs 런처 견고화** — DSI 커넥터 2개 connected라 자동선택 모호. `run_qt.sh`+`eglfs_kms.json`로
      card/커넥터/모드 고정 + `QT_QPA_EGLFS_HIDECURSOR=1` + (안전기본) `QT_QUICK_BACKEND=software`.
- [ ] **종료 어포던스** — 앱에 quit 버튼/단축키 없음(현재 프로세스 kill만). `main.qml`에 Esc→`Qt.quit()` 등.

## Tier 2 — 기능 패리티 / 신규 (미구현 기능 본체)

**개별 기능**

- [x] **FOCUS 컨트롤/모니터 렌더링 개편 + 라이브 미터 ✅(2026-06-25, 커밋 `1074b5e`)** — 기존 FOCUS가
      **모든 컨트롤을 원형 노브 하나**로 그리고 **출력(모니터) 포트를 통째로 버리던** 문제 해결.
      ① 컨트롤 포트를 LV2 properties로 **6종 분류**(knob/int/log/toggle/trigger/enum), 출력 포트를 **신규 지원**
      (meter/clip/gauge/numeric). 드로잉 분해 `qml/ControlWidget`·`MonitorWidget`, 해석 집약 `model.EffectPort`.
      ② **라이브 레벨미터 피드** `monitorfeed.py`(의존성無 raw WS)가 mod-ui 웹소켓 수동구독→`output_set`→미터(~30Hz throttle, `data_ready` ack).
      ③ 미터 **dB 매핑**(modmeter 출력=선형진폭 0..1이라 선형 norm이면 바가 ~1%만 차 안 보임 → `20·log10`, -60dB 바닥).
      라이브 검증 OK(HighGainRig 신호→바 가시적 움직임). 설계=[`focus-control-rendering.md`](focus-control-rendering.md).
      후속(미완): 패치선택기(아래 별도) · enum/trigger 위젯 **실조작** 검증 · 모니터 tier-2 하드코딩 레지스트리는 빈 채 둠.
- [ ] **튜너** — 콤보 B+C가 `pass`([`presenter.py:402`](../presenter.py)), Qt 튜너 화면 없음.
      ★피치검출 `yin.py`가 `under_vsersion1/`로 빠져 **누락**([`tunerpopup.py:8`](../tunerpopup.py) import 실패).
      필요: YIN DSP 복원(또는 대체) + presenter 배선(탭템포 패턴) + 풀스크린 QML 튜너 화면. (오디오버퍼 파이프는 아이캔디와 공유.)
- [ ] **패치/IR 파일 선택기** — [`qtview.py:192`](../qtview.py) `update_patch_display`가 `pass` →
      FOCUS는 IR/NAM/cabsim을 **읽기전용**([`main.qml:297`](../qml/main.qml))으로만 표시, 기기에서 새 파일 못 부름 +
      역방향 패치변경도 라벨 미갱신. QML 파일선택기 + `PATCH_FILE_DIR_MAP`([`configs.py`](../configs.py)) 재사용.
- [ ] **RECALL 북마크 등록 + FS 설정화면** — recall **실행**은 정상(A+B 모드순환으로 mode 2 진입,
      [`recall_pb_ss`](../presenter.py) `presenter.py:293`). 그러나 [`assign_pb_ss_to_footswitch`](../presenter.py) `presenter.py:274`가
      **어디서도 호출 안 됨** → 현재 PB+스냅샷을 풋스위치에 **북마크 등록할 방법이 없음**(그래서 'No assignment'서 멈춤).
      필요: 등록 캡처 제스처(롱프레스/전용콤보) + 풋스위치 **설정화면**(할당·전역기능 BYPASS ALL/MODE/BOARD◄►/SNAP◄►/TAP/TUNER 매핑).
      (영속화 `utils.load/save_footswitch_assignments`는 정상.)
- [ ] **STOMP 스트립 캡션 일치** — [`qtview.py:351`](../qtview.py) 스트립이 **첫 4개** 이펙트를 보여주는데
      presenter는 **카테고리필터 [0,1,-2,-1]**을 토글([`presenter.py:427`](../presenter.py)) → 캡션이 실제 토글대상과 다름. presenter가 선택 4개를 노출하도록.
- [ ] **스냅샷 브라우저 / 페달보드 브라우저** — 이름으로 점프. 데이터·백엔드 있음(`get_snapshot_list`+`load_snapshot`,
      `get_pedalboards_in_bank`+`set_pedalboard`) → 리스트/모달 UI만. 현재 헤더 라벨([`main.qml:69`](../qml/main.qml),[:82](../qml/main.qml))뿐, prev/next만 가능.
- [ ] **페달보드 다른이름 저장** — `save_current_pedalboard`가 `asNew:0`만 → `asNew:1`+title 확장 + 이름입력 연결.
- [ ] **스냅샷 save-as 이름입력 UI** — 백엔드 배선됨(`save_snapshot_as` [`presenter.py:591`](../presenter.py))이나 Qt 진입점/입력 없음(인앱 키보드 의존).
- [ ] **볼륨페달**(ADS1115→MIDI CC) — [`volumepedal.py`](../volumepedal.py)는 독립 프로세스로만 존재, 앱 폴링 미통합, 화면 미터 없음.
      ★먼저 정의할 미결 스펙: **페달이 물리적으로 미연결일 때 앱 거동**. 코드개선(미적용): 단발→연속모드, 860→64~128SPS, EMA+히스테리시스로 CC 지터 제거.
- [ ] **모멘터리(홀드) 모드** — [`presenter.py:365`](../presenter.py) 폴링이 릴리스엣지 전용 → press-ON/release-OFF 모멘터리 없음.
- [ ] **Bypass-all / 전역 풋스위치 액션** — presenter에 `bypass_all()` 없음.
- [ ] **확장 콤보** — [`presenter.py:408`](../presenter.py) A+B/B+C/C+D 외(A+C·A+D·B+D·3중)는 "Invalid". 콤보→액션 맵 리맵 가능화(→ [`config-todo.md`](config-todo.md)).
- [ ] **이펙터 프리셋** — 블록 단위 설정 저장/불러오기. **진짜 신규**(패치파일 IR/NAM 로딩과 다른 개념). mod-ui LV2 plugin preset 엔드포인트 지원 여부 확인 필요(→ 열린 설계결정).
- [ ] **이펙터 타입 구분(model vs param)** — 앰프/NAM(모델 줄 크게) vs 컴프/게이트(노브만). `patches` 유무/카테고리로 도출 — 모델에 작은 플래그.
- [ ] **LED 정상상태 색** — HW가 red/blue/purple 지원([`fsledctrl.py`](../hardwares/fsledctrl.py))인데 지금은 누를 때 blink만 → 할당/포커스 상태에 따라 **색을 켜둔 채 유지**로.

**화면 구조 (시안 = 상태기반 전환; 현재 = overview/focus/taptempo 3화면만)**

- [ ] **뷰 라우터 / 화면 상태머신 보강** — `view.screen` 프로퍼티로 3화면은 전환되나([`qtview.py:41`](../qtview.py)) **모달**(menu/keyboard/browser/toast)이 없음. 상태머신 확장.
- [ ] **메뉴(☰) 화면** — 3층위 저장/불러오기. 현재 스냅샷 save/saveas만.
- [ ] **토스트 / 온스크린 알림** — presenter가 stdout `print`([`presenter.py:162`](../presenter.py)) → `view.show_toast()` 없음.
- [ ] **인앱 키보드** — `toggle_keyboard`(wvkbd) 있으나([`presenter.py:477`](../presenter.py)) Qt 경로서 호출 안 됨. 시안=자체 QWERTY. (→ 열린 설계결정: 라이브러리 vs 커스텀.)

> 시안 화면 매핑(참고): Overview·Focus·TapTempo=구현됨 / Tuner·Menu·Keyboard·Browser·Toast=미구현 / HW 풋스위치 행=스트립으로 존재.

## Tier 3 — 정리 / 폴리시

- [ ] **WebUI 경로 통째 삭제** — `open_webui`/`close_webui`([`presenter.py:481`](../presenter.py),[:497](../presenter.py)) +
      `xdotool`([:519](../presenter.py)) + `minimize`/`restore`/`enable_webui_button`([`qtview.py:228`](../qtview.py) 등 `pass`) + Kivy bezel 버튼.
      **Qt 경로선 호출조차 안 됨(죽은 코드)**, 온디바이스 웹UI는 스펙서 폐기 결정.
- [ ] **죽은 스텁 제거** — `view_mode_change`([`presenter.py:149`](../presenter.py)), `view_update_footsw_display`([:152](../presenter.py)),
      `footswitch_combo_assigns` 빈 dict([:35](../presenter.py)), `boot_lightshow` 주석처리([:582](../presenter.py)).
- [x] **노드 라벨 겹침 ✅(2026-06-25, 커밋 `b06dbad`)** — 단순 elide 대신 **스네이크 그리드**로 개편(행당 4노드
      170×72, 라벨 2줄 wrap+elide, 세로스크롤 Flickable). 6이펙트 박스겹침0. ★Pi 라이브 육안검증만 추후.
- [ ] **`[undefined]→bool` 경고** — [`main.qml:307`](../qml/main.qml) FOCUS 패치 visible 바인딩, 무해. `!!(...)`로 정리.
- [ ] **docstring 'PySide6' 잔존** — [`qtview.py:1`](../qtview.py) 등 코드는 PyQt6인데 도크스트링은 PySide6. (경위는 FINISHED §2.)
- [x] **untracked 파일 커밋 ✅(2026-06-25, 커밋 `1074b5e`)** — `qt_smoke.py`(스모크앱, 보존)·`requirements.txt`
      (Kivy 베이스라인 insurance로 보존) 둘 다 커밋. Qt 런타임 deps 별도 핀은 `requirements-dev.txt`(PyQt6 6.4.2)가 담당.
- [ ] **`EffectPort.set_value` 잉여 인자** — [`modepctrl.py:457`](../modepctrl.py) 안 쓰는 `effect_instance`를 받음(self.instance 있음). 무해, 시그니처 정리.
- [ ] **LED 블링크 후 정상색 미복원** — [`fsledctrl.py`](../hardwares/fsledctrl.py) blink 끝나면 OFF, 이전색 기억 없음(cosmetic; 위 'LED 정상상태 색'과 연동).
- [ ] **HTTP 50-왕복 초기화 배칭/캐시** — `initialize_modep_pedalboard`가 포트마다 1요청 → 느린망에서 로드 지연. 배칭/캐시 검토.
- [ ] **플랫 다크 카드 / 좌표계** — QML은 이미 플랫 다크(비트맵 자산 폐기)이나, 시안 800×600 vs 실제 800×480 좌표 일관성 점검.

## 라이브 검증 백로그 (Pi 실물)

- [x] **FOCUS 실백엔드 ✅(2026-06-25)** — 노브 드래그가 실 MODEP 파라미터 바꿈 확인(라이브, 실 호스트).
- [ ] **탭템포 실검증** — 탭→BPM 반영 + LED 메트로놈 + `set_bpm` 동기.
- [x] **역방향 싱크 ✅(2026-06-25)** — 소켓(`/tmp/synapsin.sock`)으로 웹발 PB전환이 앱에 실시간 반영 확인 +
      모니터 피드 `output_set`도 라이브 수신(미터 동작). 한계: MIDI/HMI **직접** 변경은 mod-ui가 notify 안 함(기존 한계).

## 열린 설계 결정

1. **이펙터 프리셋 백엔드** — mod-ui가 LV2 plugin preset save/load를 주는가? 아니면 "현재 포트값 묶음"을 앱 JSON으로 자체구현?
2. **온스크린 키보드** — Qt VirtualKeyboard(라이브러리) vs 커스텀 QWERTY. UI 배치와 엮임.
3. **케이블 색 의미** — 시안의 CLEAN/DRIVE/FEEDBACK은 **디자인이 만든 의미**, mod는 source→target만 줌. 현재 전부 단색(green). 규칙 정의(카테고리 기반/피드백=사이클탐지) or 단색 유지.

## 폐기 / 재배치 (의도 확정됨)

- **ABCD 버튼** → 시안엔 없음. "포커스 이펙터를 FS에 수동 바인딩"은 FS 설정화면이 대체. 베젤 ABCD 컨셉 폐기 방향. (잔재 정리는 Tier 3.)
- **WebUI(Chromium)** → 온디바이스 폐기 결정(웹UI는 폰/옆 데스크톱 접속). 코드 삭제는 Tier 3.
- **베젤 합성영역**(save/saveas/pb/ss/mode/bpm) → 해체 재배치: 저장/로드→☰, PB/SS 이동→콤보, 모드→FS 설정, BPM→Tap+헤더.
- **패치파일 파일선택기(IR/NAM)** → "이펙터 프리셋/모델 불러오기" 브라우저로 흡수되는 그림.

## 미래 기능

- [ ] **아이캔디 — 오디오 반응형 캐릭터 애니** — 설계 확정, 엔진 미착수. 튜너 오디오버퍼 재사용. → [`eyecandy_idea.md`](eyecandy_idea.md).
- [ ] **네이밍 리팩터** — Synapse(앱) vs GCaMP6s(박스) 수렴(README 로드맵).

---

## 감사 정정 노트 (재추가 금지 — 오탐이었음)

코드 감사에서 블로커로 잘못 잡혔으나 **실제 코드 검증 결과 정상**인 항목. stale 문서가 원인이니 다시 손대지 말 것:

- **STOMP 클로저 버그 = 오탐.** [`presenter.py:443`](../presenter.py)의 `e0~e3`는 루프변수가 아니라 **서로 다른 변수 4개** → 각 람다가 올바른 이펙트 캡처. 정상.
- **RECALL 실행 = 정상.** 키 'pedalboard'/'snapshot_idx' 통일, `load_snapshot` 사용. (남은 건 등록수단 — Tier 2.)
- **`set_snapshot`(실 백엔드) 불필요.** `recall_pb_ss`가 `load_snapshot`으로 처리, 인터페이스에도 미선언. RECALL 리팩터 시에만 thin wrapper로.
- **WebUI minimize/restore = 블로커 아님.** Qt 경로서 호출 안 되는 죽은 코드 → Tier 3 삭제 대상.

## 참조

- [`qt-migration-FINISHED.md`](qt-migration-FINISHED.md) — 완료된 이주 스택 아카이브(결정·검증).
- [`config-todo.md`](config-todo.md) — 하드코딩→사용자설정 위시리스트(탭템포·콤보·튜너).
- [`eyecandy_idea.md`](eyecandy_idea.md) — 오디오 반응 캐릭터 애니 설계.
- [`ui-design-rules.md`](ui-design-rules.md) — 7" 800×480 2-tier 가시성 룰.
- **시안**: claude.ai/design 프로젝트 `9b9310ef…`("Kivy UI 재구성 방향") — `Pedal Prototype.dc.html`(800×600 인터랙티브) / `Pedal UI 비교.dc.html`(현행+개선안 A~F).
- [`../README.md`](../README.md) · [`../REFERENCES.md`](../REFERENCES.md) — 앱 개요 · 라이브 시스템 레퍼런스.
