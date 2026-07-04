# Ganglion 구현 결정 로그

시안 2a를 `ganglion/app.py`로 포팅하며 튀어나온 결정들. 진행하며 계속 추가한다.
`[사용자]`=님 판단 필요 · `[구현]`=내가 옵션 정리해 제안 · `[해결]`=정해짐.

상태(2026-07-04): **스파인 포팅 완료** — depth 0/−1, 슬롯 메뉴(bypass/remove/back),
SYSTEM, TUNER, COMBO 저장, 노브 focus/lock/adjust. 라이브 노브 모델 + 6개 화면 렌더 검증.

---

## A. synapse 실 모델 배선 시점 `[사용자]`
지금 `app.py`는 자체 `make_board()` + 노브 모델(K/fmt/norm)을 씀 — 시안 포팅. 실제로는
synapse `model.py`/`modepctrl.py`/`plugincatalog.py`의 **실 페달보드·LV2 플러그인·파라미터 get/set**에
붙어야 함. 언제 붙일지(하드웨어 후 vs 지금), 그리고 우리 노브 dict ↔ synapse 파라미터 모델 매핑 방식.
→ 기본값: 당분간 self-contained 샘플로 스파인 완성, 통합은 별도 단계.

## B. 플러그인 화이트리스트 `[사용자]`
시안 `WL`(카테고리×승인 플러그인)이 하드코딩. 실배선 시 `plugincatalog.py`의 실 LV2 URI로 매핑 필요.
확정본인가, 시작점인가? (피커 화면은 아직 스텁)

## C. 스텁된 인터랙션 우선순위 `[구현]`
시안엔 있으나 아직 포팅 안 함 (토스트로 스텁): **피커(place/replace)** · **move** ·
**보드/스냅샷 관리(rename/save/delete)** · **confirm 오버레이**. 로직은 시안에 다 있음.
→ 어느 것부터? 제안: 피커 → move → 관리 → confirm 순 (사용 빈도).

## D. 회전 가속(accel)을 값 조절에 반영할지 `[사용자]`
현재 `feed()`에서 Rotate.delta를 **부호로만** 축약 → 1디텐트=1스텝(노드 이동·값 조절 공통).
빠르게 돌리면 큰 스텝(대범위 파라미터 빠른 이동)이 편할 수 있음. 노드 이동엔 1:1이 맞고,
값 조절엔 accel이 유용. → 값 조절만 accel 반영할지 결정.

## E. 파라미터 스케일링(선형 vs 로그) `[구현]`
`adjust()`는 (max−min)/40 **선형**. Hz·ms·주파수류는 로그 스텝이 자연스러움.
시안도 선형. → 파라미터 단위별 스케일 곡선 정의할지.

## F. 토스트 만료 `[구현]`
시안은 토스트를 ~1.3s 후 자동 제거. 현재 컨트롤러엔 시간 기반 제거 없음(토스트가 안 사라짐).
메인루프가 `now`를 줘서 만료시키는 구조 필요. → 메인루프 설계와 함께.

## G. 무조작 자동 진입(스크린세이버) `[사용자]`
시안 언급: 10초 무조작 → 깊이 −1 자동 진입. 유지할지, 시간값.

## H. 실시간 데이터 소스 `[구현]`
현재 레벨미터(IN −14.2/OUT −4.3)·튜너 cents가 하드코딩. 실제로는 `monitorfeed.py`에서.
→ monitorfeed 배선 + 갱신 주기(코스트 모델상 좁은 밴드는 저렴).

## I. RGB LED 색 팔레트 `[사용자]`
`leds()`가 색 **이름**("amber","green","red","purple","blue","grey","off") 반환. NeoPixel엔
실 RGB 튜플 필요. 정확한 색상값·밝기(주간 시인성)·off 처리. → 팔레트 값 확정.

## J. 메인루프 구조 `[구현]`
헤드리스 루프: 입력 폴/이벤트 · monitorfeed 갱신 · 토스트/애니메이션 틱 · 디스플레이 부분 push.
`scheduler.Scheduler` seam 맞춰 plain-Python. → 스파인 다음 큰 덩어리.

---

## 해결됨 `[해결]`
- **입력 어휘**: 우리 GestureRecognizer(Rotate/Press{click,long}/Combo)가 2a에 정확히 충분. 키보드
  에뮬(r/t/w/e · f/g/s/d · x)이 ENC0/ENC1 rot/click/hold + combo에 1:1 매핑 — 검증됨.
- **깊이 모델**: depth 1 제거(2a), depth 0/−1만. ENC0 hold=줌아웃, ENC1 hold=튜너.
- **폰트**: Silkscreen 8/16/24/32 + Micro5@10 (렌더 검증).
- **화면 렌더**: chain/glance/menu/sys/tuner 라이브 상태에서 검증(`render(state)`).
