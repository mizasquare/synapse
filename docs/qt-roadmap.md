# Qt 앱 로드맵 — 남은 일

> 🛠 **살아있는 로드맵 (남은 일만).** 완료 항목은 [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md)로 이관,
> 맥락 필요 시 포인터로 참조. 마일스톤 최심층 상세 = 메모리 `synapse-roadmap`. 이주 스택 결정·검증 =
> [`qt-migration-FINISHED.md`](qt-migration-FINISHED.md).
> 마지막 갱신: **2026-07-02 (HEAD 재감사 — 6-28 이후 머지분 반영: 페달보드 에디터 M1~M7·오버뷰 보드매니저·
> default 제외·STOMP 캡션·소프트 마스터볼륨 전부 완료·머지됨. stale "미완" 표기 정정.)**

**현재 사실관계:** PyQt6+QML+eglfs 앱이 Pi에서 라이브 동작, autostart 전환됨(`dfd42c6`).
**페달보드 에디터 트랙(M1~M7)·라이브 플러그인 카탈로그·뱅크 매니저·튜너·소프트 마스터볼륨까지 완료·master 머지됨.**
"못 뜨는" 하드 블로커 없음. 남은 건 **개별 기능 신규 + 정리/폴리시 + 보류(부팅)** 위주.

★**다음 최우선은 재산정 대상** — 가장 무거운 덩어리(에디터·카탈로그)가 끝나서, 남은 큰 건은
① **볼륨페달 Phase 2**(게인 인프라는 완료, ADS 통합만) ② **i18n/테마 토큰화**(기계적 스윕) 정도.
나머지는 작은 기능·정리. 작업은 한 번에 하나씩, 변경 전 사용자 승인.

---

## 에디터 후속 (소)

- [ ] **이펙터 프리셋 적용** — M7이 프리셋 `{uri,label}`을 공급하므로 `/effect/preset/load` 래퍼 추가해 실제 적용.
      (카탈로그·이름 노출은 M7로 완료 — 적용 엔드포인트 래퍼만 남음.)
- [ ] **라이브러리 전체 보드 순서 정렬** — 뱅크 매니저는 완료됐으나 전체 보드 목록 정렬은 미구현.

## Tier 2 — 기능 (미구현 본체)

- [ ] **볼륨페달 Phase 2 (ADS1115→CC)** — 게인 스테이지 인프라는 완료(`deploy/volume-service/`, 소프트 마스터볼륨).
      남은 것: `volumepedal.py`(독립 프로세스) 앱 폴링 통합 + **부팅 페달 감지**(게인토글 프로브, ch0) +
      **config 사용여부 옵션** + **언플러그 시퀀스**(CC7→127 1초 램프·홀드→송신중단→홀드=풀 패스스루 페일세이프).
      코드개선(미적용): 단발→연속모드, 860→64~128SPS, EMA+히스테리시스 CC 지터제거. 설계 = 메모리 `soft-master-volume-plan`.
- [ ] **박자표(bpb) 설정 기능** — 탭템포는 BPM만 실배선(`_tap_on_bpm`→`backend.set_bpm`). **박자표 변경 UI·경로 미구현.**
      `backend.set_bpb`는 존재하나 라이브 호출자 없음(유일 호출처였던 미배선 래퍼 `set_beat`은 2026-07-03 삭제). transport/헤더에서 bpb 설정 배선 필요.
- [ ] **모멘터리(홀드) 모드** — [`presenter.py`](../presenter.py) 폴링이 릴리스엣지 전용 → press-ON/release-OFF 없음.
- [ ] **Bypass-all / 전역 풋스위치 액션** — presenter에 `bypass_all()` 없음.
- [ ] **이펙터 프리셋 (블록 저장/불러오기)** — 블록 단위 설정 저장. 위 "프리셋 적용"(LV2 preset)과 별개인 **진짜 신규**.
- [ ] **이펙터 타입 구분(model vs param)** — 앰프/NAM(모델 줄 크게) vs 컴프/게이트(노브만). `patches` 유무/카테고리로 도출 — 모델에 작은 플래그.
- [ ] **스냅샷 브라우저 — 오버뷰 모달만 남음** — 이름으로 목록 점프 기능 자체는 **에디터에 구현됨**(`editor.selectSnapshot`→`presenter.go_to_snapshot`, 백엔드 `get_snapshot_list`+`load_snapshot`). 백엔드·presenter·에디터 UI 완료 → 남은 건 **오버뷰 화면 전용 스냅샷 모달**(오버뷰 보드매니저에 대응하는 스냅샷판) 하나뿐.
- [ ] **LED 정상상태 색** — HW가 red/blue/purple 지원([`fsledctrl.py`](../hardwares/fsledctrl.py))인데 지금은 누를 때 blink만 → 할당/포커스 상태에 따라 색을 켜둔 채 유지.

## i18n / 테마 토큰화 (한 묶음 — 결정 2026-06-28)

> 난이도 = 흩어진 리터럴/하드코딩 값을 전부 찾아 중앙화(기계적 스윕, 멀티에이전트 적합).

- [ ] **문자열 중앙화(i18n)** — 사용자 노출 리터럴 → `resources/strings/<lang>.json` + `tr("key")` 인다이렉션.
- [ ] **테마 토큰화** — `qml/Theme.qml`(`pragma Singleton`)에 색상/폰트 토큰 집약, 전 QML 참조 → 테마 스왑.
      [`ui-design-rules.md`](ui-design-rules.md)와 정합.
- **열린 결정**: 런타임 언어/테마 전환 UI를 config에 둘지, 빌드 고정할지(후순위).

## 부팅 — 무컴포지터 eglfs — ⏸ 보류 (원격 개발 중 컴포지터 유지)

> ⏸ 우선순위 내림(2026-06-25). labwc 창모드가 remote desktop 접속에 유리. 스택 검증 끝(FINISHED §4) —
> 배선만 남음. 기기 확정/무대 단계에서 재개.

- [ ] **eglfs 풀스크린 부팅 전환** — 현재 labwc 위 창모드 잠정(`~/run_synapsepy.sh`, `dfd42c6`) → lightdm/labwc 제거 후 eglfs 직행. 롤백본 `run_synapsepy.sh.kivy-bak`.
- [ ] **eglfs 런처 견고화** — DSI 2개 connected 자동선택 모호 → `run_qt.sh`+`eglfs_kms.json`로 card/커넥터/모드 고정 + `HIDECURSOR=1` + `QT_QUICK_BACKEND=software`.
- [ ] **종료 어포던스** — 깨끗한 종료는 `Ctrl+Q`→`Qt.quit()`로 이미 있음([`main.qml:30`](../qml/main.qml)). 남은 건 Esc 키/터치 종료 어포던스 추가.

## Tier 3 — 정리 / 폴리시

- [x] **데드코드 스윕 (WebUI·wvkbd·ABCD·pb_ss·고아메소드 등 ~405줄)** — 완료 2026-07-03, → [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md) "데드코드 스윕". (`boot_lightshow`는 라이브라 존치 — 옛 "죽은 스텁" 표기는 오탐이었음.)
- [ ] **디바운스·콤보 판정을 하드웨어 추상화 단으로 이동** (2026-07-01 pi-stomp 착안) — 디바운스+릴리스엣지 콤보 검출이 앱 레이어에 섞임. pi-stomp처럼 이벤트 emit `Switch` 클래스로 내리고 Presenter는 구독만. **릴리스엣지 콤보 UX는 의미 유지, 위치만 이동.** → [`pi-stomp-comparison.md`](pi-stomp-comparison.md) §3(A).
- [ ] **`[undefined]→bool` 경고** — [`main.qml`](../qml/main.qml) FOCUS 패치 visible 바인딩, 무해. `!!(...)`로 정리.
- [ ] **LED 블링크 후 정상색 미복원** — [`fsledctrl.py`](../hardwares/fsledctrl.py) blink 끝나면 OFF, 이전색 기억 없음(위 'LED 정상상태 색'과 연동).
- [ ] **HTTP 50-왕복 초기화 배칭/캐시** — `initialize_modep_pedalboard`가 포트마다 1요청 → 느린망 로드지연. 배칭/캐시 검토.
- [ ] **플랫 다크 카드 / 좌표계** — 시안 800×600 vs 실제 800×480 좌표 일관성 점검.

## 라이브 검증 백로그 (Pi 실물)

- [ ] **탭템포 실검증** — 탭→BPM 반영 + LED 메트로놈 + `set_bpm` 동기.
- [ ] **노드 라벨 스네이크그리드 Pi 육안검증** — 실 이펙트명이 박스 내 머무는지·케이블 자연스러운지.

## 열린 설계 결정

- **케이블 색 의미** — 시안의 CLEAN/DRIVE/FEEDBACK은 디자인이 만든 의미, mod는 source→target만. 현재 단색(green). 규칙 정의(카테고리/피드백=사이클탐지) or 단색 유지.

## 폐기 / 재배치 (의도 확정됨)

- **ABCD 버튼** → 시안엔 없음. "포커스 이펙터를 FS에 수동 바인딩"은 오버뷰-인스펙터 이펙터 배정이 대체(재구현 예정). 잔재 삭제 완료(2026-07-03). [[abcd-button-intent]].
- **WebUI(Chromium)** → 온디바이스 폐기(웹UI는 폰/옆 데스크톱 접속). 온디바이스 코드 삭제 완료(2026-07-03).
- **베젤 합성영역**(save/saveas/pb/ss/mode/bpm) → 해체: 저장/로드→⚙MENU 허브(완료), PB/SS→콤보, 모드→FS 설정, BPM→Tap+헤더.
- **온스크린 키보드(wvkbd/커스텀)** → 폐기(2026-06-28). 이름추천기+HW 키보드 폴백. 잔재(`toggle_keyboard`/`toggle_wvkbd`) 삭제 완료(2026-07-03).

## 미래 기능

- [ ] **아이캔디 — 오디오 반응형 캐릭터 애니** — 설계 확정, 엔진 미착수. 튜너 오디오버퍼 재사용. → [`eyecandy_idea.md`](eyecandy_idea.md).
- [ ] **네이밍 리팩터** — Synapse(앱) vs GCaMP6s(박스) 수렴.

---

## 감사 정정 노트 (재추가 금지 — 오탐이었음)

코드 감사에서 블로커로 잘못 잡혔으나 **실제 검증 결과 정상**인 항목. stale 문서가 원인이니 다시 손대지 말 것:

- **STOMP 클로저 버그 = 오탐.** `presenter.py`의 `e0~e3`는 루프변수 아닌 서로 다른 변수 4개 → 올바른 캡처. (캡션 정합은 `5449552`로 별개 완료.)
- **RECALL 실행 = 정상.** 키 통일, `load_snapshot` 사용.
- **`set_snapshot`(실 백엔드) 불필요.** `load_snapshot`으로 처리(죽은 스텁은 `16fbb2c`로 제거됨).
- **WebUI minimize/restore = 블로커 아님.** Qt 경로 미호출 죽은 코드 → 삭제 완료(2026-07-03).

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
