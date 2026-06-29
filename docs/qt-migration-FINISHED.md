# Qt 이주 — 완료 아카이브 (FINISHED)

> ✅ **상태: 완료(FINISHED) — 능동 참조용 아님.** Kivy → **PyQt6 + QML + eglfs** 이주의
> *스택 작업*은 끝났고 Pi에서 라이브 검증까지 마쳤다. 이 문서는 "어떻게/왜 이주했나"의
> 박제(아카이브)다. **남은 기능·작업 로드맵은 [`qt-roadmap.md`](qt-roadmap.md)** 를 봐라.
> 한 가지 남은 이주 항목(무컴포지터 부팅)도 그 로드맵에 있다.

한 줄 요약: **Kivy 비트맵 UI → PyQt6+QML 벡터 UI로 이주 완료. 백엔드/하드웨어를 seam에서
주입(실물 ↔ 가짜)하고, Pi에서 eglfs 무컴포지터·터치·성능·실물 페달보드 렌더를 전부 검증함.**

---

## 1. 결과 (무엇이 됐나)

- **MVP 유지, 뷰만 교체.** presenter 로직 의미 불변, view(Kivy)만 QML+`QtView` 브리지로 교체.
- **엔트리 2개.** `qt_dev.py`(구 `qt_app.py`) = 오프디바이스 개발(가짜 백엔드/하드웨어 + 픽스처 + Z/X/C/V 키보드 풋스위치),
  `qt_main.py` = 온디바이스(실물 `ModepController` HTTP + 실물 `fsledctrl` I²C + 역방향 소켓 `/tmp/synapsin.sock`).
- **화면 3종 동작.** OVERVIEW(노드 그래프+풋스위치 스트립), FOCUS(노브/바이패스/IN·OUT 라우팅), TAP TEMPO.
- **autostart 전환됨**(커밋 `dfd42c6`): `~/run_synapsepy.sh` → `synapse-venv` + `qt_main.py`.
  롤백본 `run_synapsepy.sh.kivy-bak` 보존.

## 2. 툴킷 결정 — ★PySide6 → **PyQt6** 정정

> 이 저장소 초기 핸드오프/목업은 **PySide6**(LGPL)로 시작했으나, **실제 이주는 PyQt6로 진행했다.**
> 옛 문서의 "PySide6" 표기는 전부 PyQt6로 읽어라(혼동 방지).

- **채택: PyQt6 (apt `python3-pyqt6` 6.4.2) + QML + eglfs.**
- **왜 PySide6가 아니라 PyQt6인가:** 사용자가 **거버넌스**를 우선 — PyQt6=Riverbank(인디),
  PySide6=The Qt Company(대기업). 그 대가로 **GPL 제약 + 비격리(시스템상속) venv를 수용**
  (Pi에선 apt numpy/Pillow/Qt가 ARM 최적화라 시스템상속이 실용적, 단일목적 기기라 격리 이득 적음).
- **재정합:** 리모트 `qt-migration` 브랜치가 이미 **PySide6+QML 목업**으로 진행돼 있었음 →
  **QML→PyQt6 포팅**으로 합침. 포팅 surface 극소: `qt_app.py` import 4줄(PySide6→PyQt6),
  `qtview.py`/`qtscheduler.py`는 `pyqtSignal/pyqtProperty/pyqtSlot as Signal/Property/Slot` 별칭이라 데코레이터 무수정.
  `main.qml`의 `Shape.CurveRenderer`(Qt6.6+) 2곳 제거 → Pi의 Qt **6.4** 기본 렌더러로(기능 동일).
- **venv:** `/home/miza/synapse-venv`(`--system-site-packages`). 옛 `gcamp6s-venv`(Kivy)는 롤백용 보존.

## 3. 아키텍처 seam (확립 완료)

- **백엔드 seam:** `modepctrl.get_backend()/set_backend()` — 기본 실물 `ModepController`, 오프디바이스는 `FakeModepController`.
- **하드웨어 seam:** `hardware.HardwareController` — 실물 `fsledctrl.Controller`(I²C), 오프디바이스는 `FakeController`(no-op LED + 합성 풋스위치).
- **스케줄러 seam:** `QtScheduler`(GUI 스레드 마샬링) — Kivy Clock 의존 제거.
- 픽스처: `fixtures/01-gcamp6s-demo.json`.

## 4. 스택 검증 결과 (Pi, 전부 PASS)

| 항목 | 결과 |
|---|---|
| **eglfs 무컴포지터** (lightdm 정지 후) | DSI1 **800×480@60** 모드셋, `ft5x06`(event9) 터치 등록, exit 0 — PASS |
| **QML on eglfs 성능** | QRhi OpenGL(threaded, vsync 16.67ms), **LLVMpipe 소프트웨어 GL**인데도 노드탭→FOCUS·노브드래그 **매끄러움** — PASS |
| **실물 앱 라이브** | `qt_main.py`로 실제 'Crunch 0'(6이펙트·11연결·snap3) 그래프 렌더 성공(grim 확인) — PASS |
| **SSH·비루트 DRM master** | lightdm 정지 후 card0 DRM master 획득 가능 — PASS |

→ "PyQt6+QML+eglfs 전 스택이 Pi에서 검증 완료"(렌더·터치·성능). QML-on-eglfs 성능 우려 해소.

## 5. 비블로커 캐비엇 (참고)

- **LLVMpipe 소프트 GL**(V3D HW 가속 아님) — 이 UI/해상도엔 충분. 추후 HW가속은 튜닝거리.
- **GBM 하드웨어 커서 플레인 실패**(-6/-14) — 터치앱은 커서 숨기면 무관.
- **FS2/FS3 red 링 LED dim 깜빡** = GUI 렌더링의 **HW 전기 커플링**(소프트/폴링/CPU 무관, 격리테스트로 확정). 외형 이슈, 추후 HW(디커플링) 조사거리.

## 6. 남은 이주 항목 (→ 로드맵)

스택은 끝났지만 **무컴포지터 부팅**(lightdm/labwc 제거 후 eglfs 풀스크린 직행)은 아직.
현재 autostart는 labwc 위에서 qt_main을 **창모드로** 띄우는 잠정 상태(`dfd42c6`).
이 한 항목 + 모든 기능/정리 작업은 **[`qt-roadmap.md`](qt-roadmap.md)**(로드맵)에 있다.

관련: [`README.md`](../README.md) · [`REFERENCES.md`](../REFERENCES.md) · 프로젝트 메모리 `synapse-roadmap`.
