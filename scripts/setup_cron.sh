#!/bin/bash
# Script to set up cron job for current affairs downloader
# This will add a cron job to run on the 10th of every month at 2:00 AM

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
CRON_SCRIPT="$SCRIPT_DIR/run_current_affairs_downloader.sh"

# Cron schedule: Run on 1st of every month at 2:00 AM
# Format: minute hour day month weekday
CRON_SCHEDULE="0 2 1 * *"

# Create cron job entry
CRON_JOB="$CRON_SCHEDULE $CRON_SCRIPT"

echo "=========================================="
echo "Setting up Current Affairs Cron Job"
echo "=========================================="
echo ""
echo "Schedule: 1st of every month at 2:00 AM"
echo "Script: $CRON_SCRIPT"
echo ""

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "$CRON_SCRIPT"; then
    echo "⚠️  Cron job already exists!"
    echo ""
    echo "Current crontab entries:"
    crontab -l | grep -A 2 -B 2 "$CRON_SCRIPT" || echo "   (none found)"
    echo ""
    read -p "Do you want to remove the existing entry and add a new one? (yes/no): " response
    if [ "$response" != "yes" ]; then
        echo "❌ Cancelled. No changes made."
        exit 0
    fi
    # Remove existing entry
    crontab -l 2>/dev/null | grep -v "$CRON_SCRIPT" | crontab -
    echo "✅ Removed existing cron job"
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "✅ Cron job added successfully!"
echo ""
echo "Cron job details:"
echo "   Schedule: $CRON_SCHEDULE (1st of every month at 2:00 AM)"
echo "   Command: $CRON_SCRIPT"
echo ""
echo "To view all cron jobs, run: crontab -l"
echo "To remove this cron job, run: crontab -e (then delete the line)"
echo ""
echo "To test the script manually, run:"
echo "   $CRON_SCRIPT"

