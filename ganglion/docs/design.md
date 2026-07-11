# Ganglion 설계문서 (GECO1)

> 상태: **초안 / 하드웨어 소싱 중** (배선·설치 완료 예상 ≥ 2026-07-07)
> 대상 기기: **GECO1** — 데스크 미니 (pisound + rpi)
> 앱: **ganglion** — 헤드리스 인터페이스 (Qt 없음)
> 대비: GCaMP6s(본체) / synapse(터치스크린 앱)
> 갱신: 2026-07-04 — 시안 **2a**(상하 분할) 채택 + 실 1-bit 렌더/바이트 코스트 검증 반영.

이 문서는 코드 이전에 **정해야 할 설계 결정**을 모아 둔다. `[결정]`은 확정, `[열림]`은
사용자/시안 대기, `[조사]`는 리서치 결과. 인코더 UX 시안은 별도(사용자 준비).

---

## 0. 하드웨어 (확정 스펙)

| 요소 | 부품 | 인터페이스 | 비고 |
|---|---|---|---|
| 디스플레이 | Adafruit Monochrome **1.12" 128×128 OLED**, **SH1107**(=SSD1107 계열) | **I2C** (STEMMA QT) | 흑백 1bpp, 그레이스케일 없음 |
| 입력 ×2 | 로터리 **인코더 + 푸시스위치 + RGB LED** 통합 모듈 (Adafruit seesaw + NeoPixel) | **I2C** (seesaw) | 회전(상대)+누름+RGB 한 보드 |
| 오디오 | pisound HAT | — | 기존과 동일 |

> **7인치·풋스위치4·볼륨/exp 페달 없음.** GCaMP6s의 물리 I/O를 대부분 떼어낸 제약형 리그.

### I2C 주소 계획 `[열림]`
한 버스에 디스플레이 + 인코더 2개가 공존한다. 충돌 점검 필요:
- SH1107 디스플레이: `0x3C` 또는 `0x3D`
- seesaw 인코더: 기본 `0x36`, 두 번째는 주소 점퍼로 `0x37`(등)으로 분리
- pisound / RTC 등 기존 I2C 점유 주소 확인 → **설치 시 `i2cdetect -y 1`로 실측 후 확정**

---

## 1. 재사용 경계 `[결정]`

synapse는 seam(주입) 패턴으로 순수계층이 이미 분리돼 있다 (Qt·I2C 의존 0 확인 완료).
ganglion은 **synapse 코어를 0줄 수정**하고, 순수계층만 import 한다.

**IMPORT (공유, 포크 금지):**
`model.py` · `modepctrl.py`+`backend.py` · `monitorfeed.py` · `plugincatalog.py` ·
`scheduler.py` · `configs.py` · `taptempo.py` · `utils.py`

**재사용 안 함 (synapse 터치스크린 전용):**
`presenter.py`(52KB) · `qtview.py` · `qml/` · `hardware.py`의 `HardwareController`(풋스위치/LED 모양)

**ganglion 신규 (`ganglion/` 안에서만):** 얇은 컨트롤러 · 128×128 렌더러 · 인코더/RGB 하드웨어층 · 진입점.

> 공유 순수계층에 손대야 하는 변경은 `docs/ganglion-geco-logbook.md`(추적 채널)로 조율.

---

## 2. 디스플레이 성능 `[조사]` — 렌더링 아키텍처를 좌우하는 핵심

### 물리 한계 (측정 근거 기반)
- 프레임 크기: 128×128×1bpp = **2048 바이트/프레임**.
- **I2C 400kHz(fast mode):** 전체화면 **~10 fps(0/180° 방향)**, **~16 fps(90/270° 방향)**.
- **부분 갱신(1행 텍스트): ~5 ms.** ← 전체화면(60~100ms)보다 압도적으로 빠름.
- **I2C 1MHz 오버클럭(`dtparam=i2c_baudrate=1000000`):** ~2.5× 빨라지나 **SH1107 정격 초과 → 신뢰성 리스크**(글리치 시 폴백 필요).
- 참고: SPI 40MHz면 5~20ms지만 **이 보드는 I2C 전용(STEMMA QT)** — SPI 옵션 없음. 부드러운 애니메이션이 필수가 되면 SPI SH1107 보드로 교체해야 하는 아키텍처 제약.

### 방향 의존성의 이유
90/270°는 SH1107의 native page 구조에 프레임버퍼가 정렬돼 순차 쓰기가 가능, 0/180°는
column 단위로 흩어져 씀 → **디스플레이를 90° 회전 장착**하면 공짜로 16fps.

### 설계 결정
- `[결정]` **부분/더티-리전 렌더링을 기본으로.** 전체화면 재그리기는 "비싼 연산"으로 취급.
  매 틱 full redraw 금지 — 바뀐 영역만 push.
- `[결정]` **디스플레이 90° 회전 장착 전제** (16fps 확보). 시안도 세로/가로 방향 이걸 반영.
- `[결정]` **1bpp 흑백 UI 문법:** 그레이스케일 없음 → 볼드 라인아트·큰 텍스트·아이콘·반전(invert)
  블록으로 정보 표현. 안티에일리어싱 폰트 못 씀 → 비트맵 폰트.
- `[결정]` **폰트 = Silkscreen(본문 8/16/24/32) + Micro5(플로어 티어).** 실 1-bit 렌더로 검증:
  Silkscreen 전 티어 또렷. **Micro5는 @6/@8 뭉갬 → @10pt에서 legible**("5px" 폰트라 5px 글리프를
  내려면 10pt 래스터 필요). 시안의 "6px→6pt" 매핑은 우리 PIL/luma 경로에서 오류였음 → **Micro5@10 고정.**
  OFL 번들: `ganglion/assets/fonts/`.
- `[결정]` **실시간 요소 프레임 예산:** 작은 영역만 갱신하면 부분갱신으로 충분. 아래 코스트 모델로 정량 확인됨
  — 실시간 위젯은 화면의 좁은 밴드에 격리.

### 드라이버 선택 `[열림 → 조사]`
- **1순위: `luma.oled`** — Pillow(PIL) 네이티브 드로잉. 우리가 UI를 직접 그리는 방식에 가장 잘 맞음.
  설치 시 실제 sh1107 디바이스 지원 버전 확정 필요.
- **2순위: `adafruit-circuitpython-displayio-sh1107`** (+Blinka) — displayio 위젯 지향, 커스텀 드로잉엔 덜 편함.
- 결정 기준: 커스텀 UI + 부분갱신 제어권 → **luma.oled 우선**. 벤치 실측 후 확정.

### 측정: 바이트 코스트 모델 `[조사]` — `ganglion/i2c_cost.py`
SH1107은 **페이지=8px×128** 단위 저장(16 페이지행). 부분갱신 비용 = *(건드린 페이지행 수 × 폭)* + 명령 오버헤드.
시안 2a 화면을 실 1-bit로 렌더(`ganglion/design_screens.py`)하고 프레임 diff로 실측:

| 리프레시 이벤트 | 전송 | @400kHz | 성격 |
|---|---|---|---|
| 전체 재그리기 | 2192 B | 49ms → 20fps* | 화면 전환 시에만 |
| 노드 스크롤(스트립+밴드) | 1379 B | 31ms → 32fps | 이산 조작 |
| 스냅샷 전환 | 377 B | 8.5ms → 118fps | 저렴 |
| 마퀴 1스텝(이름 밴드) | 349 B | 7.8ms → 127fps | 저렴 |
| 튜너 바늘 1스텝 | 155 B | 3.5ms → 287fps | 저렴 |
| 노브 값 1개 | 37 B | 0.8ms → 1201fps | 무시 가능 |

*(전체 20fps는 와이어타임 상한 — 실측 10–16fps는 SW·방향 오버헤드 포함)*

- `[결정]` **핵심:** 비싼 건 화면 **전체가 바뀌는 순간**(전환·노드스크롤)뿐이고 이건 *이산 조작*. **마퀴·바늘·미터·노브
  같은 매 프레임 애니메이션은 한 페이지 밴드만 건드려 전부 저렴**(이전 "마퀴가 리스크" 판단은 코스트 모델로 반증됨).
- `[결정]` 규율: 정적 레이아웃은 표현력 마음껏 / 매 프레임 애니메이션은 **한 페이지 밴드에 격리** → 항상 두 자릿수 fps.

---

## 3. 입력 모델 `[결정]` — 시안 2a 채택

물리 입력: **로터리 2개(회전 상대델타) + 푸시 2개 + RGB LED 2개**. 시안 2a가 이걸 다음으로 확정:

- `[결정]` **상하 밴드 매핑:** 인코더가 화면 좌측에 **세로로** 배치 → **ENC0(위)=상단 밴드(구조/노드체인),
  ENC1(아래)=하단 밴드(값/노브)**. 물리 위치 = 조작 영역, 학습 없이 직관적.
- `[결정]` **입력 어휘 = 우리 `GestureRecognizer`와 정확히 일치:** Rotate + Press{click,long} + Combo.
  ENC0 CLICK=슬롯 메뉴(바이패스·이동·교체·제거), ENC0 HOLD=한 단계 위(→깊이 −1), ENC1 CLICK=노브 락(점선→실선),
  ENC1 HOLD=튜너, **0+1 COMBO=스냅샷 저장**. → 하드웨어 확장 불필요.
- `[결정]` **회전은 상대 델타 + 가속.** (구현됨: `ganglion/input.py`)
- `[결정]` **RGB LED 의미론** (시안 `leds()` 채택): ENC0=이펙트 카테고리 버킷색(Drive=주황·EQ=파랑·Mod=보라…),
  바이패스=적색 / ENC1=락·편집=녹색, 메뉴=주황, 삭제=적색, **튜너=보라**, 이동=파랑. → **열린결정 #3 닫힘.**
- `[결정]` **폴링 확정. seesaw INT는 조건부 백로그.** 커뮤니티 정찰(2026-07-07): seesaw INT는
  레벨 신호 + **read-to-clear**(위치를 I2C로 읽어야 플래그 클리어) → 어차피 읽기 1회 필수라 오프로드
  아님. "폴링 없이 INT가 안 뜬다"·"멀티 인코더 INT wired-OR 시 불안정(~2.6V 처짐)"·쿼드러처 카운트
  드리프트(seesaw#51, open) 리포트 다수. 노브는 사람 손 속도라 33Hz 폴링으로 충분하고, 버스 경합의
  주범은 인코더 폴이 아니라 OLED 풀프레임. → 현 스텁(`ganglion/hw/seesaw.py`)의 폴링 유지. INT는
  실기 벤치에서 "OLED 전송이 인코더 폴을 굶겨 입력 레이턴시가 튄다"가 실측될 때만, 모듈당 별도 GPIO +
  read-to-clear 패턴으로 재검토.

---

## 4. 정보 아키텍처 (화면 스택) `[결정]` — 시안 2a

- `[결정]` **깊이 모델:** −1(보드/스냅샷 글랜스) · 0(메인 체인 + 노브). *깊이 1(단일 노브 화면) 제거* —
  노브 편집을 전부 깊이 0 하단 밴드에서 완결.
- `[결정]` **모달 상태:** menu(슬롯) · pick(화이트리스트 피커) · moving · rename · sub(관리) · confirm · sys · tuner.
- `[결정]` **화면 = 실 1-bit 렌더 검증 완료**(`ganglion/design_screens.py`): 글랜스·체인·튜너 포팅, 가독성 OK.
  체인 노드 배선은 **셀 사이 간격에만**(취소선 방지), 노드 약어 8px.
- `[열림]` 헤더 이름 티어: 24px는 ~6자에서 잘림 → 마퀴 필수거나 16px(~10자)로 낮출지.
- `[결정]` 화면 전환은 전체 재그리기(~2KB)라 **이산 사용자 조작에만** — 코스트 모델 참조.

---

## 5. 런타임 / 프로세스 모델 `[결정 대부분]`

- `[결정]` **단일 프로세스, 헤드리스.** X/Qt 없음. `ganglion/main.py`가 진입점(= `qt_main.py` 대응).
  순수계층 import + 실물 하드웨어(디스플레이/인코더) 주입.
- `[결정]` **자체 메인루프/스케줄러.** synapse는 Qt 이벤트루프(`qtscheduler`)에 얹혔지만 ganglion은
  헤드리스 → 순수 `scheduler.Scheduler` seam에 맞춰 **plain-Python 루프**(단일 스레드 select/폴 또는 asyncio)
  구현. 루프가 하는 일: 인코더 입력 폴/이벤트 처리 · monitorfeed(레벨/튜너) 갱신 · 디스플레이 부분 push.
- `[결정]` **단일 인스턴스.** MODEP 호스트와 I2C 버스를 독점. synapse처럼 하나만 뜨게.
- `[열림]` **부팅 자동실행:** systemd 유닛(권장) vs `.desktop` autostart. 헤드리스니 systemd 서비스가 자연스러움.
- `[열림]` **역채널 소켓(`/tmp/synapsin.sock`):** 폰/데스크탑 웹UI(mod-ui) 변경과 동기화. GECO도 웹UI가
  살아있으니 **유지 권장**. 소켓 이름/경로를 그대로 쓸지(코드 공유상 편함) 검토.
- `[결정]` **Fail-loud:** 디스플레이/인코더가 죽으면 조용히 fake로 폴백 금지. 단 에러 표시 화면이 OLED뿐 —
  I2C 자체가 죽으면 로그(파일)로. 부팅 진단은 OLED 스플래시로.

---

## 6. 실시간 피드 (레벨미터 / 튜너) `[결정]`

`monitorfeed.py`(순수)는 이미 공유. 시안 2a + 코스트 모델로 확정:
- `[결정]` **레벨미터:** 체인 화면 상단에 IN/OUT peak 값(좁은 밴드). 시안 2a 채택.
- `[결정]` **튜너:** ENC1 HOLD 진입. 바늘 1스텝 = **155B/3.5ms**(코스트 실측) → 부분갱신으로 충분. 인/플랫/샤프는 RGB(보라) 보조.
- 원칙: **실시간 위젯 = 좁은 리전만**, 나머지 정적 (코스트 모델이 뒷받침).

---

## 7. 설정 / 식별자 `[열림]`

- `[결정]` `configs.py` 공유하되 **GECO 고유값**(I2C 주소, 디스플레이 회전, seesaw INT 핀, 인코더 매핑)은
  `ganglion/` 하위 별도 설정(파일/env)에 둔다 — synapse config와 충돌 방지.
- `[열림]` **MIDI/호스트 식별자:** README상 `GAAD67`/`GCaMP6s` 식별자가 MIDI 배선에 박혀 있음.
  GECO가 자체 MIDI 정체성이 필요한지(별도 기기니 충돌 여지) 확인.

---

## 8. Dev / Fake 하네스 `[결정]` — 하드웨어 도착 전 개발용 (중요)

하드웨어가 ≥3일 뒤 → **지금 개발 가능하게** synapse의 fake 패턴을 그대로 미러:
- `[결정]` **fake 디스플레이:** 실제 OLED 대신 **PNG/터미널로 128×128 프레임 렌더** → UI를 눈으로 확인.
- `[결정]` **fake 인코더:** 키보드 입력(← → 회전, Enter 누름)으로 이벤트 주입.
- `[결정]` **fakemodep 재사용:** `fakemodep.py`(픽스처 서빙)로 MODEP 없이 로직 검증.
- → `ganglion/dev.py`(= `qt_dev.py` 대응)에서 fake 3종 주입. **하드웨어 0으로 컨트롤러·화면·네비게이션 완성 가능.**

---

## 9. 열린 결정 요약

**시안 2a로 닫힘:** ~~인코더 UX 매핑~~ · ~~화면 스택/네비~~ · ~~RGB 의미론~~ · ~~레벨미터/튜너 형태~~ · ~~폰트~~.

**하드웨어 도착 후 실측:**
1. I2C 주소 실측 확정 (설치 후 `i2cdetect -y 1`; 디스플레이 0x3C/3D + 인코더 0x36/0x37 + pisound 충돌)
2. 폴링 vs 인터럽트 (seesaw INT 배선 여부)
3. 회전 부호·스위치/픽셀 핀 확정 (`ganglion/hw/seesaw.py` 스텁의 3개 TODO)
4. luma.oled sh1107 지원 버전 확정 + Micro5@10 실 패널 재확인
5. 1MHz I2C 오버클럭 채택 여부 (신뢰성 실측 후)

**설계/구현 진행 중 결정:**
6. 부팅 자동실행 방식 (systemd 권장)
7. GECO 자체 MIDI 정체성 필요 여부
8. 헤더 이름 티어 (24px+마퀴 vs 16px)
9. 플러그인 화이트리스트 확정본 여부 (시안 `WL` ↔ `plugincatalog.py` 실 LV2 URI 매핑)
10. `10초 무조작 → 깊이 −1 자동 진입`(스크린세이버성) 유지 여부

---

## 관련 코드 (ganglion/)
- `display.py` — 128×128 프레임버퍼 + 터미널 렌더러(braille/half)
- `input.py` — `GestureRecognizer`(공유) + 키보드 소스. Rotate/Press{click,long}/Combo
- `hw/seesaw.py` — 실물 인코더 입력 스텁 (배선 후 3개 TODO 확정)
- `emulator.py` — 하드웨어 없이 화면·인터랙션 검증하는 CLI
- `i2c_cost.py` — SH1107 바이트 코스트 모델 (§2 측정)
- `design_screens.py` — 시안 2a 화면(glance/chain/tuner) 실 1-bit 포팅 + 렌더/코스트 데모
- `assets/fonts/` — Silkscreen R/B + Micro5 (OFL 번들)

## 참고문헌
- peter-l5/SH1107 (벤치마크: 방향별 fps, 부분갱신 5ms) — https://github.com/peter-l5/SH1107
- luma.oled Usage & Benchmarking — https://github.com/rm-hull/luma.oled/wiki/Usage-&-Benchmarking
- Adafruit 1.12" 128×128 OLED (제품 5297) — https://www.adafruit.com/product/5297
- Adafruit CircuitPython DisplayIO_SH1107 — https://github.com/adafruit/Adafruit_CircuitPython_DisplayIO_SH1107
- SH1107 데이터시트 — https://www.displayfuture.com/Display/datasheet/controller/SH1107.pdf
- I2C vs SPI OLED 속도 — https://www.displaymodule.com/blogs/knowledge/spi-vs-i2c-for-oled-speed-pin-count
