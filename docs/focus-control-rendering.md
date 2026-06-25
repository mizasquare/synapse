# 포커스 카드 — 컨트롤/모니터 렌더링 설계

> 상태: **계층1(UI/분류) 구현 완료 + 오프디바이스 육안검증 완료. 계층2(라이브 피드)
> 미착수.** 미배포·미커밋. 라이브 앱은 미반영(서비스 재시작 전까지 구코드). 진행 내역은 §10.
> 관련: [`qt-roadmap.md`](qt-roadmap.md), [`ui-design-rules.md`](ui-design-rules.md).
> 작성: 2026-06-25 (mod-web-ui 동작 6에이전트 분석 + 플러그인 라이브러리 서베이 + 계층1 구현).

## TL;DR

포커스 카드가 **모든 컨트롤 포트를 원형 노브 하나로** 그린다
([`qtview._build_focus`](../qtview.py) → `knobs`, [`main.qml`](../qml/main.qml) 노브 Repeater).
그래서 (1) 토글/버튼/셀렉터 위주 이펙터(레코더 등)가 어색하고, (2) **출력(모니터) 포트를
통째로 버려서**([`modepctrl.py:713`](../modepctrl.py)) 레벨미터류 모니터 이펙터는 빈 카드가 된다.

해법은 두 갈래가 같은 뿌리다 — `effect/get`가 주는 **포트 메타데이터(LV2 properties)** 를
렌더 단계에서 살려쓰는 것. 컨트롤은 properties로 위젯 종류를 고르고, 모니터는 출력 포트
값을 스트림으로 받아 미터로 그린다. **synapse는 이미 properties를 파싱해 `EffectPort`에
담고 있다** — 버리는 건 렌더 직전(`_build_focus`)뿐이다.

---

## 1. mod-web-ui가 컨트롤/모니터를 그리는 방식 (요약)

플러그인 GUI는 LV2 TTL의 `modgui` 블록으로 선언된다. 두 개의 **독립된** 포트-매핑 어휘:

- `modgui:port` — 입력 컨트롤 포트 → 노브/스위치 (라벨·순서)
- `modgui:monitoredOutputs` — **출력** 컨트롤 포트 → 값 **스트리밍 등록**

위젯 종류 판별은 전적으로 **포트의 `properties`** 기반이다 (`modgui.js`). 핵심 결정 트리:
"enumeration도 toggled도 trigger도 아니면 → 노브." 최종 모양은 플러그인 템플릿의
`mod-widget` 속성이 덮어쓸 수 있으나, **기본값은 properties에서 자동 결정**된다.

값 전송 (웹소켓, 공백구분 텍스트):
- `param_set <inst> <sym> <float>` — 입력 컨트롤 값
- `output_set <inst> <sym> <float>` — **출력(모니터) 스칼라 값** ← 레벨미터
- `patch_set <inst> <uri> <atom>` — **atom 포트의 구조화 데이터(배열 등)** ← 스펙트럼

자세한 모니터 데이터 경로(monitor_output 구독 / 피드백 소켓 / data_ready 스로틀)는
참조 메모리 `mod-ui-monitor-path` 참고.

---

## 2. 컨트롤 타입 → 위젯 매핑 (LV2 properties 기반)

| 포트 속성 | 위젯 | synapse 현재 | 비고 |
|---|---|---|---|
| `enumeration` (+`scalePoints`) | 세그먼트 셀렉터/드롭다운 | 노브로 그림 ❌ | `scale_points` 라벨 사용 |
| `toggled` (enum/trigger 아님) | 온/오프 토글 | `is_toggle` 파싱됨, 렌더 안 함 | 2-state |
| `trigger` (pprop:trigger) | **순간 누름 버튼** | 노브로 그림 ❌ | record/stop/reset. 누르면 잠깐 뒤 default 복귀(`modgui.js:524`) |
| `integer` (enum/toggle 아님) | 스텝 노브(정수 스냅) | 연속 노브로 그림 | `range_steps` 활용 |
| `logarithmic` | 로그 노브 | 선형 노브로 그림 | 매핑만 다름 |
| `mod:tapTempo` | 탭 버튼 | — | 기존 탭템포 화면 재사용 |
| 그 외 float | 연속 링 노브 | **현행 그대로** | 변경 없음 |

**synapse가 이미 파싱하는 것** ([`modepctrl.py:716-730`](../modepctrl.py)):
`is_toggle`, `port_properties`(전체 리스트), `range_steps`, `scale_points`. → 데이터는
모델(`EffectPort`)에 다 있고, `_build_focus`가 `knobs` 만들 때 버릴 뿐.

**단서:** 속성 기반 매핑은 "스킨 100% 복제"가 아니라 거의 항상 맞는 **합리적 기본값**이다
(드물게 정수 포트를 노브로 보여주는 플러그인도 있음). "전부 노브"보다 비교 불가하게 정확하고,
플러그인 JS/템플릿을 실행할 필요가 없다.

---

## 3. 모니터 출력 포맷 분류 (라이브러리 서베이)

`/var/modep/lv2` 68개 중 **모니터 출력을 가진 건 9개뿐**. 포맷은 두 종류로 갈린다:

### (A) 스칼라 float — 9개 중 8개. `output_set`로 포트당 숫자 1개.

| 플러그인 | 모니터 출력 | 성격 |
|---|---|---|
| `modmeter` | level, peak, rms (0..1) | **레벨미터** (dB는 JS가 20·log10) |
| `sc_record` | LMETER (0..1), CLIP (0..1) | 레벨 + 클립 플래그 |
| `tuna` | note, cent, octave, freq_out | **튜너** (여러 스칼라) |
| `fat1` | 23개 (error, nmask, corr, m00…) | 오토튜너 상태/상관값 |
| `stepseq_s8n8` | pos, hostbpm | 현재 스텝/BPM |
| `bolliedelay` | tempo_out | 딜레이 템포 |
| `carla-files` | num_channels, bit_rate, … | 파일 메타데이터 |
| `rt-neural-generic` | ModelInSize | 모델 메타 |

→ **레벨미터는 단일 실수가 맞다.** "여러 값" 디스플레이(튜너)는 스칼라 포트 여러 개일 뿐이다.
LV2 컨트롤 출력 포트는 물리적으로 **float 1개**만 나른다 — 벡터를 컨트롤 포트로 못 낸다.

### (B) atom 배열 — 9개 중 1개 (`modspectre`). `patch_set`로 배열 전체.

`modspectre`(스펙트럼 애널라이저)의 `notify`는 컨트롤 포트가 **아니라** `atom:AtomPort`
(`atom:Sequence`)다. 프레임마다 **256-float 배열**(FFT bins)을 atom 메시지로 보내고
(`script-modspectre.js`의 `event.value.length !== 256`), 커스텀 JS가 SVG 패스로 그린다.

→ 스펙트럼/스코프류는 **근본적으로 다른(무거운) 경로**다: atom 디코딩 + 플러그인별 전용
드로잉. 이 라이브러리엔 사실상 `modspectre` 하나뿐.

---

## 4. 모니터 렌더링 — 3-tier 대응 (결정 2026-06-25)

모니터 시각 형태는 스펙만으론 완벽 분류 불가(MOD도 JS로 그림). 따라서 **세 단계로 대응**한다.
비배포 + 플러그인 셋이 정적이라 엣지케이스 하드코딩이 감당 가능하다는 전제.

**해석 순서: ② 하드코딩 레지스트리 → ① 휴리스틱 → ③ 스킵.**
(레지스트리는 오버라이드 겸 엣지케이스의 집. 휴리스틱이 일반 경로. 둘 다 실패하면 안 그림.)

### ① 휴리스틱 판독 → 범용 위젯
포트 **(타입 · units · range 모양)** 으로 분류. 플러그인 이름 안 씀. 대부분을 커버.

| 판독 신호 | 범용 위젯 | 예 |
|---|---|---|
| range [0..1], units 없음 | **세로 바 미터** (peak-hold 옵션) | modmeter level/peak/rms, sc_record LMETER |
| 정수 0/1 (toggled류) | **클립 LED** (>0 빨강 점등) | sc_record CLIP |
| units 보유 (db/hz/bpm/oct…) | **숫자 리드아웃** (+단위) | tuna freq/octave, stepseq bpm |
| 대칭 range [-N..+N] | **센터-제로 게이지** (v1=숫자+간이바) | tuna cent ±50 |
| 위 어디에도 안 걸림 | **숫자 리드아웃** (graceful fallback) | — |

### ② 하드코딩 → 개별 위젯
휴리스틱이 틀리거나 전용 표현이 필요한 포트를, **(plugin_uri[, symbol]) 키의 작은 레지스트리**
(데이터 테이블, 코드 아님)로 명시 지정. "시행착오로 찾은 엣지케이스"가 여기 쌓인다.
예: 다중밴드 디스플레이, 또는 나중에 만들 `modspectre` 스펙트럼(atom 256-배열) 전용 위젯.

### ③ 판독·하드코딩 둘 다 안 됨 → 표시 안 함
범용으로도 못 읽고 레지스트리에도 없는 모니터는 **그냥 안 그린다**(깨진/빈 위젯 대신 생략).
v1 기준: `modspectre`(atom), `fat1`의 난해한 상관 출력 23종, `rt-neural` ModelInSize 등.

---

## 5. 렌더링 파이프라인 개선 — 데이터 계약

### 현재
`_build_focus`가 `effect_ports`(입력 컨트롤만) → `knobs:[{symbol,name,value,norm,min,max,unit,display}]`
하나로 평탄화. QML이 항목마다 96px 링을 그린다.

### 제안
`_build_focus`에서 각 포트의 **`kind`** 를 properties로 도출하고, 위젯별 필드를 실어 보낸다.
모니터는 별도 리스트로.

```
focus = {
  ...,
  controls: [            # 입력 컨트롤 (kind별 분기)
    { kind: "knob"|"knob_int"|"knob_log"|"toggle"|"trigger"|"enum"|"tap",
      symbol, name, value, norm, min, max, unit, display,
      steps,             # knob_int
      default,           # trigger 복귀값
      options }          # enum: [{value,label}]  (scale_points)
  ],
  monitors: [            # 출력(모니터) 포트
    { kind: "meter"|"clip"|"numeric"|"gauge"|"spectrum",
      symbol, name, value, norm, min, max, unit,
      db: bool }         # dB 환산 여부
  ],
}
```

- `controls`는 기존 `knobs`를 **대체**(또는 `kind:"knob"` 하위호환 유지하며 점진 이행).
- `monitors`는 신규. `_build_focus`에서 입력 포트의 `if v is None` 가드를 **모니터엔 적용 안 함**
  (출력 포트는 시드값이 없을 수 있음).
- 노브 드래그의 무emit 갱신([`update_parameter_display`](../qtview.py:179)) 규율을 모니터에도
  적용 — `update_monitor_display`는 `dataChanged.emit()` 없이 norm만 in-place 갱신해야
  고빈도 틱이 카드를 통째로 리빌드하지 않는다.

---

## 6. 위젯별 QML 렌더 스펙 (테마: 800×480, cGreen `#5fd0a0` / cPanel `#141925` / 링 96px·stroke 9)

**입력 컨트롤**
- `knob` / `knob_log` — 현행 96px 링. 세로 드래그. log은 norm↔value 매핑만 로그.
- `knob_int` — 링 + `steps` 스냅. 값은 정수 표시. 드래그가 단계로 끊김.
- `toggle` — 알약형 스위치. on=cGreen 채움/off=cBorder 외곽. 탭=토글. 라벨 아래.
- `trigger` — 둥근 푸시 버튼. 누름=cGreen 플래시 → ~150ms 뒤 default 복귀(momentary).
  record/stop/reset에 사용.
- `enum` — 세그먼트(옵션 ≤4) 또는 드롭다운(>4). 현재 라벨 = `options`에서. 탭=다음/리스트.
- `tap` — 탭 버튼. 기존 탭템포 경로로 위임.

**모니터(읽기 전용, MouseArea 없음)**
- `meter` — 세로 바. 높이 ∝ norm, cGreen. dB range면 0dB 상단·하단 클램프. peak-hold는
  얇은 라인(옵션). 레벨미터의 level/peak/rms는 같은 카드에 바 2~3개.
- `clip` — 작은 원형 LED. value>0 → cRed 점등, 잠깐 유지 후 소등.
- `numeric` — 큰 숫자 Text(+단위). 튜너 note/freq, bpm, pos.
- `gauge` — 중앙 0 기준 좌우 바(cent ±). v1은 numeric+간이 바로 시작.
- `spectrum` — **v1 미구현.** "웹 UI에서 확인" placeholder 박스.

치수/색은 전부 튜너블 — 온디바이스 후 조정([`ui-design-rules.md`](ui-design-rules.md) 전제).

---

## 6.5 아키텍처 — "뷰가 길어지는 문제"를 어디서 흡수하나

플러그인을 강건하게 그리고 조작하게 만들수록 **세 가지 다른 성장 압력**이 생긴다. 각각
집이 다르다 — 한 곳(뷰 또는 modctrl)에 다 몰면 안 된다.

| 성장 압력 | 무엇 | 집 | 이유 |
|---|---|---|---|
| ① 포트 **해석** | kind 분류, norm↔value(log/int), dB 환산, enum 라벨, trigger default | **`EffectPort` 강화** (순수 파이썬, Qt·HTTP 무관) | 이미 raw 필드+behavior 보유. presenter도 view도 얇게 유지 |
| ② **드로잉** | kind별 픽셀 | **`qml/widgets/<Kind>.qml` 컴포넌트 + Loader/DelegateChooser(kind 키)** | 그림은 본질상 뷰에 있어야 함. "길어짐"은 **파일 분해**로 푼다(로직 이동 아님) |
| ③ 모니터 **스트리밍** | output_set 구독·마샬링 | **소형 전용 피드 모듈**(예 `monitorfeed.py`) — Backend seam 뒤 | 드로잉도 HTTP 요청/응답도 아닌 새 전송. fakemodep는 합성판 |

**핵심 원칙**
- `_build_focus`/`_build_view_effect`는 **번역기**로 유지 — `EffectPort.kind`가 미리 계산되면
  필드 복사만 한다. 위젯 로직이 여기서 자라면 안 됨.
- **modctrl(=`ModepController`)에 위젯 분류를 넣지 말 것.** 거긴 전송+raw 모델 계층이다.
  프레젠테이션 taxonomy를 거기 묶으면 `fakemodep`/테스트/미래의 비-MOD 백엔드가 UI 지식을
  짊어진다. modctrl은 **raw 포트 dict 반환**, 해석은 `EffectPort`가.
- **거대한 선제적 "PluginAbstraction" 모듈은 짓지 말 것 (YAGNI).** seam은 이미 있다
  (Backend ABC → Effect/EffectPort 모델 → presenter → qtview → qml). 위젯 ~7종 + 모니터
  ~5종은 작다 — `EffectPort`의 property+메서드면 충분하다. 그 클래스가 커지면 그때
  `portspec.py`로 추출. 모듈은 **자격을 얻으면** 만든다.
- §4 tier② **하드코딩 레지스트리는 코드가 아니라 데이터** — `(plugin_uri[,symbol]) → 위젯` 맵.
  해석 계층(EffectPort/portspec) 옆에 둔다. 분류 로직 자체엔 plugin 이름이 안 들어간다(레지스트리 조회뿐).
- 정당한 신규 모듈은 ③ **모니터 피드**뿐 — 새 능력이라 전용 조각 가치가 있다.

요약: 사용자 직관(중간 추상화)이 맞다 — 단 그 추상화는 **모델(EffectPort) 안의 해석 계층**
이지 새 god-module이 아니고, 뷰의 길어짐은 **QML 컴포넌트 분해**로 따로 푼다.

## 7. 통합 지점 (파일/함수)

1. [`modepctrl.py:713`](../modepctrl.py) — `['control']['input']`만 읽는 루프에서
   `['control']['output']`도 읽어 모니터로 보관 (입력의 `if current_value` 트루시 가드는
   모니터에 적용 안 함). `EffectPort`에 `is_output`/별도 컬렉션.
2. [`backend.py`](../backend.py) — 모니터 값 공급 수단 추가 (구독/콜백 또는 폴링). 실
   `ModepController` + `fakemodep` 양쪽. (전송 방식 A/C 결정은 §9.)
3. [`presenter.py`](../presenter.py) `_build_view_effect` — `effect_monitors` 병렬 방출 +
   `update_monitor_display(instance,symbol,value)` 진입점.
4. [`qtview.py:238`](../qtview.py) `_build_focus` — `controls`(kind 분기) + `monitors` 빌드,
   무emit `update_monitor_display`.
5. [`qml/main.qml`](../qml/main.qml) 노브 Repeater 부근 — kind별 Loader/위젯 + 모니터 Repeater.
6. 갱신 구동 — push(A/C)면 [`QtScheduler.schedule_once`](../qtscheduler.py)로 Qt 스레드 마샬링
   (풋스위치 폴 패턴), poll(D)이면 `schedule_interval` ~20-30Hz **오프스레드**.

---

## 8. 검증 체크리스트

서버 측(`http://localhost/`, 포트 80 authbind)으로 확인 완료:
- [x] `effect/get` JSON 모양 — modmeter `gui.monitoredOutputs=['level','peak','rms']`,
  `ports.control.output` 3개, ranges 0..1, **units 빈값**, props 빈값. (→ tier① 바 미터로 판독)
- [x] `syn_get`이 출력 포트 값을 **안 줌**(500). 출력값은 push 전용 → **폴링(D) 폐기, 스트림(A) 필수.**

온디바이스(머신 가능 + 모니터 플러그인 로드 필요 — 보드 상태 변경이라 사용자 승인 후):
- [ ] mod-ui 웹소켓에서 `output_set <inst> <sym> <val>` 프레임 실제 포맷·흐름 캡처 (A안 검증).
- [ ] 모니터 instance 경로(`/graph/..`)가 synapse 내부 instance 키와 일치하는지.
- [ ] `data_ready N` ack 왕복이 의도대로 도는지 + 미터가 매끈한 타깃 레이트.
- [ ] (개발용) `fakemodep`에 모니터 fixture + 합성 값 생성기 — 머신 없이 위젯 육안검증용.

## 9. 미해결 / 결정사항

- **전송 방식 A vs C** (설계 분기점):
  A = 기존 mod-ui 웹소켓에 수동 리스너로 붙어 `output_set` 읽기 (추천, 구독 이미 켜져있음).
  C = synapse `synapsin.sock` 리버스 채널에 `output_set` 전달 추가(`mod-tweaks/webserver.py` 패치).
- **dB 환산** — JS가 하던 `20·log10`을 synapse가 범용 적용할지, 포트 `units.render`로 포트별 결정할지.
- ~~**스펙트럼(atom)**~~ — **결정**: v1은 §4 tier③(표시 안 함). 전용 위젯 만들면 tier②로 승격.
- ~~**enum/trigger 스코프**~~ — **결정**: 계층1에서 전 kind 한 번에 구현(아래 §10).

## 10. 구현 진행 (계층1, 2026-06-25)

**완료 — 분류만으로(플러그인 하드코딩 없이) 전 타입 렌더, 오프디바이스 PNG 검증.**
`qt_app.py --shot --focus WidgetLab` (offscreen+software 백엔드, 라이브 앱 무관)로
쇼케이스 카드 확인: 컨트롤 6종(knob/knob_int/knob_log/toggle/trigger/enum) +
모니터 4종(meter/clip/numeric/gauge) 전부 distinct 렌더.

변경 파일:
- `model.py` — `EffectPort.is_output`/`forced_kind` + `widget_kind` property(컨트롤=properties,
  모니터=type/units/range) + `MONITOR_WIDGET_OVERRIDES`(tier-2 스텁). `Effect.monitors`.
  `initialize_modep_pedalboard`에 모니터 출력 루프(monitoredOutputs ∩ control.output; atom=tier-3 자동스킵).
- `presenter.py` `_build_view_effect` — 포트별 `port_kind`, `effect_monitors`(get_value 안 씀, None 제외 안 함).
- `qtview.py` `_build_focus` — `controls`(kind/options/display) + `monitors`; `_norm`이 knob_log 로그 매핑.
- `qml/ControlWidget.qml`·`qml/MonitorWidget.qml` — 신규(드로잉 분해). `main.qml`은 두 패널 인덱스.
- `fixtures/00-widget-lab.json` — 전 kind 쇼케이스 이펙트(검증 타깃).

폴리시 완료: 로그노브 norm/역매핑, 정수 스냅, 토글/트리거/enum 중복 값라벨 제거.

**실보드 검증 (qt_app.py `--real`, 라이브 mod-host에 read-only HTTP, 라이브 앱 무관).**
현재 보드 `clean 0`(Noisegate/3BandEQ/modmeter×2/AIDA-X/CabinetLoader/CfgStereo) 렌더 확인.
실데이터가 잠복 버그 2개를 드러내 수정:
- `model.py` 빌더 `if current_value:` → `is not None`. 값 0 컨트롤(0 dB 게인, reset 트리거)이 버려지던 것 수정(EQ 6노브 다 표시).
- `qtview._enum_options` — 실 mod-ui scalePoints는 **dict**(`{value,label}`)인데 tuple로 가정해 크래시. dict+tuple 양형 처리.
다(多)컨트롤 플러그인(AIDA-X ~12개) 오버플로 → `main.qml` 컨트롤 패널을 **단일행 가로 스크롤**(Flickable)로. 모니터 영역 침범 해소.
주의(온디바이스 확인 필요): 노브 위(preventStealing) 가로 플릭 스크롤 감도 — 실 터치 튜닝 필요.

**남음 — 계층2(머신 복귀 후):**
- 라이브 모니터 피드 = mod-ui 웹소켓(A안) `output_set` 구독 + `data_ready` ack + Qt 스레드 마샬.
- `update_monitor_display` 무emit 타깃 갱신 신호(현재 정적 시드 렌더).
- 실 플러그인 fixture(sc_record/modmeter)로 충실도 검증(필요시). 온디바이스 검증 = §8.
- (미배포·미커밋: 라이브 반영하려면 서비스 재시작 필요.)
