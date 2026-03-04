#!/usr/bin/env python3
"""Create n8n workflow: Email Prospection v2 — via Zoho SMTP.

Fixed version: Code node builds everything, passes data through cleanly.
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
SMTP_CRED = {"smtp": {"id": "LDNW2tM882i9Ir3R", "name": "Zoho SMTP"}}

PIPELINE_DB_ID = "c36269c4-df76-4c8a-9ac2-0085724a8573"

workflow = {
    "name": "Email Prospection v2 — Zoho SMTP",
    "nodes": [
        {
            "id": "trigger",
            "name": "Webhook Send Prospection",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [250, 300],
            "webhookId": "send-prospection",
            "parameters": {
                "path": "send-prospection",
                "httpMethod": "POST",
                "responseMode": "lastNode",
                "options": {},
            },
        },
        {
            "id": "notion-query",
            "name": "Get Prospects",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [450, 300],
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{PIPELINE_DB_ID}/query",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "notionApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Notion-Version", "value": "2022-06-28"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": json.dumps({
                    "filter": {
                        "and": [
                            {"property": "Status", "select": {"equals": "A contacter"}},
                            {"property": "Email", "email": {"is_not_empty": True}},
                        ]
                    }
                }),
                "options": {},
            },
            "credentials": NOTION_CRED,
        },
        {
            "id": "split",
            "name": "Split Prospects",
            "type": "n8n-nodes-base.splitOut",
            "typeVersion": 1,
            "position": [650, 300],
            "parameters": {
                "fieldToSplitOut": "results",
                "options": {},
            },
        },
        # Main Code node: builds email + Notion update body + all data
        {
            "id": "prepare-all",
            "name": "Prepare Email + Data",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [850, 300],
            "parameters": {
                "jsCode": r"""
const item = $input.first().json;
const props = item.properties || item;

function getProp(p, type) {
  if (!p) return '';
  switch(type) {
    case 'title': return p.title?.[0]?.plain_text || '';
    case 'email': return p.email || '';
    case 'phone': return p.phone_number || '';
    case 'select': return p.select?.name || '';
    case 'number': return p.number || 0;
    case 'rich_text': return p.rich_text?.[0]?.plain_text || '';
    default: return '';
  }
}

const nom = getProp(props.Nom, 'title');
const email = getProp(props.Email, 'email');
const leadScore = getProp(props['Lead Score'], 'number');
const notes = getProp(props.Notes, 'rich_text');
const pageId = item.id;

const isHotel = nom.toLowerCase().includes('hotel') || nom.toLowerCase().includes('hôtel');
const isRestaurant = nom.toLowerCase().includes('restaurant') || nom.toLowerCase().includes('cafe') || nom.toLowerCase().includes('café') || nom.toLowerCase().includes('fondues');

let subject = nom + ' — vos avis Google sont un levier inexploite';
let body = 'Bonjour,\n\nJe me permets de vous contacter car j\'ai analyse la fiche Google de ' + nom + '.\n\n';

if (isHotel) {
  body += 'Pour un hotel, les avis Google sont un facteur de decision majeur. Les voyageurs comparent systematiquement les notes et les reponses avant de reserver. Un etablissement qui repond a ses avis envoie un signal fort : "nous prenons soin de nos clients".\n\nLa plupart de vos avis restent sans reponse — c\'est une opportunite manquee, surtout que les avis negatifs non traites pesent lourd dans la decision des futurs clients.\n\n';
} else if (isRestaurant) {
  body += 'J\'ai remarque que la grande majorite de vos avis restent sans reponse. C\'est dommage, car ces avis sont un levier enorme pour attirer de nouveaux clients. Google favorise les etablissements qui repondent activement — ca ameliore votre classement local et ca montre aux futurs clients que vous etes a l\'ecoute.\n\nLe probleme, c\'est que repondre aux avis ca prend un temps fou. Et meme au quotidien, il faut y penser, trouver les mots, et ne pas faire de copier-coller generique.\n\n';
} else {
  body += 'J\'ai remarque que beaucoup de vos avis Google restent sans reponse. Les avis sont aujourd\'hui le premier reflexe des clients avant de choisir un prestataire — et un etablissement qui repond montre qu\'il est a l\'ecoute.\n\n';
}

body += 'C\'est pour ca que j\'ai cree Review Autopilot : une IA qui repond automatiquement a chaque nouvel avis Google, avec des reponses personnalisees et dans le ton de votre etablissement. Pas de reponses robotiques — chaque reponse est unique et adaptee au contenu de l\'avis.\n\nConcretement :\n- Reponse automatique a chaque nouvel avis (positif comme negatif)\n- Ton personnalise selon votre etablissement\n- Vous gardez le controle : validation avant publication si vous le souhaitez\n- Installation en moins d\'une journee\n\nJe suis base a Avignon, donc si ca vous interesse, je peux passer vous faire une demonstration rapide sur place.\n\nPlus d\'infos sur notre site : https://adaptive-logic.fr\n\nBonne continuation,\n\nChris\nAdaptive Logic — Automatisation IA pour commercants locaux\ncontact@adaptive-logic.fr\nhttps://adaptive-logic.fr';

// Build Notion update body as string
const notionBody = JSON.stringify({
  properties: {
    Status: { select: { name: "Email envoye" } }
  }
});

return [{json: {
  to: email,
  subject: subject,
  body: body,
  nom: nom,
  pageId: pageId,
  leadScore: leadScore,
  notionBody: notionBody,
  notionUrl: 'https://api.notion.com/v1/pages/' + pageId
}}];
"""
            },
        },
        # Send email
        {
            "id": "send-email",
            "name": "Send Email Zoho",
            "type": "n8n-nodes-base.emailSend",
            "typeVersion": 2.1,
            "position": [1050, 300],
            "parameters": {
                "fromEmail": "contact@adaptive-logic.fr",
                "toEmail": "={{ $json.to }}",
                "subject": "={{ $json.subject }}",
                "emailType": "text",
                "message": "={{ $json.body }}",
                "options": {
                    "replyTo": "contact@adaptive-logic.fr",
                },
            },
            "credentials": SMTP_CRED,
        },
        # Notion update — uses data from Prepare node
        {
            "id": "notion-update",
            "name": "Update Status Notion",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1250, 300],
            "parameters": {
                "method": "PATCH",
                "url": "={{ $('Prepare Email + Data').first().json.notionUrl }}",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "notionApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Notion-Version", "value": "2022-06-28"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ $('Prepare Email + Data').first().json.notionBody }}",
                "options": {},
            },
            "credentials": NOTION_CRED,
        },
        # Telegram notification
        {
            "id": "telegram",
            "name": "Telegram Recap",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [1450, 300],
            "credentials": TELEGRAM_CRED,
            "parameters": {
                "chatId": TELEGRAM_CHAT_ID,
                "text": "=📧 *Email envoye*\n\n👤 {{ $('Prepare Email + Data').first().json.nom }}\n📬 {{ $('Prepare Email + Data').first().json.to }}\n📊 Lead Score: {{ $('Prepare Email + Data').first().json.leadScore }}\n\n✅ Status mis a jour → Email envoye",
                "additionalFields": {
                    "parse_mode": "Markdown",
                },
            },
        },
    ],
    "connections": {
        "Webhook Send Prospection": {
            "main": [[{"node": "Get Prospects", "type": "main", "index": 0}]]
        },
        "Get Prospects": {
            "main": [[{"node": "Split Prospects", "type": "main", "index": 0}]]
        },
        "Split Prospects": {
            "main": [[{"node": "Prepare Email + Data", "type": "main", "index": 0}]]
        },
        "Prepare Email + Data": {
            "main": [[{"node": "Send Email Zoho", "type": "main", "index": 0}]]
        },
        "Send Email Zoho": {
            "main": [[{"node": "Update Status Notion", "type": "main", "index": 0}]]
        },
        "Update Status Notion": {
            "main": [[{"node": "Telegram Recap", "type": "main", "index": 0}]]
        },
    },
    "settings": {"executionOrder": "v1"},
}


def main():
    print("Creating workflow v2...")
    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow,
    )
    if resp.status_code not in (200, 201):
        print(f"Error: {resp.status_code}")
        print(resp.text)
        return

    wf = resp.json()
    wf_id = wf["id"]
    print(f"Workflow created: {wf_id}")

    print("Activating...")
    resp = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS)
    if resp.status_code == 200:
        print("Workflow activated!")
    else:
        print(f"Activation: {resp.status_code} — {resp.text}")

    print(f"\nWebhook: POST {N8N_URL}/webhook/send-prospection")


if __name__ == "__main__":
    main()
