#!/usr/bin/env python3
"""Create n8n workflow: Sport Coach Telegram Bot.

Telegram webhook that acts as a dedicated sport coach chatbot.
Chris can chat directly with the coach about:
- Training questions, form checks
- Nutrition advice, meal planning
- Recovery, stretching, injury prevention
- Programme adjustments
- Progress tracking

Also accessible by the Manager Bot as a sub-workflow tool.
"""

import json
import os
import uuid
import requests

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = open(os.path.expanduser("~/.n8n-api-key")).read().strip()
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

ANTHROPIC_CRED = {"httpCustomAuth": {"id": "sE8nBT8crViDOv1E", "name": "Anthropic account"}}
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}

TELEGRAM_CHAT_ID = "7342622615"
SPORT_TRACKER_DB = "8d079e42-5bfd-4e95-a00c-ee35b96e3e16"
SPORT_PROGRAMS_DB = "74aa4177-387a-47a7-90f3-b6d4196da837"
TIME_BLOCKS_DB = "51eceb13-346a-4f7e-a07f-724b6d8b2c81"

WORKFLOW_NAME = "Sport Coach Bot"

# Load the knowledge base
KB_PATH = os.path.join(os.path.dirname(__file__), "sport_knowledge_base.json")
with open(KB_PATH) as f:
    KNOWLEDGE_BASE = json.load(f)

# Compact the KB for the system prompt (key sections only)
KB_COMPACT = {
    "nutrition": KNOWLEDGE_BASE["nutrition"],
    "recovery": KNOWLEDGE_BASE["recovery"],
    "calisthenics_progressions": {k: {"levels": [l["name"] for l in v["levels"]]} for k, v in KNOWLEDGE_BASE["calisthenics_progressions"].items()},
    "rep_ranges": KNOWLEDGE_BASE["rep_ranges"],
    "running_program": KNOWLEDGE_BASE["running_restart_program"],
    "combat_conditioning": [e["name"] for e in KNOWLEDGE_BASE["combat_conditioning"]["exercises"]],
    "progression_principles": KNOWLEDGE_BASE["progression_principles"],
    "benchmarks": KNOWLEDGE_BASE["body_metrics_tracking"]["performance_benchmarks"],
}

SYSTEM_PROMPT = r"""Tu es le COACH SPORT PERSONNEL de Chris. Expert en calisthenics, musculation fonctionnelle, course a pied, nutrition sportive et recuperation.

PROFIL ATHLETE:
- Chris, Avignon, debutant en reprise apres longue pause
- Objectif physique: style Baki / Garou / Gun Park — combattant fonctionnel, sec, explosif, agile
- Target body fat: 10-12%. V-taper, abdos visibles, pas de masse bodybuilder
- Equipement: barre de traction + sol (maison) + salle complete (gym)
- Programme: Muscu 4x/sem (Push/Pull/Legs/Full Body Explosif) + Course 5x/sem (reprise progressive)

KNOWLEDGE BASE:
""" + json.dumps(KB_COMPACT, ensure_ascii=False, indent=None)[:6000] + r"""

REGLES:
1. Reponds en FRANCAIS, style coach direct et motivant (pas condescendant)
2. Sois PRECIS: donne des chiffres, des temps, des programmes concrets
3. Si Chris demande un exercice, donne: technique, erreurs courantes, progressions, alternatives
4. Si Chris demande nutrition: donne des repas concrets, pas juste des macros
5. Si Chris signale une douleur: STOP exercice concerne, propose alternatives, recommande medecin si necessaire
6. Si Chris partage un enregistrement/photo de forme: analyse et corrige
7. Utilise les donnees de ses sessions recentes (fournies en contexte) pour personnaliser les conseils
8. Motive-le style anime: "Un guerrier ne saute pas leg day" / "Garou n'a pas atteint ce niveau en restant au lit"
9. Maximum 2000 caracteres par reponse (limite Telegram)

COMMANDES SPECIALES:
- /programme : affiche le programme de la semaine en cours
- /progression : analyse la progression sur les 4 dernieres semaines
- /nutrition [repas] : conseils nutrition pour un repas specifique
- /recovery : protocole de recuperation personnalise
- /benchmark : ou en est Chris vs objectifs
"""


def uid():
    return str(uuid.uuid4())


def build_workflow():
    # Nodes
    webhook_id = uid()
    manager_trigger_id = uid()
    query_recent_id = uid()
    query_program_id = uid()
    build_ctx_id = uid()
    claude_id = uid()
    parse_id = uid()
    send_tg_id = uid()

    # Webhook trigger (Telegram sends messages here)
    webhook = {
        "id": webhook_id,
        "name": "Webhook Sport Coach",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [0, 300],
        "webhookId": "sport-coach",
        "parameters": {
            "path": "sport-coach",
            "httpMethod": "POST",
            "responseMode": "responseNode",
            "options": {},
        },
    }

    # Response node (immediate 200 OK)
    respond_id = uid()
    respond = {
        "id": respond_id,
        "name": "Respond OK",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.1,
        "position": [220, 200],
        "parameters": {
            "respondWith": "json",
            "responseBody": '={"ok": true}',
        },
    }

    # Manager Bot trigger (sub-workflow)
    manager_trigger = {
        "id": manager_trigger_id,
        "name": "Manager Trigger",
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [0, 500],
        "parameters": {},
    }

    # Extract message
    extract_id = uid()
    extract = {
        "id": extract_id,
        "name": "Extract Message",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 400],
        "parameters": {
            "jsCode": """
// From webhook (Telegram or direct POST)
const body = $json.body || $json;
let userMessage = '';
let source = 'webhook';

// If from Telegram webhook (raw update)
if (body.message?.text) {
    userMessage = body.message.text;
    source = 'telegram';
}
// If from Manager Bot or direct call
else if (body.query || body.message) {
    userMessage = body.query || body.message;
    source = body.source || 'manager';
}
// Fallback
else {
    userMessage = JSON.stringify(body).substring(0, 500);
}

return [{json: {userMessage, source}}];
"""
        },
    }

    # Query recent sport sessions from Sport Tracker
    query_recent = {
        "id": query_recent_id,
        "name": "Query Recent Sessions",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [440, 300],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{SPORT_TRACKER_DB}/query",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({
                "sorts": [{"property": "Date", "direction": "descending"}],
                "page_size": 10
            }),
        },
        "onError": "continueRegularOutput",
        "continueOnFail": True,
    }

    # Query current program from Sport Programs
    query_program = {
        "id": query_program_id,
        "name": "Query Current Program",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [440, 500],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{SPORT_PROGRAMS_DB}/query",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({
                "filter": {"property": "Status", "select": {"equals": "Active"}},
                "page_size": 1
            }),
        },
        "onError": "continueRegularOutput",
        "continueOnFail": True,
    }

    # Build context for Claude
    build_ctx = {
        "id": build_ctx_id,
        "name": "Build Coach Context",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [680, 400],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": r"""
const msgData = $('Extract Message').first().json;
const userMessage = msgData.userMessage;
const source = msgData.source;

// Parse recent sessions
let recentSessions = [];
try {
    const data = $('Query Recent Sessions').first().json;
    for (const page of (data.results || [])) {
        const p = page.properties || {};
        const name = (p['Seance']?.title || [])[0]?.plain_text || '?';
        const type = p['Type']?.select?.name || '?';
        const date = p['Date']?.date?.start || '?';
        const duration = p['Duree (min)']?.number || 0;
        const volume = p['Volume (kg)']?.number || 0;
        const distance = p['Distance (km)']?.number || 0;
        const details = (p['Details']?.rich_text || [])[0]?.plain_text || '';
        recentSessions.push({name, type, date, duration, volume, distance, details: details.substring(0, 100)});
    }
} catch(e) {}

// Parse current program
let currentProgram = null;
try {
    const data = $('Query Current Program').first().json;
    const page = (data.results || [])[0];
    if (page) {
        const p = page.properties || {};
        currentProgram = {
            name: (p['Programme']?.title || [])[0]?.plain_text || '?',
            week: p['Week Number']?.number || '?',
            sessionsPlanned: p['Sessions Planned']?.number || 0,
            sessionsDone: p['Sessions Done']?.number || 0,
            notes: (p['Progression Notes']?.rich_text || [])[0]?.plain_text || '',
        };
    }
} catch(e) {}

const systemPrompt = `""" + SYSTEM_PROMPT.replace('`', '\\`').replace('${', '\\${') + """`;

let contextMsg = '';
if (recentSessions.length > 0) {
    contextMsg += '\n\nSESSIONS RECENTES:\n';
    for (const s of recentSessions.slice(0, 5)) {
        contextMsg += '- ' + s.date + ': ' + s.name + ' (' + s.type + ', ' + s.duration + 'min';
        if (s.volume) contextMsg += ', ' + s.volume + 'kg';
        if (s.distance) contextMsg += ', ' + s.distance + 'km';
        contextMsg += ')\n';
    }
}

if (currentProgram) {
    contextMsg += '\nPROGRAMME ACTUEL: ' + currentProgram.name + ' (Semaine ' + currentProgram.week + ', ' + currentProgram.sessionsDone + '/' + currentProgram.sessionsPlanned + ' seances faites)\n';
    if (currentProgram.notes) contextMsg += 'Notes: ' + currentProgram.notes + '\n';
}

const fullUserMsg = userMessage + contextMsg;

return [{json: {systemPrompt, userMessage: fullUserMsg, source, rawMessage: userMessage}}];
"""
        },
    }

    # Claude API
    claude = {
        "id": claude_id,
        "name": "Claude Sport Coach",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [920, 400],
        "credentials": ANTHROPIC_CRED,
        "parameters": {
            "method": "POST",
            "url": "https://api.anthropic.com/v1/messages",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "httpCustomAuth",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "anthropic-version", "value": "2023-06-01"},
                {"name": "content-type", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({"model":"claude-sonnet-4-20250514","max_tokens":2000,"system":$json.systemPrompt,"messages":[{"role":"user","content":$json.userMessage}]}) }}',
        },
    }

    # Parse response
    parse = {
        "id": parse_id,
        "name": "Parse Response",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1140, 400],
        "parameters": {
            "jsCode": """
const prev = $('Build Coach Context').first().json;
const source = prev.source;
let reply = '';

try {
    reply = $json.content?.[0]?.text || 'Erreur: pas de reponse du coach.';
} catch(e) {
    reply = 'Erreur technique. Reessaie.';
}

// Truncate for Telegram
if (reply.length > 4000) reply = reply.substring(0, 3997) + '...';

return [{json: {text: reply, source}}];
"""
        },
    }

    # Send via Telegram
    send_tg = {
        "id": send_tg_id,
        "name": "Send Reply",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [1360, 400],
        "credentials": TELEGRAM_CRED,
        "parameters": {
            "chatId": TELEGRAM_CHAT_ID,
            "text": "={{$json.text}}",
            "additionalFields": {"parse_mode": "HTML"},
        },
    }

    connections = {
        "Webhook Sport Coach": {"main": [[
            {"node": "Respond OK", "type": "main", "index": 0},
            {"node": "Extract Message", "type": "main", "index": 0},
        ]]},
        "Manager Trigger": {"main": [[{"node": "Extract Message", "type": "main", "index": 0}]]},
        "Extract Message": {"main": [[
            {"node": "Query Recent Sessions", "type": "main", "index": 0},
            {"node": "Query Current Program", "type": "main", "index": 0},
        ]]},
        "Query Recent Sessions": {"main": [[{"node": "Build Coach Context", "type": "main", "index": 0}]]},
        "Query Current Program": {"main": [[{"node": "Build Coach Context", "type": "main", "index": 0}]]},
        "Build Coach Context": {"main": [[{"node": "Claude Sport Coach", "type": "main", "index": 0}]]},
        "Claude Sport Coach": {"main": [[{"node": "Parse Response", "type": "main", "index": 0}]]},
        "Parse Response": {"main": [[{"node": "Send Reply", "type": "main", "index": 0}]]},
    }

    return {
        "name": WORKFLOW_NAME,
        "nodes": [webhook, respond, manager_trigger, extract, query_recent, query_program, build_ctx, claude, parse, send_tg],
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris", "saveManualExecutions": True},
    }


if __name__ == "__main__":
    print(f"Building workflow: {WORKFLOW_NAME}")
    wf = build_workflow()

    resp = requests.post(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, json=wf, timeout=30)
    if resp.status_code in (200, 201):
        data = resp.json()
        wf_id = data.get("id", "?")
        print(f"[OK] Created: {wf_id}")
        act = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS, timeout=10)
        print(f"[OK] Active: {act.status_code == 200}")
        print(f"\nWebhook URL: {N8N_URL}/webhook/sport-coach")
        print("POST with: {\"message\": \"Question sport ici\"}")
    else:
        print(f"[ERROR] {resp.status_code}: {resp.text[:300]}")
