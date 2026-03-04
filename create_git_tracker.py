#!/usr/bin/env python3
"""Create the Git Activity Tracker workflow in n8n.

CRON (6h) → fetch commits 3 repos → fetch Notion tasks → Claude analysis → auto-update Notion → Telegram recap.
"""

import json
import requests

import os

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = open(os.path.expanduser("~/.n8n-api-key")).read().strip()
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

GITHUB_TOKEN = open(os.path.expanduser("~/.github-token")).read().strip() if os.path.exists(os.path.expanduser("~/.github-token")) else os.environ.get("GITHUB_TOKEN", "")
ANTHROPIC_KEY = open(os.path.expanduser("~/.anthropic-key")).read().strip() if os.path.exists(os.path.expanduser("~/.anthropic-key")) else os.environ.get("ANTHROPIC_API_KEY", "")

REPOS = [
    "prinsechris/AI-Business-Automation-Suite",
    "prinsechris/tiktok-automation-pro",
    "prinsechris/automation-projects"
]

workflow = {
    "name": "Git Activity Tracker",
    "nodes": [
        # 1. Schedule Trigger - every 6 hours
        {
            "parameters": {
                "rule": {
                    "interval": [{"field": "hours", "hoursInterval": 6}]
                }
            },
            "id": "schedule-1",
            "name": "Every 6h",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 0]
        },
        # 2. Setup - define repos and time window
        {
            "parameters": {
                "jsCode": """// Calculate time window (last 7 hours to overlap slightly)
const since = new Date(Date.now() - 7 * 60 * 60 * 1000).toISOString();
const repos = """ + json.dumps(REPOS) + """;

return [{json: {since, repos, github_token: '""" + GITHUB_TOKEN + """'}}];
"""
            },
            "id": "setup-1",
            "name": "Setup",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [220, 0]
        },
        # 3. Fetch commits repo 1
        {
            "parameters": {
                "method": "GET",
                "url": "=https://api.github.com/repos/" + REPOS[0] + "/commits?since={{ $json.since }}&per_page=50",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Accept", "value": "application/vnd.github.v3+json"},
                        {"name": "User-Agent", "value": "n8n-git-tracker"}
                    ]
                },
                "options": {"response": {"response": {"fullResponse": False}}}
            },
            "id": "commits-1",
            "name": "Commits: AI-Business",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [440, -200],
            "credentials": {"httpHeaderAuth": {"id": "github-header", "name": "GitHub Token"}},
            "onError": "continueRegularOutput"
        },
        # 4. Fetch commits repo 2
        {
            "parameters": {
                "method": "GET",
                "url": "=https://api.github.com/repos/" + REPOS[1] + "/commits?since={{ $json.since }}&per_page=50",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Accept", "value": "application/vnd.github.v3+json"},
                        {"name": "User-Agent", "value": "n8n-git-tracker"}
                    ]
                },
                "options": {"response": {"response": {"fullResponse": False}}}
            },
            "id": "commits-2",
            "name": "Commits: TikTok",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [440, 0],
            "credentials": {"httpHeaderAuth": {"id": "github-header", "name": "GitHub Token"}},
            "onError": "continueRegularOutput"
        },
        # 5. Fetch commits repo 3
        {
            "parameters": {
                "method": "GET",
                "url": "=https://api.github.com/repos/" + REPOS[2] + "/commits?since={{ $json.since }}&per_page=50",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Accept", "value": "application/vnd.github.v3+json"},
                        {"name": "User-Agent", "value": "n8n-git-tracker"}
                    ]
                },
                "options": {"response": {"response": {"fullResponse": False}}}
            },
            "id": "commits-3",
            "name": "Commits: Automation",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [440, 200],
            "credentials": {"httpHeaderAuth": {"id": "github-header", "name": "GitHub Token"}},
            "onError": "continueRegularOutput"
        },
        # 6. Fetch current Notion tasks
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.notion.com/v1/databases/305da200-b2d6-818e-bad3-000b048788f1/query",
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
                        "and": [
                            {"property": "Status", "status": {"does_not_equal": "Complete"}},
                            {"property": "Status", "status": {"does_not_equal": "Archive"}}
                        ]
                    },
                    "page_size": 100
                }),
                "options": {}
            },
            "id": "notion-tasks-1",
            "name": "Fetch Notion Tasks",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [440, 400],
            "credentials": {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
        },
        # 7. Compile all data for Claude
        {
            "parameters": {
                "jsCode": r"""// Compile git commits from all repos
const repos = [
  {name: 'AI-Business-Automation-Suite', data: $('Commits: AI-Business').first().json},
  {name: 'tiktok-automation-pro', data: $('Commits: TikTok').first().json},
  {name: 'automation-projects', data: $('Commits: Automation').first().json}
];

let gitSummary = '';
let totalCommits = 0;

for (const repo of repos) {
  const commits = Array.isArray(repo.data) ? repo.data : [];
  if (commits.length === 0) continue;

  gitSummary += `\n## ${repo.name} (${commits.length} commits)\n`;
  for (const c of commits) {
    const msg = c.commit?.message || '(no message)';
    const date = c.commit?.author?.date || '';
    const sha = (c.sha || '').substring(0, 7);
    gitSummary += `- [${sha}] ${date.substring(0,16)} — ${msg.split('\n')[0]}\n`;
    totalCommits++;
  }
}

if (totalCommits === 0) {
  return [{json: {skip: true, reason: 'No commits in time window'}}];
}

// Compile Notion tasks
const notionData = $('Fetch Notion Tasks').first().json;
const results = notionData.results || [];
let notionSummary = '\n## Current Notion Tasks\n';

for (const page of results) {
  const props = page.properties || {};
  const name = props.Name?.title?.[0]?.plain_text || '(unnamed)';
  const status = props.Status?.status?.name || '?';
  const type = props.Type?.select?.name || '?';
  const category = props.Category?.select?.name || '';
  const id = page.id;
  notionSummary += `- [${id}] ${name} | Type: ${type} | Status: ${status} | Category: ${category}\n`;
}

return [{json: {
  gitSummary,
  notionSummary,
  totalCommits,
  taskCount: results.length
}}];
"""
            },
            "id": "compile-1",
            "name": "Compile Data",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [700, 100]
        },
        # 8. Check if should skip (no commits)
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "skip-check",
                            "leftValue": "={{ $json.skip }}",
                            "rightValue": True,
                            "operator": {"type": "boolean", "operation": "equals"}
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "if-skip-1",
            "name": "Has Commits?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [920, 100]
        },
        # 9. Claude Analysis
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.anthropic.com/v1/messages",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "x-api-key", "value": ANTHROPIC_KEY},
                        {"name": "anthropic-version", "value": "2023-06-01"},
                        {"name": "Content-Type", "value": "application/json"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": """={
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 4096,
  "messages": [{"role": "user", "content": "Tu es un assistant de tracking de projets. Analyse les commits Git recents et compare-les avec les taches Notion existantes.\\n\\n# Commits Git recents\\n" + $json.gitSummary.replace(/"/g, '\\\\"').replace(/\\n/g, '\\\\n') + "\\n\\n# Taches Notion actuelles\\n" + $json.notionSummary.replace(/"/g, '\\\\"').replace(/\\n/g, '\\\\n') + "\\n\\nAnalyse et retourne un JSON STRICT (pas de texte autour) avec cette structure :\\n{\\n  \\"summary\\": \\"Resume en 1-2 phrases de l'activite\\",\\n  \\"actions\\": [\\n    {\\n      \\"type\\": \\"update\\",\\n      \\"task_id\\": \\"notion-page-id\\",\\n      \\"task_name\\": \\"nom de la tache\\",\\n      \\"new_status\\": \\"Complete\\" ou \\"In Progress\\",\\n      \\"reason\\": \\"pourquoi ce changement\\"\\n    },\\n    {\\n      \\"type\\": \\"create\\",\\n      \\"task_name\\": \\"nouvelle tache detectee\\",\\n      \\"task_type\\": \\"Task\\" ou \\"Sub-task\\",\\n      \\"status\\": \\"In Progress\\" ou \\"Backlog\\",\\n      \\"category\\": \\"Business\\" ou \\"Automatisation\\" ou \\"Perso\\",\\n      \\"reason\\": \\"pourquoi creer cette tache\\"\\n    }\\n  ]\\n}\\n\\nRegles :\\n- Ne marque Complete QUE si les commits montrent clairement que le travail est fini\\n- Marque In Progress si du travail a ete fait mais pas fini\\n- Cree une nouvelle tache SEULEMENT si le travail ne correspond a aucune tache existante\\n- Si aucune action necessaire, retourne {actions: [], summary: \\"...\\"}\\n- IMPORTANT: retourne UNIQUEMENT le JSON, rien d'autre"}]
}""",
                "options": {}
            },
            "id": "claude-1",
            "name": "Claude Analysis",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1140, 0]
        },
        # 10. Parse Claude response into actions
        {
            "parameters": {
                "jsCode": r"""// Parse Claude's response
const response = $input.first().json;
const content = response.content?.[0]?.text || '{}';

let analysis;
try {
  // Try to extract JSON from the response
  const jsonMatch = content.match(/\{[\s\S]*\}/);
  analysis = JSON.parse(jsonMatch ? jsonMatch[0] : content);
} catch (e) {
  return [{json: {error: 'Failed to parse Claude response', raw: content.substring(0, 500), actions: [], summary: 'Parse error'}}];
}

const actions = analysis.actions || [];
const summary = analysis.summary || 'No summary';

if (actions.length === 0) {
  return [{json: {summary, actions: [], actionCount: 0, skip: true}}];
}

// Return individual items for each action
const items = actions.map((action, i) => ({
  json: {
    ...action,
    index: i,
    totalActions: actions.length,
    summary
  }
}));

return items;
"""
            },
            "id": "parse-actions-1",
            "name": "Parse Actions",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1360, 0]
        },
        # 11. Route: create vs update
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "type-check",
                            "leftValue": "={{ $json.type }}",
                            "rightValue": "update",
                            "operator": {"type": "string", "operation": "equals"}
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "route-1",
            "name": "Update or Create?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [1580, 0]
        },
        # 12. Update existing task
        {
            "parameters": {
                "method": "PATCH",
                "url": "=https://api.notion.com/v1/pages/{{ $json.task_id }}",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "notionApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '={\n  "properties": {\n    "Status": {"status": {"name": "{{ $json.new_status }}"}}\n    {{ $json.new_status === "Complete" ? \',"Completed On": {"date": {"start": "\' + new Date().toISOString() + \'"}}\' : \'\' }}\n  }\n}',
                "options": {}
            },
            "id": "update-task-1",
            "name": "Update Task",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1800, -100],
            "credentials": {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}},
            "onError": "continueRegularOutput"
        },
        # 13. Create new task
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.notion.com/v1/pages",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "notionApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": """={\n  "parent": {"database_id": "305da200-b2d6-818e-bad3-000b048788f1"},\n  "properties": {\n    "Name": {"title": [{"text": {"content": "{{ $json.task_name }}"}}]},\n    "Type": {"select": {"name": "{{ $json.task_type || 'Task' }}"}},\n    "Status": {"status": {"name": "{{ $json.status || 'Backlog' }}"}},\n    "Category": {"select": {"name": "{{ $json.category === 'Business' ? '💼 Business' : $json.category === 'Automatisation' ? '🤖 Automatisation' : '🏠 Perso' }}"}}\n  }\n}""",
                "options": {}
            },
            "id": "create-task-1",
            "name": "Create Task",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1800, 100],
            "credentials": {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}},
            "onError": "continueRegularOutput"
        },
        # 14. Build recap
        {
            "parameters": {
                "jsCode": r"""// Build Telegram recap from all processed actions
const allItems = $input.all();
const parseItems = $('Parse Actions').all();
const compileData = $('Compile Data').first().json;
const summary = parseItems[0]?.json?.summary || 'Aucune activite detectee';

let updated = 0;
let created = 0;
let details = '';

for (const item of parseItems) {
  const j = item.json;
  if (j.skip) continue;
  if (j.type === 'update') {
    updated++;
    details += `🔄 ${j.task_name} → ${j.new_status}\n`;
  } else if (j.type === 'create') {
    created++;
    details += `➕ ${j.task_name} (${j.status})\n`;
  }
}

let recap = `🤖 *Git Activity Tracker*\n\n`;
recap += `${summary}\n\n`;
recap += `📊 ${compileData.totalCommits} commits analyses\n`;
recap += `📋 ${compileData.taskCount} taches Notion verifiees\n`;

if (updated > 0 || created > 0) {
  recap += `\n*Actions :*\n`;
  recap += details;
  recap += `\n✅ ${updated} mises a jour, ➕ ${created} creees`;
} else {
  recap += `\n✅ Notion est a jour, aucune action necessaire`;
}

return [{json: {recap}}];
"""
            },
            "id": "recap-1",
            "name": "Build Recap",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2020, 0]
        },
        # 15. Telegram
        {
            "parameters": {
                "chatId": "7342622615",
                "text": "={{ $json.recap }}",
                "additionalFields": {"parse_mode": "Markdown"}
            },
            "id": "telegram-1",
            "name": "Telegram Recap",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [2240, 0],
            "credentials": {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}
        }
    ],
    "connections": {
        "Every 6h": {
            "main": [[{"node": "Setup", "type": "main", "index": 0}]]
        },
        "Setup": {
            "main": [[
                {"node": "Commits: AI-Business", "type": "main", "index": 0},
                {"node": "Commits: TikTok", "type": "main", "index": 0},
                {"node": "Commits: Automation", "type": "main", "index": 0},
                {"node": "Fetch Notion Tasks", "type": "main", "index": 0}
            ]]
        },
        "Commits: AI-Business": {
            "main": [[{"node": "Compile Data", "type": "main", "index": 0}]]
        },
        "Commits: TikTok": {
            "main": [[{"node": "Compile Data", "type": "main", "index": 0}]]
        },
        "Commits: Automation": {
            "main": [[{"node": "Compile Data", "type": "main", "index": 0}]]
        },
        "Fetch Notion Tasks": {
            "main": [[{"node": "Compile Data", "type": "main", "index": 0}]]
        },
        "Compile Data": {
            "main": [[{"node": "Has Commits?", "type": "main", "index": 0}]]
        },
        "Has Commits?": {
            "main": [
                [{"node": "Telegram Recap", "type": "main", "index": 0}],
                [{"node": "Claude Analysis", "type": "main", "index": 0}]
            ]
        },
        "Claude Analysis": {
            "main": [[{"node": "Parse Actions", "type": "main", "index": 0}]]
        },
        "Parse Actions": {
            "main": [[{"node": "Update or Create?", "type": "main", "index": 0}]]
        },
        "Update or Create?": {
            "main": [
                [{"node": "Update Task", "type": "main", "index": 0}],
                [{"node": "Create Task", "type": "main", "index": 0}]
            ]
        },
        "Update Task": {
            "main": [[{"node": "Build Recap", "type": "main", "index": 0}]]
        },
        "Create Task": {
            "main": [[{"node": "Build Recap", "type": "main", "index": 0}]]
        },
        "Build Recap": {
            "main": [[{"node": "Telegram Recap", "type": "main", "index": 0}]]
        }
    },
    "settings": {
        "executionOrder": "v1"
    }
}


def main():
    # First, check if GitHub httpHeaderAuth credential exists
    print("Checking for GitHub credential in n8n...")
    r = requests.get(f"{N8N_URL}/api/v1/credentials", headers=HEADERS)
    creds = r.json().get("data", [])

    github_cred_id = None
    for c in creds:
        if "github" in c.get("name", "").lower() and c.get("type") == "httpHeaderAuth":
            github_cred_id = c["id"]
            print(f"  Found: {c['name']} (id={c['id']})")

    if not github_cred_id:
        # Create GitHub credential
        print("  Creating GitHub httpHeaderAuth credential...")
        cred_payload = {
            "name": "GitHub Token",
            "type": "httpHeaderAuth",
            "data": {
                "name": "Authorization",
                "value": f"Bearer {GITHUB_TOKEN}"
            }
        }
        r = requests.post(f"{N8N_URL}/api/v1/credentials", headers=HEADERS, json=cred_payload)
        if r.status_code in (200, 201):
            github_cred_id = r.json()["id"]
            print(f"  Created: {github_cred_id}")
        else:
            print(f"  Failed: {r.status_code} {r.text[:200]}")
            # Try without auth - use direct headers instead
            print("  Falling back to direct auth headers...")
            github_cred_id = None

    # Update credential references
    for node in workflow["nodes"]:
        creds = node.get("credentials", {})
        if "httpHeaderAuth" in creds:
            if github_cred_id:
                creds["httpHeaderAuth"]["id"] = github_cred_id
                creds["httpHeaderAuth"]["name"] = "GitHub Token"
            else:
                # Remove credential, add auth header directly
                del node["credentials"]
                params = node["parameters"]
                params["authentication"] = "genericCredentialType"
                params["genericAuthType"] = "httpHeaderAuth"
                # Add Authorization header
                existing_headers = params.get("headerParameters", {}).get("parameters", [])
                existing_headers.append({"name": "Authorization", "value": f"Bearer {GITHUB_TOKEN}"})
                params["headerParameters"] = {"parameters": existing_headers}

    # Create workflow
    print("\nCreating Git Activity Tracker workflow...")
    r = requests.post(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, json=workflow)

    if r.status_code in (200, 201):
        wf = r.json()
        wf_id = wf["id"]
        print(f"  Created: {wf_id}")

        # Activate
        r2 = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS)
        if r2.status_code == 200:
            print(f"  Activated!")
        else:
            print(f"  Activation: {r2.status_code}")

        # Verify
        r3 = requests.get(f"{N8N_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
        wf_data = r3.json()
        print(f"\n  Name: {wf_data['name']}")
        print(f"  Active: {wf_data['active']}")
        print(f"  Nodes: {len(wf_data['nodes'])}")
        for n in wf_data["nodes"]:
            c = n.get("credentials", {})
            c_info = ""
            if c:
                c_info = " — " + ", ".join(f"{k}={v['id']}" for k,v in c.items())
            print(f"    - {n['name']}{c_info}")

        print(f"\n  Workflow ID: {wf_id}")
        return wf_id
    else:
        print(f"  Error: {r.status_code}")
        print(f"  {r.text[:500]}")
        return None


if __name__ == "__main__":
    main()
