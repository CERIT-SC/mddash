#!/bin/bash
set -euo pipefail

echo "$(date): [API] Starting API container..."

# Start forward auth service in background
echo "$(date): [API] Starting Forward Auth on port 5001..."
python /opt/auth/auth.py &
AUTH_PID=$!
echo "$(date): [API] Forward Auth started with PID: $AUTH_PID"

# Start API server in foreground
echo "$(date): [API] Starting API on port 5000..."
exec python /opt/api/app.py
