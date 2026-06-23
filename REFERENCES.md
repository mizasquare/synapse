# 외부 의존 / 라이브 시스템 참조

이 repo는 **gcamp6s 앱** + 내가 mod-ui에 넣은 **패치 사본(mod-tweaks/)** 만 담는다.
실제 modep 소스(외부 소유·대용량)는 커밋하지 않고 여기에 위치만 기록한다.

## 라이브 시스템 (이 Pi가 ground truth)

| 대상 | 경로 | 비고 |
|---|---|---|
| 실제 mod-ui 라이브 소스 | `/usr/lib/python3/dist-packages/mod/` | modep-mod-ui 1.13.0, root 소유 |
| mod-host 바이너리 | `/usr/bin/mod-host` (`-p 5555 -f 5556`) | modep-mod-host 1.13.0 |
| 앱 venv | `/home/miza/gcamp6s-venv/` | repo 밖 |
| 앱 실행 스크립트(원본) | `/home/miza/run_synapsepy.sh` | repo의 `run_synapsepy.sh`는 그 사본 |

## 패치 적용 상태

`mod-tweaks/{host,session,webserver}.py` 가 패치 적용된 **완본**이며, 라이브
`/usr/lib/python3/dist-packages/mod/` 와 byte-identical 로 유지된다.
`mod-tweaks/org/` 는 upstream 원본 + `.diff`.

## mod 코드 배포 (mod-tweaks/deploy.sh)

mod 코드(host/session/webserver) 수정 시 **파일 통째 cp** 전략을 쓴다(diff-patch 아님 —
컨텍스트 어긋남으로 인한 부분 적용 실패가 라이브 악기에서 더 위험하므로).

절차:
1. `mod-tweaks/` 안의 해당 `.py` 를 직접 수정(= 다음 배포의 소스).
2. 라이브 반영: Pi 실제 터미널에서 `cd ~/synapse/mod-tweaks && sudo ./deploy.sh`
   - 배포 전 py_compile 검사 → 덮어쓰기 전 `<file>.bak-<타임스탬프>` 백업 → cp → diff 검증 → `modep-mod-ui` 재시작.
   - `./deploy.sh --check` : 라이브 vs 소스 차이만 확인(sudo 불필요).
   - `./deploy.sh --dry-run` / `--no-restart` 옵션 있음.
   - ★sudo 는 비대화형 셸 불가 → 반드시 사용자가 Pi 터미널에서 직접 실행.

## 자동 실행 체인

```
~/.config/labwc/autostart  →  ~/run_synapsepy.sh  →  venv activate  →  python app.py
```
- 컴포지터: **labwc (Wayland)**, 세션 `LXDE-pi-labwc`
- 웹UI: 온디맨드 `chromium-browser --start-fullscreen http://localhost/` (presenter.py)

## 환경

- Raspberry **Pi 5** (RP1, `pinctrl-rp1`), RAM 8GB, 부팅 ~12s
- 시스템 Python **3.11.2**, modep **1.13.0**
- I2C bus1: `0x27` MCP23017(풋스위치/LED), `0x49` ADS1115(노브/익스프레션)
- 터치: `ft5x06` 7" → `/dev/input/event9`
- MIDI: pisound / touchosc / pisound-ctl / amidithru `GAAD67`

## 커스텀 엔드포인트 (내 패치가 추가)

- `POST /effect/parameter/syn_set/<port>` , `GET /effect/parameter/syn_get/<port>`
- `POST /effect/parameter/syn_patch_set/<instance>` , `GET /effect/parameter/syn_patch_get/...`
- `POST /general/` (transport-bpm / transport-bpb)
- 역방향 알림: `notify_synapsin()` → unix dgram socket `/tmp/synapsin.sock` (앱이 bind)

## 알려진 이슈 (세션 0 정찰)

- `app.py:60 notify_presenter()` 가 `pass` → 역방향 채널 수신 후 폐기 (배선 끊김)
- `syn_parameter_set` 가 broadcast 경로(`host_and_web_parameter_set`) 우회 → 웹UI/HMI desync
- `presenter.py close_webui()` 가 `xdotool`(X11) 사용 → Wayland(labwc)에서 미동작 위험
