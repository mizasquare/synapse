# Qt 앱 로드맵 — 남은 일

> 🛠 **살아있는 로드맵 (남은 일만).** 완료 항목은 [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md)로 이관,
> 맥락 필요 시 포인터로 참조. 마일스톤 최심층 상세 = 메모리 `synapse-roadmap`. 이주 스택 결정·검증 =
> [`qt-migration-FINISHED.md`](qt-migration-FINISHED.md).
> 마지막 갱신: **2026-07-11 (③ LED seam 완료·이관 + FOCUS 풋스위치 수동배정 재구현 + 삭제보드 부팅 fallback으로 ① 잔여 재확인. 실기 검증 전 항목 통과.)**
>
> **정렬 원칙 — 우선순위 축:** ① 안정성(크래시/데이터손상/무대 리스크) → ② 기능(미구현 본체) →
> ③ 설계상 미덕(상태를 올바로 드러냄) → ④ 아키텍처 우아함(관심사 분리·유지보수성) → ⑤ 미관.
> 같은 축 안에서는 대체로 규모 작은 것 먼저. 작업은 한 번에 하나씩, 변경 전 사용자 승인.

**현재 사실관계:** PyQt6+QML 앱이 Pi에서 라이브 동작, autostart 전환됨(`dfd42c6`).
페달보드 에디터 트랙(M1~M7)·라이브 플러그인 카탈로그·뱅크 매니저·튜너·소프트 마스터볼륨·
**볼륨페달 Phase 2**·**폴리싱 브랜치**(프리셋 적용·스냅샷 모달·bpb·bypass-all·타입구분·보드순서·
_uid픽스·리뷰픽스 11건, 2026-07-10 머지)·**LED seam+FOCUS FS 배정+부팅 fallback**(2026-07-11)까지
완료. **터치패널은 복구됨**(플렉스 재라우팅,
[`hardware.md`](hardware.md)) — 2026-07-11 재조립 후 **실기 검증 전 항목 통과**(신기능 육안·탭템포·
C* Click·오버뷰 렌더·손감각 1차, [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md) 상단). eglfs 이주가
드러낸 메뉴 종료권한 리그레션도 polkit 규칙으로 해결. 남은 코드 작업은 아래 소항목뿐.

---

## ① 안정성 (라이브 신뢰성 — 최우선)

> ✅ 잔여 없음. **탭템포 실검증**(탭→BPM + LED 메트로놈 동기)은 2026-07-11 Pi 실기 통과 →
> [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md). 인스펙터 ACTIVE/BYPASSED 칩 no-op 버그도 수정 완료(2026-07-03).
> **삭제된 현재 페달보드 부팅 크래시 루프**(잠재 벽돌 버그)는 2026-07-11 4단계 fallback으로 영구 방어 →
> [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md) 상단(`37bfa24`). 볼륨페달 **언플러그 페일세이프**(CC7 램프·홀드)는
> 안정성 성격이지만 볼륨페달 Phase 2(②)에 묶여 있어 그쪽에 기재.

## ② 기능 (미구현 / 부분구현 본체)

> ✅ 2026-07-10 폴리싱 브랜치로 완료·이관: 프리셋 적용 / 스냅샷 모달 / bpb / Bypass-all / 보드 순서
> (+③ 타입구분, 에디터 _uid 픽스, add 실패사유 surfacing) → [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md).

- [x] **볼륨페달 Phase 2 (ADS1115→CC)** — 아키텍처 통합 완료: `reflex.py`(독립 MIDI 장치 서비스,
      `deploy/reflex-service/`) + `synapse-volume` 컨트롤 데몬(`deploy/volume-service/volumectl.py`,
      taper·CC7 private 링크 소유) + 앱 슬라이더 양방향 동기화(state echo). 앱 폴링 통합은
      **의도적으로 하지 않기로 결정**(격리 우선 — reflex는 앱 밖의 장치).
      온디바이스 검증·캘리브레이션·현장 페달 확인까지 완료(2026-07-05,
      [`expression-pedal-handoff-DONE.md`](expression-pedal-handoff-DONE.md)).
- [ ] **볼륨페달 후속(온디바이스)** — **부팅 페달 감지**(게인토글 프로브, ch0) + **config 사용여부 옵션**.
      ~~언플러그 시퀀스~~ → 구현 불필요 판정(2026-07-05): 분리 후 풀업이 캘리 상한을 넘어 CC 127
      유니티로 자연 고정됨 — 실측 확인, [`expression-pedal-handoff-DONE.md`](expression-pedal-handoff-DONE.md) 노트.
      코드개선(미적용): 단발→연속모드, EMA+히스테리시스 CC 지터제거. 앱 내 캘리브레이션 화면
      (reflex 소켓 클라이언트, 프로토콜은 확정됨). (중)
- [ ] **모멘터리(홀드) 모드** — **이벤트 경로는 이제 열림**(2026-07-11 ④ 리팩터로 `FootswitchReader`가
      `('press',i)`/`('release',i)` 디바운스 엣지를 emit). 남은 건 **소비처**: `_dispatch_fs_events`에서
      press/release를 홀드 액션(누르는 동안 engage·떼면 disengage)에 연결 + 홀드 모드 진입 UX. 단일/콤보
      릴리스엣지 판정과 공존하도록 press 즉시발화 vs 콤보윈도 정책 결정 필요(pi-stomp 타임스탬프 윈도 참고). (중)
- [ ] **이펙터 프리셋 (블록 저장/불러오기)** — 사용자 블록 단위 파라미터셋 저장. 위 LV2 preset 적용과 **별개인 진짜 신규**
      (스냅샷=보드 전체, 이건 단일 블록 재사용). 저장소·모델·UI 전무. (중, 후순위)

## ③ 설계상 미덕 (상태를 올바로 드러냄)

> ✅ 2026-07-11 완료·이관: **LED 정상상태 색 + 블링크 후 복원** — LED 렌더 코드를 `LedView` seam
> (`ledview.py`)으로 전부 이관, `fsledctrl.set_resting`으로 blink 종료 시 OFF 아닌 정상상태 색 복원.
> 실기 육안 통과 → [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md) 상단. 잔여 없음.

## ④ 아키텍처 우아함 (관심사 분리 · 유지보수성)

> ✅ 2026-07-11 완료·이관: **디바운스·콤보 판정을 하드웨어 추상화 단으로 이동** — 인라인 디바운스+릴리스엣지
> 래치를 순수 상태기계 `hardwares/footswitches.FootswitchReader`로 내리고 Presenter는 `poll()`이 emit한
> 이벤트만 구독. 릴리스엣지 콤보 의미는 2000개 랜덤 시퀀스 비트동일 검증(의미 유지·위치 이동). press/release
> 엣지도 surface → ② 모멘터리 경로 개통. → [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md) 상단.
- [ ] **i18n / 테마 토큰화 (한 묶음 — 결정 2026-06-28)** — 설계·진행 = [`theme-tokenization-plan.md`](theme-tokenization-plan.md).
      - **테마 토큰화 (색)**: ✅ **완료** 2026-07-11 (`8b9eb72`, Pi 색검증 통과). 언어중립 정본 `theme/tokens.json`
        하나를 QML(`Theme` 컨텍스트 prop)·Python(`theme.py`)이 각자 읽음 → 파이썬 이중소스 함정 해소. 7파일 코드
        hex 리터럴 0, 색토큰 72개. 값 비트동일(collapse 2곳만 sub-perceptual).
      - [ ] **테마 토큰화 (폰트)**: ⬜ Phase 3+4 잔여 — 역할토큰(button/title/smallLabel…) + 27종 px→9스케일
        합리화. 인프라(`scale`/`type` 토큰·`Theme.typeFont`)는 이미 존재, 요소별 역할배정+스냅만. **실제 시각변화 →
        화면별 Pi 확인 필요.**
      - [ ] **문자열 중앙화(i18n)**: 사용자 노출 리터럴 → `resources/strings/<lang>.json` + `tr("key")` 인다이렉션.
        (현재 `qsTr()`/`tr()` 0건, 리터럴이 QML에 직접 하드코딩.) 별건, 미착수.
      - **열린 결정**: 런타임 언어/테마 전환 UI를 config에 둘지, 빌드 고정할지(후순위). (중)

## ⑤ 미관

- [ ] **케이블 색 의미 (열린 설계 결정)** — 오버뷰는 단색 green(`qtview.py:802`). **에디터는 이미 자체 색체계 보유**
      (bypass=회색/활성입력=파랑/스테레오 등, `editor_bridge.py:668~`). 결정 시 오버뷰↔에디터 색의미 이원화 주의.
      시안의 CLEAN/DRIVE/FEEDBACK은 디자인 의미(mod는 source→target만). 규칙 정의 or 단색 유지.
> ✅ **노드 라벨 스네이크그리드**(실 이펙트명 박스 내 머무름·케이블 자연스러움)·**플랫 다크 카드**
> (480 화면 클리핑 없음) Pi 육안검증은 2026-07-11 통과(오버뷰 노드 부제 확인과 동시) →
> [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md).
- [ ] **아이캔디 — 오디오 반응형 캐릭터 애니** — 설계 확정, 엔진 미착수. 튜너 오디오버퍼 재사용.
      폴리싱·기능 다 끝난 뒤. → [`eyecandy_idea.md`](eyecandy_idea.md). (대)

## ✅ 완료 — 무컴포지터 eglfs 부팅 (2026-07-08)

> `deploy/ui-service/` 참조. 부팅 체인: `multi-user.target → synapse-ui.service → run_qt.sh → qt_main.py`
> (eglfs 직행, lightdm/labwc/wayvnc 제거 — VNC는 사용자가 불용 확인). 개발용 데스크톱 복귀 = `sudo revert.sh`.

- [x] **eglfs 풀스크린 부팅 전환** — `synapse-ui.service`(User=miza, Restart=always, `RuntimeDirectory=synapse-ui`)
      + `install.sh`(lightdm disable + set-default multi-user). labwc autostart의 앱 실행 라인은 제거(이중 실행 방지).
      kivy 롤백(`run_synapsepy.sh.kivy-bak`/`app.py` 복원)은 **폐기** — Qt 안정화로 무의미.
- [x] **eglfs 런처 견고화** — `eglfs_kms.json`: 패널을 by-path(`platform-1f00118000.dsi-card`)로 고정
      (DSI-2는 phantom connected — 자동선택 모호 해소), `hwcursor:false` + `HIDECURSOR=1`.
      `JACK_PROMISCUOUS_SERVER=jack` 필수(LevelMeter가 modep jackd에 붙는 열쇠).
      `QT_QUICK_BACKEND=software`는 불필요했음. 실기 확인(2026-07-09, fdinfo `drm-driver: v3d` + `renderD128` 오픈):
      LLVMpipe가 아니라 **V3D 하드웨어 가속**으로 렌더 중 — Mesa kmsro(`drm-rp1-dsi_dri.so`)가 DSI 스캔아웃과
      V3D 렌더를 자동으로 이어줌(무설정). 유휴 GPU 부하 ~2%.
- [x] **원격 육안확인 대체** — grim(Wayland 전용) 사망 → 앱 내장 스크린샷 훅(`qt_main.py`):
      `touch /tmp/synapse-shot.trigger` → `/tmp/synapse-shot.png`. ⚠️ PyQt 함정: QTimer 래퍼/클로저를
      모듈 레벨 `_SHOT_HOOK`에 강참조 고정(안 하면 GC 뒤 세그폴트 — gdb로 확정).
- [ ] **종료 어포던스 (nice-to-have)** — 깨끗한 종료는 `Ctrl+Q`→`Qt.quit()`([`main.qml:30`])와 **⚙MENU→SYSTEM
      안전종료**로 가능(키보드 없는 기기도 종료). ⚠️ SYSTEM 종료는 eglfs 세션리스 서비스라 polkit 규칙
      (`deploy/ui-service/49-synapse-power.rules`)에 의존 — 없으면 조용히 실패(2026-07-11 해결, install.sh 배치).
      남은 건 Esc 키/터치 전용 어포던스뿐 — 편의성.

## 폐기 / 재배치 (의도 확정됨)

- **ABCD 버튼** → 시안엔 없음. "포커스 이펙터를 FS에 수동 바인딩"은 오버뷰-인스펙터 FS 배정으로 **재구현 완료**(2026-07-11, `0bb19e6` — FOCUS 카드 A/B/C/D 슬롯, 자동배정 위 슬롯별 오버라이드+페달보드별 영속 → [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md)). Qt 잔재 삭제는 2026-07-03. [[abcd-button-intent]].
- **WebUI(Chromium)** → 온디바이스 폐기(웹UI는 폰/옆 데스크톱 접속). 온디바이스 코드 삭제 완료(2026-07-03).
- **베젤 합성영역**(save/saveas/pb/ss/mode/bpm) → 해체: 저장/로드→⚙MENU 허브(완료), PB/SS→콤보, 모드→FS 설정, BPM→Tap+헤더.
- **온스크린 키보드(wvkbd/커스텀)** → 폐기(2026-06-28). 이름추천기+HW 키보드 폴백. 런타임 잔재(`toggle_keyboard`/`toggle_wvkbd`) 삭제 완료(2026-07-03). (dev 스크립트 `tools/test.py`는 존치 — README에 obsolete 표기.)

---

## 감사 정정 노트 (재추가 금지 — 오탐이거나 이미 완료됨)

코드 감사에서 블로커/미완으로 잘못 잡혔으나 **실제 검증 결과 정상이거나 이미 끝난** 항목. stale 문서가 원인이니 다시 손대지 말 것:

- **STOMP 클로저 버그 = 오탐.** `presenter.py`의 `e0~e3`는 루프변수 아닌 서로 다른 변수 4개 → 올바른 캡처. (캡션 정합은 `5449552`로 별개 완료.)
- **RECALL 실행 = 정상.** 키 통일, `load_snapshot` 사용.
- **`set_snapshot`(실 백엔드) 불필요.** `load_snapshot`으로 처리(죽은 스텁은 `16fbb2c`로 제거됨).
- **WebUI minimize/restore = 블로커 아님.** Qt 경로 미호출 죽은 코드 → 삭제 완료(2026-07-03).
- **`[undefined]→bool` 경고 = 이미 해결됨.** `main.qml:940` FOCUS 패치 visible 바인딩은 이미 `!!(...)`로 가드됨(`e89a458`). 코드상 후보 없음 — Pi 콘솔에 여전히 뜨면 다른 미식별 바인딩이므로 런타임 로그로 재특정.
- **플랫 다크 카드 좌표계 = 코드는 이미 통일됨.** 800×480로 일관(`main.qml:9-10`). 남은 건 실기 육안검증뿐(→ ⑤ 미관).
- **네이밍 리팩터 = 코드는 이미 수렴 완료.** 라이브 코드에 `GCaMP6s` 참조 0(archived/에만 잔존), 전부 `Synapse`. 코드 TODO 아님 → 하드웨어/브랜딩 명칭 결정 메모로만 남김.
- **HTTP 50-왕복 배칭 = 전제 틀림.** 컨트롤 포트값은 포트마다 요청이 아니라 단일 `dump_graph`로 일괄수신(`model.py:356~400`), 플러그인 정보는 URI 메모이즈됨. 실제 남은 배칭 대상은 동일 인스턴스 `patch_get` 중복뿐(대부분 보드에서 미미) — 필요 시 인스턴스당 1회로 묶는 소규모.

## 참조

- [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md) — **완료 항목 아카이브(커밋·근거).**
- [`qt-migration-FINISHED.md`](qt-migration-FINISHED.md) — 이주 스택 아카이브(결정·검증).
- [`config-todo.md`](config-todo.md) — 하드코딩→사용자설정 위시리스트.
- [`pi-stomp-comparison.md`](pi-stomp-comparison.md) — pi-stomp 비교 연구(디바운스 이동·웹소켓 학습).
- [`eyecandy_idea.md`](eyecandy_idea.md) — 오디오 반응 캐릭터 애니 설계.
- [`ui-design-rules.md`](ui-design-rules.md) — 7" 800×480 2-tier 가시성 룰.
- [`../deploy/volume-service/README.md`](../deploy/volume-service/README.md) — 소프트 마스터볼륨 서비스.
- **시안**: claude.ai/design `9b9310ef…` — `Pedal Prototype.dc.html`(800×600) / `Pedal UI 비교.dc.html`.
- [`../README.md`](../README.md) · [`../REFERENCES.md`](../REFERENCES.md) — 앱 개요 · 라이브 레퍼런스.
