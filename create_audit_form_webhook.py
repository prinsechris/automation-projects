#!/usr/bin/env python3
"""Create n8n workflow: Audit Form Webhook.

Receives form data from adaptive-logic.fr -> Creates prospect in Pipeline Prospects
-> Sends Telegram notification with lead details.

Webhook: POST /webhook/audit-form
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

TELEGRAM_CHAT_ID = "7342622615"
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}

PIPELINE_DB_ID = "c36269c4-df76-4c8a-9ac2-0085724a8573"

SECTEUR_TO_SERVICE = {
    "restaurant": "Review Autopilot",
    "commerce": "Review Autopilot",
    "artisan": "Autre",
    "sante": "Review Autopilot",
    "immobilier": "Client Magnet",
    "services": "Consulting n8n",
    "autre": "Autre",
}

workflow = {
    "name": "Audit Form Webhook — Site adaptive-logic.fr",
    "nodes": [
        {
            "id": "webhook",
            "name": "Webhook Audit Form",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [250, 300],
            "webhookId": "audit-form",
            "parameters": {
                "path": "audit-form",
                "httpMethod": "POST",
                "responseMode": "responseNode",
                "options": {
                    "allowedOrigins": "https://adaptive-logic.fr"
                }
            },
        },
        {
            "id": "respond",
            "name": "Respond OK",
            "type": "n8n-nodes-base.respondToWebhook",
            "typeVersion": 1.1,
            "position": [450, 300],
            "parameters": {
                "respondWith": "json",
                "responseBody": '={"status": "ok", "message": "Merci, votre audit sera envoye sous 24h."}',
            },
        },
        {
            "id": "set-fields",
            "name": "Prepare Fields",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [650, 300],
            "parameters": {
                "mode": "manual",
                "duplicateItem": False,
                "assignments": {
                    "assignments": [
                        {
                            "id": "nom",
                            "name": "nom",
                            "value": "={{ $json.body.nom }}",
                            "type": "string",
                        },
                        {
                            "id": "email",
                            "name": "email",
                            "value": "={{ $json.body.email }}",
                            "type": "string",
                        },
                        {
                            "id": "telephone",
                            "name": "telephone",
                            "value": "={{ $json.body.telephone || '' }}",
                            "type": "string",
                        },
                        {
                            "id": "secteur",
                            "name": "secteur",
                            "value": "={{ $json.body.secteur }}",
                            "type": "string",
                        },
                        {
                            "id": "equipe",
                            "name": "equipe",
                            "value": "={{ $json.body.equipe || '' }}",
                            "type": "string",
                        },
                        {
                            "id": "taches",
                            "name": "taches",
                            "value": "={{ $json.body.taches }}",
                            "type": "string",
                        },
                        {
                            "id": "heures",
                            "name": "heures",
                            "value": "={{ $json.body.heures || '' }}",
                            "type": "string",
                        },
                        {
                            "id": "details",
                            "name": "details",
                            "value": "={{ $json.body.details || '' }}",
                            "type": "string",
                        },
                        {
                            "id": "date_today",
                            "name": "date_today",
                            "value": "={{ $now.toISODate() }}",
                            "type": "string",
                        },
                    ]
                },
            },
        },
        {
            "id": "calc-score",
            "name": "Calculate Lead Score",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [850, 300],
            "parameters": {
                "jsCode": """
const item = $input.first().json;
let score = 30; // base score for filling the form

// Heures par semaine = plus de douleur = meilleur lead
const heuresMap = {'1-3': 5, '3-5': 10, '5-10': 20, '10+': 30};
score += heuresMap[item.heures] || 0;

// Nombre de taches cochees
const tachesCount = item.taches ? item.taches.split(', ').length : 0;
score += tachesCount * 5;

// Telephone fourni = plus engage
if (item.telephone && item.telephone.trim()) score += 10;

// Details fournis = plus engage
if (item.details && item.details.trim().length > 20) score += 5;

// Secteur mapping
const secteurMap = {
  'restaurant': 'Review Autopilot',
  'commerce': 'Review Autopilot',
  'artisan': 'Autre',
  'sante': 'Review Autopilot',
  'immobilier': 'Client Magnet',
  'services': 'Consulting n8n',
  'autre': 'Autre'
};

// Notes pour Notion
const notes = [];
notes.push('Source: Site web adaptive-logic.fr');
notes.push('Secteur: ' + item.secteur);
notes.push('Equipe: ' + item.equipe);
notes.push('Taches a automatiser: ' + item.taches);
notes.push('Heures/semaine: ' + item.heures);
if (item.details) notes.push('Details: ' + item.details);

return [{json: {
  ...item,
  lead_score: Math.min(score, 100),
  service: secteurMap[item.secteur] || 'Autre',
  notes: notes.join('\\n')
}}];
"""
            },
        },
        {
            "id": "notion-create",
            "name": "Create Prospect Notion",
            "type": "n8n-nodes-base.notion",
            "typeVersion": 2.2,
            "position": [1050, 300],
            "credentials": NOTION_CRED,
            "parameters": {
                "resource": "databasePage",
                "operation": "create",
                "databaseId": {
                    "__rl": True,
                    "value": PIPELINE_DB_ID,
                    "mode": "id",
                },
                "propertiesUi": {
                    "propertyValues": [
                        {
                            "key": "Nom|title",
                            "title": "={{ $json.nom }}",
                        },
                        {
                            "key": "Email|email",
                            "emailValue": "={{ $json.email }}",
                        },
                        {
                            "key": "Telephone|phone_number",
                            "phoneValue": "={{ $json.telephone }}",
                        },
                        {
                            "key": "Status|select",
                            "selectValue": "A contacter",
                        },
                        {
                            "key": "Canal|select",
                            "selectValue": "Local Avignon",
                        },
                        {
                            "key": "Service|select",
                            "selectValue": "={{ $json.service }}",
                        },
                        {
                            "key": "Lead Score|number",
                            "numberValue": "={{ $json.lead_score }}",
                        },
                        {
                            "key": "Notes|rich_text",
                            "textContent": "={{ $json.notes }}",
                        },
                        {
                            "key": "Date Contact|date",
                            "date": "={{ $json.date_today }}",
                        },
                    ]
                },
            },
        },
        {
            "id": "telegram-notif",
            "name": "Telegram Notification",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [1250, 300],
            "credentials": TELEGRAM_CRED,
            "parameters": {
                "chatId": TELEGRAM_CHAT_ID,
                "text": '=🚨 *NOUVEAU LEAD — Site Web*\n\n👤 *{{ $json.nom }}*\n📧 {{ $json.email }}\n📱 {{ $json.telephone || "Non fourni" }}\n\n🏢 Secteur: {{ $json.secteur }}\n👥 Equipe: {{ $json.equipe }}\n⏰ Heures/sem sur taches: {{ $json.heures }}\n📋 Taches: {{ $json.taches }}\n💡 Details: {{ $json.details || "Aucun" }}\n\n📊 Lead Score: {{ $json.lead_score }}/100\n🎯 Service suggere: {{ $json.service }}\n\n➡️ Prospect cree dans Pipeline Prospects',
                "additionalFields": {
                    "parse_mode": "Markdown",
                },
            },
        },
    ],
    "connections": {
        "Webhook Audit Form": {
            "main": [
                [
                    {"node": "Respond OK", "type": "main", "index": 0},
                    {"node": "Prepare Fields", "type": "main", "index": 0},
                ]
            ]
        },
        "Respond OK": {"main": [[]]},
        "Prepare Fields": {
            "main": [
                [{"node": "Calculate Lead Score", "type": "main", "index": 0}]
            ]
        },
        "Calculate Lead Score": {
            "main": [
                [{"node": "Create Prospect Notion", "type": "main", "index": 0}]
            ]
        },
        "Create Prospect Notion": {
            "main": [
                [{"node": "Telegram Notification", "type": "main", "index": 0}]
            ]
        },
    },
    "settings": {
        "executionOrder": "v1",
    },
}


def main():
    # Create workflow
    print("Creating workflow...")
    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow,
    )
    if resp.status_code not in (200, 201):
        print(f"Error creating workflow: {resp.status_code}")
        print(resp.text)
        return

    wf = resp.json()
    wf_id = wf["id"]
    print(f"Workflow created: {wf_id}")

    # Activate workflow
    print("Activating workflow...")
    resp = requests.patch(
        f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS,
    )
    if resp.status_code == 200:
        print(f"Workflow activated!")
    else:
        print(f"Activation: {resp.status_code} — {resp.text}")

    print(f"\nWebhook URL: {N8N_URL}/webhook/audit-form")
    print("Done!")


if __name__ == "__main__":
    main()
