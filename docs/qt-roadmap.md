# Qt 앱 로드맵

> 🛠 **통합 로드맵 (원 문서).** Kivy→PyQt6+QML+eglfs **이주 스택 자체는 완료**
> (검증 내역 = [`qt-migration-FINISHED.md`](qt-migration-FINISHED.md) 아카이브).
> 이 문서는 그 위의 **남은 기능·신뢰성·정리·부팅·설계결정·검증**을 모은 살아있는 로드맵이다.
> 구 `qt-migration-handoff`(후속작업) + `ui-migration-review`(시안↔현행 갭 분석)를 **흡수·통합**했다.
> 마지막 갱신: 2026-06-28 (**페달보드 에디터 트랙 M1~M6d 전부 완료·라이브검증** — 임베드/읽기로드/파라미터·바이패스/패치(M3.5)/그래프변형(M4·M5)/보드 로드·저장·스냅샷(M6a~c)/라이브 QUICK 모드(M6d)까지. 마일스톤별 상세는 메모리 `synapse-roadmap`이 권위본. **다음 최우선 = M7 라이브 플러그인 카탈로그**).

**현재 사실관계:** PyQt6+QML+eglfs 앱이 Pi에서 라이브 동작하고 autostart도 전환됨(`dfd42c6`).
FOCUS 컨트롤/모니터 렌더링 + 라이브 레벨미터 피드까지 라이브 검증됨(커밋 `1074b5e`).
"못 뜨는" 하드 블로커는 없다. 남은 일 = ① 라이브 신뢰성 ② 기능 패리티/신규 ③ 정리/폴리시
④ 무컴포지터 부팅 ⑤ 검증 ⑥ 열린 설계결정 ⑦ 미래.
**우선순위 = Tier 1 → Tier 2 → Tier 3 → 부팅(보류).** ★부팅(무컴포지터 eglfs)은 의도적으로 **내림**:
원격 개발 동안 labwc 창모드가 remote desktop(PiConnect/VNC) 접속 이득이 커서, 당분간 컴포지터 유지.
무대 실사용/기기 확정 단계에서 다시 올린다. (2026-06-25 사용자 결정.)

**★페달보드 에디터 트랙(가장 무거운 덩어리)은 M1~M6d로 완료됨**(아래 전용 섹션). 그래프 편집·보드 로드/저장·스냅샷·라이브 QUICK 모드까지 실호스트 배선·라이브검증 끝.
**★다음 최우선 = M7 라이브 플러그인 카탈로그**(아래 전용 섹션) — 에디터를 동결 72-플러그인 서브셋에서 **호스트의 전체 설치 플러그인**으로 승격.

각 항목은 `파일:라인` 근거로 검증됨. 작업은 한 번에 하나씩, 변경 전 사용자 승인.

---

## Tier 1 — 라이브 무대 신뢰성 (작지만 먼저)

앱은 잘 뜨지만, 호스트가 죽거나 느릴 때 **무대에서 얼어붙지 않게** 만드는 게 핵심.

- [x] **HTTP timeout 추가 ✅(2026-06-25, 커밋 `1074b5e`)** — `_request`에 `setdefault("timeout", 2.0)` +
      8개 직접 get/post 호출 전부 `timeout=2.0`. `parameter_set`/`parameter_get`는 예외처리로 감쌈.
      ★이게 노브/토글 드래그 시 앱 프리즈의 **실제 원인**이었음(동기 `requests.post` 무타임아웃 → mod-ui 핸들러
      wedge에 GUI 스레드 영구블록). 남은 안전화는 아래 None 가드.
- [x] **`_request` None 반환 가드 ✅(2026-06-26)** — `_request` 실패 시 None인데 호출부가 무가드로 deref하던 것 →
      9개 메서드에 명시적 None 가드. 부수로 선재 크래시 3건 수정: `effect_get_information`의 `logging(...)`(모듈을
      함수로 호출→TypeError), `get_current_pedalboard`/`get_last_pedalboard`의 bare 클래스속성 참조 `NameError`(콜드부팅 경로).
- [x] **콜드부팅 게이트 = 스플래시 후 차단 대기 ✅(2026-06-26)** — `_modep_ready()`(`_request` non-None 프로브, 기존
      `get_current_pedalboard`은 실패 시 DEFAULT 반환=truthy라 무력했음) + QML 먼저 로드해 "MODEP 대기 중…" 스플래시
      (`view.screen=="booting"`) → 백그라운드 무한 대기 후 GUI스레드서 presenter 구성 → overview. 깨진 첫 화면 제거.

### Tier 1 후속 — 페달보드 저장 영속성 + ttl 부패 (2026-06-26 세션, 중대)
> 오래 망가진 `save_current_pedalboard`를 고치는 과정에서 mod-ui 저장의 ttl-이름 부패 버그를 발견·차단.
> 상세 포스트모템 = [`save-corruption-postmortem.md`](save-corruption-postmortem.md).
- [x] **페달보드 저장 영속성 복구** — `save_current_pedalboard`가 ① full-URL을 endpoint로 넘겨 더블-prefix 404,
      ② 고친 뒤엔 `json=` 바디라 Tornado `get_argument`가 못 읽어 400. → 바른 endpoint + `data=`(form-encoded, 웹UI와 동일)로
      수정. snapshot save/save-as의 PB저장 묶음도 같이 복구.
- [x] **앱측 저장 가드** — `save_current_pedalboard`가 `symbolify(title)[:16]`(mod-ui와 동일)이 번들 dir과 어긋나면
      **저장 중단+로그**. stale title이 와도 앱이 ttl을 잘못 명명/고아화 못 함.
- [x] **서버측 구조적 차단(mod-tweak)** — `host.py:3965`(asNew=0 분기) ttl 심볼을 클라이언트 title이 아니라
      **번들 dir명**에서 도출 → `dir==ttl==manifest` 구조 보장. **웹발 stale-title 저장도 파일 부패 불가**(`doap:name`은 별도
      `title` 인자라 이름변경은 유지). `mod-tweaks/host.py` 반영, `sudo deploy.sh` 배포.

## ★ 페달보드 에디터 (다음 최우선 — 가장 무겁고 힘든 태스크)

> 앱이 **그래프 자체를 편집**(이펙트 추가·삭제·연결·끊기·노브 MIDI 바인딩)하게 만드는 본체.
> 옛 Kivy 로드맵의 "트랙2"(앱이 직접 이펙터 추가/라우팅/바인딩)에 해당하고, **볼륨페달 자동 라우팅**도
> 이 백엔드(`/effect/add`+`/connect`+`/parameter/address`)를 공유한다. 여러 화면·백엔드·역방향싱크가 동시에
> 엮여서 지금까지 손댄 어떤 항목보다 표면이 크다. 한 번에 하나씩, 단계별로 라이브 검증하며 진행할 것.

**현재 상태 (트랙 완료 — 2026-06-28, 브랜치 `pedalboard-editor`, master 미머지):**
- **목업 본체 완성**(브랜치 `pedalboard-editor`): `editor_bridge.py`(브레인) + `qml/PedalboardEditorView.qml`(본문, advanced 포트그래프·레이디얼연결·bake·인스펙터) + standalone `qt_editor.py`. P1~P3 완료(메모리 로드맵 참조).
- **라이브 앱 배선을 마일스톤으로 진행**(각 끝에서 Pi 육안검증). 진실원 = `presenter.pedalboard`; 에디터는 거기서 advanced 그래프를 시드하고 쓰기는 backend로, 리버스 채널이 자동 갱신:
  - [x] **M1 — 임베드 ✅(2026-06-27)** — `PedalboardEditor.qml` 본문을 `PedalboardEditorView.qml`(Item)로 분리 → standalone Window와 라이브 EDIT 화면이 **같은 본문** 공유. [`main.qml`](../qml/main.qml) `editScreen` = `PedalboardEditorView` Loader(`source:`, EDIT 진입마다 새로 생성), 헤더 `◄ 나가기`→`view.goOverview()`. `editor` 컨텍스트 프로퍼티를 `qt_main.py`/`qt_dev.py`에 등록. **+ 라이브 앱도 `showFullScreen()`+`Ctrl+Q`**(에디터와 동일).
  - [x] **M2 — 읽기전용 라이브 로드 ✅(2026-06-27)** — `editor.enterLive()`(Loader onLoaded)가 `_seed_from_pedalboard(presenter.pedalboard)` 호출 → 실제 체인 렌더. 식별자 매핑: **정수 gnode id ↔ 라이브 인스턴스**(`_gid_by_inst`/`_inst_by_gid`; 피드백 DFS의 `int()` 제약 + 이후 backend 주소지정용). `Connection`(`bluesbreaker/out0`) → 포트키(`gid:out:audio:idx`), HW(`capture_N`/`playback_N`)→IN/OUT. 좌표 정규화·`vals`=라이브 포트값·보드명=`pb.title`. `live` 프로퍼티가 목업 크롬(BOARD/UNDO/REDO/SHUF) 숨김. ClaudeCanEdit 검증 OK.
  - [x] **M3 — 파라미터·바이패스 라이브 쓰기 ✅(2026-06-27)** — 인스펙터 노브/토글/enum/리셋→`parameter_set`, bypass→`bypass_effect`(신규 backend API 0). 에디터가 `self.presenter.view`(QtView)를 통해 써서 **FOCUS와 같은 throttle 재사용**(별도 배선 0): `_inst_of`/`_live_param`/`_live_bypass`, gnode id→라이브 인스턴스. 부수: **FOCUS parameter_set 점검(이미 동작 확인) + 정리** — `model.EffectPort.set_value` 디버그 `print('wow')` 제거·`return error_msg`, `qtview.setParameter`에 **드래그 throttle**(`(inst,sym)`별 coalesce, leading+trailing, 40ms≈25/s). ClaudeCanEdit GAIN/bypass 라이브 검증 OK.
  - [x] **M3.5 — patch_set(NAM·IR·cabsim 파일 로딩) ✅(2026-06-27, 커밋 `e89a458`+`cf0fcfe`)** — FOCUS·에디터 인스펙터 둘 다 구현. 공유 `qml/PatchPicker.qml` + `presenter.list_patch_files`(디렉터리 재귀스캔) + `qtview.setPatch`/`update_patch_display` + `editor.inspPatches`/`setPatch`. ★mod-ui `fileTypes`=카테고리명('nammodel','cabsim')→`configs.PATCH_FILE_TYPE_EXTS` 매핑. (Tier 2 "패치/IR 파일 선택기"와 동일 — 완료.) 상세 [[param-vs-patch-set]].
  - [x] **M4 — 라이브 그래프 read + backend 그래프변형 4종 ✅(커밋 `3b9f163`[M4a]·`4fba6c3`[M4b])** — M4a: `syn_dump_graph` 포크 엔드포인트로 **라이브 그래프 read**(stale 디스크 근본해결, plugins/connections만 라이브 우선·폴백 안전). M4b: `modepctrl` add/remove/connect/disconnect 래퍼(포크 무관, 웹UI desktop.js와 동일 엔드포인트) + Backend ABC + fakemodep. namespace [[mod-port-namespaces]].
  - [x] **M5 — 구조편집 + 식별자 매핑 ✅(커밋 `9779e99`)** — 노드 add/remove·케이블 connect/disconnect이 라이브 그래프에 반영. **포트심볼 해석층**(`model.Effect.audio_inputs/outputs` + `_endpoint_from_port_key` + `_mint_instance`), 편집슬롯 host-first 낙관반영, **화면 진입=호스트 재독**(`enterLive`/`goOverview`가 `refresh_pedalboard`), 고아 인스턴스 보존.
  - [x] **M6a/b/c — 보드 로드·저장·스냅샷 ✅(커밋 `0e860ae`/`9a28727`/`9074982`)** — M6a: 에디터 라이브 보드 전환(LOAD, dirty 폐기-확인). M6b: SAVE in-place + SAVE AS(기존 3겹 부패방어 위임, 새 직렬화 0). M6c: 인-앱 스냅샷 관리(목록/탭전환/저장, 헤더 SAVE가 스냅샷 재캡처+보드저장 통합).
  - [x] **M6d — 라이브 QUICK 모드 + NEW BOARD + 모드 라우팅 ✅(커밋 ~`e0860ae`, on-device 통합검증)** — **생성기=판정기 단일함수 `_quick_wire_keys()`**(편집 배선생성+표현가능 판정 둘 다 파생→desync 불가). `_quick_representable`(mono/stereo 둘 다 시도), `_reconcile_live_quick`(델타 connect-first), NEW 빈보드+강제 save-as, default 보호/숨김, 양방향 토글+전환이펙트. evolve/bake 제거(모드=라우팅에서 판독되는 뷰).

**백엔드 완전 부재 (가장 큰 덩어리):**
- [`modepctrl.py`](../modepctrl.py)에 **그래프 변형 메서드가 하나도 없다** — 현재는 parameter/bypass/patch/snapshot/PB-load뿐.
  추가/삭제/연결/끊기/주소(바인딩) 래퍼를 **전부 신규 작성** 해야 함.
- mod-ui 엔드포인트는 **이미 다 존재** (mod-tweak 불필요할 수 있음, notify만 보강):
  - `/effect/add/<instance>/<uri>?x=&y=` ([`mod-tweaks/webserver.py:2486`](../mod-tweaks/webserver.py))
  - `/effect/remove/<instance>` ([:2487](../mod-tweaks/webserver.py))
  - `/effect/connect/<port_a>,<port_b>` ([:2512](../mod-tweaks/webserver.py)) · `/effect/disconnect/<port_a>,<port_b>` ([:2513](../mod-tweaks/webserver.py))
  - `/effect/list` (LV2 카탈로그 — "추가" 브라우저용, [:899](../mod-tweaks/webserver.py)) · `/effect/get` (플러그인 메타, 포트/카테고리, [:1096](../mod-tweaks/webserver.py))
  - MIDI 바인딩은 `/effect/parameter/address`(트랙2 스펙, 볼륨페달과 공유) — 엔드포인트 존재 재확인 필요.

**역방향 싱크 — 부분만 됨 (갭 있음):**
- `EffectAdd`/`EffectRemove`는 이미 notify_synapsin 발화([`webserver.py:1086,1094`](../mod-tweaks/webserver.py)) +
  presenter가 전체 재동기화로 처리 ([`presenter.py:227`](../presenter.py)). → 추가/삭제는 앱이 따라옴.
- **★connect/disconnect 배선 변경 싱크 = 구현+라이브 검증 OK(2026-06-26). 2단 수정:**
  검증: `/effect/disconnect` HTTP → 앱 그래프서 해당 케이블 즉시 사라짐, `/effect/connect` → 즉시 복원(grim before/after 확인).
  서버 notify 발화는 `journalctl -u modep-mod-ui`의 "Notification sent: EffectDisconnect/Connect …"로 확인.
  **사용자가 실제 웹UI(폰)에서 직접 배선 변경 → 앱 그래프 즉시 따라옴까지 양측 교차확인(2026-06-26).**
  ① **서버 notify**(배포 완료): `/effect/connect`·`/effect/disconnect`가 성공시 `notify_synapsin("EffectConnect/Disconnect <a>, <b>")`
  발화([`webserver.py`](../mod-tweaks/webserver.py) EffectConnect/EffectDisconnect, `sudo deploy.sh` 반영됨).
  ② **★델타 적용**(presenter, 앱재실행만): notify를 `refresh_pedalboard()`(전체 재동기화)에 걸었더니 **안 그려짐** —
  **근본원인:** `refresh_pedalboard`→`initialize_modep_pedalboard`→`get_pedalboard_info`가 `/pedalboard/info/?bundlepath=`로
  **디스크 번들 .ttl 을 읽는다**. 웹 배선은 라이브 호스트 그래프에만 있고 **저장 전엔 디스크에 없어** 재조회해도 옛 케이블뿐.
  → `handle_reverse_event`가 connect/disconnect를 메시지의 두 포트로 **모델 `connections` 에 직접 델타 적용**
  (`apply_external_connection`, 파라미터/패치의 `apply_external_*` 패턴). 포트는 `/graph/` 접두만 떼면 디스크 포맷과 일치
  (`mod-port`=`/graph/Click/out` ↔ 디스크 `Click/out`; JS도 로드 시 `/graph/` 재부착). [`presenter.py:227,287`](../presenter.py).
- ★**EffectAdd/EffectRemove 도 같은 디스크-stale 잠복버그** — 여전히 `refresh_pedalboard`(디스크 재조회)라 웹발 추가/삭제도
  저장 전엔 앱에 안 보일 수 있음. connect/disconnect처럼 델타 적용하려면 플러그인 메타(name/category/ports) 조회가 필요(추후).
- ★저장은 **호스트 권위** — 앱 `save_current_pedalboard`는 그래프를 안 보내고([`modepctrl.py:330`](../modepctrl.py) title+asNew만)
  mod-ui가 호스트 라이브 그래프를 직렬화 → 앱 뷰가 stale여도 **디스크엔 올바른 배선**이 써짐(무결성 위험 아님, 표시 문제일 뿐).
  따라서 "stale 중 앱 저장 차단" 가드는 불필요.

**UI 재사용:**
- 스네이크 그리드 그래프([`qtview.py`](../qtview.py) `_rebuild_graph`)가 이미 체인을 렌더 → 에디터는 그 위에 **상호작용**만 얹음
  (노드 선택→삭제, "+" →카탈로그서 플러그인 골라 추가, 노드↔노드 드래그→연결/끊기).
- 플러그인 추가 브라우저(`/effect/list`+`/effect/get`) = 신규 리스트/모달 UI. 스냅샷/PB 브라우저(Tier 2)와 패턴 공유 가능.

**제안 분해 (대략, 의존순):**
1. modepctrl 래퍼 4종(add/remove/connect/disconnect) + 에러/timeout 가드(Tier 1 패턴 따라).
2. 노드 선택 → 삭제, bypass 토글은 이미 있음.
3. `/effect/list`·`/effect/get` 카탈로그 조회 + 추가 브라우저 UI → `/effect/add`.
4. 노드 간 연결/끊기 인터랙션 + `/connect`·`/disconnect`.
5. ~~connect/disconnect 역방향 notify 보강(mod-tweak)~~ ✅ 코드 반영(2026-06-26) — 배포+검증만 남음(위 참조).
6. (연계) MIDI 바인딩 `/parameter/address` → 볼륨페달 자동 라우팅과 합류.

**열린 설계 결정:** 편집을 **앱 단독**(웹발 배선변경 동기화 불필요 → 5번 생략)으로 둘지, 진짜 양방향으로 갈지 먼저 정할 것.

## 페달보드 에디터 — 남은 후속 (소, 사용자 제시 2026-06-28)

> 트랙 본체(M1~M6d)는 끝났고, 아래는 일관성·편의 후속. 큰 카탈로그 작업은 M7로 분리.

- [ ] **메인 nav도 default 보드 제외** — 에디터 목록은 default를 이미 제외하나
      `modepctrl.get_all_pedalboards`/`set_next_pedalboard`/`set_prev_pedalboard`는 **default 포함** →
      풋스위치 NAVIGATE가 숨김 보드를 밟음. 에디터와 동일 제외 규칙으로 통일. (제일 쌈)
- [ ] **오버뷰에서도 보드 매니저 열기** — 현재 라이브 보드 스위처/매니저는 **에디터 안에서만**. 오버뷰 헤더에도 진입점.
- [x] **뱅크 매니저 ✅(2026-06-29, 브랜치 `feat/bank-manager`)** — 오버뷰 헤더 BANK 버튼 → 풀 CRUD 오버레이.
      뱅크 생성/이름변경/삭제(2탭) + 보드 추가·제거·순서변경(위/아래; 앞 4개=mode2 FS A·B·C·D) + 활성 뱅크 지정.
      시임: `modepctrl.get_banks`/`save_banks`(호스트 `GET`/`POST banks/`, **전체 읽기→수정→통째 저장**) ·
      `presenter.bank_manager_*`(드래프트 + `_commit_banks`가 저장+mode2 재바인딩) · `qtview` `bankList`/`boardCatalog` +
      슬롯들 · `qml/main.qml` `bankMgr` 오버레이. 이름은 책상 물리키보드 전제(wvkbd 안 뜸) → 새 뱅크 기본값 = 날짜-시간.
      `fakemodep`도 인메모리 뱅크 구현(데스크톱 테스트). 남은 것: **라이브러리(전체 보드) 순서 정렬**은 별개로 미구현.
      폴리싱(2026-06-29): ① **마지막 뱅크 삭제 금지** 가드(presenter `_notify` + qml 삭제버튼 dim) — 0개로 자멸 방지.
      ② **활성 뱅크 영속**(`utils.load/save_last_bank` → `~/.modep/app_state.json`) — MOD HMI가 기기-측에서 마지막
      뱅크를 홀드하던 걸 재현. 재시작 시 로드 + stale 인덱스(앱 꺼진 새 뱅크 삭제됨) 진입 시 0 클램프.
- [x] **UNDO/REDO 제거 ✅(2026-06-29)** — 웹 UI(mod-ui)에도 없는 기능(프론트엔드의 "undo"는
      잭 연결 실패 롤백 주석뿐). 라이브엔 애초에 미배선(스냅샷 스택은 디스크-편집 경로 전용)이라
      스냅샷-restore desync를 감수하고 유지할 가치가 없어 **버튼+백엔드 기계 전부 제거**
      (`editor_bridge`의 `_undo/_redo/_snapshot/_push_hist/_restore/canUndo/canRedo/undo/redo`,
      `PedalboardEditorView.qml` UNDO/REDO Pill). 구조 편집의 `_push_hist()`는 더티 추적
      `_touch()`로 치환. (SHUF는 dev `demoScramble` 데모로 잔존.)
- [ ] **이펙터 프리셋 적용** — M7으로 프리셋 **이름/uri**까지 노출되면, `/effect/preset/load` 엔드포인트 래퍼 추가해
      실제 적용. (지금은 카탈로그가 개수만 → M7이 이름 공급, 적용은 별도 작은 후속.)

## ★ 라이브 플러그인 카탈로그 (M7 — 다음 최우선)

> 에디터를 **동결 72-플러그인 서브셋**(`resources/effects-catalog.json`)에서 **호스트의 전체 설치 플러그인**으로 승격.
> 동결본은 오프디바이스 베이크라 재생성 불가 + 다음이 잘려 있음: ① **`ctl` 16포트 truncate**(8개 플러그인이
> 포트 손실 — amsynth 41, Step Seq 79, Aether 47…) ② **프리셋 개수만**(값/이름 없음) ③ 포트 범위 베이크값(우회 원인).

**호스트 라이브 경로(이미 존재):**
- `GET /effect/list` → `get_all_plugins()` = **전체 설치 플러그인 풀 정보**(포트 범위·프리셋 리스트·카테고리, truncation 0). `modepctrl` 래퍼 **신규 필요**.
- `GET /effect/get?uri=` → `get_plugin_info(uri)` = 단일 풀 정보. `modepctrl.effect_get_information()`로 **이미 있음**.
- `POST /effect/bulk` → uri 리스트 배치 조회.

**설계(결정됨):**
- **소스만 교체, 소비 스키마 유지** — `modepctrl.effect_list()`(라이브 풀 dump) + **정규화 함수**(mod-ui 네이티브 →
  에디터 축약 스키마, 전 포트 보존). `editor_bridge`는 `self.cat`/`by_uri`/`by_name` 구성만 바뀌고 소비코드 거의 무변.
  Backend ABC + fakemodep에도 메서드 추가(오프디바이스 dev 유지). → 16-truncation·프리셋·포트범위 우회 **부수 해소**.
- **캐시/갱신 = B. 자가치유 하이브리드(결정 2026-06-28):**
  ① 기동시 `get_all_plugins` 1회 → 세션 메모리 캐시.
  ② **미스시 per-uri 폴백** — add/seed가 캐시에 없는 uri를 만나면 `effect/get?uri=`로 **그 하나만** 라이브 조회해
     캐시에 흡수(전체 리스캔 없이 self-heal; "있다고 생각했는데 못 부르는" 케이스 자동복구).
  ③ **수동 리스캔** 버튼(config/메뉴) — 실행 중 설치한 플러그인 반영용.
  ④ (옵션·보류) 디스크 영속+서명체크는 **Pi에서 startup 비용 실측 후**에만 — 동결JSON이 애초에 startup 스캔 회피용일 수 있어 측정 먼저.
- **프리셋**: 라이브가 `{uri,label}` 리스트 제공 → 이름까지 노출 가능(개수→목록). 적용은 `/effect/preset/load` 래퍼(에디터 후속).

**검증:** off-device(fakemodep 정규화) → Pi 라이브(전 버킷 브라우저·>16포트 플러그인 인스펙터 포트 전부·미스 폴백·수동 리스캔).

## i18n / 테마 토큰화 (한 묶음 — 결정 2026-06-28)

> 핵심 난이도는 메커니즘이 아니라 **흩어진 리터럴/하드코딩 값을 전부 찾아 중앙화**하는 것. 둘 다 "하드코딩→스왑가능 토큰 추출"
> 동일 패턴이라 한 묶음으로. 방식 = **커스텀 테이블 + 테마 토큰(결정)**.

- [ ] **문자열 중앙화(i18n)** — 모든 사용자 노출 리터럴(QML `Text`, Python 토스트·스테이지 단어·라벨)을
      중앙 카탈로그(`resources/strings/<lang>.json`)로 추출 + `tr("key")` 인다이렉션(QML엔 `tr` 컨텍스트 프로퍼티).
      오늘은 한국어 identity, 언어 추가 = 카탈로그 추가. **작업 본체 = 리터럴 감사+추출 스윕**(기계적, 멀티에이전트 적합).
- [ ] **테마 토큰화** — `qml/Theme.qml`(`pragma Singleton`)에 색상 토큰(`bg/surface/accent/text/meter…`) +
      폰트 토큰(`fontFamily/sizeTier1/sizeTier2`) 집약, 전 QML이 참조 → 테마 전환 = 토큰셋 스왑.
      기존 [`ui-design-rules.md`](ui-design-rules.md)(800×480 2-tier 가시성)와 정합.
- **열린 결정**: 런타임 언어/테마 전환 UI를 config 화면에 둘지, 빌드/설정파일 고정으로 둘지(후순위).

## 부팅 — 무컴포지터 (남은 이주 항목) — ⏸ 보류 (원격 개발 중 컴포지터 유지)

> ⏸ **우선순위 내림(2026-06-25).** 주말까지 원격 개발이라 labwc 위 창모드가 remote desktop 접속에 유리.
> 스택 검증은 이미 끝났으니(아무때나 켤 수 있음) 배선만 남음 — 기기 확정/무대 단계에서 재개.

- [ ] **eglfs 풀스크린 부팅으로 전환** — 현재는 labwc 위에서 `qt_main`을 **창모드로** 띄우는 잠정상태
      (`~/run_synapsepy.sh` → `synapse-venv` + `qt_main.py`, autostart=labwc, 커밋 `dfd42c6`).
      목표: lightdm/labwc 제거 후 **eglfs 직행**(systemd 서비스 또는 autologin→eglfs 런처).
      스택 검증은 끝남(FINISHED §4) — 남은 건 부팅 체인 배선. 롤백본 `run_synapsepy.sh.kivy-bak`.
- [ ] **eglfs 런처 견고화** — DSI 커넥터 2개 connected라 자동선택 모호. `run_qt.sh`+`eglfs_kms.json`로
      card/커넥터/모드 고정 + `QT_QPA_EGLFS_HIDECURSOR=1` + (안전기본) `QT_QUICK_BACKEND=software`.
- [ ] **종료 어포던스** — 앱에 quit 버튼/단축키 없음(현재 프로세스 kill만). `main.qml`에 Esc→`Qt.quit()` 등.

## Tier 2 — 기능 패리티 / 신규 (미구현 기능 본체)

**개별 기능**

- [x] **FOCUS 컨트롤/모니터 렌더링 개편 + 라이브 미터 ✅(2026-06-25, 커밋 `1074b5e`)** — 기존 FOCUS가
      **모든 컨트롤을 원형 노브 하나**로 그리고 **출력(모니터) 포트를 통째로 버리던** 문제 해결.
      ① 컨트롤 포트를 LV2 properties로 **6종 분류**(knob/int/log/toggle/trigger/enum), 출력 포트를 **신규 지원**
      (meter/clip/gauge/numeric). 드로잉 분해 `qml/ControlWidget`·`MonitorWidget`, 해석 집약 `model.EffectPort`.
      ② **라이브 레벨미터 피드** `monitorfeed.py`(의존성無 raw WS)가 mod-ui 웹소켓 수동구독→`output_set`→미터(~30Hz throttle, `data_ready` ack).
      ③ 미터 **dB 매핑**(modmeter 출력=선형진폭 0..1이라 선형 norm이면 바가 ~1%만 차 안 보임 → `20·log10`, -60dB 바닥).
      라이브 검증 OK(HighGainRig 신호→바 가시적 움직임). 설계=[`focus-control-rendering.md`](focus-control-rendering.md).
      후속(미완): 패치선택기(아래 별도) · enum/trigger 위젯 **실조작** 검증 · 모니터 tier-2 하드코딩 레지스트리는 빈 채 둠.
- [ ] **튜너** — 콤보 B+C가 `pass`([`presenter.py:402`](../presenter.py)), Qt 튜너 화면 없음.
      ★피치검출 `yin.py`가 `under_vsersion1/`로 빠져 **누락**([`tunerpopup.py:8`](../tunerpopup.py) import 실패).
      필요: YIN DSP 복원(또는 대체) + presenter 배선(탭템포 패턴) + 풀스크린 QML 튜너 화면. (오디오버퍼 파이프는 아이캔디와 공유.)
- [x] **패치/IR 파일 선택기 ✅(2026-06-27, M3.5, 커밋 `e89a458`+`cf0fcfe`)** — FOCUS·에디터 둘 다 구현.
      공유 `qml/PatchPicker.qml` + `presenter.list_patch_files` + `qtview.setPatch`/`update_patch_display`.
      ★mod-ui `fileTypes`=카테고리명→`configs.PATCH_FILE_TYPE_EXTS` 매핑. 상세는 에디터 섹션 M3.5 / [[param-vs-patch-set]].
- [x] **풋스위치 모드 스펙 재정의 ✅(2026-06-26)** — mode 0(NAVIGATE)는 **전체 페달보드 라이브러리** 순회
      (`get_all_pedalboards`, 기존 뱅크 한정→전체). mode 2(BANK)는 **RECALL 폐기 → 뱅크 페달보드를 풋스위치에 바인딩**:
      뱅크 자체를 고르는 게 아니라, 활성 뱅크(`current_bank`, 이제 **뱅크 매니저**(`set_active_bank`)가 구동 — 아래 ✅)의
      **첫 4보드를 FS0~3에 직접 바인딩**(`get_bank_pedalboard_entries`) → 밟으면 그 보드 로드. 뱅크 없으면 토스트+mode 1 복귀.
      스트립이 바인딩된 4보드명+"●현재" 표시. 포커스 중 FS PB변경 시 오버뷰 복귀(`_return_to_overview`).
      옛 `recall_pb_ss`/`assign_pb_ss_to_footswitch`는 죽은코드로 잔존(Tier 3 정리).
- [ ] **STOMP 스트립 캡션 일치** — [`qtview.py:351`](../qtview.py) 스트립이 **첫 4개** 이펙트를 보여주는데
      presenter는 **카테고리필터 [0,1,-2,-1]**을 토글([`presenter.py:427`](../presenter.py)) → 캡션이 실제 토글대상과 다름. presenter가 선택 4개를 노출하도록.
- [ ] **스냅샷 브라우저 / 페달보드 브라우저(오버뷰)** — 이름으로 점프. 데이터·백엔드 있음(`get_snapshot_list`+`load_snapshot`,
      `get_pedalboards_in_bank`+`set_pedalboard`) → 리스트/모달 UI만. **에디터 안에는 이미 보드 스위처·스냅샷 관리 있음(M6a/c)** →
      오버뷰로 끌어오는 작업(에디터 후속 "오버뷰에서도 보드 매니저"와 동일). 현재 오버뷰 헤더는 라벨+prev/next만.
- [x] **페달보드 다른이름 저장 ✅(M6b, 커밋 `9a28727`)** — `modepctrl.save_pedalboard_as`(asNew=1, dir=symbolify(title)=부패면역) +
      에디터 SAVE AS UI. (오버뷰 헤더에서의 PB save-as 노출은 위 "오버뷰 보드 매니저" 후속에 포함.)
- [x] **스냅샷 SAVE / SAVE AS / EDIT 버튼 + SAVE AS 네이밍 모달 ✅(2026-06-26)** — 오버뷰 헤더에 3버튼. SAVE=
      `save_snapshot`, SAVE AS=**3+2 네이밍 모달**(무대용어 칩 탭→`Drive-cupcake`식 제안[중복회피 무작위 접미사],
      제안 탭 저장/칩 재탭 재롤/✎ HW키보드 직접입력/취소). 접미사 풀=외부 `resources/snapshot_words.txt`(Hunspell 6천단어,
      lazy-load+모듈캐시). EDIT=실 페달보드 에디터(M1~M6d 완료, 위 섹션). 신규 **토스트 시스템**(`view.show_toast`+QML 자동소멸).
- [ ] **볼륨페달**(ADS1115→MIDI CC) — [`volumepedal.py`](../volumepedal.py)는 독립 프로세스로만 존재, 앱 폴링 미통합, 화면 미터 없음.
      ★먼저 정의할 미결 스펙: **페달이 물리적으로 미연결일 때 앱 거동**. 코드개선(미적용): 단발→연속모드, 860→64~128SPS, EMA+히스테리시스로 CC 지터 제거.
- [ ] **모멘터리(홀드) 모드** — [`presenter.py:365`](../presenter.py) 폴링이 릴리스엣지 전용 → press-ON/release-OFF 모멘터리 없음.
- [ ] **Bypass-all / 전역 풋스위치 액션** — presenter에 `bypass_all()` 없음.
- [ ] **확장 콤보** — [`presenter.py:408`](../presenter.py) A+B/B+C/C+D 외(A+C·A+D·B+D·3중)는 "Invalid". 콤보→액션 맵 리맵 가능화(→ [`config-todo.md`](config-todo.md)).
- [ ] **이펙터 프리셋** — 블록 단위 설정 저장/불러오기. **진짜 신규**(패치파일 IR/NAM 로딩과 다른 개념).
      ★M7로 확인됨: mod-ui `get_plugin_info`가 프리셋 `{uri,label}` 리스트 제공 + `/effect/preset/load` 적용 엔드포인트 존재 →
      "지원 여부" 열린결정 해소. M7이 이름 공급, 적용 래퍼는 에디터 후속(위 에디터 후속 섹션).
- [ ] **이펙터 타입 구분(model vs param)** — 앰프/NAM(모델 줄 크게) vs 컴프/게이트(노브만). `patches` 유무/카테고리로 도출 — 모델에 작은 플래그.
- [ ] **LED 정상상태 색** — HW가 red/blue/purple 지원([`fsledctrl.py`](../hardwares/fsledctrl.py))인데 지금은 누를 때 blink만 → 할당/포커스 상태에 따라 **색을 켜둔 채 유지**로.

**화면 구조 (시안 = 상태기반 전환; 현재 = overview/focus/taptempo 3화면만)**

- [ ] **뷰 라우터 / 화면 상태머신 보강** — `view.screen` 프로퍼티로 3화면은 전환되나([`qtview.py:41`](../qtview.py)) **모달**(menu/keyboard/browser/toast)이 없음. 상태머신 확장.
- [ ] **메뉴(☰) 화면** — 3층위 저장/불러오기. 현재 스냅샷 save/saveas만.
- [x] **토스트 / 온스크린 알림 ✅(2026-06-26)** — `QtView.show_toast`+`toastRequested` 시그널 + QML 자동소멸 오버레이(2.6s).
      presenter `_notify()`가 사용(Kivy 가드). 뱅크 없음 등 메시지에 쓰임. (presenter의 잔여 `print`는 점진 이전.)
- ~~**인앱 키보드**~~ **폐기(2026-06-28).** 주 용도였던 PB/스냅샷 저장시 이름입력은 **이름추천기**(스테이지 단어 칩→제안,
      `Drive-cupcake`식)로 해결됨 + 필요시 연결된 **HW 무선 키보드**가 폴백. 온스크린 키보드(wvkbd/커스텀 QWERTY) 불필요.
      잔재 `toggle_keyboard`(wvkbd, [`presenter.py:477`](../presenter.py))는 Qt 경로서 미호출 죽은코드 → Tier 3 삭제 대상.

> 시안 화면 매핑(참고): Overview·Focus·TapTempo·Toast=구현됨 / Tuner·Menu·Browser=미구현 / **Keyboard=폐기**(이름추천기로 대체) / HW 풋스위치 행=스트립으로 존재.

## Tier 3 — 정리 / 폴리시

- [ ] **WebUI 경로 통째 삭제** — `open_webui`/`close_webui`([`presenter.py:481`](../presenter.py),[:497](../presenter.py)) +
      `xdotool`([:519](../presenter.py)) + `minimize`/`restore`/`enable_webui_button`([`qtview.py:228`](../qtview.py) 등 `pass`) + Kivy bezel 버튼.
      **Qt 경로선 호출조차 안 됨(죽은 코드)**, 온디바이스 웹UI는 스펙서 폐기 결정.
- [ ] **죽은 스텁 제거** — `view_mode_change`([`presenter.py:149`](../presenter.py)), `view_update_footsw_display`([:152](../presenter.py)),
      `footswitch_combo_assigns` 빈 dict([:35](../presenter.py)), `boot_lightshow` 주석처리([:582](../presenter.py)),
      `toggle_keyboard`(wvkbd, [:477](../presenter.py) — 온스크린 키보드 폐기로 죽은코드).
- [x] **노드 라벨 겹침 ✅(2026-06-25, 커밋 `b06dbad`)** — 단순 elide 대신 **스네이크 그리드**로 개편(행당 4노드
      170×72, 라벨 2줄 wrap+elide, 세로스크롤 Flickable). 6이펙트 박스겹침0. ★Pi 라이브 육안검증만 추후.
- [ ] **`[undefined]→bool` 경고** — [`main.qml:307`](../qml/main.qml) FOCUS 패치 visible 바인딩, 무해. `!!(...)`로 정리.
- [x] **docstring 'PySide6' 잔존 ✅(2026-06-28)** — 코드는 PyQt6인데 도크스트링만 PySide6였음. `fakehardware`·`backend`·`hardware`·`qtscheduler` 정정 완료(레포 정리 작업 중). FINISHED §2의 역사 기록만 의도적으로 보존.
- [x] **untracked 파일 커밋 ✅(2026-06-25, 커밋 `1074b5e`)** — `qt_smoke.py`(스모크앱, 보존)·`requirements.txt`
      (Kivy 베이스라인 insurance로 보존) 둘 다 커밋. Qt 런타임 deps 별도 핀은 `requirements-dev.txt`(PyQt6 6.4.2)가 담당.
- [ ] **`EffectPort.set_value` 잉여 인자** — [`modepctrl.py:457`](../modepctrl.py) 안 쓰는 `effect_instance`를 받음(self.instance 있음). 무해, 시그니처 정리.
- [ ] **LED 블링크 후 정상색 미복원** — [`fsledctrl.py`](../hardwares/fsledctrl.py) blink 끝나면 OFF, 이전색 기억 없음(cosmetic; 위 'LED 정상상태 색'과 연동).
- [ ] **HTTP 50-왕복 초기화 배칭/캐시** — `initialize_modep_pedalboard`가 포트마다 1요청 → 느린망에서 로드 지연. 배칭/캐시 검토.
- [ ] **플랫 다크 카드 / 좌표계** — QML은 이미 플랫 다크(비트맵 자산 폐기)이나, 시안 800×600 vs 실제 800×480 좌표 일관성 점검.

## 라이브 검증 백로그 (Pi 실물)

- [x] **FOCUS 실백엔드 ✅(2026-06-25)** — 노브 드래그가 실 MODEP 파라미터 바꿈 확인(라이브, 실 호스트).
- [ ] **탭템포 실검증** — 탭→BPM 반영 + LED 메트로놈 + `set_bpm` 동기.
- [x] **역방향 싱크 ✅(2026-06-25)** — 소켓(`/tmp/synapsin.sock`)으로 웹발 PB전환이 앱에 실시간 반영 확인 +
      모니터 피드 `output_set`도 라이브 수신(미터 동작). 한계: MIDI/HMI **직접** 변경은 mod-ui가 notify 안 함(기존 한계).

## 열린 설계 결정

1. ~~**이펙터 프리셋 백엔드**~~ ✅ **해소(M7 조사)** — mod-ui `get_plugin_info`가 프리셋 `{uri,label}` 리스트 제공 +
   `/effect/preset/load` 적용 엔드포인트 존재. LV2 plugin preset을 그대로 쓰면 됨(앱 JSON 자체구현 불필요). 적용 래퍼만 남음.
2. ~~**온스크린 키보드**~~ ✅ **해소 = 폐기(2026-06-28).** 이름입력은 이름추천기+HW 키보드 폴백으로 충분 → 온스크린 키보드 미채택.
3. **케이블 색 의미** — 시안의 CLEAN/DRIVE/FEEDBACK은 **디자인이 만든 의미**, mod는 source→target만 줌. 현재 전부 단색(green). 규칙 정의(카테고리 기반/피드백=사이클탐지) or 단색 유지.

## 폐기 / 재배치 (의도 확정됨)

- **ABCD 버튼** → 시안엔 없음. "포커스 이펙터를 FS에 수동 바인딩"은 FS 설정화면이 대체. 베젤 ABCD 컨셉 폐기 방향. (잔재 정리는 Tier 3.)
- **WebUI(Chromium)** → 온디바이스 폐기 결정(웹UI는 폰/옆 데스크톱 접속). 코드 삭제는 Tier 3.
- **베젤 합성영역**(save/saveas/pb/ss/mode/bpm) → 해체 재배치: 저장/로드→☰, PB/SS 이동→콤보, 모드→FS 설정, BPM→Tap+헤더.
- **패치파일 파일선택기(IR/NAM)** → "이펙터 프리셋/모델 불러오기" 브라우저로 흡수되는 그림.
- **온스크린 키보드(wvkbd/커스텀 QWERTY)** → **폐기(2026-06-28).** 이름입력은 이름추천기(스테이지 단어 칩)+HW 무선 키보드 폴백으로 해결. 잔재 `toggle_keyboard` 죽은코드는 Tier 3 삭제.

## 미래 기능

- [ ] **아이캔디 — 오디오 반응형 캐릭터 애니** — 설계 확정, 엔진 미착수. 튜너 오디오버퍼 재사용. → [`eyecandy_idea.md`](eyecandy_idea.md).
- [ ] **네이밍 리팩터** — Synapse(앱) vs GCaMP6s(박스) 수렴(README 로드맵).

---

## 감사 정정 노트 (재추가 금지 — 오탐이었음)

코드 감사에서 블로커로 잘못 잡혔으나 **실제 코드 검증 결과 정상**인 항목. stale 문서가 원인이니 다시 손대지 말 것:

- **STOMP 클로저 버그 = 오탐.** [`presenter.py:443`](../presenter.py)의 `e0~e3`는 루프변수가 아니라 **서로 다른 변수 4개** → 각 람다가 올바른 이펙트 캡처. 정상.
- **RECALL 실행 = 정상.** 키 'pedalboard'/'snapshot_idx' 통일, `load_snapshot` 사용. (남은 건 등록수단 — Tier 2.)
- **`set_snapshot`(실 백엔드) 불필요.** `recall_pb_ss`가 `load_snapshot`으로 처리, 인터페이스에도 미선언. RECALL 리팩터 시에만 thin wrapper로.
- **WebUI minimize/restore = 블로커 아님.** Qt 경로서 호출 안 되는 죽은 코드 → Tier 3 삭제 대상.

## 참조

- [`qt-migration-FINISHED.md`](qt-migration-FINISHED.md) — 완료된 이주 스택 아카이브(결정·검증).
- [`config-todo.md`](config-todo.md) — 하드코딩→사용자설정 위시리스트(탭템포·콤보·튜너).
- [`eyecandy_idea.md`](eyecandy_idea.md) — 오디오 반응 캐릭터 애니 설계.
- [`ui-design-rules.md`](ui-design-rules.md) — 7" 800×480 2-tier 가시성 룰.
- **시안**: claude.ai/design 프로젝트 `9b9310ef…`("Kivy UI 재구성 방향") — `Pedal Prototype.dc.html`(800×600 인터랙티브) / `Pedal UI 비교.dc.html`(현행+개선안 A~F).
- [`../README.md`](../README.md) · [`../REFERENCES.md`](../REFERENCES.md) — 앱 개요 · 라이브 시스템 레퍼런스.
