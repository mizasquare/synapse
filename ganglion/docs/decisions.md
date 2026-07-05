# Ganglion 구현 결정 로그

시안 2a를 `ganglion/app.py`로 포팅하며 튀어나온 결정들. 진행하며 계속 추가한다.
`[사용자]`=님 판단 필요 · `[구현]`=내가 옵션 정리해 제안 · `[해결]`=정해짐.

상태(2026-07-05): **스파인 + 피커 포팅 완료** — depth 0/−1, 슬롯 메뉴(bypass/remove/back),
SYSTEM, TUNER, COMBO 저장, 노브 focus/lock/adjust, **플러그인 피커(place/replace,
`geco_whitelist.json` 8버킷)**. 라이브 노브 모델 + 7개 화면 렌더 검증.

---

## A. synapse 실 모델 배선 시점 `[사용자]`
지금 `app.py`는 자체 `make_board()` + 노브 모델(K/fmt/norm)을 씀 — 시안 포팅. 실제로는
synapse `model.py`/`modepctrl.py`/`plugincatalog.py`의 **실 페달보드·LV2 플러그인·파라미터 get/set**에
붙어야 함. 언제 붙일지(하드웨어 후 vs 지금), 그리고 우리 노브 dict ↔ synapse 파라미터 모델 매핑 방식.
→ 기본값: 당분간 self-contained 샘플로 스파인 완성, 통합은 별도 단계.
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

## D. 회전 가속(accel)을 값 조절에 반영할지 `[사용자]`
현재 `feed()`에서 Rotate.delta를 **부호로만** 축약 → 1디텐트=1스텝(노드 이동·값 조절 공통).
빠르게 돌리면 큰 스텝(대범위 파라미터 빠른 이동)이 편할 수 있음. 노드 이동엔 1:1이 맞고,
값 조절엔 accel이 유용. → 값 조절만 accel 반영할지 결정.

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

## 해결됨 `[해결]`
- **입력 어휘**: 우리 GestureRecognizer(Rotate/Press{click,long}/Combo)가 2a에 정확히 충분. 키보드
  에뮬(r/t/w/e · f/g/s/d · x)이 ENC0/ENC1 rot/click/hold + combo에 1:1 매핑 — 검증됨.
- **깊이 모델**: depth 1 제거(2a), depth 0/−1만. ENC0 hold=줌아웃, ENC1 hold=튜너.
- **폰트**: Silkscreen 8/16/24/32 + Micro5@10 (렌더 검증).
- **화면 렌더**: chain/glance/menu/sys/tuner 라이브 상태에서 검증(`render(state)`).
