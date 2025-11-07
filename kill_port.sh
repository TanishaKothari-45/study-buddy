#!/bin/bash

# Script to properly kill all processes on a given port
# Usage: ./kill_port.sh <PORT_NUMBER>

PORT=${1:-8003}

if [ -z "$PORT" ]; then
    echo "Usage: $0 <PORT_NUMBER>"
    echo "Example: $0 8003"
    exit 1
fi

echo "🔍 Checking for processes on port $PORT..."

# Find all PIDs using the port
PIDS=$(lsof -ti:$PORT 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo "✅ No processes found on port $PORT"
    exit 0
fi

echo "📋 Found processes: $PIDS"

# Method 1: Try graceful shutdown first (SIGTERM)
echo "🛑 Attempting graceful shutdown (SIGTERM)..."
for PID in $PIDS; do
    echo "  → Sending SIGTERM to PID $PID"
    kill -TERM $PID 2>/dev/null
done

# Wait a bit for graceful shutdown
sleep 2

# Check if processes are still running
REMAINING=$(lsof -ti:$PORT 2>/dev/null)

if [ -n "$REMAINING" ]; then
    echo "⚠️  Some processes didn't terminate gracefully"
    echo "💀 Force killing remaining processes (SIGKILL)..."
    
    # Method 2: Force kill (SIGKILL)
    for PID in $REMAINING; do
        echo "  → Force killing PID $PID"
        kill -9 $PID 2>/dev/null
    done
    
    sleep 1
fi

# Final check
FINAL_CHECK=$(lsof -ti:$PORT 2>/dev/null)

if [ -z "$FINAL_CHECK" ]; then
    echo "✅ Successfully killed all processes on port $PORT"
    echo "✅ Port $PORT is now free"
else
    echo "❌ Warning: Some processes may still be running: $FINAL_CHECK"
    echo "   These processes may be in an uninterruptible state (zombie processes)"
    echo "   You may need to:"
    echo "   1. Restart your Mac"
    echo "   2. Or use: sudo kill -9 $FINAL_CHECK"
    exit 1
fi

