#!/bin/bash
# Activate the virtual environment
source /home/miza/synapse-venv/bin/activate

# Navigate to your app's directory
cd /home/miza/synapse  # Replace with the actual path to your app

# Run the app (Qt on-device entry: real MODEP + real I2C; rollback: run_synapsepy.sh.kivy-bak)
python qt_main.py

