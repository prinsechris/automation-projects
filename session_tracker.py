#!/usr/bin/env python3
"""
Session Tracker — Log Claude Code sessions to Notion automatically.

Captures work done in Claude Code sessions even without git commits.
Called via Claude Code hooks (post-session) or manually.

Writes to:
- Notion Activity Log (for gamification tracking)
- Notification queue (for digest)
- Notion Projects & Tasks (updates task status if applicable)
"""

import json
import os
import sys
import requests
from datetime import datetime

# Config
NOTION_API = "https://api.notion.com/v1"
NOTION_TOKEN = open(os.path.expanduser("~/.notion-api-token")).read().strip() if os.path.exists(os.path.expanduser("~/.notion-api-token")) else None
PROJECTS_DB = "305da200-b2d6-8145-bc16-eaee02925a14"
ACTIVITY_LOG_DB = "305da200-b2d6-819f-915f-d35f51386aa8"
QUEUE_FILE = os.path.expanduser("~/n8n-workflows/notification_queue.json")
SESSION_LOG = os.path.expanduser("~/n8n-workflows/session_log.json")

def _headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def log_session(summary: str, tasks_worked: list = None, files_changed: list = None,
                category: str = "dev", duration_min: int = 0):
    """Log a Claude Code session to Notion and the notification queue."""

    now = datetime.now()
    session = {
        "timestamp": now.isoformat(),
        "summary": summary,
        "tasks_worked": tasks_worked or [],
        "files_changed": files_changed or [],
        "category": category,
        "duration_min": duration_min,
    }

    results = []

    # 1. Update matching Notion tasks to "In Progress" if not already
    if NOTION_TOKEN and tasks_worked:
        for task_keyword in tasks_worked:
            try:
                # Search for matching task
                query = {
                    "filter": {
                        "and": [
                            {"property": "Status", "status": {"does_not_equal": "Complete"}},
                            {"property": "Status", "status": {"does_not_equal": "Archive"}},
                        ]
                    },
                    "page_size": 20
                }
                r = requests.post(
                    f"{NOTION_API}/databases/{PROJECTS_DB}/query",
                    headers=_headers(), json=query, timeout=10
                )
                if r.status_code == 200:
                    for page in r.json().get("results", []):
                        name = ""
                        title_prop = page.get("properties", {}).get("Name", {})
                        for t in title_prop.get("title", []):
                            name += t.get("plain_text", "")

                        if task_keyword.lower() in name.lower():
                            # Check if status is not already In Progress
                            status = page.get("properties", {}).get("Status", {}).get("status", {}).get("name", "")
                            if status not in ("In Progress", "Complete"):
                                # Move to In Progress
                                requests.patch(
                                    f"{NOTION_API}/pages/{page['id']}",
                                    headers=_headers(),
                                    json={"properties": {"Status": {"status": {"name": "In Progress"}}}},
                                    timeout=10
                                )
                                results.append(f"Task '{name}' → In Progress")
                            break
            except Exception as e:
                results.append(f"Error updating task: {e}")

    # 2. Log to Activity Log via gamification.py (updates state + Notion + Leaderboard)
    if duration_min > 0:
        try:
            import sys
            sys.path.insert(0, os.path.expanduser("~/manager-bot"))
            from gamification import log_activity
            xp = min(duration_min // 10 * 5, 50)  # 5 XP per 10 min, max 50
            gold = xp // 2
            gami_result = log_activity(f"Session: {summary[:80]}", activity_type="session", xp=xp, gold=gold)
            results.append(f"Gamification: +{xp} XP, +{gold} Gold (via gamification.py)")
        except Exception as e:
            # Fallback: write directly to Notion if gamification.py fails
            try:
                if NOTION_TOKEN:
                    xp = min(duration_min // 10 * 5, 50)
                    requests.post(
                        f"{NOTION_API}/pages",
                        headers=_headers(),
                        json={
                            "parent": {"database_id": ACTIVITY_LOG_DB},
                            "properties": {
                                "Name": {"title": [{"text": {"content": f"Session: {summary[:80]}"}}]},
                                "XP": {"number": xp},
                                "Gold": {"number": xp // 2},
                                "Date": {"date": {"start": now.strftime("%Y-%m-%d")}},
                            }
                        },
                        timeout=10
                    )
                    results.append(f"Activity Log (fallback): +{xp} XP, +{xp//2} Gold")
            except Exception as e2:
                results.append(f"Activity Log error: {e2}")

    # 3. Add to notification queue
    try:
        queue = []
        if os.path.exists(QUEUE_FILE):
            with open(QUEUE_FILE) as f:
                queue = json.load(f)

        files_str = f" ({len(files_changed)} fichiers)" if files_changed else ""
        queue.append({
            "timestamp": now.isoformat(),
            "message": f"Session Claude Code: {summary}{files_str}",
            "category": "task",
            "priority": "P2",
            "source": "Session Tracker"
        })
        with open(QUEUE_FILE, "w") as f:
            json.dump(queue, f, indent=2)
        results.append("Queued for digest")
    except Exception as e:
        results.append(f"Queue error: {e}")

    # 4. Append to local session log
    try:
        sessions = []
        if os.path.exists(SESSION_LOG):
            with open(SESSION_LOG) as f:
                sessions = json.load(f)
        sessions.append(session)
        # Keep last 100 sessions
        sessions = sessions[-100:]
        with open(SESSION_LOG, "w") as f:
            json.dump(sessions, f, indent=2)
    except Exception:
        pass

    return {"success": True, "results": results, "session": session}


if __name__ == "__main__":
    # CLI usage: python3 session_tracker.py "summary" --tasks "task1,task2" --duration 60
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", help="Session summary")
    parser.add_argument("--tasks", default="", help="Comma-separated task keywords")
    parser.add_argument("--files", default="", help="Comma-separated files changed")
    parser.add_argument("--category", default="dev", help="Category")
    parser.add_argument("--duration", type=int, default=0, help="Duration in minutes")
    args = parser.parse_args()

    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    files = [f.strip() for f in args.files.split(",") if f.strip()]

    result = log_session(args.summary, tasks, files, args.category, args.duration)
    print(json.dumps(result, indent=2, ensure_ascii=False))
