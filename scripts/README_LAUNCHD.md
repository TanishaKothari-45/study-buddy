# Current Affairs Automatic Downloader - Setup Guide

This directory contains scripts to automatically download and process the latest VisionIAS monthly current affairs magazine on the **2nd of every month at 1:00 PM**.

## Files

- `run_current_affairs_downloader.sh` - Main script that runs the downloader
- `setup_launchd.sh` - Setup script for macOS launchd (recommended)
- `setup_cron.sh` - Legacy cron setup (not recommended for macOS)
- `com.studybuddy.currentaffairs.plist` - launchd configuration file
- `README_LAUNCHD.md` - This file

## Quick Setup (macOS - Recommended)

### Using launchd (Recommended for macOS)

1. **Set up the launchd job:**
   ```bash
   ./scripts/setup_launchd.sh
   ```

2. **Verify the job is loaded:**
   ```bash
   launchctl list | grep studybuddy
   ```

3. **Test the job manually (optional):**
   ```bash
   launchctl start com.studybuddy.currentaffairs
   ```

### Using cron (Legacy - Not Recommended)

⚠️ **Note:** Cron jobs don't run when your Mac is asleep. Use launchd instead.

```bash
./scripts/setup_cron.sh
```

## What It Does

The scheduled job will:
1. Run on the **2nd of every month at 1:00 PM (13:00)**
2. Wake your Mac from sleep (if plugged into power)
3. Download the latest VisionIAS monthly workbook PDF
4. Extract Geography and Environment sections (pages 27-37)
5. Process the extracted PDF through chunking and metadata classification
6. Store embeddings in Pinecone index
7. Store full content in SQLite database (content_store)
8. Send email notification on success/failure
9. Log all output to `logs/current_affairs_YYYYMMDD_HHMMSS.log`

## Manual Testing

To test the script manually:
```bash
./scripts/run_current_affairs_downloader.sh
```

Check the logs:
```bash
ls -lt logs/current_affairs_*.log | head -1
tail -f logs/current_affairs_*.log
```

## Managing the launchd Job

**View job status:**
```bash
launchctl list | grep studybuddy
```

**View detailed job info:**
```bash
launchctl print gui/$(id -u)/com.studybuddy.currentaffairs
```

**Unload (disable) the job:**
```bash
launchctl unload ~/Library/LaunchAgents/com.studybuddy.currentaffairs.plist
```

**Reload (re-enable) the job:**
```bash
launchctl load ~/Library/LaunchAgents/com.studybuddy.currentaffairs.plist
```

**Trigger job manually (test run):**
```bash
launchctl start com.studybuddy.currentaffairs
```

**Remove the job completely:**
```bash
launchctl unload ~/Library/LaunchAgents/com.studybuddy.currentaffairs.plist
rm ~/Library/LaunchAgents/com.studybuddy.currentaffairs.plist
```

## Log Files

- **Script logs:** `logs/current_affairs_YYYYMMDD_HHMMSS.log`
- **launchd stdout:** `logs/launchd_stdout.log`
- **launchd stderr:** `logs/launchd_stderr.log`
- Only the last 10 script log files are kept (old ones are automatically deleted)

Each log file contains:
- Download status
- Extraction status
- Chunking progress
- Metadata enrichment progress
- Pinecone storage status
- Email notification status

## Troubleshooting

### If the launchd job doesn't run:

1. **Check if job is loaded:**
   ```bash
   launchctl list | grep studybuddy
   ```

2. **Check launchd logs:**
   ```bash
   cat ~/Documents/Personal/study-buddy/logs/launchd_stderr.log
   cat ~/Documents/Personal/study-buddy/logs/launchd_stdout.log
   ```

3. **Check if Mac was asleep:**
   - launchd will attempt to wake your Mac, but this works best when plugged into power
   - Check: System Settings → Battery → Options → Enable Power Nap

4. **Verify file permissions:**
   ```bash
   ls -l scripts/run_current_affairs_downloader.sh
   ls -l ~/Library/LaunchAgents/com.studybuddy.currentaffairs.plist
   ```

5. **Test manually:**
   ```bash
   launchctl start com.studybuddy.currentaffairs
   # Then check logs immediately
   tail -f logs/launchd_stdout.log
   ```

### If the script fails:

1. **Check the latest log file:**
   ```bash
   ls -lt logs/current_affairs_*.log | head -1
   cat $(ls -t logs/current_affairs_*.log | head -1)
   ```

2. **Verify virtual environment:**
   ```bash
   ls venv/bin/activate
   ```

3. **Verify Python dependencies:**
   ```bash
   source venv/bin/activate
   pip list | grep -E "playwright|pypdf|pinecone"
   ```

4. **Check environment variables:**
   ```bash
   grep -E "OPENAI_API_KEY|PINECONE_API_KEY" .env
   ```

## Schedule Customization

To change the schedule, edit the plist file:
```bash
nano ~/Library/LaunchAgents/com.studybuddy.currentaffairs.plist
```

Find the `StartCalendarInterval` section and modify:
```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Day</key>
    <integer>2</integer>        <!-- Day of month (1-31) -->
    <key>Hour</key>
    <integer>13</integer>       <!-- Hour (0-23, 13 = 1 PM) -->
    <key>Minute</key>
    <integer>0</integer>        <!-- Minute (0-59) -->
</dict>
```

After editing, reload the job:
```bash
launchctl unload ~/Library/LaunchAgents/com.studybuddy.currentaffairs.plist
launchctl load ~/Library/LaunchAgents/com.studybuddy.currentaffairs.plist
```

### Example Schedules:

**Run on 1st at 3:00 PM:**
```xml
<key>Day</key><integer>1</integer>
<key>Hour</key><integer>15</integer>
<key>Minute</key><integer>0</integer>
```

**Run on 1st and 15th at 1:00 PM:**
```xml
<key>StartCalendarInterval</key>
<array>
    <dict>
        <key>Day</key><integer>1</integer>
        <key>Hour</key><integer>13</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <dict>
        <key>Day</key><integer>15</integer>
        <key>Hour</key><integer>13</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
</array>
```

## Why launchd Instead of cron?

1. ✅ **Can wake Mac from sleep** (when plugged into power)
2. ✅ **Native macOS solution** - better integrated with the system
3. ✅ **More reliable** - cron jobs don't run when Mac is asleep
4. ✅ **Better logging** - separate stdout/stderr logs
5. ✅ **Easier management** - simple load/unload commands

## Email Notifications

The script sends email notifications on both success and failure:
- **Success:** Includes PDF name and chunk count
- **Failure:** Includes error details and log file path

Email configuration is in `.env` file.
