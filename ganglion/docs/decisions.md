# Ganglion 구현 결정 로그

시안 2a를 `ganglion/app.py`로 포팅하며 튀어나온 결정들. 진행하며 계속 추가한다.
`[사용자]`=님 판단 필요 · `[구현]`=내가 옵션 정리해 제안 · `[해결]`=정해짐.

상태(2026-07-06): **스파인 + 피커 포팅 완료** — depth 0/−1, 슬롯 메뉴(bypass/remove/back),
SYSTEM, TUNER, COMBO 저장, 노브 focus/lock/adjust, **플러그인 피커(place/replace,
`geco_whitelist.json` 8버킷)**. 라이브 노브 모델 + 7개 화면 렌더 검증.
이후 **구조 리팩터**(입력 state-major 재배치 + `GecoBackend` seam으로 mock 분리 → N) 완료 —
`app.py`는 seam surface에만 의존, 실전 배선 직전.
그리고 **실 배선 시작(2026-07-07 → O)**: `GecoAdapter`가 라이브 MODEP(mod-host/pisound)에 붙어
실 페달보드를 ganglion에 렌더 + set_param/bypass 라이브 조작 확인. `python3 ganglion/app.py --live`.

---

## A. synapse 실 모델 배선 시점 `[사용자]`
~~지금 `app.py`는 자체 `make_board()` + 노브 모델을 씀~~ → **갱신(N)**: 그 mock은 이제 `GecoBackend`
seam 뒤 `FakeGeco`로 분리됨. 실제로는 synapse `model.py`/`modepctrl.py`/`plugincatalog.py`의
**실 페달보드·LV2 플러그인·파라미터 get/set**에 붙어야 함 — 이제 `GecoBackend` surface를 구현하는
`GecoAdapter`(live)를 진입점에서 주입하면 됨. **언제** 붙일지(하드웨어 후 vs 지금)는 여전히 열림.
노브 dict ↔ synapse 파라미터 모델 매핑도 그 어댑터에서.
→ 기본값: 당분간 `FakeGeco`로 스파인 완성, live 어댑터는 별도 단계.
- 하위 과제: **move 실시간 재배선** — C의 move 메모 참조(들고 이동 매 스텝마다
  disconnect/reconnect, 취소 시 원복).

## B. 플러그인 화이트리스트 `[사용자]`
시안 `WL`(카테고리×승인 플러그인) → 이제 `tools/catalog.py`로 큐레이션한
`geco_whitelist.json`(8버킷)을 `load_whitelist()`로 로드해 피커가 사용. URI도 이미 실 LV2 값.
남은 것: 실배선 시 이 URI로 `plugincatalog.py`/`modepctrl.py`에 인스턴스화·파라미터 매핑(→ A/E).
화이트리스트 자체는 언제든 catalog 툴로 재큐레이션 가능(증분 유지).

## C. 스텁된 인터랙션 `[해결]` — 시안 2a 인터랙션 전부 포팅됨
~~피커(place/replace)~~ · ~~move~~ · ~~보드/스냅샷 관리~~ · ~~confirm 오버레이~~.
- **[해결] 보드/스냅샷 관리 + naming + confirm**: 글랜스(depth −1)에서 ENC0 클릭=보드
  관리, ENC1 클릭=스냅 관리 → **sub 서브메뉴**(Save/Save As/Rename/Delete/Back).
  - **naming = synapse 단어장 재사용** [사용자 지시]: 접미사 풀은 **동일 공유 리소스**
    `resources/snapshot_words.txt`(~6k, 캐시) 직접 로드 — synapse 코어 0줄 수정(그 로직은
    순수계층 아닌 qtview/editor_bridge에 이미 각자 복제돼 있음).
    - **보드/스냅 스킴 분리** [사용자]: 둘 다 `용어-랜덤단어`면 위계가 안 살아서 스킴을 나눔.
      **보드 = 스테이지용어-단어**(`Drive-seafloor`), **스냅 = 단어-요일**(`hospital-thursday`).
      → 이름만 봐도 보드/스냅 구분됨.
    - **2인코더 매핑(통일)** [사용자]: **ENC0=범주부 순환**(보드=용어 12개 / 스냅=요일 7개),
      **ENC1 회전/클릭=랜덤단어 리롤**, ENC0 클릭=확정, ENC0 홀드=취소. 범주 변경 시 단어는
      유지(리롤 안 함) — 마음에 드는 단어 두고 용어만 돌릴 수 있음. `name_cats`/`name_build`,
      상태 `ncat`(범주)·`nrand`(단어). NAME 12px 전체표시, 범주부는 칩.
  - **confirm**: Delete → 오버레이(No/Yes). 마지막 1개는 삭제 불가("KEEP 1 MIN").
  - **[해결] 연-인코더가 조작한다** [사용자 버그리포트]: 서브메뉴/confirm은 **그걸 연
    인코더**가 조작한다. 보드=ENC0(글랜스 상단밴드), 스냅=ENC1(하단밴드)로 열리므로
    각각 그 인코더의 회전=이동·클릭=선택. (버그: 스냅을 ENC1로 열었는데 서브에선 ENC1
    클릭이 back이라 튕긴 것처럼 느껴짐.) back은 ENC0 홀드로 통일, 반대 인코더 클릭도 back.
    `_op(which)`로 판별(새 상태 없음), 푸터/LED도 연-인코더 반영.
  - 상태: `sub`/`sub_idx`·`naming`("which:mode")·`nterm`/`nname`·`confirm`("del:which")/`cyes`.
    보드/스냅 이름은 이제 AppState `boards`/`snaps`(모듈 상수 PBS/SNAPS 복제) — 뮤테이션 격리.
    `--walk`(Save As→삭제 시퀀스)·렌더 검증됨. 랜덤은 `_rng`(walk에서 seed).
- 남음(실배선 A): naming 확정 시 실제 페달보드/스냅샷 저장(presenter.save_snapshot 등)에 매핑.
- **[해결] move** [사용자 설계]: 슬롯 메뉴 Move → 레벨0(체인) 복귀, 대상 노드만 5px
  위로 오프셋(들고 있는 듯, 반전 셀). ENC0 회전=인접 슬롯과 swap(전체 체인 재드로),
  ENC0 클릭=그 자리 착지(dirty, "MOVED"), ENC0 홀드=취소(move_from 복원). 하단 패널에
  MOVING/노드명/슬롯/조작 힌트. `moving`/`move_from` 상태, `--walk`·렌더 검증됨.
  - **[사용자 메모] 실배선 시 move 중 재배선은 실시간**: 지금은 board 리스트 swap만
    (드롭 때 커밋 개념). 실 모델 연결(→A) 후에는 노드를 들고 이동하는 **매 스텝마다**
    modep 그래프를 disconnect/reconnect 해서 순서 변경에 따른 음색 변화를 즉시 들을 수
    있게 한다. 취소(홀드) 시엔 원래 배선으로 복원. → move 커밋/취소를 실 그래프 연산에
    매핑하는 게 A의 하위 과제.
- **[해결] 피커(place/replace)**: `geco_whitelist.json`(큐레이션 8버킷) 로드.
  **상하 분할 레이아웃** [사용자 요청]:
  - 위: 노드 체인 — 대상 슬롯을 dashed 셀로, 들어갈 카테고리 약어 미리보기(라이브).
  - 아래: 좌(카테고리 약어 스트립)·우(플러그인 스트립). 포커스=채운 박스, 잠금=빈 박스.
  - **ENC1 전담**: 회전=스크롤, 클릭=select(cat→fx→배치). **ENC1 홀드=없음**.
  - **ENC0 홀드=백** (일관성; fx→cat→나가기). ENC0 회전/클릭=무동작.
  `_pick_chain`/`_striplist`/`_fit`(폭 맞춤 잘림). 배치 노드는 버킷별 **플레이스홀더
  노브 템플릿**(`_KNOB_TMPL`) — 실 LV2 파라미터 배선은 A/B/E와 함께
  (placed node의 name=display, abbr=버킷 약어). 렌더·`--walk` 검증됨.

## D. 회전 가속(accel)을 값 조절에 반영 `[해결]` (2026-07-07)
[사용자] 값 조절/patch에만 accel. `feed()`가 `_rotmag=max(1,abs(delta))` 저장, 내비/포커스엔
부호(1:1) 전달, `adjust()`가 `mult=d*_rotmag`로 스텝 배율. **노드 이동/노브 포커스=1:1 유지,
값·patch만 가속.** 키보드는 |delta|=1이라 no-op(골든 무영향); 멀티디텐트는 실 인코더(폴 간 pos
delta)에서. 동기: patch 리스트가 수백 개(AIDA-X 323)라 빠른 스핀으로 4/8/12개씩 훑어야 실용적(→ O).

## E. 파라미터 스케일링(선형 vs 로그) `[구현]`
`adjust()`는 (max−min)/40 **선형**. Hz·ms·주파수류는 로그 스텝이 자연스러움.
시안도 선형. → 파라미터 단위별 스케일 곡선 정의할지.

## F. 토스트 만료 → 0.5s 블로킹 splash `[해결]`
시안은 토스트를 ~1.3s 후 자동 제거. **[사용자] 임베디드 스타일이니 링거링 토스트+만료
대신, 확정 피드백(SAVED/MOVED/placed)은 ~0.5s 블로킹 splash**(그 프레임 한 번 그리고
블록 후 복귀, 그 동안 입력 삼킴)로 간다. 만료시킬 상태가 없어 더 단순.
- 착각 정정: "타이머/스케쥴러 없음" 전제는 원래 불가 — 롱프레스/콤보 판정이 `now`를
  요구하고(GestureRecognizer.update(now,…)), seesaw는 INT 안 쓰면 폴링 필요. 즉 연속
  폴 루프는 어차피 있고(스케쥴러 객체 아님, `while: poll; render`), 시간 관련은 공짜로 얹힘.
- **경계**: splash의 sleep/블록은 **런타임 루프·디스플레이 계층**에만. 순수 `AppController`는
  `st.toast` 메시지만 세팅(`--walk`/테스트 순수성 유지). 루프가 splash 여부·지속을 결정.
- → J(메인루프)에서 흡수. 지속 상태표시(확정 아님)엔 splash 안 씀.

## G. 무조작 자동 진입(스크린세이버) `[사용자]`
시안 언급: 10초 무조작 → 깊이 −1 자동 진입. 유지할지, 시간값.

## H. 실시간 데이터 소스 `[구현]`
현재 레벨미터(IN −14.2/OUT −4.3)·튜너 cents가 하드코딩. 실제로는 `monitorfeed.py`에서.
→ monitorfeed 배선 + 갱신 주기(코스트 모델상 좁은 밴드는 저렴).

## I. RGB LED 색 팔레트 `[사용자]`
`leds()`가 색 **이름**("amber","green","red","purple","blue","grey","off") 반환. NeoPixel엔
실 RGB 튜플 필요. 정확한 색상값·밝기(주간 시인성)·off 처리. → 팔레트 값 확정.

## J. 메인루프 구조 `[해결]`
`ganglion/runtime.py`: `Runtime.step()` = source.poll(now) → controller.feed →
view 그리기 → (토스트 있으면) F의 0.5s 블로킹 splash → clear → tick sleep.
모두 주입(source/sink/clock/sleep)이라 **fake clock으로 헤드리스 테스트 가능**(순수
컨트롤러는 I/O·시간 무지). 심: `source.poll(now)->events`, `sink.show(frame)`,
`led_out((c0,c1))`. 드라이버 둘: `run_terminal`(키보드+터미널, dev),
`run_device`(seesaw+luma SH1107, 온메탈 — seesaw처럼 lazy import 스텁, 미검증).
`app.py --looptest`가 루프+splash를 fake clock으로 검증(SPLASH-OK). monitorfeed
갱신(H)·LED 팔레트 실값(I)은 배선/하드웨어 때 이 루프에 얹음.
- 남음: monitorfeed 틱(H), 스크린세이버 무조작 진입(G)을 step에 추가.

## K. UI 워크플로우 검토 (Claude Design 스터디) `[진행]`
시안 2a 상태머신을 훑어 quirky 7개(Q1–Q7) 도출 → `docs/workflow-review-todo.md`.
적용 결과:
- **Q1** TUNER: 아무 press로 빠른 이탈 유지, 푸터 `press exit`로 정합. `[해결]`
- **Q2** SYSTEM 발견성: node0에서 좌측에 `<SYS` 힌트 셀 노출(웜홀 진입 유지). `[해결]`
- **Q4** SLOT MENU·SYSTEM 회전을 ENC0로 한정(다른 모달과 일관). `[해결]`
- **Q5** SLOT MENU Remove hover 시 위험색(red)을 커밋손 ENC0로 이동(CONFIRM과 통일). `[해결]`
- **Q6** 모달 내 ENC1 hold=예약(튜너 삼킴)은 의도로 확정, 문서화. 코드 변경 없음. `[해결]`
- **Q7** COMBO 저장이 depth를 GLANCE로 강제하던 것 제거 → 현재 depth 유지, splash만. `[해결]`
  - 부수: `--walk`가 이 강제-glance의 우발적 재동기화에 의존하던 잠재 버그(초기 slot-menu 단계가
    보드 노드 추가 후 Move로 밀려있었음) 노출 → walk의 stray `t` 제거로 정합. 런타임 무관.
- **Q3** 스냅 관리 조작손(E1→E0) 튐: **[사용자] "요일은 시스템 날짜 자동, enc1만 사용"** 채택. `[해결]`
  스냅 naming = ENC1 단일손(리롤·확정·취소), 요일 자동(day_provider 주입, 컨트롤러 순수성 유지).
  보드는 현행(E0 term 다이얼) 유지. confirm 취소도 `_op`로 라우팅. **리스크: rpi RTC/NTP 없으면
  요일 어긋남(라벨용, 비치명) — 하드웨어 때 RTC 확인.**

## L. 인코더 레일 인디케이터 (Claude Design 스터디) `[해결]`
화면 좌측 3px 엣지 레일 = ENC0(위)/ENC1(아래) 상시 인디케이터 → `docs/encoder-rail-todo.md`.
"어느 인코더를 언제 쓰나 / 스크롤 필요 순간이 헷갈린다"는 워크플로우 검토 발견의 시각적 해소.
- `rails(st)`(상태→(z0,z1) 분류, 데이터는 이미 AppState에 있음) + `_rail()` 렌더러를 `render()`
  래퍼가 `_frame()` 위에 오버레이. 존 상태: off/idle/list(썸)/solid. 정적만 → 갱신부담 0. 순수 흑백
  (색은 LED). 위험색은 레일 제외.
- 재배치: `_chain`(노드스트립/IN/<SYS/노브col0 +3px), `_menu`(패널 x0→x4), `_pick`(카테고리
  스트립 x0→x5). 디덥: GLANCE `dots()` + PICKER `_caret` 제거(레일이 단일 스크롤 진실).
- 손바뀜 가시화: MOVE=(solid,off) 위손 · PICKER/NAMING(snap)=(off,solid) 아래손. PNG 렌더 검증.
- **[사용자] 존 분할 = 콘텐츠 분할선 추종(`_rail_split`)**: 체인 노드:노브 ≈ 3:7인데 1:1 레일이
  안 맞는다는 지적 → 체인/move=y40 · glance=y56 · 모달=y64(~1:1). design의 물리-1:1에서
  콘텐츠-정렬로 트레이드(각 화면 레일이 자기 콘텐츠 옆). 체인 존비 35:83≈3:7 렌더 검증.
- 남음: 패널 실측(디더 명도), TUNER 레일(E0-solid)↔Q1(아무 press 이탈) 정합은 Q1 재검 시.

## M. 노드→SYS 진입 가드 (엣지 디텐트) `[해결]`
[사용자] 첫 노드에서 ENC0를 드르륵 굴리면 첫 노드에 멈추고 싶어도 SYSTEM으로 워프해버림.
→ 왼쪽 끝을 넘으면 **곧바로 진입하지 않고 `sys_focus`(SYS 진입 포커스)로 멈춘다**. 실제
진입은 **E0 클릭**으로만. 빠른 스핀이 엣지에서 정지 → 우발 이탈 방지.
- `AppState.sys_focus`: 파킹 상태. rot: 왼쪽 끝 넘으면 `sys_focus=True`(진입 X). 파킹 중
  ENC0-right=체인 복귀(node0), 왼쪽=벽, ENC1=무동작. click ENC0=SYSTEM 진입. hold=glance.
- 화면 `_sys_focus`: "CHAIN EDGE" + `< SYSTEM` 하이라이트 칩 + 안내(click 진입/turn 체인/hold glance).
  레일=(solid,off), LED=(grey,off). Q2의 `<SYS` 힌트가 이 파킹 상태로 이어진다.
- 검증: 6틱 좌스핀 → node0+파킹(sys 미진입), E1 무동작, 우회전 복귀, click 진입, hold glance.
  `--walk` r→sysf=1/sys=0, w→sysf=0/sys=1 코헤런트.

## N. GecoBackend seam — mock/live 분리 `[해결]` (2026-07-06)
`app.py`에 박혀 있던 가짜 페달보드/플러그인/persist를 `ganglion/geco_backend.py`의 **seam** 뒤로
분리. synapse `backend.py` 패턴 이식 — 컨트롤러/Mode/뷰는 `GecoBackend` surface에만 의존하고,
데이터 출처(fake/live)는 **진입점에서 갈아끼우기만** 하면 됨. A(배선 시점)의 "어떻게/어디서"를 확정
(언제는 여전히 A의 `[사용자]` 판단).

- **패턴(synapse 관찰)**: `backend.py`=추상 surface(계약+`NotImplementedError`) · **구조적 타이핑**
  (실물은 상속 안 함, 이름/계약만) · **오브젝트 seam(와이어 아님)** · `modepctrl.get_backend/
  set_backend` 주입 · `qt_main`(real, fake 0)/`qt_dev`(fake) **진입점 분기**. 우리도 동형.
- **surface**(`GecoBackend`): reads `board()/boards()/snapshots()/catalog()` ·
  뮤테이션 `place/remove/move/set_bypass/set_param` · persist `save/save_as/rename/delete`.
  계약: 뮤테이션 `None`=성공/else 에러문자열, `save_as`/`delete`는 인덱스 반환(synapse 미러).
  node/knob/bucket dict 스키마를 모듈 docstring에 명시.
- **상태 소유권 = (a)**: backend가 진실source, `AppState.board/boards/snaps/wl`는 **렌더 캐시**로
  강등(기본값 빈 리스트). `AppController.__init__`이 seeding, 뮤테이션 후 `_sync_board/
  _sync_lists`로 재동기화. 뷰(`f(st)`)는 st만 읽어 **무손상**. `FakeGeco.board()`는 복사본을
  돌려줘 캐시가 진실을 못 건드림(= live 투영과 동형).
- **⚠️ move = 에디터-레벨 계약**: full synapse에서 "순서 변경 → out→in 재라우팅 + 그래프 refresh"는
  backend가 아니라 **pedalboard editor**(`editor_bridge.py` + QML, `_route`/`be.connect`/
  `be.disconnect`/`_rebuild`)가 오케스트레이션. live `GecoAdapter`의 `move`는 이걸 포팅해야 함 —
  backend 원시연산만 보고 새로 만들지 말 것. (fake는 리스트 재정렬로 끝.)
- **이동**: `K/_node/make_board/_empty/_KNOB_TMPL/load_whitelist/make_node/PBS/SNAPS` → seam.
  **유지**: `norm/fmt`(노브 렌더) · `BUCKETCOL`(LED) · 네이밍 워드뱅크(UI 로직). `BUCKET`(dead) 제거.
- **검증**: `--walk`/`--looptest`/뷰 골든(11모드 rails·leds·split·frame-hash)/스택-pop 회귀
  전부 diff 0 — 순수 행동보존 리팩터.
- **남은 것**: (1) live `GecoAdapter` = synapse `get_backend()`/model 위 얇은 어댑터(move는 위 ⚠️).
  (2) effect 채널(toast/persist emit) — 이제 seam이 생겨 진짜 타깃(디스크 persist/param push)이
  존재하므로 live 배선 이음매에 녹이는 게 최적(mock 위 선반영은 시기상조).

## O. Live GecoAdapter — read-side + conform 착지 `[진행]` (2026-07-07)
N의 seam에 라이브 구현체를 붙임. 이 Pi는 살아있는 MODEP/pisound(`jackd`+`mod-host:5555`+`mod-ui`)라
어댑터가 **실제 오디오 그래프**를 편집. synapse 코어 0줄 수정(전부 `ganglion/` 신규).
- **`geco_routing.py`** — Qt-free 라우팅 코어. editor_bridge 순수 로직 포팅: `desired_wiring`
  (=`_quick_wire_keys`+`_connect_audio` 포트페어링) · `reconcile`(=`_reconcile_live_quick`:
  connect-first→disconnect, 호스트-ack 시에만 tracked 갱신) · `host_wiring`. **conform·adapter 공유**
  (메모리 constraint "에디터 참고" 한 벌).
- **`geco_conform.py`** — pre-flight 정규화. **정책[사용자]**: whitelist에 없는 플러그인 = 사용자가
  배제한 것 → **파괴**(remove_effect); MIDI/CV-only도. 생존자를 정규 quick 배선으로 reconcile →
  `_quick_representable` 통과 보장. dry-run 기본, `--apply`(라이브)/`--save`(디스크) 분리.
  실 보드 Crunch 0에 적용 검증: CfgStereo(uncatalogued) 파괴, 미터 탭 재홈, 멱등 확인.
- **conform-on-load[사용자]**: 대량 pre-flight-sanitize 폐기(ttl 파서 부담·실익 적음). 대신 보드가
  current 되는 순간(런치+`select_board`) **싼 검증 → 표현불가일 때만 파괴/재구성**. non-representable
  보드를 렌더할 일이 원천 차단. (`--all` 배치 영구화는 선택적 위생, 미구현.)
- **`geco_adapter.py`** — `GecoAdapter(GecoBackend)`. reads: synapse `model.Pedalboard`→geco dict
  (uri→whitelist로 bucket/abbr/display, widget_kind→k, scale_points→라벨). 캐시된 Pedalboard=읽기 투영
  (상태소유권 a), param/bypass는 in-place 갱신(노브 1틱=호스트 1콜, 풀 재빌드 회피). `app.py --live`로 주입.
- **검증**: 실 보드 렌더 OK, **set_param·set_bypass 라이브 조작 성공(소리 변화 확인)**. FakeGeco 경로 무손상.
- **남은 것(백로그)**:
  - 그래프 뮤테이션 `place`/`move`/`remove` `[해결]`(2026-07-07): routing 코어 경유.
    `_pb.effects`가 순서 authoritative 리스트(board/set_param이 인덱싱), 뮤테이션이 이걸 바꾸고
    `_reconcile`(desired_wiring→host diff)로 라이브 재배선. **move**=pop/insert+reconcile
    (per-detent = C의 "이동 매 스텝 실 그래프 재배선" 실현), **remove**=remove_effect+갭 브릿지,
    **place**=라이브엔 빈 슬롯 없어 **replace-at-slot**(add→remove old→rewire). 라이브 검증:
    AIDA-X↔Cab swap 라운드트립 배선 완전복원, Click remove, EQ→BandPass 교체(모노 1→2 팬·탭 정확).
    - **IN=mono L(capture_1)** 확정[사용자, 기타]. **메모**: 나중에 시스템설정에서 스테레오 입력
      선택(그때 `_reconcile`의 in_mode 파라미터화).
    - **net-new 노드 삽입** `[해결]`(2026-07-07): place=replace뿐이던 갭 해소. UX 결정 —
      라이브는 가변 길이(remove 시 체인 축소, 빈 슬롯 없음)라 trailing 빈 슬롯을 가짜로 넣으면
      Move/인덱싱과 충돌 → **슬롯 메뉴 "Insert" 액션**(포커스 노드 **뒤에** 신규 splice)으로 결정.
      picker+reconcile 재사용, 위치는 기존 Move. `GecoBackend.insert(at,bi,pi)` 신설
      (Fake=list insert, Adapter=add_effect→`_pb.effects.insert(at)`→`_reconcile`). 앱: `inserting`
      플래그로 picker 커밋을 insert/place 분기, 커밋 후 신규 노드로 focus 이동. 라이브 검증:
      Exct-NAM-Widr(7노드)에 3BandEQ를 idx1 삽입→8노드·직렬 in+out 배선 확인→번들 재로드 복구.
      **메모**: Insert=after-only(맨 앞은 Move로). 빈 체인(0노드) 삽입 진입점은 후순위.
    - 성능 메모: move가 per-detent full reconcile(dump_graph GET/detent). tracked-set 유지로 최적화 여지.
  - persist `[일부 해결]`(2026-07-07):
    - **save/save_as** 착지 — board=`save_current_pedalboard`/`save_pedalboard_as`,
      snap=`snapshot_save`/`snapshot_save_as`. save_as는 새 항목 인덱스 반환. board save_as 라이브 검증.
    - **rename/delete 갭 해소** — 정찰 결과 삭제/리네임은 **포크 mod-ui**(mod-tweaks)에 엔드포인트가
      있고 modep 권한으로 도는데 modepctrl이 안 감쌌을 뿐. **공유 modepctrl.py 확장**(첫 synapse-core
      확장, [[logbook]] 기록): `snapshot_rename`·`snapshot_remove`·`remove_pedalboard`.
      snap rename/delete = 어댑터 배선+라이브 검증. `remove_pedalboard`는 **현재 로드 보드 못 지움** →
      board delete/rename은 `select_board`와 함께(아래).
    - **select_board/select_snapshot 착지** `[해결]`(2026-07-07): `GecoBackend.select(which,idx)`
      +`current(which)` 신설. board=`set_pedalboard`(/reset+load_bundle)→성공시 `_load_current`
      (conform-on-load 훅 발화), snap=`load_snapshot`+투영 재빌드. `current`=host 조회 매핑
      (`get_current_pedalboard`→entries 인덱스 / `get_current_snapshot`). glance UX[사용자 결정]:
      **2-단계 제스처** — 하이라이트≠로드 시 클릭=**로드**, 로드된 것 재클릭=관리 서브메뉴(Save/…/Delete).
      상태에 `pb_cur`/`snap_cur`(로드된 인덱스) 추가, glance 뷰에 로드 마커(우측 사각)+LOAD/manage 힌트.
      이 게이트 해소로 **board rename**(save_as+remove 합성; 2-단계가 idx==current 보장)·**board delete**
      (이웃 보드로 먼저 전환 후 `remove_pedalboard`)도 어댑터 배선 완료 — **둘 다 실기 육안검증 완료**
      [사용자, 2026-07-07]. --walk에 board/snap 로드→관리 전 구간 추가(회귀+신경로 검증).
      - **라이브 검증**(2026-07-07, 실기 pisound/MODEP up): `current()` 인덱스 매핑 실 host 일치
        (board=bundle 비교, snap=`get_current_snapshot`가 **이름** 반환→list dict 매핑). board/snap
        select 가역 라운드트립 `select()`↔`current()` 정합. 원상복구.
      - **스냅 재홈 버그**(라이브서 포착·수정): 보드 로드(`set_pedalboard`)는 host가 그 보드의 current
        스냅으로 리셋 → 로드 후 `snap`/`snap_cur`가 옛 인덱스로 stale. 보드 전환 모든 경로
        (`_select`·board save_as/rename/delete)에서 `_rehome_snap`(=`current("snap")`)으로 재홈.
        **부수 효과**: 스냅 적은 보드로 전환 시 `st.snaps[st.snap]` IndexError 크래시도 차단.
      - **stale 스냅 패널**(사용자 지적): 하이라이트≠로드 보드일 때 아래 스냅 목록은 로드된 보드 것 →
        ENC1 무작동(rail `off`, 회전/클릭 inert), 뷰는 "— load board first —". 로드/복귀 시 재활성.
  - **patch 디렉터리 재귀** `[해결]`(2026-07-12, 버그): `--live`에서 **NAM 모델이 2개밖에 안 보였다**
    [사용자]. `_dirlist`가 `os.listdir`+`isfile`이라 **하위 폴더를 통째로 못 봤다** — 정작 라이브러리는
    폴더 안에 있다: NAM = 최상위 2개 + 12폴더 **231개**, Reverb IRs = 7 + 1폴더 **141개**,
    Cab IRs 21→36. (Aida만 평면 323이라 멀쩡해 보였던 것.) → `os.walk`로 재귀, **디렉터리 상대경로**
    반환(`Driftwood/Tudor N …nam`). 상대경로라 `os.path.join(file_path, name)`(set_param)이 그대로
    유효하고, 정렬하면 폴더별로 묶이며, 이름에 폴더가 붙어 동명이 구분된다(2×1 셀 + marquee가 받아줌).
    현재값 매칭도 `basename` → `_rel()`(상대경로)로 교체 — **중첩 파일은 basename 매칭이 실패해
    무조건 인덱스 0을 가리키고 있었다**(엉뚱한 모델이 현재값으로 표시됨).
    **라이브 검증**: 실 보드에서 NAM 231개 인식 + 현재 모델 인덱스 154 정확히 지목, 중첩 경로
    `set_param` 왕복(mod-host가 중첩 절대경로 수용 확인) 후 원 모델로 원상복구. Cnv Loader의
    IR File은 734개(폴더 프리픽스로 구분됨) — D의 회전 가속이 여기서 값을 한다.
  - **patch 위젯** `[해결]`(2026-07-07): NAM/AIDA-X 모델·Cab IR = LV2 patch. 어댑터가 patch를
    **최상단 `k="file"` 노브**로 투영(옵션=디렉토리 리스트, 캐시), 회전=`patch_set`로 그 자리 교체
    (모달 없음). D 가속으로 수백 목록 훑기. 라이브 검증(AIDA-X 323모델 cycle/+12 점프/복원).
    [사용자] 큰 2열 위젯은 완화(현재 반칸+trunc로 족함, 정밀표시는 marquee로).
  - 뷰 폴리시[사용자]: **노브명 폭 trunc 착지**(`_fit`); **장기=marquee 스크롤**(긴 patch/param명·
    페달보드명 공통). 남음: 노브 focus 스크롤(7+ 노브 시 화면 밖) · 미터/메트로놈 탭이 체인 노드로
    노출(숨김/배지?) · Utils 약어 뭉침(per-plugin 약어) · 키보드 타이밍-accel(하드웨어 전 테스트용, 선택).
  - IN/OUT 헤더 레벨 하드코딩(H, monitorfeed 미배선).

## P. 노브 그리드 — 패치 2×1 + 행 스크롤 `[해결]` (2026-07-12)
[사용자] "패치(NAM 모델·Cab IR)는 다른 노브보다 2배 부동산이 필요하다. 2×3 그리드에서 패치만 2×1로
표시될 수 있나?" → **된다. 그리고 반드시 해야 한다** — 실측이 결정적이었다.

- **근거(실측, `/var/modep/user-files`)**: 어댑터가 `scale`에 넣는 실제 파일명(확장자 제거)을
  각 셀 폭에 `_fit`해봤을 때 **전체표시되는 비율**:

  | 소스 | 개수 | 이름 길이(중앙/최대) | 반칸 52px·Silk8 (기존) | 2×1 112px·Silk8 | **2×1 112px·Micro5** |
  |---|---|---|---|---|---|
  | NAM Models | 14 | 13 / 34 | **21%** | 85% | **100%** |
  | Aida DSP Models | 323 | 31 / 52 | **0%** | 3% | **61%** |
  | Speaker Cabinets IRs | 23 | 20 / 30 | **4%** | 52% | **100%** |
  | Reverb IRs | 8 | 12 / 22 | **12%** | 75% | **100%** |

  반칸엔 **7글자**밖에 안 들어간다(`Helga B 5150 BlockLetter - Boosted` → `Helga B`). 패치 반칸은
  사실상 정보 0이었다. → **패치 = 전체폭(2×1) + 값 줄만 Micro5 티어**로 확정. 라벨("Model"/"IR")은
  짧으므로 Silk8 유지. 남는 AIDA 39%는 marquee 몫(로드맵 ③).
- **행 패킹 레이아웃**: 고정 2×3 격자(`knobs[:6]` — **7번째부터 잘려나갔다**)를 폐기하고
  `knob_rows(knobs)`로 행을 싼다 — `k=="file"`은 한 행을 통째로, 나머지는 반칸 둘씩. 어댑터가
  patches를 ports보다 먼저 emit하므로(`geco_adapter.py:_node`) 패치는 자연히 최상단 행에 온다.
- **스크롤 = 순수**: 창은 기존 `_window(nrows, row_of(focus), 3)`로 **st.knob에서 파생**. 새 상태
  없음 → 뷰는 계속 `f(st)`, `--walk` 결정론 유지. 로드맵 ③의 "노브 focus 스크롤(7+ 노브 시 화면 밖)"이
  이걸로 닫힘.
- **레일 승격**[사용자]: CHAIN의 ENC1을 `idle` → **`list(knob)`**. 스크롤이 생긴 이상 레일 썸이
  "화면 밖에 더 있다"를 알리는 유일한 수단이고, 레일 규약("목록 주역=list")과도 더 맞다. 락=solid 유지,
  노브 0개=off. → [`encoder-rail-todo.md`](encoder-rail-todo.md) 표 개정.
- **부수 수정**: 노드명(16px)이 우상단 약어(x=100)와 **겹치고 있었다**(trunc 부재, 기존 버그).
  긴 패치 플러그인명("NAM Loader"/"AIDA-X")에서 상시 노출 → `_fit(…, 92)`로 차단. 근본 해법은 marquee.
- **검증**: 11모드 뷰 골든 — **`chain`의 레일만 변함**(`idle`→`(2,4)`), 나머지 10모드 프레임 해시
  비트동일. `--walk` 상태출력 diff 0(상태머신 무변경), `--looptest` SPLASH-OK. 실 NAM/AIDA 이름으로
  렌더 육안확인(패치 포커스/락/스크롤/롱네임 4종). **실기 검증은 ① 브링업 때.**

## Q. marquee — 긴 이름 스크롤 + 표시용 시계 `[해결]` (2026-07-12)
128px에 우리가 실제로 갖고 있는 이름이 안 들어간다. P의 2×1이 패치 **값**은 살렸지만 나머지 라벨은
그대로였고, 실측 잘림률은 **보드·스냅명 100% · 노드명 75% · 피커 카테고리 62% · AIDA 패치값 39%**.
`CompAmpCabE`나 `NAM LOA`는 잘린 게 아니라 **정보가 없는 것**이라 marquee로 간다.

- **핵심 문제 = 순수성**: 뷰는 `f(st)`(골든·`--walk` 결정론의 근거)인데 marquee는 시간이 필요하다.
  → **표시용 시계를 상태에 둔다**: `AppState.t`(루프 시작 이후 초). `Runtime.step()`이 그리기 직전에
  써넣고(`st.t = now - t0`), **컨트롤러는 여전히 시간을 모른다**. F의 경계("시간·블로킹은 런타임 계층")와
  같은 결. 루프 밖(`--walk`/골든)에선 `t=0.0` 고정 → offset 0 → **프레임 비트동일**(검증됨).
  대안(뷰 시그니처에 `now` 추가)은 `view(st)` 심을 깨뜨려 기각.
- **모션**: dwell(1.1s) → scroll(24px/s) → dwell → 되감기. `t`의 순수 함수(`_marq`). 머리·꼬리에서
  멈춰 실제로 읽을 시간을 준다.
- **위상 앵커 = 마지막 입력**[사용자, 에뮬 테스트]: 절대시간으로 흘리면 GLANCE에서 마키가 흐르는 중
  ENC0로 다른 보드에 착지했을 때 **새 이름이 중간부터 보인다**(위상이 이어짐). → `AppState.t_mark`에
  마지막 입력 시각을 찍고 위상 = `t - t_mark`(`phase(st)`). 모든 제스처가 모든 이름을 머리로 되감는다.
  `feed()` 끝에서 `st.t_mark = st.t` — 시계를 읽는 게 아니라 **이미 상태에 있는 표시용 시계에 앵커만**
  다는 것이라 컨트롤러의 시간-무지는 유지된다.
- **클리핑**: `Screen.Tclip`(render.py) — 텍스트를 maxw 폭 밴드에 오프스크린으로 그려 paste. 글리프가
  박스를 넘어 번지지 못한다(반전 행은 `bg=1`/`fill=0`으로 동일 경로). `Screen.Th(size)`=티어 잉크 높이로
  밴드가 딱 한 줄만 덮게 함(피커 선택 행 박스 안에 들어가는 것 확인).
- **규율[design §2]**: **포커스된 한 줄만** 흐른다 — 매 프레임 애니메이션을 한 페이지 밴드에 격리.
  정적 맥락(비포커스 노브, 비선택 행)은 `_fit` trunc 유지. 이 격리가 곧 ① diff 드라이버가 밀어야 할
  변경 페이지와 정확히 일치한다(지금은 매 틱 풀프레임이라 marquee의 추가비용 0).
- **적용**: 보드명·스냅명(GLANCE 24px) · 노드명(체인 헤더 16px) · 포커스 노브의 이름/값 · 피커 선택 행
  (`_striplist`, 카테고리 16px·플러그인 8px).
- **정정**: 로드맵 최초 집계표의 피커 수치는 틀렸다(호출부 티어·폭 오독 — 8px/56px로 쟀으나 실제는
  카테고리 16px/38px, 플러그인 8px/71px). 카테고리 62%·플러그인 12%가 정확한 값.
- **검증**: 11모드 골든 `t=0` 비트동일, `--walk` diff 0, `--looptest` SPLASH-OK. 실 보드명
  (`CompAmpCabEqRev`)·NAM 플러그인명으로 시간축 필름스트립 육안확인(스크롤·클리핑·되감기).
  **실기 가독성(속도·dwell)은 ① 브링업 때 튜닝.**

## 해결됨 `[해결]`
- **입력 어휘**: 우리 GestureRecognizer(Rotate/Press{click,long}/Combo)가 2a에 정확히 충분. 키보드
  에뮬(r/t/w/e · f/g/s/d · x)이 ENC0/ENC1 rot/click/hold + combo에 1:1 매핑 — 검증됨.
- **깊이 모델**: depth 1 제거(2a), depth 0/−1만. ENC0 hold=줌아웃, ENC1 hold=튜너.
- **폰트**: Silkscreen 8/16/24/32 + Micro5@10 (렌더 검증).
- **화면 렌더**: chain/glance/menu/sys/tuner 라이브 상태에서 검증(`render(state)`).
