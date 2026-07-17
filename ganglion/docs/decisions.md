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
현재 레벨미터(IN −14.2/OUT −4.3)·튜너 cents가 하드코딩.

> ~~실제로는 `monitorfeed.py`에서. → monitorfeed 배선 + 갱신 주기.~~ **[폐기 2026-07-17]**
> **틀렸다.** `monitorfeed.py`는 mod-ui 웹소켓의 `output_set`, 즉 **LV2 output 포트**를
> 나른다 — 체인에 꽂힌 플러그인의 미터·튜너 값이지 IN/OUT 레벨이 아니다. synapse의
> overview IN/OUT은 **`levelmeter.py`**가 자체 `jack.Client`로 JACK 버퍼를 직접 뜬다:
> IN은 `system:capture_1/2` 탭, OUT은 `system:playback`이 **싱크라 읽을 수 없어서**
> 거기 물린 소스를 미러링(보드/스냅마다 바뀌므로 graph-order 콜백으로 re-tap).
> 튜너는 `monitorfeed`와 **무관**하다 — `cochlea`가 같은 `capture_1`에 자기 클라이언트를
> 띄워 NSDF+HPS로 직접 피치를 뽑는다(`presenter.enter_tuner`, 온디맨드).
>
> 두 문장을 "실시간 데이터"로 묶은 게 오류의 전부였고, 로드맵까지 전파돼 "튜너는
> monitorfeed 배선이 전제"라는 **없는 의존을 만들어냈다**. 실제 의존은 반대다:
> 튜너는 안 막혀 있었고, 오히려 **온디맨드라 안전한 쪽**이다(튜닝 중엔 연주 중이 아니다).
> 어려운 쪽은 **연주 중에 정확히 돌아야 하는** 헤더 미터다.
> [사용자] 헤더 미터는 **필수 — 입력 클리핑 확인용**.

**실제 선결과제 = JACK 클라이언트**(monitorfeed 아님). 그 하나가 헤더 미터와 튜너를
동시에 뚫는다. 온메탈 확인(2026-07-17): `levelmeter.LevelMeter`를 **synapse 코어 0수정**으로
GECO에서 그대로 기동 — 48kHz/blocksize 128, `in_l←system:capture_1`,
`out_l←mod-monitor:out_1`(미러링이 스스로 찾음 — 그래프상 `_3BandEQ`가 아니라 MODEP의
마스터 모니터가 playback 앞에 있다), 무음 IN −59dB/OUT −77dB. `python3-jack-client`(apt)만
있으면 되고 `miza`는 **이미 `jack`·`audio` 그룹**이라 polkit 때 같은 권한 관문이 없었다.

포맷도 새로 정할 게 없다 — synapse `qtview._meter_display` = `"%.1f dB" % 20*log10(amp)`가
헤더의 `-14.2` 그 포맷이고, 바는 `_norm(...,"meter")`로 floor −60dB/ceiling 0dB.
**숫자는 live amp가 아니라 5초 윈도 peak를 쓴다**(synapse `pack()`이 그렇게 한다):
live는 매 틱 −59.2/−59.9/−60.2로 떨려 헤더 밴드를 매번 밀지만 peak는 눌러앉는다.
synapse와 맞추는 게 곧 싼 선택.

남음: `Meter` 심(하드웨어→상태 방향 — `power`/`settings`/`radio`의 반대, `st.t`와 같은 부류) +
`st.inlvl`/`st.outlvl` + `_chain` 렌더. ~~**전제였던 X가 닫혔으므로 인프로세스로 간다.**~~
~~[사용자] 다만 궁극적으로는 성능상 프로세스 분리가 자연스러운 최적화 — 로드맵 ④에 남긴다.~~

**[해결] 2026-07-17 저녁 — 인프로세스로 산다. 라이브 검증 완료.** 배선(d7add74) → 철회(127f1f8,
xrun 688) → **원인이 파이썬이 아니라 유닛의 `LimitRTPRIO` 부재였음이 밝혀져 재배선**. 전말은 X의
"정정의 정정". 최종: `meter = Meter()`, 콜백 스레드 `SCHED_FIFO 90`, xrun 22/10분(= 리그 자신의
베이스라인 ~19와 같은 자리, 남의 클라이언트 0). **실기 헤더**: 무음 IN −59, 드라이브 보드 OUT −14
(게인이 잔뜩 걸려 험노이즈만으로). 프로세스 분리는 **불필요**로 판명 — 로드맵 ④에서 내렸다.

## X. 텍스트 래스터 캐시 — render 8.7ms → 0.26ms `[해결]`
H를 붙이려다 **그 앞에 선 결함**을 만났다. 인프로세스 JACK 클라이언트가 **40 xruns/s**를
냈다. 원인은 I2C가 아니다(DiffSink diff = 0.05ms, 이미 잘 짜여 있다): JACK 주기는
128/48k = **2.67ms**인데 `render(st)`가 매 틱 **8.7ms**의 GIL을 잡았고 cffi 콜백은 GIL을
얻어야 돈다. 콜백은 97% 돌았다 — **못 돈 게 아니라 늦게** 돌았다.

프로파일: 8.7ms 중 **8.2ms가 PIL `Font.render` + `getsize`** — 매 틱 **같은 문자열을 다시
래스터라이즈**. `DiffSink`는 **버스를 아끼지 CPU를 아끼지 않는다.** 33틱/s × 8.7ms =
패널이 켜진 동안 **코어의 29%**를 안 변하는 화면 다시 그리는 데 태우고 있었다. 번인
방어(S)가 패널을 꺼서 이걸 **우연히 숨기고** 있었다(서비스 수명 평균 5.7%) — 전류는
그렇게 파고들었는데 CPU는 아무도 안 봤다.

`_Face`가 글리프 런을 문자열당 한 번 굽고 블릿:

| | before | after |
|---|---|---|
| `render(st)` | 8.73 ms | **0.26 ms** (33x) |
| 틱 전체 GIL | 8.79 ms | **0.32 ms** (JACK 마감의 8배 아래) |

xrun은 **연역하지 않고** GIL 홀드를 스윕해 확인했다(스위치 인터벌 **기본 5ms 그대로**):

| GIL hold/틱 | 8.70ms | 2.67ms | 1.00ms | 0.25ms | 0.00ms |
|---|---|---|---|---|---|
| xruns/s | 40.6 | 8.0 | **0** | **0** | 0 |

0.25ms는 **"아예 안 그리는 것"과 구별되지 않는다.**

> ⚠️ **[정정 — 같은 날 온메탈]** 위 표는 맞다. **거기서 "그러므로 인프로세스 JACK이 안전하다"로
> 간 도약이 틀렸다.** 미터를 실제로 붙이자:
>
> | xruns/10분, 클라이언트별 | 미터 전 | 미터 후 |
> |---|---|---|
> | GangMeter | — | **688** (전체의 97%) |
> | mod-monitor · effect_5/6/8/9 | 3 각각 | **11 각각** (3.7배 악화) |
> | 합계 | ~19 (0.03/s) | ~740 (**1.23/s**) |
>
> **구멍**: `render`의 GIL을 재고 그걸 **"루프의 GIL"로 읽었다.** 아니다 — `source.poll()`이
> seesaw 인코더 2개를 blinka로 매 틱 I2C 폴링하는데 이건 blanked 가드 **바깥**이고 나는 한 번도
> 재지 않았다. **결정적 증거: 패널이 꺼져 `_draw()`도 `meter.observe()`도 안 도는 상태에서
> 비율이 1.17/s로 동일했다.** 드로잉이 범인이었으면 0으로 떨어졌어야 한다.
>
> jackd가 모든 클라이언트를 기다리므로 **우리가 늦으면 리그 자신의 플러그인도 같이 늦는다.**
> `meter = None`으로 철회 → 0.027/s로 복귀(45배). 자세한 건 H.
>
> **아직 모르는 것 (정직하게)**: 이 xrun이 **귀에 들리는지 측정하지 않았다.** 엔진의 "클라이언트가
> 못 끝냄" 회계 이벤트와 ALSA 하드웨어 언더런은 다른 경로다. 남의 클라이언트가 3.7배 늦어진 건
> 그래프가 전진하지 않았다는 강한 정황이지만, 파형 캡처로 확인한 것은 아니다.

> ⛔ **[정정의 정정 — 같은 날 저녁, 측정으로 확정]** 위 정정도 틀렸다. **`source.poll()`은 무죄다.**
> 범인은 파이썬도 GIL도 아니고 **`ganglion.service`에 `LimitRTPRIO`가 없던 것**이다.
>
> 저널이 미터 기동 때부터 말하고 있었다(16:58:24). 우리는 8시간 뒤에 읽었다:
>
> ```
> python[381794]: Cannot lock down 107350048 byte memory area (Cannot allocate memory)
> python[381794]: Cannot use real-time scheduling (RR/90) (1: Operation not permitted)
> python[381794]: JackClient::AcquireSelfRealTime error
> python[381794]: INFO:levelmeter:LevelMeter: active @ 48000 Hz    ← 그리고 "정상"이라 보고했다
> ```
>
> 미터의 콜백 스레드는 **SCHED_OTHER**로 돌았다 — sync(`-S`) 그래프에서 **혼자만 비-FIFO**였고,
> jackd는 모두를 기다린다. 그래서 남의 플러그인이 3.7배 나빠진 것이다. 유닛에 두 줄
> (`LimitRTPRIO=95` / `LimitMEMLOCK=infinity`) 넣고 10분 재측정:
>
> | xruns/10분 | 미터 전 | 미터 (RT 실패) | **미터 (RT 성공)** |
> |---|---|---|---|
> | GangMeter | — | 688 | **22** |
> | mod-monitor · effect_5/6/8/9 | 3 각각 | 11 각각 | **0** |
> | 합계 | ~19 (0.03/s) | ~740 (1.23/s) | **22 (0.037/s)** |
>
> 콜백 스레드는 이제 `SCHED_FIFO 90`(`ps -L -o tid,cls,rtprio`). 미터는 **인프로세스로 살아 있다.**
>
> **위 GIL 홀드 스윕 표(8.70ms→40.6 xruns/s …)는 여전히 맞다. 틀린 건 그걸 미터에 적용한 것이다.**
> 실제로 재보니 그 경로엔 거의 아무것도 없었다 — `tools/gil_probe`(2.67ms 카나리로 GIL 지각을
> 재고, 놓친 마감을 **그 시각에 돌던 구간**에 사후 귀속한다):
>
> | 구간 | wall p50 | GIL 지각 p50 | p95 | >2.67ms |
> |---|---|---|---|---|
> | poll | **33.7ms** | 0.058 | 0.084 | **0** |
> | draw | 6.5ms | 0.059 | 0.309 | 2 |
> | sleep (대조군) | 30.1ms | 0.058 | 0.079 | 0 |
>
> `poll`의 GIL 지각이 **유휴 `sleep`과 같다.** 34ms의 정체는 `adafruit_seesaw`의 `read()`가 거는
> **강제 `time.sleep(0.008)`×4**고, `time.sleep`은 GIL을 놓는다. 콜백 자체도 **0.025ms = 예산의
> 0.9%**, GC는 아예 안 돈다(할당/해제 균형으로 gen0 미트립). **두 가설이 다 측정으로 죽었다.**
>
> 남은 22/10분 = 0.037/s는 **2/3만 주소가 있다.** 패널 상태로 가르면 — 켜짐 232s에 15건
> (**0.065/s**, `draw`가 도는 구간) 대 꺼짐 368s에 7건(**0.019/s**). 차이 **0.046/s**가 프로브가
> `draw`의 꼬리로 잰 크기(0.03/s)와 같은 자리다. 남는 **바닥 0.019/s는 `_draw()`도 `observe()`도
> 안 도는 중에 나므로 아직 우리 것이 아니다** — 미터가 없던 시절 리그 자신의 베이스라인(0.03/s,
> mod-monitor·effect_*에 분산)이 앉아 있던 자리이고, 그 배경 스톨이 이제 그래프에서 **유일하게
> 파이썬인** 클라이언트로 귀속만 옮겨온 것으로 보이지만 — **안 쟀다.** 로드맵 ④에 둘 다 있다.
>
> GIL은 범인이 아니라 **잔당**이고 주소는 `poll`이 아니라 `draw`다 — 다만 **잔당의 2/3만**.
>
> **방법론 (8) — 숫자가 맞는 것은 인과가 아니다.** 이 문단은 처음에 "잔여 = `draw`의 꼬리"라고
> 적었다. 프로브의 0.03/s와 실측 0.037/s가 맞는 걸 보고 **일치를 인과로 읽었다** — 그 10분의
> 대부분은 패널이 꺼져 `draw`가 **돌지도 않았는데**. 드러낸 건 [사용자]의 "dim 전 조작 중에만
> 갱신하면 xrun도 없어지지 않나" 제안이었고, 그 제안 자체는 성립하지 않지만(콜백은 우리 폴링과
> 무관하게 jackd가 부른다) **가드가 이미 거기 있다는 사실이 곧 "그럼 꺼진 동안 난 건 뭐냐"**였다.
> (3)·(7)과 한 가족이다 — 각각 틀린 부분, 틀린 소거, 틀린 일치. 셋 다 측정은 정확했다.
>
> **방법론 (6) — 셸 ≠ 서비스, 세 번째.** `/etc/security/limits.d/audio.conf`의 `@audio rtprio 95`는
> **pam_limits**가 적용하고 systemd 서비스는 PAM 세션이 아니다. 셸에선 `ulimit -r`이 95, 서비스는 0.
> (4)가 이미 "W polkit → H 환경변수"로 두 번을 셌는데, 이번 건 **그 두 번째 사례의 주석 바로 아래**,
> 같은 유닛 파일에서 났다. 병이 같으면 이웃도 의심했어야 했다.
>
> **방법론 (7) — 소거법은 측정이 아니다.** 위 정정은 "패널을 꺼도 비율이 같더라 → 그러므로 `poll`"로
> 갔다. 그 관측은 맞았지만 결론이 틀렸다: 범인이 **루프 안에 없었다**는 뜻이었기 때문이다. 남은
> 용의자가 하나라고 그게 범인인 게 아니라, **용의선상 자체가 틀릴 수 있다.** (3)이 "부분을 재고
> 전체라 불렀다"였다면 이건 "**안 잰 것을 소거로 지목했다**"이다 — 오늘 세 번째로 같은 병이다.
>
> **[사용자]의 원래 조언("성능상 프로세스 분리가 자연스러운 최적화")은 이 건에선 불필요했다.**
> 그러나 그건 조언이 틀려서가 아니라 문제가 성능이 아니었기 때문이다 — 아무도, 나를 포함해,
> 저널 네 줄을 먼저 읽지 않았다.

**유계**(`MASK_CACHE_MAX=256/face`): 앱은 노브 값·dB 수치처럼 **반복되지 않는** 텍스트도
그리므로 그리는 문자열로 키를 잡으면 가동 내내 자란다(숫자 400개 → **+398 엔트리** 실측).
벌크 clear가 아니라 1개씩 축출 — **콜드 캐시는 8ms 프레임, 즉 xrun이다.**

**[사용자] 글리프 아틀라스 제안** ("사이즈도 정해져 있고 ASCII 이상 안 쓰는데 다 구워서
램에 올려도 몇 MB 안 될 것"): 재봤다. 전체 **5,345바이트**(사용자 추정 "수 MB", 내 추정
25KB — **둘 다 틀렸고 실제는 5KB**). 유계여야 한다는 **방향이 옳았고, 그 직감이 문자열
캐시의 무한 증식이라는 진짜 약점을 짚어 위 상한을 낳았다.** 하지만 채택 안 함: 글자별
조립은 advance를 매 글자 반올림해 오차가 누적되고 **15프레임 중 9개가 달라졌다**
(PIL은 문자열을 통째로 놓을 때 advance가 서브픽셀). 0.05ms(0.45→0.40)를 위해 확정된
타이포그래피를 조용히 바꾸는 거래 — 시안을 얼려둔 프로젝트에서 남는 장사가 아니다.

**오라클**: `draw()`는 Pillow 사유 API(`_getink`, `draw.draw_bitmap`)에 닿는다 —
`ImageDraw.text`가 바로 그걸 호출하지만 사유는 사유다. 그래서 느린 경로를 `draw_slow`로
**남기고** `--fonttest`가 전 화면 × t 3값(마퀴 dwell/스크롤/tail)을 픽셀 비교한다.
Pillow가 움직이면 조용히 틀리는 대신 터진다. **테스트가 실패할 수 있는지 1px 어긋남을
주입해 확인**(FONT-CACHE-MISMATCH, exit 1) — 오늘 이미 "실패할 수 없는 테스트"에 한 번
속았기 때문이다(아래).

### 이 결정이 남긴 방법론
1. **틀린 전제가 고른 질문을 재면, 측정도 진다.** 문서가 "monitorfeed"라 적었다는 이유로
   웹소켓을 떠서 `modmeter`를 찾아냈고 — 실측은 맞았지만 **질문이 틀렸다**. 형제 앱이
   IN/OUT을 실제로 어떻게 그리는지 먼저 읽었으면 5분이었다. design.md §2의 "연역이
   측정에 진다"의 새 변종: **측정이 이기려면 옳은 대상을 골라야 한다.** 사용자가 잡아줬다.
2. **통과가 보장된 테스트는 통과해도 아무 말도 안 한다.** 첫 xrun 프로브는 `set_xrun_callback`만
   달고 **process 콜백을 안 달아** RT 스레드에서 아무 일도 안 했다 — 0 xrun이 나올 수밖에
   없었다. `re-show after wake: 0 bytes`(S)와 같은 형태. **프로브가 실패할 수 있는지를 먼저 확인.**
3. **부분을 재고 전체라고 부르면, 측정도 연역이 된다.** (2)에서 "프로브가 실패할 수 있는지"는
   확인했지만 "프로브가 **옳은 것을 재는지**"는 확인하지 않았다. render를 재고 루프라고 불렀고,
   재지 않은 `source.poll()`이 진짜 GIL 홀더였다. **1·3은 같은 병의 두 얼굴이다** — 하나는 틀린
   *질문*, 하나는 틀린 *범위*. 둘 다 측정 자체는 정확했다는 게 함정이다.
4. **셸에서 되는 것은 서비스에서 된다는 보장이 아니다 — 두 번째.** W에서 polkit `allow_active`를
   겪고 `loginctl list-sessions`가 비어 "셸=서비스 컨텍스트"를 확인했는데, **환경변수엔 그 등식이
   성립하지 않는다**: `/etc/environment`는 **PAM이 로그인 세션에** 적용하고 systemd 시스템 서비스는
   읽지 않는다. 셸 프로브는 붙고 서비스는 못 붙었다(H). **온메탈 검증은 서비스 컨텍스트에서.**
5. **[사용자]의 틀린 숫자가 옳은 방향을 실어나를 수 있다.** 글리프 아틀라스 제안의 크기 추정은
   1000배 빗나갔지만(수 MB vs 5,345바이트) "유한하니 유계여야 한다"는 방향이 옳았고 캐시 상한을
   낳았다. **추정치를 반박하고 제안을 버리면 그 방향까지 버린다.**

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

## R. [+] 셀 — 0노드 크래시·삽입 어휘 정리 `[해결]` (2026-07-12)
[사용자] "0노드 진입점이 트릭으로 덮여 있는 게 찜찜하다. 모든 슬롯이 안 찼다면 0노드 앞에
`[new effector +]`를 상시 표시하면 되지 않나?" → **맞다. 그리고 이건 찜찜한 정도가 아니라 크래시였다.**

- **버그(발견)**: 0노드 보드에서 `render`/`rails`/`leds`가 전부 `st.board[st.node]` → **IndexError**.
  라이브 `remove`엔 마지막 노드를 막는 가드가 없다 → **이펙트 1개짜리 보드에서 그것을 지우면 앱이 죽는다.**
  0노드가 "표현 불가능한 상태"였던 게 원인. **가드로 막는 대신 합법적 상태로 만든다**(= [+] 셀).
- **[+] 의사-셀**: 체인 커서 축이 `["head", 0..n-1, "tail"]`(`cells(st)`/`cpos(st)`). 머리와 **꼬리**
  (아웃풋 직전)에 상시. 빈 체인 = 머리 [+] 하나뿐 → 0노드가 평범한 화면이 된다. 파킹 상태는
  `st.add`("head"/"tail") — M의 `sys_focus`(엣지 디텐트) 선례와 동형. **`st.node=-1` 센티널은 기각**:
  파이썬 음수 인덱싱이 조용히 마지막 노드를 반환해 9개 인덱싱 지점이 전부 지뢰가 된다.
  좌측 순서: `[SYS 파킹] ← [+] ← [node0]` (Q2의 웜홀이 한 칸 더 왼쪽으로).
- **삽입 방향[사용자]**: "노드에서 추가하면 뒤에 붙는다"는 절대규칙이 직관적이지 않다 → 방향을 명시.
  **되묻는 모달 대신 슬롯 메뉴를 두 항목으로**(`Add Before`/`Add After`) — 클릭 수가 안 늘고 새 모드·
  레일·LED 대응이 필요 없다. `st.inserting`(bool) → `st.ins_at`(int, -1=replace)로 일반화하니
  메뉴·머리·꼬리가 **한 경로**로 합류. 어휘도 [+] 셀의 "ADD FX"와 통일(Insert는 내부 용어로만).
  → **O의 "Insert=after-only, 맨 앞은 Move로" 갭과 "빈 체인 삽입 진입점 후순위"가 함께 닫힘.**
- **빈 슬롯 폐기[사용자]**: `FakeGeco`만 고정 슬롯+`empty=True` 구멍을 갖고 있었다(라이브는 가변 길이).
  즉 **에뮬레이터에서 실기에 존재하지도 않는 UX("EMPTY SLOT n / add FX")를 테스트하고 있었다.**
  → fake의 `remove`를 pop으로 바꾸고 `empty` 키를 **노드 스키마에서 제거**(죽은 분기가 되살아날 여지 차단).
  이제 에뮬 == 실기. 체인 길이 상한(MAX_NODES)은 **두지 않음**[사용자] — 라이브 그래프에 대응 개념이 없고,
  DSP 한계는 코드가 아니라 소리/xrun으로 드러나는 게 정직하다.
- **피커 미리보기**: `_pick_chain`이 "대상 슬롯"이 아니라 **삽입 후의 체인**을 그린다(새 셀이 끼어들어
  체인이 자라는 모습). 헤더도 INSERT/REPLACE로 갈린다.
- **검증**: 6노드를 전부 제거 → 빈 체인 → [+]에서 재구축까지 크래시 0. `--walk`에 머리 [+]·Add Before·
  Add After·꼬리 [+] 전 구간 추가(인덱스 0/1/끝 정확히 착지 확인). 뷰 골든: 의도한 4모드(chain·
  chain-locked·menu·pick)만 변경 + 신규 3모드(add-head/add-tail/chain-empty), **나머지 전부 비트동일**
  (moving은 [+] 셀을 감춰 원래 프레임 유지 — 들고 있는 노드를 [+]에 내려놓을 수는 없으므로).
  라이브 어댑터 렌더 확인(7노드 보드, 축 9칸). `--looptest` SPLASH-OK.

## S. 무조작 dim/off — 번인 방어 `[해결]` (2026-07-17)

**문제**: 앱이 무조작으로 몇 시간이고 같은 프레임을 켜 둔다. OLED는 점등 시간에 비례해 열화하고
우리 UI는 **정적 furniture가 대부분**(헤더·레일·라벨이 늘 같은 자리) — 번인의 교과서적 조건이다.
다른 미완 항목은 늦어져도 코드가 기다리지만 **이건 늦어진 만큼 패널이 영구히 상한다.**

- **폐기: "10초 무조작 → depth −1"**(시안, 결정 G / design.md 열린결정 #12). 그건 부품이 없던 시절
  "무조작 상태를 뭐에 쓸까"에서 나온 **기능성 탐구 설계**였다. 실물을 단 지금 무조작 상태의 임자는
  번인 방어고, 화면을 끌 거면 그 밑에서 depth를 바꿔 두는 건 의미가 없다(깨어나 맥락만 잃는다).
- **결정: 30초 → dim(`contrast`), 5분 → off(`hide`/`0xAE`).** `off_s=300`은 **잠정** — 살아보고 확정.
- **자리 = `Runtime`, 앱이 아니다.** dim/off는 contrast·0xAE라는 **하드웨어 상태**지 픽셀이 아니다.
  순수 앱에 넣으면 `view = f(st)`가 깨지고 골든·`--walk`가 오염된다. `Runtime.step()`이 이미 시계를
  들고 있어 **`AppState` 필드 0개·뷰 0줄**로 끝났다(`--walk` 전 프레임 비트동일로 확인).
- **`st.t_mark`를 쓰지 않는다.** 그것도 "마지막 입력"이지만 **마퀴 위상 앵커**(결정 Q) — 렌더링
  관심사에 수명 기능을 얹으면 나중에 앵커링을 바꿀 때 조용히 깨진다. 게다가 아래 삼킴 때문에
  `feed()`를 안 타서 애초에 못 쓴다. → `Runtime`이 `_t_input`을 자체 추적.
- **off의 첫 입력은 삼킨다.** 안 보이는 화면에서 노브를 돌려 파라미터가 편집되면 안 된다.
  스플래시(결정 F)의 "입력을 의도적으로 삼킨다"가 선례. dim은 삼키지 않는다(보이니까).
- **off 중엔 `_draw()`를 건너뛴다.** 0xAE는 표시만 끄므로 그리기는 순수 낭비고, 인코더와 **같은
  버스**를 문다. 마퀴가 계속 도느라 매 틱 diff가 나가던 것도 같이 막힌다.
- **dim = `contrast(0x01)`.** design.md §2가 contrast를 `[폐기]`(약한 레버)로 적은 건 **플리커
  대책으로서**다. **번인엔 강한 레버** — 실측 결과 우리 UI의 패널 몫을 **43.9 → 12.2mA(−72%)**로
  깎는다(아래 표). 그리고 같은 실측의 "사용자가 밝기 변화를 잘 못 느꼈다"가 여기선 **요구사항과
  일치**한다(dim 상태는 읽혀야 한다). 같은 측정이 한 결정엔 반증, 다른 결정엔 근거가 된 사례.
- `[정정]` 이 결정을 처음 적을 때 **"floor가 구동 전류를 ~44% 깎는다"고 썼는데 틀렸다.** 그건
  design.md의 **전백** 측정(0x01/0x7F = 49/78mA)에서 **연역한** 값이다. 실측하니 우리 UI에선
  **−72%**로 훨씬 크다. 이유는 §2의 자체 모델과 정합한다: 전백은 charge pump가 이미 포화된
  레짐이라 contrast가 더 깎을 게 없고, 15% 점등·짧은 세로 런인 우리 UI엔 헤드룸이 있어 거의
  선형으로 듣는다. **즉 contrast의 세기는 화면 내용에 의존한다** — 전백 수치로 일반화하면 안 된다.
  이 프로젝트에서 부품 없이 연역한 스펙이 틀린 **네 번째** 사례(주소·회전·버스속도에 이어).
- **`on` = `contrast(0x7F)`** — 우리가 고른 수가 아니라 **luma의 sh1107 init이 세팅하는 값**(소스
  확인). 복귀가 패널 자신의 nominal로 돌아가게 한다.
- **엣지 온리**: 정상 상태에선 1바이트도 안 나간다(`--sleeptest`가 313틱 동안 명령 **4개**를 검증).
- **검증**:
  - `--sleeptest` (페이크 시계): dim@30.0s · off@300.0s · blank 중 frames 정지 · 첫 입력이 깨우되
    `node` 불변(삼킴) · 패널 로그 `['contrast(0x01)','hide','show','contrast(0x7F)']` **정확히 일치**.
  - **온메탈**: 세 명령 모두 I2C 오류 없이 나감, 전환당 0.1~0.2ms.
  - `[결정]` **0xAE는 GDDRAM을 보존한다 — 실물 확인**(hide→show 후 프레임 그대로 살아있음, 육안).
    데이터시트가 그렇다고 **연역만 하고 넘어가면 안 되는** 자리였다: 만약 지워졌다면 깨어날 때
    앱 상태가 그대론 한 diff가 0바이트라 **빈 화면으로 깨어나는** 버그가 됐다(skip-draw가 이 사실
    위에 서 있다). 아니었으므로 wake 시 풀 재동기는 **불필요**.
  - **레일 실측**(PMIC ADC, design.md §2 기법) — 라이브 systemd 서비스를 재시작해 idle을 0에
    맞추고 on/dim/off를 각각 샘플: **165.9 / 134.2 / 122.0 mA**. → design.md §2 "유휴 전력" 표.
    `[주의]` 첫 측정은 **서비스를 켜 두고 문서를 쓰다가** 재는 바람에 "active" 행이 이미 dim이었고
    on→dim이 +1mA(노이즈)로 나왔다. **idle 시계의 0점은 서비스 시작 시각**이라 측정이 그걸
    소유해야 한다(스크립트가 직접 restart 하도록 고침). 무조작 상태를 재는 계측의 함정.

## T. 버그 2건 — 패스스루 소실 · 콤보 저장 `[해결]` (2026-07-17)

둘 다 **사용자에게 거짓말을 하는** 종류라 finalize 전에 닫았다. 공통점: 조용히 틀린다.

**① 패스스루 소실 `[치명]` — `geco_routing.py`**
- `desired_wiring()`의 `if fx:`가 IN→OUT 종단을 감싸고 있어 **트렁크 fx(`ain`&`aout`)가 0개면
  IN이 OUT에 안 붙는다 = 기타 무음.**
- `[정정]` 로드맵 최초 집계는 조건을 "빈 체인/소스만"으로 적었는데 **틀렸다.** 실제 조건은
  **fx 0개인 모든 체인**이고, 여기엔 **탭 전용**(레벨미터 1개: `aout==[]`)도 포함된다 — 탭은
  출력이 없어 playback에 닿지 못한다. 6가지 체인 형태를 경로 도달성으로 재현해서 발견했다.
  (첫 재현 시도는 판정식을 `capture→playback` **직결** 유무로 잡아 전 케이스가 False로 나왔다 —
  이펙트를 경유하면 직결이 없는 게 정상이다. 판정식이 틀리면 버그도 픽스도 안 보인다.)
- **픽스 = 가드 제거 한 줄.** fx가 비면 `prev`가 여전히 `'IN'`이라 그 줄이 **그대로 IN→OUT
  패스스루**가 된다. fx가 있으면 `prev`가 마지막 fx라 동작 불변(불필요한 직결이 안 생김을 검증).
- **왜 회피가 아니라 정면 픽스인가**: 결정 R([+] 셀)로 **0노드 체인이 합법 상태**가 됐다. 이펙트를
  마지막 하나까지 지울 수 있는 UI에서 "빈 체인 = 무음"은 못 쓴다. **페달의 바닥은 패스스루다.**
- **포팅 원본에 같은 버그** — `editor_bridge._quick_wire_keys`에 동일한 `if fx:`가 있다. verbatim
  포팅이라 버그까지 옮겨온 것. 그쪽은 `_quick_representable`이 `'빈 보드'`를 advanced로 보내
  (도크스트링: "empty/passthrough -> advanced (M6d-3 전 무음 회피)") **절반은 알고 있었으나**, 그
  가드는 이펙트 0개만 막아 소스/탭 전용 보드는 통과한다. → 교환일기로 넘김(원본 판단은 그쪽 몫).
  `[주의]` 그쪽 분류기는 `desired == host` **정확 일치**를 요구하므로, 우리만 고친 동안은 소스/탭
  전용 보드가 그쪽에서 **advanced로 강등**된다(무음보다 낫다는 판단).
- **검증**: 6형태 전부 기타 도달(빈/소스만/탭만/fx1/fx2/fx+메트로놈) · fx 있을 때 IN→OUT 직결 없음 ·
  **라이브 보드 conform 드라이런 +0/−0**(fx 4개라 무영향 — 픽스가 정상 보드를 안 건드림을 실증).

**② 콤보 스냅샷 저장이 저장을 안 함 — `app.py combo()`**
- `st.dirty`를 지우고 `"SNAPSHOT SAVED"` 토스트만 띄웠다. **`backend.save()`를 아예 호출하지 않는다.**
  dirty 점까지 지워서 **사용자에겐 저장된 것으로 보이고 작업이 사라진다.** 픽스는 `_sub_act`의
  기존 저장 경로와 같은 seam 한 줄(`self.backend.save("snap")`).
- **`--looptest`가 이미 콤보를 누르고 있었다**(`["t","x","t"]`) — 스플래시만 보고 **결과를 안 봤다.**
  → `_SpyGeco`로 `save calls=['snap']` 검증 추가. 제스처를 태우는 테스트가 그 제스처의 *목적*을
  확인하지 않으면 통과해도 아무 말을 안 한다.
- `FakeGeco.save`는 no-op(픽스처가 RAM)이라 에뮬 행동은 불변 — 골든 무영향.

## U. SYSTEM > Brightness — ENC1 제자리 편집 + `config.py` `[해결]` (2026-07-17)

**먼저 물은 것: 만들 가치가 있나?** design.md §2가 "사용자는 밝기 변화조차 잘 못 느꼈다"고 적어둬서
지각 안 되는 슬라이더면 방금 지운 MIDI Ch와 같은 부류였다. **실 UI에서 재보니 6단계가 확연히
구분됐다** — 그 관찰은 전백 테스트 화면 것이었고, 전류 때와 같은 이유로 틀렸다(§2). 실기능 확정.

- `[결정]` **3단계 `(0x08, 0x2D, 0xFF)`, 기본 mid.** 유효 범위 [0x08, 0xFF](그 아래는 무변화),
  지각이 비율 기반이라 **등비 ~5.6배**로 3점. 구분 가능한 6단계를 다 두지 않는 이유: 한 번
  맞춰놓고 쓰는 설정에 해상도는 값이 없다[사용자].
- `[결정]` **새 모드도 새 화면도 없다 — ENC1이 제자리에서 편집.** 사용자 제안. Q4는 목록 스크롤을
  ENC0 전용으로 했지만("양손 스크롤 제거, 일관성 우선") 그건 **ENC1을 중복 스크롤휠에서 뺀 것**이지
  예약한 게 아니다. ENC1은 여전히 2a §3의 **값 밴드**다. → SYSTEM 항목은 두 종류가 된다:
  **액션**(ENC0 click: Tuner·About·Back) / **값**(ENC1 rotate: Brightness). 체인과 같은 문법
  (ENC0 고르고 ENC1 돌린다)이라 배울 게 없다.
- `[결정]` **어포던스 = ENC1이 값 위에서만 살아난다.** 액션 항목에선 ENC1 레일 `"off"` + LED `OFF`,
  Brightness에선 레일 `(bright, 3)` + LED **green**(=편집, 결정 I). **손으로 종류가 느껴진다.**
  값은 항상 점 3개로 표시(포커스 행은 반전이라 `dots(fill=0)` — `render.dots`에 `fill` 인자 추가).
  회전은 **clamp, wrap 아님** — 값이 최대에서 최소로 튀면 안 된다.
- `[결정]` **앱은 contrast 바이트를 모른다.** `st.bright`는 `BRIGHT_LEVELS`의 **인덱스**고, Runtime이
  `set_on(BRIGHT_LEVELS[st.bright])`로 민다 — **`led_out`과 정확히 같은 모양**(순수 상태 → 주입된
  seam → 하드웨어). 그래서 순수성이 안 깨진다. 새 모드 0개, `AppState` 필드 1개, 뷰는 점 한 줄.
  `set_on`은 **엣지 온리**(매 틱 불리므로 무변화 시 0바이트).
- `[결정]` **`config.py` 신설** — design.md §7이 결정만 해놓고 안 만든 자리[사용자: "매직넘버 말고
  중앙화"]. 진짜 이유는 취향이 아니다: **`0x3D`와 `rotate=0`이 `runtime.run_device`와
  `tools/oled_probe`에 설명 주석까지 복사된 채 두 벌** 있었고, 하필 **계측 도구가 자기 사본을
  읽고** 있었다 — 앱이 쓰는 값과 조용히 어긋날 수 있는 구조. 한 번 틀렸던 적 있고(0x3C) 유리로만
  확인되는 값이라 특히 나쁘다. 지금 config: 패널 주소·회전·밝기 3단계·dim·유휴 시간값.
  seesaw 상수(`hw/seesaw.py` 상단)와 `runtime.LED_RGB`는 이미 각자 응집돼 있어 두었다.
- `[정정]` **`--sleeptest`가 이 변경으로 FAIL 났고, 그게 옳았다.** 기대값에 `0x7F`가 **하드코딩**돼
  있어서, "깨어있음"의 의미가 설정 가능해진 순간 깨졌다. 테스트도 config에서 끌어오게 고쳤다.
- **미완**: **영속화 없음** — 재부팅하면 mid로 돌아간다. 설정 저장소가 로드맵 ①의 선결 항목이고
  `BRIGHT_DEFAULT`가 그때까지의 부팅값이다.
- **검증**: 오프메탈(액션 항목에서 ENC1 무반응 + 레일/LED off · Brightness에서 레일 (1,3)/green ·
  양끝 clamp · SYS 렌더) + **온메탈**(실 Runtime·실 PanelPower로 high→mid→low→high, 사용자 육안:
  "실용적인 수준에서 밝기 조절이 된다"). `--sleeptest`/`--looptest`/`--walk`/`oled_bench` 전부 통과.

## V. 설정 영속화 저장소 `[해결]` (2026-07-17)

로드맵 ①의 **선결** 항목. 없는 동안 Brightness는 매 부팅 mid로 돌아갔다 — 설정이 아니라 장난감이다.

- `[결정]` **`config.py`와 `settings.py`는 다른 물건이다.** 전자는 **코드가 아는 값**(패널 주소,
  구분되는 contrast 바이트), 후자는 **사용자가 고른 값**. 상수는 설정이 될 수 없다.
- `[결정]` **위치 = `configs.LOCAL_STORAGE + "ganglion.json"`** (`~/.modep/ganglion.json`).
  synapse의 `LOCAL_STORAGE`에서 파생시킨 이유가 있다: **`SYNAPSE_STATE_DIR` 오버라이드를 공짜로
  물려받는다** — qt_dev가 fake-backend 실행이 실기 상태를 덮어쓰는 걸 막으려고 만든 그 가드다.
  `configs`는 **지연 import**(라이브러리 모듈이라 sys.path를 entry point만 세운다).
- `[결정]` **온메탈 드라이버만 쓴다.** `run_device`만 `Settings`를 주입 — 터미널/fake 실행이 실기의
  선택을 덮어쓰면 안 된다(위 가드와 같은 이유). `power`와 같은 모양의 seam이라 순수 컨트롤러는
  디스크의 존재를 모른다: `apply(st)` 부팅 시, `observe(st)` 매 틱.
- **이 기기는 종료되지 않고 뽑힌다.** 파워스트립에 물린 기타 페달이라 flush할 정상 종료가 없고 쓰기가
  아무 바이트에서나 잘린다. [`../../docs/save-corruption-postmortem.md`](../../docs/save-corruption-postmortem.md)의
  교훈이 여기 직접 걸린다 — **반쯤 쓰인 파일은 잃어버린 설정이 아니라, 다음 부팅이 읽고 행동하는
  파일**이고, writer를 나중에 고쳐도 디스크는 안 낫는다. 그래서 세 규칙:
  - `[결정]` **원자적**: 같은 디렉토리에 tmp → `fsync` → `os.replace`(파일시스템 내 rename은 원자적)
    → **디렉토리도 `fsync`**(rename 자체를 durable하게). 파일은 옛것 아니면 새것, 반쪽이 없다.
  - `[결정]` **관대함**: 없음·빈 파일·잘림·타입 틀림·모르는 키 — 전부 에러가 아니다. **필드별로 각각**
    검증해 하나가 나빠도 나머지를 잃지 않는다(미래 버전이 쓴 파일도 이 버전이 아는 건 다 산다).
    **설정 파일에 잡바이트 하나 있다고 안 켜지는 페달이 밝기를 잊은 페달보다 훨씬 나쁘다.**
  - `[결정]` **즉시 쓰기**: 값이 바뀐 그 틱에. 타이머도 종료시점도 아니다(**종료가 없으므로**). 값이
    적고 이산적이라 손이 카드를 괴롭힐 만큼 만들 수 없다 — 디바운스는 여기선 과설계다.
- `[결정]` **쓰기 실패는 로그 1회 후 계속.** design.md §5는 fail-loud지만 화면이 사용자가 보고 있는
  그것뿐이고 이건 취향 설정이다. **꽉 찼거나 read-only인 카드가 페달을 죽이면 안 된다.**
- **스키마 = `FIELDS` 한 곳**(`attr -> (default, validator)`). 설정 추가 = 여기 한 줄 + `AppState` 필드.
- **검증**: `--settingstest` 12케이스 — 첫 부팅·변경 시 쓰기·무변경 시 침묵·재부팅 생존·`.tmp` 잔재
  없음 + **고의 파손 6종**(잘림/빈파일/비-dict/타입틀림/범위밖/bool은 인덱스 아님) 전부 defaults로
  착지하고 **아무것도 raise 안 함** + 미래 키 무시하고 나머지 유지.
  **온메탈**: 실 Runtime에 ENC1 이벤트를 넣어 `{"bright": 0}`이 디스크에 앉는 것 확인 → 서비스
  재시작 후 **레일 실측으로 적용 확인**: `bright=0`(0x08) 패널 몫 **+16.1mA** vs `bright=2`(0xFF)
  **+65.4mA** — **4배 차, 저장된 선택이 유리까지 간다**(눈 없이 증명됨).

## W. 라디오 — WiFi 3상태 / BT 2상태 `[해결]` (2026-07-17)

앱 최초의 라디오 제어(리포지토리에 선례 0). 사양[사용자]: WiFi `on`/`hotspot`/`off` 기본 **on**,
BT `on`/`off` 기본 **off**. 둘 다 SYSTEM의 **값 항목**(결정 U 문법 — on/off도 2단계짜리 값이다).

- `[결정]` **hotspot이 계획을 뒤집었다.** 이전 로드맵은 "rfkill이면 sudo도 polkit도 불필요"로
  결론냈는데 **무효다**: rfkill은 라디오를 끌 뿐 **AP를 만들 수 없다.** → WiFi는 NetworkManager,
  그럼 polkit. **BT만 rfkill로 남는다**(on/off뿐이고, `miza`의 `netdev`는 *그룹* 권한이라 polkit의
  `allow_active`를 무력화하는 세션 없는 서비스 컨텍스트에서도 산다 — 규칙 불필요).
- `[결정]` **`pb-hotspot`은 이미 있었다** [사용자 지적] — AP/SSID `starry`/wpa-psk/`ipv4.method=shared`
  (172.24.1.1/24 + NM 내장 DHCP)/`autoconnect=no`. **프로파일 생성이 계획에서 빠졌고**, 앱은 up/down만
  하면 된다 → polkit에서 `settings.modify.*`를 **뺄 수 있었다**(권한이 좁아짐).
- `[결정]` **polkit 규칙 3액션** — `deploy/ganglion-service/50-ganglion-radio.rules`,
  `49-synapse-power.rules`와 같은 모양·같은 이유. **추측이 아니라 실측**: 이 박스는
  `loginctl list-sessions`가 **비어 있어** 내 셸이 서비스와 같은 컨텍스트였고, 거기서
  `enable-disable-wifi`=아니요 / `wifi.share.protected`=아니요 / `network-control`=인증(물어볼 세션이
  없으니 사실상 거부)였다. 규칙 설치 후 **셋 다 예**로 뒤집히는 것을 **라디오를 건드리지 않고** 확인.
- `[결정]` **클라이언트 SSID를 코드에 안 적는다.** `on`은 `radio wifi on` 후 **NM의 autoconnect에
  맡긴다**(저장된 클라이언트 프로파일이 여럿 — Florsheim/KBRI_WiFi6/KT_…). 그래야 리그가 다른 방,
  다른 집으로 따라간다. 하드코딩했으면 이사할 때 깨진다.
- `[결정]` **`con down`은 관용(`must=False`)** — `off → on` 경로에선 hotspot이 애초에 안 떠 있고
  nmcli는 그걸 **에러(rc=10)로 취급**한다(실 nmcli로 확인). 관용 안 하면 전환마다 헛 경고가 뜬다.
- `[결정]` **루프를 절대 막지 않는다.** `nmcli con up`은 수 초가 걸리는데 이 루프는 33Hz로 인코더를
  폴하고 패널과 버스를 공유한다 — 거기서 멈추면 UI도 노브도 그 시간 내내 죽는다. → **워커 스레드
  fire-and-forget.** 결과를 기다리지도, 라디오를 되읽지도 않는다: UI는 **고른 값**을 보여준다
  (밝기와 같은 계약 — contrast도 되읽지 않는다). 실패는 로그로.
- `[결정]` **부팅 시 적용**[사용자 선택] — `Radio`가 엣지 온리라 **첫 호출이 곧 부팅 적용**이 된다
  (별도 코드 없음). 위험은 알고 고른 것: 저장값이 `off`면 부팅 후 SSH로 못 들어온다(노브로만 복구).
  기본이 `on`이라 새 박스는 안전하고, 앱이 안 뜨면 NM 자신의 기억이 남으므로 위험은 유계다.
- `[결정]` **SYSTEM 항목 6개 → 레이아웃 재작업.** 18px 간격이면 6번째가 y=114에서 시작해 푸터(120)를
  뚫는다 → **16px**. 값 표시는 종류를 따른다: 밝기는 **점**(레벨 = 범위 내 위치), 라디오는
  **이름**(`ON`/`AP`/`OFF`) — 익명의 점 3개보다 정직하다. 반전 행에서도 `fill=0`으로 읽힌다(실 렌더 확인).
- `[결정]` **`SYSVALUES` 테이블** — Brightness 특수분기를 대체. 밝기는 **인덱스**를 저장하고(선택지가
  contrast 바이트라 라벨로선 무의미) 라디오는 **이름**을 저장한다(설정 파일에서 튜플 순서가 바뀌어도
  의미가 유지돼야 한다). 선택지 튜플을 인덱싱하면 둘이 같은 방식으로 걷는다.
- `[정정]` **ENC0 click이 값 항목에 `TODO:` 토스트를 뱉었다**[사용자 발견] — 잘 동작하는 WiFi
  설정 위에서 "TODO: WiFi"라고. 액션/값 분리(위)를 **rotate 핸들러에만 심고 click 핸들러엔 안
  알려준** 탓으로, 값 항목이 전부 `else`로 떨어졌다. 값은 클릭할 게 없다(ENC1로 제자리 편집하고
  레일·LED가 이미 그렇게 말한다) → `elif it not in SYSVALUES`. 이제 `TODO:`는 **About 하나**,
  즉 실제로 미구현인 유일한 액션에만 남는다. **어떤 구분을 도입하면 그걸 읽는 자리를 전부 찾아야
  한다** — 한 곳만 고치면 나머지가 조용히 옛 규칙을 따른다.
- **온메탈 검증 완료**[사용자]: `hotspot`·`off` **동작 확인**("올굿"). Claude는 확인할 수 없는
  자리였다 — 실행하는 순간 이 박스가 관리 통로인 네트워크에서 떨어진다. Claude가 확인한 것: BT는
  **재시작 전 `Soft blocked: no` → 후 `yes`**(저장된 기본값 off가 부팅 시 적용됨), WiFi `on`은
  no-op이라 Florsheim 유지.
- **검증**: `--radiotest` 8케이스(상태별 argv 3+2 · `con down` 관용 플래그 · 엣지 온리 · 첫 호출은
  발화) — 러너 주입이라 서브프로세스 0. `--settingstest` 15케이스(라디오 필드 포함, **"bad field
  costs only itself"**: `bright=99` 거부하면서 `wifi=hotspot`은 유지). 온메탈은 위.

## 해결됨 `[해결]`
- **입력 어휘**: 우리 GestureRecognizer(Rotate/Press{click,long}/Combo)가 2a에 정확히 충분. 키보드
  에뮬(r/t/w/e · f/g/s/d · x)이 ENC0/ENC1 rot/click/hold + combo에 1:1 매핑 — 검증됨.
- **깊이 모델**: depth 1 제거(2a), depth 0/−1만. ENC0 hold=줌아웃, ENC1 hold=튜너.
- **폰트**: Silkscreen 8/16/24/32 + Micro5@10 (렌더 검증).
- **화면 렌더**: chain/glance/menu/sys/tuner 라이브 상태에서 검증(`render(state)`).
