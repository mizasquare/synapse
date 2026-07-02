# volume-service — 소프트웨어 마스터 볼륨 (JACK 게인 스테이지)

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

볼륨은 synapsevol의 `midi in`으로 **MIDI CC7**을 보내 조절한다. 게인 클라이언트를
synapse 앱과 **독립된 systemd 서비스**로 두는 이유: 앱(GUI)이 죽어도 오디오는 마지막
게인으로 계속 흘러야 하기 때문. synapse는 CC를 *보내기만* 한다(`mastervolume.py`).

## 구성

| 파일 | 역할 |
|---|---|
| `synapse-mastervol.service` | jack_mix_box를 메인 프로세스로 기동(0dB 유니티 시작), ExecStartPost=삽입, ExecStopPost=원복 |
| `rewire.sh` / `revert.sh` | 삽입 / 원복 (서비스가 호출, idempotent, 포트 대기 포함) |
| `install.sh` | 스크립트를 `/usr/local/bin`, 유닛을 `/etc/systemd/system`에 설치 + enable/start |
| `tools/` | 브링업·진단·재보정 (아래) |

## 설치

```bash
sudo deploy/volume-service/install.sh
systemctl status synapse-mastervol.service
jack_lsp -c | grep -E 'synapsevol|playback'    # playback ← synapsevol:MAIN 확인
```

제거:
```bash
sudo systemctl disable --now synapse-mastervol.service
sudo rm /etc/systemd/system/synapse-mastervol.service /usr/local/bin/synapse-mastervol-*.sh
sudo systemctl daemon-reload
```
서비스를 stop 하면 ExecStopPost가 직결(mod-monitor→playback)을 복구하므로 오디오는
유지된다.

## 다른 기계에 옮길 때 — 재보정 필수

볼륨 커브는 `jack_mix_box`의 CC→dB 페이더 법칙(**linear-in-dB**, 이 Pi에서
`dB ≈ 0.5545·CC − 70.4`, CC127=0dB, CC0=mute)을 역산해서 만든다. jack_mixer
빌드가 다르면 이 상수가 달라질 수 있으니 **재측정 후** `mastervolume.py`의
`_DB_PER_CC`, `_CC_UNITY`를 갱신한다:

```bash
python3 deploy/volume-service/tools/measure-cc-gain.py
#  -> _DB_PER_CC = 0.5545   _CC_UNITY = 127   (출력값을 그대로 복붙)
```

## tools/ — 브링업 · 진단

| 스크립트 | 용도 |
|---|---|
| `measure-cc-gain.py` | CC→게인 실측 + 상수 피팅 (재보정) |
| `manual-insert.sh [dB]` | 서비스 없이 수동으로 게인 스테이지 삽입 (기본 -20dB, 가청 확인) |
| `manual-revert.sh` | 위 원복 |
| `cc-sweep.py [dest]` | CC7 스윕으로 볼륨 라이브 제어 확인 (full→무음→중간) |

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
