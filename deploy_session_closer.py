#!/usr/bin/env python3
"""Update Session Closer with evolved features + Telegram split."""
import json, requests

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_KEY = "***N8N_API_KEY***"
HEADERS = {"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"}
WF_ID = "QCI4C4b4bqKtZkCm"
CHAT_ID = "7342622615"
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}

parse_session_code = r"""const body = $input.first().json.body;

// Detect auto-calls from Git Activity Tracker (session_number=0)
const isAuto = body.session_number === 0 || body.session_number === '0';

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
  git_pushed: body.git_pushed || false,
  isAuto: isAuto
};

// Calculate XP/Gold based on session work
const baseXP = Math.max(session.duration_hours * 50, 25);
const taskBonus = session.tasks_completed.length * 15;
session.xp = isAuto ? 0 : (baseXP + taskBonus);
session.gold = isAuto ? 0 : Math.round(session.xp * 0.4);

let recap = '';
if (isAuto) {
  if (session.highlights.length === 0) {
    return [{json: {...session, recap: '', skipTelegram: true}}];
  }
  recap = `\ud83d\udd04 *Auto-report ${session.date}*\n`;
  recap += session.summary + '\n\n';
  const urgent = session.highlights.filter(h => h.startsWith('EN RETARD'));
  if (urgent.length > 0) {
    recap += `*\u26a0\ufe0f ${urgent.length} tache(s) en retard :*\n`;
    for (const h of urgent.slice(0, 5)) { recap += `\u2022 ${h}\n`; }
    if (urgent.length > 5) recap += `... et ${urgent.length - 5} autres\n`;
  }
  // Add non-urgent highlights (limit 5)
  const nonUrgent = session.highlights.filter(h => !h.startsWith('EN RETARD'));
  if (nonUrgent.length > 0) {
    for (const h of nonUrgent.slice(0, 5)) { recap += `\u2022 ${h}\n`; }
  }
} else {
  recap = `\ud83d\udccb *Session ${session.session_number} \u2014 ${session.date}*\n`;
  recap += `${session.summary}\n\n`;
  if (session.highlights.length > 0) {
    recap += `*Highlights :*\n`;
    for (const h of session.highlights) { recap += `\u2022 ${h}\n`; }
    recap += `\n`;
  }
  recap += `\u2705 ${session.tasks_completed.length} taches completees\n`;
  recap += `\ud83d\udd04 ${session.tasks_started.length} taches demarrees\n`;
  recap += `\ud83d\udcc1 ${session.files_changed} fichiers modifies\n`;
  recap += `\u2699\ufe0f ${session.workflows_modified} workflows n8n modifies\n`;
  recap += `\u23f1\ufe0f ~${session.duration_hours}h de travail\n`;
  recap += `\u2728 +${session.xp} XP | +${session.gold} Gold\n`;
  if (session.git_pushed) { recap += `\n\u2705 Session log pushe sur GitHub`; }
}

return [{json: {...session, recap, skipTelegram: false}}];
"""

build_activity_body_code = r"""const session = $('Parse Session').first().json;

if (session.isAuto) {
  return [{json: {skip: true, body: '{}'}}];
}

const body = {
  parent: {database_id: "305da200-b2d6-819f-915f-d35f51386aa8"},
  properties: {
    Name: {title: [{text: {content: "Session " + session.session_number + " \u2014 " + session.summary.substring(0, 80)}}]},
    Date: {date: {start: session.date}},
    XP: {number: session.xp || 25},
    Gold: {number: session.gold || 10}
  }
};

if (session.tasks_completed && session.tasks_completed.length > 0) {
  body.properties.Quests = {
    relation: session.tasks_completed.map(id => ({id}))
  };
}

return [{json: {body: JSON.stringify(body), skip: false}}];
"""

split_telegram_code = """// Split long messages for Telegram (4096 char limit)
const fullMsg = $('Parse Session').first().json.recap;
const MAX = 4000;

if (!fullMsg || fullMsg.length <= MAX) {
    return [{json: {text: fullMsg || ''}}];
}

const sections = fullMsg.split(/\\n\\n/);
const parts = [];
let current = '';

for (const section of sections) {
    if (current.length + section.length + 2 > MAX) {
        if (current) parts.push(current.trim());
        if (section.length > MAX) {
            const lines = section.split('\\n');
            let chunk = '';
            for (const line of lines) {
                if (chunk.length + line.length + 1 > MAX) {
                    if (chunk) parts.push(chunk.trim());
                    chunk = line;
                } else {
                    chunk += (chunk ? '\\n' : '') + line;
                }
            }
            current = chunk;
        } else {
            current = section;
        }
    } else {
        current += (current ? '\\n\\n' : '') + section;
    }
}
if (current) parts.push(current.trim());

// Merge small consecutive parts to avoid tiny messages
const merged = [];
for (const part of parts) {
    if (merged.length > 0 && merged[merged.length - 1].length + part.length + 2 <= MAX) {
        merged[merged.length - 1] += '\\n\\n' + part;
    } else {
        merged.push(part);
    }
}

// Ensure first part isn't tiny (merge into second if < 200 chars)
if (merged.length > 1 && merged[0].length < 200) {
    merged[1] = merged[0] + '\\n\\n' + merged[1];
    merged.shift();
}

if (merged.length === 1) return [{json: {text: merged[0]}}];
return merged.map((p, i) => ({json: {text: '[' + (i+1) + '/' + merged.length + ']\\n' + p}}));
"""

workflow = {
    "name": "Session Closer",
    "nodes": [
        {"parameters": {"httpMethod": "POST", "path": "session-close", "responseMode": "responseNode", "options": {}},
         "id": "webhook-1", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0], "webhookId": "session-close-001"},
        {"parameters": {"jsCode": parse_session_code}, "id": "parse-1", "name": "Parse Session", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [220, 0]},
        {"parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": ""}, "combinator": "or", "conditions": [
            {"id": "cond-1", "leftValue": "={{ $json.isAuto }}", "rightValue": False, "operator": {"type": "boolean", "operation": "equals"}},
            {"id": "cond-2", "leftValue": "={{ $json.highlights.length }}", "rightValue": 0, "operator": {"type": "number", "operation": "gt"}}
        ]}}, "id": "is-real-session", "name": "Is Real Session?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [440, 0]},
        {"parameters": {"jsCode": "const session = $input.first().json;\nconst tasks = session.tasks_completed || [];\nif (tasks.length === 0) return [{json: {skip: true}}];\nreturn tasks.map(taskId => ({json: {taskId, action: 'complete'}}));"}, 
         "id": "split-completed-1", "name": "Split Completed", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [660, -200]},
        {"parameters": {"method": "PATCH", "url": "=https://api.notion.com/v1/pages/{{ $json.taskId }}", "authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi",
         "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
         "sendBody": True, "specifyBody": "json", "jsonBody": '={\n  "properties": {\n    "Status": {"status": {"name": "Complete"}},\n    "Completed On": {"date": {"start": "{{ new Date().toISOString() }}"}}\n  }\n}', "options": {}},
         "id": "update-completed-1", "name": "Mark Complete", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [880, -200], "credentials": NOTION_CRED, "onError": "continueRegularOutput"},
        {"parameters": {"jsCode": "const session = $input.first().json;\nconst tasks = session.tasks_started || [];\nif (tasks.length === 0) return [{json: {skip: true}}];\nreturn tasks.map(taskId => ({json: {taskId, action: 'start'}}));"}, 
         "id": "split-started-1", "name": "Split Started", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [660, 0]},
        {"parameters": {"method": "PATCH", "url": "=https://api.notion.com/v1/pages/{{ $json.taskId }}", "authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi",
         "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
         "sendBody": True, "specifyBody": "json", "jsonBody": '={\n  "properties": {\n    "Status": {"status": {"name": "In Progress"}}\n  }\n}', "options": {}},
         "id": "update-started-1", "name": "Mark In Progress", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [880, 0], "credentials": NOTION_CRED, "onError": "continueRegularOutput"},
        {"parameters": {"jsCode": build_activity_body_code}, "id": "build-activity-body", "name": "Build Activity Body", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [660, 200]},
        {"parameters": {"method": "POST", "url": "https://api.notion.com/v1/pages", "authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi",
         "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
         "sendBody": True, "specifyBody": "json", "jsonBody": "={{ $json.body }}", "options": {}},
         "id": "activity-log-1", "name": "Activity Log Entry", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [880, 200], "credentials": NOTION_CRED, "onError": "continueRegularOutput"},
        {"parameters": {"jsCode": split_telegram_code}, "id": "split-telegram-1", "name": "Split for Telegram", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1100, 200]},
        {"parameters": {"chatId": CHAT_ID, "text": "={{ $json.text }}", "additionalFields": {"parse_mode": "Markdown"}},
         "id": "telegram-1", "name": "Telegram Recap", "type": "n8n-nodes-base.telegram", "typeVersion": 1.2, "position": [1320, 200], "credentials": TELEGRAM_CRED},
        {"parameters": {"respondWith": "json", "responseBody": "={{ JSON.stringify({status: 'ok', session: $('Parse Session').first().json.session_number, tasks_completed: $('Parse Session').first().json.tasks_completed.length, tasks_started: $('Parse Session').first().json.tasks_started.length}) }}"},
         "id": "response-1", "name": "Response", "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1.1, "position": [1540, 200]}
    ],
    "connections": {
        "Webhook": {"main": [[{"node": "Parse Session", "type": "main", "index": 0}]]},
        "Parse Session": {"main": [[{"node": "Is Real Session?", "type": "main", "index": 0}]]},
        "Is Real Session?": {"main": [
            [{"node": "Split Completed", "type": "main", "index": 0}, {"node": "Split Started", "type": "main", "index": 0}, {"node": "Build Activity Body", "type": "main", "index": 0}],
            [{"node": "Response", "type": "main", "index": 0}]
        ]},
        "Split Completed": {"main": [[{"node": "Mark Complete", "type": "main", "index": 0}]]},
        "Split Started": {"main": [[{"node": "Mark In Progress", "type": "main", "index": 0}]]},
        "Build Activity Body": {"main": [[{"node": "Activity Log Entry", "type": "main", "index": 0}]]},
        "Activity Log Entry": {"main": [[{"node": "Split for Telegram", "type": "main", "index": 0}]]},
        "Split for Telegram": {"main": [[{"node": "Telegram Recap", "type": "main", "index": 0}]]},
        "Telegram Recap": {"main": [[{"node": "Response", "type": "main", "index": 0}]]}
    },
    "settings": {"executionOrder": "v1", "callerPolicy": "workflowsFromSameOwner"}
}

# Deactivate, update, reactivate
print("Deactivating...")
requests.post(f"{N8N_URL}/api/v1/workflows/{WF_ID}/deactivate", headers=HEADERS)

print("Updating...")
r = requests.put(f"{N8N_URL}/api/v1/workflows/{WF_ID}", headers=HEADERS, json=workflow)
if r.ok:
    print(f"  Updated successfully! Nodes: {len(workflow['nodes'])}")
else:
    print(f"  ERROR: {r.status_code} - {r.text[:300]}")

print("Activating...")
r2 = requests.post(f"{N8N_URL}/api/v1/workflows/{WF_ID}/activate", headers=HEADERS)
print(f"  Active: {r2.json().get('active')}")

print(f"\nDone! Session Closer ID: {WF_ID}")
print(f"Webhook: {N8N_URL}/webhook/session-close")
