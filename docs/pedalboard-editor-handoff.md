# 페달보드 에디터 목업 — 핸드오프 명세

> ✅ **상태: 완료(FINISHED) — 능동 작업용 아님(소비 완료).** 이 핸드오프가 지시한 목업 제작 →
> 라이브 이식(M1~M6d, 브랜치 `pedalboard-editor`)이 **전부 끝났다**. 5절 포트→위젯 매핑은 여전히
> 유효한 레퍼런스지만, **7절의 동결 72-플러그인 카탈로그는 M7(라이브 플러그인 카탈로그)이 통째로
> 대체 완료됐다**(호스트 전체 설치 플러그인으로 승격, ctl 16포트 truncate·프리셋 누락 해소).
> 현재 로드맵은 [`qt-roadmap.md`](qt-roadmap.md) 참조.
>
> **목적(원문)**: 페달보드 에디터(이펙터 노드를 배치/배선하는 그래프 UI)를 윈도 머신에서 **목업 먼저** 만들어
> UI/사용성을 확정한 뒤 본 앱(Qt/QML)으로 이식한다. 이 문서는 그 목업이 "실제 설치된 이펙터"를
> 그대로 쓸 수 있도록 데이터 명세 + 렌더링 가이드를 정리한 핸드오프 문서다.
>
> **동봉 데이터**: [`fixtures/installed-effects.json`](../fixtures/installed-effects.json)

---

## 1. 데이터 출처와 신뢰도

- 라이브 mod-ui 호스트(`http://localhost:80`)의 `/effect/list` + `/effect/get?uri=` 응답을 그대로 덤프.
- 즉 **실제 파이에 설치되어 동작 중인 72개 이펙터**의 메타/포트가 손실 없이 들어있다. 가짜 샘플 아님.
- 재생성: 파이의 레포 루트에서 `python3 tools/dump_effects.py` (플러그인 추가/삭제 시 다시 돌리면 갱신).
- 덤프 시 다음만 정리했다(목업에 무의미·과대):
  - `gui.iconTemplate` / `gui.stylesheet` / `gui.javascript` / `gui.documentation` → `"<dropped: N chars>"` 마커로 치환.
  - `gui.screenshot` / `gui.thumbnail` / `gui.resourcesDirectory` → 파이 절대경로 대신 **basename만** 남김.
  - **포트 데이터(audio/control/cv/midi)는 무손실.**

---

## 2. 빠른 시작 (목업에서 로드)

```js
const catalog = await fetch('installed-effects.json').then(r => r.json());
// catalog.count      -> 72
// catalog.categories -> { Utility: 13, Reverb: 10, ... }  팔레트 그룹핑용
// catalog.plugins    -> 이펙터 배열 (아래 스키마)

for (const p of catalog.plugins) {
  const audioIn  = p.ports.audio.input.length;    // 입력 핀 개수
  const audioOut = p.ports.audio.output.length;   // 출력 핀 개수
  const knobs    = p.ports.control.input;          // 노브/스위치/드롭다운 후보
}
```

---

## 3. 최상위 스키마

```jsonc
{
  "generated_from": "http://localhost:80/effect/list + /effect/get",
  "note": "...",
  "count": 72,
  "categories": { "Utility": 13, "Reverb": 10, ... },   // 팔레트 그룹 + 개수
  "plugins": [ /* 아래 plugin 객체 */ ]
}
```

## 4. `plugin` 객체 스키마

| 필드 | 타입 | 목업에서의 용도 |
|------|------|-----------------|
| `uri` | string | 이펙터 고유 ID. 노드 인스턴스가 참조할 키. |
| `name` | string | 표시 이름 (노드 타이틀). |
| `label` | string | 짧은 라벨(좁은 폭 표기용). |
| `brand` | string | 제조사 — 카드/뱃지. (없으면 `author.name` 참고) |
| `category` | string[] | 분류. 첫 원소가 1차 카테고리 (예: `["Filter","Equaliser"]`). 팔레트 그룹핑. |
| `comment` | string | 설명 툴팁. |
| `version` / `microVersion` / `minorVersion` | string/int | 버전 표기(선택). |
| `iotype` | int(0~3) | 오디오 I/O 토폴로지 힌트(내부값). **목업에선 신뢰하지 말고 `ports.audio` 개수로 판단 권장.** |
| `hasExternalUI` | bool | 외부 전용 UI 여부(목업에선 보통 무시). |
| `ports` | object | **핵심.** 아래 5절. |
| `gui` | object | 스킨 메타(브랜드 색/노브 종류 등). 6절. |
| `presets` | array | 프리셋 목록(있으면 노드에 프리셋 셀렉터). 49개 플러그인이 보유. |
| `parameters` | array | LV2 patch 파라미터(파일 로더류). 대부분 빈 배열. |
| `author` | object | `{ name, homepage, email }`. |
| `bundles` | string[] | 파이 절대경로(목업 무관). |

---

## 5. `ports` 스키마 — 목업의 핵심

`ports`는 4종 × (input/output) 구조:

```jsonc
"ports": {
  "audio":   { "input": [ Port… ], "output": [ Port… ] },   // 배선 대상(오디오 신호)
  "control": { "input": [ Port… ], "output": [ Port… ] },   // input = 노브/스위치, output = 모니터값
  "cv":      { "input": [ … ],     "output": [ … ] },        // 컨트롤 볼티지(소수 플러그인만)
  "midi":    { "input": [ … ],     "output": [ … ] }         // MIDI 포트(신스/시퀀서)
}
```

### 5.1 `Port` 객체 (control.input 기준 — 노브 1개)

```jsonc
{
  "index": 4,                 // LV2 포트 인덱스
  "symbol": "THRES",          // 내부 심볼(주소지정 키)
  "name": "Threshold",        // 표시 이름
  "shortName": "Thres",       // 짧은 표기
  "ranges":  { "minimum": -70.0, "maximum": 0.0, "default": -20.0 },
  "units":   { "label": "decibels", "render": "%f dB", "symbol": "dB", "_custom": false },
  "properties": [],           // 위젯 종류 결정 (아래 5.2)
  "scalePoints": [],          // 드롭다운 항목 [{ "value": 0, "label": "PRE" }, …]
  "designation": "",          // LV2 designation URI (enabled, BPM 등 특수역할)
  "rangeSteps": 0,
  "comment": ""
}
```

오디오 포트는 `ranges`/`units`가 의미 없고 `symbol`/`name`만 쓰면 된다(배선 핀 라벨).

### 5.2 `properties` → 위젯 매핑 (덤프에 실제 등장하는 값 전부)

| property | 의미 | 목업 위젯 |
|----------|------|-----------|
| `toggled` | on/off (min/max=0/1) | **토글 스위치** |
| `enumeration` (+ `scalePoints` 채워짐) | 이산 선택지 | **드롭다운/세그먼트** (`scalePoints` 라벨) |
| `integer` | 정수값만 | **정수 스텝퍼/노브** |
| `logarithmic` | 로그 스케일 | **로그 테이퍼 노브** |
| `trigger` | 순간 동작(눌렀다 복귀) | **모멘터리 버튼** |
| `tapTempo` | 탭으로 템포 입력 | **탭 버튼** |
| `hasStrictBounds` | min/max 강제 클램프 | 입력 클램프 |
| `connectionOptional` | 배선 필수 아님 | 핀 점선/옵셔널 표시 |
| `notOnGUI` | UI 비노출 | **숨김** |
| `causesArtifacts` | 값 변경 시 오디오 글리치 | 실시간 드래그 자제(스텝/디바운스) |
| `tempoRelatedDynamicScalePoints` | scalePoints가 템포 따라 동적 | 동적 라벨 |

> 매핑 우선순위: `scalePoints` 비어있지 않으면 드롭다운 → `toggled`면 스위치 → `integer`면 스텝퍼 →
> 그 외 연속값은 노브(`logarithmic`이면 로그 테이퍼). `notOnGUI`는 항상 숨김.

### 5.3 `units.symbol` 에 실제 등장하는 단위
`%`, `dB`, `Hz`, `ms`, `s`, `BPM`, `semi`(반음), `m`, `x`/`X`(배율), `v`, `*`, `HAAS<>COMB` 등.
노브 값 표기는 `units.render`(예: `"%f dB"`)에 값 대입.

### 5.4 `designation` (특수 역할 포트 — 있으면 일반 노브로 그리지 말 것)
- `lv2core#enabled` → 이펙터 **바이패스/인에이블** 토글. 노드 헤더의 ON/OFF로 승격 권장.
- `time#beatsPerMinute` / `parameters#*`(attack/decay/sustain/release/cutoffFrequency/resonance/frequency/waveform/wetDryRatio/pulseWidth) → 호스트가 의미를 아는 표준 파라미터. 목업에선 일반 노브로 둬도 되나 라벨 일관성에 활용 가능.

---

## 6. `gui` 객체 (스킨 힌트 — 선택적)

목업을 "제네릭 노드 박스"로 가도 되지만, 실제 느낌을 내려면 일부 필드가 유용:

| 필드 | 용도 |
|------|------|
| `brand` / `label` | 카드 브랜딩 |
| `color` | 페달 대표색 |
| `knob` | 노브 스타일 키 |
| `model` / `panel` | 패널 레이아웃 힌트 |
| `screenshot` / `thumbnail` | 페달 썸네일 **파일명**(실제 이미지는 파이에 있음 — 필요 시 별도 동기화) |
| `ports` / `monitoredOutputs` | modgui의 포트 배치·모니터 대상 |
| `iconTemplate`/`stylesheet`/`javascript`/`documentation` | **덤프에서 제외**(마커만). 목업엔 불필요. |

---

## 7. 설치된 이펙터 전체 목록 (72개, 카테고리→이름 정렬)

| # | 이펙터 | 브랜드 | 카테고리 | 오디오 in/out | 컨트롤 | MIDI in/out | CV | 프리셋 |
|--:|--------|--------|----------|:-------------:|:------:|:-----------:|:--:|:------:|
| 1 | ADClip7 | Hannes Braun | (uncategorized) | 2/2 | 4 | – | – | – |
| 2 | Audio to CV | MOD | ControlVoltage | 1/0 | 3 | – | 1 | – |
| 3 | AudioToCV Pitch | MOD/DISTRHO | ControlVoltage | 1/0 | 5 | – | 2 | 1 |
| 4 | Bollie Delay | Bollie | Delay | 2/2 | 15 | – | – | 1 |
| 5 | floaty | remaincalm.org | Delay | 1/1 | 6 | – | – | 6 |
| 6 | Bitta | OpenAV | Distortion | 1/1 | 3 | – | – | 1 |
| 7 | bluesbreaker | brummer | Distortion | 1/1 | 4 | – | – | – |
| 8 | ChowCentaur | chowdsp | Distortion | 1/1 | 7 | – | – | 1 |
| 9 | GxColorSoundTonebender | Guitarix | Distortion | 1/1 | 3 | – | – | 1 |
| 10 | abGate | A. Bruzas | Dynamics / Gate | 1/1 | 6 | – | – | 1 |
| 11 | Compressor Advanced | MOD | Dynamics | 2/2 | 6 | – | – | – |
| 12 | GxCompressor | Guitarix team | Dynamics / Compressor | 1/1 | 5 | – | – | 1 |
| 13 | GxExpander | Guitarix team | Dynamics / Expander | 1/1 | 5 | – | – | 1 |
| 14 | GxMultiBandCompressor | Guitarix team | Dynamics / Compressor | 1/1 | 34 | – | – | 1 |
| 15 | GxSlowGear | Guitarix | Dynamics / Gate | 1/1 | 3 | – | – | 1 |
| 16 | Harmonic Exciter | brummer | Dynamics | 1/1 | 5 | – | – | – |
| 17 | 3 Band EQ | DISTRHO | Filter / Equaliser | 2/2 | 6 | – | – | 2 |
| 18 | BandPassFilter | MOD | Filter | 1/1 | 3 | – | – | 1 |
| 19 | Capacitor2 | Hannes Braun | Filter | 2/2 | 4 | – | – | – |
| 20 | CrossOver 2 | MOD | Filter | 1/2 | 4 | – | – | 1 |
| 21 | CrossOver 3 | MOD | Filter | 1/3 | 6 | – | – | 1 |
| 22 | GxQuack | Guitarix | Filter | 1/1 | 8 | – | – | 1 |
| 23 | mud | remaincalm.org | Filter | 1/1 | 3 | – | – | 6 |
| 24 | amsynth | Dowell | Generator / Instrument | 0/2 | 41 | 1/0 | – | 27 |
| 25 | DIE Fluid Synth | DISTRHO | Generator / Instrument | 0/2 | 13 | 1/0 | – | – |
| 26 | Fluid Guitars | FluidGM | Generator / Instrument | 0/2 | 2 | 1/0 | – | 1 |
| 27 | Fluid Organs | FluidGM | Generator / Instrument | 0/2 | 2 | 1/0 | – | 1 |
| 28 | Fluid SynthLeads | FluidGM | Generator / Instrument | 0/2 | 2 | 1/0 | – | 1 |
| 29 | Kars | DISTRHO | Generator / Instrument | 0/1 | 3 | 1/0 | – | 1 |
| 30 | Nekobi | DISTRHO | Generator / Instrument | 0/1 | 9 | 1/0 | – | 1 |
| 31 | MIDI Step Sequencer8x8 | x42 | MIDI | 0/0 | 79 | 0/1 | – | 1 |
| 32 | C* PhaserII - Mono phaser modulated by a Lorenz fractal | CAPS | Modulator / Phaser | 1/1 | 5 | – | – | 1 |
| 33 | GxFlanger | Guitarix team | Modulator / Flanger | 1/1 | 6 | – | – | 1 |
| 34 | GxTremolo | Guitarix team | Modulator | 1/1 | 4 | – | – | 1 |
| 35 | GxTubeVibrato | Guitarix team | Modulator | 1/1 | 4 | – | – | 1 |
| 36 | the infamous power cut | infamous | Modulator | 1/1 | 3 | – | – | – |
| 37 | Aether | Dougal Stewart | Reverb | 2/2 | 47 | – | – | – |
| 38 | C* Plate - Versatile plate reverb | CAPS | Reverb | 1/2 | 4 | – | – | 1 |
| 39 | Convolution Loader | MOD | Reverb | 2/2 | 6 | – | – | 1 |
| 40 | Dragonfly Early Reflections | Dragonfly | Reverb | 2/2 | 7 | – | – | 1 |
| 41 | Dragonfly Hall Reverb | Dragonfly | Reverb | 2/2 | 18 | – | – | 25 |
| 42 | Dragonfly Plate Reverb | Dragonfly | Reverb | 2/2 | 9 | – | – | 8 |
| 43 | Dragonfly Room Reverb | Dragonfly | Reverb | 2/2 | 17 | – | – | 25 |
| 44 | StarChild | Airwindows | Reverb | 2/2 | 3 | – | – | – |
| 45 | x42 - IR Convolver Mono | x42 | Reverb | 1/1 | 3 | – | – | 1 |
| 46 | x42 - IR Convolver Stereo | x42 | Reverb | 2/2 | 3 | – | – | 1 |
| 47 | AIDA-X | Aida DSP | Simulator | 1/1 | 19 | – | – | – |
| 48 | Cabinet Loader | MOD | Simulator | 1/1 | 2 | – | – | – |
| 49 | GxRedeye Vibro Chump | Guitarix | Simulator | 1/1 | 8 | – | – | 1 |
| 50 | IR loader cabsim | MOD | Simulator | 1/1 | 1 | – | – | – |
| 51 | Neural Amp Modeler | Mike Oliphant | Simulator | 1/1 | 3 | – | – | – |
| 52 | C* Wider - Stereo image Synthesis | CAPS | Spatial | 1/2 | 2 | – | – | 1 |
| 53 | MDA Stereo | MDA | Spatial | 2/2 | 5 | – | – | 1 |
| 54 | 2Voices | MOD | Spectral | 1/2 | 5 | – | – | 1 |
| 55 | Autotune | x42 | Spectral / Pitch Shifter | 1/1 | 20 | 1/0 | – | 1 |
| 56 | Capo | MOD | Spectral | 1/1 | 3 | – | – | 1 |
| 57 | Harmonizer | MOD | Spectral | 1/2 | 8 | – | – | 1 |
| 58 | MDA VocInput | MDA | Spectral | 2/2 | 5 | – | – | 1 |
| 59 | TAP Fractal Doubler | TAP | Spectral | 2/2 | 8 | – | – | 1 |
| 60 | ALO |  | Utility | 2/2 | 14 | 1/0 | – | – |
| 61 | Audio File | falkTX | Utility | 0/2 | 5 | – | – | – |
| 62 | C* Click - Metronome | CAPS | Utility | 0/1 | 4 | – | – | 1 |
| 63 | C* Noisegate - Attenuate noise resident in silence | CAPS | Utility | 1/1 | 4 | – | – | 2 |
| 64 | Gain | MOD | Utility | 1/1 | 1 | – | – | 1 |
| 65 | Gain 2x2 | MOD | Utility | 2/2 | 1 | – | – | 1 |
| 66 | Instrument Tuner | x42 | Utility / Analyser | 1/1 | 9 | – | – | – |
| 67 | Level Meter | x42 | Utility | 1/0 | 1 | – | – | – |
| 68 | MIDI File | falkTX | Utility | 0/0 | 4 | 0/1 | – | – |
| 69 | Record-Mono | brummer | Utility | 1/1 | 2 | – | – | – |
| 70 | Record-Quad | brummer | Utility | 4/4 | 2 | – | – | – |
| 71 | Record-Stereo | brummer | Utility | 2/2 | 2 | – | – | – |
| 72 | Spectrum Analyzer | x42 | Utility | 1/0 | 1 | – | – | – |

### 카테고리 분포

| 카테고리 | 개수 |
|----------|-----:|
| Utility | 13 |
| Reverb | 10 |
| Generator | 7 |
| Filter | 7 |
| Dynamics | 7 |
| Spectral | 6 |
| Simulator | 5 |
| Modulator | 5 |
| Distortion | 4 |
| Spatial | 2 |
| ControlVoltage | 2 |
| Delay | 2 |
| MIDI | 1 |
| (uncategorized) | 1 |

---

## 8. 목업 → 이식 시 주의(이 덤프에 **없는** 것)

- **현재 페달보드 그래프/연결 상태**는 카탈로그가 아니므로 없음. 목업은 빈 캔버스에서 "이 72개를 끌어다 배치/배선"하는 흐름을 설계하면 된다. (실제 보드 상태는 이식 단계에서 앱의 그래프 모델과 연결.)
- **어드레싱(풋스위치/노브 → 파라미터 매핑)** 정보 없음 — 이식 단계 관심사.
- `gui` 템플릿/실제 스킨 이미지는 제외됨 — 목업은 제네릭 위젯으로 충분, 실제 스킨이 필요해지면 그때 동기화.
- 경로(`bundles`, screenshot 등)는 파이 기준이라 윈도에서 파일로 직접 못 연다.

## 9. 권장 목업 범위 (이식 난이도 낮추는 선)

1. **팔레트**: `categories`로 그룹, 이펙터 카드(이름/브랜드/오디오 in·out 핀 수).
2. **캔버스**: 노드 배치 + 오디오 포트끼리 배선(드래그). mono/stereo는 `audio.input/output` 개수로.
3. **노드 인스펙터**: `control.input`을 5.2 매핑대로 위젯 렌더 — 여기가 사용성 검증의 핵심.
4. (선택) MIDI/CV 포트 색 구분, `designation: enabled`를 노드 ON/OFF로.
