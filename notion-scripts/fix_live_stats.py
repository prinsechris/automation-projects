#!/usr/bin/env python3
"""
Fix: Command Center — Live Stats workflow
Problem: After gamification redesign, callout blocks are nested inside columns.
The old code searched top-level blocks for "CETTE SEMAINE" text and found null.

Fix: Use hardcoded block IDs for the text blocks inside callouts,
and PATCH them as paragraph blocks (not callouts).

Reduces from 19 nodes to 11.
"""

import json
import requests
import time

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9.sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

WORKFLOW_ID = "XCoyGKYl0y8r3Geg"

# Known block IDs (verified 2026-02-24)
CETTE_SEMAINE_TEXT_BLOCK = "88b71720-6678-4d99-ae1c-eacad65f01b4"
CE_MOIS_TEXT_BLOCK = "444af0ec-800f-4f3f-b582-51b8b6a634e5"
ALL_TIME_TEXT_BLOCK = "51a77758-829e-4151-999f-af7467163e89"
PLAYER_STATS_TEXT_BLOCK = "46f38215-9555-4aac-8416-d2063a6edc95"

# Notion page/DB IDs
PLAYER_STATS_PAGE = "310da200-b2d6-8005-aeb9-e410436b48cf"
WEEKLY_SUMMARY_DB = "8559b19c-86a5-4034-bc4d-ea45459ef6bd"
ACTIVITIES_DB = "305da200-b2d6-819f-915f-d35f51386aa8"


def build_workflow():
    """Build the fixed workflow."""

    # -- Node: Schedule Trigger --
    trigger = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000001",
        "name": "Every 2 Hours",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [260, 300],
        "parameters": {
            "rule": {
                "interval": [{"field": "hours", "hoursInterval": 2}]
            }
        }
    }

    # -- Node: Get Player Stats --
    get_player = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000002",
        "name": "Get Player Stats",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 300],
        "parameters": {
            "method": "GET",
            "url": f"https://api.notion.com/v1/pages/{PLAYER_STATS_PAGE}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "options": {}
        },
        "credentials": {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
    }

    # -- Wait 1s --
    wait1 = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000003",
        "name": "Wait 1s",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [700, 300],
        "parameters": {"amount": 1, "unit": "seconds"},
        "webhookId": "wait-1"
    }

    # -- Node: Get Weekly Summary --
    get_weekly = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000004",
        "name": "Get Weekly Summary",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [920, 300],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{WEEKLY_SUMMARY_DB}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({"page_size": 100}),
            "options": {}
        },
        "credentials": {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
    }

    # -- Wait 1s (2) --
    wait2 = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000005",
        "name": "Wait 1s (2)",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [1140, 300],
        "parameters": {"amount": 1, "unit": "seconds"},
        "webhookId": "wait-2"
    }

    # -- Node: Get Weekly Activities --
    get_activities = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000006",
        "name": "Get Weekly Activities",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1360, 300],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{ACTIVITIES_DB}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({"page_size": 100}),
            "options": {}
        },
        "credentials": {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
    }

    # -- Node: Build All Updates --
    # This replaces Format Stats + Identify & Update Blocks + Find Stats Column + Build Player Stats Update
    build_updates_code = f"""
// Gather data
const playerPage = $('Get Player Stats').first().json;
const props = playerPage.properties || {{}};
const weeklyItems = $('Get Weekly Summary').first().json;
const activitiesData = $('Get Weekly Activities').first().json;
const activities = activitiesData.results || [];

function getFormulaValue(prop) {{
    if (!prop) return '--';
    if (prop.type === 'formula') {{
        const f = prop.formula;
        if (f.type === 'number') return f.number != null ? f.number : '--';
        if (f.type === 'string') return f.string || '--';
    }}
    if (prop.type === 'number') return prop.number != null ? prop.number : '--';
    return '--';
}}

const level = getFormulaValue(props['Level'] || props['level']);
const gold = getFormulaValue(props['Gold'] || props['gold']);
const health = getFormulaValue(props['Health'] || props['health']);
const habits = getFormulaValue(props['Habits'] || props['habits']);
const xpTotal = getFormulaValue(props['XP'] || props['xp']);
const xpNext = getFormulaValue(props['XP to Next Level'] || props['xp_to_next_level']);

const dayCount = (weeklyItems.results || []).length;

// Sum XP/Gold from activities this week
let weekXP = 0;
let weekGold = 0;
let habitsCompleted = 0;
const now = new Date();
const startOfWeek = new Date(now);
startOfWeek.setDate(now.getDate() - now.getDay() + 1); // Monday
startOfWeek.setHours(0, 0, 0, 0);

for (const activity of activities) {{
    const p = activity.properties || {{}};
    const xp = getFormulaValue(p['XP'] || p['xp']);
    const goldVal = getFormulaValue(p['Gold'] || p['gold']);
    if (typeof xp === 'number') weekXP += xp;
    if (typeof goldVal === 'number') weekGold += goldVal;
    const habitsRel = p['Habits'] || p['habits'];
    if (habitsRel && habitsRel.type === 'relation') {{
        if ((habitsRel.relation || []).length > 0) habitsCompleted++;
    }}
}}

// Build progress bars
function progressBar(current, max) {{
    const pct = Math.min(current / max, 1);
    const filled = Math.round(pct * 10);
    return '\\u2588'.repeat(filled) + '\\u2591'.repeat(10 - filled);
}}

const xpBar = progressBar(weekXP, 500);
const habitsTarget = 35;
const habitsBar = progressBar(habitsCompleted, habitsTarget);

// Build CETTE SEMAINE text
const cetteSemaineText = `\\ud83d\\udd25 CETTE SEMAINE\\n\\u2b50 XP: ${{weekXP}}/500 ${{xpBar}}\\n\\ud83d\\udcb0 Gold: ${{weekGold}} | \\u2764\\ufe0f Streak: ${{dayCount}}j\\n\\ud83d\\udcd3 Habits: ${{habitsCompleted}}/${{habitsTarget}} ${{habitsBar}}\\n\\ud83d\\udcc5 ${{activities.length}} activities | \\ud83d\\udd52 Auto`;

// Build PLAYER STATS text
const xpNum = typeof xpTotal === 'number' ? xpTotal : 0;
const xpNextNum = typeof xpNext === 'number' ? xpNext : 200;
const pctLevel = xpNextNum > 0 ? Math.round((xpNum / xpNextNum) * 100) : 0;
const lvlBar = progressBar(xpNum, xpNextNum);
const playerStatsText = `PLAYER STATS \\u2192 Stats & Analytics\\n\\u2b50 Level: ${{level}}\\n${{pctLevel}}% ${{lvlBar}} ${{xpNum}}/${{xpNextNum}} | \\ud83d\\udcb0 Gold: ${{gold}}\\n\\u2764\\ufe0f Health: ${{health}} HP | \\ud83d\\udcd3 Habits: ${{habitsCompleted}}/${{habits || 5}}`;

// Build paragraph PATCH bodies
const cetteSemaineBody = JSON.stringify({{
    paragraph: {{
        rich_text: [
            {{type: "text", text: {{content: cetteSemaineText}}}}
        ]
    }}
}});

const playerStatsBody = JSON.stringify({{
    paragraph: {{
        rich_text: [
            {{type: "text", text: {{content: playerStatsText}}}}
        ]
    }}
}});

return [{{
    json: {{
        cetteSemaineBlockId: '{CETTE_SEMAINE_TEXT_BLOCK}',
        playerStatsBlockId: '{PLAYER_STATS_TEXT_BLOCK}',
        cetteSemaineBody,
        playerStatsBody
    }}
}}];
"""

    build_updates = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000007",
        "name": "Build All Updates",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1580, 300],
        "parameters": {"jsCode": build_updates_code}
    }

    # -- Wait 1s (3) --
    wait3 = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000008",
        "name": "Wait 1s (3)",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [1800, 300],
        "parameters": {"amount": 1, "unit": "seconds"},
        "webhookId": "wait-3"
    }

    # -- Node: Update Cette Semaine --
    update_semaine = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000009",
        "name": "Update Cette Semaine",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2020, 300],
        "parameters": {
            "method": "PATCH",
            "url": f"=https://api.notion.com/v1/blocks/{{{{ $json.cetteSemaineBlockId }}}}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.cetteSemaineBody }}",
            "options": {
                "retryOnFail": True,
                "maxTries": 3,
                "waitBetweenTries": 3000
            }
        },
        "credentials": {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}},
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 3000
    }

    # -- Wait 1s (4) --
    wait4 = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000010",
        "name": "Wait 1s (4)",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [2240, 300],
        "parameters": {"amount": 1, "unit": "seconds"},
        "webhookId": "wait-4"
    }

    # -- Node: Update Player Stats --
    update_player = {
        "id": "a1b2c3d4-5678-9abc-def0-000000000011",
        "name": "Update Player Stats",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2460, 300],
        "parameters": {
            "method": "PATCH",
            "url": f"=https://api.notion.com/v1/blocks/{{{{ $('Build All Updates').item.json.playerStatsBlockId }}}}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $('Build All Updates').item.json.playerStatsBody }}",
            "options": {
                "retryOnFail": True,
                "maxTries": 3,
                "waitBetweenTries": 3000
            }
        },
        "credentials": {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}},
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 3000
    }

    nodes = [trigger, get_player, wait1, get_weekly, wait2, get_activities,
             build_updates, wait3, update_semaine, wait4, update_player]

    connections = {
        "Every 2 Hours": {"main": [[{"node": "Get Player Stats", "type": "main", "index": 0}]]},
        "Get Player Stats": {"main": [[{"node": "Wait 1s", "type": "main", "index": 0}]]},
        "Wait 1s": {"main": [[{"node": "Get Weekly Summary", "type": "main", "index": 0}]]},
        "Get Weekly Summary": {"main": [[{"node": "Wait 1s (2)", "type": "main", "index": 0}]]},
        "Wait 1s (2)": {"main": [[{"node": "Get Weekly Activities", "type": "main", "index": 0}]]},
        "Get Weekly Activities": {"main": [[{"node": "Build All Updates", "type": "main", "index": 0}]]},
        "Build All Updates": {"main": [[{"node": "Wait 1s (3)", "type": "main", "index": 0}]]},
        "Wait 1s (3)": {"main": [[{"node": "Update Cette Semaine", "type": "main", "index": 0}]]},
        "Update Cette Semaine": {"main": [[{"node": "Wait 1s (4)", "type": "main", "index": 0}]]},
        "Wait 1s (4)": {"main": [[{"node": "Update Player Stats", "type": "main", "index": 0}]]}
    }

    return {
        "name": "Command Center — Live Stats",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "saveExecutionProgress": True,
            "callerPolicy": "workflowsFromSameOwner"
        }
    }


def main():
    workflow = build_workflow()

    # First deactivate
    print("1. Deactivating workflow...")
    r = requests.patch(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=HEADERS,
        json={"active": False}
    )
    print(f"   Status: {r.status_code}")
    time.sleep(2)

    # Update workflow
    print("2. Updating workflow nodes...")
    r = requests.put(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=HEADERS,
        json=workflow
    )
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        print(f"   Error: {r.text[:500]}")
        return False

    time.sleep(2)

    # Reactivate
    print("3. Reactivating workflow...")
    r = requests.patch(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=HEADERS,
        json={"active": True}
    )
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        print(f"   Error: {r.text[:500]}")
        return False

    time.sleep(2)

    # Test execute
    print("4. Test execution...")
    r = requests.post(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}/execute",
        headers=HEADERS,
        json={}
    )
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json().get('data', {})
        status = data.get('status', 'unknown')
        print(f"   Execution status: {status}")
        if status == 'error':
            err = data.get('resultData', {}).get('error', {})
            print(f"   Error: {err.get('message', 'N/A')}")
            node = err.get('node', {})
            if isinstance(node, dict):
                print(f"   Node: {node.get('name', 'N/A')}")
            # Check node-level errors
            run_data = data.get('resultData', {}).get('runData', {})
            for node_name, runs in run_data.items():
                for run in runs:
                    if run.get('error'):
                        e = run['error']
                        print(f"   Node '{node_name}': {e.get('message', 'N/A')}")
        elif status == 'success':
            print("   SUCCESS! Workflow is fixed.")
    else:
        print(f"   Error: {r.text[:300]}")

    return True


if __name__ == "__main__":
    main()
