#!/usr/bin/env python3
"""라이브 mod-ui 호스트에서 설치된 LV2 이펙터 + 포트 정보를 단일 JSON으로 덤프.

페달보드 에디터 목업(윈도)에서 "실제 설치된 이펙터/포트"를 그대로 쓰기 위한 카탈로그.

- /effect/list  -> 설치된 플러그인 URI 목록(요약, 포트 없음)
- /effect/get   -> 플러그인별 풀 정보(audio/control/cv/midi 포트 상세 포함)

gui 항목 중 절대경로(파이 한정) / 대용량 템플릿 문자열은 목업에 불필요하므로
basename 또는 길이 마커로 치환한다. 포트 데이터는 손실 없이 보존.

사용법:  python3 tools/dump_effects.py [--host http://localhost:80] [--out fixtures/installed-effects.json]
        (레포 루트에서 실행 — 기본 --out 경로 fixtures/...가 CWD 기준이므로)
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

# gui 에서 통째로 보존하기엔 크거나(아이콘 템플릿/스타일시트) 파이 절대경로라
# 목업에서 무의미한 필드 -> 길이 마커로 치환
GUI_DROP_BIG = ("iconTemplate", "stylesheet", "javascript", "documentation")
# 절대경로 -> basename 만 남길 필드
GUI_PATH_FIELDS = ("screenshot", "thumbnail", "resourcesDirectory")


def http_get_json(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def slim_gui(gui):
    """gui dict 정리: 포트 매핑/메타는 유지, 대용량·절대경로만 정리."""
    if not isinstance(gui, dict):
        return gui
    out = {}
    for k, v in gui.items():
        if k in GUI_DROP_BIG:
            if isinstance(v, str) and v:
                out[k] = f"<dropped: {len(v)} chars>"
            # 비어있으면 그냥 생략
        elif k in GUI_PATH_FIELDS and isinstance(v, str) and v:
            out[k] = os.path.basename(v.rstrip("/"))
        else:
            out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:80",
                    help="라이브 mod-ui 베이스 URL (기본 http://localhost:80)")
    ap.add_argument("--out", default="fixtures/installed-effects.json")
    args = ap.parse_args()

    base = args.host.rstrip("/")
    print(f"[*] /effect/list 조회: {base}/effect/list")
    summary = http_get_json(f"{base}/effect/list")
    uris = [e["uri"] for e in summary]
    print(f"[*] 설치된 이펙터 {len(uris)}개")

    plugins = []
    cat_count = {}
    for i, uri in enumerate(uris, 1):
        q = urllib.parse.urlencode({"uri": uri})
        try:
            info = http_get_json(f"{base}/effect/get?{q}")
        except Exception as ex:  # noqa: BLE001
            print(f"  [!] {uri} 실패: {ex}", file=sys.stderr)
            continue
        info["gui"] = slim_gui(info.get("gui"))
        plugins.append(info)

        p = info.get("ports", {})
        ai = len(p.get("audio", {}).get("input", []))
        ao = len(p.get("audio", {}).get("output", []))
        ci = len(p.get("control", {}).get("input", []))
        cat = (info.get("category") or ["(uncategorized)"])
        cat = cat[0] if isinstance(cat, list) and cat else (cat or "(uncategorized)")
        cat_count[cat] = cat_count.get(cat, 0) + 1
        print(f"  [{i:>2}/{len(uris)}] {info.get('name','?'):<28} "
              f"audio {ai}in/{ao}out  ctrl {ci:>2}  [{cat}]")

    out_doc = {
        "generated_from": f"{base}/effect/list + /effect/get",
        "note": "라이브 mod-ui 호스트에서 덤프. 페달보드 에디터 목업용 이펙터/포트 카탈로그.",
        "count": len(plugins),
        "categories": dict(sorted(cat_count.items(), key=lambda kv: -kv[1])),
        "plugins": plugins,
    }

    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_doc, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(out_path)
    print(f"\n[OK] {out_path} 작성 ({len(plugins)} plugins, {size:,} bytes)")
    print("[카테고리]")
    for c, n in out_doc["categories"].items():
        print(f"  {n:>3}  {c}")


if __name__ == "__main__":
    main()
