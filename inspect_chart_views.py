#!/usr/bin/env python3
"""Inspect existing chart views to understand series/split format."""
import requests, json
from pathlib import Path

NOTION_API = "https://www.notion.so/api/v3"
token = (Path.home() / ".notion-token").read_text().strip()
headers = {"Content-Type": "application/json", "Cookie": f"token_v2={token}"}

def api_post(endpoint, payload):
    return requests.post(f"{NOTION_API}/{endpoint}", headers=headers, json=payload)

# Fetch all views from Activity Log DB page (has chart views)
# Activity Log DB block in CC: 310da200-b2d6-80d1-8c2b-ce052652371a
# Also check the Activity Log DB itself: 305da200-b2d6-8116-8039-000b9a9d9070

# First get the Activity Log collection's views
resp = api_post("getRecordValues", {
    "requests": [
        # The Activity Log DB page (original)
        {"table": "block", "id": "1b9da200-b2d6-816d-80a2-000b7ae44c7e"},
        # New Habits Stats DB page
        {"table": "block", "id": "9f7d5ff0-ff5e-4c47-be47-faa6f7447bc0"},
    ]
})

if resp.status_code == 200:
    results = resp.json()["results"]
    for r in results:
        v = r.get("value", {})
        bid = v.get("id", "?")[:12]
        vids = v.get("view_ids", [])
        print(f"Block {bid}: {len(vids)} views")
        
        # Fetch each view to see chart configs
        if vids:
            vresp = api_post("getRecordValues", {
                "requests": [{"table": "collection_view", "id": vid} for vid in vids[:8]]
            })
            if vresp.status_code == 200:
                for vr in vresp.json()["results"]:
                    vv = vr.get("value", {})
                    vtype = vv.get("type", "?")
                    vname = vv.get("name", "?")
                    if vtype == "chart":
                        fmt = vv.get("format", {})
                        cc = fmt.get("chart_config", {})
                        print(f"\n  CHART: '{vname}'")
                        print(f"  Config: {json.dumps(cc, indent=2)}")
                    else:
                        print(f"  {vtype}: '{vname}'")
else:
    print(f"Error: {resp.status_code}")

# Also check the Habits Stats original DB for its views
print("\n\n=== CHECKING OLD HABITS STATS VIEWS ===")
resp2 = api_post("getRecordValues", {
    "requests": [{"table": "block", "id": "74199404-89cb-4ea1-ad77-bf7f387fa518"}]
})
if resp2.status_code == 200:
    v = resp2.json()["results"][0].get("value", {})
    vids = v.get("view_ids", [])
    print(f"Old Habits Stats: {len(vids)} views")
    if vids:
        vresp = api_post("getRecordValues", {
            "requests": [{"table": "collection_view", "id": vid} for vid in vids]
        })
        if vresp.status_code == 200:
            for vr in vresp.json()["results"]:
                vv = vr.get("value", {})
                vtype = vv.get("type", "?")
                vname = vv.get("name", "?")
                if vtype == "chart":
                    fmt = vv.get("format", {})
                    cc = fmt.get("chart_config", {})
                    dc = cc.get("dataConfig", {})
                    print(f"\n  CHART: '{vname}' type={cc.get('type')}")
                    print(f"  dataConfig keys: {list(dc.keys())}")
                    print(f"  Full dataConfig: {json.dumps(dc, indent=2)}")
                else:
                    print(f"  {vtype}: '{vname}'")

# Check Activity Log views (the ones with Breakdown chart)
print("\n\n=== CHECKING ACTIVITY LOG VIEWS (original DB) ===")
resp3 = api_post("getRecordValues", {
    "requests": [{"table": "block", "id": "305da200-b2d6-8116-8039-000b9a9d9070"}]
})
if resp3.status_code == 200:
    # This is a collection, not a block - need the DB page
    pass

# Try the actual Activity Log DB page
print("\n=== Activity Log DB page views ===")
resp4 = api_post("loadPageChunk", {
    "pageId": "305da200-b2d6-8116-8039-000b9a9d9070",
    "limit": 50, "cursor": {"stack": []}, "chunkNumber": 0, "verticalColumns": False,
})
if resp4.status_code == 200:
    rm = resp4.json().get("recordMap", {})
    views = rm.get("collection_view", {})
    for vid, vdata in views.items():
        vv = vdata.get("value", {})
        vtype = vv.get("type", "?")
        vname = vv.get("name", "?")
        if vtype == "chart":
            fmt = vv.get("format", {})
            cc = fmt.get("chart_config", {})
            print(f"\n  CHART: '{vname}' type={cc.get('type')}")
            print(f"  Full config: {json.dumps(cc, indent=2)}")
        else:
            print(f"  {vtype}: '{vname}'")
else:
    print(f"  loadPageChunk error: {resp4.status_code}")
