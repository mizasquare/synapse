# Ganglion 로드맵 — 남은 일 (finalize 기준선)

> 🛠 **살아있는 로드맵 (남은 일만).** 끝난 것은 여기 안 적는다 — 결정의 근거·검증 기록은
> [`decisions.md`](decisions.md)(구현 결정 로그 A~U)에, 주제별 상세는
> [`encoder-rail-todo.md`](encoder-rail-todo.md) · [`workflow-review-todo.md`](workflow-review-todo.md)에 남아 있고
> 이 문서는 거기 흩어진 "남은 것"만 집계한다. 설계 정본 = [`design.md`](design.md).
> 마지막 갱신: **2026-07-17 (전면 재작성 — 온메탈축 폐지(닫힘), 번인 방어 신설 후 같은 날 완료,
> 버그 2건 발견, 유틸 노드 항목 정정.)**
>
> **정렬 원칙 — 우선순위 축:** ① 기능(미구현 본체) → ② 뷰 폴리시 → ③ 온메탈 잔여 →
> ④ 아키텍처·성능 → ⑤ 백로그. (번인 방어·버그 축은 열린 날 닫혔다 — 위 ✅ 둘.)
> 같은 축 안에서는 대체로 규모 작은 것 먼저. 작업은 한 번에 하나씩, 변경 전 사용자 승인.
>
> **synapse(GCaMP6s) 쪽 로드맵은 이 머신의 일이 아니다.** 저쪽 변경 중 ganglion에 영향을 주는 것만
> [`../../docs/ganglion-geco-logbook.md`](../../docs/ganglion-geco-logbook.md)(교환일기)로 노티받는다.
> 지금까지의 유일한 synapse-core 접점 = `modepctrl.py` 확장(snapshot rename/remove, remove_pedalboard).

**현재 사실관계 (2026-07-17):** **온메탈 브링업이 닫혔다.** 이전 로드맵의 ①축("유일한 진짜 미지수")은
전부 착지했다 — I2C 주소(`36 37 3d`, 패널은 **0x3D**), 버스 400kHz, 장착 `rotate=0`, `LumaWriter`
온메탈 검증(미지수 3개 전부 해소), diff 드라이버, LED 팔레트·밝기 0.1, systemd 자동실행(cc00eb1).
1MHz 오버클럭은 **불필요** 판정(남은 병목은 대역이 아니라 패널 구동 전류). → 근거는 전부
[`design.md`](design.md) §0·§2 "실기 확정".

즉 **미지수가 있던 자리에 이제 실물이 있고, 우선순위가 뒤집혔다.** 소프트웨어는 거의 완성이고
(상태머신·1-bit 렌더·인코더 레일·워크플로우 Q1–Q7, `GecoAdapter`가 라이브 MODEP에 붙어 실 오디오
그래프를 편집), 실물이 들어오며 드러난 **유일한 비가역 리스크**(패널이 24시간 같은 정적 프레임을
켜 두던 것)는 아래 ✅로 같은 날 닫혔다. **남은 것은 전부 되돌릴 수 있는 일**이라, 여기서부터가
finalize다.

---

> ✅ **2026-07-17 완료: 번인 방어 — 무조작 30초 dim / 5분 off.** 최우선으로 올라왔던 축이라
> 같은 날 닫았다. 패널이 24시간 같은 정적 프레임을 켜 두던 것이 이 앱의 **유일한 비가역
> 리스크**였다(다른 미완 항목은 늦어져도 코드가 기다린다). `hw/oled.PanelPower` + `Runtime`,
> **`AppState` 필드 0개·뷰 0줄**(dim/off는 픽셀이 아니라 하드웨어 상태라 순수층에 안 들어간다).
> 레일 실측 **165.9 → 134.2 → 122.0 mA**로 off가 Pi 자체 소비에 정확히 안착(패널 몫 0) —
> design.md §2 "유휴 전력", [`decisions.md`](decisions.md) S. **열린결정 #12("10초 무조작 →
> depth −1")는 폐기하고 이걸로 대체** — 그건 부품 없던 시절의 기능성 탐구 설계였다.
>
> **남은 것:** `off_s=300`은 **잠정값** — 살아보고 확정. `[열림]` NeoPixel도 같이 재울지
> (LED는 번인이 없어 수명 이슈는 아니다. 순수 취향).

> ✅ **2026-07-17 완료: 버그 2건** — 둘 다 사용자에게 **거짓말을 하던** 종류라 finalize 전에 닫았다.
> → [`decisions.md`](decisions.md) T.
>
> - **패스스루 소실 `[치명]`** — `geco_routing.py`의 `if fx:`가 IN→OUT 종단을 감싸 **트렁크 fx가
>   0개면 기타가 무음**이었다. 정확한 조건은 "빈 체인/소스만"이 아니라 **fx 0개인 모든 체인**
>   (탭 전용 = 레벨미터 1개도 무음 — 로드맵 최초 집계가 이걸 빠뜨렸다). `prev`가 그때 `'IN'`이라
>   **가드 제거만으로** 그 줄이 IN→OUT 패스스루가 된다. 6가지 체인 형태로 재현→검증, 라이브 보드는
>   **+0/−0**(fx가 4개라 무영향). **포팅 원본(`editor_bridge._quick_wire_keys`)에 같은 버그**가
>   있어 교환일기에 넘김.
> - **콤보 스냅샷 저장** — `combo()`가 `backend.save()`를 **아예 호출하지 않고** 토스트만 띄우고
>   dirty 점까지 지웠다. `--looptest`가 이미 콤보를 누르고 있었는데 결과를 안 봤다 → 스파이 백엔드로
>   `save calls=['snap']` 검증 추가.

## ① 기능 (미구현 / 부분구현 본체)

- [ ] **설정 영속화 저장소 `[선결]`** — ganglion은 **설정을 저장하지 않는다.** [`../config.py`](../config.py)가
      생겼지만 그건 **상수**(코드가 아는 값)고, **사용자가 고른 값**(밝기 단계, WiFi/BT 상태, 번인
      `off_s`)을 재부팅 너머로 나르는 물건이 없다 — 지금 Brightness는 매 부팅 mid로 돌아간다.
      synapse의 `configs.py`는 공유 상수 모듈이라 writer가 없고 손대지 않는다(§1 재사용 경계).
      `configs.LOCAL_STORAGE` 아래 JSON 하나면 충분. (중, **선결** — 아래 전부가 여기 걸려 있다)
- [ ] **SYSTEM `About`** — 마지막 남은 `TODO:` 토스트 스텁([`../app.py`](../app.py):471). 무엇을
      보일지 미결(버전? 보드수? I2C 주소?). (소, 결정 필요)
      > ✅ 2026-07-17: **`Brightness` 완료** — ENC1 제자리 편집(새 모드 0개, `AppState` 필드 1개),
      > 3단계 `(0x08, 0x2D, 0xFF)`. 만들기 전에 "지각되긴 하나"부터 쟀고, design.md의 "밝기 변화를
      > 못 느낀다"는 **전백에서만 참**이었다(실 UI는 6단계 구분). 수치는 신설 [`../config.py`](../config.py)로
      > — §7이 결정만 해두고 안 만든 자리이고, `0x3D`/`rotate=0`이 두 벌 있던 중복도 같이 없앴다.
      > 영속화는 아직(재부팅 시 mid로). → [`decisions.md`](decisions.md) U.
      >
      > ✅ 2026-07-17: **`MIDI Ch` 제거**[사용자 동의] — 설계가 없는 라벨이었다(스펙 0,
      > design.md §7의 열린 질문 한 줄이 전부). GECO는 **보낼 게 없고**(synapse의 MIDI = 페달
      > 배선인데 이 기기엔 페달이 없다), 인바운드는 **MODEP가 이미 처리한다**(PC ch1 → 스냅샷,
      > 지금 켜져 있음). 검증할 장비도 없어 만들면 영원히 미검증으로 남았을 것. → design.md §9-9 닫음.
- [ ] **WiFi / BT on/off** — 리포지토리에 **선례 0**(첫 라디오 제어). (중)
  - **`rfkill`을 쓰면 sudo도 polkit도 필요 없다** — `/dev/rfkill`이 `root:netdev`이고 `miza`가
    `netdev` 소속. **그룹 권한은 세션 독립**이라 로그인 세션 없는 systemd 서비스에서도 산다.
  - **`nmcli radio wifi off`는 거부된다** — polkit `enable-disable-wifi`가 `allow_active=yes`,
    `allow_inactive=no`. 서비스는 세션이 없어 inactive(`nmcli general permissions`가 이미 "아니요").
    **synapse 전원 메뉴가 겪은 것과 같은 실패**이고 그때 해법이
    `deploy/ui-service/49-synapse-power.rules`다. → **rfkill 경로 채택**(새 polkit 규칙 불필요).
  - `[열림]` SYSTEM 하위 항목 vs 별도 화면.
- [ ] **monitorfeed 배선 (결정 H)** — IN/OUT 헤더 레벨(−14.2/−4.3)이 **하드코딩**. synapse
      `monitorfeed.py`를 `Runtime.step()`에 틱으로 얹는다. 코스트 모델상 좁은 밴드 갱신은 저렴. (중)
- [ ] **튜너 실동작** — 지금은 **껍데기**다. `tcents=6` / `tnote="A"`가 `AppState` 기본값
      ([`../app.py`](../app.py):156-157)이고 **쓰는 코드가 없다** — 라이브 튜너는 영구히 "A / +6 cents",
      바늘은 x≈70에 얼어 있다. `TunerMode`는 플래그만 세운다. **monitorfeed 배선이 전제.** (중)
- [ ] **effect 채널 (toast/persist emit)** — 콤보 저장 버그(위 ✅)는 닫혔지만 채널 자체는
      남아 있다. → [`decisions.md`](decisions.md) N "남은 것"(2). (소)

## ② 뷰 폴리시 (상태를 올바로 드러냄)

- [ ] **유틸 노드가 이펙트처럼 보인다** — ⚠️ **정정: 라우팅 예외처리는 이미 되어 있다.**
      [`../geco_routing.py`](../geco_routing.py):53 `desired_wiring()`이 포트 **개수를 가정하지 않고**
      실 LV2 포트 심볼을 보고 셋으로 분류한다 — 트렁크 fx(`ain`&`aout`, :62) / **소스**(`ain==[]`:
      Audio File 0/2, Metronome 0/1 → OUT 직결, :76) / **탭**(`aout==[]`: Level Meter 1/0 → 직전
      트렁크에서 받음, :73). editor의 `_quick_wire_keys()`([`../../editor_bridge.py`](../../editor_bridge.py):800)
      verbatim 포팅이라 검증된 로직이다. **문제는 UI가 이걸 모른다는 것** —
      `geco_adapter._node()`(:105-110)가 투영에서 `ain`/`aout`을 버려서 체인 스트립에 메트로놈이
      인라인으로 그려지고, 옮겨도 소리가 안 바뀐다. editor는 소스를 트렁크 **위**, 탭을 **아래**
      레인에 그려 구분한다([`../../editor_bridge.py`](../../editor_bridge.py):1810-1815). 우리 1차원
      스트립엔 레인 개념이 없다. `[열림]` **레인 vs 배지 vs 숨김.** (소, 결정 필요)
- [ ] **Utils 약어 뭉침** — 버킷 약어(`UTL`)가 Utils 안에서 다 같아 구분이 안 됨. per-plugin 약어
      필요. 위 항목과 같은 화면이라 **같이 손대는 게 자연스럽다.** 참고: Utils는 **혼합 버킷**이라
      (소스 2 · 탭 1 · 진짜 인라인 fx 6) **버킷 멤버십은 라우팅 클래스의 프록시가 못 된다.** (소)

## ③ 온메탈 잔여

온메탈 브링업에서 닫힌 축의 부스러기. 전부 육안 확인류라 작다.

- [ ] **0x36 인코더 보드 교체** — 디솔더-교체 중 파손. 교체 예정. design.md §2의 색상별 전류
      측정이 이 파손 상태에서 나온 값이라 **신뢰도가 낮다**(재측정은 선택 — 밝기 0.1에서 무의미).
- [ ] **Micro5@10 실 패널 legibility 육안** — UI는 떴고 티어 확인만 남음. → design.md §9-6.
- [ ] **레일 디더 실측** — 좌측 3px 레일의 1:2 가로줄 디더가 목표 명도로 읽히는지. 안 읽히면 간격
      튜닝. → [`encoder-rail-todo.md`](encoder-rail-todo.md) "남은 검토".
- [ ] **RTC/NTP 확인** — 스냅 이름의 요일이 시스템 날짜 자동(결정 Q3)이라 RTC 없고 NTP도 안 닿으면
      요일이 어긋난다. 라벨용이라 비치명. → [`workflow-review-todo.md`](workflow-review-todo.md) Q3.
- [ ] `[열림]` **전백 플리커 미해결** — "열당 연속 길이" 모델대로면 전백(모든 열 128/col)은 붕괴해야
      하는데 76.6mA로 높게 나온다. 육안상 실사용 문제가 아니라 **UI 제약은 걸지 않는다**(design.md
      §2). 모델의 구멍으로만 남긴다.

## ④ 아키텍처 · 성능

- [ ] **move per-detent reconcile 최적화** — 노드를 들고 한 칸 움직일 때마다 full reconcile
      (`dump_graph` GET/detent). tracked-set을 유지하면 diff만으로 충분. 실기에서 체감되면 착수. (중)
- [ ] **파라미터 스케일링 곡선 (결정 E)** — `adjust()`는 `(max−min)/40` **선형**. Hz·ms류는 로그가
      자연스럽다. 시안도 선형이라 급하진 않음. 단위별 곡선을 정의할지 **미결**. (중, 결정 필요)

## ⑤ 백로그 · 미세관찰

한 줄짜리 결정 후보들.

- [ ] **knob lock 탈출 비대칭** — 락 해제는 ENC1 토글뿐인데 ENC0 hold는 GLANCE로 점프해버린다.
- [ ] **back 3중 중복** — MENU·SYS·SUB의 `< Back` 항목 + ENC0 hold + 반대손 click. 항목형 Back 제거 여지.
- [ ] **dirty 비대칭** — board saveas는 dirty를 안 세우고 snap saveas만 세운다. 상단 점 의미가 갈림.
- [ ] **스테레오 입력 옵션** — IN=mono L(`capture_1`) 확정[사용자, 기타]. 나중에 SYSTEM에서 선택 시
      `_reconcile`의 `in_mode` 파라미터화.
- [ ] **`geco_conform --all` 배치 영구화** — conform-on-load로 충분해서 미구현. 선택적 위생.
- [ ] **키보드 타이밍-accel** — 하드웨어 전 테스트용(키보드는 |delta|=1이라 D의 가속이 no-op). 선택.
- [ ] **TUNER 레일 ↔ Q1 정합** — 레일은 E0-solid(=E0 hold 나감)로 그리는데 코드는 "아무 press 이탈".
      레일은 힌트라 상충은 아님. 튜너 이탈을 E0-hold 전용으로 좁힐지는 Q1 재검 시 함께.
- [ ] **헤더 이름 티어** (24px+마퀴 vs 16px, design.md §9-10) — 열린 결정.
- [ ] **GAAD67 잔재 정리** — `/etc/rc.local`의 `amidithru "GAAD67"`가 이 박스에서도 뜨는데
      (클론 이미지 잔재) `reflex`/`mastervol`이 inactive라 **아무도 안 쓴다**. 지울지 확인. (소)
- [ ] **관찰: connect 500 버스트** — 2026-07-16 23:17~23:20 `journalctl -u ganglion`에 `/effect/connect`
      HTTP 500이 134건. 그 이후로는 없다(MODEP 재기동 흔적으로 보임). 재발하면 조사, 아니면 폐기.

---

## 참조

- [`design.md`](design.md) — **설계 정본.** 하드웨어 스펙(실측) · 2a 인터랙션 모델 · 화면별 결정 · §9 열린결정.
- [`decisions.md`](decisions.md) — **구현 결정 로그(A~U).** 왜 그렇게 정했나 + 라이브 검증 기록.
- [`encoder-rail-todo.md`](encoder-rail-todo.md) — 좌측 3px 인코더 레일 (구현 완료, 상세·비용표 보존).
- [`workflow-review-todo.md`](workflow-review-todo.md) — 워크플로우 검토 Q1–Q7 (전부 착지, 대응 근거 보존).
- [`plugin-whitelist.md`](plugin-whitelist.md) — 피커 버킷 큐레이션 (→ `geco_whitelist.json`). **스테일**:
  전 항목 미체크 상태로 `geco_catalog.json`에 의해 대체됨. 라우팅/포트 메모는 없다(④ 참조).
- [`../../docs/ganglion-geco-logbook.md`](../../docs/ganglion-geco-logbook.md) — **교환일기.** synapse↔ganglion 크로스머신 채널.
- [`../README.md`](../README.md) — 앱 개요 · 실행법 · 파일맵.
