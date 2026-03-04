#!/usr/bin/env python3
"""
Fix the Hand In button on the Habits Tracker database.

Problem: The button's create_page action has no template_page_id, AND the
existing templates in the Activity Log are dead (alive=False). This means
clicking Hand In creates empty Activity Log entries.

Fix:
1. Create a NEW template page in the Activity Log collection
2. Set template_page_id on the create_page action
"""

import json
import requests
import uuid
import sys
from pathlib import Path

NOTION_API = "https://www.notion.so/api/v3"

# IDs
ACTIVITY_LOG_COLLECTION = "305da200-b2d6-8116-8039-000b9a9d9070"
SPACE_ID = "eba9b7f4-a4f9-4b63-a58c-b40e79eb44c7"
CHRIS_LEADERBOARD = "310da200-b2d6-8005-aeb9-e410436b48cf"

# Automation action to fix
CREATE_PAGE_ACTION_ID = "305da200-b2d6-81ed-a179-005a1bea39cb"

DRY_RUN = "--dry-run" in sys.argv


def load_token():
    return (Path.home() / ".notion-token").read_text().strip()


def get_headers(token):
    return {"Content-Type": "application/json", "Cookie": f"token_v2={token}"}


def api_post(headers, endpoint, payload):
    resp = requests.post(f"{NOTION_API}/{endpoint}", headers=headers, json=payload)
    return resp


def new_id():
    return str(uuid.uuid4())


def main():
    print("=" * 55)
    print("  Fix Hand In Button — Create Template + Reconnect")
    print("=" * 55)

    if DRY_RUN:
        print("\n  [DRY RUN MODE]\n")

    token = load_token()
    headers = get_headers(token)

    # Step 1: Verify current state
    print("\n[1/4] Reading current action config...")
    resp = api_post(headers, "getRecordValues", {
        "requests": [
            {"table": "automation_action", "id": CREATE_PAGE_ACTION_ID}
        ]
    })
    if resp.status_code != 200:
        print(f"  FAILED to read: {resp.status_code}")
        return

    action = resp.json()["results"][0]["value"]
    config = action.get("config", {})
    print(f"  Action type: {action.get('type')}")
    print(f"  Current template_page_id: {config.get('template_page_id', 'MISSING')}")
    print(f"  Current properties: {config.get('properties', [])}")

    if config.get("template_page_id"):
        # Check if the template is alive
        resp_tpl = api_post(headers, "getRecordValues", {
            "requests": [{"table": "block", "id": config["template_page_id"]}]
        })
        if resp_tpl.status_code == 200:
            tpl = resp_tpl.json()["results"][0].get("value", {})
            if tpl.get("alive"):
                print(f"  Button already has a LIVE template. Nothing to fix!")
                return
            else:
                print(f"  Template exists but is DEAD. Will replace.")

    # Step 2: Create new template
    print("\n[2/4] Creating new template page...")
    template_id = new_id()

    # Template properties (modeled after original working template):
    # - title: [now] - [Chris leaderboard page mention]
    # - Date ({pkI}): now
    # - Leaderboard (eU\R): Chris's entry
    # - F~~A: me (current user)
    template_properties = {
        "title": [
            ["\u2023", [["tv", {"type": "now"}]]],
            [" - "],
            ["\u2023", [["p", CHRIS_LEADERBOARD, SPACE_ID]]]
        ],
        "{pkI": [
            ["\u2023", [["tv", {"type": "now"}]]]
        ],
        "eU\\R": [
            ["\u2023", [["p", CHRIS_LEADERBOARD, SPACE_ID]]]
        ],
        "F~~A": [
            ["\u2023", [["tv", {"type": "me"}]]]
        ]
    }

    create_ops = [
        # Create the template page
        {
            "pointer": {"table": "block", "id": template_id},
            "path": [],
            "command": "set",
            "args": {
                "id": template_id,
                "version": 1,
                "type": "page",
                "alive": True,
                "is_template": True,
                "parent_id": ACTIVITY_LOG_COLLECTION,
                "parent_table": "collection",
                "space_id": SPACE_ID,
                "properties": template_properties,
            }
        },
        # Register in collection's template_pages
        {
            "pointer": {"table": "collection", "id": ACTIVITY_LOG_COLLECTION},
            "path": ["template_pages"],
            "command": "listAfter",
            "args": {"id": template_id}
        }
    ]

    print(f"  New template ID: {template_id}")
    print(f"  Sets: title=[now]-[Chris], Date=now, Leaderboard=Chris, User=me")

    # Step 3: Update the action to use the template
    print("\n[3/4] Building action update...")

    new_config = {
        "values": config.get("values", {}),
        "collection": config.get("collection", {
            "id": ACTIVITY_LOG_COLLECTION,
            "table": "collection",
            "spaceId": SPACE_ID
        }),
        "properties": config.get("properties", ["\\LTx"]),
        "template_page_id": template_id
    }

    import time
    now_ms = int(time.time() * 1000)

    update_ops = [
        {
            "pointer": {"table": "automation_action", "id": CREATE_PAGE_ACTION_ID},
            "path": ["config"],
            "command": "set",
            "args": new_config
        },
        # Must update automation's last_edited_time or API rejects the transaction
        {
            "pointer": {"table": "automation", "id": "305da200-b2d6-8114-80f3-004d3cda2a21"},
            "path": ["last_edited_time"],
            "command": "set",
            "args": now_ms
        }
    ]

    all_ops = create_ops + update_ops
    print(f"  Total operations: {len(all_ops)}")

    # Step 4: Execute
    print(f"\n[4/4] Executing...")

    if DRY_RUN:
        print("\n  [DRY RUN] Would execute:")
        for i, op in enumerate(all_ops):
            table = op['pointer']['table']
            oid = op['pointer']['id'][:12]
            cmd = op['command']
            path = op.get('path', [])
            print(f"    {i+1}. {cmd} on {table}:{oid}... path={path}")
        print(f"\n  Run without --dry-run to apply.")
        return

    resp = api_post(headers, "saveTransactions", {
        "requestId": new_id(),
        "transactions": [{
            "id": new_id(),
            "spaceId": SPACE_ID,
            "operations": all_ops
        }]
    })

    if resp.status_code == 200:
        print("\n  SUCCESS!")
    else:
        print(f"\n  FAILED: {resp.status_code}")
        print(f"  Response: {resp.text[:500]}")
        return

    # Verify
    print("\n[VERIFY] Checking results...")
    resp2 = api_post(headers, "getRecordValues", {
        "requests": [
            {"table": "automation_action", "id": CREATE_PAGE_ACTION_ID},
            {"table": "block", "id": template_id}
        ]
    })

    if resp2.status_code == 200:
        results = resp2.json()["results"]

        # Action check
        updated_action = results[0]["value"]
        cfg = updated_action.get("config", {})
        print(f"\n  Action:")
        print(f"    template_page_id: {cfg.get('template_page_id', 'NOT SET')}")
        print(f"    properties: {cfg.get('properties', [])}")

        # Template check
        tpl = results[1].get("value", {})
        print(f"\n  Template:")
        print(f"    alive: {tpl.get('alive')}")
        print(f"    is_template: {tpl.get('is_template')}")
        tpl_props = tpl.get("properties", {})
        print(f"    has title: {'title' in tpl_props}")
        print(f"    has Date: {'{{pkI' in tpl_props or '{pkI' in tpl_props}")
        print(f"    has Leaderboard: {'eU\\\\R' in tpl_props or 'eU\\R' in tpl_props}")

        if cfg.get("template_page_id") == template_id and tpl.get("alive"):
            print("\n  FIX CONFIRMED!")
            print("\n  When you click Hand In now:")
            print("  1. Confirmation dialog: 'Claim Rewards'")
            print("  2. Creates Activity Log entry with:")
            print("     - Name: [current time] - Chris")
            print("     - Date: now")
            print("     - Leaderboard: Chris")
            print("     - Habits: the habit you clicked on")
            print("  3. Opens the new entry")
            print("\n  n8n Activity Router will then add XP/Gold/HP/Daily Summary")
        else:
            print("\n  WARNING: Verification incomplete")
    else:
        print(f"  Verify failed: {resp2.status_code}")


if __name__ == "__main__":
    main()
