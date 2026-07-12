# Ganglion 로드맵 — 남은 일

> 🛠 **살아있는 로드맵 (남은 일만).** 끝난 것은 여기 안 적는다 — 결정의 근거·검증 기록은
> [`decisions.md`](decisions.md)(구현 결정 로그 A~O)에, 주제별 상세는
> [`encoder-rail-todo.md`](encoder-rail-todo.md) · [`workflow-review-todo.md`](workflow-review-todo.md)에 남아 있고
> 이 문서는 거기 흩어진 "남은 것"만 집계한다. 설계 정본 = [`design.md`](design.md).
> 마지막 갱신: **2026-07-12 (문서 신설 — 첫 집계. + ③ 노브 스크롤·패치 2×1·marquee, ⑤ [+] 셀 완료 반영.)**
>
> **정렬 원칙 — 우선순위 축:** ① 온메탈 브링업(유일한 진짜 미지수) → ② 기능(미구현 본체) →
> ③ 뷰 폴리시(상태를 올바로 드러냄) → ④ 아키텍처·성능 → ⑤ 백로그·미세관찰.
> 같은 축 안에서는 대체로 규모 작은 것 먼저. 작업은 한 번에 하나씩, 변경 전 사용자 승인.
>
> **synapse(GCaMP6s) 쪽 로드맵은 이 머신의 일이 아니다.** 저쪽 변경 중 ganglion에 영향을 주는 것만
> [`../../docs/ganglion-geco-logbook.md`](../../docs/ganglion-geco-logbook.md)(교환일기)로 노티받는다.
> 지금까지의 유일한 synapse-core 접점 = `modepctrl.py` 확장(snapshot rename/remove, remove_pedalboard).

**현재 사실관계:** 앱은 **소프트웨어적으로 거의 완성**이다. 상태머신(depth 0/−1 + 8모달)·1-bit 렌더·
인코더 레일·워크플로우 검토 Q1–Q7 전부 착지했고, `GecoAdapter`가 **살아있는 MODEP/pisound에 붙어
실 오디오 그래프를 편집**한다(param/bypass/place/insert/move/remove/save/rename/delete + patch 위젯,
전부 라이브 검증). synapse 코어 수정은 `modepctrl.py` 확장 한 건뿐.
**미지수는 실물 하드웨어 하나로 수렴한다** — OLED·인코더 모듈이 아직 온메탈 검증 전이고,
`runtime.run_device`와 `hw/seesaw.py`는 **스텁**(하드웨어 없이 작성, 미실행)이다.

---

## ① 온메탈 브링업 (최우선 — 유일한 미검증 층)

앱 로직은 터미널·라이브 백엔드로 다 검증됐다. 반면 **물리 I/O 경로는 한 번도 실행된 적이 없다.**
이 축이 닫히기 전엔 나머지 항목의 우선순위도 확정할 수 없다(실측이 설계를 바꿀 수 있으므로).

- [ ] **I2C 실측 & 주소 확정** — 설치 후 `i2cdetect -y 1`: 디스플레이(0x3C/0x3D) + 인코더 2개
      (0x36 / 점퍼로 0x37) + **pisound와의 주소·버스 충돌 확인**. → `hw/seesaw.py` TODO ①.
- [ ] **`hw/seesaw.py` 실기 확정 (스텁 → 실물)** — ② 회전 부호(`invert=`로 모듈별 반전),
      ③ 스위치/NeoPixel 핀(문서상 기본값 24/6, 보드 리비전 대조). 폴링은 **확정**
      (INT는 read-to-clear라 오프로드 아님 — [`design.md`](design.md) §3). 33Hz 폴 기준.
- [ ] **`runtime.run_device` 실기 기동** — luma.oled `sh1107` 지원 버전 확정 + 실 패널 렌더 확인.
      현재 `rotate=0`으로 열지만 **FFC-down 고정 방향이라 rotate 강제가 필요**(design.md의 90° 전제와
      충돌 — 실측이 정본). 여기서 방향을 못 박는다.
- [ ] **OLED diff 기반 on-change 드라이버** — ①의 진짜 성능 레버. 지금은 매 틱 풀프레임 전송이라
      I2C 버스를 독차지한다(인코더 폴 굶김 위험). **바뀐 페이지 밴드만 전송**하는 diff 드라이버로
      바꾼다. 코스트 모델은 [`../i2c_cost.py`](../i2c_cost.py), 규율은 design.md §2. rotate 성능 비교는
      무의미(방향이 고정이므로) — 레버는 diff 하나뿐. (중)
- [ ] **1MHz I2C 오버클럭 채택 여부** — 위 diff 드라이버로 충분하면 불필요. 신뢰성 실측 후 판단.
- [ ] **LED 팔레트 실값 확정 (결정 I)** — `runtime.LED_RGB`는 잠정값. 실 NeoPixel에서 **주간 시인성·
      밝기·off 처리** 튜닝. 버킷색 구분이 실제로 눈에 들어오는지가 판정 기준.
- [ ] **레일 디더 실측** — 좌측 3px 레일의 1:2 가로줄 디더가 목표 명도로 읽히는지. 안 읽히면 간격 튜닝.
      → [`encoder-rail-todo.md`](encoder-rail-todo.md) "남은 검토".
- [ ] **RTC/NTP 확인** — 스냅 이름의 요일이 시스템 날짜 자동(결정 Q3)이라, RTC 없고 NTP도 안 닿으면
      요일이 어긋난다. 라벨용이라 비치명이지만 배선 때 확인. → [`workflow-review-todo.md`](workflow-review-todo.md) Q3.
- [ ] **부팅 자동실행 (systemd)** — synapse의 `deploy/ui-service/` 패턴 참고(헤드리스라 훨씬 단순:
      eglfs·polkit 불필요). 온메탈 기동이 안정된 뒤. (소)

## ② 기능 (미구현 / 부분구현 본체)

- [ ] **SYSTEM 메뉴 항목 3개** — `Brightness` · `MIDI Ch` · `About`이 아직 `TODO:` 토스트 스텁
      (`app.py:431`). Tuner·Back만 실동작. Brightness는 ①의 OLED 드라이버(contrast)와 함께 붙이는 게 자연스럽다. (소)
- [ ] **monitorfeed 배선 (결정 H)** — IN/OUT 헤더 레벨(−14.2/−4.3)과 튜너 cents가 **하드코딩**.
      synapse `monitorfeed.py`를 `Runtime.step()`에 틱으로 얹는다. 코스트 모델상 좁은 밴드 갱신은 저렴.
      **튜너가 실제로 동작하려면 이게 전제** — 현재 튜너는 껍데기다. (중)
- [ ] **effect 채널 (toast/persist emit)** — seam이 생겼으니 실 타깃(디스크 persist·param push)이
      존재한다. live 배선 이음매에 녹인다. → [`decisions.md`](decisions.md) N "남은 것"(2). (소)
- [ ] **무조작 자동 진입 (스크린세이버, 결정 G)** — 시안의 "10초 무조작 → depth −1". 유지할지·시간값
      **미결**. `Runtime.step()`에 얹는 자리는 이미 있음. (소, 결정 필요)

## ③ 뷰 폴리시 (상태를 올바로 드러냄)

라이브 보드를 실제로 렌더해보며 사용자가 지목한 것들. 128×128의 공간 압박에서 오는 문제라
하드웨어 실측(①)과 무관하게 지금 손댈 수 있다.

> ✅ 2026-07-12 완료: **노브 focus 스크롤 + 패치 2×1 셀** — 고정 2×3 격자(7번째 노브부터 잘려나갔다)를
> 행 패킹으로 교체, 패치(`k="file"`)는 전체폭 한 행 + 값 줄 Micro5 티어. 반칸 7글자 → 전체폭 30글자로
> NAM·Cab·Reverb IR 이름 **100% 전체표시**. 창은 `st.knob`에서 파생(순수 유지), CHAIN의 ENC1 레일은
> `list(knob)`으로 승격. → [`decisions.md`](decisions.md) P.

> ✅ 2026-07-12 완료: **marquee 스크롤** — 포커스된 한 줄만 dwell→scroll→dwell로 흐른다. 위상은
> `st.t`(런타임이 그려주기 전에 써넣는 표시용 시계)의 순수 함수라 뷰는 계속 `f(st)`, 컨트롤러는
> 시간을 모른다. `t=0`(--walk/골든)에서 프레임 **비트동일**. 적용: 보드·스냅명(GLANCE),
> 노드명(체인 헤더), 포커스 노브의 이름·값, 피커의 선택 행(카테고리·플러그인).
> 위상은 **마지막 입력 기준**(`t - t_mark`)이라 제스처가 모든 이름을 머리로 되감는다(에뮬 피드백).
> → [`decisions.md`](decisions.md) Q. 정적 맥락은 여전히 `_fit` trunc(캄).
>
> **정정**: 최초 집계표의 피커 수치는 호출부 티어·폭을 잘못 읽어 틀렸다. 실제 스트립 폭 기준으로
> 카테고리 = **62% 잘림**(8개 중 5개 — Dynamics·Filter·Pedal·Spatial…), 플러그인명 = 12%(42% 아님).
> 잘림률 상위는 보드·스냅명 100% > 노드명 75% > 카테고리 62% > AIDA 패치값 39% 순.
> 남은 trunc(0% 잘림이라 marquee 불필요): confirm 대상명 · NAMING 생성이름 · 피커 헤더 카테고리 라벨.
- [ ] **미터/메트로놈 탭이 체인 노드로 노출** — 라이브 보드의 유틸리티 탭이 이펙트 노드처럼 보인다.
      숨김 or 배지 처리? (결정 필요) (소)
- [ ] **Utils 약어 뭉침** — 버킷 약어가 Utils 안에서 다 같아 구분이 안 됨. per-plugin 약어 필요. (소)

## ④ 아키텍처 · 성능

- [ ] **move per-detent reconcile 최적화** — 노드를 들고 한 칸 움직일 때마다 full reconcile
      (`dump_graph` GET/detent). tracked-set을 유지하면 diff만으로 충분. 실기에서 체감되면 착수. (중)
- [ ] **파라미터 스케일링 곡선 (결정 E)** — `adjust()`는 `(max−min)/40` **선형**. Hz·ms류는 로그가
      자연스럽다. 시안도 선형이라 급하진 않음. 단위별 곡선을 정의할지 **미결**. (중, 결정 필요)

## ⑤ 백로그 · 미세관찰

한 줄짜리 결정 후보들. 워크플로우 검토의 "미세 관찰" + 라이브 배선 중 남긴 메모.

- [ ] **knob lock 탈출 비대칭** — 락 해제는 ENC1 토글뿐인데 ENC0 hold는 GLANCE로 점프해버린다.
- [ ] **back 3중 중복** — MENU·SYS·SUB의 `< Back` 항목 + ENC0 hold + 반대손 click. 항목형 Back 제거 여지.
- [ ] **dirty 비대칭** — board saveas는 dirty를 안 세우고 snap saveas만 세운다. 상단 점 의미가 갈림.
> ✅ 2026-07-12 완료: **[+] 셀** — 빈 체인(0노드) 진입점 + Insert after-only 갭이 한꺼번에 닫힘.
> 파보니 0노드는 진입점이 없는 게 아니라 **크래시**였다(`render`/`rails`/`leds` IndexError; 이펙트
> 1개짜리 보드에서 그것을 지우면 앱 사망). 체인 커서 축에 머리·꼬리 `[+]` 의사-셀을 두어 0노드를
> 합법적 상태로 만들고, 슬롯 메뉴는 `Add Before`/`Add After`로 방향을 명시. FakeGeco의 빈 슬롯은
> 폐기(에뮬 == 실기). 체인 상한은 두지 않음. → [`decisions.md`](decisions.md) R.
- [ ] **스테레오 입력 옵션** — IN=mono L(`capture_1`) 확정[사용자, 기타]. 나중에 SYSTEM에서 선택 시
      `_reconcile`의 `in_mode` 파라미터화.
- [ ] **`geco_conform --all` 배치 영구화** — conform-on-load로 충분해서 미구현. 선택적 위생.
- [ ] **키보드 타이밍-accel** — 하드웨어 전 테스트용(키보드는 |delta|=1이라 D의 가속이 no-op). 선택.
- [ ] **TUNER 레일 ↔ Q1 정합** — 레일은 E0-solid(=E0 hold 나감)로 그리는데 코드는 "아무 press 이탈".
      레일은 힌트라 상충은 아님. 튜너 이탈을 E0-hold 전용으로 좁힐지는 Q1 재검 시 함께.
- [ ] **GECO 자체 MIDI 정체성** (design #7) · **헤더 이름 티어**(24px+마퀴 vs 16px, #8) — 열린 결정.

---

## 참조

- [`design.md`](design.md) — **설계 정본.** 하드웨어 스펙 · 2a 인터랙션 모델 · 화면별 결정 · §9 열린결정.
- [`decisions.md`](decisions.md) — **구현 결정 로그(A~R).** 왜 그렇게 정했나 + 라이브 검증 기록.
- [`encoder-rail-todo.md`](encoder-rail-todo.md) — 좌측 3px 인코더 레일 (구현 완료, 상세·비용표 보존).
- [`workflow-review-todo.md`](workflow-review-todo.md) — 워크플로우 검토 Q1–Q7 (전부 착지, 대응 근거 보존).
- [`plugin-whitelist.md`](plugin-whitelist.md) — 피커 버킷 큐레이션 (→ `geco_whitelist.json`).
- [`../../docs/ganglion-geco-logbook.md`](../../docs/ganglion-geco-logbook.md) — **교환일기.** synapse↔ganglion 크로스머신 채널.
- [`../README.md`](../README.md) — 앱 개요 · 실행법 · 파일맵.
