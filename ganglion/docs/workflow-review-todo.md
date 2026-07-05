# UI 워크플로우 검토 — 대응 TODO

출처: Claude Design 프로젝트 *"Ganglion Workflow Review"* (시안 2a 상태머신 `ganglion/app.py`
을 상태·전이·일관성 관점에서 훑고 quirky 지점 7개 + 미세 관찰 4개를 뽑음). 이 문서는 그
**제안 7개(Q1–Q7)에 어떻게 대응할지 확정**한다. 우선순위는 검토 문서의 지목(Q1·Q2·Q3)을 따른다.

핵심 불변식(대응의 근거로 반복 사용):
- **ENC0 = 구조/카테고리**, ENC1 = 값. LED 팔레트에서도 amber=메뉴/카테고리는 ENC0쪽.
- **복귀 = "여는 인코더의 hold"**. depth 스파인은 ENC0 hold. 모달은 그 모달을 연 인코더(`_op`)의 hold.
- 확정 피드백은 0.5s 블로킹 splash (decision F/J).

---

## 대응 요약

| # | 지점 | 심각도 | 대응 | 코드 변경 |
|---|------|--------|------|-----------|
| Q1 | TUNER 복귀가 규칙 이탈 + 푸터 불일치 | 中 | 빠른-이탈(아무 press) 유지, **푸터를 실제와 일치** | `_tuner()` 푸터 문구 |
| Q2 | SYSTEM 진입(스크롤로 화면 밖) 발견성 | 中 | 스크롤-진입 유지 + **좌측 끝 `<SYS` 힌트 셀** | `_chain()` 힌트 |
| Q3 | 스냅 관리에서 조작손 E1→E0 튐 | 中 | **✔ 확정 — day 자동(시스템 날짜) → 스냅 관리 전부 ENC1 단일손** | `_name_open`/`rot·click·hold`/`_naming·_confirm`/`leds` + walk |
| Q4 | SLOT MENU·SYSTEM 회전이 enc를 안 가림 | 低 | **담당 인코더(ENC0)로 한정** (다른 모달과 일관) | `rot()` sys/menu 분기 |
| Q5 | 삭제 위험(red) LED가 커밋 인코더와 어긋남 | 低 | **위험색을 커밋 인코더(ENC0)에** (CONFIRM과 통일) | `leds()` menu 분기 |
| Q6 | 모달 내 ENC1 hold(=튜너)가 삼켜짐 | 低 | **의도로 확정·문서화** (예약). 스냅 naming에선 ENC1 hold=조작-취소로 유효화 | 문서 + Q3에 포함 |
| Q7 | COMBO 저장이 화면을 GLANCE로 끌어냄 | 低 | **현재 depth 유지**, splash만으로 확정 | `combo()` |

---

## 상세 대응

### Q1 — TUNER 복귀/푸터 정합  ✔ 채택(문구 수정)
- **현상:** `if st.tuner:` 가드가 click/hold(어느 인코더든) 즉시 이탈시키고 rotate는 무시.
  푸터는 `e1 hold ret` 만 안내 → 실제(아무 버튼)와 불일치.
- **결정:** 라이브 연주 중 **아무 버튼으로 빠르게 빠지는 건 오히려 장점** → 동작은 유지.
  대신 푸터를 실제와 맞춤: `press exit` (회전은 무시되므로 우발 이탈은 이미 방지됨).
- **진입 2경로(E1 hold / SYSTEM 항목)** 는 발견성 이중화라 유지.

### Q2 — SYSTEM 발견성  ✔ 채택(힌트 셀)
- **현상:** node0에서 ENC0를 start 넘어 좌회전(`nn<0 → sys`)해야 열림. 클릭/홀드 진입 없음.
  좌=웜홀 / 우=벽 비대칭. GLANCE에선 직접 도달 불가.
- **결정:** 웜홀 진입은 유지(값싸고 깔끔). node0일 때 노드 스트립 좌측 여백에 `<SYS` 힌트를
  노출해 "더 왼쪽에 뭔가 있다"를 시각화. 별도 진입 제스처는 추가 안 함(어휘 절약).

### Q3 — 스냅 흐름 손바뀜  ✔ 확정 (day 자동 → 스냅 = ENC1 단일손)
- **현상:** 스냅 경로는 GLANCE 스크롤=E1, SUB=E1 (아래손)인데 NAMING 확정/복귀, CONFIRM 백이
  E0(윗손) 고정. 보드 경로는 내내 E0라 스냅만 손이 튐.
- **[사용자] 핵심 통찰:** 스냅명의 `요일`은 인코더로 고를 필요가 없다 — **시스템 날짜에서 자동**으로
  채우면 된다. 그러면 스냅 naming에 카테고리 다이얼 자체가 사라져 **ENC1 한 손**(리롤·저장·취소)으로
  떨어지고, "ENC0=카테고리" 전역 불변식과도 충돌하지 않는다(고를 카테고리가 없으니).
- **확정 매핑:**
  - **보드**(현행 유지): E0 회전=term, E0 click=확정, E0 hold=취소, E1=리롤. term은 사용자 선택이라 다이얼 필요.
  - **스냅**: `word-요일`, **요일=오늘(시스템 날짜) 자동**. E1 회전=리롤, E1 click=확정, E1 hold=취소.
    ENC0 무동작. Delete confirm 도 No/Yes·커밋·취소 전부 E1.
- **불변식(순수성) 처리:** 컨트롤러가 시계를 직접 안 읽는다 — `day_provider`를 주입(Runtime의
  clock 주입과 동일 패턴). `--walk`는 고정 요일(thursday) 주입해 결정론 유지. 기본값=실제 시스템 날짜.
- **리스크(문서화):** GECO rpi에 RTC/NTP 없으면 요일이 실제와 어긋날 수 있음. 라벨용이라 치명적이지
  않으나, 하드웨어 배선 때 RTC 유무 확인 필요.
- **Q6 연동:** 스냅 naming/confirm에선 ENC1이 여는 인코더이므로 그 hold는 튜너가 아니라 "조작-취소"로
  소비된다(정합). 보드/그 외 모달에선 ENC1 hold 예약(=no-op) 유지.
- **검증:** `--walk` 스냅 saveas가 ENC1('s')로 확정(`formerly-thursday`), 보드 saveas는 baseline과
  동일(`Drive-seafloor`). 라우팅 단위 스모크(보드/스냅 rot·click·hold, confirm) 전부 통과.

### Q4 — 목록 회전 인코더 미가름  ✔ 채택(가름)
- **현상:** `st.menu += d` / `st.sys_idx += d` 분기에 enc 체크 없음 → ENC1로도 스크롤.
- **결정:** sub/pick/confirm 처럼 **담당 인코더(ENC0)로 한정**. 양손 스크롤은 제거(일관성 우선).

### Q5 — 위험색 LED ↔ 손 어긋남  ✔ 채택
- **현상:** SLOT MENU에서 Remove 선택 시 red가 ENC1(`l1`)에 뜨는데 실제 제거는 ENC0 click.
  CONFIRM은 red가 커밋(조작) 인코더에 뜸 → 두 파괴동작이 반대.
- **결정:** SLOT MENU에서 Remove hover 시 **red를 ENC0(`l0`, 커밋손)** 에, ENC1은 amber(메뉴 open 표시).

### Q6 — 모달 내 ENC1 hold 삼킴  ✔ 채택(의도 확정 + 문서)
- **현상:** move/pick/sub/naming/confirm 의 `hold()` 는 enc0만 처리·return → ENC1 hold=no-op.
- **결정:** **의도된 예약이다** — 모달 중엔 "여는 인코더 hold=back" 규칙을 지키고, 반대손 hold는
  오조작 방지를 위해 소비하지 않는다. "어디서나 튜너"는 depth 0(CHAIN/GLANCE) 특권으로 한정.
  단 **Q3에서 A/D 안을 택하면** 스냅 naming/confirm의 ENC1 hold는 튜너가 아니라 취소로 유효해진다.
- 코드 변경 없음(문서화). *(추후 피커/값조절에서 튜너 허용 재검토는 열어둠 — 이번 범위 밖)*

### Q7 — COMBO 저장이 GLANCE로 튐  ✔ 채택(depth 유지)
- **현상:** `combo()` 가 `depth=-1` 강제 → 노브 편집 중 저장하면 편집 컨텍스트 끊김.
- **결정:** splash(`SNAPSHOT SAVED`)로 확정은 충분 → **현재 depth 유지**, `dirty=False` 만 리셋.

---

## 미세 관찰 (이번 범위 밖 — 백로그)
- **knob lock 탈출:** 락 해제는 ENC1 토글뿐, ENC0 hold는 GLANCE로 점프. → decision 후보.
- **back 3중 중복:** MENU·SYS·SUB의 `< Back` 항목 + ENC0 hold + 반대손 click. 항목형 Back 제거 여지.
- **dirty 비대칭:** `_name_accept` 에서 board saveas는 dirty 안 세움, snap saveas만 세움. 상단 점 의미 상이.
- **가속 미반영:** `feed()` 가 회전 델타를 부호로 축약(decision D). 대범위 파라미터 느림. → D에서 다룸.

## 검증
- `_walk()` 를 Q3(스냅 확정=ENC1)·Q7(combo depth 유지)에 맞게 갱신.
- `python3 ganglion/app.py --walk` / `--looptest` 통과 확인.
- `docs/decisions.md` 에 Q1–Q7 처리 결과 반영.
