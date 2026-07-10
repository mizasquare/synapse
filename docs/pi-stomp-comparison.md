# pi-stomp 비교 연구 (2026-07-01 세션)

`C:\Users\-----\pi-stomp`(treefallsound의 성숙한 오픈소스 MOD 스톰박스)와 synapse를
축별로 비교하고, 무엇을 배워올지 분류한 기록. **참고문헌 성격** — 대부분 당장 작업 대상이
아니라 "그들이 먼저 밟은 돌"을 알아두는 용도.

두 프로젝트는 같은 목표(Pi에서 MOD/MODEP 호스트 제어 + 물리 풋스위치/LED 구동)를 다르게 풀었다.
한 줄 요약: **엔지니어링 성숙도(테스트/CI/배포/패키징)는 pi-stomp가, 코드 구조(추상화/DI/모듈성)는
synapse가 앞선다.**

---

## 1. 지금 단계에선 참고만 (프로젝트 성숙 단계가 달라서 채택 보류)

pi-stomp는 키트를 팔고 여러 사용자·릴리스 주기가 있는 프로젝트라 필요한 것들. synapse는 아직
1인 개발 단계라 오버엔지니어링.

- **스냅샷(비주얼 회귀) 테스트** — `tests/snapshots/`에 기능·HW버전별 PNG 베이스라인 다수 +
  `conftest.py`가 Pi 모듈 전부 목킹, PIL 폰트 렌더 크로스플랫폼 정규화. synapse는 스모크 2개뿐.
  (`qt_dev.py --shot`이 이미 스크린샷을 찍으니, 나중에 원하면 `pytest-snapshot`/`syrupy`에 물릴 수 있음.)
- **CI 워크플로** — `.github/workflows/test.yml`(uv → 시스템deps → pytest). synapse는 CI 없음.
- **uv 패키징** — `pyproject.toml` + `uv.lock`(재현 빌드), `[hardware]` 옵셔널 그룹, `tool.uv` 오버라이드.
  synapse는 `--system-site-packages` + 분리된 requirements. 스냅샷/CI가 먼저 정착돼야 의미.
- **다세대 하드웨어 지원** — config version 필드 + `HardwareFactory` + `Pistomp/Pistompcore/Pistomptre`
  서브클래스로 한 코드베이스가 v1/v2/v3 구동. synapse는 MCP23017@0x27 단일 HW 하드코딩. **여러 HW
  타깃이 로드맵에 없으면 불필요.** (단 Relay/트루바이패스 추상화는 그 계획이 생기면 소규모로 유용.)
- **CHANGELOG/GUIDE 문서 규율** — Keep-a-Changelog + 개발자 가이드. synapse는 README·docs가 이미 충실.

## 2. synapse가 이미 더 나은 점 (후퇴 금지)

- **Backend/Model/Presenter seam 분리** — pi-stomp는 1400줄 모놀리식 `Mod` 핸들러가 HTTP 직접 호출.
  synapse의 `Backend` 인터페이스 + 순수 dataclass 모델 + 주입식 `fakemodep`가 오프디바이스 개발을 압도.
- **프레임워크 독립 tap-tempo 엔진** — `taptempo.py`는 scheduler+콜백만 의존(단위 테스트 가능).
  pi-stomp는 TapTempo를 `Footswitch` 안에 박아 결합.
- **명시적 DI + 구조적(덕타이핑) 인터페이스** — pi-stomp의 ABC 강제 상속 + config 자동탐지보다 유연·명확.
- **Qt/QML** — pi-stomp 커스텀 `uilib`은 320×240 픽셀고정. synapse QML은 스케일·터치·반응형.

---

## 3. 아키텍처적으로 당기는 2가지 (→ 로드맵/미래 카드)

### (A) 디바운스·콤보 판정을 Presenter → 하드웨어 추상화 단으로 이동 ✅ 완료 (2026-07-11)

> **완료:** `hardwares/footswitches.FootswitchReader`(순수 상태기계, I2C·스레드 무관)로 이관.
> Presenter 폴링루프는 `raw 읽기 → reader.poll(raw) → 이벤트 마샬`만; 디바운스/래치 부기 전부 리더 소유.
> 릴리스엣지 콤보 의미는 2000개 랜덤 시퀀스 대조로 구 인라인 루프와 비트동일 검증. press/release 엣지도
> emit해 모멘터리(홀드) 경로 개통(소비처는 ② 잔여). 상세 [`qt-roadmap-DONE.md`](qt-roadmap-DONE.md). 아래는 착안 기록 보존.

**현 상태(약간 우아하지 않음):** 디바운스와 콤보(릴리스엣지) 판정이 앱 레이어에 섞여 있다.
- `presenter.py:660` `DEBOUNCE_SAMPLES = 3`
- `presenter.py:683` `_footswitch_poll_loop` — raw 샘플 카운팅으로 디바운스 + 콤보 캡처, `:708`에서
  **전원 릴리스 엣지**에 발화(단일 vs 콤보 모호성 제거).
- `presenter.py:712/732` `handle_footswitch_event` / `handle_multiple_footswitches`(콤보→액션 맵, A+B=`:738`).

**pi-stomp 방식(참고):** 디바운스·롱프레스 상태머신이 하드웨어 클래스 안에 산다 —
`pistomp/gpioswitch.py`(`GpioSwitch`, `bounce_time`, per-switch 롱프레스 임계), `pistomp/footswitch.py`
(`Footswitch`의 static `all_longpress_groups` + `check_longpress_events()` 타임스탬프-윈도우 콤보).

**하고 싶은 것:** 디바운스+엣지검출을 새 `Switch`류 클래스(예: `hardwares/`의 `fsledctrl.Footswitch`를
감싸 안정상태·press/release 이벤트를 emit)로 내리고, Presenter는 **이벤트만 구독**. 하드웨어 단위
테스트가 가능해지고 Presenter가 깨끗해짐.

**주의(후퇴 금지):** synapse의 **릴리스엣지 콤보 판정**은 단일/콤보를 명확히 가르는 좋은 UX라 유지.
pi-stomp의 타임스탬프-윈도우는 릴리스 타이밍에 더 관대하지만 그 트레이드오프는 별개 결정. 지금은
**"의미 유지, 위치만 이동"** 리팩터로 한정. 당장 작업 아님.

관련 로드맵 항목: 확장 콤보(`presenter.py:408`→`config-todo.md`), 모멘터리 모드(`presenter.py` 폴링).

### (B) 웹소켓 이주 — **미래 카드로 보유(당장 아님)**

오늘 학습의 핵심. 상세는 아래 §4. 결론만: synapse는 이미 역방향 푸시를 손수 구현했고,
웹소켓은 성능/기능이 아니라 **유지보수·신뢰성·거리** 문제가 아플 때 꺼낼 카드.

---

## 4. 웹소켓 vs synapse `notify_synapsin` — 학습 정리

### 오해 정정
"HTTP는 외부 변경을 못 감지한다"는 HTTP **단독**엔 맞지만 **synapse엔 틀림.** synapse는 이미
역방향 푸시 채널을 갖고 있다:
- **호스트 패치**(`mod-tweaks/webserver.py`): 상태변경 핸들러마다 `notify_synapsin(...)` 발화 —
  `EffectAdd/Remove`, `EffectConnect/Disconnect`, `EffectParameterSet`, `EffectPatchSet`,
  `PedalboardLoadBundle`, `SnapshotLoad/Remove/Name`, `BankLoad`.
- **전송**: `AF_UNIX, SOCK_DGRAM` 데이터그램 → `/tmp/synapsin.sock` (fire-and-forget).
- **수신**: `qt_main.py:_start_reverse_listener`가 bind → 백그라운드 스레드 `recvfrom` →
  `scheduler.schedule_once`로 GUI 스레드 마샬 → `presenter.py:206 handle_reverse_event`.

### 웹소켓이 뭔가 (전화 비유)
- **HTTP = 걸고 끊기.** 매 요청마다 내가 먼저 걸고 답 받고 끊는다. **서버는 절대 먼저 말 못 함.**
  안 물어본 변경은 알 방법이 없음 → 계속 되묻기 = 폴링.
- **웹소켓 = 한 번 걸고 안 끊기.** 선이 계속 열려 있어 **서버가 아무 때나 먼저 말할 수 있음.** 시작은
  평범한 HTTP인데 `Upgrade: websocket` 헤더로 지속 양방향 파이프가 됨. HTTP 대비 유일한 본질 추가:
  **"서버가 먼저 말한다 + 선이 지속된다."**

**핵심 통찰:** synapse는 "서버가 먼저 말해줘야 하는" 바로 그 필요를 **웹소켓 없이 손수 구현한 것**이
`notify_synapsin`이다. 웹소켓과 같은 아이디어의 커스텀 최소판.

### treefallsound의 진화 = 당신 질문의 답
pi-stomp의 `setup/mod-tweaks/*.diff`가 그의 경로를 드러낸다:
- **2020**: 호스트 패치로 커스텀 HTTP get/set 추가(`EffectParameterSetPiStomp`,
  `pi_stomp_param_get`/`session.pi_stomp_parameter_set`). ← **지금 synapse가 있는 자리.**
- **2024**: 그 위에 웹소켓 얹음(`feat/websocket-sync`, `feat/websocket-parameter-set`, PR #141/#149).
  이때는 mod-ui가 **브라우저용으로 원래 열어둔 `/websocket`(`ws://localhost:80/websocket`)을 소비** —
  패치 불필요. "Track MOD tempo via inbound transport WS message"(#168)처럼 **인바운드 이벤트 수신**이 동기.

즉 synapse는 뒤처진 게 아니라 그가 4년 전 밟은 돌을 밟는 중. (주의: pi-stomp도 호스트를 패치하지만
그 패치는 웹소켓용이 아니라 위 2020년 커스텀 HTTP + 잡다한 버그픽스다.)

### 실질적 차이 4가지 (= 웹소켓으로 갈 rationale)
| 축 | synapse `notify_synapsin` | pi-stomp `/websocket` |
|---|---|---|
| 발화 지점 관리 | mod-ui를 **직접 패치**, 업그레이드마다 리베이스 | mod-ui가 이미 다 쏨 → **패치 0**, 웹UI 커버리지 자동 |
| 방향 | 인바운드 전용(세팅은 HTTP) | **양방향**(param_set도 같은 선으로 → latency↓) |
| 신뢰성 | DGRAM fire-and-forget, flow control 없음 → **폭주 시 유실 위험** | TCP: 순서·무손실·backpressure |
| 거리 | Unix 소켓 = **같은 기계만** | TCP = **네트워크 너머**도 |

메시지 형태는 synapse가 유리: 앱 친화적 커스텀 문자열이라 파싱 거의 없음. 웹소켓은 mod-ui 원본
프로토콜(`param_set /graph/...`)을 파싱해야 함(그래서 pi-stomp `modalapi/ws_protocol.py`의 dataclass 파서).

### 결론 / 트리거
지금 갈아탈 이유 없음. synapse 방식이 이 유스케이스엔 더 단순·저지연·검증됨(역방향 싱크 2026-06-25 확인).
**웹소켓 카드를 꺼낼 트리거:**
1. mod-ui 업그레이드마다 `webserver.py` 패치 리베이스가 지겨워질 때. (특히 `focus-control-rendering.md`의
   `output_set` 역채널 추가처럼 패치 표면이 늘수록 비용↑.)
2. 페달보드 로드 등 **버스트 시 이벤트 누락**이 실제 관측될 때(위젯 몇 개 안 뜨는 증상). — 그전이라도
   완화책: Unix 소켓을 `SOCK_DGRAM`→`SOCK_STREAM`으로 바꾸거나 `SO_RCVBUF` 확대(웹소켓 안 가고 해결).
3. 화면을 **다른 기계/폰**으로 뺄 때.

최소 도입 형태(그때 가서): 기존 HTTP·notify는 두고, mod-ui `/websocket`을 **인바운드 수신용으로만** 하나
더 열어 `ws_protocol.py`식 파서로 붙이는 **가산적** 변경 → 롤백 쉬움.

---

## 참조
- pi-stomp 레포: `C:\Users\swson\pi-stomp` (`modalapi/websocket_bridge.py`, `modalapi/ws_protocol.py`,
  `pistomp/gpioswitch.py`, `pistomp/footswitch.py`, `setup/mod-tweaks/*.diff`)
- synapse 관련: [`qt-roadmap.md`](qt-roadmap.md)(디바운스 카드), [`config-todo.md`](config-todo.md)(콤보 리맵),
  `mod-tweaks/webserver.py`(`notify_synapsin`), `qt_main.py`(역방향 리스너), `presenter.py:206`(수신 핸들러).
