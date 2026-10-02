#!/bin/bash
cd "$(dirname "$0")"
nohup python app.py > app.log 2>&1 &
echo "PID: $!"