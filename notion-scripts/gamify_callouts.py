#!/usr/bin/env python3
"""
Gamify the 3 stats callouts (Week/Month/All Time) to match PLAYER STATS style.
Uses progress bars, icons, compact game-like layout.
"""

import requests
import uuid
import sys
from pathlib import Path

NOTION_API = "https://www.notion.so/api/v3"
COMMAND_CENTER_ID = "306da200-b2d6-819c-8863-cf78f61ae670"
STATS_PAGE_ID = "311da200-b2d6-8109-9fa4-ec1f53a93e7d"
DRY_RUN = "--dry-run" in sys.argv


def load_token():
    return (Path.home() / ".notion-token").read_text().strip()

def new_id():
    return str(uuid.uuid4())

def get_headers(token):
    return {"Content-Type": "application/json", "Cookie": f"token_v2={token}"}

def api_post(headers, endpoint, payload):
    resp = requests.post(f"{NOTION_API}/{endpoint}", headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()

def get_page_deep(headers, page_id):
    data = api_post(headers, "loadPageChunk", {
        "pageId": page_id, "limit": 200,
        "cursor": {"stack": []}, "chunkNumber": 0, "verticalColumns": False,
    })
    return data["recordMap"]["block"]

def get_text(block):
    titles = block.get("properties", {}).get("title", [])
    if not titles:
        return ""
    return "".join([seg[0] for seg in titles])

def find_callout_text_blocks(blocks, page_id):
    """Find the text child blocks of the stats callouts"""
    page = blocks.get(page_id, {}).get("value", {})
    results = {}

    for bid in page.get("content", []):
        b = blocks.get(bid, {}).get("value", {})
        if b.get("type") != "column_list":
            continue

        for col_id in b.get("content", []):
            col = blocks.get(col_id, {}).get("value", {})
            for callout_id in col.get("content", []):
                callout = blocks.get(callout_id, {}).get("value", {})
                if callout.get("type") != "callout":
                    continue

                # Check children for identifying text
                for child_id in callout.get("content", []):
                    child = blocks.get(child_id, {}).get("value", {})
                    text = get_text(child)

                    if "CETTE SEMAINE" in text:
                        results["week"] = {"callout_id": callout_id, "text_id": child_id}
                    elif "CE MOIS" in text:
                        results["month"] = {"callout_id": callout_id, "text_id": child_id}
                    elif "ALL TIME" in text:
                        results["alltime"] = {"callout_id": callout_id, "text_id": child_id}

    return results


def progress_bar(current, target, width=10):
    """Generate a text progress bar like ████░░░░░░"""
    if target == 0:
        filled = 0
    else:
        filled = min(int((current / target) * width), width)
    empty = width - filled
    return "\u2588" * filled + "\u2591" * empty


def main():
    print("=" * 55)
    print("  Gamify Stats Callouts")
    print("=" * 55)
    if DRY_RUN:
        print("\n  [DRY RUN]\n")

    token = load_token()
    headers = get_headers(token)
    blocks = get_page_deep(headers, COMMAND_CENTER_ID)

    targets = find_callout_text_blocks(blocks, COMMAND_CENTER_ID)
    for key, info in targets.items():
        print(f"  Found {key}: callout={info['callout_id'][:12]}... text={info['text_id'][:12]}...")

    if len(targets) < 3:
        print(f"  WARNING: Only found {len(targets)}/3 callouts")

    operations = []

    # === CETTE SEMAINE — gamified ===
    if "week" in targets:
        # Current week values (placeholder — n8n will update)
        xp, xp_goal = 100, 500
        gold = 125
        habits, habit_goal = 5, 35
        activities = 2
        streak = 2

        bar_xp = progress_bar(xp, xp_goal)
        bar_habits = progress_bar(habits, habit_goal)

        operations.append({
            "pointer": {"table": "block", "id": targets["week"]["text_id"]},
            "path": ["properties", "title"],
            "command": "set",
            "args": [
                ["\U0001f525 CETTE SEMAINE", [["b"]]],
                ["\n"],
                [f"\u2b50 XP: {xp}/{xp_goal} {bar_xp}"],
                ["\n"],
                [f"\U0001f4b0 Gold: {gold} | \u2764\ufe0f Streak: {streak}j"],
                ["\n"],
                [f"\U0001f4d3 Habits: {habits}/{habit_goal} {bar_habits}"],
                ["\n"],
                [f"\U0001f4c5 {activities} activities | \U0001f552 Auto"],
            ]
        })
        print(f"  Week: gamified with bars")

    # === CE MOIS — gamified ===
    if "month" in targets:
        xp, xp_goal = 100, 2000
        gold = 125
        habits, habit_goal = 5, 150
        activities = 2
        days_active = 2

        bar_xp = progress_bar(xp, xp_goal)
        bar_habits = progress_bar(habits, habit_goal)

        operations.append({
            "pointer": {"table": "block", "id": targets["month"]["text_id"]},
            "path": ["properties", "title"],
            "command": "set",
            "args": [
                ["\U0001f4c5 CE MOIS", [["b"]]],
                ["\n"],
                [f"\u2b50 XP: {xp}/{xp_goal} {bar_xp}"],
                ["\n"],
                [f"\U0001f4b0 Gold: {gold} | \U0001f4c6 {days_active}j actifs"],
                ["\n"],
                [f"\U0001f4d3 Habits: {habits}/{habit_goal} {bar_habits}"],
                ["\n"],
                [f"\U0001f3af {activities} activities | \U0001f552 Auto"],
            ]
        })
        print(f"  Month: gamified with bars")

    # === ALL TIME — gamified ===
    if "alltime" in targets:
        level = 1
        xp_total = 100
        xp_next = 200
        gold_total = 125
        best_streak = 2
        total_habits = 5
        total_quests = 0

        bar_level = progress_bar(xp_total, xp_next)

        operations.append({
            "pointer": {"table": "block", "id": targets["alltime"]["text_id"]},
            "path": ["properties", "title"],
            "command": "set",
            "args": [
                ["\U0001f3c6 ALL TIME", [["b"]]],
                [" \u2192 "],
                ["\u2068", [["p", STATS_PAGE_ID]]],
                ["\u2069"],
                ["\n"],
                [f"\u2b50 Lv.{level} {bar_level} {xp_total}/{xp_next} XP"],
                ["\n"],
                [f"\U0001f4b0 {gold_total} Gold | \U0001f525 Best: {best_streak}j"],
                ["\n"],
                [f"\U0001f4d3 {total_habits} habits | \u2694\ufe0f {total_quests} quests"],
            ]
        })
        print(f"  All Time: gamified with level bar")

    print(f"\n  Total: {len(operations)} operations")

    if DRY_RUN:
        print(f"\n  [DRY RUN] Remove --dry-run to execute.")
        return

    print(f"\n  Executing...")
    space_id = blocks.get(COMMAND_CENTER_ID, {}).get("value", {}).get("space_id")
    resp = requests.post(f"{NOTION_API}/saveTransactions", headers=headers, json={
        "requestId": new_id(),
        "transactions": [{"id": new_id(), "spaceId": space_id, "operations": operations}]
    })

    if resp.status_code == 200:
        print("  [SUCCESS] Callouts gamified!")
        print(f"  Open: https://www.notion.so/{COMMAND_CENTER_ID.replace('-', '')}")
    else:
        print(f"  [ERROR] {resp.status_code}: {resp.text[:500]}")


if __name__ == "__main__":
    main()
