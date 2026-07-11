# Synapse UI 색상·타이포 집중화 설계

> 로드맵 ④ i18n/테마 항목의 **테마 토큰화** 절반(문자열 i18n은 별건). 색상이 QML과 Python
> **양쪽**에 존재하므로 단일 소스는 Python 측까지 덮어야 한다 — 이 문서의 핵심 제약.
>
> 작성 2026-07-11. 근거 = 7파일 병렬 감사(멀티에이전트) + 적대적 검증. 대상 파일:
> `qml/main.qml`, `qml/PedalboardEditorView.qml`, `qml/ControlWidget.qml`,
> `qml/MonitorWidget.qml`, `qml/PatchPicker.qml`, `editor_bridge.py`, `qtview.py`.

---

## 0. 세 줄 요약

1. **색**: 원시 리터럴 ~80종 → 의미로 접으면 **~32 토큰**. 병목은 개수가 아니라 같은 hue가
   **7군데 독립 재선언**된 5중 파편화. `main.qml`에 12토큰 씨앗이 있으나 형제 QML·Python이 못 봄.
2. **폰트**: `family`는 이미 단일 소스(`uiFont` 주입). **크기(27종 인라인 정수)·굵기(전무)가 미해결.**
3. **집중화**: 언어중립 정본 `theme/tokens.json` 하나를 QML과 Python이 각자 읽는다.
   폰트는 크기-스케일 위에 **역할 토큰(`Type.button`/`Type.title`/…)을 한 겹** 얹어
   "버튼 폰트만 키우기"를 한 값 수정으로 만든다.

---

## 0.5 결정 확정 (2026-07-11)

| 결정 | 선택 | 실행 함의 |
|---|---|---|
| **근접중복 접기** | **공격적으로 접기** | `surface.pickElev`→`elevated`, `state.dangerMeter`→`accent.midi`, `surface.bankPane`→`bg.screen`, `border.pickerDefault`→`border.default` 등 눈으로 구분 힘든 쌍은 통합. 목표 ~28 토큰. |
| **accent.blue 3역할** | **역할별 분리** | 한 토큰 아님 → `port.audio`·`bucket.eq`·`ui.selection` 3토큰. **초기값은 셋 다 `#3b6fe0`(현행)** → 시각변화 0, 독립 튜닝만 개통. |
| **폰트 범위** | **스케일 합리화 포함 (Phase 4)** | §2 표대로 27종 px→9스케일 스냅. **실제 시각변화 발생** → 800×480 화면별 Pi 육안확인 필수(19→22, 17→18 리플로우 주의). |

---

## 1. 색상 인벤토리

원시 리터럴 **~80종**(6자리 hex + 8자리 ARGB `#1f5fd0a0` + `rgba()` 문자열, `transparent` 제외).
상당수가 (a) 기존 토큰 값을 raw로 재기입한 **완전 중복**, (b) 같은 hue의 **alpha 파생**,
(c) 7파일이 **각자 재선언**. 의미로 접으면 **~32 실토큰**.

### 클러스터별 제안 토큰

**Background**

| 토큰 | hex | 사용처 |
|---|---|---|
| `bg.screen` | `#0e1118` | Window 바탕, cScreen |
| `bg.graph` | `#0a0d13` | QUICK 캔버스/라우팅 그래프 |
| `bg.graphWarm` | `#140f09` | ADVANCED 캔버스(앰버 틴트, 의도적 웜톤) |

**Surface** (가장 큰 클러스터 — 어두운 blue-grey 계조)

| 토큰 | hex | 사용처 |
|---|---|---|
| `surface.panel` | `#141925` | cPanel — 사이드패널/레일/다이얼로그 |
| `surface.elevated` | `#1d2433` | cElev — 선택행/입력필드/토스트/enum |
| `surface.card` | `#161b26` | 노드카드·리스트델리게이트 **(7회+ raw 재등장, 무별칭 → 최우선 토큰화)** |
| `surface.inset` | `#10212a` | IO노드·네이밍필드·볼륨박스 |
| `surface.control` | `#1b2230` | 중립버튼 idle·nav·시스템 **(전역 최다 사용)** |
| `surface.controlAlt` | `#141821` | 뱅크상세 행·카탈로그 행 |
| `surface.bypassed` | `#13161d` | 이펙트노드 OFF(바이패스) |
| `surface.track` | `#222a38` | MonitorWidget 미터/게이지 트랙 |
| `surface.pickElev` | `#171c26` | PatchPicker 기본값 *(elevated 근사중복 — §접기결정)* |
| `surface.bankPane` | `#10141d` | 뱅크매니저 좌/우 패널 *(bg 근접 — §접기결정)* |

**Border**

| 토큰 | hex | 사용처 |
|---|---|---|
| `border.default` | `#2c3648` | cBorder — 기본 외곽선 |
| `border.subtle` | `#1b2230` | editor 디바이더·term-chip **(surface.control과 동일 hex — 역할분리 주석 필수)** |
| `border.divider` | `#232b3a` | 헤더 구분선(hr) |
| `border.io` | `#2a4a44` | IN/OUT 미터노드 테두리 |
| `border.pickerDefault` | `#2a3344` | PatchPicker 기본 *(default 근사 — §접기결정)* |

**Text**

| 토큰 | hex | 사용처 |
|---|---|---|
| `text.primary` | `#e8edf4` | cText — 본문/노드명/입력텍스트 |
| `text.onLight` | `#cfd6e2` | 밝은버튼 캡션·term-chip |
| `text.secondary` | `#7e8694` | cMuted — 보조/라벨 **(l.205 pressed-border로도 인라인 — 접을 때 주의)** |
| `text.tertiary` | `#5a6270` | cDim — 카운트/메타/플레이스홀더 |
| `text.disabled` | `#3a4252` | Pill dim 라벨·bypass 포트닷 |
| `text.mutedAlt` | `#9aa3b2` | 토글 OFF 라벨·Utility 버킷 *(cMuted와 다른 값)* |
| `text.onGraph` | `#6f8a82` | 이펙트노드 서브라벨 |

**Accent (브랜드 hue)**

| 토큰 | hex | 사용처 |
|---|---|---|
| `accent.green` | `#5fd0a0` | cGreen — 1차 액센트/ACTIVE/IN단자 **(7파일 전체 등장, 단일화 최대효과)** |
| `accent.blue` | `#3b6fe0` | AUDIO 포트/선택테두리/blue버튼 **(3역할 공유 — §역할분리결정)** |
| `accent.purple` | `#b58af0` | cPurple — SNAP/스냅샷/enum |
| `accent.amber` | `#d99a4e` | cAmber — ADVANCED/OUT/dirty |
| `accent.midi` | `#e8694a` | MIDI 포트/케이블·delete danger |
| `accent.blueBright` | `#9cc2ff` | blue버튼 pressed border+캡션 |
| `accent.purpleBright` | `#cdb6f0` | purple버튼 pressed border+캡션 |
| `accent.pale` | `#cfe0ff` | 타게팅힌트·radial 라벨 |
| `accent.cyan` | `#78c8ff` | HW-edge 활성 글로우 |

**State**

| 토큰 | hex | 사용처 |
|---|---|---|
| `state.danger` | `#e6402e` | cRed — 튜너 far-off·STOMP bypass LED |
| `state.dangerMeter` | `#e6724a` | IO 미터 clip(>0.92) *(accent.midi 근접 — §접기결정)* |
| `state.warn` | `#d99a4e` | = accent.amber (튜너 slightly-off) — hue 통합, 역할 alias |
| `state.feedback` | `#e0a458` | FB 태그 테두리·피드백 케이블 |
| `state.selected` | `#eaf2ff` | **어댑터 선택 하이라이트 (editor_bridge.py:1101, Python 전용 — 감사 1차 누락, 검증이 발견)** |
| clip LED lit | `#e2524a` / border `#ff7a70` | MonitorWidget clip 점등 |
| clip LED idle | `#3a2222` / border `#5a2a2a` | clip 소등 |
| danger 버튼 triad | fill `#2a1416` · border `#7a3b3b` · text `#ffb3b3` | 삭제/안전종료 |
| delete glyph | `#ff8a6a` · bg `#3a1f1a` | 케이블삭제/radial취소 |

**Overlay / alpha 파생** — 별도 토큰 아님, `Theme.alpha()` 헬퍼로

| 리터럴 | 정체 | 처리 |
|---|---|---|
| `#000000` @0.55~0.62, `#e60a0d14` | 모달 스크림 | `overlay.scrim` (색+opacity) |
| `#1f5fd0a0` / `#2e5fd0a0` / `rgba(95,208,160,0.12)` | accent.green의 alpha 변주 | `Theme.alpha(accent.green, x)` |

**묶음 토큰 (개별 아님)**

- **mode-FX 파티클** (PedalboardEditorView 로컬): `fx.hot[]` = `#fff4e0 #ffd49a #ff9a4e`,
  `fx.cool[]` = `#eafff5 #bdf0d8 #8fe0bd`. 애니메이션 팔레트 배열 1쌍.
- **어댑터 칩 triad** (editor_bridge.py): 한 hue의 3톤 명도패밀리 `{bg, accent, fg}`.
  ⚠️ **IN 칩 bg(`#1f2636`, blue-grey)와 OUT 칩 bg(`#2a221a`, warm)는 서로 다른 hex** —
  하나로 접으면 IN 칩이 조용히 리컬러됨(검증 발견). `chip.in.*` / `chip.out.*` 분리 유지.

### 접어야 할 완전 중복 (같은 hex, 다른 곳 raw 재기입)

`#7e8694`(cMuted→pressed-border), `#2c3648`(cBorder→3파일), `#1d2433`(cElev→main 2곳),
`#0e1118`(cScreen→editor 노브썸), `#3b6fe0`(cBlue→editor), `#5fd0a0`(cGreen→editor·bridge·qtview 다수).

---

## 2. 폰트/타입 위계

`font.family`는 **이미 전면 중앙화**(`uiFont` 컨텍스트 prop). 미해결은 **크기·굵기**.
굵기(`weight`/`bold`/`italic`)는 **앱 전체 0건** — 전부 Regular. 크기는 인라인 정수.

### 실재 픽셀 크기 (~27종)

`8, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23, 24, 26, 28, 30, 32, 38, 40, 44, 52, 56, 60, 96, 190, 200`

같은 크기가 여러 요소에, 같은 요소류가 여러 크기에 — **현재 위계는 명목상일 뿐 요소마다 즉흥 배정**.

### 2계층 구조 — 크기 스케일 + 역할 토큰 (사용자 요구 정면 대응)

> **왜 2계층인가**: 순수 크기-tier만 두면 "버튼"은 tier가 아니다 — 버튼 캡션이
> 헤더 22px·토글 15px로 흩어져 "버튼 폰트만 키우기"가 한 값이 안 된다. `label` tier 하나가
> 컨트롤명·모드표시·미터포트명·토글본문 4요소를 삼켜 독립 조정 불가. **그래서 역할 토큰을 얹는다.**

**하층 — 크기 스케일** (raw 크기 정본, 직접 사용 안 함)

| 스케일 | px | 흡수 대상 |
|---|---|---|
| `scale.micro` | 11 | 8·11·12 |
| `scale.caption` | 13 | 12·13 |
| `scale.label` | 15 | 14·15·16 |
| `scale.body` | 18 | 17·18 |
| `scale.heading` | 22 | 19·20·22·23 |
| `scale.title` | 28 | 24·26·28·30·32 |
| `scale.display` | 44 | 38·40·44·52·56·60 |
| `scale.hero` | 96 | 96 |
| `scale.heroNumeric` | 200 | 190·200 |

**상층 — 역할 토큰** (사용처가 실제로 바인딩하는 것 = `font: Type.button`)

| 역할 토큰 | 기본 스케일 | 굵기 | 대표 요소 |
|---|---|---|---|
| `Type.micro` | micro | Normal | 포트 채널문자(L/R), HW 서브라벨 |
| `Type.caption` | caption | Normal | 노드 서브라벨, 칩 텍스트, 메타 |
| `Type.smallLabel` | label | Normal | 미터 포트명, 작은 라벨류 |
| `Type.controlName` | label | Normal | 컨트롤명 |
| `Type.toggle` | label | Normal | 토글 본문 |
| `Type.body` | body | Normal | 리스트 행, 다이얼로그 본문, 노드명 |
| `Type.button` | heading | Normal | **헤더/액션 버튼 캡션 (한 노브로 조정)** |
| `Type.overlayTitle` | heading | Normal | 오버레이 타이틀, 토스트 |
| `Type.title` | title | Normal | 포커스 카드명, 스크린 서브타이틀 |
| `Type.display` | display | Normal | 스크린 타이틀(TAP/TUNER), 워드마크 |
| `Type.hero` | hero | Normal | 오버뷰 보드명(glance) |
| `Type.heroNumeric` | heroNumeric | Normal | 탭템포 BPM·튜너 노트명 |

- **개별 조정 = 한 값**: 버튼만 키우기 → `Type.button.size` (또는 스케일 참조 교체).
  라벨만 굵게 → `Type.smallLabel.weight = DemiBold`. 역할끼리 독립.
- **굵기 축 신설**: 전 역할 초기값 `Normal` → 도입 시 시각 변화 0.
- 역할 여러 개가 같은 스케일을 참조해도(예: controlName·toggle·smallLabel = label) **역할별로
  분리 조정 가능** — 이게 순수 크기-tier와의 결정적 차이.

### family 예외 (글리프)

`✕ > + − ⌗ ＋` 등 **글리프 전용 Text 8곳**(main l.437/518/590/727/749/844/865,
editor l.273/543/642/694/934/1034)은 의도적으로 `font.family`를 비워 시스템 폰트로 기호 렌더.
**`Type.glyph` 역할은 family 미지정** — 통짜 `font` 값타입을 주입하면 `uiFont`가 끼어들어 기호가
깨진다(검증 지적). glyph는 size만 토큰화, family는 비운 채 유지.

---

## 3. 현재 집중화 상태 (정직한 베이스라인)

| 파일 | 색상 | 폰트 |
|---|---|---|
| `main.qml` | Window 레벨 `readonly property color` **12토큰**(l.16–27) + **45+ 인라인**. 여러 인라인이 토큰 값 복제. | family=`uiFont`. size ~55 인라인. weight 없음 |
| `PedalboardEditorView.qml` | 로컬 별칭 **12토큰**(이름이 main과 다름: `cOrange`/`cBlue`). mode-FX·글로우·`#161b26`(7회) 대량 인라인 | 〃 |
| `ControlWidget.qml` | 로컬 별칭 **5토큰** + 토글/on-accent/`#9aa3b2` 인라인 | 〃 |
| `MonitorWidget.qml` | 로컬 별칭 **4토큰** + clip LED 4색 인라인 | 〃 |
| `PatchPicker.qml` | **호스트 주입** prop 4개 + `fontFamily`. 기본값 하드코딩, 스크림/구분선 인라인 | family=주입. size 인라인 |
| `editor_bridge.py` | `BUCKET`·`PORTCOL` **2 dict**가 유일 추상화. 나머지 산재. **모든 색을 QML에 data 전송** | 없음(설계상 QML 소유) |
| `qtview.py` | 모듈레벨 `_LED_*` **4상수**(l.70). 케이블/LED 색만 payload로 나감 | 없음 |

**총평**: family는 단일 소스. 색은 **5중 파편화**(QML 4파일 각자 재선언 + PatchPicker/ControlWidget 주입 +
Python 2파일 리터럴). 같은 hue 7군데 독립이 근본 병목. **폰트 크기·굵기 추상화 0.**

---

## 4. 집중화 설계

### 4.1 원칙 — QML 싱글톤 하나로 안 끝난다

`Theme.qml`(pragma Singleton)은 형제 QML 문제만 푼다. **Python은 QML 싱글톤을 import 못 한다.**
editor_bridge/qtview가 색 hex를 **문자열 payload로 QML에 밀어넣어** 케이블·노드·LED를 그리므로,
QML만 토큰화하면 그래프가 테마를 우회한다. → **정본은 언어중립 데이터 파일**, QML·Python이 각자 읽는다.

```
theme/tokens.json         ← 유일한 정본 (색 + 타입 스케일 + 역할)
   ├─ (Python) theme.py   : json 로드 → C["accent.green"], bucket_color() …
   └─ (QML)  Theme        : 컨텍스트 prop 주입 (기존 uiFont와 동형)
```

### 4.2 `tokens.json` (정본 스케치)

```json
{
  "color": {
    "bg.screen": "#0e1118", "surface.panel": "#141925", "surface.card": "#161b26",
    "surface.control": "#1b2230", "border.default": "#2c3648",
    "text.primary": "#e8edf4", "text.secondary": "#7e8694", "text.tertiary": "#5a6270",
    "accent.green": "#5fd0a0", "accent.blue": "#3b6fe0", "accent.purple": "#b58af0",
    "accent.amber": "#d99a4e", "accent.midi": "#e8694a",
    "state.danger": "#e6402e", "state.feedback": "#e0a458", "state.selected": "#eaf2ff",
    "led.off": "#2a3140"
    /* …§1의 ~32 토큰 전량 */
  },
  "bucket": { "Drive": "accent.amber", "Comp": "accent.green", "EQ": "accent.blue" },
  "bucketAbbr": { "Drive": "DRV", "Comp": "CMP", "EQ": "EQ" },
  "port": { "audio": "accent.blue", "midi": "accent.midi", "cv": "accent.purple" },
  "scale": { "micro":11,"caption":13,"label":15,"body":18,"heading":22,
             "title":28,"display":44,"hero":96,"heroNumeric":200 },
  "type": {
    "button":     { "scale": "heading", "weight": "Normal" },
    "title":      { "scale": "title",   "weight": "Normal" },
    "smallLabel": { "scale": "label",   "weight": "Normal" }
    /* …§2 역할 전량. glyph는 family 미지정 플래그 */
  }
}
```

> `bucket`/`port`가 hex가 아니라 **토큰 이름을 가리킨다** — EQ색과 selection-blue가 지금 우연히
> 같은 값인데, 정본에서 둘 다 `accent.blue`를 참조하면 통합·갈라치기를 한 곳에서 결정할 수 있다.
> ⚠️ **`bucketAbbr` 별도 유지** — 현행 `BUCKET` dict는 `(색, 3글자약어)` 겸용이라(editor_bridge.py:105
> `bcol`, :109 `abbr`), 색만 토큰화하고 약어를 버리면 노드 배지가 깨진다(검증 지적).

### 4.3 Python 측 — `theme.py`

```python
import json, pathlib
_raw = json.loads((pathlib.Path(__file__).parent / "theme/tokens.json").read_text())
C = _raw["color"]                                   # C["accent.green"] — 점표기 그대로
def bucket_color(b): return C[_raw["bucket"].get(b, "text.secondary")]
def bucket_abbr(b):  return _raw["bucketAbbr"].get(b, "?")
def port_color(t):   return C[_raw["port"][t]]
```

- `editor_bridge.py`: `BUCKET`/`PORTCOL` dict 삭제 → `bucket_color()`·`bucket_abbr()`·`port_color()`.
  산재 리터럴(`#2c3648` 바이패스, `#eaf2ff` 선택, 칩 triad, 피드백 amber)을 `C["…"]`로 치환.
  **state 삼항은 리터럴만 토큰 참조로, 분기 구조는 유지** (`C["border.default"] if bypass else C["accent.blue"]`).
- `qtview.py`: `_LED_* = "#…"` 4상수 → `_LED_BLUE = C["accent.blue"]` 등. payload hex가 정본과 동일 소스로.

Python은 여전히 **hex 문자열을 data로 QML에 보낸다**(구조 불변, 저위험). 출처만 정본으로 바뀔 뿐.
단, 지금 구조는 **송신 시점에 hex를 baking**하므로 런타임 라이브 테마 전환은 막힌다 — 정적 테마엔 무관,
라이브 스왑이 요구되면 그때 재설계(현재 요구 아님).

### 4.4 QML 측 — 컨텍스트 프로퍼티 (권장)

기존 `uiFont`/`view` 주입과 동형이라 마찰 최소. 기동 시:

```python
ctx.setContextProperty("Theme", ThemeProvider(_raw))   # qt_main.py, uiFont 옆 한 줄
```

QML 사용: `color: Theme.color("accent.green")` 또는 `font: Theme.type("button")`.
정본은 여전히 `tokens.json` 하나. (자동완성이 아쉬우면 후속으로 `tokens.json → qml/Theme.qml`
codegen 싱글톤을 덧댈 수 있으나, 1차는 컨텍스트 prop로 충분.)

### 4.5 역할별 개별 폰트 오버라이드 (요구 실현)

`Type`를 역할마다 **`font` 값타입**으로 노출, 사용처는 `font: Theme.type("button")` 한 줄
(family·size·weight 동시 적용). **개별 조정** = `tokens.json`의 `type.button.scale` 또는
`type.smallLabel.weight` 한 값. 역할끼리 독립 → "각 위계 폰트 따로 설정"의 실현.
glyph 역할만 family 미지정.

### 4.6 state·alpha·데이터구동 색

- **state 삼항**: 토큰은 값만, 분기는 호출부 유지. 버튼 패밀리는 idle/active/border/borderActive/caption
  5필드 sub-object(`Theme.btn.blue.fillActive`). blue/purple/neutral/danger/affirm 5패밀리.
- **alpha 파생**: 새 색 아님 → `Theme.alpha(Theme.color("accent.green"), 0.12)`. Python도 동일 헬퍼.
- **Canvas 2D 문자열**: editor grid/mode-FX가 색을 JS 문자열로 읽음 → Theme 값이 hex 문자열로 넘어가야 안전.
- **데이터구동 색**(`modelData.color/.led`, `flyColor`): QML 토큰화 불가 → §4.3에서 Python이 정본 참조로 자동 해결.

---

## 5. 실행 계획 (저위험 순서)

**Phase 0 — 정본 스캐폴딩 (사용자 결정 지점)**
`tokens.json` 초안 + §접기결정 확정. **기계적이지 않은 판단**: (a) 근접중복 접기/유지
(`pickElev`↔`elevated`, `dangerMeter`↔`midi`, `bankPane`↔`bg`, `pickerDefault`↔`default`);
(b) `accent.blue` 3역할(포트·버킷·선택) 통합 vs 분리; (c) 폰트 스케일 합리화 범위(§Phase 4).

**Phase 1 — 인프라 배선 (저위험)**
`theme.py` + Theme 컨텍스트 prop 주입. **아무 것도 치환 안 함** — 배선만. 앱 정상 기동 = Pi 1회 확인.

**Phase 2 — 색 치환 (멀티에이전트 기계적 스윕, 파일 독립)**
QML 4파일 인라인 hex → `Theme.*`, 로컬 별칭 삭제, 주입 prop → Theme 직접. Python 2파일 dict/상수 →
정본 참조. **치환 값이 전부 기존과 동일 hex → 시각 회귀 이론상 0.** 파일별 grep 잔여검사 + Pi 육안 1컷.
회귀 위험: `#7e8694` 이중역할, editor 별칭명 매핑(`cOrange`/`cBlue`), Canvas JS 문자열, IN/OUT 칩 bg 분리.

**Phase 3 — 폰트 역할 토큰 도입 (순수 indirection, 저위험)**
`scale`+`type` 정본 배선 후 각 요소 `font.pixelSize: N` → `font: Theme.type("역할")`.
**역할의 기본 스케일을 그 요소의 현재 px에 맞춰** 시각 no-op 유지. weight 전부 Normal. ~55개소 기계적.

**Phase 4 — 스케일 합리화 (결정+검증 필요, 선택)**
27종 px를 9 스케일로 스냅 — **여기서만 실제 시각 변화**. 800×480 리플로우/클리핑 위험, Pi 화면별 확인.
하고 싶을 때만. 없이도 "집중화"는 Phase 3에서 완성.

**멀티에이전트 적합도**: 기계적(분산 OK) = Phase 2 색치환·Phase 3 크기 indirection.
사람 결정 = Phase 0 접기/분리·Phase 4 스냅. 최고위험 = Phase 4(시각변화) ≫ Phase 2(값동일이나 이중역할·Canvas 함정) ≫ 1·3.

---

## 부록 — 검증이 잡은 정정 (재발 방지)

1. **`#eaf2ff`**(editor_bridge.py:1101, 어댑터 선택 하이라이트) — 감사 1차 누락 → `state.selected`로 편입.
2. **IN/OUT 칩 bg 상이** — IN `#1f2636`(blue-grey) vs OUT `#2a221a`(warm). 하나로 접으면 IN 리컬러 → `chip.in`/`chip.out` 분리.
3. **`BUCKET` 약어 유실 위험** — dict가 `(색, 약어)` 겸용 → `bucketAbbr` 별도 토큰으로 보존.
4. **역할 vs 크기-tier** — 순수 크기-tier는 "버튼 폰트만" 조정 불가 → 크기 스케일 위 역할 토큰 2계층으로 해결(§2).

## 참조
- [`qt-roadmap.md`](qt-roadmap.md) ④ i18n/테마 항목. [[synapse-roadmap]] 메모리.
- 감사 근거: 워크플로우 `color-font-centralization-audit`(2026-07-11, 9에이전트).
