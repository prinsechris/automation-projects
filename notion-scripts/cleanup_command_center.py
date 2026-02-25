#!/usr/bin/env python3
"""
Clean up Command Center:
1. Remove standalone Daily Summary linked DB (ugly)
2. Remove standalone Quests & Tasks linked DB (ugly)
3. Remove the STATS & ANALYTICS callout at bottom (redundant)
4. Keep the view tabs added to existing Activity Log and Habits (useful)
"""

import requests
import uuid
import json
import sys
from pathlib import Path

NOTION_API = "https://www.notion.so/api/v3"
COMMAND_CENTER_ID = "306da200-b2d6-819c-8863-cf78f61ae670"
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


def get_block_text(block):
    titles = block.get("properties", {}).get("title", [])
    if not titles:
        return ""
    return "".join([seg[0] for seg in titles])


def main():
    print("=" * 55)
    print("  Cleanup Command Center")
    print("=" * 55)
    if DRY_RUN:
        print("\n  [DRY RUN]\n")

    token = load_token()
    headers = get_headers(token)

    space_id, content, blocks = get_page_info(headers, COMMAND_CENTER_ID)
    print(f"  Page has {len(content)} blocks\n")

    blocks_to_remove = []

    # Scan all blocks
    for bid in content:
        b = blocks.get(bid, {}).get("value", {})
        btype = b.get("type", "")
        text = get_block_text(b)
        coll_id = b.get("collection_id", "")

        # Identify blocks to remove
        remove = False
        reason = ""

        # Standalone Daily Summary linked DB
        if btype == "collection_view" and coll_id == "6613764e-a18d-4cf5-8c66-d072afb309b8":
            remove = True
            reason = "Standalone Daily Summary (ugly)"

        # Standalone Quests linked DB
        elif btype == "collection_view" and coll_id == "305da200-b2d6-818e-bad3-000b048788f1":
            remove = True
            reason = "Standalone Quests & Tasks (ugly)"

        # STATS & ANALYTICS callout
        elif btype == "callout" and "STATS & ANALYTICS" in text:
            remove = True
            reason = "STATS & ANALYTICS callout (redundant)"

        status = "REMOVE" if remove else "keep"
        print(f"  [{status}] {btype:20s} {bid[:12]}... {text[:50] if text else coll_id[:20]}")

        if remove:
            blocks_to_remove.append((bid, reason))

    print(f"\n  Blocks to remove: {len(blocks_to_remove)}")
    for bid, reason in blocks_to_remove:
        print(f"    {bid[:12]}... — {reason}")

    if not blocks_to_remove:
        print("\n  Nothing to clean up!")
        return

    # Build operations
    operations = []
    for bid, reason in blocks_to_remove:
        # Remove from parent content
        operations.append({
            "pointer": {"table": "block", "id": COMMAND_CENTER_ID},
            "path": ["content"],
            "command": "listRemove",
            "args": {"id": bid},
        })
        # Mark as dead
        operations.append({
            "pointer": {"table": "block", "id": bid},
            "path": ["alive"],
            "command": "set",
            "args": False,
        })

    if DRY_RUN:
        print(f"\n  [DRY RUN] Would execute {len(operations)} operations. Remove --dry-run to execute.")
        return

    print(f"\n  Executing {len(operations)} operations...")
    resp = requests.post(f"{NOTION_API}/saveTransactions", headers=headers, json={
        "requestId": new_id(),
        "transactions": [{"id": new_id(), "spaceId": space_id, "operations": operations}]
    })

    if resp.status_code == 200:
        print("  [SUCCESS] Cleanup done!")
    else:
        print(f"  [ERROR] {resp.status_code}: {resp.text[:300]}")


if __name__ == "__main__":
    main()
