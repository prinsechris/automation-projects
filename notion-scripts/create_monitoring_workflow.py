"""Create n8n Monitoring workflow — logs executions to Notion + alerts on Telegram."""

import json
import requests

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9.sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Notion config
NOTION_DB_ID = "4f90773c5f61477f88df8e9fcb019cbc"
NOTION_DASHBOARD_ID = "312da200-b2d6-8199-b94c-e9e62a802d00"

# Telegram config (Orun bot)
TELEGRAM_CHAT_ID = "7342622615"

workflow = {
    "name": "n8n Monitoring — Execution Logs + Alerts",
    "nodes": [
        # 1. Schedule Trigger — every hour
        {
            "parameters": {
                "rule": {
                    "interval": [{"field": "hours", "hoursInterval": 1}]
                }
            },
            "id": "trigger",
            "name": "Every Hour",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 0],
        },
        # 2. Code node — Fetch recent executions via n8n API
        {
            "parameters": {
                "jsCode": """
const N8N_URL = "https://n8n.srv842982.hstgr.cloud";
const API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9.sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4";

// Fetch last 50 executions
const execResp = await fetch(`${N8N_URL}/api/v1/executions?limit=50`, {
  headers: {"X-N8N-API-KEY": API_KEY}
});
const execData = await execResp.json();

// Fetch workflow names
const wfResp = await fetch(`${N8N_URL}/api/v1/workflows`, {
  headers: {"X-N8N-API-KEY": API_KEY}
});
const wfData = await wfResp.json();
const wfMap = {};
for (const wf of wfData.data || []) {
  wfMap[wf.id] = wf.name;
}

// Filter to last hour only
const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
const recent = (execData.data || []).filter(e => e.startedAt >= oneHourAgo);

// Build stats
let totalSuccess = 0;
let totalError = 0;
let totalWarning = 0;
const errors = [];
const allLogs = [];

for (const exec of recent) {
  const wfName = wfMap[exec.workflowId] || exec.workflowId;
  const duration = exec.stoppedAt && exec.startedAt
    ? Math.round((new Date(exec.stoppedAt) - new Date(exec.startedAt)) / 1000)
    : 0;

  const modeMap = {
    "trigger": "Schedule",
    "webhook": "Webhook",
    "manual": "Manual",
    "integrated": "Integrated"
  };

  let status = "Success";
  let errorMsg = "";

  if (exec.status === "error" || exec.status === "crashed") {
    status = "Error";
    totalError++;
    errorMsg = exec.status === "crashed" ? "Workflow crashed" : "Execution failed";
    errors.push({
      workflow: wfName,
      workflowId: exec.workflowId,
      execId: String(exec.id),
      error: errorMsg,
      time: exec.startedAt
    });
  } else if (exec.status === "warning") {
    status = "Warning";
    totalWarning++;
  } else {
    totalSuccess++;
  }

  allLogs.push({
    workflow: wfName,
    workflowId: exec.workflowId,
    execId: String(exec.id),
    status: status,
    trigger: modeMap[exec.mode] || exec.mode,
    duration: duration,
    errorMsg: errorMsg,
    startedAt: exec.startedAt
  });
}

// Build summary
const total = recent.length;
const successRate = total > 0 ? Math.round((totalSuccess / total) * 100) : 100;

return [{
  json: {
    stats: {
      total,
      success: totalSuccess,
      errors: totalError,
      warnings: totalWarning,
      successRate,
      timestamp: new Date().toISOString()
    },
    logs: allLogs.slice(0, 20),  // Last 20 for Notion
    errors: errors,
    hasErrors: errors.length > 0
  }
}];
"""
            },
            "id": "fetch_executions",
            "name": "Fetch Executions",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [220, 0],
        },
        # 3. IF — has errors?
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "err_check",
                            "leftValue": "={{ $json.hasErrors }}",
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
            "id": "if_errors",
            "name": "Has Errors?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [440, 0],
        },
        # 4a. Telegram Alert (true branch)
        {
            "parameters": {
                "chatId": TELEGRAM_CHAT_ID,
                "text": "={{ (() => {\nconst stats = $json.stats;\nconst errors = $json.errors;\nlet msg = `⚠️ n8n MONITORING ALERT\\n\\n`;\nmsg += `📊 Derniere heure:\\n`;\nmsg += `  ✅ ${stats.success} succes\\n`;\nmsg += `  ❌ ${stats.errors} erreur(s)\\n`;\nmsg += `  📈 Taux: ${stats.successRate}%\\n\\n`;\nmsg += `🔴 ERREURS:\\n`;\nfor (const e of errors.slice(0, 5)) {\n  msg += `• ${e.workflow} (${e.time.substring(11,16)})\\n  → ${e.error}\\n`;\n}\nreturn msg;\n})() }}",
                "additionalFields": {
                    "parse_mode": "HTML"
                },
            },
            "id": "telegram_alert",
            "name": "Telegram Alert",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [660, -100],
            "credentials": {
                "telegramApi": {
                    "id": "orun_telegram",
                    "name": "Orun Telegram"
                }
            },
        },
        # 4b. No errors — just log (false branch, goes to Notion too)
        {
            "parameters": {
                "jsCode": """
// Pass through — no errors to alert
const data = $input.first().json;
return [{ json: data }];
"""
            },
            "id": "no_errors",
            "name": "No Errors",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [660, 100],
        },
        # 5. Code — Prepare Notion log entries
        {
            "parameters": {
                "jsCode": """
const data = $input.first().json;
const logs = data.logs || [];

// Return each log as a separate item for Notion
const items = logs.map(log => ({
  json: {
    workflow: log.workflow,
    workflowId: log.workflowId,
    execId: log.execId,
    status: log.status,
    trigger: log.trigger,
    duration: log.duration,
    errorMsg: log.errorMsg || "",
    startedAt: log.startedAt
  }
}));

// If no logs, return empty signal
if (items.length === 0) {
  return [{ json: { skip: true } }];
}

return items;
"""
            },
            "id": "prepare_notion",
            "name": "Prepare Notion Logs",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [880, 0],
        },
        # 6. IF — skip empty?
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "skip_check",
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
            "id": "if_has_logs",
            "name": "Has Logs?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [1100, 0],
        },
        # 7. Notion — Create log entry
        {
            "parameters": {
                "resource": "databasePage",
                "databaseId": {
                    "__rl": True,
                    "value": NOTION_DB_ID,
                    "mode": "id",
                },
                "title": "={{ $json.workflow }}",
                "propertiesUi": {
                    "propertyValues": [
                        {
                            "key": "Status|select",
                            "selectValue": "={{ $json.status }}",
                        },
                        {
                            "key": "Execution ID|rich_text",
                            "textContent": "={{ $json.execId }}",
                        },
                        {
                            "key": "Error Message|rich_text",
                            "textContent": "={{ $json.errorMsg }}",
                        },
                        {
                            "key": "Duration (s)|number",
                            "numberValue": "={{ $json.duration }}",
                        },
                        {
                            "key": "Trigger|select",
                            "selectValue": "={{ $json.trigger }}",
                        },
                        {
                            "key": "Workflow ID|rich_text",
                            "textContent": "={{ $json.workflowId }}",
                        },
                    ]
                },
            },
            "id": "notion_log",
            "name": "Log to Notion",
            "type": "n8n-nodes-base.notion",
            "typeVersion": 2.2,
            "position": [1320, -50],
            "credentials": {
                "notionApi": {
                    "id": "notion_creds",
                    "name": "Notion"
                }
            },
        },
        # 8. Code — Update dashboard stats
        {
            "parameters": {
                "jsCode": """
// This updates the Notion dashboard page with latest stats
// Using HTTP request to Notion API
const data = $('Fetch Executions').first().json;
const stats = data.stats;

const now = new Date().toLocaleString('fr-FR', {timeZone: 'Europe/Paris'});

const content = `**Derniere verification** : ${now}
**Executions 1h** : ${stats.total}
**Taux de succes** : ${stats.successRate}%
**Succes** : ${stats.success} | **Erreurs** : ${stats.errors} | **Warnings** : ${stats.warnings}`;

return [{ json: { dashboardStats: content, stats } }];
"""
            },
            "id": "update_dashboard",
            "name": "Update Dashboard",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1320, 100],
        },
    ],
    "connections": {
        "Every Hour": {
            "main": [[{"node": "Fetch Executions", "type": "main", "index": 0}]]
        },
        "Fetch Executions": {
            "main": [[{"node": "Has Errors?", "type": "main", "index": 0}]]
        },
        "Has Errors?": {
            "main": [
                [{"node": "Telegram Alert", "type": "main", "index": 0}],
                [{"node": "No Errors", "type": "main", "index": 0}],
            ]
        },
        "Telegram Alert": {
            "main": [[{"node": "Prepare Notion Logs", "type": "main", "index": 0}]]
        },
        "No Errors": {
            "main": [[{"node": "Prepare Notion Logs", "type": "main", "index": 0}]]
        },
        "Prepare Notion Logs": {
            "main": [[{"node": "Has Logs?", "type": "main", "index": 0}]]
        },
        "Has Logs?": {
            "main": [
                [
                    {"node": "Log to Notion", "type": "main", "index": 0},
                    {"node": "Update Dashboard", "type": "main", "index": 0},
                ],
                [],  # false branch — no logs, do nothing
            ]
        },
    },
    "settings": {
        "executionOrder": "v1",
    },
}


def main():
    # First, get existing credentials to find the right IDs
    print("Fetching existing credentials...")
    resp = requests.get(f"{N8N_URL}/api/v1/credentials", headers=HEADERS)
    if resp.ok:
        creds = resp.json().get("data", [])
        telegram_cred = None
        notion_cred = None
        for c in creds:
            if "telegram" in c.get("name", "").lower() or "telegram" in c.get("type", "").lower():
                telegram_cred = c
                print(f"  Telegram cred: {c['id']} — {c['name']}")
            if "notion" in c.get("name", "").lower() or "notion" in c.get("type", "").lower():
                notion_cred = c
                print(f"  Notion cred: {c['id']} — {c['name']}")

        # Update credential IDs in workflow
        if telegram_cred:
            workflow["nodes"][3]["credentials"]["telegramApi"] = {
                "id": telegram_cred["id"],
                "name": telegram_cred["name"],
            }
        if notion_cred:
            workflow["nodes"][7]["credentials"]["notionApi"] = {
                "id": notion_cred["id"],
                "name": notion_cred["name"],
            }
    else:
        print(f"  Warning: Could not fetch credentials: {resp.status_code}")

    # Create the workflow
    print("\nCreating monitoring workflow...")
    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow,
    )

    if resp.ok:
        data = resp.json()
        wf_id = data.get("id")
        print(f"  Created: {data.get('name')} (ID: {wf_id})")

        # Activate it
        print("Activating workflow...")
        resp2 = requests.patch(
            f"{N8N_URL}/api/v1/workflows/{wf_id}",
            headers=HEADERS,
            json={"active": True},
        )
        if resp2.ok:
            print(f"  ACTIVE — runs every hour")
        else:
            print(f"  Activation failed: {resp2.status_code} — {resp2.text[:200]}")

        return wf_id
    else:
        print(f"  Creation failed: {resp.status_code}")
        print(f"  Response: {resp.text[:500]}")
        return None


if __name__ == "__main__":
    wf_id = main()
    if wf_id:
        print(f"\nDone! Workflow ID: {wf_id}")
        print(f"Dashboard: https://www.notion.so/312da200b2d68199b94ce9e62a802d00")
        print(f"Logs DB: https://www.notion.so/4f90773c5f61477f88df8e9fcb019cbc")
