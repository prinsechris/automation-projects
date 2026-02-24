#!/usr/bin/env python3
"""
Upgrade Command Center callouts:
1. Replace single "CETTE SEMAINE" callout with 3-column layout:
   CETTE SEMAINE | CE MOIS | ALL TIME
2. Update PLAYER STATS with link to Stats page
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

def get_page_info(headers, page_id):
    data = api_post(headers, "loadPageChunk", {
        "pageId": page_id, "limit": 100,
        "cursor": {"stack": []}, "chunkNumber": 0, "verticalColumns": False,
    })
    blocks = data["recordMap"]["block"]
    page = blocks.get(page_id, {}).get("value", {})
    return page.get("space_id"), page.get("content", []), blocks

def get_block_text_deep(blocks, block_id):
    """Get text from block and its children"""
    b = blocks.get(block_id, {}).get("value", {})
    texts = []
    # Own title
    titles = b.get("properties", {}).get("title", [])
    if titles:
        texts.append("".join([seg[0] for seg in titles]))
    # Children text
    for child_id in b.get("content", []):
        child = blocks.get(child_id, {}).get("value", {})
        child_titles = child.get("properties", {}).get("title", [])
        if child_titles:
            texts.append("".join([seg[0] for seg in child_titles]))
    return " ".join(texts)


def make_block(block_id, space_id, parent_id, parent_table, btype, **kwargs):
    """Generic block creator"""
    block = {
        "id": block_id, "version": 1, "type": btype,
        "parent_id": parent_id, "parent_table": parent_table,
        "alive": True, "space_id": space_id,
    }
    block.update(kwargs)
    return block


def main():
    print("=" * 55)
    print("  Upgrade Command Center Callouts")
    print("=" * 55)
    if DRY_RUN:
        print("\n  [DRY RUN]\n")

    token = load_token()
    headers = get_headers(token)
    space_id, content, blocks = get_page_info(headers, COMMAND_CENTER_ID)
    print(f"  Page: {len(content)} blocks")

    # Find target blocks
    cette_semaine_id = None
    player_stats_text_id = None

    for bid in content:
        b = blocks.get(bid, {}).get("value", {})
        btype = b.get("type", "")
        deep_text = get_block_text_deep(blocks, bid)

        if btype == "callout" and "CETTE SEMAINE" in deep_text:
            cette_semaine_id = bid
            print(f"  Found CETTE SEMAINE: {bid}")

        if btype == "column_list":
            # Search inside columns for PLAYER STATS
            for col_id in b.get("content", []):
                col = blocks.get(col_id, {}).get("value", {})
                for child_id in col.get("content", []):
                    child_text = get_block_text_deep(blocks, child_id)
                    if "PLAYER STATS" in child_text:
                        # Find the first text child with the actual stats text
                        child_block = blocks.get(child_id, {}).get("value", {})
                        for grandchild_id in child_block.get("content", []):
                            gc = blocks.get(grandchild_id, {}).get("value", {})
                            gc_titles = gc.get("properties", {}).get("title", [])
                            if gc_titles:
                                gc_text = "".join([s[0] for s in gc_titles])
                                if "PLAYER STATS" in gc_text:
                                    player_stats_text_id = grandchild_id
                                    print(f"  Found PLAYER STATS text: {grandchild_id}")
                                    break

    if not cette_semaine_id:
        print("  ERROR: CETTE SEMAINE not found")
        return

    operations = []

    # === 1. CREATE 3-COLUMN STATS LAYOUT ===

    col_list_id = new_id()
    col1_id, col2_id, col3_id = new_id(), new_id(), new_id()
    callout_week_id, callout_month_id, callout_alltime_id = new_id(), new_id(), new_id()
    text_week_id, text_month_id, text_alltime_id = new_id(), new_id(), new_id()

    # --- Week callout ---
    operations.append({"pointer": {"table": "block", "id": callout_week_id},
        "path": [], "command": "set", "args": make_block(
            callout_week_id, space_id, col1_id, "block", "callout",
            content=[text_week_id],
            format={"page_icon": "\U0001f525", "block_color": "orange_background"},
        )})
    operations.append({"pointer": {"table": "block", "id": text_week_id},
        "path": [], "command": "set", "args": make_block(
            text_week_id, space_id, callout_week_id, "block", "text",
            properties={"title": [
                ["CETTE SEMAINE", [["b"]]],
                ["\n"],
                ["Habits: 5 | Gold: 125"],
                ["\n"],
                ["XP: 100 | Activities: 2"],
            ]},
        )})

    # --- Month callout ---
    operations.append({"pointer": {"table": "block", "id": callout_month_id},
        "path": [], "command": "set", "args": make_block(
            callout_month_id, space_id, col2_id, "block", "callout",
            content=[text_month_id],
            format={"page_icon": "\U0001f4c5", "block_color": "yellow_background"},
        )})
    operations.append({"pointer": {"table": "block", "id": text_month_id},
        "path": [], "command": "set", "args": make_block(
            text_month_id, space_id, callout_month_id, "block", "text",
            properties={"title": [
                ["CE MOIS", [["b"]]],
                ["\n"],
                ["Habits: 0 | Gold: 0"],
                ["\n"],
                ["XP: 0 | Activities: 0"],
            ]},
        )})

    # --- All Time callout ---
    operations.append({"pointer": {"table": "block", "id": callout_alltime_id},
        "path": [], "command": "set", "args": make_block(
            callout_alltime_id, space_id, col3_id, "block", "callout",
            content=[text_alltime_id],
            format={"page_icon": "\U0001f3c6", "block_color": "purple_background"},
        )})
    operations.append({"pointer": {"table": "block", "id": text_alltime_id},
        "path": [], "command": "set", "args": make_block(
            text_alltime_id, space_id, callout_alltime_id, "block", "text",
            properties={"title": [
                ["ALL TIME", [["b"]]],
                [" \u2192 "],
                ["\u2068", [["p", STATS_PAGE_ID]]],
                ["\u2069"],
                ["\n"],
                ["Level: 1 | XP: 100"],
                ["\n"],
                ["Gold: 125 | Streak: 0"],
            ]},
        )})

    # --- Columns ---
    for col_id, callout_id in [(col1_id, callout_week_id), (col2_id, callout_month_id), (col3_id, callout_alltime_id)]:
        operations.append({"pointer": {"table": "block", "id": col_id},
            "path": [], "command": "set", "args": make_block(
                col_id, space_id, col_list_id, "block", "column",
                content=[callout_id],
            )})

    # --- Column list ---
    operations.append({"pointer": {"table": "block", "id": col_list_id},
        "path": [], "command": "set", "args": make_block(
            col_list_id, space_id, COMMAND_CENTER_ID, "block", "column_list",
            content=[col1_id, col2_id, col3_id],
        )})

    # --- Insert and remove ---
    # Insert new column_list where old callout was
    operations.append({"pointer": {"table": "block", "id": COMMAND_CENTER_ID},
        "path": ["content"], "command": "listAfter",
        "args": {"after": cette_semaine_id, "id": col_list_id}})

    # Remove old callout
    operations.append({"pointer": {"table": "block", "id": COMMAND_CENTER_ID},
        "path": ["content"], "command": "listRemove",
        "args": {"id": cette_semaine_id}})
    operations.append({"pointer": {"table": "block", "id": cette_semaine_id},
        "path": ["alive"], "command": "set", "args": False})

    # === 2. UPDATE PLAYER STATS TEXT ===
    if player_stats_text_id:
        operations.append({"pointer": {"table": "block", "id": player_stats_text_id},
            "path": ["properties", "title"], "command": "set",
            "args": [
                ["PLAYER STATS", [["b"]]],
                [" \u2192 "],
                ["\u2068", [["p", STATS_PAGE_ID]]],
                ["\u2069"],
                ["\n"],
                ["\u2b50 Level: Level 1"],
                ["\n"],
                ["0% \u25a0\u25a0\u25a0\u25a0\u25a0\u25a0\u25a0\u25a0\u25a0\u25a0 100/200 | \U0001f4b0 Gold: 125"],
                ["\n"],
                ["\u2764\ufe0f Health: 100/100 HP | \U0001f4d3 Habits: 0/5"],
            ]})
        print(f"  Will update PLAYER STATS text")

    print(f"\n  Total: {len(operations)} operations")
    print(f"  Changes:")
    print(f"    CETTE SEMAINE -> 3 callouts (Week | Month | All Time)")
    if player_stats_text_id:
        print(f"    PLAYER STATS -> link to Stats & Analytics")

    if DRY_RUN:
        print(f"\n  [DRY RUN] Remove --dry-run to execute.")
        return

    print(f"\n  Executing...")
    resp = requests.post(f"{NOTION_API}/saveTransactions", headers=headers, json={
        "requestId": new_id(),
        "transactions": [{"id": new_id(), "spaceId": space_id, "operations": operations}]
    })

    if resp.status_code == 200:
        print("  [SUCCESS]")
        print(f"  Open: https://www.notion.so/{COMMAND_CENTER_ID.replace('-', '')}")
    else:
        print(f"  [ERROR] {resp.status_code}: {resp.text[:500]}")


if __name__ == "__main__":
    main()
