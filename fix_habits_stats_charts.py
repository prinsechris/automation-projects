#!/usr/bin/env python3
"""
Fix Habits Stats charts in Command Center:
1. Add chart views to the new Habits Stats DB
2. Replace the old linked DB in Command Center with the new one
3. Add scroll icon to Activity Log template
"""

import requests
import uuid
import json
import sys
from pathlib import Path

NOTION_API = "https://www.notion.so/api/v3"
SPACE_ID = "eba9b7f4-a4f9-4b63-a58c-b40e79eb44c7"

# New Habits Stats DB (created via MCP - properly indexed)
NEW_COLLECTION = "5e950661-3a7f-4874-8f5a-c9d8f5a4f8dc"
NEW_DB_PAGE = "9f7d5ff0-ff5e-4c47-be47-faa6f7447bc0"

# Property IDs in new collection
PROP_PERIOD = "Cfpe"         # select
PROP_PERIOD_START = "]tL["   # date
PROP_COMPLETED = "`x^h"      # number
PROP_STREAK = "gkDS"         # number
PROP_TARGET = "KA`O"         # number
PROP_HABIT = "SvaR"          # relation
PROP_SUCCESS = "RjQH"        # formula

# Command Center
CC_PAGE = "306da200-b2d6-819c-8863-cf78f61ae670"
OLD_CC_BLOCK = "d650bd4d-0e3b-416b-913f-a26af709c1fc"  # Old linked DB

# Activity Log template
AL_TEMPLATE = "c8fe7a5d-80b6-439c-b3a3-e8fa98f1e203"

DRY_RUN = "--dry-run" in sys.argv


def load_token():
    return (Path.home() / ".notion-token").read_text().strip()


def get_headers(token):
    return {"Content-Type": "application/json", "Cookie": f"token_v2={token}"}


def api_post(headers, endpoint, payload):
    return requests.post(f"{NOTION_API}/{endpoint}", headers=headers, json=payload)


def new_id():
    return str(uuid.uuid4())


def main():
    print("=" * 55)
    print("  Fix Habits Stats Charts + Activity Log Icon")
    print("=" * 55)
    if DRY_RUN:
        print("\n  [DRY RUN]\n")

    token = load_token()
    headers = get_headers(token)

    all_ops = []

    # === PART 1: Create chart views in new Habits Stats DB ===
    print("\n[1/4] Creating chart views for new Habits Stats...")

    views = [
        {
            "name": "Suivi Habits",
            "type": "table",
            "query2": {"sort": [{"property": PROP_PERIOD_START, "direction": "descending"}]},
            "format": {
                "table_properties": [
                    {"property": "title", "visible": True, "width": 250},
                    {"property": PROP_PERIOD, "visible": True, "width": 100},
                    {"property": PROP_PERIOD_START, "visible": True, "width": 150},
                    {"property": PROP_COMPLETED, "visible": True, "width": 100},
                    {"property": PROP_TARGET, "visible": True, "width": 100},
                    {"property": PROP_STREAK, "visible": True, "width": 100},
                    {"property": PROP_SUCCESS, "visible": True, "width": 120},
                ]
            }
        },
        {
            "name": "Par Jour",
            "type": "chart",
            "query2": {
                "filter": {
                    "operator": "and",
                    "filters": [{
                        "property": PROP_PERIOD,
                        "filter": {"operator": "enum_is", "value": {"type": "exact", "value": "Day"}}
                    }]
                },
                "sort": [{"property": PROP_PERIOD_START, "direction": "ascending"}]
            },
            "format": {
                "chart_config": {
                    "type": "bar",
                    "dataConfig": {
                        "type": "groups_reducer",
                        "groupBy": {
                            "sort": {"type": "ascending"},
                            "type": "date",
                            "groupBy": "day",
                            "property": PROP_PERIOD_START,
                            "hideEmptyGroups": True
                        },
                        "aggregationConfig": {
                            "aggregation": {"property": PROP_COMPLETED, "aggregator": "sum"},
                            "seriesFormat": {"displayType": "bar"}
                        }
                    },
                    "chartFormat": {
                        "mainSort": "x-ascending",
                        "axisShowDataLabels": True,
                        "axisHideEmptyGroups": True
                    }
                }
            }
        },
        {
            "name": "Par Semaine",
            "type": "chart",
            "query2": {
                "filter": {"operator": "and", "filters": []},
                "sort": [{"property": PROP_PERIOD_START, "direction": "ascending"}]
            },
            "format": {
                "chart_config": {
                    "type": "bar",
                    "dataConfig": {
                        "type": "groups_reducer",
                        "groupBy": {
                            "sort": {"type": "ascending"},
                            "type": "date",
                            "groupBy": "week",
                            "property": PROP_PERIOD_START,
                            "hideEmptyGroups": True
                        },
                        "aggregationConfig": {
                            "aggregation": {"property": PROP_COMPLETED, "aggregator": "sum"},
                            "seriesFormat": {"displayType": "bar"}
                        }
                    },
                    "chartFormat": {
                        "mainSort": "x-ascending",
                        "axisShowDataLabels": True,
                        "axisHideEmptyGroups": True
                    }
                }
            }
        },
        {
            "name": "Par Mois",
            "type": "chart",
            "query2": {
                "sort": [{"property": PROP_PERIOD_START, "direction": "ascending"}]
            },
            "format": {
                "chart_config": {
                    "type": "line",
                    "dataConfig": {
                        "type": "groups_reducer",
                        "groupBy": {
                            "sort": {"type": "ascending"},
                            "type": "date",
                            "groupBy": "month",
                            "property": PROP_PERIOD_START,
                            "hideEmptyGroups": True
                        },
                        "aggregationConfig": {
                            "aggregation": {"property": PROP_COMPLETED, "aggregator": "sum"},
                            "seriesFormat": {"displayType": "line"}
                        }
                    },
                    "chartFormat": {
                        "mainSort": "x-ascending",
                        "smoothLine": True,
                        "axisShowDataLabels": True,
                        "axisHideEmptyGroups": True
                    }
                }
            }
        }
    ]

    view_ids = []
    for vc in views:
        vid = new_id()
        view_ids.append(vid)
        view_record = {
            "id": vid, "version": 1, "type": vc["type"], "name": vc["name"],
            "alive": True, "parent_id": NEW_DB_PAGE, "parent_table": "block",
            "space_id": SPACE_ID,
            "format": {
                "collection_pointer": {
                    "id": NEW_COLLECTION, "table": "collection", "spaceId": SPACE_ID
                }
            }
        }
        if vc.get("query2"):
            view_record["query2"] = vc["query2"]
        if vc.get("format"):
            view_record["format"].update(vc["format"])

        all_ops.append({
            "pointer": {"table": "collection_view", "id": vid},
            "path": [], "command": "set", "args": view_record
        })
        all_ops.append({
            "pointer": {"table": "block", "id": NEW_DB_PAGE},
            "path": ["view_ids"], "command": "listAfter",
            "args": {"id": vid}
        })
        print(f"  + View '{vc['name']}' ({vc['type']})")

    # === PART 2: Replace linked DB in Command Center ===
    print(f"\n[2/4] Replacing Habits Stats in Command Center...")

    # Update the old linked DB block to point to the new collection
    all_ops.append({
        "pointer": {"table": "block", "id": OLD_CC_BLOCK},
        "path": ["collection_id"],
        "command": "set",
        "args": NEW_COLLECTION
    })

    # Replace view_ids on the CC block with new views for CC
    cc_view_ids = []
    cc_views = [
        {"name": "Suivi", "type": "table",
         "query2": {"sort": [{"property": PROP_PERIOD_START, "direction": "descending"}]},
         "format": {"table_properties": [
             {"property": "title", "visible": True, "width": 200},
             {"property": PROP_PERIOD_START, "visible": True, "width": 120},
             {"property": PROP_COMPLETED, "visible": True, "width": 80},
             {"property": PROP_STREAK, "visible": True, "width": 80},
             {"property": PROP_SUCCESS, "visible": True, "width": 100},
         ]}},
        {"name": "Jour", "type": "chart",
         "query2": {"filter": {"operator": "and", "filters": [
             {"property": PROP_PERIOD, "filter": {"operator": "enum_is", "value": {"type": "exact", "value": "Day"}}}
         ]}},
         "format": {"chart_config": {
             "type": "bar",
             "dataConfig": {"type": "groups_reducer",
                 "groupBy": {"sort": {"type": "ascending"}, "type": "date", "groupBy": "day",
                     "property": PROP_PERIOD_START, "hideEmptyGroups": True},
                 "aggregationConfig": {"aggregation": {"property": PROP_COMPLETED, "aggregator": "sum"},
                     "seriesFormat": {"displayType": "bar"}}},
             "chartFormat": {"mainSort": "x-ascending", "axisShowDataLabels": True, "axisHideEmptyGroups": True}
         }}},
        {"name": "Semaine", "type": "chart",
         "format": {"chart_config": {
             "type": "bar",
             "dataConfig": {"type": "groups_reducer",
                 "groupBy": {"sort": {"type": "ascending"}, "type": "date", "groupBy": "week",
                     "property": PROP_PERIOD_START, "hideEmptyGroups": True},
                 "aggregationConfig": {"aggregation": {"property": PROP_COMPLETED, "aggregator": "sum"},
                     "seriesFormat": {"displayType": "bar"}}},
             "chartFormat": {"mainSort": "x-ascending", "axisShowDataLabels": True, "axisHideEmptyGroups": True}
         }}},
        {"name": "Mois", "type": "chart",
         "format": {"chart_config": {
             "type": "line",
             "dataConfig": {"type": "groups_reducer",
                 "groupBy": {"sort": {"type": "ascending"}, "type": "date", "groupBy": "month",
                     "property": PROP_PERIOD_START, "hideEmptyGroups": True},
                 "aggregationConfig": {"aggregation": {"property": PROP_COMPLETED, "aggregator": "sum"},
                     "seriesFormat": {"displayType": "line"}}},
             "chartFormat": {"mainSort": "x-ascending", "smoothLine": True, "axisShowDataLabels": True, "axisHideEmptyGroups": True}
         }}}
    ]

    for vc in cc_views:
        vid = new_id()
        cc_view_ids.append(vid)
        view_record = {
            "id": vid, "version": 1, "type": vc["type"], "name": vc["name"],
            "alive": True, "parent_id": OLD_CC_BLOCK, "parent_table": "block",
            "space_id": SPACE_ID,
            "format": {"collection_pointer": {"id": NEW_COLLECTION, "table": "collection", "spaceId": SPACE_ID}}
        }
        if vc.get("query2"):
            view_record["query2"] = vc["query2"]
        if vc.get("format"):
            view_record["format"].update(vc["format"])
        all_ops.append({
            "pointer": {"table": "collection_view", "id": vid},
            "path": [], "command": "set", "args": view_record
        })

    # Set the view_ids on the CC block
    all_ops.append({
        "pointer": {"table": "block", "id": OLD_CC_BLOCK},
        "path": ["view_ids"],
        "command": "set",
        "args": cc_view_ids
    })
    print(f"  Linked DB block updated -> new collection + {len(cc_views)} views")

    # === PART 3: Add scroll icon to Activity Log template ===
    print(f"\n[3/4] Adding scroll icon to Activity Log template...")
    all_ops.append({
        "pointer": {"table": "block", "id": AL_TEMPLATE},
        "path": ["format", "page_icon"],
        "command": "set",
        "args": "\U0001f4dc"  # scroll emoji
    })
    print(f"  Icon: scroll (parchemin)")

    # === PART 4: Execute ===
    print(f"\n[4/4] Executing {len(all_ops)} operations...")

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
        print(f"\n  What was done:")
        print(f"  1. New Habits Stats DB: {len(views)} views (table + 3 charts)")
        print(f"  2. Command Center: linked DB now uses new collection + {len(cc_views)} views")
        print(f"  3. Activity Log template: scroll icon added")
        print(f"\n  New Habits Stats collection: {NEW_COLLECTION}")
        print(f"  New DB page: {NEW_DB_PAGE}")
        print(f"\n  NEXT: Update n8n Daily Morning CRON to use new DB ID:")
        print(f"    Old: 74199404-89cb-4ea1-ad77-bf7f387fa518")
        print(f"    New: {NEW_DB_PAGE}")
    else:
        print(f"\n  FAILED: {resp.status_code}")
        print(f"  {resp.text[:500]}")


if __name__ == "__main__":
    main()
