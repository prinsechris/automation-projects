#!/usr/bin/env python3
"""Inspect all blocks on Command Center"""
import requests, json
from pathlib import Path

NOTION_API = "https://www.notion.so/api/v3"
CC_ID = "306da200-b2d6-819c-8863-cf78f61ae670"

token = (Path.home() / ".notion-token").read_text().strip()
headers = {"Content-Type": "application/json", "Cookie": f"token_v2={token}"}

data = requests.post(f"{NOTION_API}/loadPageChunk", headers=headers, json={
    "pageId": CC_ID, "limit": 100, "cursor": {"stack": []},
    "chunkNumber": 0, "verticalColumns": False,
}).json()

blocks = data["recordMap"]["block"]
page = blocks[CC_ID]["value"]
content = page.get("content", [])

print(f"Page has {len(content)} top-level blocks:\n")

def inspect_block(bid, indent=0):
    b = blocks.get(bid, {}).get("value", {})
    if not b:
        print(f"{'  '*indent}[?] {bid[:12]}... NOT IN RESPONSE")
        return

    btype = b.get("type", "?")
    titles = b.get("properties", {}).get("title", [])
    text_preview = ""
    if titles:
        text_preview = "".join([seg[0] for seg in titles])[:80]

    coll = b.get("collection_id", "")
    views = b.get("view_ids", [])
    fmt = b.get("format", {})
    icon = fmt.get("page_icon", "")
    color = fmt.get("block_color", "")

    extra = ""
    if coll:
        extra += f" coll={coll[:12]}"
    if views:
        extra += f" views={len(views)}"
    if icon:
        extra += f" icon={icon}"
    if color:
        extra += f" color={color}"

    print(f"{'  '*indent}[{btype}] {bid[:12]}...{extra}")
    if text_preview:
        print(f"{'  '*indent}  text: {text_preview}")

    # Recurse into children
    children = b.get("content", [])
    for child_id in children:
        inspect_block(child_id, indent + 1)

for bid in content:
    inspect_block(bid)
    print()
