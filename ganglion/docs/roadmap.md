# Ganglion 로드맵 — 남은 일 (finalize 기준선)

> 🛠 **살아있는 로드맵 (남은 일만).** 끝난 것은 여기 안 적는다 — 결정의 근거·검증 기록은
> [`decisions.md`](decisions.md)(구현 결정 로그 A~W)에, 주제별 상세는
> [`encoder-rail-todo.md`](encoder-rail-todo.md) · [`workflow-review-todo.md`](workflow-review-todo.md)에 남아 있고
> 이 문서는 거기 흩어진 "남은 것"만 집계한다. 설계 정본 = [`design.md`](design.md).
> 마지막 갱신: **2026-07-20** — 번인 방어(S) · 버그 2건(T) · MIDI Ch 제거 · Brightness(U) ·
> 설정 저장소(V) · 라디오(W) · **텍스트 래스터 캐시(X)** · **레벨미터(H, 실기 검증)** ·
> **튜너 실동작**(온메탈 실음 검증까지 완료) · **SYSTEM About**(네트워크·크레딧·build)까지 닫힘.
> **① 기능축이 사실상 비었다** — 남은 건 `effect 채널`(소) 하나뿐. 다음 축은 ② 뷰 폴리시.
>
> ⚠️ **④의 "RT 경로에서 파이썬 빼기"는 폐기됐다 — 문제가 존재하지 않았다.** 미터의 xrun 688은
> 파이썬도 GIL도 아니고 유닛에 `LimitRTPRIO`가 없어 콜백이 SCHED_OTHER로 돌던 것이었다. 유닛
> 두 줄로 **한가한 리그에서 사실상 0**(688 → 정착 후 관측된 xrun은 전부 개발 부하였다). C 샴 ·
> 프로세스 분리 · Zynthian 패턴 · `modmeter`가 **전부 불필요**해졌고,
> 64 에이전트 리서치는 **틀린 질문에 정교하게 답한** 것이 됐다. 전말은 [`decisions.md`](decisions.md)
> X의 "정정의 정정" — **저널 네 줄을 아무도 먼저 읽지 않은 게 그날의 전부다.**
>
> 📝 **튜너 착지(2026-07-18, 온메탈 검증 2026-07-20).** "monitorfeed 배선이 전제"였다던 것은
> 오류였고(결정 H에서 물려받음), 실제로는 `cochlea`가 자기 JACK 클라이언트로 `capture_1`을 직접
> 떠서 **안 막혀 있었다** — [`../hw/tuner.py`](../hw/tuner.py) 온디맨드 심으로 구현.
> **실기(기타 → JACK → 바늘)까지 검증 완료 — 이 축은 닫혔다**(① 참조).
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

> ✅ **2026-07-17 완료: SYSTEM 메뉴 본체 + 설정 저장소.** 하루에 축이 거의 비었다. 근거·검증은
> [`decisions.md`](decisions.md) **U**(Brightness) · **V**(저장소) · **W**(라디오).
>
> - **설정 영속화 저장소** — [`../settings.py`](../settings.py), `~/.modep/ganglion.json`. ①의
>   **선결**이었다. [`../config.py`](../config.py)(코드가 아는 값)와 **다른 물건**이다: 이건
>   *사용자가 고른 값*이고, 상수는 설정이 될 수 없다. **이 기기는 종료되지 않고 뽑히므로**
>   ([부검](../../docs/save-corruption-postmortem.md)) 원자적 쓰기(tmp→fsync→replace→dir fsync) +
>   **필드별** 관대한 로드(파손 7종 전부 defaults 착지, raise 0) + 즉시 쓰기(종료 시점이 없다).
>   `run_device`만 주입해 fake 실행이 실기 값을 못 덮는다(`SYNAPSE_STATE_DIR` 가드 상속).
>   설정 추가 = `FIELDS` 한 줄 + `AppState` 필드.
> - **Brightness** — ENC1 **제자리 편집**(새 모드 0개, `AppState` 필드 1개), 3단계
>   `(0x08, 0x2D, 0xFF)`. **만들기 전에 "지각되긴 하나"부터 쟀다** — design.md의 "밝기 변화를 못
>   느낀다"는 **전백에서만 참**이었고 실 UI는 6단계가 구분된다. 수치는 신설 `config.py`로:
>   §7이 결정만 해두고 안 만든 자리였고, `0x3D`/`rotate=0`이 두 벌(runtime + oled_probe) 있던
>   중복도 같이 없앴다.
> - **WiFi 3상태 / BT 2상태** — SYSTEM **값 항목**, 부팅 시 적용[사용자]. `hotspot`이 계획을
>   뒤집었다(rfkill은 AP를 못 만든다) → WiFi = nmcli + polkit 3액션
>   ([`50-ganglion-radio.rules`](../../deploy/ganglion-service/50-ganglion-radio.rules)),
>   BT = rfkill(`netdev` 그룹이라 규칙 불필요). **`pb-hotspot`이 이미 있어서**[사용자 지적] 앱은
>   up/down만 하고, 덕분에 polkit에서 `settings.modify.*`를 뺐다. 클라이언트 SSID는 코드에 없다 —
>   NM autoconnect에 맡겨야 리그가 다른 방으로 따라간다. 온메탈 **전 상태 확인됨**[사용자].
> - **`MIDI Ch` 제거**[사용자 동의] — 설계가 없는 라벨이었다(스펙 0). GECO는 **보낼 게 없고**
>   (synapse의 MIDI = 페달 배선인데 이 기기엔 페달이 없다), 인바운드는 **MODEP가 이미 처리한다**
>   (PC ch1 → 스냅샷, 지금 켜져 있음). → design.md §9-9 닫음.
>
> **~~남은 것~~ [닫힘, About에서 함께]:** hotspot일 때 뭘 보여줄지는 About의 네트워크 줄이
> 흡수했다 — `AP: starry` / `172.24.1.1`(config 상수). 클라이언트일 땐 `<SSID>: <IP>`를 라이브로.

- [x] **SYSTEM `About`** `[해결]`(2026-07-20) — 마지막 `TODO:` 토스트 스텁이자 유일한 미구현
      액션이었다. `tuner`처럼 실제 화면 모드로 올리되 **SYSTEM 위에 얹는 오버레이**(mode_of 최상위)라
      **이탈이 공짜로 SYSTEM 메뉴 복귀**가 된다(confirm-over-sub와 같은 패턴). 세 줄:
      **네트워크**(모드 조건부·정직) — `hotspot`→`AP: starry`/`172.24.1.1`(config 상수),
      `on`→라이브 `<SSID>: <IP>`(못 받았으면 `WiFi: --`), `off`→`WiFi: off`. 라이브 값은
      **`hw/radio.py`에 분리한 `status()` 읽기 경로**로 얻는다 — radio의 write-only 독트린은
      *컨트롤 경로*(3상태)에만 걸리고, About의 읽기는 별개다. **`set_wifi` 콜백에 안 붙인 이유**:
      클라이언트는 autoconnect가 워커 종료 *후* 붙어 IP가 없고, 로밍·DHCP가 radio 엣지 없이 세상을
      바꿔 캐시가 썩는다 → About 열 때 라이브로 읽는다(워커 스레드 1회, Runtime이 엣지 구동).
      **크레딧** `written by / miza and claude`(`&`가 이 폰트에서 `$`로 읽혀 `and`). **build**
      `<날짜> <short-hash>[*]`(runtime `_build_stamp`, `git describe`는 내부 마일스톤 태그 때문에
      장황해 `rev-parse --short`+dirty로; 릴리즈 넘버링을 안 하므로 커밋이 곧 신원). `--abouttest`
      14검(오버레이 진입/이탈, 라이브 읽기 client-only·None, Runtime 엣지 1회, 4프레임 구분, 스탬프)
      + `--walk` 골든 불변(about 기본 False). **남은 것:** 온메탈 실 네트워크 확인(SSID/IP 실측).
- [x] **레벨미터 배선 (결정 H)** `[해결]`(2026-07-17) — synapse `levelmeter.py`(자체 `jack.Client`,
      IN=`capture_1/2` 탭 · OUT=playback 피더 미러링)를 `Runtime`의 심으로 얹었다 — `power`/`settings`/
      `radio`와 같은 자리지만 **방향이 반대**(하드웨어→상태, `st.t`와 같은 부류). **인프로세스로 산다.**
      배선 → xrun 688로 철회 → **원인이 유닛의 `LimitRTPRIO` 부재였음이 측정으로 밝혀져 재배선**
      (전말은 [`decisions.md`](decisions.md) X의 "정정의 정정"; 프로세스 분리·C 샴은 **불필요**로
      판명돼 ④에서 내렸다). 실기: 무음 IN −59 / 드라이브 보드 OUT −14, **한가한 리그에서 xrun은
      0**(남의 클라이언트 0). 숫자는 live amp가 아니라 **5초 윈도 peak**(synapse `pack()`과
      동일 — live는 매 틱 떨려 헤더 밴드를 매번 민다). `st.inlvl`/`st.outlvl` 기본값은 `None`(→ `"--"`):
      JACK 없는 dev/터미널에서 가짜 −14.2를 보이면 거짓말이다. → README 스크린샷은 ⑤에 남아 있다.
- [x] **튜너 실동작** `[해결]`(2026-07-18, 온메탈 검증 2026-07-20) — 껍데기(영구 "A / +6")를 실동작으로. 미터와
      **대칭인 온디맨드 INBOUND 심** [`../hw/tuner.py`](../hw/tuner.py): `st.tuner` 엣지에서
      `cochlea.TunerEngine`(NSDF+HPS, 자체 `capture_1` JACK 클라이언트, One-Euro+노트락)를
      start/stop하고 `get_reading()`을 `st.tnote`/`st.tcents`로 쓴다(synapse `presenter.enter_tuner`와
      동형). 엔진은 **튜닝 중에만** 산다 — 리그가 연주 중이 아님이 보장되는 유일한 순간. ~~monitorfeed
      전제~~는 틀렸었고(H 폐기 블록) 튜너는 capture를 직접 뜬다. 무음/저신뢰 = `get_reading()→None`은
      새 필드 `st.tlisten`으로 "listening / play a note" 화면(마지막 노트를 얼리는 대신 정직하게
      표시 — `inlvl=None → "--"`와 같은 idiom). LED는 **인튠(|cents|<5)에서만 green/green**, 그 외
      purple. 지연 부착+재시도(부팅 레이스, 미터와 동일). `--tunertest` 17검(엣지: 진입/이탈 lifecycle,
      None→listening, 라운딩, 죽은 엔진, 부팅 레이스 재시도, LED, stop 멱등) + `--walk` 골든 불변
      (tlisten 기본 False라 골든 튜너 프레임 유지). **온메탈 검증 완료**(2026-07-20): 리그에서
      ENC1-hold 후 실제 기타 → JACK → 바늘 동작 확인 — 셀프테스트가 안 타던 DSP 경로까지 닫혔다.
- [ ] **effect 채널 (toast/persist emit)** — 콤보 저장 버그(위 ✅)는 닫혔지만 채널 자체는
      남아 있다. → [`decisions.md`](decisions.md) N "남은 것"(2). (소)

## ② 뷰 폴리시 (상태를 올바로 드러냄)

- [ ] **롱프레스는 릴리즈가 아니라 임계 시점에 발동해야 한다** [사용자, 2026-07-18] — 지금
      [`../input.py`](../input.py) `GestureRecognizer._switch`는 click/long을 **릴리즈 엣지에서만**
      판정한다(`dur >= long_press_s`). 그래서 홀드하는 동안 사용자는 자기가 지금 어느 상태인지
      **볼 수가 없다** — "충분히 눌렀나? 지금 떼면 click으로 먹나?" 하고 멈칫하게 된다. 이건
      본질적으로 **상태 은폐**라 ②에 든다. 고칠 방향: 버튼이 눌린 채 `now - since >= long_press_s`가
      되는 **그 틱에** `Press(enc, "long")`을 바로 내보내고(엣지가 아니라 매 틱 검사 필요 — `update()`가
      지금은 엣지에서만 `_switch`를 돌린다), 이후 릴리즈는 억제(콤보의 `_consumed`와 같은 플래그).
      임계 도달 순간 **햅틱 대용 피드백**(LED 깜빡/색전환 한 번)이 있으면 "됐다"가 손끝에 전해진다.
      ⚠️ **파급:** (1) 키보드 에뮬레이터는 릴리즈가 없어 이미 `Press("long")`을 즉시 낸다 — 하드웨어만
      바뀌면 되고 에뮬레이터와 동작이 **더** 일치한다. (2) `ENC0-hold=zoom-out`이 홀드 중 발동하면,
      튜너 진입(`ENC1-hold`)·무빙 취소 등 hold 액션이 **손 떼기 전에** 일어난다 — 대체로 바라던 바지만
      long 후 그 버튼의 회전/클릭이 오면 안 되므로 억제 플래그가 확실해야 한다. (3) `LONG_PRESS_S=0.6`이
      체감 임계가 되니 실기에서 재조정 여지. 결정 D(제스처)·Q1(튜너 이탈)과 같은 계열. (중)
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

- [x] ~~**RT 경로에서 파이썬 빼기 — 미터를 다시 붙이는 유일한 길**~~ **[폐기 2026-07-17 — 문제가
      존재하지 않았다.]** 이 항목 전체가 **틀린 전제** 위에 있었다. 미터의 xrun 688은 파이썬도 GIL도
      아니고 **`ganglion.service`에 `LimitRTPRIO`가 없어 콜백이 SCHED_OTHER로 돌던 것**이었다. 유닛
      두 줄로 688 → **한가한 리그에서 0**(남의 클라이언트 11 각각 → 0). "정착 후 22/10분"으로 처음
      적었으나 그 22는 기동 트랜지언트 + 내 개발 부하였다. 전말·측정치는 [`decisions.md`](decisions.md)
      X의 "정정의 정정".
      - **필요 없어진 것**: C 샴, 프로세스 분리, Zynthian 패턴(C 콜백+ctypes), `modmeter`+monitorfeed,
        `sys.setswitchinterval`. 리서치(64 에이전트, 1차 소스 추적 + 반증 패스)는 **정교하게 답했지만
        틀린 질문에 답했다.** 반증 패스조차 "GIL이 범인"이라는 전제 안에서만 반증했다.
      - **`modmeter`는 별도로 폐기** — [사용자] 판단: mod-ui 경유 보드 조작은 필요 대비 레이어가
        과하고, 보드마다 인스턴스를 심고 라우팅하고 있는지 판정하는 게 지저분하다. (synapse도 같은
        이유로 접고 JACK 버퍼 직접 뜨는 쪽으로 선회해 `levelmeter.py`가 됐다 — 레포에 없던 기록.)
      - **남은 항목은 아래 두 개**(`draw` 꼬리, 인코더 폴 34ms) — 둘 다 미터의 xrun과 무관한
        별개 축이다. `draw` 꼬리는 실제 xrun 기여가 미확인이고, 인코더 폴은 오디오가 아니라 반응성.
- [ ] **`draw`의 80ms 꼬리** ⚠️ **실제 xrun을 내는지는 미확인** — `tools/gil_probe` 실측: `draw`가
      p50 6.5ms인데 **max 80ms**, GIL 지각 max 12.5ms(= JACK 주기의 4.7배)로 60초에 2번 튄다.
      스파이크 자체는 실측이지만 **한가한 리그에서 그게 xrun이 되는 걸 본 적은 없다** — 관측된
      xrun은 전부 개발 부하에 붙어 났다(decisions X (9)). 아래 "안 바뀐 상태면 render 건너뛰기"가
      그대로 해법 후보. 먼저 잴 것: 80ms가 I2C 쓰기인지 PIL인지(`oled_bench`가 자리에 있다).
      급하진 않다 — 패널이 켜져 있는 건 서비스 수명의 **5.7%**(X 측정)뿐이다. (소)
- [ ] **인코더 폴 34ms — 루프가 15Hz다** ⚠️ **오디오와 무관하다**(GIL을 안 문다 — 그게 `time.sleep`이라).
      `tools/gil_probe` 실측: `source.poll()`이 wall **33.7ms**, 그래서 루프가 33Hz가 아니라 **15Hz**
      (883틱/60초)로 돌고 노브 반응이 최대 ~70ms 늦다. 정체는 `adafruit_seesaw`의 `read()`가 거는
      **강제 `time.sleep(0.008)`×4**(틱당 모듈 2개 × delta/pressed). `delay=`는 **인자다** — C도 새
      드라이버도 필요 없고 값만 낮추면 된다. 남는 일: seesaw가 실제로 요구하는 최소 지연을 온메탈로
      재고(`tools/encoder_bench`가 자리), 놓치는 디텐트 없이 얼마까지 내려가는지 확인. 디텐트 자체는
      seesaw 내부 카운터라 **유실되진 않는다** — 순수 지연 문제. (중)
- [ ] **`layout_engine=ImageFont.Layout.BASIC`** — 이 박스에 libraqm 0.7.0이 있어
      `ImageFont.truetype()`이 묻지 않고 RAQM을 고른다 = **ASCII 라벨에 HarfBuzz 셰이핑 전체를
      매 호출 지불**. 한 줄, 실측 1.56x(1.953→1.255ms), TTF 품질 그대로. X의 캐시가 이미 상각하므로
      이제는 **미스에만** 듣는다 — 그래서 급하지 않지만 공짜다. `--fonttest`가 픽셀 동일성을 지킨다. (소)
- [ ] **안 바뀐 상태면 render 자체를 건너뛰기** — DiffSink가 출력을 diff하듯 모델도 diff한다.
      X 이후 render는 0.26ms라 CPU 동기는 약해졌지만, RT 예산이 2.67ms인 리그에선 **GIL을 아예 안
      잡는 틱**이 여전히 값어치가 있다. 장애물은 `st.t`(매 틱 변함) — 마퀴만 그걸 읽으므로
      "스크롤 중이 아니면 t를 키에서 뺀다"가 성립한다. 단 보드명은 100%, 노드명 75%가 넘쳐
      대개 뭔가는 스크롤 중이라 이득이 제한적(dwell 2.2s/사이클이 상한). (중)
- [ ] **move per-detent reconcile 최적화** — 노드를 들고 한 칸 움직일 때마다 full reconcile
      (`dump_graph` GET/detent). tracked-set을 유지하면 diff만으로 충분. 실기에서 체감되면 착수. (중)
- [ ] **파라미터 스케일링 곡선 (결정 E)** — `adjust()`는 `(max−min)/40` **선형**. Hz·ms류는 로그가
      자연스럽다. 시안도 선형이라 급하진 않음. 단위별 곡선을 정의할지 **미결**. (중, 결정 필요)

- [ ] **README 스크린샷 4종 재촬영** — `assets/screens/*.png`가 헤더에 `-14.2`/`-4.3`을
      보이는데 **앱은 이제 그 숫자를 그릴 수 없다**(H 배선 후 미터 없으면 `--`, 있으면 실측 dB).
      README는 이들을 "`render(st)` output ... exactly what the SH1107 receives"라고 주장한다.
      ⚠️ **출처 불명 — 추측으로 다시 굽지 말 것.** 생성 스크립트가 없고(`ca8ebd5`는 PNG만 커밋),
      헤더 잉크가 x=0에서 시작하는데 이는 `app.py`의 x=5(레일 회피 +3px)도 `design_screens.py`의
      x=2도 아니다 — 다운스케일이 어긋났거나 **레일(L) 도입 이전** 이미지일 수 있다. 재현 시도는
      헤더 아래에서만 2877px 차이가 났다(= 내 상태 재현이 틀렸다는 뜻). 먼저 **어느 파이프라인이
      만들었는지 확정**하고, 재촬영은 스크립트로 고정할 것. 기기를 대표해야 하므로 `--`가 아니라
      **실측 레벨**을 넣는 게 맞다(무음 IN −59.2/OUT −77.0). (소)

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
- [`decisions.md`](decisions.md) — **구현 결정 로그(A~W).** 왜 그렇게 정했나 + 라이브 검증 기록.
- [`encoder-rail-todo.md`](encoder-rail-todo.md) — 좌측 3px 인코더 레일 (구현 완료, 상세·비용표 보존).
- [`workflow-review-todo.md`](workflow-review-todo.md) — 워크플로우 검토 Q1–Q7 (전부 착지, 대응 근거 보존).
- [`plugin-whitelist.md`](plugin-whitelist.md) — 피커 버킷 큐레이션 (→ `geco_whitelist.json`). **스테일**:
  전 항목 미체크 상태로 `geco_catalog.json`에 의해 대체됨. 라우팅/포트 메모는 없다(④ 참조).
- [`../../docs/ganglion-geco-logbook.md`](../../docs/ganglion-geco-logbook.md) — **교환일기.** synapse↔ganglion 크로스머신 채널.
- [`../README.md`](../README.md) — 앱 개요 · 실행법 · 파일맵.
