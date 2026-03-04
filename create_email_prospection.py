#!/usr/bin/env python3
"""Create n8n workflow: Email Prospection via Zoho SMTP.

Sends personalized prospection emails to Pipeline Prospects,
updates their status in Notion, and notifies via Telegram.
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

workflow = {
    "name": "Email Prospection — Zoho SMTP",
    "nodes": [
        # 1. Webhook trigger — POST /webhook/send-prospection
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
        # 2. Query Pipeline Prospects with status "A contacter" and email present
        {
            "id": "notion-query",
            "name": "Get Prospects A Contacter",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [450, 300],
            "parameters": {
                "method": "POST",
                "url": "https://api.notion.com/v1/databases/" + PIPELINE_DB_ID + "/query",
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
                            {
                                "property": "Status",
                                "select": {"equals": "A contacter"}
                            },
                            {
                                "property": "Email",
                                "email": {"is_not_empty": True}
                            }
                        ]
                    }
                }),
                "options": {},
            },
            "credentials": NOTION_CRED,
        },
        # 3. Split results into individual items
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
        # 4. Code node: build personalized email for each prospect
        {
            "id": "build-email",
            "name": "Build Email",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [850, 300],
            "parameters": {
                "jsCode": """
const item = $input.first().json;

// Extract prospect data from Notion properties
const props = item.properties || item;

// Helper to get property values
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
const telephone = getProp(props.Telephone, 'phone');
const service = getProp(props.Service, 'select');
const leadScore = getProp(props['Lead Score'], 'number');
const notes = getProp(props.Notes, 'rich_text');
const canal = getProp(props.Canal, 'select');
const pageId = item.id;

// Extract audit data from notes if available
const secteurMatch = notes.match(/Secteur:\\s*(.+)/);
const secteur = secteurMatch ? secteurMatch[1].trim() : '';
const heuresMatch = notes.match(/Heures\\/semaine:\\s*(.+)/);
const heures = heuresMatch ? heuresMatch[1].trim() : '';

// Determine if restaurant, hotel, or other
const isHotel = nom.toLowerCase().includes('hotel') || nom.toLowerCase().includes('hôtel');
const isRestaurant = secteur.includes('restaurant') || nom.toLowerCase().includes('restaurant') || nom.toLowerCase().includes('cafe') || nom.toLowerCase().includes('café');

// Build personalized email subject
let subject = '';
let body = '';

// Generic but personalized approach based on Review Autopilot
subject = nom + ' — vos avis Google sont un levier inexploite';

body = `Bonjour,

Je me permets de vous contacter car j'ai analyse la fiche Google de ${nom}.

`;

if (isHotel) {
  body += `Pour un hotel, les avis Google sont un facteur de decision majeur. Les voyageurs comparent systematiquement les notes et les reponses avant de reserver. Un etablissement qui repond a ses avis envoie un signal fort : "nous prenons soin de nos clients".

La plupart de vos avis restent sans reponse — c'est une opportunite manquee, surtout que les avis negatifs non traites pèsent lourd dans la decision des futurs clients.

`;
} else if (isRestaurant) {
  body += `J'ai remarque que la grande majorite de vos avis restent sans reponse. C'est dommage, car ces avis sont un levier enorme pour attirer de nouveaux clients. Google favorise les etablissements qui repondent activement — ca ameliore votre classement local et ca montre aux futurs clients que vous etes a l'ecoute.

Le probleme, c'est que repondre aux avis ca prend un temps fou. Et meme au quotidien, il faut y penser, trouver les mots, et ne pas faire de copier-coller generique.

`;
} else {
  body += `J'ai remarque que beaucoup de vos avis Google restent sans reponse. Les avis sont aujourd'hui le premier reflexe des clients avant de choisir un prestataire — et un etablissement qui repond montre qu'il est a l'ecoute.

`;
}

body += `C'est pour ca que j'ai cree Review Autopilot : une IA qui repond automatiquement a chaque nouvel avis Google, avec des reponses personnalisees et dans le ton de votre etablissement. Pas de reponses robotiques — chaque reponse est unique et adaptee au contenu de l'avis.

Concretement :
- Reponse automatique a chaque nouvel avis (positif comme negatif)
- Ton personnalise selon votre etablissement
- Vous gardez le controle : validation avant publication si vous le souhaitez
- Installation en moins d'une journee

Je suis base a Avignon, donc si ca vous interesse, je peux passer vous faire une demonstration rapide sur place.

Plus d'infos sur notre site : https://adaptive-logic.fr

Bonne continuation,

Chris
Adaptive Logic — Automatisation IA pour commercants locaux
contact@adaptive-logic.fr
https://adaptive-logic.fr`;

return [{json: {
  to: email,
  subject: subject,
  body: body,
  nom: nom,
  pageId: pageId,
  leadScore: leadScore
}}];
"""
            },
        },
        # 5. Send email via Zoho SMTP
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
            "credentials": {
                "smtp": {"id": "SMTP_CRED_ID", "name": "Zoho SMTP"}
            },
        },
        # 6. Update prospect status in Notion
        {
            "id": "notion-update",
            "name": "Update Status Notion",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1250, 300],
            "parameters": {
                "method": "PATCH",
                "url": '=https://api.notion.com/v1/pages/{{ $json.pageId }}',
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
                "jsonBody": '={{ JSON.stringify({"properties": {"Status": {"select": {"name": "Email envoye"}}}}) }}',
                "options": {},
            },
            "credentials": NOTION_CRED,
        },
        # 7. Telegram notification
        {
            "id": "telegram",
            "name": "Telegram Recap",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [1450, 300],
            "credentials": TELEGRAM_CRED,
            "parameters": {
                "chatId": TELEGRAM_CHAT_ID,
                "text": '=📧 *Email envoye*\n\n👤 {{ $json.nom }}\n📬 {{ $json.to }}\n📊 Lead Score: {{ $json.leadScore }}\n\n✅ Status mis a jour dans Pipeline Prospects',
                "additionalFields": {
                    "parse_mode": "Markdown",
                },
            },
        },
    ],
    "connections": {
        "Webhook Send Prospection": {
            "main": [
                [{"node": "Get Prospects A Contacter", "type": "main", "index": 0}]
            ]
        },
        "Get Prospects A Contacter": {
            "main": [
                [{"node": "Split Prospects", "type": "main", "index": 0}]
            ]
        },
        "Split Prospects": {
            "main": [
                [{"node": "Build Email", "type": "main", "index": 0}]
            ]
        },
        "Build Email": {
            "main": [
                [{"node": "Send Email Zoho", "type": "main", "index": 0}]
            ]
        },
        "Send Email Zoho": {
            "main": [
                [{"node": "Update Status Notion", "type": "main", "index": 0}]
            ]
        },
        "Update Status Notion": {
            "main": [
                [{"node": "Telegram Recap", "type": "main", "index": 0}]
            ]
        },
    },
    "settings": {
        "executionOrder": "v1",
    },
}


def create_smtp_credential():
    """Create Zoho SMTP credential in n8n."""
    print("Creating SMTP credential...")
    cred_data = {
        "name": "Zoho SMTP",
        "type": "smtp",
        "data": {
            "user": "contact@adaptive-logic.fr",
            "password": "PJe4ad!NGjqhY8C5",
            "host": "smtp.zoho.eu",
            "port": 465,
            "secure": True,
        },
    }
    resp = requests.post(
        f"{N8N_URL}/api/v1/credentials",
        headers=HEADERS,
        json=cred_data,
    )
    if resp.status_code not in (200, 201):
        print(f"Error creating SMTP credential: {resp.status_code}")
        print(resp.text)
        return None

    cred = resp.json()
    print(f"SMTP credential created: {cred['id']}")
    return cred["id"]


def main():
    # SMTP credential already exists: LDNW2tM882i9Ir3R
    smtp_id = "LDNW2tM882i9Ir3R"

    # Update workflow with real credential ID
    for node in workflow["nodes"]:
        if node["id"] == "send-email":
            node["credentials"]["smtp"]["id"] = smtp_id
            break

    # Step 3: Create workflow
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

    # Step 4: Activate workflow
    print("Activating workflow...")
    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS,
    )
    if resp.status_code == 200:
        print("Workflow activated!")
    else:
        print(f"Activation: {resp.status_code} — {resp.text}")

    print(f"\nWorkflow ID: {wf_id}")
    print("Pour envoyer les emails: lancer manuellement dans n8n ou via API")
    print(f"  POST {N8N_URL}/api/v1/workflows/{wf_id}/run")


if __name__ == "__main__":
    main()
