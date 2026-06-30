#!/bin/bash
# Activate the virtual environment
source /home/miza/synapse-venv/bin/activate

# Navigate to your app's directory
cd /home/miza/synapse  # Replace with the actual path to your app

# Run the app (Qt on-device entry: real MODEP + real I2C; rollback: run_synapsepy.sh.kivy-bak)
# 로그 캡처: 데스크탑 아이콘에서 띄우면 stdout/stderr가 사라지므로 파일로 남긴다.
# 실행마다 타임스탬프 파일로 남기고, 7일 지난 로그는 정리(일주일치 보존). 진단용.
LOGDIR=/home/miza/synapse/logs
mkdir -p "$LOGDIR"
find "$LOGDIR" -name 'synapse-*.log' -type f -mtime +7 -delete 2>/dev/null
LOG="$LOGDIR/synapse-$(date +%Y%m%d-%H%M%S)-$$.log"   # PID로 동일초 충돌 방지
ln -sfn "$(basename "$LOG")" "$LOGDIR/latest.log"      # 최신 로그 바로가기
exec python qt_main.py >"$LOG" 2>&1

