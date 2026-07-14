# 익스프레션/볼륨 페달 (ADS1115) — 핸드오프 [DONE 2026-07-05]

> **✅ 완료 (2026-07-05).** 배선·캘리브레이션(7/1 양 채널 실측) → 서비스 배포(reflex + volumectl, 7/5)
> → CC 경로 끝단검증 → 현장 실페달 힐↔토 확인까지 전부 종료. ch1 납땜 의심은 풀업 재배선 후
> 해소(플로팅 raw 양 채널 대칭 확인). 아래 체크리스트는 이력 보존용.
>
> **언플러그 거동 노트(정상, 버그 아님):** 플러그를 뽑는 도중 잭의 Ring 접점이 플러그 GND 구간을
> 스치며 CC 0으로 딥 → 완전 분리 후엔 풀업(~2.9V, raw ≈ 23k > in_max)으로 CC 127 = 유니티 고정,
> 이후 송신 없음. 설계만 해두고 미구현이던 언플러그 페일세이프(127 홀드)를 물리가 대신 구현한
> 형태. 0-딥의 뚝→펑은 "페달은 연주 전에 꽂는다" 운용으로 커버.
>
> 작성: 2026-06-28 (당시 원격 SSH only). 상세 하드웨어 노트는 [`docs/hardware.md`](hardware.md)
> (ADS1115 섹션 + 익스프레션 페달 입력 섹션) 참조.

---

## 목표
TRS 익스프레션 페달을 ADS1115로 읽어 파라미터(볼륨/익스프레션) 제어.

**아키텍처 통합 완료 (2026-07):** [`reflex.py`](../reflex.py)는 이제 박스 안의 **독립 MIDI
장치**다(의도적으로 앱 밖 — 앱이 죽어도 페달은 돈다). 볼륨 **CC#102** / 익스프레션 **CC#103**
(undefined 대역, 공유 버스 위 예약 CC 회피)을 GAAD67로 발신하고, 캘리브레이션·채널/CC 할당은
자체 소유하며 Unix 소켓으로 관리된다 — [`deploy/reflex-service/README.md`](../deploy/reflex-service/README.md).
볼륨 축은 `synapse-volume` 컨트롤 데몬(taper 소유, [`deploy/volume-service/`](../deploy/volume-service/))이
받아 마스터볼륨을 구동하고, 앱 슬라이더는 state echo로 양방향 동기화된다.
**아래의 온디바이스 하드웨어 점검·실측·캘리브레이션도 완료됨 (상단 완료 배너 참조).**

## 하드웨어 현황 (확정)
- ADS1115: I2C bus1 `0x49`, **VDD=3.3V** (입력 절대최대 3.6V, 5V 금지)
- TRS 잭 배선: `Tip ← [10kΩ 직렬] ← 3.3V`, `Sleeve ← GND`, `Ring → ADS 입력(=포트 와이퍼)`
- 페달: 25K TRS/RTS(전압분배) 또는 10K TS(가변저항). **TS 모드는 이 배선과 부적합** — TRS 분배기 모드로 쓸 것.
- 10kΩ 직렬저항 = 핫플러그 시 Tip의 3.3V가 GND로 순간단락→파이 셧다운 되던 문제의 해결책 (해결 완료).

## 적용된 변경 (커밋됨 — 게인/레이트 `1abab37`, 채널별 캘리 `27f84e5`)
[`reflex.py`](../reflex.py):
1. Gain `±2.048V → ±4.096V` (`PGA_4_096V`) — 와이퍼 상단(~2.36V)이 ±2.048V에선 클리핑되던 것 방지.
2. Data rate `860SPS → 128SPS` (`DR_128SPS`) — 페달엔 과한 속도. 노이즈↓·입력임피던스↑.
3. `map_value` 임시값(819/14745)은 **채널별 캘리브레이션 파일 방식으로 대체됨**
   (`~/.modep/pedal_calibration.json`, 파일 없으면 기본값 150/17700). 실측값은 파일에 저장.

## 미해결 핵심 의문 ⚠️ — ch1 납땜/배선 의심
연결 안 된 상태 진단 결과(상세는 hardware.md 검증로그):
- 게인 바꾸니 같은 노드 전압이 변함 → 입력이 고임피던스(풀업)로 떠 있고 ADC가 로딩 중 = 신뢰할 DC 아님. **연결유무 감지용으로 쓰지 말 것.**
- **ch1 유효 풀업이 ch0의 ~3.4배** (가정 무관 결론). ch0는 의도값 ~1M에 부합(정상), **ch1만 비정상 → 콜드조인트/부분단선/풀업값 차이 의심.**
- 단, 떠 있는 고임피던스 값으론 확진 불가. **페달 꽂아 저임피던스로 만든 뒤 양 채널 비교가 유일한 확진법.**

---

## 재개 시 할 일 (순서대로)

### 1. 납땜/배선 점검 (전원 OFF, 멀티미터)
- ch0/ch1 각 풀업저항 실제 저항값 측정 (의도 ~1M, 실측 750~850k였다고 함). ch1 쪽 콜드조인트/단선 집중 확인.
- TRS 잭 각 접점(Tip/Ring/Sleeve)이 의도대로 연결됐는지, 10kΩ 직렬저항 양단 도통 확인.

### 2. 페달 물리고 실측 (TRS 케이블, TS 아님!)
SSH에서 아래로 양 채널 스윕 읽기 (게인 ±4.096V, 128SPS 기준):
```bash
cd /home/miza/synapse
python3 -c "
import time
from hardwares.ADS1115 import ADS1115
A=ADS1115(1,0x49); A.setGain(A.PGA_4_096V); A.setDataRate(A.DR_128SPS)
print('iter  ch0      ch1      | ch0_V  ch1_V')
for i in range(40):
    c0,c1=A.readChannel(0),A.readChannel(1)
    print(f'{i:>3} {c0:>7} {c1:>7}  | {c0/32767*4.096:5.3f} {c1/32767*4.096:5.3f}')
    time.sleep(0.1)
"
```
- 페달을 힐↔토 천천히 왕복하며 확인.
- **정상 채널:** 0V → ~2.36V 매끈하게 단조 변화.
- **불량 채널:** 안 움직이거나/튀거나/범위 이상 → 납땜 이슈 확진. → 1번으로 돌아가 수리.

### 3. 캘리브레이션 — 이제 reflex 소켓으로 (하드코딩 편집 불필요)
`synapse-reflex.service`를 띄운 상태에서:
```bash
# get_status의 raw를 보며 페달 왕복 → 힐 끝에서 capture_heel, 토 끝에서 capture_toe
echo '{"cmd":"get_status"}'               | nc -U ~/.modep/reflex.sock
echo '{"cmd":"capture_heel","channel":0}' | nc -U ~/.modep/reflex.sock
echo '{"cmd":"capture_toe","channel":0}'  | nc -U ~/.modep/reflex.sock
echo '{"cmd":"save"}'                     | nc -U ~/.modep/reflex.sock   # 2% 마진 자동 적용·저장
```
- ch1(익스프레션)도 동일하게. 양끝이 확실히 CC 0/127에 닿는지 `get_status`의 `midi`로 확인.

### 4. 온디바이스 통합 검증 (캘리브레이션 후)
- `jack_lsp | grep -iE 'merger|a2j|GAAD'` — 집계 모드(mod-midi-merger) 여부/GAAD67의 JACK측 노출
  확인. `volumectl.py`의 버스 탭이 어느 쪽으로 붙었는지 `jack_lsp -c | grep synapse-volume`으로 확인.
- 페달 힐↔토 → 실제 마스터볼륨 변화 + 앱 슬라이더 추종(state echo). 앱 종료 후에도 페달 볼륨 동작(격리).
- 익스프레션: mod-ui에서 MIDI-learn으로 CC103을 원하는 플러그인 노브에 매핑.

### 5. (선택) 후속 개선 — 미구현, 설계만 논의됨
- 런타임 지터 억제: EMA(이동평균) 또는 데드밴드. 128SPS로 줄긴 했지만 마지막 1~2단계 까딱임 남으면 적용.
- ~~앱 내 캘리브레이션 화면~~ → **구현 완료 (2026-07-15, `25e119e`)**: ⚙MENU→Config→Volume Pedal —
  탈착 판별·캘리 위저드·CC 매핑. `reflexclient.py` + 목업용 `fakereflex.py`. 실기 검증 대기
  ([`qt-roadmap.md`](qt-roadmap.md) ② 참조).
- 부팅 페달 감지 / 언플러그 페일세이프 — [`qt-roadmap.md`](qt-roadmap.md) 볼륨페달 후속 항목.

---

## 참고 포인터
- 하드웨어 상세/검증로그/데이터시트 임피던스: [`docs/hardware.md`](hardware.md)
- 드라이버: [`hardwares/ADS1115.py`](../hardwares/ADS1115.py)
- TI 데이터시트: SBAS444E (ADS1113/1114/1115)
