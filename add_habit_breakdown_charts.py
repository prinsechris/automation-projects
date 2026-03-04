#!/usr/bin/env python3
"""
Add per-habit breakdown to Habits Stats charts.

Updates existing chart views to add stackOptions (color by Habit),
and adds a new "Par Habitude" summary chart.
"""
import requests, uuid, json, sys
from pathlib import Path

NOTION_API = "https://www.notion.so/api/v3"
SPACE_ID = "eba9b7f4-a4f9-4b63-a58c-b40e79eb44c7"

# New Habits Stats DB
NEW_DB_PAGE = "9f7d5ff0-ff5e-4c47-be47-faa6f7447bc0"
NEW_COLLECTION = "5e950661-3a7f-4874-8f5a-c9d8f5a4f8dc"
CC_BLOCK = "d650bd4d-0e3b-416b-913f-a26af709c1fc"

# Property IDs
PROP_PERIOD_START = "]tL["
PROP_COMPLETED = "`x^h"
PROP_HABIT = "SvaR"        # relation to Habits
PROP_PERIOD = "Cfpe"       # select: Day/Week/Month

DRY_RUN = "--dry-run" in sys.argv

def load_token():
    return (Path.home() / ".notion-token").read_text().strip()

def get_headers(token):
    return {"Content-Type": "application/json", "Cookie": f"token_v2={token}"}

def api_post(headers, endpoint, payload):
    return requests.post(f"{NOTION_API}/{endpoint}", headers=headers, json=payload)

def new_id():
    return str(uuid.uuid4())

# stackOptions config to color by Habit relation
HABIT_STACK = {
    "groupBy": {
        "type": "relation",
        "groupBy": {
            "sort": {"type": "ascending"},
            "type": "text",
            "groupBy": "exact",
            "property": PROP_HABIT,
            "hideEmptyGroups": True
        },
        "property": PROP_HABIT,
        "hideEmptyGroups": True
    }
}


def main():
    print("=" * 55)
    print("  Add Per-Habit Breakdown to Habits Stats Charts")
    print("=" * 55)
    if DRY_RUN:
        print("\n  [DRY RUN]\n")

    token = load_token()
    headers = get_headers(token)
    all_ops = []

    # Step 1: Get all chart view IDs from both DB page and CC block
    print("\n[1/3] Fetching existing chart views...")
    resp = api_post(headers, "getRecordValues", {
        "requests": [
            {"table": "block", "id": NEW_DB_PAGE},
            {"table": "block", "id": CC_BLOCK},
        ]
    })
    if resp.status_code != 200:
        print(f"  FAILED: {resp.status_code}")
        return

    results = resp.json()["results"]
    db_view_ids = results[0].get("value", {}).get("view_ids", [])
    cc_view_ids = results[1].get("value", {}).get("view_ids", [])
    all_view_ids = db_view_ids + cc_view_ids
    print(f"  DB page views: {len(db_view_ids)}, CC block views: {len(cc_view_ids)}")

    # Fetch all views
    resp2 = api_post(headers, "getRecordValues", {
        "requests": [{"table": "collection_view", "id": vid} for vid in all_view_ids]
    })
    if resp2.status_code != 200:
        print(f"  FAILED to fetch views: {resp2.status_code}")
        return

    chart_views = []
    for vr in resp2.json()["results"]:
        vv = vr.get("value", {})
        if vv.get("type") == "chart":
            chart_views.append(vv)

    print(f"  Found {len(chart_views)} chart views to update")

    # Step 2: Update each chart view to add stackOptions
    print("\n[2/3] Adding stackOptions (color by Habit) to charts...")
    for cv in chart_views:
        vid = cv["id"]
        name = cv.get("name", "?")
        fmt = cv.get("format", {})
        cc = fmt.get("chart_config", {})
        dc = cc.get("dataConfig", {})

        if not dc:
            print(f"  SKIP '{name}' (empty dataConfig)")
            continue

        # Check if already has stackOptions
        agg = dc.get("aggregationConfig", {})
        if agg.get("stackOptions"):
            print(f"  SKIP '{name}' (already has stackOptions)")
            continue

        # Build updated chart_config with stackOptions
        new_agg = dict(agg)
        new_agg["stackOptions"] = HABIT_STACK

        new_dc = dict(dc)
        new_dc["aggregationConfig"] = new_agg

        new_cc = dict(cc)
        new_cc["dataConfig"] = new_dc

        # For bar charts, make them stacked
        cf = dict(cc.get("chartFormat", {}))
        if cc.get("type") == "bar":
            cf["barStyle"] = "stacked"
        new_cc["chartFormat"] = cf

        all_ops.append({
            "pointer": {"table": "collection_view", "id": vid},
            "path": ["format", "chart_config"],
            "command": "set",
            "args": new_cc
        })
        print(f"  + '{name}' → stacked by Habit")

    # Step 3: Add a new "Par Habitude" chart (X=Habit, Y=sum Completed)
    print("\n[3/3] Adding 'Par Habitude' summary charts...")

    # Add to both DB page and CC block
    targets = [
        ("DB", NEW_DB_PAGE),
        ("CC", CC_BLOCK),
    ]

    for label, parent_id in targets:
        vid = new_id()
        view_record = {
            "id": vid, "version": 1, "type": "chart",
            "name": "Par Habitude",
            "alive": True, "parent_id": parent_id, "parent_table": "block",
            "space_id": SPACE_ID,
            "format": {
                "collection_pointer": {
                    "id": NEW_COLLECTION, "table": "collection", "spaceId": SPACE_ID
                },
                "chart_config": {
                    "type": "bar",
                    "dataConfig": {
                        "type": "groups_reducer",
                        "groupBy": {
                            "sort": {"type": "ascending"},
                            "type": "relation",
                            "groupBy": "exact",
                            "property": PROP_HABIT,
                            "hideEmptyGroups": True
                        },
                        "aggregationConfig": {
                            "aggregation": {"property": PROP_COMPLETED, "aggregator": "sum"},
                            "seriesFormat": {"displayType": "bar"}
                        }
                    },
                    "chartFormat": {
                        "mainSort": "value-descending",
                        "axisShowDataLabels": True,
                        "axisHideEmptyGroups": True
                    }
                }
            }
        }

        all_ops.append({
            "pointer": {"table": "collection_view", "id": vid},
            "path": [], "command": "set", "args": view_record
        })
        all_ops.append({
            "pointer": {"table": "block", "id": parent_id},
            "path": ["view_ids"], "command": "listAfter",
            "args": {"id": vid}
        })
        print(f"  + 'Par Habitude' on {label} (X=Habit, Y=total completed)")

    # Execute
    print(f"\n  Total operations: {len(all_ops)}")

    if DRY_RUN:
        for i, op in enumerate(all_ops):
            t = op['pointer']['table']
            oid = op['pointer']['id'][:12]
            p = op.get('path', [])
            print(f"  {i+1}. {op['command']} on {t}:{oid}... path={p}")
        print("\n  Run without --dry-run to apply.")
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
        print("\n  Ce qui change :")
        print("  - Charts Jour/Semaine/Mois : barres empilees colorees par habitude")
        print("  - Nouveau chart 'Par Habitude' : total completions par habitude")
        print("\n  Tu verras chaque habitude en couleur differente.")
        print("  Les habitudes que tu ne completes pas n'apparaitront pas (ou a 0).")
    else:
        print(f"\n  FAILED: {resp.status_code}")
        print(f"  {resp.text[:500]}")


if __name__ == "__main__":
    main()
