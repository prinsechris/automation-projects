#!/usr/bin/env python3
"""
Command Center Stats Automation
Updates Player Stats and Cette Semaine callouts with live data from Notion.

Workflow:
1. Schedule Trigger (every 2 hours)
2. HTTP Request: Get Leaderboard "Me" page properties (Level, Gold, Health, Habits)
3. HTTP Request: Query Daily Summary for this week
4. Code: Aggregate weekly stats
5. HTTP Request: Find Command Center callout block IDs
6. HTTP Request: Update callout text blocks with live values
"""

import json
import requests
import time
import sys

# ── Config ──────────────────────────────────────────────────────────
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9.sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Credentials
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}

# Notion IDs
LEADERBOARD_ME_PAGE = "305da200-b2d6-8161-8ddf-e4e641c36b45"
DAILY_SUMMARY_DB = "8559b19c-86a5-4034-bc4d-ea45459ef6bd"
COMMAND_CENTER_PAGE = "306da200-b2d6-819c-8863-cf78f61ae670"


def uid():
    """Generate a unique node ID."""
    import uuid
    return str(uuid.uuid4())


def build_workflow():
    """Build the Command Center Stats Automation workflow."""

    trigger_id = uid()
    get_leaderboard_id = uid()
    get_daily_summary_id = uid()
    wait_id = uid()
    aggregate_id = uid()
    find_blocks_id = uid()
    update_stats_id = uid()

    workflow = {
        "name": "Command Center — Live Stats",
        "nodes": [
            # 1. Schedule Trigger — every 2 hours
            {
                "id": trigger_id,
                "name": "Every 2 Hours",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
                "parameters": {
                    "rule": {
                        "interval": [
                            {"field": "hours", "hoursInterval": 2}
                        ]
                    }
                }
            },
            # 2. Get Leaderboard "Me" page properties
            {
                "id": get_leaderboard_id,
                "name": "Get Player Stats",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [220, -100],
                "parameters": {
                    "method": "GET",
                    "url": f"https://api.notion.com/v1/pages/{LEADERBOARD_ME_PAGE}/properties/{{{{ $json.propertyId }}}}",
                    "authentication": "predefinedCredentialType",
                    "nodeCredentialType": "notionApi",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Notion-Version", "value": "2022-06-28"}
                        ]
                    },
                    "options": {}
                },
                "credentials": NOTION_CRED
            },
            # 2b. Actually, let's use a Code node to call Notion API for all properties at once
            # Replacing nodes 2 with a simpler approach: get the full page
            {
                "id": get_leaderboard_id,
                "name": "Get Player Stats",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [220, -100],
                "parameters": {
                    "method": "GET",
                    "url": f"https://api.notion.com/v1/pages/{LEADERBOARD_ME_PAGE}",
                    "authentication": "predefinedCredentialType",
                    "nodeCredentialType": "notionApi",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Notion-Version", "value": "2022-06-28"}
                        ]
                    },
                    "options": {}
                },
                "credentials": NOTION_CRED
            },
            # 3. Query Daily Summary for this week
            {
                "id": get_daily_summary_id,
                "name": "Get Weekly Summary",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [220, 100],
                "parameters": {
                    "method": "POST",
                    "url": f"https://api.notion.com/v1/databases/{DAILY_SUMMARY_DB}/query",
                    "authentication": "predefinedCredentialType",
                    "nodeCredentialType": "notionApi",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Notion-Version", "value": "2022-06-28"}
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": json.dumps({
                        "filter": {
                            "property": "Date",
                            "date": {
                                "this_week": {}
                            }
                        },
                        "sorts": [
                            {"property": "Date", "direction": "descending"}
                        ]
                    }),
                    "options": {}
                },
                "credentials": NOTION_CRED
            },
        ],
        "connections": {},
        "settings": {
            "executionOrder": "v1"
        },
        "staticData": None
    }

    # Clear nodes and rebuild properly
    workflow["nodes"] = []

    # ── Node 1: Schedule Trigger ──
    workflow["nodes"].append({
        "id": trigger_id,
        "name": "Every 2 Hours",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 300],
        "parameters": {
            "rule": {
                "interval": [
                    {"field": "hours", "hoursInterval": 2}
                ]
            }
        }
    })

    # ── Node 2: Get Leaderboard "Me" page ──
    workflow["nodes"].append({
        "id": get_leaderboard_id,
        "name": "Get Player Stats",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [260, 160],
        "parameters": {
            "method": "GET",
            "url": f"https://api.notion.com/v1/pages/{LEADERBOARD_ME_PAGE}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"}
                ]
            },
            "options": {}
        },
        "credentials": NOTION_CRED
    })

    # ── Node 3: Query Daily Summary this week ──
    workflow["nodes"].append({
        "id": get_daily_summary_id,
        "name": "Get Weekly Summary",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [260, 440],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{DAILY_SUMMARY_DB}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({
                "filter": {
                    "property": "Date",
                    "date": {"this_week": {}}
                },
                "sorts": [
                    {"property": "Date", "direction": "descending"}
                ]
            }),
            "options": {}
        },
        "credentials": NOTION_CRED
    })

    # ── Node 4: Wait (rate limit) ──
    workflow["nodes"].append({
        "id": wait_id,
        "name": "Wait 1s",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [520, 300],
        "parameters": {
            "amount": 1,
            "unit": "seconds"
        }
    })

    # ── Node 5: Aggregate + Format stats ──
    aggregate_code = r"""
// Get Player Stats from Leaderboard "Me" page
const playerPage = $('Get Player Stats').first().json;
const props = playerPage.properties || {};

// Extract formula values (Notion API returns formula results)
function getFormulaValue(prop) {
    if (!prop) return '--';
    if (prop.type === 'formula') {
        const f = prop.formula;
        if (f.type === 'number') return f.number != null ? f.number : '--';
        if (f.type === 'string') return f.string || '--';
    }
    return '--';
}

const level = getFormulaValue(props['Level'] || props['level']);
const gold = getFormulaValue(props['Gold'] || props['gold']);
const health = getFormulaValue(props['Health'] || props['health']);
const habits = getFormulaValue(props['Habits'] || props['habits']);

// Get Weekly Summary
const weeklyItems = $('Get Weekly Summary').first().json;
const results = weeklyItems.results || [];

let totalXP = 0;
let totalGold = 0;
let habitsCompleted = 0;
let dayCount = results.length;

for (const page of results) {
    const p = page.properties || {};

    // Rollup values
    function getRollupValue(prop) {
        if (!prop) return 0;
        if (prop.type === 'rollup') {
            const r = prop.rollup;
            if (r.type === 'number') return r.number || 0;
        }
        return 0;
    }

    totalXP += getRollupValue(p['Total XP'] || p['total_xp']);
    totalGold += getRollupValue(p['Total Gold'] || p['total_gold']);
    habitsCompleted += getRollupValue(p['Habits Completed'] || p['habits_completed']);
}

// Format Player Stats text
const playerStatsText = `⭐ Level: ${level} | 💰 Gold: ${gold} | ❤️ Health: ${health}\n📓 Habits: ${habits} | 🕐 Mis a jour auto`;

// Format Cette Semaine text
const weekText = `✅ Habits: ${habitsCompleted} | 💰 Gold: ${totalGold}\n⭐ XP: ${totalXP} | 📅 ${dayCount} jours`;

return [{
    json: {
        playerStatsText,
        weekText,
        level, gold, health, habits,
        totalXP, totalGold, habitsCompleted, dayCount,
        commandCenterPageId: '""" + COMMAND_CENTER_PAGE + r"""'
    }
}];
"""

    workflow["nodes"].append({
        "id": aggregate_id,
        "name": "Format Stats",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [740, 300],
        "parameters": {
            "jsCode": aggregate_code
        }
    })

    # ── Node 6: Find Command Center blocks ──
    workflow["nodes"].append({
        "id": find_blocks_id,
        "name": "Find Callout Blocks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [960, 300],
        "parameters": {
            "method": "GET",
            "url": f"https://api.notion.com/v1/blocks/{COMMAND_CENTER_PAGE}/children?page_size=100",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"}
                ]
            },
            "options": {}
        },
        "credentials": NOTION_CRED
    })

    # ── Node 7: Update callout blocks ──
    update_code = r"""
// Find the column blocks, then drill into callouts
const blocks = $('Find Callout Blocks').first().json;
const topBlocks = blocks.results || [];
const stats = $('Format Stats').first().json;

// The Command Center structure:
// blocks[0] = header callout
// blocks[1] = divider
// blocks[2] = columns (Today's Focus | Player Stats)
// blocks[3] = Navigation database
// blocks[4] = Cette Semaine callout
// ...

// We need to find:
// 1. The columns block containing Player Stats (index 2)
// 2. The Cette Semaine callout (index 4 or nearby)

let playerStatsColumnBlockId = null;
let cetteSemaineBlockId = null;

for (const block of topBlocks) {
    // Find Cette Semaine callout (top-level callout with orange)
    if (block.type === 'callout') {
        const text = (block.callout?.rich_text || []).map(t => t.plain_text).join('');
        if (text.includes('CETTE SEMAINE')) {
            cetteSemaineBlockId = block.id;
        }
    }
    // Find the columns block that contains Player Stats
    if (block.type === 'column_list' && !playerStatsColumnBlockId) {
        // This might be the first column_list (Today's Focus | Player Stats)
        playerStatsColumnBlockId = block.id;
    }
}

return [{
    json: {
        ...stats,
        playerStatsColumnBlockId,
        cetteSemaineBlockId,
        topBlockTypes: topBlocks.map(b => ({type: b.type, id: b.id, hasChildren: b.has_children}))
    }
}];
"""

    workflow["nodes"].append({
        "id": update_stats_id,
        "name": "Identify & Update Blocks",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1180, 300],
        "parameters": {
            "jsCode": update_code
        }
    })

    # ── Connections ──
    workflow["connections"] = {
        "Every 2 Hours": {
            "main": [[
                {"node": "Get Player Stats", "type": "main", "index": 0},
                {"node": "Get Weekly Summary", "type": "main", "index": 0}
            ]]
        },
        "Get Player Stats": {
            "main": [[
                {"node": "Wait 1s", "type": "main", "index": 0}
            ]]
        },
        "Get Weekly Summary": {
            "main": [[
                {"node": "Wait 1s", "type": "main", "index": 0}
            ]]
        },
        "Wait 1s": {
            "main": [[
                {"node": "Format Stats", "type": "main", "index": 0}
            ]]
        },
        "Format Stats": {
            "main": [[
                {"node": "Find Callout Blocks", "type": "main", "index": 0}
            ]]
        },
        "Find Callout Blocks": {
            "main": [[
                {"node": "Identify & Update Blocks", "type": "main", "index": 0}
            ]]
        }
    }

    return workflow


def deploy_workflow(workflow_json):
    """Deploy workflow to n8n."""
    print(f"\n📡 Creating workflow: {workflow_json['name']}")

    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow_json,
        timeout=30
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        wf_id = data.get("id", "unknown")
        print(f"   ✅ Created: {wf_id}")
        return wf_id
    else:
        print(f"   ❌ Error {resp.status_code}: {resp.text[:500]}")
        return None


def activate_workflow(wf_id):
    """Activate workflow."""
    print(f"   🔄 Activating {wf_id}...")
    resp = requests.patch(
        f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS,
        timeout=15
    )
    if resp.status_code == 200:
        print(f"   ✅ Activated!")
    else:
        print(f"   ⚠️ Activation: {resp.status_code} — {resp.text[:200]}")


def main():
    activate = "--activate" in sys.argv

    workflow = build_workflow()
    wf_id = deploy_workflow(workflow)

    if wf_id and activate:
        activate_workflow(wf_id)

    print(f"\n📊 Workflow ID: {wf_id}")
    print(f"🔗 {N8N_URL}/workflow/{wf_id}")
    print("\nℹ️  Ce workflow lit les stats Leaderboard + Daily Summary")
    print("   et identifie les blocs a mettre a jour sur le Command Center.")
    print("   Phase 2 : ajouter les PATCH requests pour updater les textes.")


if __name__ == "__main__":
    main()
