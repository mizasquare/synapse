# 아이캔디 — 오디오 반응형 캐릭터 애니 (아이디어/설계 메모)

> 인터페이스 배경에 **오디오 버퍼에 반응해 기타 치는 픽셀 캐릭터**(보치 더 록 / 픽셀레이티드 동물 뮤지션 류) 12/24프레임 애니를 띄우는 아이캔디.
> 8GB Pi5라 성능은 여유. 핵심은 성능이 아니라 **의존성/정확도/포팅 리스크**.
> 상태: 아이디어 확정, 엔진 구현 미착수. 관련: `docs/qt-migration-handoff.md`, 튜너 오디오 버퍼 파이프(재사용 대상).
> 작성 맥락: 2026-06-24 디스커션 정리. 모델/엔진 작업은 집 PC에서 계속.

---

## 1. 핵심 컨셉

오디오 버퍼는 튜너에서 이미 **성능 열화 없이 / 코드적으로도 쉽게** 따오고 있음. 그 위에:
- 스트림에서 **리듬축**(언제 튕겼나)과 **바이브축**(어떻게 들리나)을 추출
- 그걸로 배경 캐릭터 애니를 구동 (스트럼 프레임 트리거, 강약, 무드/배경)

신호를 두 축으로 분리하는 게 설계의 뼈대:
- **리듬축** = 언제 튕겼나 / BPM / 박자 위상 → 애니 **타이밍·스트럼 트리거**
- **바이브축** = 얼마나 세게 / 밝게 / 무슨 무드 → 애니 **강도·변형·배경**

---

## 2. 씬 조사 (경량 오디오 분석 도구, 가벼운 순)

| Tier | 도구 | 뽑는 것 | Pi5 부하 | 비고 |
|---|---|---|---|---|
| **0. 순수 DSP (ML 없음)** | RMS 에너지 + spectral centroid + onset density (numpy FFT 또는 aubio 내장) | 음량·밝기·연주밀도 = "바이브 벡터" | 사실상 0 | 튜너 버퍼 파이프에 FFT 한 줄. **아이캔디의 80%는 이걸로 끝** |
| **1. aubio** | C 라이브러리 + 파이썬 바인딩 | onset(피킹 어택), tempo/BPM, beat 위상, pitch | 매우 낮음 (hop 512 @ 44.1k, Pi 검증됨) | causal=실시간 설계. 워크호스. `pip install aubio` ARM OK |
| **2. Essentia (+TF MusiCNN)** | C++/파이썬 | 진짜 ML mood(aggressive/happy/relaxed), danceability, genre | 중간 (1~2초마다 추론) | "무드 라벨" 진짜 필요할 때만. **ARM64 `essentia-tensorflow` 휠 빈약 → 직접 빌드 함정** |
| **3. BeatNet / BeatNet+** | CRNN + 파티클 필터, PyTorch | SOTA beat/downbeat/meter 실시간 | 높음 (PyTorch+madmom+librosa) | aubio 박자추적 부족할 때만. 아이캔디엔 오버킬 |

**결론:** 아이캔디엔 **Tier 0 + aubio**가 거의 항상 정답. Essentia/BeatNet은 ROI 낮음(특히 ARM 빌드 고생).

### 기타(guitar) 특화 주의점
- 솔로 기타는 **비타악기 신호 → BPM 락이 원래 잘 안 됨**. aubio tempo는 octave error(절반/2배), ~107 BPM 편향.
- 정확히 이 "비타악기/보컬 박자추적"을 개선한 게 BeatNet+(2024)지만 아이캔디엔 과함.
- **기타엔 BPM보다 onset(어택 검출)이 훨씬 좋은 구동 신호.** 한 번 튕길 때마다 onset → 스트럼 프레임 한 번.

---

## 3. 확정 결정사항

### 3.1 BPM은 검출하지 말고 글로벌 호스트에서 따온다
MOD/MODEP 글로벌 템포는 **JACK transport로 브로드캐스트**됨(플러그인들이 sync 거는 신호). 탭템포(FS C+D)로 맞춘 BPM이 그대로 실림. 오디오 처리 0, 메타데이터만 폴링:

```python
import jack
c = jack.Client('synapse-bpm', no_start_server=True)
state, pos = c.transport_query()
bpm = pos.get('beats_per_minute')   # transport가 timebase master일 때 채워짐
```

- `beats_per_minute`는 **BBT valid(timebase master 존재)일 때만** 채워짐. transport stopped면 비어있을 수 있음 → `None`이면 마지막 값 유지/기본값 fallback.
- 1초에 한 번 폴링이면 충분. → **onset 검출은 박자추적 부담을 완전히 내려놓고 "방금 튕겼나"만** 보면 됨.

### 3.2 스타일 분류: 스트럼 / 파워코드 / 솔로 (DSP + onset)
저비용으로 충분. **결정적 축 = 단음(mono) vs 화음(poly).** 나머지가 파워코드 vs 스트럼 fuzzy 영역.

| 피처 (윈도우 ~100–200ms) | 출처 | 스트럼 | 파워코드 | 솔로 |
|---|---|---|---|---|
| **pitch confidence** (mono) | aubio `yinfft` conf | 낮음/불안정 | 낮음 | **높음·안정** ← 핵심 |
| onset density | aubio onset (`specflux`) | 높음·규칙적 | 중간·청키/싱코페이션 | 가변·레가토 |
| spectral centroid (밝기) | FFT | 중 | **낮음**(머트/저역) | **높음**(리드역) |
| low-band ratio (<~300Hz) | FFT | 중 | **높음** | 낮음 |
| envelope decay | RMS 기울기 | 울림(sustain) | **짧음**(팜뮤트 chug) | 레가토 |

**판정 로직 (게이트 → 트리):**
1. RMS < 임계 → `IDLE`
2. pitch conf 높고 안정 → `SOLO`
3. 폴리포닉: 짧은 decay + 낮은 centroid + 저역 우세 → `POWER`, 그 외 브로드밴드·sustain·dense → `STRUM`

**시행착오 지름길:** 임계값 손으로 깎지 말고 — 스타일별 30초씩 치며 `[feature_vector, label]` CSV 로깅 → `DecisionTreeClassifier(max_depth=3)` 학습. 추론 마이크로초, **트리가 임계값을 직접 뱉음** → 원하면 그 숫자만 하드코딩해 런타임 의존성 제거.

**디바운스(아이캔디 필수):** 분류는 10~20Hz로 빠르게, 화면 전환은 **0.4~0.6초 다수결/히스테리시스 + 최소 dwell time**. 안 그러면 캐릭터가 스트로빙. 상태 내 강약(RMS→스트럼 세기)은 연속 매핑.

**현실적 기대치:** 솔로 vs 화음(mono/poly)은 거의 확실. 스트럼 vs 파워코드가 fuzzy 경계 — 팜뮤트 decay + 저역비 + onset 패턴이 캐리, 학습 트리 이득 최대 구간.

---

## 4. Pre-FX + Post-FX 듀얼 탭 (채택)

둘 중 하나 고르지 말고 **둘 다 따는 게 더 깔끔**. 두 신호가 상보적이고 2축에 정확히 맵핑됨.

- **Pre-FX = "무엇을 연주하나"**(player의 손) — 클린, 피치/어택/다이내믹스 신뢰도 높음, **패치 무관**
- **Post-FX = "어떻게 들리나"**(the vibe) — 디스토션/리버브/딜레이가 만드는 실제 분위기

| | Pre-FX (드라이) | Post-FX (웻) |
|---|---|---|
| 피치 confidence | ✅ 깨끗 | ❌ 디스토션이 망침 |
| 어택/온셋 | ✅ 또렷 | 컴프레서가 뭉갬 |
| 진짜 다이내믹스 | ✅ | 압축됨 |
| 패치 의존성 | **없음** | 큼 |
| 공간감/앰비언스 | 없음 | ✅ 리버브·딜레이 테일 |
| 그릿/공격성 | 없음 | ✅ 디스토션 |

### 결정적 이득
1. **패치 불변 분류기 (최대 승리).** 스타일 분류를 **pre-FX에서** 하면 드라이 신호는 패치 무관 → 트리 한 번 학습 → **모든 프리셋에서 작동.** 포팅 최대 리스크였던 "탭 포인트/신호체인 민감성"이 사라짐.
2. **디스토션 컨파운드 격파.** 하이게인에선 단음(솔로)도 하모닉이 스펙트럼 채워 post만 보면 화음처럼 보임 → post 분류기는 솔로를 STRUM 오판. pre-FX 피치 conf는 게인 벽 너머에서도 "단음" → **솔로가 솔로로 읽힘.** dual-tap 킬러 논거.
3. **웻−드라이 델타 = 공짜 vibe 피처 (ML 없음):**
   - `RMS(post)−RMS(pre)` ↑, crest factor ↓ → 압축/서스테인 → **공격성/게인량**
   - `spectral flatness(post)` ↑ → 디스토션 하모닉 → **그릿 정도**
   - `centroid(post)−centroid(pre)` → 톤 밝기 변화
   - 드라이 노트 끝났는데 post 계속 울림 → **리버브/딜레이 테일 = 공간감**(실시간 측정)

### 비주얼 매핑
```
전경 = 연주자 캐릭터  ← pre-FX  : 스트럼/파워/솔로 포즈, 피킹마다 스트럼 프레임, 손 세기
배경 = 사운드의 분위기 ← post-FX : 리버브 → 안개/파티클, 디스토션 → 불꽃/강렬함,
                                   딜레이 → 캐릭터 잔상/에코, 밝기 → 색온도
```
캐릭터는 *손이 하는 것*, 배경은 *귀에 들리는 것*. 클린 아르페지오 = 잔잔 캐릭터 + 넓은 리버브 안개 / 하이게인 파워코드 = 같은 동작인데 배경이 불타는 식.

### 실무 노트
- **비용:** FFT 2배지만 hop당 FFT는 Pi5에서 무시 수준.
- **JACK 라우팅:** 분석 클라이언트 입력 포트 2개 → 하나는 페달보드 입력(또는 튜너 탭), 하나는 페달보드 출력/모니터 버스.
- **정렬 주의:** post는 체인 레이턴시만큼 늦음. **샘플 정확 빼기 금지** — 100~200ms 윈도우 피처 비교만. 딜레이/리버브 desync는 버그 아님, *그게 신호*(테일=앰비언스).
- **데모데이터 단순화:** 스타일 분류기는 **드라이만 라벨링**(패치 불변). vibe-델타는 비지도 연속 매핑 → 라벨 불필요.

---

## 5. 개발 워크플로 — PC에서 다듬고 머신으로

엔진이 numpy+aubio라 **플랫폼 무관**. 이미 Step A+B에서 presenter를 fakes로 Windows headless 돌게 해둔 패턴 그대로. PC↔Pi 차이는 딱 두 seam(오디오 소스 / BPM 소스)뿐.

### 구조 (기존 seam 패턴)
```python
class AudioSource(Protocol):        # frames(hop) 이터레이터; pre/post 2채널
    def frames(self) -> Iterator[np.ndarray]: ...
# Pi:  LiveJackSource   (튜너 버퍼 파이프, pre+post 2포트)
# PC:  FileSource(wav)  (realtime 재생 OR faster-than-realtime 배치평가)

class TempoSource(Protocol):
    def bpm(self) -> float | None: ...
# Pi:  JackTransportTempo
# PC:  FixedTempo(120)

class StyleEngine:                  # 순수: frame → features → state. 플랫폼 의존 0
    def push(self, frame) -> StyleState: ...
```

`StyleEngine`이 순수 → PC에서:
- 라벨링된 WAV 폴더 → `FileSource` batch → 피처 CSV + **confusion matrix** 뽑고 트리 반복
- 만족하면 임계값 하드코딩
- Pi로 갈 땐 `FileSource`→`LiveJackSource`, `FixedTempo`→`JackTransportTempo` **두 줄만 교체**
- 같은 녹음으로 **골든 회귀 테스트** 가능("이 리프는 SOLO여야 함")

### 포팅 체크리스트 (PC↔Pi 동일해야 하는 것)
1. **탭 포인트 (사활).** 피처는 신호체인에 극도로 민감. → 튜너 콜백에서 **pre-FX 드라이 탭 위치부터 확인.** (듀얼 탭 채택으로 분류는 드라이에서 하니 리스크 대폭 완화.)
2. **샘플레이트.** pisound 보통 48k. 데모 WAV를 런타임 레이트로 리샘플(44.1k 튜닝 → 48k 배포 시 centroid 임계 밀림).
3. **hop/window 동일.** 라이브 JACK 버퍼와 오프라인 청킹 같은 hop.
4. **RMS 게이트만 현장 재보정.** 노이즈 플로어/게인 다르니 IDLE 게이트 임계만 Pi에서 마지막 캘리브.

### 데모데이터 수집
- 스타일별 30초~1분, 깨끗/지저분 둘 다 (느슨/꽉찬 스트럼, 팜뮤트/오픈 파워코드, 레가토/얼터네이트 솔로).
- 가능하면 **실제 그 기타로**(픽업 출력 특성이 피처에 들어감).
- 경계 케이스 포함: 아르페지오(솔로 같은 화음), 더블스톱(솔로 같은 2음) — fuzzy 튜닝용.

---

## 6. 다음 스텝 (집 PC)

1. [ ] 튜너 콜백에서 오디오 버퍼 탭 위치/시그니처 확인 (pre-FX 드라이인지) — **1순위**
2. [ ] `AudioSource`(pre/post) / `TempoSource` / `StyleEngine` seam 스케치
3. [ ] PC용 `FileSource` + 피처 추출기(aubio onset/pitch + numpy RMS/centroid/flatness) + CSV 로거
4. [ ] 데모데이터 녹음 (스타일별, 가능하면 실 기타)
5. [ ] depth-3 결정트리 학습 → confusion matrix → 반복 → 임계 하드코딩
6. [ ] 디바운스 상태머신 (0.4~0.6s 히스테리시스)
7. [ ] vibe-델타(웻−드라이) 연속 피처 매핑
8. [ ] QML 스프라이트 애니 바인딩 (onset→프레임, energy→강약, delta→배경)
9. [ ] Pi 배포: 소스 어댑터 2줄 교체 + RMS 게이트 현장 캘리브
