#!/bin/bash
# Image Validator API - Restart Script

API_DIR="/opt/media-pipeline/dataset-prep/01-validate"
PORT=8100
LOG_FILE="$API_DIR/api.log"

echo "[$(date)] Restarting Image Validator API..."

# Kill existing process
pkill -f "01-validate.*run.py api" 2>/dev/null
sleep 1

# Start API
cd "$API_DIR"
nohup ./venv/bin/python run.py api --port $PORT > "$LOG_FILE" 2>&1 &

echo "[$(date)] API started on port $PORT (PID: $!)"
