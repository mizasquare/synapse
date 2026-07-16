# ganglion-service — GECO1 페달 UI 부팅 자동실행

[`ganglion/app.py --device --live`](../../ganglion/app.py)를 systemd로 돌린다.
design.md ⑨-8("부팅 자동실행 방식, systemd 권장")의 구현.

```
sudo ./install.sh
```

## 무엇이 도는가

`--device` = 하드웨어 seam 양쪽 다 실물 (`runtime.run_device`):
입력은 seesaw 인코더 2개(0x36/0x37), 출력은 SH1107 OLED(0x3D) + NeoPixel 2개.
`--live` = 백엔드가 `FakeGeco`가 아니라 `GecoAdapter` → mod-host의 **실 그래프**를 편집한다.

**7인치 화면이 없는 리그다.** 그래서 `synapse-ui.service`와 공존을 고려할 필요가
없다(이 기기엔 설치조차 안 돼 있다). ganglion이 유일한 UI다.

## 왜 이렇게 짰나 (재론 방지)

- **`KillSignal=SIGINT`** — 이 유닛에서 제일 중요한 줄. systemd는 SIGTERM으로
  정지시키는데 파이썬 기본 SIGTERM은 `finally`도 `atexit`도 **안 태우고 즉사한다.**
  그러면 `systemctl stop`마다 OLED가 정적 화면을 켠 채 남고(**번인**) NeoPixel도
  켜진 채 남는다 — 정리 코드가 각각 `run_device`의 `finally`와 luma의 atexit 훅에
  살기 때문. SIGINT는 `KeyboardInterrupt`를 올리고 `run_device`가 그걸 이미 잡는다.
- **`Wants=` + `Restart=always`** (`Requires=` 아님) — `GecoAdapter.__init__`이
  생성 시점에 mod-host와 통신하므로 호스트가 답하기 전엔 못 뜬다. `After=`는 순서만
  줄 뿐 준비성을 기다려주지 않아서, 실제로 초기 부팅 레이스를 막는 건 재시도 루프다.
  `synapse-ui.service`가 택한 것과 같은 거래("fails loud, we retry").
  `Requires=`가 아닌 이유: mod-host 재시작이 이걸 같이 끌어내리면 안 된다.
- **`User=miza`** — `i2c` 그룹 소속이라 `/dev/i2c-1`(root:i2c 0660)에 닿는다.
  인코더와 OLED가 **같은 버스**를 쓴다.
- **venv 경로** — `/home/miza/synapse/venv`(system-site, gitignore됨). 시스템 파이썬은
  externally-managed라 luma.oled/blinka를 직접 못 넣는다. venv를 옮기면 유닛도 고칠 것.

## 버스 소유권 — 브링업 도구와 충돌한다

서비스가 도는 동안 인코더와 OLED를 **점유한다.** `oled_probe`/`encoder_bench`를
쓰려면 먼저 세워야 한다:

```
sudo systemctl stop ganglion.service
venv/bin/python -m ganglion.tools.oled_probe
sudo systemctl start ganglion.service
```

## 주의 — `--live`는 부팅 시 보드를 재작성할 수 있다

`GecoAdapter`는 기본적으로 **conform-on-load**다(사용자 결정 2026-07-06):
현재 보드가 quick-representable 형태가 아니면 로드 시점에 **파괴적으로 리빌드**한다.
즉 이 서비스는 부팅할 때마다 현재 보드를 정규화한다. 의도된 동작이지만,
mod-ui로 손댄 보드가 부팅 후 달라져 있으면 원인은 여기다.

## 진단

```
systemctl status ganglion.service
journalctl -u ganglion.service -f      # --device는 헤드리스라 평소엔 조용하다
journalctl -u ganglion.service -b      # 이번 부팅 전체 (재시작 루프 확인)
```

재시작 루프가 돌면 대개 둘 중 하나다: mod-host가 아직 안 떴거나(정상, 곧 붙는다),
i2c에 아무것도 없거나(`i2cdetect -y 1` → `36 37 3d`가 보여야 한다).
