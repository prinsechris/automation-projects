#!/usr/bin/env python3
"""Create the Session Closer workflow in n8n.

Webhook receives session data → updates Notion tasks → logs activity → sends Telegram recap.
"""

import json
import requests

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = "***N8N_API_KEY***"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

workflow = {
    "name": "Session Closer",
    "nodes": [
        {
            "parameters": {
                "httpMethod": "POST",
                "path": "session-close",
                "responseMode": "responseNode",
                "options": {}
            },
            "id": "webhook-1",
            "name": "Webhook",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [0, 0],
            "webhookId": "session-close-001"
        },
        {
            "parameters": {
                "jsCode": """// Parse and prepare session data
const body = $input.first().json.body;

const session = {
  session_number: body.session_number || 0,
  date: body.date || new Date().toISOString().split('T')[0],
  summary: body.summary || '',
  highlights: body.highlights || [],
  tasks_completed: body.tasks_completed || [],
  tasks_started: body.tasks_started || [],
  files_changed: body.files_changed || 0,
  workflows_modified: body.workflows_modified || 0,
  duration_hours: body.duration_hours || 0,
  git_pushed: body.git_pushed || false
};

// Build recap message
let recap = `📋 *Session ${session.session_number} — ${session.date}*\\n`;
recap += `${session.summary}\\n\\n`;

if (session.highlights.length > 0) {
  recap += `*Highlights :*\\n`;
  for (const h of session.highlights) {
    recap += `• ${h}\\n`;
  }
  recap += `\\n`;
}

recap += `✅ ${session.tasks_completed.length} taches completees\\n`;
recap += `🔄 ${session.tasks_started.length} taches demarrees\\n`;
recap += `📁 ${session.files_changed} fichiers modifies\\n`;
recap += `⚙️ ${session.workflows_modified} workflows n8n modifies\\n`;
recap += `⏱️ ~${session.duration_hours}h de travail\\n`;

if (session.git_pushed) {
  recap += `\\n✅ Session log commite et pushe sur GitHub`;
}

return [{json: {...session, recap}}];
"""
            },
            "id": "parse-1",
            "name": "Parse Session",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [220, 0]
        },
        {
            "parameters": {
                "jsCode": """// Split completed tasks into individual items
const session = $input.first().json;
const tasks = session.tasks_completed || [];

if (tasks.length === 0) {
  return [{json: {skip: true}}];
}

return tasks.map(taskId => ({json: {taskId, action: 'complete'}}));
"""
            },
            "id": "split-completed-1",
            "name": "Split Completed",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [440, -200]
        },
        {
            "parameters": {
                "method": "PATCH",
                "url": "=https://api.notion.com/v1/pages/{{ $json.taskId }}",
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
    "Status": {"status": {"name": "Complete"}},
    "Completed On": {"date": {"start": "{{ new Date().toISOString() }}"}}
  }
}""",
                "options": {}
            },
            "id": "update-completed-1",
            "name": "Mark Complete",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [660, -200],
            "credentials": {
                "notionApi": {
                    "id": "notion-cred",
                    "name": "Notion API"
                }
            },
            "onError": "continueRegularOutput"
        },
        {
            "parameters": {
                "jsCode": """// Split started tasks into individual items
const session = $input.first().json;
const tasks = session.tasks_started || [];

if (tasks.length === 0) {
  return [{json: {skip: true}}];
}

return tasks.map(taskId => ({json: {taskId, action: 'start'}}));
"""
            },
            "id": "split-started-1",
            "name": "Split Started",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [440, 0]
        },
        {
            "parameters": {
                "method": "PATCH",
                "url": "=https://api.notion.com/v1/pages/{{ $json.taskId }}",
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
    "Status": {"status": {"name": "In Progress"}}
  }
}""",
                "options": {}
            },
            "id": "update-started-1",
            "name": "Mark In Progress",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [660, 0],
            "credentials": {
                "notionApi": {
                    "id": "notion-cred",
                    "name": "Notion API"
                }
            },
            "onError": "continueRegularOutput"
        },
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.notion.com/v1/pages",
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
  "parent": {"database_id": "305da200-b2d6-8116-8039-000b9a9d9070"},
  "properties": {
    "Name": {"title": [{"text": {"content": "Session " + $('Parse Session').first().json.session_number + " — " + $('Parse Session').first().json.summary.substring(0, 80)}}]},
    "Date": {"date": {"start": $('Parse Session').first().json.date}},
    "Quests": {"relation": {{ JSON.stringify(($('Parse Session').first().json.tasks_completed || []).map(id => ({"id": id}))) }}}
  }
}""",
                "options": {}
            },
            "id": "activity-log-1",
            "name": "Activity Log Entry",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [440, 200],
            "credentials": {
                "notionApi": {
                    "id": "notion-cred",
                    "name": "Notion API"
                }
            },
            "onError": "continueRegularOutput"
        },
        {
            "parameters": {
                "jsCode": "// Split long messages for Telegram (4096 char limit)\nconst fullMsg = $('Parse Session').first().json.recap;\nconst MAX = 4000;\n\nif (fullMsg.length <= MAX) {\n    return [{json: {text: fullMsg}}];\n}\n\nconst sections = fullMsg.split(/\\n\\n/);\nconst parts = [];\nlet current = '';\n\nfor (const section of sections) {\n    if (current.length + section.length + 2 > MAX) {\n        if (current) parts.push(current.trim());\n        if (section.length > MAX) {\n            const lines = section.split('\\n');\n            let chunk = '';\n            for (const line of lines) {\n                if (chunk.length + line.length + 1 > MAX) {\n                    if (chunk) parts.push(chunk.trim());\n                    chunk = line;\n                } else {\n                    chunk += (chunk ? '\\n' : '') + line;\n                }\n            }\n            current = chunk;\n        } else {\n            current = section;\n        }\n    } else {\n        current += (current ? '\\n\\n' : '') + section;\n    }\n}\nif (current) parts.push(current.trim());\n\nif (parts.length === 1) return [{json: {text: parts[0]}}];\nreturn parts.map((p, i) => ({json: {text: '[' + (i+1) + '/' + parts.length + ']\\n' + p}}));"
            },
            "id": "split-telegram-1",
            "name": "Split for Telegram",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [660, 200]
        },
        {
            "parameters": {
                "chatId": "7376920302",
                "text": "={{ $json.text }}",
                "additionalFields": {
                    "parse_mode": "Markdown"
                }
            },
            "id": "telegram-1",
            "name": "Telegram Recap",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [880, 200],
            "credentials": {
                "telegramApi": {
                    "id": "telegram-cred",
                    "name": "Telegram API"
                }
            }
        },
        {
            "parameters": {
                "respondWith": "json",
                "responseBody": "={{ JSON.stringify({status: 'ok', session: $('Parse Session').first().json.session_number, tasks_completed: $('Parse Session').first().json.tasks_completed.length, tasks_started: $('Parse Session').first().json.tasks_started.length}) }}"
            },
            "id": "response-1",
            "name": "Response",
            "type": "n8n-nodes-base.respondToWebhook",
            "typeVersion": 1.1,
            "position": [1100, 200]
        }
    ],
    "connections": {
        "Webhook": {
            "main": [[{"node": "Parse Session", "type": "main", "index": 0}]]
        },
        "Parse Session": {
            "main": [
                [
                    {"node": "Split Completed", "type": "main", "index": 0},
                    {"node": "Split Started", "type": "main", "index": 0},
                    {"node": "Activity Log Entry", "type": "main", "index": 0}
                ]
            ]
        },
        "Split Completed": {
            "main": [[{"node": "Mark Complete", "type": "main", "index": 0}]]
        },
        "Split Started": {
            "main": [[{"node": "Mark In Progress", "type": "main", "index": 0}]]
        },
        "Activity Log Entry": {
            "main": [[{"node": "Split for Telegram", "type": "main", "index": 0}]]
        },
        "Split for Telegram": {
            "main": [[{"node": "Telegram Recap", "type": "main", "index": 0}]]
        },
        "Telegram Recap": {
            "main": [[{"node": "Response", "type": "main", "index": 0}]]
        }
    },
    "settings": {
        "executionOrder": "v1"
    }
}

def main():
    # Check existing credentials
    print("Fetching existing credentials...")
    r = requests.get(f"{N8N_URL}/api/v1/credentials", headers=HEADERS)
    creds = r.json().get("data", [])

    notion_cred_id = None
    telegram_cred_id = None

    for c in creds:
        if "notion" in c.get("name", "").lower() or c.get("type") == "notionApi":
            notion_cred_id = c["id"]
            print(f"  Found Notion cred: {c['name']} (id={c['id']})")
        if "telegram" in c.get("name", "").lower() or c.get("type") == "telegramApi":
            telegram_cred_id = c["id"]
            print(f"  Found Telegram cred: {c['name']} (id={c['id']})")

    if not notion_cred_id or not telegram_cred_id:
        print(f"WARNING: Missing credentials - Notion: {notion_cred_id}, Telegram: {telegram_cred_id}")

    # Update credential references in workflow
    for node in workflow["nodes"]:
        if "credentials" in node:
            if "notionApi" in node["credentials"]:
                node["credentials"]["notionApi"]["id"] = str(notion_cred_id)
            if "telegramApi" in node["credentials"]:
                node["credentials"]["telegramApi"]["id"] = str(telegram_cred_id)

    # Create workflow
    print("Creating Session Closer workflow...")
    r = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow
    )

    if r.status_code in (200, 201):
        wf = r.json()
        wf_id = wf["id"]
        print(f"  Created: {wf_id}")

        # Activate
        print("Activating workflow...")
        r2 = requests.post(
            f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
            headers=HEADERS
        )
        if r2.status_code == 200:
            print(f"  Activated!")
        else:
            print(f"  Activation failed: {r2.status_code} {r2.text[:200]}")

        print(f"\nWorkflow ID: {wf_id}")
        print(f"Webhook URL: {N8N_URL}/webhook/session-close")
        return wf_id
    else:
        print(f"  Error: {r.status_code}")
        print(f"  {r.text[:500]}")
        return None

if __name__ == "__main__":
    main()
