# 페달보드 저장 ttl 부패 — 포스트모템 (2026-06-26)

`save_current_pedalboard` 가 오래 망가져 있던 걸 고치는 과정에서, mod-ui 저장이 **stale 제목**으로
인해 페달보드 번들의 ttl 파일을 잘못 이름 붙여 **dir≠ttl 불일치(부패)** 를 만드는 버그를 발견·차단했다.

## 증상

- 풋스위치로 페달보드를 바꾼 뒤(또는 웹UI 타이틀이 stale인 상태에서) **저장**하면, 저장된 보드의 폴더 안에
  **엉뚱한 이름의 ttl** 이 생기고 manifest 가 그걸 가리켜, 원래 ttl 이 고아가 됨.
  - 예: `Exct_NAM_Widr.pedalboard/` 안에 `Crunch_0.ttl`(doap "Crunch 0") 이 활성, 원본 `Exct_NAM_Widr.ttl` 고아.
  - 손상된 번들들: `Exct_NAM_Widr`, `Drive_0`, `Drive_1` (모두 자기 그래프는 보존, **제목만** 오염).
- 자기강화: 일단 doap:name 이 오염되면, 그 보드를 깨끗이 로드만 해도 호스트가 오염된 이름을 방송 →
  웹UI 타이틀 stale 유지 → 다음 저장 또 오염. (디스크 복구 없이는 코드 수정만으로 안 멈춤.)

## 근본 원인 (2겹)

1. **앱 저장이 오래 죽어 있었음** — `save_current_pedalboard` 가 ① full-URL 을 `_request` endpoint 로 넘겨
   `http://localhost/http://localhost/...` 더블-prefix → 404, ② 그걸 고친 뒤엔 `json=` 바디라 mod-ui
   `PedalboardSave` 핸들러의 `get_argument('title')`(쿼리/form 만 읽음, JSON 바디 못 읽음)가 빈값 → 400.
   → 바른 endpoint + `data=`(form-encoded, 웹UI `$.ajax` 와 동일)로 복구.
   *(이 수정이 오래 실패하던 저장을 마침내 동작시키면서, 잠재돼 있던 stale-제목 결함이 디스크에 구현됨.)*
2. **stale 제목으로 잘못 명명** — mod-ui `host.py save()` 의 asNew=0 분기는 ttl 을 **현재 로드된 번들 dir**
   (`self.pedalboard_path`)에 쓰되 **파일명을 `symbolify(title)[:16]`**(클라이언트가 보낸 title)로 짓는다.
   풋스위치 내비 중 클라이언트(특히 웹UI)의 타이틀이 stale 하면, 로드된 보드(맞음)에 **이전 보드 이름의 ttl**을 써서 불일치.

### 확정 증거
- 고아 `Exct_NAM_Widr.ttl`(2025-03)의 `doap:name "Exct-NAM-Widr"`, `symbolify == "Exct_NAM_Widr" ==` dir →
  부패 직전까지 건강했음(잠복 노출 아니라 **그날 탄생**).
- 부패본 `Crunch_0.ttl`(Drive_1 안)은 **9블록 = Drive_1 자기 그래프**(진짜 Crunch_0 는 6블록) → 런타임 보드는
  올바르게 Drive_1 이었고 **제목만** 외래.
- 라이브 ws 캡처: 방송 메커니즘은 정상(`pedalboard_name` 발화). "staleness" 의 정체는 **디스크 doap:name 오염을 충실히 방송**한 것.

## 수정 (3겹 방어)

1. **앱 가드** (`modepctrl.save_current_pedalboard`): `symbolify(title)[:16]`(mod-ui와 동일 `_symbolify`)이 번들 dir 과
   어긋나면 **저장 중단+로그**. 앱은 절대 잘못 명명 못 함. (`-NNNNN` 충돌 접미사 dir 도 통과.)
2. **서버 구조적 차단(mod-tweak)** (`host.py:3965`, asNew=0 분기): ttl 심볼을 **번들 dir 명**에서 도출 →
   `dir==ttl==manifest` 구조 보장. **웹발 stale 저장도 파일 부패 불가**. `doap:name`(표시명)은 별도 `title` 인자라
   이름변경은 유지. save-as-new(else 분기)·로딩(manifest seeAlso 기반)·다른 보드 무영향. `sudo mod-tweaks/deploy.sh` 배포.
3. **디스크 복구**(1회성, 코드만으론 안 나음): 손상 번들마다 백업(`cp -a`+`tar`) → 활성(최신) ttl 을 `<dir>.ttl` 로 리네임 →
   `doap:name` 교정 → manifest seeAlso/subject 교정 → 고아 삭제. 복구 대상: `Exct_NAM_Widr`(→"Exct-NAM-Widr"),
   `Drive_0`(→"Drive 0"), `Drive_1`(→"Drive 1"), `BluesBreaker`(doap만 "Crunch 1"→"BluesBreaker"). 복구 후 전 보드 dir==ttl==doap 일치 확인.

## 잔여 / 후속

- **최초 트리거**(맨 처음 stale 제목이 어떻게 떴나)는 미확정 — 유력 가설: mod-ui 재시작 등으로 **끊긴 브라우저 웹UI 탭**이
  옛 이름을 들고 있다 저장. 웹 타이틀이 이상하면 **하드 리프레시**. 이제 mod-tweak 으로 파일 부패는 불가(최악이 doap 재오염, 복구 가능).
- **웹 타이틀 동기화(secondary)** — `loading_end` 의 `/snapshot/name` ajax 시퀀스 가드 / `snapshot_load` 시 `pedalboard_name`
  방송 등. 무결성엔 불필요, **표시 정확성용**으로만 추후.
- `CompAmpCabEqRev.pedalboard/Exct_NAM_Widr.ttl` (doap 없는 옛 고아 1개) — lilv 경고만, 무해. 청소 후보.
- **mod-ui 단독 재시작이 wedge 될 수 있음**(살아있는 mod-host 와 재핸드셰이크 실패, accept 큐 적체). 복구:
  `sudo systemctl restart modep-mod-host modep-mod-ui`(mod-host NAM/컨볼버 재로드 ~1분).
