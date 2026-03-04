#!/bin/bash
# Git pre-push hook — triggers the Activity Tracker after push completes.
# Runs in background with 15s delay (time for push to finish on GitHub).
# Uses lockfile to avoid concurrent runs with cron.

TRACKER="/home/claude-agent/n8n-workflows/git_activity_tracker.py"
LOG="/home/claude-agent/n8n-workflows/tracker.log"
REPO_NAME=$(basename "$(git rev-parse --show-toplevel)")

(
    sleep 15
    /usr/bin/python3 "$TRACKER" --window 1 --repo "$REPO_NAME" --source "push-hook" >> "$LOG" 2>&1
) &

exit 0
