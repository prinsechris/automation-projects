#!/usr/bin/env python3
"""Inspect chart views - focus on new Habits Stats + find any chart with series."""
import requests, json
from pathlib import Path

NOTION_API = "https://www.notion.so/api/v3"
token = (Path.home() / ".notion-token").read_text().strip()
headers = {"Content-Type": "application/json", "Cookie": f"token_v2={token}"}

def api_post(endpoint, payload):
    r = requests.post(f"{NOTION_API}/{endpoint}", headers=headers, json=payload)
    return r

# 1. Check new Habits Stats DB views
print("=== NEW HABITS STATS DB VIEWS ===")
resp = api_post("getRecordValues", {
    "requests": [{"table": "block", "id": "9f7d5ff0-ff5e-4c47-be47-faa6f7447bc0"}]
})
if resp.status_code == 200:
    v = resp.json()["results"][0].get("value", {})
    vids = v.get("view_ids", [])
    print(f"Views: {len(vids)}")
    if vids:
        vresp = api_post("getRecordValues", {
            "requests": [{"table": "collection_view", "id": vid} for vid in vids]
        })
        if vresp.status_code == 200:
            for vr in vresp.json()["results"]:
                vv = vr.get("value", {})
                vtype = vv.get("type", "?")
                vname = vv.get("name", "?")
                fmt = vv.get("format", {})
                cc = fmt.get("chart_config", {})
                if vtype == "chart":
                    print(f"\n  CHART: '{vname}' type={cc.get('type')}")
                    print(f"  Full config: {json.dumps(cc, indent=2)}")
                else:
                    print(f"  {vtype}: '{vname}'")

# 2. Check CC linked DB views for Habits Stats
print("\n\n=== CC HABITS STATS LINKED DB VIEWS ===")
resp2 = api_post("getRecordValues", {
    "requests": [{"table": "block", "id": "d650bd4d-0e3b-416b-913f-a26af709c1fc"}]
})
if resp2.status_code == 200:
    v = resp2.json()["results"][0].get("value", {})
    vids = v.get("view_ids", [])
    print(f"Views: {len(vids)}")
    if vids:
        vresp = api_post("getRecordValues", {
            "requests": [{"table": "collection_view", "id": vid} for vid in vids]
        })
        if vresp.status_code == 200:
            for vr in vresp.json()["results"]:
                vv = vr.get("value", {})
                vtype = vv.get("type", "?")
                vname = vv.get("name", "?")
                fmt = vv.get("format", {})
                cc = fmt.get("chart_config", {})
                if vtype == "chart":
                    print(f"\n  CHART: '{vname}' type={cc.get('type')}")
                    print(f"  Full config: {json.dumps(cc, indent=2)}")
                else:
                    print(f"  {vtype}: '{vname}'")

# 3. Load Command Center to find ALL chart views in workspace
print("\n\n=== ALL CHART VIEWS ON COMMAND CENTER ===")
resp3 = api_post("loadPageChunk", {
    "pageId": "306da200-b2d6-819c-8863-cf78f61ae670",
    "limit": 200, "cursor": {"stack": []}, "chunkNumber": 0, "verticalColumns": False,
})
if resp3.status_code == 200:
    rm = resp3.json().get("recordMap", {})
    views = rm.get("collection_view", {})
    for vid, vdata in views.items():
        vv = vdata.get("value", {})
        vtype = vv.get("type", "?")
        vname = vv.get("name", "?")
        if vtype == "chart":
            fmt = vv.get("format", {})
            cc = fmt.get("chart_config", {})
            dc = cc.get("dataConfig", {})
            print(f"\n  CHART: '{vname}' type={cc.get('type')}")
            # Check for any series/split config
            keys = list(dc.keys()) if dc else []
            print(f"  dataConfig keys: {keys}")
            if dc:
                print(f"  Full dataConfig: {json.dumps(dc, indent=2)}")
else:
    print(f"  Error: {resp3.status_code}")
