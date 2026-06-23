#!/usr/bin/env bash
# mod-tweaks/deploy.sh — modep(mod-ui) 라이브 시스템 파일에 패치 사본을 배포한다.
#
# 전략: diff-patch 가 아니라 "파일 통째 cp".
#   mod-tweaks/*.py 는 패치가 적용된 완본이며 라이브와 byte-identical 로 유지된다.
#   cp 는 결정적(컨텍스트 어긋남으로 인한 부분 적용 실패가 없음)이라 라이브 악기에 가장 안전.
#   트레이드오프: modep 패키지 업데이트로 라이브가 바뀌면 그 변경을 통째로 덮어쓴다.
#   → 덮어쓰기 전 항상 타임스탬프 백업을 남기고, 적용 후 diff 로 검증한다.
#
# 앞으로 mod 코드(host/session/webserver) 수정 절차:
#   1) mod-tweaks/ 안의 해당 .py 를 직접 고친다 (= 다음 배포의 소스).
#   2) sudo ./deploy.sh 로 라이브에 반영.
#
# 사용법:
#   sudo ./deploy.sh                # 컴파일검사 → 백업 → cp → 검증 → 서비스 재시작
#   sudo ./deploy.sh --no-restart   # 재시작만 건너뜀
#   ./deploy.sh --check             # (sudo 불필요) 라이브 vs 소스 차이만 보고
#   ./deploy.sh --dry-run           # 무엇을 할지 출력만 (변경 없음)

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="/usr/lib/python3/dist-packages/mod"
SERVICE="modep-mod-ui"
FILES=(host.py session.py webserver.py)
# 비-파이썬 자산(웹 프론트 등): "소스파일::대상경로" 쌍. py_compile 없이 통째 cp.
ASSETS=("host.js::/usr/share/mod/html/js/host.js")

CHECK_ONLY=0
DRY_RUN=0
RESTART=1
for arg in "$@"; do
  case "$arg" in
    --check)      CHECK_ONLY=1 ;;
    --dry-run)    DRY_RUN=1 ;;
    --no-restart) RESTART=0 ;;
    -h|--help)    grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "알 수 없는 옵션: $arg" >&2; exit 2 ;;
  esac
done

echo "소스: $SRC_DIR"
echo "대상: $DEST_DIR"
echo

# --check : 차이만 보고하고 종료 (root 불필요)
if [[ "$CHECK_ONLY" == 1 ]]; then
  differ=0
  for f in "${FILES[@]}"; do
    if [[ ! -f "$DEST_DIR/$f" ]]; then
      echo "  [없음]   $f (라이브에 파일 없음)"; differ=1; continue
    fi
    if diff -q "$SRC_DIR/$f" "$DEST_DIR/$f" >/dev/null; then
      echo "  [동일]   $f"
    else
      echo "  [다름]   $f"; differ=1
    fi
  done
  for pair in "${ASSETS[@]}"; do
    src="${pair%%::*}"; dst="${pair##*::}"
    if [[ ! -f "$dst" ]]; then
      echo "  [없음]   $src (라이브에 없음: $dst)"; differ=1; continue
    fi
    if diff -q "$SRC_DIR/$src" "$dst" >/dev/null; then
      echo "  [동일]   $src"
    else
      echo "  [다름]   $src"; differ=1
    fi
  done
  exit $differ
fi

# 배포: root 필요
if [[ "$DRY_RUN" == 0 && "$(id -u)" != 0 ]]; then
  echo "오류: 시스템 디렉터리에 쓰려면 root 권한이 필요합니다. 'sudo ./deploy.sh'" >&2
  exit 1
fi

# 안전장치: 배포 전 모든 소스 파일이 파이썬 문법상 유효한지 확인 (깨진 코드 배포 방지)
echo "▶ 소스 컴파일 검사..."
for f in "${FILES[@]}"; do
  [[ -f "$SRC_DIR/$f" ]] || { echo "오류: 소스 없음 $SRC_DIR/$f" >&2; exit 1; }
  python3 -m py_compile "$SRC_DIR/$f" || { echo "오류: $f 컴파일 실패 — 배포 중단" >&2; exit 1; }
done
# 자산(.js) best-effort 문법검사: node 가 설치돼 있을 때만.
if command -v node >/dev/null 2>&1; then
  for pair in "${ASSETS[@]}"; do
    case "${pair%%::*}" in
      *.js) node --check "$SRC_DIR/${pair%%::*}" \
              || { echo "오류: ${pair%%::*} JS 문법 오류 — 배포 중단" >&2; exit 1; } ;;
    esac
  done
fi
echo "  OK"
echo

TS="$(date +%Y%m%d-%H%M%S)"
changed=0
for f in "${FILES[@]}"; do
  src="$SRC_DIR/$f"; dst="$DEST_DIR/$f"
  if [[ -f "$dst" ]] && diff -q "$src" "$dst" >/dev/null; then
    echo "  [건너뜀] $f (이미 최신)"
    continue
  fi
  changed=1
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "  [dry-run] $f → 백업 후 cp 예정"
    continue
  fi
  if [[ -f "$dst" ]]; then
    cp -p "$dst" "$dst.bak-$TS"
    echo "  [백업]   $f → $f.bak-$TS"
  fi
  cp "$src" "$dst"
  chown root:root "$dst"
  chmod 644 "$dst"
  # 적용 검증
  if diff -q "$src" "$dst" >/dev/null; then
    echo "  [배포]   $f ✓"
  else
    echo "오류: $f 배포 후 검증 실패" >&2; exit 1
  fi
done

# 자산(.js 등) 배포: py_compile 없이, .py 와 동일한 백업/cp/검증.
for pair in "${ASSETS[@]}"; do
  name="${pair%%::*}"; src="$SRC_DIR/$name"; dst="${pair##*::}"
  [[ -f "$src" ]] || { echo "오류: 소스 없음 $src" >&2; exit 1; }
  if [[ -f "$dst" ]] && diff -q "$src" "$dst" >/dev/null; then
    echo "  [건너뜀] $name (이미 최신)"
    continue
  fi
  changed=1
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "  [dry-run] $name → 백업 후 cp 예정"
    continue
  fi
  if [[ -f "$dst" ]]; then
    cp -p "$dst" "$dst.bak-$TS"
    echo "  [백업]   $name → $(basename "$dst").bak-$TS"
  fi
  cp "$src" "$dst"
  chown root:root "$dst"
  chmod 644 "$dst"
  if diff -q "$src" "$dst" >/dev/null; then
    echo "  [배포]   $name ✓"
  else
    echo "오류: $name 배포 후 검증 실패" >&2; exit 1
  fi
done

if [[ "$changed" == 0 ]]; then
  echo; echo "변경 없음 — 라이브가 이미 소스와 동일합니다."
  exit 0
fi

if [[ "$DRY_RUN" == 1 ]]; then
  echo; echo "dry-run 종료 (실제 변경 없음)."
  exit 0
fi

echo
if [[ "$RESTART" == 1 ]]; then
  echo "▶ $SERVICE 재시작..."
  systemctl restart "$SERVICE"
  echo "  완료. 상태: $(systemctl is-active "$SERVICE")"
else
  echo "재시작 건너뜀(--no-restart). 수동 반영: sudo systemctl restart $SERVICE"
fi
