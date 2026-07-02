# Qt 앱 로드맵 — 남은 일

> 🛠 **살아있는 로드맵 (남은 일만).** 완료 항목은 [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md)로 이관,
> 맥락 필요 시 포인터로 참조. 마일스톤 최심층 상세 = 메모리 `synapse-roadmap`. 이주 스택 결정·검증 =
> [`qt-migration-FINISHED.md`](qt-migration-FINISHED.md).
> 마지막 갱신: **2026-07-03 (데드코드 재수색 + 스테일 문서 스윕 후 우선순위 축으로 재배열.)**
>
> **정렬 원칙 — 우선순위 축:** ① 안정성(크래시/데이터손상/무대 리스크) → ② 기능(미구현 본체) →
> ③ 설계상 미덕(상태를 올바로 드러냄) → ④ 아키텍처 우아함(관심사 분리·유지보수성) → ⑤ 미관.
> 같은 축 안에서는 대체로 규모 작은 것 먼저. 작업은 한 번에 하나씩, 변경 전 사용자 승인.

**현재 사실관계:** PyQt6+QML 앱이 Pi에서 라이브 동작, autostart 전환됨(`dfd42c6`).
페달보드 에디터 트랙(M1~M7)·라이브 플러그인 카탈로그·뱅크 매니저·튜너·소프트 마스터볼륨까지 완료·master 머지됨.
"못 뜨는" 하드 블로커 없음. 남은 큰 건은 **볼륨페달 Phase 2**(게인 인프라 완료, ADS 통합만)뿐이고
나머지는 작은 기능·정리·보류(부팅) 위주.

---

## ① 안정성 (라이브 신뢰성 — 최우선)

- [ ] **탭템포 실검증 (Pi 실물)** — 코드 경로는 완비(`TapTempoEngine`→`_tap_on_bpm`→`backend.set_bpm`,
      `taptempo.beat_plan` LED 체이스). **실동작 미검증**: 탭→BPM 반영 + LED 메트로놈 동기가 무대에서 맞는지
      육안 확인 필요. 라이브 연주 기능이라 미관 검증보다 앞.

> 참고: **인스펙터 ACTIVE/BYPASSED 칩 no-op 버그는 수정 완료**(2026-07-03) → [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md).
> 볼륨페달 **언플러그 페일세이프**(CC7 램프·홀드)는 안정성 성격이지만 볼륨페달 Phase 2(②)에 묶여 있어 그쪽에 기재.

## ② 기능 (미구현 / 부분구현 본체)

- [ ] **이펙터 프리셋 적용 (LV2 preset)** — M7이 프리셋 `{uri,label}`을 공급하고 카탈로그·이름 노출까지 완료.
      남은 건 `/effect/preset/load` 래퍼 + presenter/에디터 배선뿐. **지금은 프리셋 이름이 보이는데 탭해도 안 먹음**(UX 갭). (소)
- [ ] **스냅샷 브라우저 — 오버뷰 모달** — 이름 점프는 **에디터에 이미 구현됨**(`editor.selectSnapshot`→
      `presenter.go_to_snapshot`, 백엔드 `get_snapshot_list`+`load_snapshot`). 남은 건 **오버뷰 화면 전용 스냅샷 모달**
      하나(오버뷰 보드매니저 패턴 재사용). (소, 부분구현)
- [ ] **박자표(bpb) 설정 기능** — `backend.set_bpb`는 3계층 다 구현됨(`backend.py:183`/`modepctrl.py:553`/`fakemodep.py:308`)
      이나 **라이브 호출자 0**(탭템포는 BPM만 배선). transport/헤더에 bpb 설정 UI·경로만 배선하면 됨. (소)
- [ ] **Bypass-all / 전역 풋스위치 액션** — presenter에 `bypass_all()` 없음(있는 건 per-instance `bypass_effect`,
      mode-1 `toggle_bypass`뿐). 전 이펙트 루프 돌리는 단순 액션 + 전용 풋스위치 슬롯. (소)
- [ ] **라이브러리 보드 순서 (연구 → 편집/정렬)** — 현재 오버뷰 보드 전환 모달·풋스위치 NAVIGATE가 호스트
      `pedalboard/list` 순서를 **그대로** 씀(정렬·편집 없음, default만 제외). 목표는 **내비게이션 순서를 사용자가
      직접 제어**하는 것. ①먼저 조사: 보드 순서가 어디에 어떻게 저장·인출되는가(호스트 파일순? `app_state.json`?
      뱅크 매니저 순서변경과의 관계?) ②그 위에 편집/정렬 UI. (소~중, **먼저 연구 필요**)
- [ ] **볼륨페달 Phase 2 (ADS1115→CC)** — 게인 스테이지 인프라는 완료(`deploy/volume-service/`, 소프트 마스터볼륨).
      남은 것: `volumepedal.py`(독립 프로세스) 앱 폴링 통합 + **부팅 페달 감지**(게인토글 프로브, ch0) +
      **config 사용여부 옵션** + **언플러그 시퀀스**(CC7→127 1초 램프·홀드→송신중단→홀드=풀 패스스루 페일세이프, ★안정성).
      코드개선(미적용): 단발→연속모드, EMA+히스테리시스 CC 지터제거. (128SPS는 이미 적용됨 — `1abab37`.)
      설계 = 메모리 `soft-master-volume-plan`. (대 — 남은 최대 덩어리)
- [ ] **모멘터리(홀드) 모드** — [`presenter.py`](../presenter.py) 폴링이 릴리스엣지 전용(`stable==[0,0,0,0]`일 때만
      발화) → press-ON/release-OFF 이벤트 경로 없음. ④ '디바운스·콤보 HW단 이동'과 함께 설계하면 자연히 열림. (중)
- [ ] **이펙터 프리셋 (블록 저장/불러오기)** — 사용자 블록 단위 파라미터셋 저장. 위 LV2 preset 적용과 **별개인 진짜 신규**
      (스냅샷=보드 전체, 이건 단일 블록 재사용). 저장소·모델·UI 전무. (중, 후순위)

## ③ 설계상 미덕 (상태를 올바로 드러냄)

- [ ] **LED 정상상태 색 + 블링크 후 복원 (한 쌍)** — HW가 red/blue/purple 지원([`fsledctrl.py`](../hardwares/fsledctrl.py))
      인데 지금은 누를 때 blink만·끝나면 OFF(이전색 기억 없음). ★두 항목은 강결합: **먼저 '정상상태 색' 개념**
      (할당/포커스/활성-바이패스 상태별 색 유지)을 도입해야 '블링크 후 그 색으로 복원'이 성립. 함께 설계할 것. (중)
- [ ] **이펙터 타입 구분 (model vs param)** — 앰프/NAM(모델 줄 크게) vs 컴프/게이트(노브만). 파생 소스(`patches`/
      카테고리)는 이미 모델에 있음 → 노드 dict에 플래그 하나 + QML 렌더 분기. (소)

## ④ 아키텍처 우아함 (관심사 분리 · 유지보수성)

- [ ] **디바운스·콤보 판정을 하드웨어 추상화 단으로 이동** (2026-07-01 pi-stomp 착안) — 디바운스+릴리스엣지 콤보
      검출이 Presenter 앱레이어에 섞임(`presenter.py:633~716`). pi-stomp처럼 이벤트 emit `Switch` 클래스로 내리고
      Presenter는 구독만. **릴리스엣지 콤보 UX는 의미 유지, 위치만 이동.** 현 로직은 정상 동작하므로 저위험·저보상 —
      서두를 이유 없음(리팩터 실수 시 입력 회귀 위험 신규 도입). → [`pi-stomp-comparison.md`](pi-stomp-comparison.md) §3(A). (중)
- [ ] **i18n / 테마 토큰화 (한 묶음 — 결정 2026-06-28)** — 다국어·테마 스왑이 요구사항이 아니면 무기한 미룸 가능(순수
      유지보수성). 기계적 스윕이라 멀티에이전트 적합.
      - **문자열 중앙화(i18n)**: 사용자 노출 리터럴 → `resources/strings/<lang>.json` + `tr("key")` 인다이렉션.
        (현재 `qsTr()`/`tr()` 0건, 리터럴이 QML에 직접 하드코딩.)
      - **테마 토큰화**: `qml/Theme.qml`(`pragma Singleton`)에 색/폰트 토큰 집약. ⚠️ **색이 QML뿐 아니라 파이썬
        (`editor_bridge`/`qtview`)에도 있음** → 진짜 단일 소스화하려면 파이썬 측 색도 함께 중앙화해야 완전.
      - **열린 결정**: 런타임 언어/테마 전환 UI를 config에 둘지, 빌드 고정할지(후순위). (중)

## ⑤ 미관

- [ ] **케이블 색 의미 (열린 설계 결정)** — 오버뷰는 단색 green(`qtview.py:802`). **에디터는 이미 자체 색체계 보유**
      (bypass=회색/활성입력=파랑/스테레오 등, `editor_bridge.py:668~`). 결정 시 오버뷰↔에디터 색의미 이원화 주의.
      시안의 CLEAN/DRIVE/FEEDBACK은 디자인 의미(mod는 source→target만). 규칙 정의 or 단색 유지.
- [ ] **노드 라벨 스네이크그리드 Pi 육안검증** — 실 이펙트명이 박스 내 머무는지·케이블 자연스러운지(코드 완성, 검증만).
- [ ] **플랫 다크 카드 Pi 육안검증** — 코드 좌표계는 이미 800×480 통일(`main.qml:9-10`, `showFullScreen`). 남은 건
      실기 480 화면에서 카드가 안 잘리는지 육안 확인만. (위 노드라벨 검증과 한 세션에서 같이)
- [ ] **아이캔디 — 오디오 반응형 캐릭터 애니** — 설계 확정, 엔진 미착수. 튜너 오디오버퍼 재사용.
      폴리싱·기능 다 끝난 뒤. → [`eyecandy_idea.md`](eyecandy_idea.md). (대)

## ⏸ 보류 — 무컴포지터 eglfs 부팅 (원격 개발 중 컴포지터 유지)

> ⏸ 우선순위 내림(2026-06-25). labwc 창모드가 remote desktop 접속에 유리. 스택 검증 끝(FINISHED §4) —
> 배선만 남음. 기기 확정/무대 단계에서 재개. 개발 중엔 안정성 무관(오히려 창모드가 접속에 유리).

- [ ] **eglfs 풀스크린 부팅 전환** — 현재 labwc 위 창모드 잠정(`~/run_synapsepy.sh`, `dfd42c6`) → lightdm/labwc
      제거 후 eglfs 직행. 롤백본 `run_synapsepy.sh.kivy-bak`(+ **git 히스토리에서 `app.py` 복원 선행 필요** —
      백업 스크립트는 `python app.py`를 부르는데 app.py는 워킹트리에서 삭제됨, README §Entry points 참조).
- [ ] **eglfs 런처 견고화** — DSI 2개 connected 자동선택 모호 → `run_qt.sh`+`eglfs_kms.json`로 card/커넥터/모드 고정
      + `HIDECURSOR=1` + `QT_QUICK_BACKEND=software`. (부팅전환의 하위작업)
- [ ] **종료 어포던스 (nice-to-have)** — 깨끗한 종료는 `Ctrl+Q`→`Qt.quit()`([`main.qml:30`])와 **⚙MENU→SYSTEM
      안전종료가 이미 존재**(키보드 없는 기기도 종료 가능). 남은 건 Esc 키/터치 전용 어포던스뿐 — 편의성.

## 폐기 / 재배치 (의도 확정됨)

- **ABCD 버튼** → 시안엔 없음. "포커스 이펙터를 FS에 수동 바인딩"은 오버뷰-인스펙터 이펙터 배정이 대체(재구현 예정). 잔재 삭제 완료(2026-07-03). [[abcd-button-intent]].
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
