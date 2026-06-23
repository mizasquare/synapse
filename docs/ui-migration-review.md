# 새 UI 이주 검토 (2026-06-24)

> 상태: **검토만 완료. 코드 변경 없음.** Claude Design 시안
> (`Pedal Prototype.dc.html`, 프로젝트 "Kivy UI 재구성 방향")을 현재 비트맵 UI 코드와
> 대조해, 이주 시 **추가로 구현해야 할 기능/뷰**를 정리한다.

## TL;DR

- 가장 무거워 보이는 **그래프 뷰(Overview/Focus 라우팅)는 데이터가 이미 다 들어온다** —
  `Pedalboard.connections`(포트단위 source→target) + `Effect.x/y`를 mod `pedalboard/info`에서
  이미 받아오고 있고(`modepctrl.py`), 현재 UI가 안 쓰고 flat 리스트로 뭉갰을 뿐이다.
- 진짜 **신규 백엔드는 사실상 #8 이펙터 프리셋 하나**, **깨진 것 복구가 #10 FS 할당/리콜**.
- 큰 덩어리(#13 뷰 라우터, #14 플랫카드)는 코딩이라기보다 **구조 단순화 = LEAN화 그 자체**라
  이주 방향과 정확히 맞물린다(비트맵 자산 `resources/*.png` 의존이 사라짐).

---

## 1. 시안이 요구하는 화면/뷰

시안은 **상태 기반 화면 전환** 구조. 현재는 `UI-design_3.png` 위에 모든 영역이 항상
떠 있는 **단일 합성화면** — 이게 가장 큰 구조 차이다.

| 새 뷰 | 역할 | 현재 대응물 |
|---|---|---|
| **Overview** | 노드 그래프 미니맵(IN→FX→OUT, 케이블) | ❌ flat 리스트(`PedalboardDisplay`)뿐 |
| **Focus** | 한 블록: 라우팅(텍스트 IN/OUT)+노브+ON/OFF+prev/next | △ `PortCtrlArea`(파라미터만, 라우팅·네비 없음) |
| **Tuner** | 풀스크린 스트로브+현 표시 | △ `tunerpopup.py` 존재하나 **뷰에 안 물림(고아)** |
| **Menu(☰)** | 3층위 저장/불러오기 | △ 스냅샷 save/saveas만 |
| **Keyboard** | 인앱 QWERTY(이름 입력) | △ 외부 `wvkbd` + `SaveAsPopup` |
| **Browser** | 이름으로 불러오기 리스트 | ❌ prev/next만 |
| **Toast** | 일시 알림 | ❌ |
| **HW 풋스위치 행** | 스위치4 + 콤보브리지3 + LED링 | △ 라벨 4개(`FooterArea`)만 |

---

## 2. Gap 분석 (난이도/의존성 순)

### 🟢 Tier 1 — 데이터는 이미 있고 "뷰/상호작용"만 새로 (LEAN 친화, 먼저)

| # | 기능 | 근거 (이미 있는 것) |
|---|---|---|
| 1 | **노드 그래프 Overview** | `Pedalboard.connections`(포트단위) + `Effect.x/y`를 `pedalboard/info`에서 **이미 받음**. `_order_instances()`가 인접그래프까지 만듦 → 안 쓰던 데이터를 그리기만. |
| 2 | **Focus 텍스트 라우팅(IN/OUT)** | 포커스 instance로 `connections` 필터하면 도출. prev/next는 정렬된 `effects` 순회. |
| 3 | **Snapshot 불러오기 브라우저** | `get_snapshot_list()`+`load_snapshot(idx)` 존재 → 리스트 UI만. |
| 4 | **Board 불러오기 브라우저** | `get_pedalboards_in_bank()`+`set_pedalboard()` 존재 → 리스트 UI만. |
| 5 | **Tap Tempo** | `set_bpm()` 존재. 탭 간격 평균 = 앱 로직(시안에 `tapTimes` 스케치됨). |
| 6 | **Tuner 배선** | YIN 피치검출+JACK 캡처 로직 `tunerpopup.py`에 완비 → 풀스크린 재스킨+콤보 진입/탈출만. |
| 7 | **LED 정상상태 색** | HW가 red/blue/purple 지원(`fsledctrl.LED`=red_pin+blue_pin). 지금은 누를 때 `blink`만 → 할당/포커스 상태에 따라 **색을 켜둔 채 유지**로. |

> ⚠️ **데이터 공백 1개**: 케이블 색 `CLEAN/DRIVE/FEEDBACK`은 **디자인이 만든 의미**지 mod엔 없음
> (source→target만 제공). 피드백 루프는 사이클 탐지로 자동 검출 가능하나, clean/drive 구분은
> mod가 안 줌 → **규칙을 정하거나(예: 카테고리 기반) 색을 단순화**해야 함.

### 🟡 Tier 2 — 새 백엔드/모델 작업 필요

| # | 기능 | 필요한 일 |
|---|---|---|
| 8 | **이펙터 프리셋(블록 단위 모델+설정 저장/불러오기)** | **진짜 신규.** 패치파일(NAM/IR *파일*) 로딩과 다른 개념. mod-ui LV2 plugin preset 엔드포인트 지원 여부 **확인 필요** — 없으면 "현재 포트값 묶음"을 앱 JSON으로 자체 구현. |
| 9 | **Board 다른이름 저장** | `save_current_pedalboard()`가 `asNew:0`만 → `asNew:1`+title 확장 + 이름입력 연결. |
| 10 | **FS 할당 모델 + 영속화 + 설정화면(비교문서 Frame F)** | 현재 `assign_footswitches()` 하드코딩 + 모드2 리콜 **깨짐**(`self.fs_assignment_data` 미정의, `presenter.py:206`). 할당 구조 + 저장/로드(`utils.save/load_footswitch_assignments` 참조만 있고 본체 없음) + 전역기능(BYPASS ALL, MODE, BOARD◄►, SNAPSHOT◄►, TAP, TUNER). |
| 11 | **FS 콤보(A+B/B+C/C+D)** | `handle_multiple_footswitches()` 전부 `pass`. **단, 폴링 루프가 콤보를 이미 래치/캡처**(release-edge)하므로 인프라는 완성 — 액션 배선만. |
| 12 | **Momentary(순간) 모드** | 현재 release-edge에서만 발화(토글·콤보용). 모멘터리는 press-edge ON+release OFF → 폴링 루프 보강. |

### 🔴 Tier 3 — 구조 전환 (LEAN화의 본체)

| # | 기능 | 내용 |
|---|---|---|
| 13 | **뷰 라우터 / 화면 상태머신** | 단일 합성화면 → `overview/focus/tuner`+모달(menu/keyboard/browser/toast) 전환. `SynapseGUI` 구조 핵심 재편. |
| 14 | **플랫 다크 카드(스큐어모픽 제거)** | `resources/*.png` 비트맵 배경/위젯이미지 제거 → 평면 카드. **자산 의존이 사라져 코드가 가벼워짐(LEAN 이득).** 800×600 네이티브(현재 4× 스케일 좌표계 폐기). |
| 15 | **노브 vs 슬라이더** | 시안=로터리 노브(conic 링, 세로 드래그). 현재=`MySlider`(가로). 기능 아닌 표현 선택 — 결정 필요. |
| 16 | **이펙터 타입 구분(model vs param)** | 앰프/NAM(모델 줄 크게) vs 컴프/게이트(노브만). `patches` 유무/카테고리로 도출 — 모델에 작은 플래그. |
| 17 | **인앱 키보드 vs wvkbd** | 시안=자체 QWERTY. 현재=외부 `wvkbd`. 빌드 vs 재사용 결정. |

---

## 3. 바뀌거나 사라지는 것 (의도 확인 필요)

- **ABCD 버튼** → 시안엔 없음. 기획했던 "포커스 이펙터를 FS에 수동 바인딩"은
  **Frame F 풋스위치 설정화면이 대체**(더 확장된 형태). 베젤 ABCD 컨셉은 폐기 방향.
- **WebUI 버튼(Chromium)** → 시안 프로토타입에 **없음**. 완전 폐기인지, ☰ 한 켠에 남길지 **결정 필요**.
- **베젤 합성영역**(save/saveas/pb/ss/mode/bpm) → 해체 재배치: 저장/로드→☰, PB/SS 이동→콤보,
  모드→FS 설정, BPM→Tap+헤더.
- **패치파일 파일선택기(IR/NAM)** → "이펙터 프리셋/모델 불러오기" 브라우저로 흡수되는 그림.

---

## 4. 결정 필요 3건

1. **이펙터 프리셋(#8)**: mod-ui가 LV2 plugin preset save/load를 주는가? 아니면 앱 JSON 자체구현?
2. **WebUI**: 새 UI에서 완전 폐기 vs ☰ 메뉴 잔존?
3. **컨트롤**: 로터리 노브 신규 vs 기존 가로 슬라이더 유지?

## 5. 참조

- 시안: claude.ai/design 프로젝트 `9b9310ef-…` ("Kivy UI 재구성 방향"),
  파일 `Pedal Prototype.dc.html`(800×600 인터랙티브) / `Pedal UI 비교.dc.html`(00 현재 + A·B·C·C2·D·E·E2·F 개선안).
- 관련 메모리: `abcd-button-intent`, `synapse-roadmap`.
