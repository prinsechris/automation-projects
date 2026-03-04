#!/usr/bin/env python3
"""Create n8n workflow: Goals Progress Auto-Calculator.

Schedule (4h) -> Query active Goals -> For each goal, query tasks & sub-goals
-> Calculate progress % -> Update Goal in Notion -> Telegram if delta > 10%.

Uses Notion official API via HTTP Request nodes with notionApi credential.
"""

import json
import requests

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9."
    "sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
)
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Notion IDs
GOALS_DB_PAGE_ID = "bc88ee5f-f09b-4f45-adb9-faae179aa276"
GOALS_COLLECTION_ID = "affa9ce1-a3d7-4182-a87d-8cbabf6fa983"
TASKS_DB_COLLECTION_ID = "305da200-b2d6-818e-bad3-000b048788f1"
TASKS_DB_PAGE_ID = "305da200-b2d6-8145-bc16-eaee02925a14"

# Telegram
TELEGRAM_CHAT_ID = "7342622615"

# Credential references (will be replaced with real IDs at deploy time)
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}

workflow = {
    "name": "Goals Progress Auto-Calculator",
    "nodes": [
        # ---------------------------------------------------------------
        # 1. Schedule Trigger — every 4 hours
        # ---------------------------------------------------------------
        {
            "parameters": {
                "rule": {
                    "interval": [{"field": "hours", "hoursInterval": 4}]
                }
            },
            "id": "schedule-trigger",
            "name": "Every 4h",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 300],
        },

        # ---------------------------------------------------------------
        # 2. Query Active Goals — POST to Notion /databases/:id/query
        # ---------------------------------------------------------------
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{GOALS_DB_PAGE_ID}/query",
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
                        "property": "Status",
                        "select": {
                            "equals": "In Progress"
                        }
                    },
                    "page_size": 100
                }),
                "options": {}
            },
            "id": "query-goals",
            "name": "Query Active Goals",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [240, 300],
            "credentials": {**NOTION_CRED},
        },

        # ---------------------------------------------------------------
        # 3. Split Goals — Code node extracts each goal into its own item
        # ---------------------------------------------------------------
        {
            "parameters": {
                "jsCode": """// Extract goals from Notion query response
const results = $input.first().json.results || [];

if (results.length === 0) {
  return [{json: {skip: true, message: 'No active goals found'}}];
}

const goals = results.map(page => {
  const props = page.properties || {};

  // Extract title
  const titleProp = props['Name'] || props['name'] || {};
  const titleArr = titleProp.title || [];
  const name = titleArr.map(t => t.plain_text || '').join('') || 'Untitled';

  // Current progress
  const progressProp = props['Progress %'] || props['Progress'] || {};
  const currentProgress = progressProp.number != null ? progressProp.number : null;

  // Sub-Goals relation IDs
  const subGoalsProp = props['Sub-Goals'] || props['Sub-goals'] || {};
  const subGoalIds = (subGoalsProp.relation || []).map(r => r.id);

  // Projects relation IDs (linked tasks/projects)
  const projectsProp = props['Projects'] || {};
  const projectIds = (projectsProp.relation || []).map(r => r.id);

  return {
    json: {
      goalId: page.id,
      goalName: name,
      currentProgress: currentProgress,
      subGoalIds: subGoalIds,
      projectIds: projectIds,
      hasSubGoals: subGoalIds.length > 0,
      hasProjects: projectIds.length > 0
    }
  };
});

return goals;
"""
            },
            "id": "split-goals",
            "name": "Split Goals",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [480, 300],
        },

        # ---------------------------------------------------------------
        # 4. Skip check — IF not skip
        # ---------------------------------------------------------------
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict"
                    },
                    "conditions": [
                        {
                            "id": "skip-check",
                            "leftValue": "={{ $json.skip }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "notEquals",
                                "singleValue": True,
                            },
                        }
                    ],
                    "combinator": "and",
                },
            },
            "id": "if-not-skip",
            "name": "Has Goals?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [700, 300],
        },

        # ---------------------------------------------------------------
        # 5. Query Related Tasks — For each goal, query Projects & Tasks
        #    where "Goal 1" relation contains this goal's ID
        # ---------------------------------------------------------------
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{TASKS_DB_PAGE_ID}/query",
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
                "jsonBody": """={
  "filter": {
    "property": "Goal 1",
    "relation": {
      "contains": "{{ $json.goalId }}"
    }
  },
  "page_size": 100
}""",
                "options": {}
            },
            "id": "query-tasks",
            "name": "Query Related Tasks",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [940, 200],
            "credentials": {**NOTION_CRED},
            "onError": "continueRegularOutput",
        },

        # ---------------------------------------------------------------
        # 6. Query Sub-Goals — For each goal, fetch sub-goal pages
        #    to get their Progress % values
        # ---------------------------------------------------------------
        {
            "parameters": {
                "jsCode": """// Fetch sub-goal progress values via Notion API
const goalId = $('Has Goals?').item.json.goalId;
const goalName = $('Has Goals?').item.json.goalName;
const currentProgress = $('Has Goals?').item.json.currentProgress;
const subGoalIds = $('Has Goals?').item.json.subGoalIds || [];
const hasSubGoals = $('Has Goals?').item.json.hasSubGoals;
const hasProjects = $('Has Goals?').item.json.hasProjects;

// Parse tasks from the HTTP response
const tasksResponse = $('Query Related Tasks').item.json;
const tasks = tasksResponse.results || [];

// Count task statuses
let totalTasks = 0;
let completedTasks = 0;

for (const task of tasks) {
  const props = task.properties || {};
  const statusProp = props['Status'] || {};

  // Status is a "status" type property with groups
  const statusObj = statusProp.status || {};
  const statusName = (statusObj.name || '').toLowerCase();

  // Only count actual tasks (Type != Project), or count all if no Type property
  const typeProp = props['Type'] || {};
  const typeSelect = typeProp.select || {};
  const typeName = (typeSelect.name || '').toLowerCase();

  // Skip items that are projects — we only want tasks/sub-tasks
  if (typeName === 'project') continue;

  totalTasks++;

  // Check if complete — Notion status groups: Complete group
  // Common complete statuses: Complete, Done, Completed, Shipped
  if (statusName === 'complete' || statusName === 'done' ||
      statusName === 'completed' || statusName === 'shipped') {
    completedTasks++;
  }
}

// If sub-goals exist, we need to fetch them
// We'll fetch each sub-goal page individually
let subGoalProgressValues = [];

if (hasSubGoals && subGoalIds.length > 0) {
  for (const sgId of subGoalIds) {
    try {
      const resp = await fetch(`https://api.notion.com/v1/pages/${sgId}`, {
        headers: {
          'Authorization': 'Bearer ' + $credentials.notionApi.apiKey,
          'Notion-Version': '2022-06-28'
        }
      });
      if (resp.ok) {
        const page = await resp.json();
        const props = page.properties || {};
        const progProp = props['Progress %'] || props['Progress'] || {};
        const progValue = progProp.number;
        if (progValue != null) {
          subGoalProgressValues.push(progValue);
        } else {
          // Sub-goal with no progress set — treat as 0
          subGoalProgressValues.push(0);
        }
      }
    } catch (e) {
      // If fetch fails, skip this sub-goal
      subGoalProgressValues.push(0);
    }
  }
}

// Calculate progress
let newProgress = null;

const taskProgress = totalTasks > 0
  ? Math.round((completedTasks / totalTasks) * 100)
  : null;

const subGoalProgress = subGoalProgressValues.length > 0
  ? Math.round(subGoalProgressValues.reduce((a, b) => a + b, 0) / subGoalProgressValues.length)
  : null;

if (taskProgress !== null && subGoalProgress !== null) {
  // Both exist — weighted average: 60% tasks, 40% sub-goals
  newProgress = Math.round(taskProgress * 0.6 + subGoalProgress * 0.4);
} else if (taskProgress !== null) {
  newProgress = taskProgress;
} else if (subGoalProgress !== null) {
  newProgress = subGoalProgress;
} else {
  // No tasks, no sub-goals with progress — keep current or set 0
  newProgress = currentProgress != null ? currentProgress : 0;
}

// Clamp to 0-100
newProgress = Math.max(0, Math.min(100, newProgress));

// Calculate delta
const previousProgress = currentProgress != null ? currentProgress : 0;
const delta = Math.abs(newProgress - previousProgress);
const progressChanged = newProgress !== previousProgress;

return [{
  json: {
    goalId,
    goalName,
    previousProgress: previousProgress,
    newProgress,
    delta,
    progressChanged,
    significantChange: delta > 10,
    totalTasks,
    completedTasks,
    taskProgress,
    subGoalCount: subGoalIds.length,
    subGoalProgress,
    calculationMethod:
      taskProgress !== null && subGoalProgress !== null ? 'weighted (60% tasks, 40% sub-goals)' :
      taskProgress !== null ? 'tasks only' :
      subGoalProgress !== null ? 'sub-goals only' : 'no data'
  }
}];
"""
            },
            "id": "calculate-progress",
            "name": "Calculate Progress",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1180, 300],
            "credentials": {**NOTION_CRED},
        },

        # ---------------------------------------------------------------
        # 7. IF Progress Changed — only update if value actually changed
        # ---------------------------------------------------------------
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict"
                    },
                    "conditions": [
                        {
                            "id": "progress-changed",
                            "leftValue": "={{ $json.progressChanged }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "equals",
                                "singleValue": True,
                            },
                        }
                    ],
                    "combinator": "and",
                },
            },
            "id": "if-changed",
            "name": "Progress Changed?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [1420, 300],
        },

        # ---------------------------------------------------------------
        # 8. Update Goal Progress — PATCH the Goal page in Notion
        # ---------------------------------------------------------------
        {
            "parameters": {
                "method": "PATCH",
                "url": "=https://api.notion.com/v1/pages/{{ $json.goalId }}",
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
                "jsonBody": """={
  "properties": {
    "Progress %": {
      "number": {{ $json.newProgress }}
    }
  }
}""",
                "options": {}
            },
            "id": "update-goal",
            "name": "Update Goal Progress",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1660, 200],
            "credentials": {**NOTION_CRED},
            "onError": "continueRegularOutput",
        },

        # ---------------------------------------------------------------
        # 9. Check Delta — IF progress changed > 10%, notify
        # ---------------------------------------------------------------
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict"
                    },
                    "conditions": [
                        {
                            "id": "delta-check",
                            "leftValue": "={{ $json.significantChange }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "equals",
                                "singleValue": True,
                            },
                        }
                    ],
                    "combinator": "and",
                },
            },
            "id": "if-significant",
            "name": "Delta > 10%?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [1900, 200],
        },

        # ---------------------------------------------------------------
        # 10. Send Telegram Notification
        # ---------------------------------------------------------------
        {
            "parameters": {
                "chatId": TELEGRAM_CHAT_ID,
                "text": "={{ (() => {\nconst g = $json;\nconst arrow = g.newProgress > g.previousProgress ? '📈' : '📉';\nconst sign = g.newProgress > g.previousProgress ? '+' : '';\nlet msg = `${arrow} *Goal Progress Update*\\n\\n`;\nmsg += `*${g.goalName}*\\n`;\nmsg += `${g.previousProgress}% → ${g.newProgress}% (${sign}${g.newProgress - g.previousProgress}%)\\n\\n`;\nmsg += `📊 Methode: ${g.calculationMethod}\\n`;\nif (g.totalTasks > 0) {\n  msg += `✅ Taches: ${g.completedTasks}/${g.totalTasks}\\n`;\n}\nif (g.subGoalCount > 0) {\n  msg += `🎯 Sous-objectifs: ${g.subGoalCount} (avg ${g.subGoalProgress}%)\\n`;\n}\nreturn msg;\n})() }}",
                "additionalFields": {
                    "parse_mode": "Markdown"
                },
            },
            "id": "telegram-notify",
            "name": "Notify Progress",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [2140, 100],
            "credentials": {**TELEGRAM_CRED},
        },

        # ---------------------------------------------------------------
        # 11. Log Summary — Code node that logs all results (no-op end)
        # ---------------------------------------------------------------
        {
            "parameters": {
                "jsCode": """// Summary log — collects all processed goals
const item = $input.first().json;
const msg = `Goal "${item.goalName}": ${item.previousProgress}% -> ${item.newProgress}% (delta: ${item.delta}%, method: ${item.calculationMethod})`;
console.log(msg);
return [{json: {logged: true, summary: msg}}];
"""
            },
            "id": "log-summary",
            "name": "Log Summary",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2140, 300],
        },
    ],
    "connections": {
        # Schedule -> Query Goals
        "Every 4h": {
            "main": [[{"node": "Query Active Goals", "type": "main", "index": 0}]]
        },
        # Query Goals -> Split Goals
        "Query Active Goals": {
            "main": [[{"node": "Split Goals", "type": "main", "index": 0}]]
        },
        # Split Goals -> Has Goals?
        "Split Goals": {
            "main": [[{"node": "Has Goals?", "type": "main", "index": 0}]]
        },
        # Has Goals? -> true: Query Tasks, false: nothing
        "Has Goals?": {
            "main": [
                [{"node": "Query Related Tasks", "type": "main", "index": 0}],
                [],
            ]
        },
        # Query Tasks -> Calculate Progress
        "Query Related Tasks": {
            "main": [[{"node": "Calculate Progress", "type": "main", "index": 0}]]
        },
        # Calculate Progress -> Progress Changed?
        "Calculate Progress": {
            "main": [[{"node": "Progress Changed?", "type": "main", "index": 0}]]
        },
        # Progress Changed? -> true: Update Goal, false: Log Summary
        "Progress Changed?": {
            "main": [
                [{"node": "Update Goal Progress", "type": "main", "index": 0}],
                [{"node": "Log Summary", "type": "main", "index": 0}],
            ]
        },
        # Update Goal -> Delta > 10%?
        "Update Goal Progress": {
            "main": [[{"node": "Delta > 10%?", "type": "main", "index": 0}]]
        },
        # Delta > 10%? -> true: Telegram, false: Log Summary
        "Delta > 10%?": {
            "main": [
                [{"node": "Notify Progress", "type": "main", "index": 0}],
                [{"node": "Log Summary", "type": "main", "index": 0}],
            ]
        },
        # Telegram -> Log Summary
        "Notify Progress": {
            "main": [[{"node": "Log Summary", "type": "main", "index": 0}]]
        },
    },
    "settings": {
        "executionOrder": "v1",
    },
}


def main():
    """Create and activate the Goals Progress Auto-Calculator workflow."""

    # ------------------------------------------------------------------
    # 1. Fetch existing credentials to get correct IDs
    # ------------------------------------------------------------------
    print("Fetching existing credentials...")
    resp = requests.get(f"{N8N_URL}/api/v1/credentials", headers=HEADERS)
    notion_cred_id = None
    notion_cred_name = None
    telegram_cred_id = None
    telegram_cred_name = None

    if resp.ok:
        creds = resp.json().get("data", [])
        for c in creds:
            ctype = c.get("type", "")
            cname = c.get("name", "")
            if ctype == "notionApi" or "notion" in cname.lower():
                notion_cred_id = c["id"]
                notion_cred_name = cname
                print(f"  Notion cred: {c['id']} — {cname}")
            if ctype == "telegramApi" or "telegram" in cname.lower():
                telegram_cred_id = c["id"]
                telegram_cred_name = cname
                print(f"  Telegram cred: {c['id']} — {cname}")
    else:
        print(f"  WARNING: Could not fetch credentials: {resp.status_code}")
        print(f"  Using default credential IDs from spec")

    # Use found creds or fall back to known IDs
    if not notion_cred_id:
        notion_cred_id = "FPqqVYnRbUnwRzrY"
        notion_cred_name = "Notion account"
    if not telegram_cred_id:
        telegram_cred_id = "37SeOsuQW7RBmQTl"
        telegram_cred_name = "Orun Telegram Bot"

    # ------------------------------------------------------------------
    # 2. Update credential references in all nodes
    # ------------------------------------------------------------------
    print("\nUpdating credential references...")
    for node in workflow["nodes"]:
        if "credentials" in node:
            if "notionApi" in node["credentials"]:
                node["credentials"]["notionApi"] = {
                    "id": str(notion_cred_id),
                    "name": notion_cred_name,
                }
                print(f"  {node['name']}: notionApi -> {notion_cred_id}")
            if "telegramApi" in node["credentials"]:
                node["credentials"]["telegramApi"] = {
                    "id": str(telegram_cred_id),
                    "name": telegram_cred_name,
                }
                print(f"  {node['name']}: telegramApi -> {telegram_cred_id}")

    # ------------------------------------------------------------------
    # 3. Check for existing workflow with same name and remove it
    # ------------------------------------------------------------------
    print("\nChecking for existing workflow...")
    resp = requests.get(f"{N8N_URL}/api/v1/workflows", headers=HEADERS)
    if resp.ok:
        existing = resp.json().get("data", [])
        for wf in existing:
            if wf.get("name") == workflow["name"]:
                wf_id = wf["id"]
                print(f"  Found existing workflow: {wf_id} — deleting...")
                del_resp = requests.delete(
                    f"{N8N_URL}/api/v1/workflows/{wf_id}",
                    headers=HEADERS,
                )
                if del_resp.ok:
                    print(f"  Deleted old workflow {wf_id}")
                else:
                    print(f"  WARNING: Could not delete: {del_resp.status_code}")

    # ------------------------------------------------------------------
    # 4. Create the workflow
    # ------------------------------------------------------------------
    print("\nCreating Goals Progress Auto-Calculator workflow...")
    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow,
    )

    if not resp.ok:
        print(f"  ERROR: Creation failed: {resp.status_code}")
        print(f"  Response: {resp.text[:500]}")
        return None

    data = resp.json()
    wf_id = data.get("id")
    print(f"  Created: {data.get('name')} (ID: {wf_id})")

    # ------------------------------------------------------------------
    # 5. Activate the workflow
    # ------------------------------------------------------------------
    print("\nActivating workflow...")
    resp2 = requests.patch(
        f"{N8N_URL}/api/v1/workflows/{wf_id}",
        headers=HEADERS,
        json={"active": True},
    )

    if resp2.ok:
        print(f"  ACTIVE — runs every 4 hours")
    else:
        print(f"  Activation failed: {resp2.status_code}")
        print(f"  Response: {resp2.text[:200]}")
        # Try alternative activation endpoint
        print("  Trying POST /activate endpoint...")
        resp3 = requests.post(
            f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
            headers=HEADERS,
        )
        if resp3.ok:
            print(f"  ACTIVE via /activate endpoint")
        else:
            print(f"  Also failed: {resp3.status_code} — {resp3.text[:200]}")

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("GOALS PROGRESS AUTO-CALCULATOR")
    print("=" * 60)
    print(f"Workflow ID:     {wf_id}")
    print(f"Schedule:        Every 4 hours")
    print(f"Goals DB:        {GOALS_DB_PAGE_ID}")
    print(f"Tasks DB:        {TASKS_DB_PAGE_ID}")
    print(f"Telegram chat:   {TELEGRAM_CHAT_ID}")
    print()
    print("Flow:")
    print("  1. Schedule Trigger (4h)")
    print("  2. Query Goals with Status='In Progress'")
    print("  3. Split into individual goal items")
    print("  4. For each goal: query linked tasks from Projects & Tasks DB")
    print("  5. For each goal: fetch sub-goal pages and their Progress %")
    print("  6. Calculate new progress:")
    print("     - Tasks only:      completed/total * 100")
    print("     - Sub-goals only:  average of sub-goal progress")
    print("     - Both:            60% tasks + 40% sub-goals")
    print("  7. Update Goal page if progress changed")
    print("  8. Send Telegram notification if delta > 10%")
    print("=" * 60)

    return wf_id


if __name__ == "__main__":
    wf_id = main()
    if wf_id:
        print(f"\nDone! Workflow ID: {wf_id}")
    else:
        print("\nFailed to create workflow.")
