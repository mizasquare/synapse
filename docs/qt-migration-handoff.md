# Qt 이주 1차 — 핸드오프 (branch: `qt-migration`)

> 이 문서는 **새 Claude Code 세션(실행자)** 이 맥락 0에서 이 작업을 이어받기 위한 것이다.
> 한 줄 요약: **Windows에서 돌아가는 PySide6+QML 모의 UI를 만든다. 백엔드(modepctrl)·하드웨어를
> 가짜로 주입해 Pi 없이 개발하고, 1차로 현재 기능의 모던 재현 + 읽기전용 라우팅 뷰어까지 간다.**

---

## 0. 먼저 읽을 것 (순서대로)

1. `README.md` — 앱 개요, 아키텍처, 하드웨어.
2. `REFERENCES.md` — 라이브 시스템/외부 의존(이 작업에선 배경지식).
3. `presenter.py`, `view.py`, `modepctrl.py` — **이 셋이 이주의 핵심.** 특히 `modepctrl.py`는
   메서드 표면(인터페이스)을 직접 세려면 통째로 읽어야 한다.
4. 같은 머신이면 프로젝트 메모리(`MEMORY.md`)에 `ui-migration-direction`, `wip-decouple-kivy-branch`,
   `naming-synapse-vs-gcamp6s` 항목이 있다. 핵심은 이 문서에 다 옮겨놨으니 없어도 무방.

## 1. 결정 배경 (왜 이 길인가)

- **GUI 대이주 목표**: 데스크톱 컴포지터(labwc/wayfire) 제거 → CLI에서 GUI 직행, 픽셀아트 폐기 →
  모던·벡터·풀해상도, MODEP 웹UI(chromium) **온디바이스 제거**(웹UI는 폰/옆 데스크톱에서 접속).
- **크로미움을 지금 떼도 됨** → 화면에 앱 하나뿐 → **베어 KMS 단일앱**이 가능. (단 이건 Pi 배포 단계 얘기.
  1차 개발은 Windows에서 한다.)
- **툴킷 = Qt Quick(QML) + PySide6, 배포 시 `eglfs`로 KMS 직행.** 이유: 선언형 벡터 UI, 드래그/스크롤
  제스처를 코드로 직접 제어(포트 라우팅 드래그 문제 해결), 노드 캔버스 강함, **PySide6가 CPython
  네이티브**라 기존 엔진(`modepctrl`·`mido`·I²C·threading) 그대로 재활용.
- **PySide6** = Qt 공식 파이썬 바인딩(LGPL). PyQt(GPL) 아님.
- **가짜 백엔드 전략(핵심)**: mod-host/mod-ui 프로토콜(HTTP/소켓)을 **흉내내지 않는다**(과함).
  대신 `modepctrl`이라는 **객체 seam에서** 가짜를 주입한다 → `FakeModepController`가 픽스처를 반환.

## 2. 현재 아키텍처 사실 (실행 전 반드시 인지)

- 구조는 **MVP**: `view`(Kivy SynapseGUI) ↔ `presenter`(로직/상태) ↔ `modepctrl`(HTTP 클라이언트) + 모델.
- **이 브랜치 계보(`decouple-kivy`)에서 스케줄러는 이미 주입형**이다: `scheduler.py`(`Scheduler`/
  `KivyScheduler`), `Presenter(view, scheduler)`, `fsledctrl.Controller(scheduler)`. → **seam 주입 패턴의
  선례가 이미 코드에 있다. 백엔드·하드웨어도 똑같이 하면 된다.**
- **`modepctrl.ModepController`는 `@staticmethod` 묶음 + 클래스 속성**(`session = requests.Session()`,
  `SERVER_URI`, `TESTMODE`)이다. presenter가 `ModepController.foo(...)`처럼 **클래스/스태틱으로 직접
  호출**한다. → 가짜로 갈아끼우려면 **주입 가능한 인스턴스/인터페이스로 전환**해야 한다.
- **모델 객체도 백엔드를 친다(중요 wrinkle)**: presenter는 `effect.ports[sym].set_value(...)`,
  `effect.patches[uri].set_patch(...)`, `port.get_value()`, `patch.get_patch()`를 호출하는데, 이 모델
  메서드들이 내부에서 `ModepController`로 HTTP를 쏜다. → 단순히 `ModepController`만 가짜로 바꿔선
  부족할 수 있다. (해법은 Step A 참고. 1차는 "쓰기=로컬상태 변경/no-op"로 단순화 가능.)
- `modepctrl.initialize_modep_pedalboard()`(모듈 함수)가 HTTP로 `Pedalboard` 모델을 빌드한다.
  presenter가 이걸로 초기 상태를 만든다. → 가짜도 **같은 모델 클래스를** 픽스처로 채워 반환해야 한다.

### presenter가 의존하는 백엔드 표면 (modepctrl.py에서 정확히 재확인할 것)
대략: `set_bpb` `set_bpm` `set_prev_pedalboard` `set_next_pedalboard` `load_snapshot`
`snapshot_current_idx` `set_pedalboard` `set_snapshot` `bypass_effect` `parameter_get`
`snapshot_save` `snapshot_save_as` + 모듈함수 `initialize_modep_pedalboard` + 모델 메서드
`Port.set_value/get_value`, `Patch.set_patch/get_patch`. **실행자는 `modepctrl.py`를 읽어 이 목록을
확정**하고 그걸 그대로 Backend 인터페이스로 삼아라.

## 3. 1차 스코프 / 비목표

**1차에 포함**
- PySide6+QML 앱이 **Windows에서** 픽스처로 기동.
- 현재 UI 기능의 모던 재현(읽기 중심): 페달보드 제목/이펙터 리스트/스냅샷 표시, 이펙터 선택 →
  파라미터 영역, BPM 표시. 파라미터/바이패스 조작은 **로컬 상태 반영**(가짜 백엔드가 받아 인메모리 갱신).
- **페달보드 에디터 모드 진입 시 읽기전용 라우팅 뷰어**(노드=플러그인, 엣지=포트연결)를 그래프 데이터로 렌더.

**1차 비목표(나중)**
- 완전한 라우팅 *에디터*(드래그로 연결/생성/삭제) — 뷰어까지만.
- 실제 하드웨어(풋스위치/LED/페달, I²C), `eglfs`/KMS 베어메탈 부팅, 실제 터치 — 전부 Pi 단계.
- 실제 mod-host 연동 검증 — Pi에서.
- 픽셀 비트맵 에셋 이식 — 버린다. 새 벡터/QML 스타일로.

## 4. 작업 분해 (단계별)

**Step A — 백엔드 seam 주입**
- `modepctrl.py`를 읽어 presenter가 쓰는 메서드 목록 = **Backend 인터페이스**로 추출.
- `RealModepController`(현 HTTP 로직 래핑) / `FakeModepController`(픽스처 반환) 두 구현.
- presenter를 `Presenter(view, scheduler, backend)`로 바꿔 `ModepController.foo()` → `self.backend.foo()`.
- 모델 wrinkle 처리: 가장 단순한 1차안 = 모델의 쓰기 메서드(`Port.set_value` 등)도 주입 backend를
  타게 하거나, `FakeModepController`에서 그 경로를 no-op/로컬변경으로 흡수. (실제 mod-host 동작 검증은
  1차 목표 아님 — "UI가 반응하는 것"까지면 충분.)

**Step B — 하드웨어 seam 주입**
- `fsledctrl.Controller`는 이미 `scheduler`를 받는다. **추상화/가짜**를 추가: presenter가 받는
  `hwi`를 인터페이스화해서 `FakeController`(LED no-op, 풋스위치 비활성 또는 합성 이벤트) 주입.
- Windows에선 I²C가 없으니 `FakeController`가 기본. (`fsledctrl` 실물은 Pi 전용.)

**Step C — 픽스처**
- 가능하면 **Pi에서 실응답 캡처**: `pedalboard/list`, 스냅샷, 이펙터 파라미터 JSON을 curl로 떠서
  `fixtures/*.json`에 저장 → `FakeModepController`가 반환. (Pi 접근 전이면 손으로 최소 1개 페달보드 +
  2~3개 이펙터 + 2개 스냅샷 픽스처를 만들어 시작.)

**Step D — PySide6+QML 스켈레톤 (Windows)**
- `pip install PySide6`. 새 진입점(예: `qt_app.py`)에서 QML 루트 로드.
- `FakeModepController` + `FakeController` + (Qt용)`QtScheduler` 또는 임시 즉시실행 스케줄러를 주입해
  `Presenter` 생성. QML ↔ presenter 브리지(QObject/Slot/Signal 또는 context property).
- **주의**: presenter는 현재 Kivy view 메서드(`refresh_plugin_display`, `populate_port_area`,
  `update_parameter_display`, `update_bpm_display`, `update_mode_display`, `minimize/restore` 등)를
  호출한다. Qt view는 **같은 메서드 시그니처를 구현**하거나, presenter의 view 호출을 시그널로 바꾸는
  얇은 어댑터를 둔다. (presenter 로직 의미는 보존.)

**Step E — 읽기 경로 먼저**
- 픽스처 데이터로 페달보드/이펙터/스냅샷/파라미터가 QML에 뜨게. 선택·표시까지.

**Step F — 라우팅 뷰어**
- 그래프 구조(노드/연결)는 이미 데이터 자산 → QML Shapes/Canvas로 노드+엣지 읽기전용 렌더.
  에디터 모드 진입 시 표시.

## 5. Windows에서 되는 것 / Pi에서만 되는 것

| | Windows(이 작업) | Pi(나중) |
|---|---|---|
| QML/UX 반복, presenter 로직 | ✅ | ✅ |
| 가짜 백엔드/하드웨어로 구동 | ✅ | — |
| 실제 mod-host 라우팅, I²C HW, eglfs/KMS, 실터치 | ❌ | ✅ |

## 6. 환경 / 실행

- Windows: `python -m venv .venv && .venv\Scripts\activate && pip install PySide6`
- 실행: `python qt_app.py` (가짜 주입 → 픽스처로 기동).
- 기존 `app.py`(Kivy)는 **건드리지 말고 그대로 둔다** (Pi 현행 유지용). 새 진입점은 별도 파일.

## 7. 베이스 브랜치 주의 ⚠️

- `qt-migration`은 **미머지 브랜치 `decouple-kivy` 위에서** 분기됐다(스케줄러 주입 골격 상속).
- `decouple-kivy`는 **Pi 회귀 테스트 대기 중**(풋스위치/LED/웹UI). 테스트에서 수정이 나오면 이 브랜치도
  영향. 그 수정은 작을 것이므로 `git rebase`/cherry-pick으로 흡수. 최악의 경우에도 디커플링은 작은
  변경이라 재건 부담 적음(사용자 판단).
- `decouple-kivy`가 master에 머지되면, 가능하면 `qt-migration`을 갱신된 master 위로 rebase.

## 8. 1차 완료 정의 (DoD)

- [ ] Windows에서 `python qt_app.py`로 가짜 백엔드/하드웨어 주입 후 앱이 뜬다.
- [ ] 픽스처의 페달보드/이펙터/스냅샷/파라미터가 모던 QML로 표시된다.
- [ ] 이펙터 선택 → 파라미터 영역 갱신, 파라미터/바이패스 조작이 로컬로 반영된다.
- [ ] 에디터 모드 진입 → 읽기전용 라우팅 뷰어가 노드/엣지를 그린다.
- [ ] presenter/modepctrl/하드웨어의 **기존 로직 의미가 보존**된다(주입만 바뀜, 동작 의미 불변).
- [ ] `app.py`(Kivy) 및 Pi 현행 경로는 그대로 — 새 진입점은 별도.

## 9. 원칙

- **seam 주입만 추가, 로직 의미는 보존.** (스케줄러 때처럼 "이름/배선만 교체".)
- 와이어 프로토콜 흉내 금지 — 가짜는 항상 **객체 seam**에서.
- 커밋은 작게, 메시지에 "무엇을·왜". 새 위젯/엔트리는 기존 파일과 같은 결로.

## 10. 후속 작업 / 알려진 미완성

이번 세션에 추가됨(Stage 3 풋스위치 입력의 일부): **탭템포 모드**(C+D 콤보 진입, `taptempo.py`),
목업 전용 **키보드 풋스위치 입력**(Z/X/C/V→FS0–3, `fakehardware.set_switch`+QML Keys). 설정값 TODO는
`docs/config-todo.md`.

### RECALL 모드(풋스위치 mode 2) 되살리기

의도: 풋스위치 4개 = 리스트상 멀리 흩어진 **(페달보드+스냅샷) 조합 4개로 한 방에 점프**하는 라이브
셋리스트 모드. (NAVIGATE=순차 탐색, STOMP=이펙트 bypass 토글, **RECALL=북마크 직점프**.) 지금은 변수
배선이 어긋난 채 미완성이라 RECALL에서 풋스위치를 밟으면 죽는다. 되살리려면:

- [ ] **변수명 통일**: `recall_pb_ss`/`assign_pb_ss_to_footswitch`는 `self.fs_assignment_data`를
      읽고/쓰는데 `__init__`이 만드는 건 `self.fs_mode2_assigns`뿐 → 하나로 통일
      ([presenter.py:55](../presenter.py), [276](../presenter.py), [295](../presenter.py)).
- [ ] **키 이름 통일**: 초기화는 `"pedalboard_path"`로 저장, recall은 `assignment["pedalboard"]`로 읽음.
- [ ] **부팅 시 디스크 로드 복구**: `load_footswitch_assignments()` 호출이 주석처리됨
      ([presenter.py:51](../presenter.py)). 저장소 = `~/.modep/footswitch_assignments.json`
      (`utils.save/load_footswitch_assignments`).
- [ ] **배정 경로/ UI 추가**: 현재 `assign_pb_ss_to_footswitch`를 호출하는 곳이 없음(=북마크 등록 수단
      자체가 없음). print문도 미정의 `fs_idx`/`pedalboard_id` 참조(NameError).
- [ ] **`set_snapshot`**: 실제 `ModepController`엔 없고 `FakeModepController`만 stub — recall의 스냅샷
      경로가 의존하므로 실 백엔드에도 구현 필요.
