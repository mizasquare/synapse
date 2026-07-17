# Ganglion 로드맵 — 남은 일 (finalize 기준선)

> 🛠 **살아있는 로드맵 (남은 일만).** 끝난 것은 여기 안 적는다 — 결정의 근거·검증 기록은
> [`decisions.md`](decisions.md)(구현 결정 로그 A~W)에, 주제별 상세는
> [`encoder-rail-todo.md`](encoder-rail-todo.md) · [`workflow-review-todo.md`](workflow-review-todo.md)에 남아 있고
> 이 문서는 거기 흩어진 "남은 것"만 집계한다. 설계 정본 = [`design.md`](design.md).
> 마지막 갱신: **2026-07-17** — 전면 재작성(온메탈축 폐지) 후 같은 날: 번인 방어(S) · 버그 2건(T) ·
> MIDI Ch 제거 · Brightness(U) · 설정 저장소(V) · 라디오(W) · **텍스트 래스터 캐시(X)**까지 닫힘.
> **①에 About·레벨미터·튜너만 남았다.**
>
> ⚠️ **이 문서가 "튜너는 monitorfeed 배선이 전제"라고 적었던 것은 오류였다**(결정 H에서 물려받음).
> 튜너는 monitorfeed를 안 쓴다 — `cochlea`가 자기 JACK 클라이언트로 `capture_1`을 직접 뜬다.
> 없는 의존을 만들어 순서를 거꾸로 잡고 있었다. 자세한 건 [`decisions.md`](decisions.md) H의 폐기 블록.
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
> **남은 것:** `[열림]` **hotspot일 때 화면에 뭘 보여줄지** — 지금 SYSTEM 행엔 `AP`뿐이다. 붙을
> SSID(`starry`)·IP(172.24.1.1)를 어디 보여줄지 미결. 아래 `About`과 같은 주제.

- [ ] **SYSTEM `About`** — 마지막 남은 `TODO:` 토스트 스텁이자 **유일한 미구현 액션**(값 항목은
      클릭에 반응하지 않는다 — 결정 W 후속). 무엇을 보일지 미결: 버전? 보드수? I2C 주소?
      **hotspot SSID/IP?** 위 `[열림]`과 같은 주제라 같이 정하는 게 자연스럽다. (소, 결정 필요)
- [ ] **레벨미터 배선 (결정 H)** — IN/OUT 헤더 레벨(−14.2/−4.3)이 **하드코딩**. ~~monitorfeed~~가
      아니라 synapse `levelmeter.py`(자체 `jack.Client`, IN=`capture_1/2` 탭 · OUT=playback 피더
      미러링)를 `Runtime`의 심으로 얹는다 — `power`/`settings`/`radio`와 같은 자리지만 **방향이
      반대**(하드웨어→상태, `st.t`와 같은 부류). **[사용자] 필수 — 입력 클리핑 확인용.**
      온메탈 기동 확인 완료(2026-07-17), 전제였던 X도 닫혀 **인프로세스로 간다**. 숫자는 live amp가
      아니라 **5초 윈도 peak**(synapse `pack()`과 동일 — live는 매 틱 떨려 헤더 밴드를 매번 민다).
      포맷 = `"%.1f dB" % 20*log10(amp)`. 남음: `Meter` 심 + `st.inlvl`/`st.outlvl` + `_chain` 렌더.
      `st` 기본값을 `None`(→ `"--"`)으로 둘지 결정 필요 — **JACK 없는 dev/터미널에서 가짜 −14.2를
      보이면 거짓말**이지만, README 스크린샷(`assets/screens/*.png`)이 같이 바뀐다. (중)
- [ ] **튜너 실동작** — 지금은 **껍데기**다. `tcents=6` / `tnote="A"`가 `AppState` 기본값
      ([`../app.py`](../app.py):156-157)이고 **쓰는 코드가 없다** — 라이브 튜너는 영구히 "A / +6 cents",
      바늘은 x≈70에 얼어 있다. `TunerMode`는 플래그만 세운다. ~~monitorfeed 배선이 전제~~ —
      **틀렸다**(H 폐기 블록). 튜너는 `cochlea.TunerEngine`(NSDF+HPS, 자체 `capture_1` 클라이언트,
      `get_reading()` 풀 API)이고 **안 막혀 있었다**. 오히려 **온디맨드라 안전한 쪽**이다 —
      튜닝 중엔 연주 중이 아니다. 심 모양은 미터와 같고, 모드 진입/이탈 엣지에서 engine을
      start/stop(synapse `presenter.enter_tuner`와 동형). 무음/저신뢰 = `get_reading()→None`이라
      "listening" 표시가 필요하다(지금 상태엔 그 자리가 없다). (중)
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

- [ ] **RT 경로에서 파이썬 빼기 — 미터를 다시 붙이는 유일한 길** ⚠️ **①의 레벨미터가 여기 막혀 있다.**
      인프로세스 `LevelMeter`는 철회됐다(결정 X 정정: 리그 xrun의 97%, 남의 플러그인 3.7배 악화).
      **분리가 답이 아니다** — 리서치(64 에이전트, 1차 소스 추적 + 반증 패스)의 결론은
      "프로세스를 분리하라"가 아니라 **"RT 콜백이 GIL을 잡지 않게 하라"**이고, 그 둘은 다르다.
      - **대조군 Zynthian**: JACK 콜백을 **같은 프로세스**에서 돌린다. `zynlibs/zynmixer/mixer.c`가
        C이고 1335줄에 `Py_`/`PyGILState` 매치 **0개**. 파이썬은 `getDpm()` ctypes getter로 값을
        **당겨간다**. UI가 GIL을 5ms 붙들어도 오디오는 무관하다. ⚠️ 베낄 땐 뮤텍스는 베끼지 말 것 —
        `onJackProcess`가 콜백 전체에 걸쳐 잡는 그 뮤텍스를 ctypes로 노출된 `addStrip()` 등도
        잡는다. `PRIO_INHERIT` 없음 = 우선순위 역전 경로.
      - **`-S`가 이 박스를 못박는다**: 리서치는 우리 jackd를 `-R -P 95`로 보고 async라 판정하며
        "argv에 `-S`가 있으면 예산이 5.33→2.67ms로 반토막 나고 **어떤 스위치 인터벌도 못 맞춘다**"고
        스스로 조건을 달았다. 실제 argv: `jackd -t 2000 -R -P 95 -d alsa -d hw:pisound -r 48000
        -p 128 -n 3 -X seq -s -S` — **`-S`가 있다**(`-s`는 이 바이너리에선 `--silent`). 즉 sync.
        우리 실측(남의 클라이언트 3.7배 악화)이 독립적으로 확증한다. → `sys.setswitchinterval`은
        해법이 아니다.
      - **가장 싼 길 (권장): `modmeter` + monitorfeed.** 리서치의 "다섯 번째 선택지" — *애초에 JACK
        클라이언트가 필요한가.* 레벨 값은 **이미 오디오 그래프 안의 C에서** 나온다. `modmeter`는
        이 리그에 **이미 돌고 있고**(체인 끝 탭 = OUT) 화이트리스트 Utils에 있으며, `monitorfeed.py`가
        그 `level`/`peak`/`rms`를 웹소켓으로 **이미 나른다**(실측: `output_set modmeter level 0.0`).
        mod-host가 C로 RT에서 DSP하고 우리는 30Hz로 숫자만 읽는다 — **우리 프로세스에 JACK 클라이언트
        0개, C 코드 0줄, 새 프로세스 0개.** pi-stomp/MOD가 하는 방식. 남는 일: IN 탭용 두 번째
        인스턴스 + 그것들을 체인 노드로 보이지 않게 소유(conform 통과). **결정 H의 원래 문장이
        우연히 옳았다** — 틀린 이유로 도달했고, synapse에 대한 옳은 정정을 ganglion에 과적용해
        버렸다.
      - **차선: C 콜백 + ctypes**(Zynthian 패턴). 미터 외에 **튜너**가 걸리면 이쪽이 필요할 수 있다 —
        cochlea의 DSP는 LV2 플러그인으로 대체하기 어렵다(단, `gareus tuna#mod`가 카탈로그에 있다).
      - **먼저 잴 것**: 이 xrun이 **실제로 들리는지 미측정**. 엔진의 "클라이언트가 못 끝냄" 회계와
        ALSA 하드웨어 언더런은 다른 경로다. 파형 캡처로 불연속이 없으면 우선순위가 내려간다.
        (남의 클라이언트 3.7배 악화는 강한 정황이지 파형 증거가 아니다.) (대)
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
