# 문자열 중앙화(i18n) — 설계 · 진행

> 테마 토큰화(색+폰트, `theme-tokenization-plan.md`)의 자매 작업. **같은 아키텍처를 문자열에 적용**:
> 언어별 정본 JSON 하나를 QML(`Tr` 컨텍스트 prop)·Python(`strings.py`)이 각자 읽음 → 색과 동일한
> "파이썬 이중소스" 함정 해소. 마지막 갱신: **2026-07-11 (설계 확정, 착수 전).**

## 0. 결정 (2026-07-11)

**동기(사용자):** mod/LV2 플러그인·노드 이름이 태생적으로 영어 → 화면에 알파벳이 불가피.
거기에 한국어 문장이 섞이면 시각적으로 안 예쁘고, 영·한을 한 화면에 둘 다 예쁘게 공존시키는
공수가 큼. **→ UI를 영어 1순위로 이주.** 결과적으로 화면이 시각적으로 일관됨 + 한국어 조사
보간 문제(`(으)로`)가 기본 영어에선 대부분 소멸.

- **D1. 기본 언어 = 영어(en).** `en.json`이 정본이자 런타임 기본. 현재 한국어 문자열 ~100개를
  UI에 맞는 **간결한 영어**로 이주(내가 번역, 사용자가 파이에서 육안 검수).
- **D2. `ko.json`은 유지(동결 스냅샷).** 현재 한국어를 키로 옮겨 보존 → 미래 토글·회귀 대비.
  단 **영어가 정본**이며 ko는 best-effort(신규 문자열이 en에만 있어도 됨 — 아래 fallback).
- **D3. 런타임 언어 전환 UI = 후순위.** 지금은 기본 en 고정(config/기본값). ⚙MENU 토글은 인프라가
  이미 양언어라 나중에 한 줄로 붙일 수 있음(로드맵 "열린 결정"과 합치).
- **D4. 파라미터는 `{0}`/`{name}` 스타일(파이썬 `str.format`).** QML도 Python 프로바이더의
  `Tr.trf(key, [args])`를 통해 **같은 파이썬 포맷 경로**로 치환(placeholder 규약 이원화 방지).
- **D5. 글리프(✕ + − ▸ ◆ ● ▾ ⌗ …)는 절대 키화 안 함.** 언어중립 심볼. 문장 안에 낀 ▸/✓/✗는
  그 문장 키의 값 일부로 함께 이주(문자열이 글리프만 있는지로 필터 불가 — recon §5.8).
- **D6. bucketAbbr(DRV/CMP…)는 `tokens.json`에 존치.** 이미 영어 약어·언어중립. 문자열 파일로
  안 옮김(세 번째 소스 만들지 않음). `theme.bucket_abbr()` 그대로.

## 1. 아키텍처 (theme와 대칭)

```
resources/strings/
  en.json        ← 정본(기본 런타임 언어)
  ko.json        ← 동결 스냅샷(toggle·회귀용)

strings.py       ← Python 절반. 현재 lang JSON 로드, tr(key)/trf(key,*a). Qt import 없음(순수).
strings_qml.py   ← I18nProvider(QObject): @pyqtSlot tr(key)->str, trf(key, QVariantList)->str.
qt_main.py       ← ctx.setContextProperty("Tr", i18n_provider)  (ThemeProvider 옆, 참조 보존)
```

- **로드/폴백:** `strings.py`가 `en.json`을 베이스로 읽고, 현재 lang이 ko면 `ko.json`을 그 위에
  덮음(키 누락 시 en으로 자연 폴백). 기본 lang="en".
- **missing 키:** 값 `⟨key⟩` 반환(색의 magenta 대응 — 화면에서 즉시 눈에 띔).
- **포맷:** 값에 `{}`/`{0}`/`{name}`. `strings.trf("toast.snapshot", name)` → `.format(name)`.
  QML: `Tr.trf("overview.hostBoards", [n])`. 무인자면 `tr(key)`.

## 2. 키 네이밍 (화면 도메인 dotted)

recon의 12 카테고리 기반. 예:
```
chrome.save / chrome.bank / chrome.edit / chrome.menu / chrome.engaged / chrome.bypass
overview.boardSwitch / overview.hostBoards / overview.current / overview.up / overview.down
snapshot.title / snapshot.saveAsNew / snapshot.count
bank.manager / bank.new / bank.active / bank.rename / bank.delete / bank.confirmDelete
menu.system / menu.masterVol / menu.timeSig / menu.shutdown / menu.reboot / menu.confirmShutdown
editor.pill.quick / editor.pill.adv / editor.io.in / editor.io.stereo / editor.exit / editor.reset
editor.canvasHint / editor.portHint.send / editor.portHint.recv
inspector.bypassed / inspector.active / value.on / value.off
naming.placeholder / naming.saveAs / naming.enterToSave
tuner.title / tap.title / tap.beatsPerBar
toast.snapshot / toast.addFail / toast.saved / toast.switchFail / toast.saveFail …
hmi.mode.navigate / hmi.mode.stomp / hmi.mode.bank / hmi.mode.tap / hmi.current
```

## 3. 함정 해소 (recon §5)

- **§5.1 이중 심 필수** — QML+Python 양쪽 `tr`. 반영됨(§1).
- **§5.2 %-포맷/접합** — 접합(`"("+n+")"`)은 **단일 파라미터 키**로 합침(`overview.hostBoards`={0}).
- **§5.3 조사 보간** — 영어 기본이라 대부분 소멸. ko 값만 안전형(으)로 유지.
- **§5.4 dirty 마커** — `*`/`⇄`는 **키 밖에서 합성**(`tr("editor.save") + (dirty?" *":"")`).
- **§5.5 로직겸용 문자열** — editor_bridge:839~866 quick-reason(`(bool,reason)` 튜플)은 **키화 전
  소비처 확인**: 비교에 쓰이면 로직값 유지하고 표시 시점에만 tr. Editor 그룹에서 개별 검증.
- **§5.6 bucketAbbr** — D6대로 tokens에 존치.
- **§5.8 글리프** — D5대로 제외. 문장 내 글리프는 값에 포함.

## 4. 스케줄 (6 왕복 — 색/폰트와 같은 리듬)

**모든 왕복이 가시적 변화**(한→영). 각 검수 = "영어가 잘 읽히는가 + 안 깨졌는가".

1. **인프라 + 파일럿(top-bar/글로벌 크롬)** — `strings.py`·`strings_qml.py`·`en/ko.json` 신설,
   `Tr` 주입, main.qml 상단바 이주. **기제 전체(이중소스·파라미터·기본언어 로드·글리프 제외) Pi 검증.**
2. **오버뷰 허브 + 보드전환 + 뱅크매니저** (main.qml 중단).
3. **스냅샷 + save-as/네이밍 + tap-tempo + tuner** (main.qml 나머지 오버레이).
4. **메뉴/시스템/config** (main.qml leaf + qtview 전원 라벨).
5. **에디터 QML** (PedalboardEditorView pills·팔레트·캔버스·다이얼로그·인스펙터 +
   ControlWidget/PatchPicker/MonitorWidget).
6. **Python 토스트/상태** (editor_bridge 27 + presenter 9 + qtview 오버뷰/모드/상태 힌트).

각 왕복: 오프디바이스 컴파일·잔여리터럴 grep 클린 → 커밋 아님(그룹 끝 커밋) → Pi 재시작 육안 →
"이상무" 확인 후 다음. 색/폰트처럼 그룹 완료 시 커밋, 전체 완료 시 master 머지 완주.

## 5. 진행 — ✅ 전체 완료 (2026-07-12, 6그룹 Pi 육안검증·master 머지)

- [x] 1. 인프라 + top-bar 파일럿 (`9273691`) — strings.py·strings_qml.py·en/ko.json·Tr 주입
- [x] 2. 오버뷰/보드전환/뱅크 (`71db936`) — common.*·action.* 공유키 신설
- [x] 3. 스냅샷/네이밍/tap/tuner/FOCUS (`08455fc`) — main.qml 대부분
- [x] 4. 메뉴/시스템/config (`29f7e30`) — **main.qml 한글 리터럴 0 달성**
- [x] 5. 에디터 QML (`315d369`) — PedalboardEditorView·ControlWidget·PatchPicker
- [x] 6. Python 토스트/상태 (`06c47d2`) — editor_bridge·qtview·presenter

**결과:** 참조 키 **173개**, en=ko **완전 동수**, 누락(⟨key⟩) 0. 기본 언어 영어. 스킵(의도):
editor_bridge 죽은 quick-reason 4개(표시·비교 안 됨), mono/stereo·quick/advanced·화면상태·
노드 id "IN"/"OUT"·LED상수(로직), 라디얼 포트라벨·노드라벨 IN/OUT/GUITAR/STEREO(영어·로직인접,
번역가치 0). 런타임 언어전환 UI는 후순위(인프라는 `Tr.setLang`/`strings.set_lang`로 준비됨).
