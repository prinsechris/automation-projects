#!/usr/bin/env python3
"""
Stats & Analytics Dashboard — View Creator

Uses Notion internal API v3 to:
1. Replace placeholder text blocks with linked database views
2. Create filtered/sorted views for each database section

Prerequisites:
    1. Get your token_v2 from Notion web (DevTools > Application > Cookies > token_v2)
    2. Save it to ~/.notion-token
    3. pip install requests
    4. Run: python3 create_stats_views.py
    5. Add --dry-run to preview without making changes

Author: Adaptive Logic / Claude Code
"""

import requests
import uuid
import json
import sys
import os
from pathlib import Path

# === CONFIG ===
NOTION_API = "https://www.notion.so/api/v3"
STATS_PAGE_ID = "311da200-b2d6-8109-9fa4-ec1f53a93e7d"
COMMAND_CENTER_ID = "306da200-b2d6-819c-8863-cf78f61ae670"

# Collection IDs (from Notion MCP fetch)
COLLECTIONS = {
    "activity_log": "305da200-b2d6-8116-8039-000b9a9d9070",
    "daily_summary": "6613764e-a18d-4cf5-8c66-d072afb309b8",
    "habits": "305da200-b2d6-8102-9f86-000b90c9fc2c",
    "quests": "305da200-b2d6-818e-bad3-000b048788f1",
}

# Database display names
DB_NAMES = {
    "activity_log": "Activity Log",
    "daily_summary": "Daily Summary",
    "habits": "Habits",
    "quests": "Quests & Tasks",
}

DRY_RUN = "--dry-run" in sys.argv


# === HELPERS ===

def load_token():
    token_path = Path.home() / ".notion-token"
    if not token_path.exists():
        print(f"ERROR: Token file not found at {token_path}")
        print()
        print("How to get your token_v2:")
        print("  1. Open https://www.notion.so in your browser")
        print("  2. Open DevTools (F12)")
        print("  3. Go to Application > Cookies > notion.so")
        print("  4. Find 'token_v2' and copy its value")
        print(f"  5. Save it: echo 'YOUR_TOKEN' > {token_path}")
        sys.exit(1)
    return token_path.read_text().strip()


def get_headers(token):
    return {
        "Content-Type": "application/json",
        "Cookie": f"token_v2={token}",
    }


def new_id():
    return str(uuid.uuid4())


def api_post(headers, endpoint, payload):
    resp = requests.post(f"{NOTION_API}/{endpoint}", headers=headers, json=payload)
    if resp.status_code != 200:
        print(f"  API ERROR ({endpoint}): {resp.status_code}")
        print(f"  {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json()


# === STEP 1: PAGE INFO ===

def get_page_info(headers, page_id):
    """Load page blocks, space_id, and block tree"""
    data = api_post(headers, "loadPageChunk", {
        "pageId": page_id,
        "limit": 100,
        "cursor": {"stack": []},
        "chunkNumber": 0,
        "verticalColumns": False,
    })

    blocks = data["recordMap"]["block"]
    page_block = blocks.get(page_id, {}).get("value", {})
    space_id = page_block.get("space_id")
    content = page_block.get("content", [])

    return space_id, content, blocks


# === STEP 2: COLLECTION SCHEMAS ===

def get_collection_schema(headers, collection_id):
    """Get property name -> property ID mapping for a collection"""
    data = api_post(headers, "getRecordValues", {
        "requests": [{"table": "collection", "id": collection_id}]
    })

    result = data["results"][0]
    if not result.get("value"):
        raise ValueError(f"Collection {collection_id} not found")

    schema = result["value"]["schema"]
    prop_map = {}
    for prop_id, prop_info in schema.items():
        prop_map[prop_info["name"]] = prop_id

    return prop_map


# === STEP 3: FIND PLACEHOLDERS ===

def get_block_text(block_data):
    """Extract plain text from a block's title property"""
    titles = block_data.get("properties", {}).get("title", [])
    if not titles:
        return ""
    return "".join([segment[0] for segment in titles])


def find_placeholder_blocks(blocks, page_content):
    """Find placeholder blocks that should be replaced with databases.

    Returns dict: db_key -> {
        "placeholder_id": block to remove,
        "heading_id": heading block to insert after
    }
    """
    placeholders = {}

    for i, block_id in enumerate(page_content):
        block = blocks.get(block_id, {}).get("value", {})
        if block.get("type") != "text":
            continue

        text = get_block_text(block)
        if "Base de donnees" not in text:
            continue

        # Look backwards for the heading
        if i == 0:
            continue

        prev_id = page_content[i - 1]
        prev_block = blocks.get(prev_id, {}).get("value", {})
        prev_text = get_block_text(prev_block)

        # Match heading to database key
        db_key = None
        if "Activity Log" in prev_text:
            db_key = "activity_log"
        elif "Daily Summary" in prev_text:
            db_key = "daily_summary"
        elif "Habits" in prev_text:
            db_key = "habits"
        elif "Quests" in prev_text:
            db_key = "quests"

        if db_key:
            placeholders[db_key] = {
                "placeholder_id": block_id,
                "heading_id": prev_id,
            }

    return placeholders


# === STEP 4: VIEW CONFIGURATIONS ===

def make_table_format(columns):
    """Build table_properties format from column list"""
    return {
        "table_properties": [
            {"property": col["id"], "visible": True, "width": col.get("width", 150)}
            for col in columns
        ]
    }


def make_date_filter(date_prop_id, period, direction="descending"):
    """Build a query2 with date filter and sort"""
    return {
        "filter": {
            "operator": "and",
            "filters": [{
                "property": date_prop_id,
                "filter": {
                    "operator": "date_is_within",
                    "value": {"type": "exact", "value": period}
                }
            }]
        },
        "sort": [{"property": date_prop_id, "direction": direction}]
    }


def build_activity_log_views(prop_map):
    """4 views: This Week, This Month, This Year, XP Trend"""
    p = {k: prop_map.get(k, "") for k in ["Date", "XP", "Gold", "Type", "Habits"]}

    base_cols = [
        {"id": "title", "width": 250},
        {"id": p["Date"], "width": 150},
        {"id": p["XP"], "width": 80},
        {"id": p["Gold"], "width": 80},
        {"id": p["Type"], "width": 120},
    ]

    return [
        {
            "name": "This Week",
            "type": "table",
            "query2": make_date_filter(p["Date"], "this_week"),
            "format": make_table_format(base_cols + [{"id": p["Habits"], "width": 150}]),
        },
        {
            "name": "This Month",
            "type": "table",
            "query2": make_date_filter(p["Date"], "this_month"),
            "format": make_table_format(base_cols + [{"id": p["Habits"], "width": 150}]),
        },
        {
            "name": "This Year",
            "type": "table",
            "query2": make_date_filter(p["Date"], "this_year"),
            "format": make_table_format(base_cols),
        },
        {
            "name": "XP Trend",
            "type": "chart",
            "query2": make_date_filter(p["Date"], "this_month", "ascending"),
            "format": {
                "chart_style": "line",
                "chart_properties": {
                    "x_axis_property": p["Date"],
                    "y_axis_property": p["XP"],
                    "y_axis_aggregation": "sum",
                },
            },
        },
    ]


def build_daily_summary_views(prop_map):
    """3 views: Weekly, Monthly, Yearly"""
    p = {k: prop_map.get(k, "") for k in ["Date", "Activity Count", "Habits Completed", "Day of Week"]}

    return [
        {
            "name": "Weekly",
            "type": "table",
            "query2": make_date_filter(p["Date"], "this_week"),
            "format": make_table_format([
                {"id": "title", "width": 200},
                {"id": p["Date"], "width": 150},
                {"id": p["Activity Count"], "width": 120},
                {"id": p["Habits Completed"], "width": 140},
            ]),
        },
        {
            "name": "Monthly",
            "type": "table",
            "query2": make_date_filter(p["Date"], "this_month"),
            "format": make_table_format([
                {"id": "title", "width": 200},
                {"id": p["Date"], "width": 150},
                {"id": p["Activity Count"], "width": 120},
                {"id": p["Day of Week"], "width": 120},
            ]),
        },
        {
            "name": "Yearly",
            "type": "table",
            "query2": make_date_filter(p["Date"], "this_year"),
            "format": make_table_format([
                {"id": "title", "width": 200},
                {"id": p["Date"], "width": 150},
                {"id": p["Activity Count"], "width": 120},
            ]),
        },
    ]


def build_habits_views(prop_map):
    """2 views: Performance (table sorted by success rate), By Type (board)"""
    p = {k: prop_map.get(k, "") for k in [
        "Type", "Current Streak", "Success Rate %", "Completed This Month", "Difficulty"
    ]}

    return [
        {
            "name": "Performance",
            "type": "table",
            "query2": {
                "sort": [{"property": p["Success Rate %"], "direction": "descending"}]
            },
            "format": make_table_format([
                {"id": "title", "width": 200},
                {"id": p["Type"], "width": 130},
                {"id": p["Current Streak"], "width": 120},
                {"id": p["Success Rate %"], "width": 120},
                {"id": p["Completed This Month"], "width": 150},
                {"id": p["Difficulty"], "width": 120},
            ]),
        },
        {
            "name": "By Type",
            "type": "board",
            "query2": {
                "group_by": p["Type"],
            },
            "format": {
                "board_properties": [
                    {"property": "title", "visible": True},
                    {"property": p["Success Rate %"], "visible": True},
                    {"property": p["Current Streak"], "visible": True},
                ],
                "board_groups2": [
                    {"property": p["Type"], "value": {"type": "multi_select", "value": "Morning"}, "hidden": False},
                    {"property": p["Type"], "value": {"type": "multi_select", "value": "Mid-Day"}, "hidden": False},
                    {"property": p["Type"], "value": {"type": "multi_select", "value": "Evening"}, "hidden": False},
                    {"property": p["Type"], "value": {"type": "multi_select", "value": "Bedtime"}, "hidden": False},
                ],
            },
        },
    ]


def build_quests_views(prop_map):
    """3 views: Completed, By Category, Active"""
    p = {k: prop_map.get(k, "") for k in [
        "Category", "Status", "Difficulty", "XP", "Gold", "Completed On", "Due Date"
    ]}

    return [
        {
            "name": "Completed",
            "type": "table",
            "query2": {
                "filter": {
                    "operator": "and",
                    "filters": [{
                        "property": p["Status"],
                        "filter": {
                            "operator": "enum_is",
                            "value": {"type": "exact", "value": "Complete"}
                        }
                    }]
                },
                "sort": [{"property": p["Completed On"], "direction": "descending"}]
            },
            "format": make_table_format([
                {"id": "title", "width": 250},
                {"id": p["Category"], "width": 130},
                {"id": p["Difficulty"], "width": 120},
                {"id": p["XP"], "width": 80},
                {"id": p["Gold"], "width": 80},
                {"id": p["Completed On"], "width": 150},
            ]),
        },
        {
            "name": "By Category",
            "type": "board",
            "query2": {
                "filter": {
                    "operator": "and",
                    "filters": [{
                        "property": p["Status"],
                        "filter": {
                            "operator": "enum_is_not",
                            "value": {"type": "exact", "value": "Archive"}
                        }
                    }]
                },
                "group_by": p["Category"],
            },
            "format": {
                "board_properties": [
                    {"property": "title", "visible": True},
                    {"property": p["Status"], "visible": True},
                    {"property": p["Difficulty"], "visible": True},
                    {"property": p["Due Date"], "visible": True},
                ],
            },
        },
        {
            "name": "Active",
            "type": "table",
            "query2": {
                "filter": {
                    "operator": "or",
                    "filters": [
                        {
                            "property": p["Status"],
                            "filter": {
                                "operator": "enum_is",
                                "value": {"type": "exact", "value": "In Progress"}
                            }
                        },
                        {
                            "property": p["Status"],
                            "filter": {
                                "operator": "enum_is",
                                "value": {"type": "exact", "value": "Ready To Start"}
                            }
                        },
                    ]
                },
                "sort": [{"property": p["Due Date"], "direction": "ascending"}]
            },
            "format": make_table_format([
                {"id": "title", "width": 250},
                {"id": p["Category"], "width": 130},
                {"id": p["Status"], "width": 120},
                {"id": p["Due Date"], "width": 150},
                {"id": p["Difficulty"], "width": 120},
            ]),
        },
    ]


# === STEP 5: BUILD OPERATIONS ===

def build_linked_db_operations(space_id, parent_block_id, placeholder_id, heading_id,
                                collection_id, views_config):
    """Build all saveTransactions operations for one linked database.

    Creates:
    - collection_view block (linked database)
    - N collection_view records (views with filters/sorts)
    - Replaces placeholder block in parent content
    """
    operations = []
    db_block_id = new_id()
    view_ids = []

    # 1. Create each view record
    for vc in views_config:
        view_id = new_id()
        view_ids.append(view_id)

        view_record = {
            "id": view_id,
            "version": 1,
            "type": vc["type"],
            "name": vc["name"],
            "alive": True,
            "parent_id": db_block_id,
            "parent_table": "block",
            "space_id": space_id,
        }

        # Add query2 (filters/sorts)
        if vc.get("query2"):
            view_record["query2"] = vc["query2"]

        # Add format (columns, widths, board config)
        if vc.get("format"):
            view_record["format"] = vc["format"]

        operations.append({
            "pointer": {"table": "collection_view", "id": view_id},
            "path": [],
            "command": "set",
            "args": view_record,
        })

    # 2. Create the collection_view block (linked database)
    operations.append({
        "pointer": {"table": "block", "id": db_block_id},
        "path": [],
        "command": "set",
        "args": {
            "id": db_block_id,
            "version": 1,
            "type": "collection_view",
            "collection_id": collection_id,
            "view_ids": view_ids,
            "parent_id": parent_block_id,
            "parent_table": "block",
            "alive": True,
            "space_id": space_id,
        },
    })

    # 3. Insert linked DB after the heading (before placeholder position)
    operations.append({
        "pointer": {"table": "block", "id": parent_block_id},
        "path": ["content"],
        "command": "listAfter",
        "args": {"after": heading_id, "id": db_block_id},
    })

    # 4. Remove placeholder from parent content
    operations.append({
        "pointer": {"table": "block", "id": parent_block_id},
        "path": ["content"],
        "command": "listRemove",
        "args": {"id": placeholder_id},
    })

    # 5. Mark placeholder as dead
    operations.append({
        "pointer": {"table": "block", "id": placeholder_id},
        "path": ["alive"],
        "command": "set",
        "args": False,
    })

    return operations, db_block_id, view_ids


# === MAIN ===

def main():
    print("=" * 50)
    print("  Stats & Analytics — View Creator")
    print("=" * 50)

    if DRY_RUN:
        print("\n  [DRY RUN MODE — no changes will be made]\n")

    # Load token
    token = load_token()
    headers = get_headers(token)
    print("[OK] Token loaded")

    # Step 1: Get page info
    print(f"\n[1/5] Loading page structure...")
    space_id, page_content, blocks = get_page_info(headers, STATS_PAGE_ID)
    print(f"  Space ID: {space_id}")
    print(f"  Child blocks: {len(page_content)}")

    # Step 2: Find placeholders
    print("\n[2/5] Finding placeholder blocks...")
    placeholders = find_placeholder_blocks(blocks, page_content)
    for key, info in placeholders.items():
        print(f"  {key}: placeholder={info['placeholder_id'][:8]}... heading={info['heading_id'][:8]}...")

    missing = [k for k in COLLECTIONS if k not in placeholders]
    if missing:
        print(f"\n  WARNING: Missing placeholders for: {missing}")
        print("  These databases may have already been set up.")

    # Step 3: Load schemas
    print("\n[3/5] Loading collection schemas...")
    schemas = {}
    for name, coll_id in COLLECTIONS.items():
        if name not in placeholders:
            continue
        schemas[name] = get_collection_schema(headers, coll_id)
        print(f"  {name}: {len(schemas[name])} properties found")
        # Show key property IDs for debugging
        for prop_name, prop_id in sorted(schemas[name].items()):
            print(f"    {prop_name} -> {prop_id}")

    # Step 4: Build views
    print("\n[4/5] Building view configurations...")
    view_builders = {
        "activity_log": build_activity_log_views,
        "daily_summary": build_daily_summary_views,
        "habits": build_habits_views,
        "quests": build_quests_views,
    }

    all_operations = []
    created_dbs = {}

    for db_key in COLLECTIONS:
        if db_key not in placeholders:
            continue

        views = view_builders[db_key](schemas[db_key])
        print(f"  {DB_NAMES[db_key]}: {len(views)} views")
        for v in views:
            print(f"    - {v['name']} ({v['type']})")

        ops, db_block_id, view_ids = build_linked_db_operations(
            space_id=space_id,
            parent_block_id=STATS_PAGE_ID,
            placeholder_id=placeholders[db_key]["placeholder_id"],
            heading_id=placeholders[db_key]["heading_id"],
            collection_id=COLLECTIONS[db_key],
            views_config=views,
        )

        all_operations.extend(ops)
        created_dbs[db_key] = {
            "block_id": db_block_id,
            "view_ids": view_ids,
            "view_names": [v["name"] for v in views],
        }

    # Step 5: Execute
    total_ops = len(all_operations)
    total_views = sum(len(v["view_ids"]) for v in created_dbs.values())

    print(f"\n[5/5] Executing transaction...")
    print(f"  {len(created_dbs)} linked databases")
    print(f"  {total_views} views")
    print(f"  {total_ops} total operations")

    if DRY_RUN:
        print("\n  [DRY RUN] Would send the following transaction:")
        print(f"  Space: {space_id}")
        for db_key, info in created_dbs.items():
            print(f"\n  {DB_NAMES[db_key]}:")
            print(f"    Block: {info['block_id']}")
            for vid, vname in zip(info["view_ids"], info["view_names"]):
                print(f"    View '{vname}': {vid}")
        print("\n  [DRY RUN] No changes made. Remove --dry-run to execute.")
        return

    resp = requests.post(f"{NOTION_API}/saveTransactions", headers=headers, json={
        "requestId": new_id(),
        "transactions": [{
            "id": new_id(),
            "spaceId": space_id,
            "operations": all_operations,
        }]
    })

    if resp.status_code == 200:
        print("\n  [SUCCESS] All databases and views created!")
    else:
        print(f"\n  [ERROR] HTTP {resp.status_code}")
        print(f"  Response: {resp.text[:500]}")
        sys.exit(1)

    # Summary
    page_url = f"https://www.notion.so/{STATS_PAGE_ID.replace('-', '')}"
    print(f"\n{'=' * 50}")
    print(f"  DONE! Open your Stats page:")
    print(f"  {page_url}")
    print(f"{'=' * 50}")

    # Print created structure
    print("\nCreated structure:")
    for db_key, info in created_dbs.items():
        print(f"\n  {DB_NAMES[db_key]}:")
        for vname in info["view_names"]:
            print(f"    - {vname}")

    print("\n  Next steps:")
    print("  1. Open the page and verify each view")
    print("  2. If any view needs adjustment, edit directly in Notion UI")
    print("  3. The chart view (XP Trend) may need manual fine-tuning in the UI")
    print(f"  4. Add a link to this page in your Command Center")


if __name__ == "__main__":
    main()
