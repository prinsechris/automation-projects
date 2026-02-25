#!/usr/bin/env python3
"""
Add filtered/sorted views to the Command Center's existing linked databases.
Also adds linked databases for Daily Summary and Quests & Tasks.

Uses Notion internal API v3.
"""

import requests
import uuid
import json
import sys
from pathlib import Path

NOTION_API = "https://www.notion.so/api/v3"
COMMAND_CENTER_ID = "306da200-b2d6-819c-8863-cf78f61ae670"

# Existing linked DB blocks on Command Center
CC_BLOCKS = {
    "leaderboard": "310da200-b2d6-80c8-8722-e5c4e52d5993",
    "habits": "310da200-b2d6-80ce-9206-f5a1938275b9",
    "activity_log": "310da200-b2d6-80d1-8c2b-ce052652371a",
}

# Collection IDs
COLLECTIONS = {
    "activity_log": "305da200-b2d6-8116-8039-000b9a9d9070",
    "daily_summary": "6613764e-a18d-4cf5-8c66-d072afb309b8",
    "habits": "305da200-b2d6-8102-9f86-000b90c9fc2c",
    "quests": "305da200-b2d6-818e-bad3-000b048788f1",
    "leaderboard": "305da200-b2d6-81f1-8145-000b6fd7b000",
}

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

def get_collection_schema(headers, collection_id):
    data = api_post(headers, "getRecordValues", {
        "requests": [{"table": "collection", "id": collection_id}]
    })
    schema = data["results"][0]["value"]["schema"]
    return {info["name"]: pid for pid, info in schema.items()}

def make_table_format(columns):
    return {"table_properties": [
        {"property": c["id"], "visible": True, "width": c.get("width", 150)}
        for c in columns
    ]}

def make_date_filter(date_prop, period, direction="descending"):
    return {
        "filter": {"operator": "and", "filters": [{
            "property": date_prop,
            "filter": {"operator": "date_is_within", "value": {"type": "exact", "value": period}}
        }]},
        "sort": [{"property": date_prop, "direction": direction}]
    }


# === VIEW CONFIGS ===

def activity_log_views(p):
    """Views to add to existing Activity Log linked DB"""
    date = p.get("Date", "")
    cols = [
        {"id": "title", "width": 250}, {"id": date, "width": 150},
        {"id": p.get("XP", ""), "width": 80}, {"id": p.get("Gold", ""), "width": 80},
        {"id": p.get("Type", ""), "width": 120},
    ]
    return [
        {"name": "This Week", "type": "table",
         "query2": make_date_filter(date, "this_week"),
         "format": make_table_format(cols + [{"id": p.get("Habits", ""), "width": 150}])},
        {"name": "This Month", "type": "table",
         "query2": make_date_filter(date, "this_month"),
         "format": make_table_format(cols)},
        {"name": "This Year", "type": "table",
         "query2": make_date_filter(date, "this_year"),
         "format": make_table_format(cols)},
    ]

def habits_views(p):
    """Views to add to existing Habits linked DB"""
    return [
        {"name": "Performance", "type": "table",
         "query2": {"sort": [{"property": p.get("Success Rate %", ""), "direction": "descending"}]},
         "format": make_table_format([
             {"id": "title", "width": 200},
             {"id": p.get("Type", ""), "width": 130},
             {"id": p.get("Current Streak", ""), "width": 110},
             {"id": p.get("Success Rate %", ""), "width": 110},
             {"id": p.get("Completed This Month", ""), "width": 140},
         ])},
        {"name": "By Type", "type": "board",
         "query2": {"group_by": p.get("Type", "")},
         "format": {
             "board_properties": [
                 {"property": "title", "visible": True},
                 {"property": p.get("Success Rate %", ""), "visible": True},
                 {"property": p.get("Current Streak", ""), "visible": True},
             ],
         }},
    ]

def daily_summary_views(p):
    """Views for new Daily Summary linked DB"""
    date = p.get("Date", "")
    return [
        {"name": "Weekly", "type": "table",
         "query2": make_date_filter(date, "this_week"),
         "format": make_table_format([
             {"id": "title", "width": 200}, {"id": date, "width": 150},
             {"id": p.get("Activity Count", ""), "width": 120},
             {"id": p.get("Habits Completed", ""), "width": 140},
         ])},
        {"name": "Monthly", "type": "table",
         "query2": make_date_filter(date, "this_month"),
         "format": make_table_format([
             {"id": "title", "width": 200}, {"id": date, "width": 150},
             {"id": p.get("Activity Count", ""), "width": 120},
             {"id": p.get("Day of Week", ""), "width": 120},
         ])},
    ]

def quests_views(p):
    """Views for new Quests & Tasks linked DB"""
    status = p.get("Status", "")
    return [
        {"name": "Active", "type": "table",
         "query2": {
             "filter": {"operator": "or", "filters": [
                 {"property": status, "filter": {"operator": "enum_is", "value": {"type": "exact", "value": "In Progress"}}},
                 {"property": status, "filter": {"operator": "enum_is", "value": {"type": "exact", "value": "Ready To Start"}}},
             ]},
             "sort": [{"property": p.get("Due Date", ""), "direction": "ascending"}]
         },
         "format": make_table_format([
             {"id": "title", "width": 250},
             {"id": p.get("Category", ""), "width": 130},
             {"id": status, "width": 120},
             {"id": p.get("Due Date", ""), "width": 150},
             {"id": p.get("Difficulty", ""), "width": 120},
         ])},
        {"name": "Completed", "type": "table",
         "query2": {
             "filter": {"operator": "and", "filters": [{
                 "property": status,
                 "filter": {"operator": "enum_is", "value": {"type": "exact", "value": "Complete"}}
             }]},
             "sort": [{"property": p.get("Completed On", ""), "direction": "descending"}]
         },
         "format": make_table_format([
             {"id": "title", "width": 250},
             {"id": p.get("Category", ""), "width": 130},
             {"id": p.get("XP", ""), "width": 80},
             {"id": p.get("Gold", ""), "width": 80},
             {"id": p.get("Completed On", ""), "width": 150},
         ])},
        {"name": "By Category", "type": "board",
         "query2": {
             "filter": {"operator": "and", "filters": [{
                 "property": status,
                 "filter": {"operator": "enum_is_not", "value": {"type": "exact", "value": "Archive"}}
             }]},
             "group_by": p.get("Category", ""),
         },
         "format": {
             "board_properties": [
                 {"property": "title", "visible": True},
                 {"property": status, "visible": True},
                 {"property": p.get("Difficulty", ""), "visible": True},
                 {"property": p.get("Due Date", ""), "visible": True},
             ],
         }},
    ]


# === OPERATIONS ===

def build_add_views_to_existing_block(space_id, block_id, views_config):
    """Add new views as tabs to an existing linked database block"""
    operations = []
    view_ids = []

    for vc in views_config:
        view_id = new_id()
        view_ids.append(view_id)

        view_record = {
            "id": view_id, "version": 1, "type": vc["type"], "name": vc["name"],
            "alive": True, "parent_id": block_id, "parent_table": "block",
            "space_id": space_id,
        }
        if vc.get("query2"):
            view_record["query2"] = vc["query2"]
        if vc.get("format"):
            view_record["format"] = vc["format"]

        # Create the view record
        operations.append({
            "pointer": {"table": "collection_view", "id": view_id},
            "path": [], "command": "set", "args": view_record,
        })
        # Add view_id to the block's view_ids list
        operations.append({
            "pointer": {"table": "block", "id": block_id},
            "path": ["view_ids"],
            "command": "listAfter",
            "args": {"id": view_id},
        })

    return operations, view_ids


def build_new_linked_db(space_id, parent_id, collection_id, views_config, insert_after=None):
    """Create a new linked database block with views"""
    operations = []
    db_block_id = new_id()
    view_ids = []

    for vc in views_config:
        view_id = new_id()
        view_ids.append(view_id)

        view_record = {
            "id": view_id, "version": 1, "type": vc["type"], "name": vc["name"],
            "alive": True, "parent_id": db_block_id, "parent_table": "block",
            "space_id": space_id,
        }
        if vc.get("query2"):
            view_record["query2"] = vc["query2"]
        if vc.get("format"):
            view_record["format"] = vc["format"]

        operations.append({
            "pointer": {"table": "collection_view", "id": view_id},
            "path": [], "command": "set", "args": view_record,
        })

    # Create the collection_view block
    operations.append({
        "pointer": {"table": "block", "id": db_block_id},
        "path": [], "command": "set",
        "args": {
            "id": db_block_id, "version": 1, "type": "collection_view",
            "collection_id": collection_id, "view_ids": view_ids,
            "parent_id": parent_id, "parent_table": "block",
            "alive": True, "space_id": space_id,
        },
    })

    # Insert in parent content
    insert_args = {"id": db_block_id}
    if insert_after:
        insert_args["after"] = insert_after
    operations.append({
        "pointer": {"table": "block", "id": parent_id},
        "path": ["content"],
        "command": "listAfter",
        "args": insert_args,
    })

    return operations, db_block_id, view_ids


def main():
    print("=" * 55)
    print("  Add Views to Command Center")
    print("=" * 55)
    if DRY_RUN:
        print("\n  [DRY RUN]\n")

    token = load_token()
    headers = get_headers(token)

    # Load page
    print("[1/4] Loading Command Center...")
    space_id, content, blocks = get_page_info(headers, COMMAND_CENTER_ID)
    print(f"  Space: {space_id}, blocks: {len(content)}")

    # Verify existing blocks
    print("\n[2/4] Checking existing database blocks...")
    for name, block_id in CC_BLOCKS.items():
        block = blocks.get(block_id, {}).get("value", {})
        if block:
            existing_views = block.get("view_ids", [])
            coll = block.get("collection_id", "?")
            print(f"  {name}: block OK, collection={coll[:8]}..., {len(existing_views)} view(s)")
        else:
            print(f"  {name}: BLOCK NOT FOUND (will skip)")

    # Load schemas
    print("\n[3/4] Loading schemas...")
    schemas = {}
    for name in ["activity_log", "daily_summary", "habits", "quests"]:
        schemas[name] = get_collection_schema(headers, COLLECTIONS[name])
        print(f"  {name}: {len(schemas[name])} props")

    # Build operations
    print("\n[4/4] Building views...")
    all_ops = []
    summary = []

    # A) Add views to existing Activity Log
    al_block = CC_BLOCKS.get("activity_log")
    if al_block and blocks.get(al_block):
        views = activity_log_views(schemas["activity_log"])
        ops, vids = build_add_views_to_existing_block(space_id, al_block, views)
        all_ops.extend(ops)
        summary.append(f"  Activity Log: +{len(views)} views (This Week, This Month, This Year)")
        print(summary[-1])

    # B) Add views to existing Habits
    h_block = CC_BLOCKS.get("habits")
    if h_block and blocks.get(h_block):
        views = habits_views(schemas["habits"])
        ops, vids = build_add_views_to_existing_block(space_id, h_block, views)
        all_ops.extend(ops)
        summary.append(f"  Habits: +{len(views)} views (Performance, By Type)")
        print(summary[-1])

    # C) Create new Daily Summary linked DB
    # Find where to insert: after the columns block that contains the 3 databases
    # We'll find the divider after the columns
    columns_end = None
    for i, bid in enumerate(content):
        b = blocks.get(bid, {}).get("value", {})
        if b.get("type") == "column_list":
            # Check if this column_list contains our database blocks
            col_content = b.get("content", [])
            for col_id in col_content:
                col = blocks.get(col_id, {}).get("value", {})
                col_children = col.get("content", [])
                for child_id in col_children:
                    if child_id in CC_BLOCKS.values():
                        columns_end = bid
                        break

    if columns_end:
        print(f"  Found database columns block: {columns_end[:8]}...")

    # Insert Daily Summary after the columns
    insert_point = columns_end or content[-1]
    ds_views = daily_summary_views(schemas["daily_summary"])
    ops, ds_block, _ = build_new_linked_db(
        space_id, COMMAND_CENTER_ID, COLLECTIONS["daily_summary"],
        ds_views, insert_after=insert_point
    )
    all_ops.extend(ops)
    summary.append(f"  Daily Summary: NEW linked DB + {len(ds_views)} views (Weekly, Monthly)")
    print(summary[-1])

    # D) Create new Quests & Tasks linked DB after Daily Summary
    q_views = quests_views(schemas["quests"])
    ops, q_block, _ = build_new_linked_db(
        space_id, COMMAND_CENTER_ID, COLLECTIONS["quests"],
        q_views, insert_after=ds_block
    )
    all_ops.extend(ops)
    summary.append(f"  Quests & Tasks: NEW linked DB + {len(q_views)} views (Active, Completed, By Category)")
    print(summary[-1])

    # Execute
    total_views = sum(1 for op in all_ops if op["pointer"]["table"] == "collection_view")
    print(f"\n  Total: {total_views} views, {len(all_ops)} operations")

    if DRY_RUN:
        print("\n  [DRY RUN] No changes. Remove --dry-run to execute.")
        return

    resp = requests.post(f"{NOTION_API}/saveTransactions", headers=headers, json={
        "requestId": new_id(),
        "transactions": [{"id": new_id(), "spaceId": space_id, "operations": all_ops}]
    })

    if resp.status_code == 200:
        print(f"\n  [SUCCESS] Views added to Command Center!")
        print(f"  Open: https://www.notion.so/{COMMAND_CENTER_ID.replace('-', '')}")
    else:
        print(f"\n  [ERROR] {resp.status_code}: {resp.text[:500]}")


if __name__ == "__main__":
    main()
