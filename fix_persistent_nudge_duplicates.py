#!/usr/bin/env python3
"""Fix Persistent Nudge duplicate messages.

Problem: Build Nudge Message runs in 'runOnceForEachItem' mode but receives
items from 4 parallel branches. This causes the same message to be built
and sent multiple times (once per incoming item).

Fix: Change mode to 'runOnceForAllItems'.
"""

import json
import requests
import os

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

NUDGE_WF_ID = "3duVDOa80aKp3YA6"


def fix_workflow():
    resp = requests.get(
        f"{N8N_URL}/api/v1/workflows/{NUDGE_WF_ID}",
        headers=HEADERS,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch: {resp.status_code}")
        return

    data = resp.json()

    # Fix Build Nudge Message mode
    for node in data["nodes"]:
        if node["name"] == "Build Nudge Message":
            old_mode = node["parameters"].get("mode", "runOnceForEachItem")
            node["parameters"]["mode"] = "runOnceForAllItems"
            print(f"[OK] Build Nudge Message: mode '{old_mode}' -> 'runOnceForAllItems'")
            break

    # Remove read-only fields
    for key in ["updatedAt", "createdAt", "isArchived", "id", "staticData",
                 "meta", "pinData", "versionId", "activeVersionId",
                 "versionCounter", "triggerCount", "shared", "tags",
                 "activeVersion", "description", "active"]:
        data.pop(key, None)

    resp = requests.put(
        f"{N8N_URL}/api/v1/workflows/{NUDGE_WF_ID}",
        headers=HEADERS,
        json=data,
        timeout=30,
    )
    if resp.status_code == 200:
        print(f"[OK] Persistent Nudge updated - duplicates fixed")
    else:
        print(f"[ERROR] Update failed: {resp.status_code}")
        print(resp.text[:500])


if __name__ == "__main__":
    fix_workflow()
