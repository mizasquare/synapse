# reflex-service — 풋 페달 MIDI 장치 (볼륨 + 익스프레션)

[`reflex.py`](../../reflex.py)를 systemd 서비스로 돌린다. 이름은 척수 반사궁에서 —
발 입력이 뇌(Synapse GUI)를 거치지 않고 동작한다. **앱이 죽어도 페달은 계속 돈다.**

## 개념 모델 — 박스 안의 아웃보드 MIDI 페달

reflex는 Synapse의 하드웨어 인터페이스(풋스위치/LED, `hardware.py`)가 아니라
GCaMP6s 박스 안에 사는 **독립 MIDI 컨트롤러**다. 실물 MIDI 페달과 동형으로 동작한다:

- **연주 신호 = MIDI 케이블 하나.** 두 축 모두 `GAAD67`(amidithru 가상 포트)로 CC 발신
  → OS가 박스의 MIDI 입력(mod-midi-merger → mod-host / synapse-volume)에 공급.
- **하드웨어 관리 = Unix 소켓.** 캘리브레이션과 축별 채널/CC# 할당은
  `~/.modep/reflex.sock`으로 원격 관리(실물 컨트롤러의 "펌웨어 에디터 앱" 채널).
  Synapse가 유일한 의도된 클라이언트지만, reflex는 앱 없이도 완전 동작한다.
- **캘리브레이션은 reflex 소유.** 실물 페달이 자기 엔드포인트를 스스로 기억하듯,
  `~/.modep/pedal_calibration.json`(기존 경로 유지)을 reflex가 읽고 쓴다.

## MIDI 할당 (기본값, 소켓으로 변경 가능)

| 축 | ADS1115 | CC# | 이유 |
|---|---|---|---|
| volume | ch0 | **CC102** | 공유 버스에 예약 CC(7)를 올리면 채널 물린 플러그인이 명시 바인딩 없이 네이티브 반응할 수 있음 → undefined 대역(102-119) 사용. synapse-volume이 이 CC를 listen. |
| expression | ch1 | **CC103** | 같은 이유로 CC11 회피. mod-ui MIDI-learn으로 원하는 노브에 명시 매핑. |

CC7은 synapse-volume 내부의 private 링크(volumectl → jack_mix_box)에만 존재한다.

## 소켓 프로토콜 (JSON 한 줄 = 요청 하나, 응답 한 줄)

```bash
echo '{"cmd":"get_status"}' | nc -U ~/.modep/reflex.sock
```

| cmd | 인자 | 동작 |
|---|---|---|
| `get_status` | — | raw/현재 CC/매핑/캘리브레이션/pending/포트 상태 |
| `capture_heel` | `channel` | 현재 raw를 힐(최소) 후보로 기록 |
| `capture_toe` | `channel` | 현재 raw를 토(최대) 후보로 기록 |
| `save` | — | pending을 2% 안쪽 마진 적용해 캘리브레이션에 반영·저장 |
| `get_mapping` | — | 축별 {channel, cc} |
| `set_mapping` | `axis`, `channel`, `cc` | 매핑 변경·영속화(`~/.modep/reflex.json`) |

응답은 항상 `{"ok": true/false, ...}` + `get_status`에 `version` 필드.

## 캘리브레이션 절차 (SSH 또는 추후 앱 화면)

```bash
# 페달을 힐 끝까지 → capture_heel, 토 끝까지 → capture_toe, 저장
echo '{"cmd":"capture_heel","channel":0}' | nc -U ~/.modep/reflex.sock
echo '{"cmd":"capture_toe","channel":0}'  | nc -U ~/.modep/reflex.sock
echo '{"cmd":"save"}'                     | nc -U ~/.modep/reflex.sock
```

`get_status`의 `raw`를 보면서 페달을 왕복하면 배선/납땜 문제도 진단된다
(정상: 매끈한 단조 변화 — [`docs/expression-pedal-handoff-DONE.md`](../../docs/expression-pedal-handoff-DONE.md)).

## 설치

```bash
sudo deploy/reflex-service/install.sh
systemctl status synapse-reflex.service
```

GAAD67 포트가 아직 없어도 서비스는 뜬다(2초 간격 재시도, 그동안 소켓 캘리브레이션 가능).
MIDI 도착 확인: `aseqdump -p GAAD67` 또는 mod-ui MIDI-learn.
