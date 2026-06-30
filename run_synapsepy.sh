#!/bin/bash
# Activate the virtual environment
source /home/miza/synapse-venv/bin/activate

# Navigate to your app's directory
cd /home/miza/synapse  # Replace with the actual path to your app

# Run the app (Qt on-device entry: real MODEP + real I2C; rollback: run_synapsepy.sh.kivy-bak)
# 로그 캡처: 데스크탑 아이콘에서 띄우면 stdout/stderr가 사라지므로 파일로 남긴다.
# 현재 실행은 synapse.log, 직전 실행은 synapse.log.prev 로 1세대 보존(진단용).
LOG=/home/miza/synapse/logs/synapse.log
mkdir -p "$(dirname "$LOG")"
[ -f "$LOG" ] && mv "$LOG" "$LOG.prev"
exec python qt_main.py >"$LOG" 2>&1

