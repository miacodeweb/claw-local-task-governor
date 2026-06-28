#!/bin/bash
# Start calibration app

APP_DIR="/opt/app"
LOG_FILE="/var/log/app.log"

cd "$APP_DIR" || exit 1

echo "Starting app at $(date)" >> "$LOG_FILE"
./bin/app --port 8080 >> "$LOG_FILE" 2>&1 &

echo "App started with PID $!"
