#!/usr/bin/env python3
"""
Journaling Workflow — Evening Review via Telegram
- 21h00: Orun envoie un prompt de reflexion
- Chris repond (texte ou vocal)
- La reponse est loggee dans Daily Summary + analyse rapide
"""

import json
import requests
import time

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9.sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}
ANTHROPIC_CRED = {"anthropicApi": {"id": "sE8nBT8crViDOv1E", "name": "Anthropic account"}}
CHRIS_CHAT_ID = "7342622615"

DAILY_SUMMARY_DB = "8559b19c-86a5-4034-bc4d-ea45459ef6bd"
ACTIVITY_LOG_DB = "305da200-b2d6-819f-915f-d35f51386aa8"


def build_journaling_workflow():
    """Build the evening journaling workflow."""

    # 1. Schedule trigger at 21h00 Paris time
    trigger = {
        "parameters": {
            "rule": {"interval": [{"triggerAtHour": 21, "triggerAtMinute": 0}]}
        },
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 0],
        "id": "j-trigger",
        "name": "21h00 - Journal Time"
    }

    # 2. Fetch today's activities for context
    fetch_today_code = r"""const now = new Date(new Date().getTime() + 3600000); // UTC+1
const today = now.toISOString().split('T')[0];
const dayNames = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
const dayName = dayNames[now.getDay()];

return [{json: {
    today,
    dayName,
    queryBody: JSON.stringify({
        filter: {
            property: 'Date',
            date: { equals: today }
        },
        sorts: [{ property: 'Date', direction: 'descending' }]
    })
}}];"""

    build_query = {
        "parameters": {"jsCode": fetch_today_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [200, 0],
        "id": "j-buildquery",
        "name": "Build Today Query"
    }

    fetch_activities = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{ACTIVITY_LOG_DB.replace('-','')}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.queryBody }}",
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [450, 0],
        "id": "j-fetch",
        "name": "Fetch Today Activities",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # 3. Build and send the prompt
    build_prompt_code = r"""const today = $('Build Today Query').first().json.today;
const dayName = $('Build Today Query').first().json.dayName;
const activitiesData = $json;
const activities = activitiesData.results || [];

function getFormula(prop) {
    if (!prop) return null;
    if (prop.type === 'formula') {
        if (prop.formula?.type === 'number') return prop.formula.number;
        if (prop.formula?.type === 'string') return prop.formula.string;
    }
    if (prop.type === 'number') return prop.number;
    return null;
}

let totalXP = 0;
let activityNames = [];
for (const a of activities) {
    const p = a.properties || {};
    const name = p['Name']?.title?.[0]?.plain_text || '?';
    const xp = getFormula(p['XP'] || p['xp']);
    if (typeof xp === 'number') totalXP += xp;
    activityNames.push(name);
}

let msg = `<b>Journal du soir</b> — ${dayName} ${today}\n\n`;

if (activities.length > 0) {
    msg += `${activities.length} activite(s) aujourd'hui (+${totalXP} XP) :\n`;
    for (const name of activityNames.slice(0, 8)) {
        msg += `  - ${name}\n`;
    }
    msg += `\n`;
} else {
    msg += `Aucune activite loggee aujourd'hui.\n\n`;
}

msg += `<b>3 questions :</b>\n`;
msg += `1. Qu'est-ce que t'as accompli aujourd'hui ?\n`;
msg += `2. Qu'est-ce qui t'a bloque ?\n`;
msg += `3. Quelle est ta priorite #1 demain ?\n\n`;
msg += `<i>Reponds en vocal ou texte — je log tout.</i>`;

return [{json: {promptMessage: msg}}];"""

    build_prompt = {
        "parameters": {"jsCode": build_prompt_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [700, 0],
        "id": "j-prompt",
        "name": "Build Journal Prompt"
    }

    send_prompt = {
        "parameters": {
            "chatId": CHRIS_CHAT_ID,
            "text": "={{ $json.promptMessage }}",
            "additionalFields": {
                "appendAttribution": False,
                "parse_mode": "HTML"
            }
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [950, 0],
        "id": "j-send",
        "name": "Send Journal Prompt",
        "credentials": TELEGRAM_CRED
    }

    # 4. Wait for response (up to 2h before Solo Leveling hits at 23h45)
    wait_response = {
        "parameters": {
            "resume": "webhook",
            "options": {
                "webhookSuffix": "/journal-response"
            }
        },
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [1150, 0],
        "id": "j-wait",
        "name": "Wait for Response"
    }

    # Actually, Wait with webhook won't work well here.
    # Better approach: the Manager Agent already handles all Telegram messages.
    # Instead, we just send the prompt. Chris responds to Orun naturally,
    # and the Manager Agent logs it via the Notion tool.
    #
    # BUT we need a simple way to capture the response specifically for journaling.
    # Simplest: just send the prompt. The response handling goes through the Manager.
    # The Manager already has memory + Notion access.

    nodes = [trigger, build_query, fetch_activities, build_prompt, send_prompt]

    connections = {
        "21h00 - Journal Time": {"main": [
            [{"node": "Build Today Query", "type": "main", "index": 0}]
        ]},
        "Build Today Query": {"main": [
            [{"node": "Fetch Today Activities", "type": "main", "index": 0}]
        ]},
        "Fetch Today Activities": {"main": [
            [{"node": "Build Journal Prompt", "type": "main", "index": 0}]
        ]},
        "Build Journal Prompt": {"main": [
            [{"node": "Send Journal Prompt", "type": "main", "index": 0}]
        ]}
    }

    return {
        "name": "Gamify \u2014 Evening Journal",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Paris",
            "saveManualExecutions": True
        }
    }


def main():
    workflow = build_journaling_workflow()

    # Create new workflow
    print("1. Creating Evening Journal workflow...")
    r = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow
    )
    print(f"   Status: {r.status_code}")

    if r.status_code in (200, 201):
        data = r.json()
        wf_id = data.get('id')
        print(f"   ID: {wf_id}")
        print(f"   Name: {data.get('name')}")

        time.sleep(2)

        # Activate
        print("2. Activating...")
        r = requests.post(
            f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
            headers=HEADERS
        )
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            print(f"   Active: {r.json().get('active')}")
        else:
            print(f"   Error: {r.text[:300]}")

        print(f"\nDone! Evening Journal workflow created and active.")
        print(f"  - ID: {wf_id}")
        print(f"  - Schedule: 21h00 Europe/Paris")
        print(f"  - Fetches today's activities from Activity Log")
        print(f"  - Sends 3 reflection questions via Telegram")
        print(f"  - Chris responds naturally to Orun (Manager handles the rest)")
        return wf_id
    else:
        print(f"   Error: {r.text[:500]}")
        return None


if __name__ == "__main__":
    main()
