# volume-service — 시스템 볼륨 조절 장치 (synapse-volume)

Pisound의 ALSA `PCM` 컨트롤은 드라이버 레벨에서 **read-only**(`access=r-------`)라
소프트웨어 볼륨을 걸 수 없다. 그래서 출력 경로

```
페달보드 → mod-monitor:out → system:playback (Pisound DAC → 물리 노브)
```

의 `mod-monitor:out → system:playback` 링크를 끊고, 사이에 `jack_mix_box` 게인
스테이지(**synapsevol**)를 끼워 넣는다:

```
mod-monitor:out → synapsevol(Channel 1) → synapsevol(MAIN) → system:playback
```

## 구조 — 컨트롤 데몬이 볼륨 권한을 소유

서비스의 메인 프로세스는 [`volumectl.py`](volumectl.py) **컨트롤 데몬**이다. 데몬이
jack_mix_box를 자식으로 spawn하고, 마스터볼륨 권한을 온전히 소유한다:

```
reflex 페달 ─(CC102)─► GAAD67 ─► mod-midi-merger ─┬─► mod-host (learn/플러그인)
                                                  └─► synapse-volume:control in
앱 슬라이더 ─(raw CC102, 직결 JACK)───────────────────► synapse-volume:control in
volumectl: CC102 수신 → 로그감쇄 taper → CC7 (private) ─► synapsevol:midi in
         └─(적용값 echo, CC102)─► synapse-volume:state out ─► 앱 midi-in (슬라이더 동기화)
```

- **`control in`** — 볼륨 *명령* 수신: raw 선형 CC102 (0-127), 채널 무관.
  기동 시 `mod-midi-merger:out`(집계 하드웨어 MIDI 버스)을 탭하고, merger가 없으면
  GAAD67의 JACK측 포트로 폴백(2초 간격 lazy retry). 앱 슬라이더는 직결로 붙는다.
- **taper** — raw 0-127 → 진폭 제곱법칙 → dB → 믹서 CC. 예전엔 앱(`mastervolume.py`)에
  있었지만, **모든 컨트롤러(페달·슬라이더)가 같은 볼륨 법칙을 타도록** 데몬으로 이주했다.
- **`state out`** — 적용된 값을 CC102로 에코(모터라이즈드 페이더의 MIDI feedback 관용구).
  그래프 변화 시 재송신하므로 늦게 붙는 구독자(앱)도 현재값을 받는다.
- **CC7은 공유 버스에 절대 올라가지 않는다** — volumectl↔jack_mix_box 사이 private
  링크에만 존재. (공유 버스 위 예약 CC는 채널 물린 플러그인이 명시 바인딩 없이 네이티브
  반응할 수 있음. 그래서 버스 위 볼륨은 undefined 대역 CC102를 쓴다.)

게인 클라이언트를 synapse 앱과 **독립된 systemd 서비스**로 두는 이유: 앱(GUI)이 죽어도
오디오는 마지막 게인으로 계속 흐르고, **reflex 페달로 볼륨도 계속 조절**되어야 하기 때문.
앱은 이 장치의 여러 컨트롤러 중 하나일 뿐이다(`mastervolume.py` = raw CC 송신 + echo 구독).

## 구성

| 파일 | 역할 |
|---|---|
| `volumectl.py` | **컨트롤 데몬**(메인 프로세스): jack_mix_box spawn, CC102 수신→taper→CC7, state echo |
| `synapse-mastervol.service` | 데몬 기동, ExecStartPost=삽입, ExecStopPost=원복 |
| `rewire.sh` / `revert.sh` | 삽입 / 원복 (서비스가 호출, idempotent, 포트 대기 포함) |
| `install.sh` | 스크립트를 `/usr/local/bin`, 유닛을 `/etc/systemd/system`에 설치 + enable/start |
| `tools/` | 브링업·진단·재보정 (아래) |

의존성: 시스템 python3에 `jack` 모듈(JACK-Client) 필요 — 없으면 install.sh가 경고한다.
(pip로 설치하거나, 유닛의 ExecStart를 jack 있는 venv python으로 바꿔도 된다.)

## 설치

```bash
sudo deploy/volume-service/install.sh
systemctl status synapse-mastervol.service
jack_lsp -c | grep -E 'synapsevol|synapse-volume|playback'
```

제거:
```bash
sudo systemctl disable --now synapse-mastervol.service
sudo rm /etc/systemd/system/synapse-mastervol.service /usr/local/bin/synapse-mastervol-*.sh /usr/local/bin/synapse-volumectl.py
sudo systemctl daemon-reload
```
서비스를 stop 하면 ExecStopPost가 직결(mod-monitor→playback)을 복구하므로 오디오는
유지된다.

## 다른 기계에 옮길 때 — 재보정 필수

볼륨 커브는 `jack_mix_box`의 CC→dB 페이더 법칙(**linear-in-dB**, 이 Pi에서
`dB ≈ 0.5545·CC − 70.4`, CC127=0dB, CC0=mute)을 역산해서 만든다. jack_mixer
빌드가 다르면 이 상수가 달라질 수 있으니 **재측정 후** `volumectl.py`의
`DB_PER_CC`, `CC_UNITY`를 갱신한다:

```bash
python3 deploy/volume-service/tools/measure-cc-gain.py
#  -> DB_PER_CC = 0.5545   CC_UNITY = 127   (출력값을 그대로 복붙)
```

## tools/ — 브링업 · 진단

| 스크립트 | 용도 |
|---|---|
| `measure-cc-gain.py` | CC→게인 실측 + 상수 피팅 (재보정) |
| `manual-insert.sh [dB]` | 서비스 없이 수동으로 게인 스테이지 삽입 (기본 -20dB, 가청 확인) |
| `manual-revert.sh` | 위 원복 |
| `cc-sweep.py [dest]` | CC7 스윕으로 볼륨 라이브 제어 확인 (full→무음→중간). 기본 dest는 믹서 직접(`synapsevol:midi in`); 데몬 경유를 시험하려면 CC 번호를 102로 바꿔 `synapse-volume:control in`에 쏠 것 |

전형적 브링업 순서:
```bash
deploy/volume-service/tools/manual-insert.sh -20     # 볼륨 작아지면 삽입 성공
python3 deploy/volume-service/tools/cc-sweep.py synapsevol-test:midi\ in
deploy/volume-service/tools/manual-revert.sh         # 원복
python3 deploy/volume-service/tools/measure-cc-gain.py   # 커브 확인/재보정
sudo deploy/volume-service/install.sh                # 통과하면 정식 설치
```

## 지속성 메모

`mod-monitor:out ↔ system:playback` 재배선을 mod-ui가 만지는 곳은 **MOD 튜너 뮤트
경로 하나뿐**(`mod/host.py` mute/unmute). 페달보드/스냅샷/뱅크 전환은 이 링크를 건드리지
않으므로 삽입이 유지된다. synapse는 자체 cochlea 튜너를 쓰므로 MOD 튜너 뮤트 경로를
타지 않는다. (필요해지면 mod-tweaks에서 mute/unmute 타깃을 synapsevol로 패치.)
