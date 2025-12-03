#!/bin/bash
# Script to set up launchd job for current affairs downloader
# This replaces the cron-based scheduling with macOS native launchd

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PLIST_FILE="$SCRIPT_DIR/com.studybuddy.currentaffairs.plist"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
LAUNCHD_PLIST="$LAUNCHD_DIR/com.studybuddy.currentaffairs.plist"

echo "🚀 Setting up launchd job for Current Affairs Downloader"
echo "=================================================="

# Create LaunchAgents directory if it doesn't exist
if [ ! -d "$LAUNCHD_DIR" ]; then
    echo "📁 Creating LaunchAgents directory..."
    mkdir -p "$LAUNCHD_DIR"
fi

# Copy plist file to LaunchAgents
echo "📋 Copying plist file to LaunchAgents..."
cp "$PLIST_FILE" "$LAUNCHD_PLIST"

# Unload existing job if it exists (ignore errors)
echo "🔄 Unloading existing job (if any)..."
launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true

# Load the new job
echo "✅ Loading launchd job..."
launchctl load "$LAUNCHD_PLIST"

# Verify the job is loaded
echo ""
echo "🔍 Verifying job status..."
if launchctl list | grep -q "com.studybuddy.currentaffairs"; then
    echo "✅ SUCCESS! launchd job is loaded and active"
    echo ""
    echo "📅 Schedule: 2nd of every month at 1:00 PM (13:00)"
    echo "📝 Logs will be written to:"
    echo "   - $HOME/Documents/Personal/study-buddy/logs/current_affairs_*.log"
    echo "   - $HOME/Documents/Personal/study-buddy/logs/launchd_stdout.log"
    echo "   - $HOME/Documents/Personal/study-buddy/logs/launchd_stderr.log"
    echo ""
    echo "💡 Note: Your Mac will attempt to wake from sleep to run this job"
    echo "   (works best when plugged into power)"
else
    echo "❌ ERROR: Job failed to load"
    exit 1
fi

echo ""
echo "=================================================="
echo "🎉 Setup complete!"
echo ""
echo "Useful commands:"
echo "  - View job status:  launchctl list | grep studybuddy"
echo "  - Unload job:       launchctl unload $LAUNCHD_PLIST"
echo "  - Reload job:       launchctl unload $LAUNCHD_PLIST && launchctl load $LAUNCHD_PLIST"
echo "  - Test run now:     launchctl start com.studybuddy.currentaffairs"
echo ""
