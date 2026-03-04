#!/usr/bin/env python3
"""
Add Stats & Analytics link to the Command Center page.
Uses Notion internal API v3 to insert a callout block.
"""

import requests
import uuid
import json
from pathlib import Path

NOTION_API = "https://www.notion.so/api/v3"
COMMAND_CENTER_ID = "306da200-b2d6-819c-8863-cf78f61ae670"
STATS_PAGE_ID = "311da200-b2d6-8109-9fa4-ec1f53a93e7d"


def load_token():
    return (Path.home() / ".notion-token").read_text().strip()


def new_id():
    return str(uuid.uuid4())


def get_headers(token):
    return {
        "Content-Type": "application/json",
        "Cookie": f"token_v2={token}",
    }


def get_page_info(headers, page_id):
    resp = requests.post(f"{NOTION_API}/loadPageChunk", headers=headers, json={
        "pageId": page_id,
        "limit": 100,
        "cursor": {"stack": []},
        "chunkNumber": 0,
        "verticalColumns": False,
    })
    resp.raise_for_status()
    data = resp.json()
    blocks = data["recordMap"]["block"]
    page_block = blocks.get(page_id, {}).get("value", {})
    space_id = page_block.get("space_id")
    content = page_block.get("content", [])
    return space_id, content, blocks


def find_cette_semaine_block(blocks, content):
    """Find the 'CETTE SEMAINE' callout block to insert after it"""
    for block_id in content:
        block = blocks.get(block_id, {}).get("value", {})
        if block.get("type") == "callout":
            titles = block.get("properties", {}).get("title", [])
            text = "".join([seg[0] for seg in titles]) if titles else ""
            if "CETTE SEMAINE" in text:
                return block_id
    return None


def main():
    token = load_token()
    headers = get_headers(token)

    print("Loading Command Center...")
    space_id, content, blocks = get_page_info(headers, COMMAND_CENTER_ID)
    print(f"  Space: {space_id}, blocks: {len(content)}")

    # Find the "CETTE SEMAINE" callout to insert after
    target_block = find_cette_semaine_block(blocks, content)
    if not target_block:
        print("  Could not find 'CETTE SEMAINE' block, inserting at end")
        target_block = content[-1] if content else None

    print(f"  Insert after: {target_block[:8]}...")

    # Create a new callout block with link to Stats
    callout_id = new_id()

    operations = [
        # Create the callout block
        {
            "pointer": {"table": "block", "id": callout_id},
            "path": [],
            "command": "set",
            "args": {
                "id": callout_id,
                "version": 1,
                "type": "callout",
                "properties": {
                    "title": [
                        ["STATS & ANALYTICS ", [["b"]]],
                        [" \u2014 "],
                        ["\u2068"],
                        ["\u2068", [["p", STATS_PAGE_ID]]],
                        ["\u2069"],
                        ["\u2069"],
                        ["\n"],
                        ["Habits | Quests | Activity | Daily Summary"],
                    ]
                },
                "format": {
                    "page_icon": "\ud83d\udcca",
                    "block_color": "blue_background",
                },
                "parent_id": COMMAND_CENTER_ID,
                "parent_table": "block",
                "alive": True,
                "space_id": space_id,
            },
        },
        # Insert after the target block
        {
            "pointer": {"table": "block", "id": COMMAND_CENTER_ID},
            "path": ["content"],
            "command": "listAfter",
            "args": {"after": target_block, "id": callout_id},
        },
    ]

    print(f"  Sending {len(operations)} operations...")
    resp = requests.post(f"{NOTION_API}/saveTransactions", headers=headers, json={
        "requestId": new_id(),
        "transactions": [{
            "id": new_id(),
            "spaceId": space_id,
            "operations": operations,
        }]
    })

    if resp.status_code == 200:
        print("\n  [SUCCESS] Stats callout added to Command Center!")
        print(f"  Open: https://www.notion.so/{COMMAND_CENTER_ID.replace('-', '')}")
    else:
        print(f"\n  [ERROR] {resp.status_code}: {resp.text[:300]}")


if __name__ == "__main__":
    main()
