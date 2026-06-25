# 스냅샷 동기화 이슈 진단 — 완료 아카이브 (FINISHED, 2026-06-24)

> ✅ **상태: 해결됨(FINISHED) — 능동 참조용 아님.** 아래 본문은 2026-06-24 진단 기록을 그대로
> 박제한 것이고, 그 뒤 **수정 완료·코드 검증됨**. 요약:
> - 공통 뿌리 `snapshot_current_idx()` 항상 -1 → **dict 역조회로 수정**(§5 (a)안, [`modepctrl.py:147-149`](../modepctrl.py)).
>   이 한 군데로 **§2(앱 PREV/NEXT 먹통)·§3(웹→앱 라벨 안 변함)이 동시 해결**됨.
> - §6.1 미정의 `list_snapshot()` 지뢰 → `get_snapshot_list()`로 교체([`modepctrl.py:191,251`](../modepctrl.py)).
> - `handle_reverse_event`에 echo idx 파싱 + pb별 스냅샷 기억 추가([`presenter.py:200-214`](../presenter.py)).
>
> **인지된 잔여 약점(의도적):** ① (b)안 대신 (a)안을 택해 **이름 중복 스냅샷이면 역조회가 첫 매치를
> 짚을 수 있음**(§5 ⚠️). ② 역방향 `SnapshotLoad`가 여전히 무거운 `refresh_pedalboard()` 전체
> 재동기화를 탐(§6.3, "기존 동작 유지"로 보존).

## TL;DR

보고된 두 증상은 **하나의 공통 뿌리**에서 나온다:

> `ModepController.snapshot_current_idx()`가 **항상 `-1`을 반환**한다.
> `/snapshot/list`가 **dict**(`{"0":"Default", ...}`)를 주는데 코드가 그걸 **list로 가정**하고 `.index()`를 호출 → `dict`엔 `.index`가 없어 `AttributeError` → `try/except`에 먹혀 `-1` 반환.

- **Issue B (앱 NEXT/PREV SNAPSHOT 먹통)** = 직접 결과. `current_snapshot_idx`가 -1이라 prev 가드(`>0`)는 영영 불통과, next는 항상 0번(Default)만 다시 로드.
- **Issue A (웹→앱 스냅샷 표시 안 변함)** = 같은 -1이 뷰 라벨 조회 `dict["-1"]`에서 `KeyError` → `except KeyError: pass`로 삼켜져 라벨이 안 갱신됨. (역방향 알림 자체는 정상 도착하고 있음.)

→ `snapshot_current_idx()` 하나를 고치면 **둘 다** 해결된다.

이번 세션의 풋스위치 스레드화와는 **무관**하다(아래 §4).

---

## 0. 라이브 근거 (실측)

```
GET http://localhost/snapshot/list
  → {"0": "Default", "1": "hhhhdddd", "2": "hhhhdddd (2)", "3": "hhhhdddd (3)", "4": "hhhhdddd (4)"}
    (dict, 키가 문자열 "0".."4", 값이 이름)

GET http://localhost/snapshot/current
  → Default            (이름 문자열, 인덱스 아님)

python: hasattr(<그 dict>, "index")  →  False
```

mod-ui 핸들러(라이브 `/usr/lib/python3/dist-packages/mod/webserver.py`):
- `SnapshotList` → `dict((i, snapshots[i]['name']) ...)` 반환 (= 위 dict)
- `SnapshotCurrent` → `SESSION.host.snapshot_name()` (= 현재 스냅샷 **이름**)

---

## 1. 공통 뿌리: `snapshot_current_idx()` → 항상 -1

`modepctrl.py:141`
```python
@staticmethod
def snapshot_current_idx():
    snapshotlist = ModepController.get_snapshot_list()   # dict {"0":"Default", ...}
    if not snapshotlist:
        return -1
    try:
        current = ModepController.get_current_snapshot()  # "Default" (이름)
        idx = snapshotlist.index(current)                 # ← dict.index() 없음 → AttributeError
        if idx >= 0:
            return idx
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return -1                                             # ← 항상 여기로
```

- `get_snapshot_list()`(`modepctrl.py:166`)는 `/snapshot/list`의 `r.json()`을 그대로 반환 = **dict**.
- `dict.index(...)`는 존재하지 않음 → `AttributeError` → `except`로 잡혀 **-1** 반환.
- 설령 list였더라도 의도(이름→인덱스 역조회)는 `list.index(name)`이어야 하는데, 실제 반환이 dict라 처음부터 어긋남.

이 값은 `Pedalboard` 모델 생성 시마다 박힌다:
- `Pedalboard.__post_init__` → `_get_current_snapshot_idx()` (`modepctrl.py:574`) → `snapshot_current_idx()` → **-1**
- 즉 `self.pedalboard.current_snapshot_idx`는 부팅 직후에도, `refresh_pedalboard()` 후에도 **항상 -1**.
- `self.pedalboard.list_of_snapshots`는 그 **dict** 자체가 들어감(`_get_list_of_snapshots`, `modepctrl.py:578`). `len()`은 개수로 동작하나(=5) 의미상 list가 아님.

---

## 2. Issue B — 앱 NEXT/PREV SNAPSHOT 먹통

풋스위치 mode 0에서 FS2=`prev_snapshot`, FS3=`next_snapshot` (`presenter.py:332-336`).

`presenter.py:185`
```python
def prev_snapshot(self):
    if self.pedalboard.current_snapshot_idx > 0:     # -1 > 0  →  False  (영영 불통과)
        self.pedalboard.current_snapshot_idx -= 1
        ModepController.load_snapshot(self.pedalboard.current_snapshot_idx)
        self.refresh_pedalboard()

def next_snapshot(self):
    if self.pedalboard.current_snapshot_idx < len(self.pedalboard.list_of_snapshots) - 1:  # -1 < 4 → True
        self.pedalboard.current_snapshot_idx += 1     # -1 → 0
        ModepController.load_snapshot(0)              # 항상 0번(Default) 로드
        self.refresh_pedalboard()                     # → current_snapshot_idx 다시 -1로 리셋
```

- **PREV**: 가드 `-1 > 0`이 항상 거짓 → **아무 동작 안 함**.
- **NEXT**: -1 → 0으로 올려 **항상 0번(Default)만 로드**, refresh가 다시 -1로 되돌려 → 반복해도 0번에 고정. 사용자에겐 "안 바뀜/먹통"으로 보임.

`load_snapshot()`(`modepctrl.py:202`, `GET /snapshot/load?id=`)와 mod-ui `SnapshotLoad` 핸들러는 **정상**이다 — 끊긴 건 오직 인덱스 계산.

---

## 3. Issue A — 웹UI에서 스냅샷 변경 시 앱 표시 안 변함

역방향 알림은 **정상 작동**한다. 끊긴 지점은 표시(인덱스)다.

1. 웹UI에서 스냅샷 선택 → `snapshot.js` → `GET /snapshot/load?id=N`.
2. mod-ui `SnapshotLoad` 핸들러가 **`notify_synapsin("SnapshotLoad {idx}")`** 발화 (라이브 `webserver.py:1852`). ★알림은 실제로 앱으로 간다.
3. 앱 `app.py` 소켓 리스너 → `notify_presenter` → `presenter.handle_reverse_event`.
4. `presenter.py:143` — `"SnapshotLoad"`는 케이스에 들어있음 → **`self.refresh_pedalboard()` 호출됨**.
5. `refresh_pedalboard()`(`presenter.py:66`) → `initialize_modep_pedalboard()` → `current_snapshot_idx = -1` (§1).
6. `view_update_effect` → `refresh_plugin_display(snapshot=[-1, dict])` (`presenter.py:82`) → 뷰 라벨 갱신 시도.
7. `view.py:395`
   ```python
   def on_current_snapshot(self, instance, value):   # value = [-1, {"0":"Default", ...}]
       try:
           self.snapshot_label.text = f"{value[0]}-{value[1][str(value[0])]}"  # dict["-1"] → KeyError
       except KeyError:
           pass                                       # ← 삼켜짐 → 라벨 그대로
   ```
   `dict["-1"]`는 없는 키 → **KeyError → `pass`로 삼켜져 라벨이 이전 값에 멈춤**.

→ 결론: 웹→앱 알림은 멀쩡한데, **-1 때문에 라벨 조회가 KeyError로 죽고 조용히 무시**되어 표시가 안 변한다. (Gap C/D처럼 mod-ui에 notify를 추가할 필요가 **없다** — 이미 보내고 있다.)

---

## 4. 풋스위치 스레드화는 원인이 아님 (이번 세션 작업 면책)

- 같은 mode 0에서 **FS0/FS1 페달보드 nav는 정상**(사용자 확인). 풋스위치 plumbing(스레드/디바운스/마샬링)은 단일 콜백 전달이 동일하므로 FS2/FS3도 콜백은 정상 도달한다.
- 끊긴 건 콜백 **이후**의 스냅샷 로직(`snapshot_current_idx` -1). 따라서 스레드화 커밋과 무관하며, 이 버그는 그 이전부터 존재했다.

---

## 5. 수정안 (내일) — 구현 안 함, 검토용

핵심은 **`current_snapshot_idx`를 신뢰 가능한 값으로 만드는 것** 하나다. 후보:

### (a) `snapshot_current_idx()`를 dict 기준 역조회로 수정 (최소 변경)
```python
snapshotlist = ModepController.get_snapshot_list()   # {"0":"Default", ...}
current = ModepController.get_current_snapshot()      # "Default"
idx = next((int(k) for k, v in snapshotlist.items() if v == current), -1)
return idx
```
- 장점: 한 함수만 고치면 §2·§3 동시 해결.
- ⚠️ 주의: **이름 중복 위험**. 라이브 데이터에 `"hhhhdddd"`, `"hhhhdddd (2)"`... 이름이 유일하지 않을 수 있어, 같은 이름이 둘이면 첫 매치로 잘못 짚을 수 있다. (이름→인덱스 역조회 자체가 근본적으로 취약.)

### (b) 인덱스를 앱이 권위적으로 들고, 역방향 메시지의 idx를 직접 사용 (더 견고)
- mod-ui가 이미 `"SnapshotLoad {idx}"`로 **인덱스를 주고 있다**. `handle_reverse_event`에서 그 idx를 파싱해 `self.pedalboard.current_snapshot_idx`에 직접 반영하고 라벨만 갱신(무거운 `refresh_pedalboard` 전체 재조회 대신).
- 앱 자체 next/prev도 로컬 idx를 권위값으로 쓰고, `snapshot_current_idx()`의 이름 역조회에 의존하지 않게.
- 장점: 이름 중복에 안전, 가볍다(전체 재동기화 회피 = "반창고" 제거 방향과 일치). 단점: 변경 범위가 (a)보다 큼.

### (c) 뷰 방어
- `on_current_snapshot`이 idx=-1/없는 키일 때 KeyError를 **조용히 삼키지 말고** 안전한 표시(예: "—" 또는 0번)로 폴백. 근본 수정은 아니지만 회귀 안전망.

> 권장: **(b)를 메인, (c)를 안전망**으로. (a)는 빠른 임시방편이나 이름 중복 리스크 인지 필요.

---

## 6. 작업 중 발견한 2차/잠복 버그 (별개, 메모)

1. **`modepctrl.load_prev_snapshot`(`:191`)와 `snapshot_save_as`(`:251`)가 미정의 `list_snapshot()`을 호출** → 호출되면 `NameError`. 풋스위치 경로(=`presenter.prev_snapshot`)는 이걸 안 쓰므로 지금 증상과 무관하나, 호출 시 터지는 지뢰. (아마 `ModepController.get_snapshot_list()` 오타.)
2. **`get_snapshot_list()`가 dict인데 list로 쓰이는 가정이 여러 곳**에 퍼져 있을 수 있음 → 수정 시 전수 점검 권장(`list_of_snapshots` 사용처: `presenter.next_snapshot`의 `len()`은 OK, 뷰 라벨의 `dict[str(idx)]`는 OK).
3. 역방향 스냅샷 경로가 **무거운 `refresh_pedalboard()`(전체 재조회)** 를 탄다 — track1에서 떼려던 "반창고"와 같은 패턴. (b)안이 이것도 가볍게 만든다.

---

## 7. 내일 검증 항목

- [ ] 수정 후 `snapshot_current_idx()`가 실제 현재 인덱스를 반환(부팅/PB변경/스냅샷변경 각각)
- [ ] 앱 FS2(PREV)/FS3(NEXT)로 스냅샷이 순환 이동, 라벨 `{idx}-{name}` 정확
- [ ] 웹UI에서 스냅샷 변경 → 앱 라벨 추종
- [ ] 페달보드 변경(FS0/FS1) 후에도 스냅샷 인덱스/리스트가 **새 PB 기준**으로 갱신되는지(현재 `refresh_pedalboard`가 재조회하므로 OK일 것)
- [ ] 이름이 중복된 스냅샷에서도 올바른 인덱스((b)안이면 자연 해결)

---

### 참고 파일·라인
- 앱: `modepctrl.py:141`(snapshot_current_idx), `:166`(get_snapshot_list), `:202`(load_snapshot), `:574-580`(Pedalboard._get_*)
- 앱: `presenter.py:66`(refresh_pedalboard), `:82`(snapshot 전달), `:127-146`(handle_reverse_event), `:185-195`(prev/next_snapshot)
- 앱: `view.py:337`(current_snapshot 기본값), `:358-368`(snapshot_label), `:395-399`(on_current_snapshot, KeyError 삼킴), `:533-540`(refresh_plugin_display)
- mod-ui(라이브): `webserver.py:1852`(SnapshotLoad→notify_synapsin), `SnapshotList`/`SnapshotCurrent`/`SnapshotName` 핸들러, `host.py:~3250`(`pedal_snapshot %d %s` broadcast)
