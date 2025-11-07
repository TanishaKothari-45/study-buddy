#!/bin/bash

# Script to properly restart the backend server
# This script kills any existing processes on the port before starting

PORT=${1:-8003}
BACKEND_DIR="backend"

echo "🔄 Restarting backend on port $PORT..."

# Step 1: Kill any existing processes on the port
echo "📋 Step 1: Cleaning up port $PORT..."
./kill_port.sh $PORT

# Step 2: Wait a moment to ensure port is free
sleep 1

# Step 3: Verify port is free
if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "❌ Port $PORT is still in use. Please check manually."
    exit 1
fi

# Step 4: Activate virtual environment and start server
echo "🚀 Step 2: Starting backend server..."
cd "$BACKEND_DIR" || exit 1

# Activate venv and start uvicorn
source ../venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port "$PORT"

