# Ganglion 설계문서 (GECO1)

> 상태: **초안 / 하드웨어 소싱 중** (배선·설치 완료 예상 ≥ 2026-07-07)
> 대상 기기: **GECO1** — 데스크 미니 (pisound + rpi)
> 앱: **ganglion** — 헤드리스 인터페이스 (Qt 없음)
> 대비: GCaMP6s(본체) / synapse(터치스크린 앱)

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
  블록으로 정보 표현. 안티에일리어싱 폰트 못 씀 → 비트맵 폰트 권장.
- `[열림]` **실시간 요소(레벨미터/튜너) 프레임 예산:** 작은 영역만 갱신하면 부분갱신으로 10~15fps
  가능. 전체를 실시간으로 흔들면 안 됨. → 실시간 위젯은 화면의 좁은 밴드에 격리.

### 드라이버 선택 `[열림 → 조사]`
- **1순위: `luma.oled`** — Pillow(PIL) 네이티브 드로잉. 우리가 UI를 직접 그리는 방식에 가장 잘 맞음.
  설치 시 실제 sh1107 디바이스 지원 버전 확정 필요.
- **2순위: `adafruit-circuitpython-displayio-sh1107`** (+Blinka) — displayio 위젯 지향, 커스텀 드로잉엔 덜 편함.
- 결정 기준: 커스텀 UI + 부분갱신 제어권 → **luma.oled 우선**. 벤치 실측 후 확정.

---

## 3. 입력 모델 `[열림]` — 인코더 UX 시안 대기

물리 입력 총량: **로터리 2개(회전 상대델타) + 푸시 2개 + RGB LED 2개**. 매우 제약적.
UX 상세(회전=?, 누름=?, 길게누름=?)는 **사용자 시안**으로. 다만 아래는 시안과 무관하게 정할 것:

- `[열림]` **폴링 vs 인터럽트:** seesaw는 INT 핀 지원. rpi GPIO 인터럽트로 인코더 이벤트를 받을지,
  메인루프에서 I2C 폴링할지. 회전 놓침 방지엔 인터럽트가 유리하나 배선 1핀 추가. → 하드웨어 확정 후.
- `[결정]` **회전은 상대 델타 + 가속(accel):** 빠르게 돌리면 큰 스텝(파라미터 대범위 이동), 천천히 돌리면 1스텝.
- `[열림]` **디바운스/롱프레스 임계값**(ms) — 시안에서 롱프레스 쓰면 확정.
- `[열림]` **RGB LED 의미론:** synapse의 링LED 상태피드백(bypass/tempo blink/튜너) 중 무엇을 2개 RGB로 매핑할지.
  후보: (a) 인코더별 컨텍스트 색, (b) 탭템포 blink, (c) 튜너 인·플랫·샤프 색, (d) 저장/오류 플래시.

---

## 4. 정보 아키텍처 (화면 스택) `[열림]` — 시안과 함께

128×128 + 인코더 2개로 표현할 화면 인벤토리(시안 전 후보):
페달보드 리스트 · 스냅샷 리스트 · 플러그인 파라미터 편집 · 튜너 · BPM/탭템포 · (레벨미터 밴드).
`[열림]` **네비게이션 모델:** 인코더A=화면/항목 스크롤, 인코더B=값 편집? 누름=진입/뒤로?
→ 시안에서 확정. 화면 전환은 부분갱신 불가(전체 다시 그림)이므로 **전환 빈도 최소화** 설계.

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

## 6. 실시간 피드 (레벨미터 / 튜너) `[열림]`

`monitorfeed.py`(순수)는 이미 공유. 문제는 **표시**다:
- `[열림]` 128×128·10~16fps·1bpp에서 **레벨미터를 보여줄지**, 보여준다면 좁은 밴드 부분갱신으로.
- `[열림]` **튜너**: 실시간성 요구 큼. 바늘/막대 애니메이션은 부분갱신 영역으로 격리. 색(인/플랫/샤프)은 RGB LED로 보조.
- 원칙: **실시간 위젯 = 화면 일부 좁은 리전만**, 나머지는 정적.

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

## 9. 열린 결정 요약 (사용자/시안 대기)

1. 인코더 UX 상세 (회전/누름/롱프레스 매핑) — **사용자 시안**
2. 화면 스택 & 네비게이션 모델 — 시안과 함께
3. RGB LED 의미론 (무엇을 색으로)
4. 레벨미터/튜너 표시 여부·형태
5. I2C 주소 실측 확정 (설치 후 `i2cdetect`)
6. 폴링 vs 인터럽트 (seesaw INT)
7. 부팅 자동실행 방식 (systemd 권장)
8. luma.oled vs Adafruit displayio 최종 (벤치 실측)
9. GECO 자체 MIDI 정체성 필요 여부
10. 1MHz I2C 오버클럭 채택 여부 (신뢰성 실측 후)

---

## 참고문헌
- peter-l5/SH1107 (벤치마크: 방향별 fps, 부분갱신 5ms) — https://github.com/peter-l5/SH1107
- luma.oled Usage & Benchmarking — https://github.com/rm-hull/luma.oled/wiki/Usage-&-Benchmarking
- Adafruit 1.12" 128×128 OLED (제품 5297) — https://www.adafruit.com/product/5297
- Adafruit CircuitPython DisplayIO_SH1107 — https://github.com/adafruit/Adafruit_CircuitPython_DisplayIO_SH1107
- SH1107 데이터시트 — https://www.displayfuture.com/Display/datasheet/controller/SH1107.pdf
- I2C vs SPI OLED 속도 — https://www.displaymodule.com/blogs/knowledge/spi-vs-i2c-for-oled-speed-pin-count
