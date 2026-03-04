#!/usr/bin/env python3
"""Deploy updated Beeminder Sync workflow with business + perso + habitudes goals."""

import json
import requests
import time

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = "***N8N_API_KEY***"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}
BEEMINDER_ID = "nnufUryOAW9Hy7KE"

NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TASKS_DB = "305da200-b2d6-8145-bc16-eaee02925a14"
ACTIVITY_LOG_DB = "305da200-b2d6-819f-915f-d35f51386aa8"
BEEMINDER_TOKEN = "28f1_C1a-W6ZPtA1joXN"
TELEGRAM_BOT = "8245723499:AAHdk-CSEBzrUDIYKEqn80DrzI5yoGq4YQQ"
CHAT_ID = "7342622615"

def build_workflow():
    trigger = {
        "parameters": {
            "rule": {"interval": [{"field": "cronExpression", "expression": "0 22 * * *"}]}
        },
        "id": "schedule-beeminder",
        "name": "CRON 22h",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 300]
    }

    date_context = {
        "parameters": {
            "jsCode": """const now = new Date();
const cetFormatter = new Intl.DateTimeFormat('fr-FR', {
  timeZone: 'Europe/Paris', year: 'numeric', month: '2-digit', day: '2-digit', hour12: false
});
const parts = cetFormatter.formatToParts(now);
const year = parts.find(p => p.type === 'year').value;
const month = parts.find(p => p.type === 'month').value;
const day = parts.find(p => p.type === 'day').value;
const today = `${year}-${month}-${day}`;
const cetMidnight = new Date(`${today}T00:00:00+01:00`);
const timestamp = Math.floor(cetMidnight.getTime() / 1000);
return [{ json: { today, timestamp, iso: now.toISOString() } }];"""
        },
        "id": "date-context",
        "name": "Date Context",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [260, 300]
    }

    # --- BUSINESS TASKS ---
    query_business = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{TASKS_DB}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ filter: { and: [ { property: "Status", status: { equals: "Complete" } }, { property: "Completed On", date: { equals: $json.today } }, { property: "Type", select: { does_not_equal: "Project" } }, { or: [ { property: "Category", select: { equals: "\\ud83d\\udcbc Business" } }, { property: "Category", select: { equals: "\\ud83e\\udd16 Automatisation" } } ] } ] }, page_size: 50 }) }}',
            "options": {}
        },
        "id": "query-business",
        "name": "Query Business Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [560, 100],
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    process_business = {
        "parameters": {
            "jsCode": """const queryResult = $('Query Business Tasks').first().json;
const results = queryResult.results || [];
const count = Array.isArray(results) ? results.length : 0;
const names = [];
if (Array.isArray(results)) {
  for (const page of results) {
    const props = page.properties || {};
    const titleArr = (props['Name'] || {}).title || [];
    const name = titleArr.map(t => t.plain_text || '').join('') || 'Sans nom';
    names.push(name);
  }
}
const ctx = $('Date Context').first().json;
return [{ json: {
  value: count, timestamp: ctx.timestamp,
  comment: `Auto-sync: ${count} tache(s) business le ${ctx.today}` + (names.length > 0 ? ' — ' + names.join(', ') : ''),
  label: 'Business', names
} }];"""
        },
        "id": "process-business",
        "name": "Process Business",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [840, 100]
    }

    beeminder_business = {
        "parameters": {
            "method": "POST",
            "url": "https://www.beeminder.com/api/v1/users/prinsechris/goals/business/datapoints.json",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({{ auth_token: '{BEEMINDER_TOKEN}', value: $json.value, timestamp: $json.timestamp, comment: $json.comment }}) }}}}",
            "options": {}
        },
        "id": "beeminder-business",
        "name": "Beeminder Business",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1120, 100],
        "onError": "continueRegularOutput"
    }

    # --- PERSO TASKS ---
    query_perso = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{TASKS_DB}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ filter: { and: [ { property: "Status", status: { equals: "Complete" } }, { property: "Completed On", date: { equals: $json.today } }, { property: "Type", select: { does_not_equal: "Project" } }, { or: [ { property: "Category", select: { equals: "\\ud83c\\udfe0 Perso" } }, { property: "Category", select: { equals: "\\ud83c\\udfa8 Creative" } } ] } ] }, page_size: 50 }) }}',
            "options": {}
        },
        "id": "query-perso",
        "name": "Query Perso Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [560, 300],
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    process_perso = {
        "parameters": {
            "jsCode": """const queryResult = $('Query Perso Tasks').first().json;
const results = queryResult.results || [];
const count = Array.isArray(results) ? results.length : 0;
const names = [];
if (Array.isArray(results)) {
  for (const page of results) {
    const props = page.properties || {};
    const titleArr = (props['Name'] || {}).title || [];
    const name = titleArr.map(t => t.plain_text || '').join('') || 'Sans nom';
    names.push(name);
  }
}
const ctx = $('Date Context').first().json;
return [{ json: {
  value: count, timestamp: ctx.timestamp,
  comment: `Auto-sync: ${count} tache(s) perso le ${ctx.today}` + (names.length > 0 ? ' — ' + names.join(', ') : ''),
  label: 'Perso', names
} }];"""
        },
        "id": "process-perso",
        "name": "Process Perso",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [840, 300]
    }

    beeminder_perso = {
        "parameters": {
            "method": "POST",
            "url": "https://www.beeminder.com/api/v1/users/prinsechris/goals/perso/datapoints.json",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({{ auth_token: '{BEEMINDER_TOKEN}', value: $json.value, timestamp: $json.timestamp, comment: $json.comment }}) }}}}",
            "options": {}
        },
        "id": "beeminder-perso",
        "name": "Beeminder Perso",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1120, 300],
        "onError": "continueRegularOutput"
    }

    # --- HABITUDES (kept as is) ---
    query_judgment = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{ACTIVITY_LOG_DB}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ filter: { and: [ { property: "Date", date: { equals: $json.today } } ] }, page_size: 100 }) }}',
            "options": {}
        },
        "id": "query-judgment",
        "name": "Query Daily Judgment",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [560, 500],
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    process_judgment = {
        "parameters": {
            "jsCode": """const queryResult = $('Query Daily Judgment').first().json;
const results = queryResult.results || [];
let doucheFroide = false;
let journaling = false;
const details = [];
if (Array.isArray(results)) {
  for (const page of results) {
    const props = page.properties || {};
    const nameProp = props['Name'] || props['name'] || {};
    const titleArr = nameProp.title || [];
    const title = titleArr.map(t => t.plain_text || '').join('').toLowerCase();
    if (title.includes('douche') || title.includes('cold') || title.includes('froide')) {
      doucheFroide = true; details.push('Douche Froide');
    }
    if (title.includes('journal') || title.includes('journaling')) {
      journaling = true; details.push('Journaling');
    }
  }
}
// Count only these 2 habits (push-ups sent separately by the app)
const score = (doucheFroide ? 1 : 0) + (journaling ? 1 : 0);
const ctx = $('Date Context').first().json;
return [{ json: {
  value: score, timestamp: ctx.timestamp,
  comment: `Auto-sync: ${details.length > 0 ? details.join(' + ') : 'aucune habitude detectee'} (${score}/2 via Notion) le ${ctx.today}`,
  label: 'Habitudes', doucheFroide, journaling, details
} }];"""
        },
        "id": "process-judgment",
        "name": "Process Judgment",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [840, 500]
    }

    beeminder_habitudes = {
        "parameters": {
            "method": "POST",
            "url": "https://www.beeminder.com/api/v1/users/prinsechris/goals/habitudes/datapoints.json",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({{ auth_token: '{BEEMINDER_TOKEN}', value: $json.value, timestamp: $json.timestamp, comment: $json.comment }}) }}}}",
            "options": {}
        },
        "id": "beeminder-habitudes",
        "name": "Beeminder Habitudes",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1120, 500],
        "onError": "continueRegularOutput"
    }

    # --- WAIT NODES (to serialize Build Recap inputs) ---
    wait_biz = {
        "parameters": {"amount": 1, "unit": "seconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [1320, 100],
        "id": "wait-biz",
        "name": "Wait Biz"
    }

    wait_perso = {
        "parameters": {"amount": 2, "unit": "seconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [1320, 300],
        "id": "wait-perso",
        "name": "Wait Perso"
    }

    # --- BUILD RECAP ---
    build_recap = {
        "parameters": {
            "jsCode": f"""let bizData, persoData, habData;
try {{ bizData = $('Process Business').first().json; }} catch(e) {{ bizData = {{ value: '?', names: [] }}; }}
try {{ persoData = $('Process Perso').first().json; }} catch(e) {{ persoData = {{ value: '?', names: [] }}; }}
try {{ habData = $('Process Judgment').first().json; }} catch(e) {{ habData = {{ value: '?', doucheFroide: false, journaling: false }}; }}

let errors = [];
try {{ const r = $('Beeminder Business').first().json; if (r.errors) errors.push('Business: ' + JSON.stringify(r.errors)); }} catch(e) {{}}
try {{ const r = $('Beeminder Perso').first().json; if (r.errors) errors.push('Perso: ' + JSON.stringify(r.errors)); }} catch(e) {{}}
try {{ const r = $('Beeminder Habitudes').first().json; if (r.errors) errors.push('Habitudes: ' + JSON.stringify(r.errors)); }} catch(e) {{}}

const ctx = $('Date Context').first().json;

const bizIcon = bizData.value >= 3 ? 'OK' : (bizData.value > 0 ? 'PARTIEL' : 'MANQUE');
const persoIcon = persoData.value >= 3 ? 'OK' : (persoData.value > 0 ? 'PARTIEL' : 'MANQUE');
const habIcon = habData.value >= 2 ? 'OK' : (habData.value > 0 ? 'PARTIEL' : 'MANQUE');

let msg = `<b>Beeminder Sync — ${{ctx.today}}</b>\\n\\n`;
msg += `<b>Business:</b> ${{bizData.value}} tache(s) [${{bizIcon}}]\\n`;
msg += `  Objectif: 3/jour | Pledge: $5\\n`;
if (bizData.names && bizData.names.length > 0) msg += `  Completees: ${{bizData.names.join(', ')}}\\n`;
msg += `\\n<b>Perso:</b> ${{persoData.value}} tache(s) [${{persoIcon}}]\\n`;
msg += `  Objectif: 3/jour | Pledge: $5\\n`;
if (persoData.names && persoData.names.length > 0) msg += `  Completees: ${{persoData.names.join(', ')}}\\n`;
msg += `\\n<b>Habitudes (Notion):</b> ${{habData.value}}/2 [${{habIcon}}]\\n`;
msg += `  Douche Froide: ${{habData.doucheFroide ? 'OK' : 'NON'}}\\n`;
msg += `  Journaling: ${{habData.journaling ? 'OK' : 'NON'}}\\n`;
msg += `  (Pompes envoyees separement par l app)\\n`;

if (errors.length > 0) {{
  msg += `\\n<b>Erreurs Beeminder:</b>\\n`;
  for (const err of errors) msg += `  ${{err}}\\n`;
}}
msg += `\\nbeeminder.com/prinsechris`;
return [{{ json: {{ message: msg }} }}];"""
        },
        "id": "build-recap",
        "name": "Build Recap",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1520, 300]
    }

    send_telegram = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({{ chat_id: '{CHAT_ID}', text: $json.message, parse_mode: 'HTML' }}) }}}}",
            "options": {}
        },
        "id": "send-telegram",
        "name": "Send Telegram Recap",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1780, 300],
        "onError": "continueRegularOutput"
    }

    nodes = [
        trigger, date_context,
        query_business, process_business, beeminder_business, wait_biz,
        query_perso, process_perso, beeminder_perso, wait_perso,
        query_judgment, process_judgment, beeminder_habitudes,
        build_recap, send_telegram
    ]

    connections = {
        "CRON 22h": {"main": [[{"node": "Date Context", "type": "main", "index": 0}]]},
        "Date Context": {"main": [[
            {"node": "Query Business Tasks", "type": "main", "index": 0},
            {"node": "Query Perso Tasks", "type": "main", "index": 0},
            {"node": "Query Daily Judgment", "type": "main", "index": 0}
        ]]},
        "Query Business Tasks": {"main": [[{"node": "Process Business", "type": "main", "index": 0}]]},
        "Process Business": {"main": [[{"node": "Beeminder Business", "type": "main", "index": 0}]]},
        "Beeminder Business": {"main": [[{"node": "Wait Biz", "type": "main", "index": 0}]]},
        "Wait Biz": {"main": [[{"node": "Build Recap", "type": "main", "index": 0}]]},
        "Query Perso Tasks": {"main": [[{"node": "Process Perso", "type": "main", "index": 0}]]},
        "Process Perso": {"main": [[{"node": "Beeminder Perso", "type": "main", "index": 0}]]},
        "Beeminder Perso": {"main": [[{"node": "Wait Perso", "type": "main", "index": 0}]]},
        "Wait Perso": {"main": [[{"node": "Build Recap", "type": "main", "index": 0}]]},
        "Query Daily Judgment": {"main": [[{"node": "Process Judgment", "type": "main", "index": 0}]]},
        "Process Judgment": {"main": [[{"node": "Beeminder Habitudes", "type": "main", "index": 0}]]},
        "Beeminder Habitudes": {"main": [[{"node": "Build Recap", "type": "main", "index": 0}]]},
        "Build Recap": {"main": [[{"node": "Send Telegram Recap", "type": "main", "index": 0}]]}
    }

    return {
        "name": "Beeminder Sync",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris"}
    }


def main():
    print("Deploying Beeminder Sync v2...")

    wf = build_workflow()

    # Deactivate
    print("  1. Deactivating...")
    r = requests.post(f"{N8N_URL}/api/v1/workflows/{BEEMINDER_ID}/deactivate", headers=HEADERS)
    print(f"     Status: {r.status_code}")
    time.sleep(1)

    # Update
    print("  2. Updating...")
    allowed = ['name', 'nodes', 'connections', 'settings', 'staticData']
    body = {k: wf[k] for k in allowed if k in wf}
    r = requests.put(f"{N8N_URL}/api/v1/workflows/{BEEMINDER_ID}", headers=HEADERS, json=body)
    print(f"     Status: {r.status_code}")
    if r.status_code != 200:
        print(f"     Error: {r.text[:500]}")
        return
    time.sleep(1)

    # Activate
    print("  3. Activating...")
    r = requests.post(f"{N8N_URL}/api/v1/workflows/{BEEMINDER_ID}/activate", headers=HEADERS)
    print(f"     Status: {r.status_code}")
    if r.status_code == 200:
        print(f"     Active: {r.json().get('active')}")

    print("\nDone! Beeminder Sync v2 deployed:")
    print("  - Business: 3 taches/jour (Category Business + Automatisation)")
    print("  - Perso: 3 taches/jour (Category Perso + Creative)")
    print("  - Habitudes: 3/jour (Douche Froide + Journaling + Pompes via app)")


if __name__ == "__main__":
    main()
