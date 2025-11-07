# Current Affairs Automatic Downloader - Cron Setup

This directory contains scripts to automatically download and process the latest VisionIAS monthly current affairs magazine on the 10th of every month.

## Files

- `run_current_affairs_downloader.sh` - Main script that runs the downloader (called by cron)
- `setup_cron.sh` - Helper script to set up the cron job
- `README_CRON.md` - This file

## Quick Setup

1. **Set up the cron job:**
   ```bash
   ./scripts/setup_cron.sh
   ```

2. **Verify the cron job was added:**
   ```bash
   crontab -l
   ```

3. **Test the script manually (optional):**
   ```bash
   ./scripts/run_current_affairs_downloader.sh
   ```

## What It Does

The cron job will:
1. Run on the **10th of every month at 2:00 AM**
2. Download the latest VisionIAS monthly workbook PDF
3. Extract Geography and Environment sections (pages 27-37)
4. Process the extracted PDF through chunking and enrichment
5. Store chunks in ChromaDB collection `geography_docs_enriched`
6. Log all output to `logs/current_affairs_YYYYMMDD_HHMMSS.log`

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

## Managing the Cron Job

**View all cron jobs:**
```bash
crontab -l
```

**Edit cron jobs:**
```bash
crontab -e
```

**Remove the current affairs cron job:**
```bash
crontab -l | grep -v "run_current_affairs_downloader.sh" | crontab -
```

## Log Files

- Logs are stored in `logs/current_affairs_YYYYMMDD_HHMMSS.log`
- Only the last 10 log files are kept (old ones are automatically deleted)
- Each log file contains:
  - Download status
  - Extraction status
  - Chunking progress
  - Metadata enrichment progress
  - ChromaDB storage status

## Troubleshooting

**If the cron job doesn't run:**
1. Check cron service is running: `sudo service cron status` (Linux) or check System Preferences (macOS)
2. Check cron logs: `grep CRON /var/log/syslog` (Linux) or check Console.app (macOS)
3. Verify the script path is correct: `which bash` and check the script path
4. Check file permissions: `ls -l scripts/run_current_affairs_downloader.sh`
5. Test manually: `./scripts/run_current_affairs_downloader.sh`

**If the script fails:**
1. Check the latest log file in `logs/`
2. Verify virtual environment exists: `ls venv/bin/activate`
3. Verify Python dependencies are installed: `pip list | grep playwright`
4. Check OpenAI API key is set: `grep OPENAI_API_KEY .env`

## Schedule Customization

To change the schedule, edit the cron job:
```bash
crontab -e
```

Cron format: `minute hour day month weekday`
- Current: `0 2 10 * *` (2:00 AM on 10th of every month)
- Examples:
  - `0 3 10 * *` - 3:00 AM on 10th
  - `0 2 10,20 * *` - 2:00 AM on 10th and 20th
  - `0 2 10 1,4,7,10 *` - 2:00 AM on 10th of Jan, Apr, Jul, Oct (quarterly)

