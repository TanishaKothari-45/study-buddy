#!/bin/bash
# Script to run the current affairs downloader
# This script sets up the environment and runs the downloader

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Change to project root
cd "$PROJECT_ROOT"

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "❌ Error: Virtual environment not found at venv/bin/activate"
    exit 1
fi

# Set up logging directory
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# Generate log filename with date
LOG_FILE="$LOG_DIR/current_affairs_$(date +%Y%m%d_%H%M%S).log"

# Run the downloader and log output
echo "==========================================" >> "$LOG_FILE"
echo "Current Affairs Downloader - $(date)" >> "$LOG_FILE"
echo "==========================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Run the Python script and capture both stdout and stderr
python backend/app/utils/current_affairs_downloader.py >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

# Capture details for email notification
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

if [ $EXIT_CODE -eq 0 ]; then
    echo "" >> "$LOG_FILE"
    echo "✅ Successfully completed at $(date)" >> "$LOG_FILE"
    
    # Extract PDF name and chunk count from log for email
    PDF_NAME=$(grep -o "Workbook[^.]*\.pdf" "$LOG_FILE" | head -1 || echo "Unknown")
    CHUNKS=$(grep -o "Created [0-9]* chunks" "$LOG_FILE" | grep -o "[0-9]*" | head -1 || echo "0")
    
    # Send success email notification
    python -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from backend.app.utils.send_email import send_success_notification
send_success_notification('$PDF_NAME', $CHUNKS, '$LOG_FILE')
" 2>> "$LOG_FILE" || echo "⚠️ Email notification failed (non-critical)" >> "$LOG_FILE"
    
else
    echo "" >> "$LOG_FILE"
    echo "❌ Failed with exit code $EXIT_CODE at $(date)" >> "$LOG_FILE"
    
    # Send failure email notification
    python -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from backend.app.utils.send_email import send_failure_notification
send_failure_notification('Download or processing failed', $EXIT_CODE, '$LOG_FILE')
" 2>> "$LOG_FILE" || echo "⚠️ Email notification failed (non-critical)" >> "$LOG_FILE"
fi

# Keep only last 10 log files (cleanup old logs)
cd "$LOG_DIR"
ls -t current_affairs_*.log | tail -n +11 | xargs rm -f 2>/dev/null

exit $EXIT_CODE


