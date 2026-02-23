#!/usr/bin/env python3
"""
Couche 2 — Multi-Agent n8n Workflows Creator
Creates 4 strategic workflows via n8n API:
1. Morning Brief (daily 8:00)
2. Strategy Advisor (Telegram /strategy)
3. Weekly Progress Review (Monday 9:00)
4. Decision Review Reminder (Friday 17:00)
"""

import json
import uuid
import requests
import time
import sys

# ── Config ──────────────────────────────────────────────────────────
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9.sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Credentials
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "1xk5rqYQ1FCdUQ7N", "name": "Braindump Bot Telegram"}}
ANTHROPIC_CRED = {"anthropicApi": {"id": "sE8nBT8crViDOv1E", "name": "Anthropic account"}}

CHAT_ID = "7342622615"

# Database IDs
GOALS_DB = "affa9ce1-a3d7-4182-a87d-8cbabf6fa983"
TASKS_DB = "305da200-b2d6-818e-bad3-000b048788f1"
DECISIONS_DB = "e2910fca-2887-474e-8e58-3f08d20195e5"

MODEL_ID = "claude-sonnet-4-5-20250929"

# ── Couche 3b — Manager Agent Config ────────────────────────────────
ORUN_TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}
SERP_API_CRED = {"serpApi": {"id": "jwkb3PzaaVxgcSMM", "name": "SerpAPI account"}}
POSTGRES_CRED = {"postgres": {"id": "TBD", "name": "n8n Postgres"}}

# Correct Notion DB IDs (verified API IDs from Couche 2 testing)
GOALS_DB_API = "bc88ee5f-f09b-4f45-adb9-faae179aa276"
TASKS_DB_API = "305da200-b2d6-8145-bc16-eaee02925a14"
DECISIONS_DB_API = "ced391a8-17ee-4115-9e48-9f6ecab02a93"

COUCHE2_STRATEGY_ADVISOR_ID = "mXGhZ6dHSvp7ZnjT"

# ── Couche 3b v2 — IDs ────────────────────────────────────────────
# Existing sub-agents to KEEP (unchanged from v1)
EXISTING_PRIORITIZER_ID = "pxThrV04KKdu1DEW"
EXISTING_DECISION_LOGGER_ID = "tO0K1z0G0aA2uNN8"
EXISTING_PROGRESS_TRACKER_ID = "T9b8PEm7mcZdIavF"

# v1 workflows to DELETE and replace
V1_MANAGER_ID = "jLo5wRXXHODkcFWm"
V1_STRATEGY_ADVISOR_ID = "4ZDkBbvF9e45QNsL"
V1_OPPORTUNITY_SCOUT_ID = "g14cA9Wxgs9qNkd3"

# Current v2 deployed IDs (for updates)
CURRENT_MANAGER_ID = "n981N02BydvguvG6"
CURRENT_STRATEGY_ID = "su5wJ4az3d9TsYV2"
CURRENT_SCOUT_ID = "kMGVJvZyMhNaV9zU"
CURRENT_WEB_SEARCH_ID = "lVIRJVTRokI7cEbi"

# ── Voice Support (OpenAI Whisper) ─────────────────────────────────
OPENAI_CRED = {"openAiApi": {"id": "fcYKeOaqJpz1X9JE", "name": "OpenAi account"}}

# Tool descriptions (critical for Manager routing)
TOOL_DESCRIPTIONS = {
    "strategy-advisor": "Analyse strategique (business et vie perso) : scenarios, challenge de decisions, conseil sur la direction de vie.",
    "prioritizer": "Scoring WICE des objectifs (tous domaines) et mise a jour dans Notion. Scorer, prioriser, trier les goals.",
    "decision-logger": "Documenter une decision ou mettre a jour le resultat d'une decision passee dans le Decision Log.",
    "progress-tracker": "Diagnostic de progression tous objectifs : velocite, blocages, bilan semaine.",
    "opportunity-scout": "Recherche de prospects TPE/PME Avignon/Vaucluse. Trouver des clients potentiels.",
}

# ── Couche 3b v3 — Tool Descriptions & Prompt ─────────────────────
TOOL_DESCRIPTIONS_V3 = {
    "strategy": (
        "Analyse strategique tous domaines (business, vie, sport, spirituel). "
        "Scenarios, challenge de decisions, conseil direction de vie. "
        "A acces aux objectifs Notion et decisions recentes."
    ),
    "prioritize": (
        "Scoring WICE des objectifs et mise a jour dans Notion. "
        "Scorer, re-scorer, prioriser, trier les goals par Strategic Score."
    ),
    "decision": (
        "Documenter une decision ou mettre a jour le resultat "
        "d'une decision passee dans le Decision Log Notion."
    ),
    "progress": (
        "Diagnostic de progression sur tous les objectifs : "
        "velocite, blocages, bilan semaine, tendances."
    ),
    "prospect": (
        "Recherche de prospects TPE/PME a Avignon/Vaucluse. "
        "Trouver des clients potentiels, identifier leurs problemes visibles."
    ),
    "search": (
        "Recherche web via Google Search et Wikipedia. "
        "Verifier une info, chercher des donnees externes, explorer un sujet."
    ),
    "scrape": (
        "Scraper le contenu d'une URL specifique. Jina AI Reader pour les pages web, "
        "ou API custom pour Reddit, SpillBox, TikTok (serveur 31.97.54.26). "
        "Utile pour analyser un site, un article, ou une page prospect."
    ),
    "knowledge": (
        "Acces aux donnees personnelles de Chris : session logs (historique de travail), "
        "competences et skills actuels, portfolio projets. "
        "Source : repos GitHub prinsechris. Utilise pour contextualiser les conseils."
    ),
}

MANAGER_V3_PROMPT = """Tu es Orun, l'assistant strategique personnel de Chris. Tu orchestres une equipe d'agents specialises.

== OUTILS DISPONIBLES ==

1. strategy : Conseiller strategique. Analyse tous domaines (business, sport, spirituel, relationnel).
   A acces aux objectifs et decisions Notion. Donne scenarios et actions concretes.

2. prioritize : Scoring WICE des objectifs. Scorer, prioriser, trier les goals par Strategic Score.

3. decision : Decision Logger. Documente une decision ou met a jour le resultat d'une decision passee.

4. progress : Diagnostic de progression. Velocite, blocages, bilan sur tous les objectifs.

5. prospect : Eclaireur commercial. Recherche prospects TPE/PME Avignon/Vaucluse, problemes visibles.

6. search : Recherche web (Google + Wikipedia). Verifier des faits, explorer un sujet.

7. scrape : Scraper une URL ou lancer un scraping specifique.
   Pages web via Jina AI Reader. Reddit, SpillBox, TikTok via API custom.

8. knowledge : Acces aux donnees de Chris. Session logs, competences, portfolio.
   Utilise pour contextualiser tes conseils avec l'historique reel de Chris.

== RACCOURCIS ==
/strategy→strategy, /score→prioritize, /decision→decision, /bilan→progress, /prospect→prospect, /search→search, /scrape→scrape, /knowledge→knowledge

== CHAINAGE MULTI-AGENT ==

Tu DOIS chainer les outils quand c'est pertinent :

- "Quelles priorites et comment avancer ?" → prioritize d'abord, puis strategy avec le resultat
- "Trouve des prospects et propose une strategie" → prospect d'abord, puis strategy avec les prospects
- "Ou j'en suis et qu'est-ce que je devrais decider ?" → progress d'abord, puis strategy avec le diagnostic
- "Cherche [X] et dis-moi comment l'appliquer" → search d'abord, puis strategy avec les resultats
- "Analyse le site [URL]" → scrape d'abord, puis strategy avec le contenu
- "Trouve des prospects et regarde leurs sites" → prospect d'abord, puis scrape sur les URLs trouvees
- "Quelles sont mes forces ?" → knowledge d'abord, puis strategy avec le contexte
- "Propose un pitch base sur ce que je sais faire" → knowledge (competences), puis strategy

Quand tu chaines : passe le RESULTAT du premier outil comme CONTEXTE au deuxieme.

== REPONSE DIRECTE (sans outil) ==

Reponds directement pour : salutations, questions sur toi, hors-scope, remerciements.

== TON ET FORMAT ==

- Tutoiement, ton direct et franc
- Ne reformule PAS le message de Chris pour les outils — passe-le tel quel
- Si ambigu, pose UNE question de clarification
- Synthese claire qui connecte les resultats si chainage
- Francais uniquement, max 600 mots"""


def uid():
    return str(uuid.uuid4())


def notion_db_ref(db_id, name=None):
    ref = {"__rl": True, "value": db_id, "mode": "id"}
    if name:
        ref["cachedResultName"] = name
    return ref


def anthropic_node(name, system_prompt, user_expr, pos):
    return {
        "parameters": {
            "modelId": {
                "__rl": True,
                "value": MODEL_ID,
                "mode": "list",
                "cachedResultName": MODEL_ID,
            },
            "messages": {
                "values": [
                    {"content": system_prompt, "role": "assistant"},
                    {"content": user_expr},
                ]
            },
            "options": {"maxTokensToSample": 2048},
        },
        "type": "@n8n/n8n-nodes-langchain.anthropic",
        "typeVersion": 1,
        "position": pos,
        "id": uid(),
        "name": name,
        "credentials": ANTHROPIC_CRED,
    }


def telegram_send_node(name, text_expr, chat_id_expr, pos):
    return {
        "parameters": {
            "chatId": chat_id_expr,
            "text": text_expr,
            "additionalFields": {
                "appendAttribution": False,
                "parse_mode": "HTML",
            },
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": pos,
        "id": uid(),
        "name": name,
        "credentials": TELEGRAM_CRED,
    }


def notion_get_all_node(name, db_id, db_name, filters, pos, return_all=True, limit=50, sort=None):
    params = {
        "resource": "databasePage",
        "operation": "getAll",
        "databaseId": notion_db_ref(db_id, db_name),
        "returnAll": return_all,
        "options": {},
    }
    if not return_all:
        params["limit"] = limit
        del params["returnAll"]
    if filters:
        params["filterType"] = "manual"
        params["matchType"] = "allFilters"
        params["filters"] = {"conditions": filters}
    if sort:
        params["options"]["sort"] = {"sortValue": sort}
    return {
        "parameters": params,
        "type": "n8n-nodes-base.notion",
        "typeVersion": 2.2,
        "position": pos,
        "id": uid(),
        "name": name,
        "credentials": NOTION_CRED,
    }


def code_node(name, js_code, pos):
    return {
        "parameters": {"jsCode": js_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos,
        "id": uid(),
        "name": name,
    }


def wait_node(name, pos, ms=300):
    return {
        "parameters": {"amount": ms, "unit": "milliseconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": pos,
        "id": uid(),
        "name": name,
        "webhookId": uid(),
    }


def if_node(name, condition_expr, pos):
    return {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": condition_expr,
                        "rightValue": 0,
                        "operator": {"type": "number", "operation": "gt"},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": pos,
        "id": uid(),
        "name": name,
    }


def connect(connections, from_node, to_node, from_output=0):
    if from_node not in connections:
        connections[from_node] = {"main": []}
    while len(connections[from_node]["main"]) <= from_output:
        connections[from_node]["main"].append([])
    connections[from_node]["main"][from_output].append(
        {"node": to_node, "type": "main", "index": 0}
    )


# ── Couche 3b Builder Functions ─────────────────────────────────────

def agent_node(name, system_prompt, input_expr, pos):
    """LangChain Tools Agent v2."""
    return {
        "parameters": {
            "promptType": "define",
            "text": input_expr,
            "options": {"systemMessage": system_prompt},
        },
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 2,
        "position": pos,
        "id": uid(),
        "name": name,
    }


def lm_chat_anthropic_node(name, model_id, pos, max_tokens=4096):
    """Claude LangChain Chat Model."""
    return {
        "parameters": {
            "model": {
                "__rl": True,
                "mode": "list",
                "value": model_id,
                "cachedResultName": model_id,
            },
            "options": {"maxTokensToSample": max_tokens},
        },
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": pos,
        "id": uid(),
        "name": name,
        "credentials": ANTHROPIC_CRED,
    }


def postgres_memory_node(name, session_key_expr, pos, context_window=20):
    """Postgres Chat Memory (persistent across sessions)."""
    return {
        "parameters": {
            "sessionIdType": "customKey",
            "sessionKey": session_key_expr,
            "tableName": "n8n_chat_histories",
            "contextWindowLength": context_window,
        },
        "type": "@n8n/n8n-nodes-langchain.memoryPostgresChat",
        "typeVersion": 1.1,
        "position": pos,
        "id": uid(),
        "name": name,
        "credentials": POSTGRES_CRED,
    }


def tool_workflow_node(name, tool_name, workflow_id, description, pos):
    """Tool sub-workflow for LangChain Agent."""
    return {
        "parameters": {
            "name": tool_name,
            "description": description,
            "workflowId": {"__rl": True, "value": workflow_id, "mode": "id"},
        },
        "type": "@n8n/n8n-nodes-langchain.toolWorkflow",
        "typeVersion": 2,
        "position": pos,
        "id": uid(),
        "name": name,
    }


def execute_workflow_trigger_node(name, pos):
    """Trigger node for sub-workflows called via executeWorkflow/toolWorkflow."""
    return {
        "parameters": {"inputSource": "passthrough"},
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": pos,
        "id": uid(),
        "name": name,
    }


def serp_api_node(name, pos):
    """SerpAPI tool for LangChain Agent."""
    return {
        "parameters": {},
        "type": "@n8n/n8n-nodes-langchain.toolSerpApi",
        "typeVersion": 1,
        "position": pos,
        "id": uid(),
        "name": name,
        "credentials": SERP_API_CRED,
    }


def connect_ai(connections, from_node, to_node, ai_type):
    """Connect AI sub-nodes: ai_languageModel, ai_memory, ai_tool."""
    if from_node not in connections:
        connections[from_node] = {}
    if ai_type not in connections[from_node]:
        connections[from_node][ai_type] = [[]]
    connections[from_node][ai_type][0].append(
        {"node": to_node, "type": ai_type, "index": 0}
    )


def telegram_trigger_node(name, pos, credentials):
    """Telegram Trigger listening to all messages."""
    return {
        "parameters": {"updates": ["message"], "additionalFields": {}},
        "type": "n8n-nodes-base.telegramTrigger",
        "typeVersion": 1.2,
        "position": pos,
        "id": uid(),
        "name": name,
        "credentials": credentials,
        "webhookId": uid(),
    }


def execute_workflow_node(name, workflow_id, pos):
    """Execute another workflow (direct call, not LangChain tool)."""
    return {
        "parameters": {
            "workflowId": {"__rl": True, "value": workflow_id, "mode": "id"},
        },
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": pos,
        "id": uid(),
        "name": name,
    }


def switch_node(name, rules, pos, fallback="extra"):
    """Switch v3.2 with multiple output rules.

    Args:
        rules: list of (output_key, field_expr, value) tuples
        fallback: "extra" (additional output) or "none"
    """
    values = []
    for output_key, field_expr, value in rules:
        values.append({
            "outputKey": output_key,
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2,
                },
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": field_expr,
                        "rightValue": value,
                        "operator": {
                            "type": "string",
                            "operation": "equals",
                        },
                    }
                ],
                "combinator": "and",
            },
        })
    return {
        "parameters": {
            "rules": {"values": values},
            "options": {"fallbackOutput": fallback},
        },
        "type": "n8n-nodes-base.switch",
        "typeVersion": 3.2,
        "position": pos,
        "id": uid(),
        "name": name,
    }


def wikipedia_node(name, pos):
    """Wikipedia tool for LangChain Agent."""
    return {
        "parameters": {},
        "type": "@n8n/n8n-nodes-langchain.toolWikipedia",
        "typeVersion": 1,
        "position": pos,
        "id": uid(),
        "name": name,
    }


# ════════════════════════════════════════════════════════════════════
# WORKFLOW 1: Morning Brief
# ════════════════════════════════════════════════════════════════════
def create_morning_brief():
    nodes = []
    connections = {}

    # 1. Schedule Trigger
    nodes.append({
        "parameters": {
            "rule": {
                "interval": [{"triggerAtHour": 8, "triggerAtMinute": 0}]
            }
        },
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.3,
        "position": [0, 0],
        "id": uid(),
        "name": "Schedule Trigger",
    })

    # 2. Query Goals (In Progress)
    nodes.append(notion_get_all_node(
        "Get Goals",
        GOALS_DB,
        "Goals",
        [{"key": "Status|select", "condition": "equals", "selectValue": "\U0001f525 In Progress"}],
        [300, 0],
    ))
    connect(connections, "Schedule Trigger", "Get Goals")

    # 3. Aggregate Goals
    nodes.append(code_node("Aggregate Goals", """
const goals = $input.all().map(item => ({
  name: item.json.name || item.json.properties?.Name?.title?.[0]?.plain_text || 'Unknown',
  status: item.json.property_Status || 'Unknown',
  priority: item.json.property_Priority || '',
  category: item.json.property_Category || '',
  progress: item.json.property_Progress || item.json['property_Progress %'] || 0,
  strategicScore: item.json.property_Strategic_Score || item.json['property_Strategic Score'] || '',
  targetDate: item.json.property_Target_Date || item.json['property_Target Date'] || '',
  revenuePotential: item.json.property_Revenue_Potential || item.json['property_Revenue Potential'] || 0,
}));
return [{json: {goals}}];
""", [600, 0]))
    connect(connections, "Get Goals", "Aggregate Goals")

    # 4. Wait 300ms
    nodes.append(wait_node("Wait", [900, 0]))
    connect(connections, "Aggregate Goals", "Wait")

    # 5. Query Tasks
    nodes.append(notion_get_all_node(
        "Get Tasks",
        TASKS_DB,
        "Tasks",
        [],  # No filter — we'll filter in code
        [1200, 0],
    ))
    connect(connections, "Wait", "Get Tasks")

    # 6. Build Context
    nodes.append(code_node("Build Context", """
const goals = $('Aggregate Goals').first().json.goals;
const allTasks = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || '',
  dueDate: item.json.property_Due_Date || item.json['property_Due Date'] || '',
  category: item.json.property_Category || '',
  type: item.json.property_Type || '',
  difficulty: item.json.property_Difficulty || '',
  description: item.json.property_Description || '',
  revenueImpact: item.json.property_Revenue_Impact || item.json['property_Revenue Impact'] || '',
}));

// Filter: Ready To Start or In Progress, Due Date within 3 days
const now = new Date();
const in3days = new Date(now.getTime() + 3 * 24 * 60 * 60 * 1000);
const today = now.toISOString().split('T')[0];

const activeTasks = allTasks.filter(t =>
  t.status === 'Ready To Start' || t.status === 'In Progress'
);

const urgentTasks = activeTasks.filter(t => {
  if (!t.dueDate) return true; // No due date = include
  const due = new Date(typeof t.dueDate === 'object' ? t.dueDate.start : t.dueDate);
  return due <= in3days;
});

const otherTasks = activeTasks.filter(t => {
  if (!t.dueDate) return false;
  const due = new Date(typeof t.dueDate === 'object' ? t.dueDate.start : t.dueDate);
  return due > in3days;
});

const contextText = `
Date: ${today}

=== OBJECTIFS ACTIFS (tries par Strategic Score) ===
${goals.map(g => `- ${g.name} | Priority: ${g.priority} | Score: ${g.strategicScore} | Progress: ${Math.round((g.progress || 0) * 100)}% | Revenue: ${g.revenuePotential}EUR | Target: ${g.targetDate}`).join('\\n')}

=== TACHES URGENTES (due dans 3 jours ou sans date) ===
${urgentTasks.length > 0 ? urgentTasks.map(t => `- [${t.status}] ${t.name} | Due: ${t.dueDate || 'Pas de date'} | Category: ${t.category}`).join('\\n') : 'Aucune tache urgente'}

=== AUTRES TACHES ACTIVES ===
${otherTasks.length > 0 ? otherTasks.map(t => `- [${t.status}] ${t.name} | Due: ${t.dueDate} | Category: ${t.category}`).join('\\n') : 'Aucune'}

Stats: ${activeTasks.length} taches actives, ${urgentTasks.length} urgentes
`.trim();

return [{json: {contextText}}];
""", [1500, 0]))
    connect(connections, "Get Tasks", "Build Context")

    # 7. Claude Prioritization Agent
    system_prompt = """Tu es le Prioritization Agent d'Adaptive Logic, une agence d'automatisation IA basee a Avignon ciblant les TPE/PME.
Objectif principal: atteindre 2000 EUR de CA d'ici fin mars 2026.

Ta mission chaque matin:
1. Analyse les objectifs actifs et leur Strategic Score
2. Identifie les 3 actions prioritaires pour AUJOURD'HUI
3. Signale les deadlines proches et les taches en retard
4. Priorise ce qui genere du revenu

Regles:
- Ton direct et actionnable, pas de blabla
- Chaque action doit etre concrete et faisable en une journee
- Si une tache est en retard, le signaler clairement
- Maximum 400 mots
- Reponds en francais"""

    nodes.append(anthropic_node(
        "Claude Prioritization",
        system_prompt,
        "={{ $json.contextText }}",
        [1800, 0],
    ))
    connect(connections, "Build Context", "Claude Prioritization")

    # 8. Format Telegram HTML
    nodes.append(code_node("Format HTML", """
const response = $json.content?.[0]?.text || $json.output || $json.text || JSON.stringify($json);

// Convert to Telegram HTML (max 4096 chars)
let html = '<b>\\u2600\\ufe0f Morning Brief</b>\\n\\n';
html += response
  .replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
  .replace(/\\*(.+?)\\*/g, '<i>$1</i>')
  .replace(/^### (.+)$/gm, '<b>$1</b>')
  .replace(/^## (.+)$/gm, '<b>$1</b>')
  .replace(/^# (.+)$/gm, '<b>$1</b>');

if (html.length > 4000) {
  html = html.substring(0, 3997) + '...';
}

return [{json: {html}}];
""", [2100, 0]))
    connect(connections, "Claude Prioritization", "Format HTML")

    # 9. Telegram Send
    nodes.append(telegram_send_node(
        "Send Morning Brief",
        "={{ $json.html }}",
        CHAT_ID,
        [2400, 0],
    ))
    connect(connections, "Format HTML", "Send Morning Brief")

    return {
        "name": "Morning Brief - Couche 2",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris"},
    }


# ════════════════════════════════════════════════════════════════════
# WORKFLOW 2: Strategy Advisor
# ════════════════════════════════════════════════════════════════════
def create_strategy_advisor():
    nodes = []
    connections = {}

    # 1. Telegram Trigger
    nodes.append({
        "parameters": {"updates": ["message"], "additionalFields": {}},
        "type": "n8n-nodes-base.telegramTrigger",
        "typeVersion": 1.1,
        "position": [0, 0],
        "id": uid(),
        "name": "Telegram Trigger",
        "credentials": TELEGRAM_CRED,
        "webhookId": uid(),
    })

    # 2. Check /strategy command
    nodes.append(code_node("Check Command", """
const msg = $json.message?.text || '';
if (!msg.startsWith('/strategy')) {
  // Not a /strategy command — stop here
  return [];
}
const question = msg.replace('/strategy', '').trim() || 'Quelle est la meilleure strategie pour cette semaine ?';
const chatId = $json.message?.chat?.id || '';
return [{json: {question, chatId}}];
""", [300, 0]))
    connect(connections, "Telegram Trigger", "Check Command")

    # 3. Get Goals
    nodes.append(notion_get_all_node(
        "Get Goals",
        GOALS_DB,
        "Goals",
        [{"key": "Status|select", "condition": "isNotEmpty"}],
        [600, 0],
    ))
    connect(connections, "Check Command", "Get Goals")

    # 4. Aggregate Goals
    nodes.append(code_node("Aggregate Goals", """
const goals = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || '',
  priority: item.json.property_Priority || '',
  category: item.json.property_Category || '',
  progress: item.json.property_Progress || item.json['property_Progress %'] || 0,
  strategicScore: item.json.property_Strategic_Score || item.json['property_Strategic Score'] || '',
  targetDate: item.json.property_Target_Date || item.json['property_Target Date'] || '',
  revenuePotential: item.json.property_Revenue_Potential || item.json['property_Revenue Potential'] || 0,
  successCriteria: item.json.property_Success_Criteria || item.json['property_Success Criteria'] || '',
}));
return [{json: {goals}}];
""", [900, 0]))
    connect(connections, "Get Goals", "Aggregate Goals")

    # 5. Wait
    nodes.append(wait_node("Wait 1", [1200, 0]))
    connect(connections, "Aggregate Goals", "Wait 1")

    # 6. Get Decisions (recent 30 days)
    nodes.append(notion_get_all_node(
        "Get Decisions",
        DECISIONS_DB,
        "Decision Log",
        [],
        [1500, 0],
        return_all=True,
    ))
    connect(connections, "Wait 1", "Get Decisions")

    # 7. Aggregate Decisions
    nodes.append(code_node("Aggregate Decisions", """
const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
const decisions = $input.all()
  .map(item => ({
    decision: item.json.name || 'Unknown',
    date: item.json.property_Date || item.json['property_Date'] || '',
    impact: item.json.property_Impact || '',
    context: item.json.property_Context || '',
    optionChoisie: item.json.property_Option_choisie || item.json['property_Option choisie'] || '',
    pourquoi: item.json.property_Pourquoi || '',
    resultatReel: item.json.property_Resultat_reel || item.json['property_Resultat reel'] || '',
    learnings: item.json.property_Learnings || '',
  }))
  .filter(d => {
    if (!d.date) return true;
    const dDate = new Date(typeof d.date === 'object' ? d.date.start : d.date);
    return dDate >= thirtyDaysAgo;
  });
return [{json: {decisions}}];
""", [1800, 0]))
    connect(connections, "Get Decisions", "Aggregate Decisions")

    # 8. Wait
    nodes.append(wait_node("Wait 2", [2100, 0]))
    connect(connections, "Aggregate Decisions", "Wait 2")

    # 9. Get Tasks
    nodes.append(notion_get_all_node(
        "Get Tasks",
        TASKS_DB,
        "Tasks",
        [],
        [2400, 0],
    ))
    connect(connections, "Wait 2", "Get Tasks")

    # 10. Build Strategic Context
    nodes.append(code_node("Build Context", """
const question = $('Check Command').first().json.question;
const goals = $('Aggregate Goals').first().json.goals;
const decisions = $('Aggregate Decisions').first().json.decisions;
const allTasks = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || '',
  category: item.json.property_Category || '',
  revenueImpact: item.json.property_Revenue_Impact || item.json['property_Revenue Impact'] || '',
}));

const activeTasks = allTasks.filter(t =>
  t.status === 'In Progress' || t.status === 'Blocked'
);

const today = new Date().toISOString().split('T')[0];

const contextText = `
QUESTION STRATEGIQUE: ${question}

Date: ${today}

=== OBJECTIFS ===
${goals.map(g => `- [${g.status}] ${g.name} | Priority: ${g.priority} | Score: ${g.strategicScore} | Progress: ${Math.round((g.progress || 0) * 100)}% | Revenue: ${g.revenuePotential}EUR | Target: ${g.targetDate}
  Success Criteria: ${g.successCriteria}`).join('\\n')}

=== DECISIONS RECENTES (30 jours) ===
${decisions.map(d => `- ${d.decision} | Impact: ${d.impact} | ${d.optionChoisie} | Learnings: ${d.learnings}`).join('\\n') || 'Aucune decision recente'}

=== TACHES EN COURS / BLOQUEES ===
${activeTasks.map(t => `- [${t.status}] ${t.name} | Revenue: ${t.revenueImpact}`).join('\\n') || 'Aucune'}
`.trim();

return [{json: {contextText}}];
""", [2700, 0]))
    connect(connections, "Get Tasks", "Build Context")

    # 11. Claude Strategy Advisor
    system_prompt = """Tu es le Strategy Advisor d'Adaptive Logic — conseiller senior pour Chris.
Adaptive Logic est une agence d'automatisation IA basee a Avignon, ciblant les TPE/PME locales (restaurants, artisans, commerces, agences immo).
Objectif : 2000 EUR de CA d'ici fin mars 2026.

Ta mission:
1. Analyse la situation actuelle (objectifs, decisions passees, taches)
2. Reponds a la question strategique posee
3. Identifie opportunites et risques
4. Propose 3 actions recommandees avec impact et effort estimes
5. Si une decision est requise, formule-la clairement

Regles:
- Analyse factuelle basee sur les donnees
- Actions concretes, pas de generalites
- Estime l'impact en EUR quand possible
- Maximum 500 mots
- Reponds en francais"""

    nodes.append(anthropic_node(
        "Claude Strategy Advisor",
        system_prompt,
        "={{ $json.contextText }}",
        [3000, 0],
    ))
    connect(connections, "Build Context", "Claude Strategy Advisor")

    # 12. Format HTML
    nodes.append(code_node("Format HTML", """
const response = $json.content?.[0]?.text || $json.output || $json.text || JSON.stringify($json);
const question = $('Check Command').first().json.question;

let html = '<b>\\U0001f9e0 Strategy Advisor</b>\\n';
html += '<i>' + question + '</i>\\n\\n';
html += response
  .replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
  .replace(/\\*(.+?)\\*/g, '<i>$1</i>')
  .replace(/^### (.+)$/gm, '<b>$1</b>')
  .replace(/^## (.+)$/gm, '<b>$1</b>')
  .replace(/^# (.+)$/gm, '<b>$1</b>');

if (html.length > 4000) {
  html = html.substring(0, 3997) + '...';
}

return [{json: {html}}];
""", [3300, 0]))
    connect(connections, "Claude Strategy Advisor", "Format HTML")

    # 13. Telegram Reply
    nodes.append(telegram_send_node(
        "Reply Strategy",
        "={{ $json.html }}",
        "={{ $('Check Command').first().json.chatId }}",
        [3600, 0],
    ))
    connect(connections, "Format HTML", "Reply Strategy")

    return {
        "name": "Strategy Advisor - Couche 2",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris"},
    }


# ════════════════════════════════════════════════════════════════════
# WORKFLOW 3: Weekly Progress Review
# ════════════════════════════════════════════════════════════════════
def create_weekly_progress():
    nodes = []
    connections = {}

    # 1. Schedule Trigger (Monday 9:00)
    nodes.append({
        "parameters": {
            "rule": {
                "interval": [
                    {
                        "field": "cronExpression",
                        "expression": "0 9 * * 1",
                    }
                ]
            }
        },
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.3,
        "position": [0, 0],
        "id": uid(),
        "name": "Schedule Trigger",
    })

    # 2. Get Goals
    nodes.append(notion_get_all_node(
        "Get Goals",
        GOALS_DB,
        "Goals",
        [{"key": "Status|select", "condition": "isNotEmpty"}],
        [300, 0],
    ))
    connect(connections, "Schedule Trigger", "Get Goals")

    # 3. Aggregate Goals
    nodes.append(code_node("Aggregate Goals", """
const goals = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || '',
  priority: item.json.property_Priority || '',
  progress: item.json.property_Progress || item.json['property_Progress %'] || 0,
  strategicScore: item.json.property_Strategic_Score || item.json['property_Strategic Score'] || '',
  targetDate: item.json.property_Target_Date || item.json['property_Target Date'] || '',
  revenuePotential: item.json.property_Revenue_Potential || item.json['property_Revenue Potential'] || 0,
}));
return [{json: {goals}}];
""", [600, 0]))
    connect(connections, "Get Goals", "Aggregate Goals")

    # 4. Wait
    nodes.append(wait_node("Wait", [900, 0]))
    connect(connections, "Aggregate Goals", "Wait")

    # 5. Get All Tasks
    nodes.append(notion_get_all_node(
        "Get Tasks",
        TASKS_DB,
        "Tasks",
        [],
        [1200, 0],
    ))
    connect(connections, "Wait", "Get Tasks")

    # 6. Build Progress Context
    nodes.append(code_node("Build Context", """
const goals = $('Aggregate Goals').first().json.goals;
const allTasks = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || '',
  completedOn: item.json.property_Completed_On || item.json['property_Completed On'] || '',
  dueDate: item.json.property_Due_Date || item.json['property_Due Date'] || '',
  category: item.json.property_Category || '',
  revenueImpact: item.json.property_Revenue_Impact || item.json['property_Revenue Impact'] || '',
}));

const now = new Date();
const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
const today = now.toISOString().split('T')[0];

// Tasks completed this week
const completedThisWeek = allTasks.filter(t => {
  if (t.status !== 'Complete') return false;
  if (!t.completedOn) return false;
  const d = new Date(typeof t.completedOn === 'object' ? t.completedOn.start : t.completedOn);
  return d >= weekAgo;
});

// Overdue tasks
const overdue = allTasks.filter(t => {
  if (t.status === 'Complete' || t.status === 'Archive') return false;
  if (!t.dueDate) return false;
  const d = new Date(typeof t.dueDate === 'object' ? t.dueDate.start : t.dueDate);
  return d < now;
});

// Blocked tasks
const blocked = allTasks.filter(t => t.status === 'Blocked');

// In progress
const inProgress = allTasks.filter(t => t.status === 'In Progress');

const contextText = `
Date: ${today}
Periode: ${weekAgo.toISOString().split('T')[0]} a ${today}

=== OBJECTIFS ===
${goals.map(g => `- [${g.status}] ${g.name} | Progress: ${Math.round((g.progress || 0) * 100)}% | Score: ${g.strategicScore} | Target: ${g.targetDate}`).join('\\n')}

=== METRIQUES HEBDOMADAIRES ===
- Taches completees cette semaine: ${completedThisWeek.length}
- Taches en cours: ${inProgress.length}
- Taches en retard: ${overdue.length}
- Taches bloquees: ${blocked.length}
- Total taches actives: ${inProgress.length + blocked.length}

=== TACHES COMPLETEES CETTE SEMAINE ===
${completedThisWeek.map(t => `- ${t.name} | Category: ${t.category} | Revenue: ${t.revenueImpact}`).join('\\n') || 'Aucune'}

=== TACHES EN RETARD ===
${overdue.map(t => `- ${t.name} | Due: ${t.dueDate} | Status: ${t.status}`).join('\\n') || 'Aucune'}

=== TACHES BLOQUEES ===
${blocked.map(t => `- ${t.name} | Category: ${t.category}`).join('\\n') || 'Aucune'}
`.trim();

return [{json: {contextText}}];
""", [1500, 0]))
    connect(connections, "Get Tasks", "Build Context")

    # 7. Claude Progress Tracker
    system_prompt = """Tu es le Progress Tracker d'Adaptive Logic.
Objectif: 2000 EUR de CA d'ici fin mars 2026.

Ta mission chaque lundi:
1. Analyse la progression vers les objectifs
2. Calcule la velocite (taches completees/semaine)
3. Detecte les blocages et retards
4. Estime le temps restant pour chaque objectif actif
5. Recommande des ajustements concrets

Regles:
- Commence par un bilan rapide (bon/mauvais/neutre)
- Sois direct sur les problemes
- Propose des solutions concretes pour les blocages
- Si la velocite est trop basse, le dire clairement
- Maximum 500 mots
- Reponds en francais"""

    nodes.append(anthropic_node(
        "Claude Progress Tracker",
        system_prompt,
        "={{ $json.contextText }}",
        [1800, 0],
    ))
    connect(connections, "Build Context", "Claude Progress Tracker")

    # 8. Format HTML
    nodes.append(code_node("Format HTML", """
const response = $json.content?.[0]?.text || $json.output || $json.text || JSON.stringify($json);

let html = '<b>\\U0001f4ca Weekly Progress Review</b>\\n\\n';
html += response
  .replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
  .replace(/\\*(.+?)\\*/g, '<i>$1</i>')
  .replace(/^### (.+)$/gm, '<b>$1</b>')
  .replace(/^## (.+)$/gm, '<b>$1</b>')
  .replace(/^# (.+)$/gm, '<b>$1</b>');

if (html.length > 4000) {
  html = html.substring(0, 3997) + '...';
}

return [{json: {html}}];
""", [2100, 0]))
    connect(connections, "Claude Progress Tracker", "Format HTML")

    # 9. Telegram Send
    nodes.append(telegram_send_node(
        "Send Weekly Report",
        "={{ $json.html }}",
        CHAT_ID,
        [2400, 0],
    ))
    connect(connections, "Format HTML", "Send Weekly Report")

    return {
        "name": "Weekly Progress Review - Couche 2",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris"},
    }


# ════════════════════════════════════════════════════════════════════
# WORKFLOW 4: Decision Review Reminder
# ════════════════════════════════════════════════════════════════════
def create_decision_review():
    nodes = []
    connections = {}

    # 1. Schedule Trigger (Friday 17:00)
    nodes.append({
        "parameters": {
            "rule": {
                "interval": [
                    {
                        "field": "cronExpression",
                        "expression": "0 17 * * 5",
                    }
                ]
            }
        },
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.3,
        "position": [0, 0],
        "id": uid(),
        "name": "Schedule Trigger",
    })

    # 2. Get Decisions (Impact = En attente)
    nodes.append(notion_get_all_node(
        "Get Pending Decisions",
        DECISIONS_DB,
        "Decision Log",
        [{"key": "Impact|select", "condition": "equals", "selectValue": "En attente"}],
        [300, 0],
    ))
    connect(connections, "Schedule Trigger", "Get Pending Decisions")

    # 3. Filter and Format
    nodes.append(code_node("Filter Old Decisions", """
const fourteenDaysAgo = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000);
const decisions = $input.all()
  .map(item => ({
    decision: item.json.name || 'Unknown',
    date: item.json.property_Date || item.json['property_Date'] || '',
    context: item.json.property_Context || '',
    optionChoisie: item.json.property_Option_choisie || item.json['property_Option choisie'] || '',
    resultatAttendu: item.json.property_Resultat_attendu || item.json['property_Resultat attendu'] || '',
    url: item.json.url || '',
  }))
  .filter(d => {
    if (!d.date) return true; // No date = include
    const dDate = new Date(typeof d.date === 'object' ? d.date.start : d.date);
    return dDate <= fourteenDaysAgo;
  });

if (decisions.length === 0) {
  return []; // Empty = stops the workflow
}

let html = '<b>\\U0001f4cb Decision Review Reminder</b>\\n\\n';
html += decisions.length + ' decision(s) en attente depuis +14 jours:\\n\\n';
decisions.forEach((d, i) => {
  html += '<b>' + (i + 1) + '. ' + d.decision + '</b>\\n';
  html += '   Date: ' + (d.date ? (typeof d.date === 'object' ? d.date.start : d.date) : 'N/A') + '\\n';
  html += '   Option: ' + d.optionChoisie + '\\n';
  html += '   Resultat attendu: ' + d.resultatAttendu + '\\n\\n';
});
html += 'Prends 5 min pour mettre a jour l\\'impact de ces decisions.';

if (html.length > 4000) {
  html = html.substring(0, 3997) + '...';
}

return [{json: {html, count: decisions.length}}];
""", [600, 0]))
    connect(connections, "Get Pending Decisions", "Filter Old Decisions")

    # 4. Telegram Send
    nodes.append(telegram_send_node(
        "Send Reminder",
        "={{ $json.html }}",
        CHAT_ID,
        [900, 0],
    ))
    connect(connections, "Filter Old Decisions", "Send Reminder")

    return {
        "name": "Decision Review Reminder - Couche 2",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris"},
    }


# ════════════════════════════════════════════════════════════════════
# COUCHE 3b — SUB-AGENT WORKFLOWS
# ════════════════════════════════════════════════════════════════════

# Common JS for extracting query from toolWorkflow trigger
EXTRACT_QUERY_JS = """
const input = $input.first().json;
const query = input.query || input.chatInput || input.text || JSON.stringify(input);
return [{json: {query}}];
"""

# Common JS for returning response to Manager
RETURN_RESPONSE_JS = """
const response = $json.content?.[0]?.text || $json.output || $json.text || JSON.stringify($json);
return [{json: {response}}];
"""

SUB_WORKFLOW_SETTINGS = {
    "executionOrder": "v1",
    "timezone": "Europe/Paris",
    "callerPolicy": "workflowsFromSameOwner",
}


def create_sub_strategy_advisor():
    """Sub-workflow: Strategy Advisor — tous domaines de vie."""
    nodes = []
    connections = {}

    # 1. Trigger
    nodes.append(execute_workflow_trigger_node("Trigger", [0, 0]))

    # 2. Extract query
    nodes.append(code_node("Extract Query", EXTRACT_QUERY_JS, [300, 0]))
    connect(connections, "Trigger", "Extract Query")

    # 3. Get Goals
    nodes.append(notion_get_all_node(
        "Get Goals", GOALS_DB_API, "Goals", [], [600, 0],
    ))
    connect(connections, "Extract Query", "Get Goals")

    # 4. Aggregate Goals
    nodes.append(code_node("Aggregate Goals", """
const query = $('Extract Query').first().json.query;
const goals = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || item.json.property_status || '',
  priority: item.json.property_Priority || item.json.property_priority || '',
  category: item.json.property_Category || item.json.property_category || '',
  progress: item.json.property_Progress || item.json['property_Progress %'] || item.json.property_progress || 0,
  strategicScore: item.json.property_Strategic_Score || item.json['property_Strategic Score'] || item.json.property_strategic_score || '',
  targetDate: item.json.property_Target_Date || item.json['property_Target Date'] || item.json.property_target_date || '',
  revenuePotential: item.json.property_Revenue_Potential || item.json['property_Revenue Potential'] || item.json.property_revenue_potential || 0,
}));
return [{json: {goals, query}}];
""", [900, 0]))
    connect(connections, "Get Goals", "Aggregate Goals")

    # 5. Wait (rate limit Notion)
    nodes.append(wait_node("Wait", [1200, 0]))
    connect(connections, "Aggregate Goals", "Wait")

    # 6. Get Decisions
    nodes.append(notion_get_all_node(
        "Get Decisions", DECISIONS_DB_API, "Decision Log", [], [1500, 0],
    ))
    connect(connections, "Wait", "Get Decisions")

    # 7. Build Context
    nodes.append(code_node("Build Context", """
const query = $('Aggregate Goals').first().json.query;
const goals = $('Aggregate Goals').first().json.goals;
const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
const decisions = $input.all()
  .map(item => ({
    decision: item.json.name || 'Unknown',
    date: item.json.property_Date || item.json.property_date || '',
    impact: item.json.property_Impact || item.json.property_impact || '',
    optionChoisie: item.json.property_Option_choisie || item.json['property_Option choisie'] || item.json.property_option_choisie || '',
    learnings: item.json.property_Learnings || item.json.property_learnings || '',
  }))
  .filter(d => {
    if (!d.date) return true;
    const dDate = new Date(typeof d.date === 'object' ? d.date.start : d.date);
    return dDate >= thirtyDaysAgo;
  });

const today = new Date().toISOString().split('T')[0];
const contextText = `QUESTION: ${query}

Date: ${today}

=== OBJECTIFS (tous domaines) ===
${goals.map(g => `- [${g.status}] ${g.name} | Cat: ${g.category} | Score: ${g.strategicScore} | Progress: ${Math.round((g.progress || 0) * 100)}% | Revenue: ${g.revenuePotential}EUR | Target: ${g.targetDate}`).join('\\n')}

=== DECISIONS RECENTES (30j) ===
${decisions.map(d => `- ${d.decision} | Impact: ${d.impact} | Learnings: ${d.learnings}`).join('\\n') || 'Aucune'}`;

return [{json: {contextText}}];
""", [1800, 0]))
    connect(connections, "Get Decisions", "Build Context")

    # 8. Claude
    system_prompt = """Tu es Orun, conseiller strategique de Chris. Tu analyses TOUS les domaines de vie (business, sport, spirituel, relationnel, apprentissage).

Contexte : Adaptive Logic, agence d'automatisation IA a Avignon, cible TPE/PME. Objectif : 2000 EUR CA d'ici fin mars 2026.

Ton role :
1. Analyse la situation basee sur les donnees Notion
2. Reponds a la question posee
3. Propose 2-3 actions concretes avec impact et effort
4. Challenge les angles morts

Regles :
- Tutoiement, ton direct, zero bullshit
- Si une idee est mauvaise, dis-le cash
- Actions concretes, pas de generalites
- Chiffres quand possible (EUR, %, deadlines)
- Max 400 mots
- Francais"""

    nodes.append(anthropic_node(
        "Claude Strategy", system_prompt,
        "={{ $json.contextText }}", [2100, 0],
    ))
    connect(connections, "Build Context", "Claude Strategy")

    # 9. Return Response
    nodes.append(code_node("Return Response", RETURN_RESPONSE_JS, [2400, 0]))
    connect(connections, "Claude Strategy", "Return Response")

    return {
        "name": "Sub: Strategy Advisor - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": SUB_WORKFLOW_SETTINGS,
    }


def create_sub_prioritizer():
    """Sub-workflow: Prioritizer — scoring WICE tous domaines."""
    nodes = []
    connections = {}

    nodes.append(execute_workflow_trigger_node("Trigger", [0, 0]))
    nodes.append(code_node("Extract Query", EXTRACT_QUERY_JS, [300, 0]))
    connect(connections, "Trigger", "Extract Query")

    nodes.append(notion_get_all_node(
        "Get Goals", GOALS_DB_API, "Goals", [], [600, 0],
    ))
    connect(connections, "Extract Query", "Get Goals")

    nodes.append(code_node("Build Context", """
const query = $('Extract Query').first().json.query;
const goals = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || item.json.property_status || '',
  priority: item.json.property_Priority || item.json.property_priority || '',
  category: item.json.property_Category || item.json.property_category || '',
  progress: item.json.property_Progress || item.json['property_Progress %'] || item.json.property_progress || 0,
  impactScore: item.json.property_Impact_Score || item.json['property_Impact Score'] || item.json.property_impact_score || '',
  effortScore: item.json.property_Effort_Score || item.json['property_Effort Score'] || item.json.property_effort_score || '',
  strategicScore: item.json.property_Strategic_Score || item.json['property_Strategic Score'] || item.json.property_strategic_score || '',
  revenuePotential: item.json.property_Revenue_Potential || item.json['property_Revenue Potential'] || item.json.property_revenue_potential || 0,
  urgency: item.json.property_Urgency || item.json.property_urgency || '',
}));

const today = new Date().toISOString().split('T')[0];
const contextText = `DEMANDE: ${query}

Date: ${today}

=== OBJECTIFS (tous domaines) ===
${goals.map(g => `- [${g.status}] ${g.name} | Cat: ${g.category} | Impact: ${g.impactScore} | Effort: ${g.effortScore} | Strategic: ${g.strategicScore} | Revenue: ${g.revenuePotential}EUR | Urgency: ${g.urgency} | Progress: ${Math.round((g.progress || 0) * 100)}%`).join('\\n')}`;

return [{json: {contextText}}];
""", [900, 0]))
    connect(connections, "Get Goals", "Build Context")

    system_prompt = """Tu es le moteur de priorisation de Chris. Ton job : scorer les objectifs avec la methodologie WICE (tous domaines de vie).

Methodologie WICE :
- Impact (35%) : revenue direct ou progression objectif de vie (1-10)
- Confidence (25%) : certitude de livraison (1-10)
- Ease (25%) : facilite d'execution (1-10)
- Alignment (15%) : alignement vision long terme (1-10)
- Score = Impact*0.35 + Confidence*0.25 + Ease*0.25 + Alignment*0.15

Regles :
- Pour chaque goal, donne le score WICE avec justification courte (1 ligne par critere)
- Challenge les scores trop optimistes
- Si Impact > 8 : quel revenu concret ?
- Si Confidence > 7 : qu'est-ce qui pourrait foirer ?
- Trie par score WICE decroissant
- Identifie les quick wins (Ease >= 7, Impact >= 6)
- Tutoiement, ton direct
- Max 500 mots
- Francais"""

    nodes.append(anthropic_node(
        "Claude Prioritizer", system_prompt,
        "={{ $json.contextText }}", [1200, 0],
    ))
    connect(connections, "Build Context", "Claude Prioritizer")

    nodes.append(code_node("Return Response", RETURN_RESPONSE_JS, [1500, 0]))
    connect(connections, "Claude Prioritizer", "Return Response")

    return {
        "name": "Sub: Prioritizer - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": SUB_WORKFLOW_SETTINGS,
    }


def create_sub_decision_logger():
    """Sub-workflow: Decision Logger — documenter decisions tous domaines."""
    nodes = []
    connections = {}

    nodes.append(execute_workflow_trigger_node("Trigger", [0, 0]))
    nodes.append(code_node("Extract Query", EXTRACT_QUERY_JS, [300, 0]))
    connect(connections, "Trigger", "Extract Query")

    nodes.append(notion_get_all_node(
        "Get Decisions", DECISIONS_DB_API, "Decision Log", [], [600, 0],
    ))
    connect(connections, "Extract Query", "Get Decisions")

    nodes.append(code_node("Aggregate Decisions", """
const query = $('Extract Query').first().json.query;
const decisions = $input.all().map(item => ({
  decision: item.json.name || 'Unknown',
  date: item.json.property_Date || item.json.property_date || '',
  impact: item.json.property_Impact || item.json.property_impact || '',
  context: item.json.property_Context || item.json.property_context || '',
  optionChoisie: item.json.property_Option_choisie || item.json['property_Option choisie'] || item.json.property_option_choisie || '',
  pourquoi: item.json.property_Pourquoi || item.json.property_pourquoi || '',
  resultatReel: item.json.property_Resultat_reel || item.json['property_Resultat reel'] || item.json.property_resultat_reel || '',
  learnings: item.json.property_Learnings || item.json.property_learnings || '',
}));
return [{json: {decisions, query}}];
""", [900, 0]))
    connect(connections, "Get Decisions", "Aggregate Decisions")

    nodes.append(wait_node("Wait", [1200, 0]))
    connect(connections, "Aggregate Decisions", "Wait")

    nodes.append(notion_get_all_node(
        "Get Goals", GOALS_DB_API, "Goals", [], [1500, 0],
    ))
    connect(connections, "Wait", "Get Goals")

    nodes.append(code_node("Build Context", """
const query = $('Aggregate Decisions').first().json.query;
const decisions = $('Aggregate Decisions').first().json.decisions;
const goals = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || item.json.property_status || '',
  category: item.json.property_Category || item.json.property_category || '',
}));

const today = new Date().toISOString().split('T')[0];
const contextText = `DEMANDE: ${query}

Date: ${today}

=== DECISIONS EXISTANTES ===
${decisions.map(d => `- ${d.decision} | Date: ${typeof d.date === 'object' ? d.date.start || '' : d.date} | Impact: ${d.impact} | Option: ${d.optionChoisie} | Resultat: ${d.resultatReel || 'En attente'} | Learnings: ${d.learnings || '-'}`).join('\\n') || 'Aucune'}

=== OBJECTIFS LIES ===
${goals.map(g => `- [${g.status}] ${g.name} | ${g.category}`).join('\\n')}`;

return [{json: {contextText}}];
""", [1800, 0]))
    connect(connections, "Get Goals", "Build Context")

    system_prompt = """Tu es le greffier strategique de Chris. Tu documentes ses decisions (tous domaines de vie).

Deux modes :

MODE 1 — Nouvelle decision :
- Identifie le contexte, les options (2-4), recommande
- Structure : Contexte / Options (pros/cons/risques) / Recommandation
- Definis des criteres de succes mesurables

MODE 2 — Mise a jour :
- Retrouve la decision dans la liste
- Documente : resultat reel vs attendu, learnings actionables

Regles :
- Tutoiement, ton direct
- Une decision = un sujet precis, pas de mega-decisions fourre-tout
- Chaque option doit avoir un contra
- Les learnings doivent etre actionables
- Si Chris hesite, pousse-le a decider
- Max 400 mots
- Francais"""

    nodes.append(anthropic_node(
        "Claude Decision Logger", system_prompt,
        "={{ $json.contextText }}", [2100, 0],
    ))
    connect(connections, "Build Context", "Claude Decision Logger")

    nodes.append(code_node("Return Response", RETURN_RESPONSE_JS, [2400, 0]))
    connect(connections, "Claude Decision Logger", "Return Response")

    return {
        "name": "Sub: Decision Logger - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": SUB_WORKFLOW_SETTINGS,
    }


def create_sub_progress_tracker():
    """Sub-workflow: Progress Tracker — diagnostic tous domaines."""
    nodes = []
    connections = {}

    nodes.append(execute_workflow_trigger_node("Trigger", [0, 0]))
    nodes.append(code_node("Extract Query", EXTRACT_QUERY_JS, [300, 0]))
    connect(connections, "Trigger", "Extract Query")

    nodes.append(notion_get_all_node(
        "Get Goals", GOALS_DB_API, "Goals", [], [600, 0],
    ))
    connect(connections, "Extract Query", "Get Goals")

    nodes.append(code_node("Aggregate Goals", """
const query = $('Extract Query').first().json.query;
const goals = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || item.json.property_status || '',
  priority: item.json.property_Priority || item.json.property_priority || '',
  category: item.json.property_Category || item.json.property_category || '',
  progress: item.json.property_Progress || item.json['property_Progress %'] || item.json.property_progress || 0,
  strategicScore: item.json.property_Strategic_Score || item.json['property_Strategic Score'] || item.json.property_strategic_score || '',
  targetDate: item.json.property_Target_Date || item.json['property_Target Date'] || item.json.property_target_date || '',
  revenuePotential: item.json.property_Revenue_Potential || item.json['property_Revenue Potential'] || item.json.property_revenue_potential || 0,
}));
return [{json: {goals, query}}];
""", [900, 0]))
    connect(connections, "Get Goals", "Aggregate Goals")

    nodes.append(wait_node("Wait", [1200, 0]))
    connect(connections, "Aggregate Goals", "Wait")

    nodes.append(notion_get_all_node(
        "Get Tasks", TASKS_DB_API, "Tasks", [], [1500, 0],
    ))
    connect(connections, "Wait", "Get Tasks")

    nodes.append(code_node("Build Context", """
const query = $('Aggregate Goals').first().json.query;
const goals = $('Aggregate Goals').first().json.goals;
const allTasks = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || item.json.property_status || '',
  dueDate: item.json.property_Due_Date || item.json['property_Due Date'] || item.json.property_due_date || '',
  completedOn: item.json.property_Completed_On || item.json['property_Completed On'] || item.json.property_completed_on || '',
  category: item.json.property_Category || item.json.property_category || '',
  revenueImpact: item.json.property_Revenue_Impact || item.json['property_Revenue Impact'] || item.json.property_revenue_impact || '',
}));

const now = new Date();
const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
const today = now.toISOString().split('T')[0];

const completedThisWeek = allTasks.filter(t => {
  if (t.status !== 'Complete') return false;
  if (!t.completedOn) return false;
  const d = new Date(typeof t.completedOn === 'object' ? t.completedOn.start : t.completedOn);
  return d >= weekAgo;
});

const overdue = allTasks.filter(t => {
  if (t.status === 'Complete' || t.status === 'Archive') return false;
  if (!t.dueDate) return false;
  const d = new Date(typeof t.dueDate === 'object' ? t.dueDate.start : t.dueDate);
  return d < now;
});

const inProgress = allTasks.filter(t => t.status === 'In Progress');
const blocked = allTasks.filter(t => t.status === 'Blocked');

const contextText = `QUESTION: ${query}

Date: ${today}

=== OBJECTIFS (tous domaines) ===
${goals.map(g => `- [${g.status}] ${g.name} | Cat: ${g.category} | Score: ${g.strategicScore} | Progress: ${Math.round((g.progress || 0) * 100)}% | Revenue: ${g.revenuePotential}EUR | Target: ${g.targetDate}`).join('\\n')}

=== METRIQUES SEMAINE ===
- Completees cette semaine: ${completedThisWeek.length}
- En cours: ${inProgress.length}
- En retard: ${overdue.length}
- Bloquees: ${blocked.length}

=== TACHES COMPLETEES (7j) ===
${completedThisWeek.map(t => `- ${t.name} | ${t.category}`).join('\\n') || 'Aucune'}

=== EN RETARD ===
${overdue.map(t => `- ${t.name} | Due: ${t.dueDate} | ${t.status}`).join('\\n') || 'Aucune'}

=== BLOQUEES ===
${blocked.map(t => `- ${t.name} | ${t.category}`).join('\\n') || 'Aucune'}`;

return [{json: {contextText}}];
""", [1800, 0]))
    connect(connections, "Get Tasks", "Build Context")

    system_prompt = """Tu es l'analyste de progression de Chris. Diagnostic sans complaisance sur TOUS les domaines de vie.

Commence TOUJOURS par un verdict brutal en une phrase. Exemples :
- "Tu es en retard de 2 semaines sur Review Autopilot et ca compromet ton objectif de CA."
- "Zero revenu genere cette semaine. Focus."
- "Tu avances bien sur 3/5 goals mais le Client Portal est un poids mort."

Puis analyse :
1. Velocity : taches completees vs semaine precedente, tendance
2. Blocages : objectifs sans mouvement depuis > 1 semaine
3. Alignement CA : progression vers 2000 EUR d'ici fin mars 2026
4. 3 recommandations concretes avec deadlines

Regles :
- Tutoiement, ton direct, zero complaisance
- Compare les faits aux objectifs, pas aux intentions
- Pas de "tu devrais envisager de..." — dis "fais X avant vendredi"
- Max 400 mots
- Francais"""

    nodes.append(anthropic_node(
        "Claude Progress", system_prompt,
        "={{ $json.contextText }}", [2100, 0],
    ))
    connect(connections, "Build Context", "Claude Progress")

    nodes.append(code_node("Return Response", RETURN_RESPONSE_JS, [2400, 0]))
    connect(connections, "Claude Progress", "Return Response")

    return {
        "name": "Sub: Progress Tracker - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": SUB_WORKFLOW_SETTINGS,
    }


def create_sub_opportunity_scout():
    """Sub-workflow: Opportunity Scout — prospection TPE/PME (business only).
    Uses Agent node with SerpAPI tool for web search."""
    nodes = []
    connections = {}

    nodes.append(execute_workflow_trigger_node("Trigger", [0, 0]))
    nodes.append(code_node("Extract Query", EXTRACT_QUERY_JS, [300, 0]))
    connect(connections, "Trigger", "Extract Query")

    nodes.append(notion_get_all_node(
        "Get Goals", GOALS_DB_API, "Goals", [], [600, 0],
    ))
    connect(connections, "Extract Query", "Get Goals")

    nodes.append(code_node("Build Context", """
const query = $('Extract Query').first().json.query;
const goals = $input.all()
  .filter(item => {
    const cat = item.json.property_Category || item.json.property_category || '';
    const status = item.json.property_Status || item.json.property_status || '';
    return status !== 'Archive' && status !== 'Abandoned';
  })
  .map(item => ({
    name: item.json.name || 'Unknown',
    status: item.json.property_Status || item.json.property_status || '',
    revenuePotential: item.json.property_Revenue_Potential || item.json['property_Revenue Potential'] || item.json.property_revenue_potential || 0,
  }));

const today = new Date().toISOString().split('T')[0];
const text = `RECHERCHE: ${query}

Date: ${today}
Objectifs business actifs: ${goals.map(g => g.name).join(', ')}

Utilise Google Search pour trouver des prospects concrets.`;

return [{json: {text}}];
""", [900, 0]))
    connect(connections, "Get Goals", "Build Context")

    system_prompt = """Tu es l'eclaireur commercial d'Adaptive Logic. Ton job : trouver des prospects TPE/PME dans la zone Avignon/Vaucluse.

Solutions disponibles :
- Review Autopilot : restaurants/hotels/commerces avec avis Google (150-300 EUR/mois)
- Client Magnet : artisans/agences immo sans lead gen (200-400 EUR/mois)
- Competitor Analysis : surveillance concurrence (100-200 EUR/mois)

Pour chaque prospect trouve :
- Nom du business
- Secteur + localisation
- Probleme identifie (concret, visible)
- Solution Adaptive Logic recommandee
- Revenu estime EUR/mois
- Prochaine action

Regles :
- UTILISE Google Search pour chaque recherche
- Cherche : avis negatifs Google, sites web obsoletes, absence reseaux sociaux
- Priorise les problemes VISIBLES (mauvais avis, pas de site)
- Zone : Avignon > Grand Avignon > Vaucluse
- Focus TPE/PME independantes, pas de chaines
- Tutoiement, ton direct
- Max 500 mots
- Francais"""

    # Agent node (with SerpAPI tool)
    nodes.append(agent_node(
        "Scout Agent", system_prompt,
        "={{ $json.text }}", [1200, 0],
    ))
    connect(connections, "Build Context", "Scout Agent")

    # LM for the Scout Agent
    nodes.append(lm_chat_anthropic_node(
        "Claude Scout LM", MODEL_ID, [1100, 300],
    ))
    connect_ai(connections, "Claude Scout LM", "Scout Agent", "ai_languageModel")

    # SerpAPI tool
    nodes.append(serp_api_node("Google Search", [1300, 300]))
    connect_ai(connections, "Google Search", "Scout Agent", "ai_tool")

    # Return Response
    nodes.append(code_node("Return Response", """
const response = $json.output || $json.text || JSON.stringify($json);
return [{json: {response}}];
""", [1500, 0]))
    connect(connections, "Scout Agent", "Return Response")

    return {
        "name": "Sub: Opportunity Scout - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": SUB_WORKFLOW_SETTINGS,
    }


# ════════════════════════════════════════════════════════════════════
# COUCHE 3b — MANAGER AGENT (main workflow)
# ════════════════════════════════════════════════════════════════════

def create_manager_agent(sub_workflow_ids):
    """Manager Agent: Telegram -> route to sub-agents.

    Args:
        sub_workflow_ids: dict mapping tool names to n8n workflow IDs.
            Keys: strategy-advisor, prioritizer, decision-logger,
                  progress-tracker, opportunity-scout
    """
    nodes = []
    connections = {}

    # 1. Telegram Trigger
    nodes.append(telegram_trigger_node(
        "Telegram Trigger", [0, 0], ORUN_TELEGRAM_CRED,
    ))

    # 2. Extract Message
    nodes.append(code_node("Extract Message", """
const msg = $json.message || {};
const text = msg.text || msg.caption || '';
const chatId = String(msg.chat?.id || '');
const firstName = msg.from?.first_name || 'Chris';

if (!text) {
  // No text content (sticker, photo without caption, etc.)
  return [{json: {text: '[message non-texte]', chatId, firstName}}];
}

return [{json: {text, chatId, firstName}}];
""", [300, 0]))
    connect(connections, "Telegram Trigger", "Extract Message")

    # 3. Manager Agent
    manager_prompt = """Tu es Orun, le Manager Agent de Chris. Tu recois ses messages Telegram.

Ton role UNIQUE : comprendre l'intention et deleguer au bon agent. Tu ne fais PAS d'analyse toi-meme.

Agents :
- strategy-advisor : analyse strategique (business ET vie perso), scenarios, challenge decisions, conseil direction de vie
- prioritizer : scorer/re-scorer les objectifs WICE (tous domaines), prioriser les goals
- decision-logger : documenter une decision ou son resultat dans le Decision Log
- progress-tracker : diagnostic progression tous objectifs, velocite, blocages, bilan
- opportunity-scout : trouver des prospects TPE/PME Avignon/Vaucluse (business only)

Regles :
1. Si ambigu, pose UNE question de clarification
2. Si clair, appelle l'agent directement avec le message complet de Chris
3. Salutations/hors-scope : reponds directement (court et sympa)
4. /strategy = strategy-advisor
5. /score ou /priorite = prioritizer
6. /decision = decision-logger
7. /progress ou /bilan = progress-tracker
8. /prospect ou /scout = opportunity-scout
9. Tutoiement, ton franc
10. Ne reformule PAS le message de Chris — passe-le tel quel a l'agent"""

    nodes.append(agent_node(
        "Manager Agent", manager_prompt,
        "={{ $json.text }}", [700, 0],
    ))
    connect(connections, "Extract Message", "Manager Agent")

    # 4. Claude Sonnet LM (connected to Manager Agent via ai_languageModel)
    nodes.append(lm_chat_anthropic_node(
        "Claude Sonnet", MODEL_ID, [500, 300],
    ))
    connect_ai(connections, "Claude Sonnet", "Manager Agent", "ai_languageModel")

    # 5. Postgres Memory (connected to Manager Agent via ai_memory)
    nodes.append(postgres_memory_node(
        "Postgres Memory",
        "=orun_{{ $('Extract Message').item.json.chatId }}",
        [700, 300],
    ))
    connect_ai(connections, "Postgres Memory", "Manager Agent", "ai_memory")

    # 6. Tool sub-workflows (connected to Manager Agent via ai_tool)
    tool_positions = {
        "strategy-advisor": [300, 500],
        "prioritizer": [500, 500],
        "decision-logger": [700, 500],
        "progress-tracker": [900, 500],
        "opportunity-scout": [1100, 500],
    }

    for tool_name, wf_id in sub_workflow_ids.items():
        display_name = f"Tool: {tool_name}"
        pos = tool_positions.get(tool_name, [600, 500])
        description = TOOL_DESCRIPTIONS.get(tool_name, tool_name)
        nodes.append(tool_workflow_node(
            display_name, tool_name, wf_id, description, pos,
        ))
        connect_ai(connections, display_name, "Manager Agent", "ai_tool")

    # 7. Format Response (Telegram HTML)
    nodes.append(code_node("Format Response", """
const response = $json.output || $json.text || JSON.stringify($json);

// Convert markdown to Telegram HTML
let html = response
  .replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
  .replace(/\\*(.+?)\\*/g, '<i>$1</i>')
  .replace(/^### (.+)$/gm, '<b>$1</b>')
  .replace(/^## (.+)$/gm, '<b>$1</b>')
  .replace(/^# (.+)$/gm, '<b>$1</b>')
  .replace(/`([^`]+)`/g, '<code>$1</code>');

// Telegram max 4096 chars
if (html.length > 4000) {
  html = html.substring(0, 3997) + '...';
}

const chatId = $('Extract Message').first().json.chatId;
return [{json: {html, chatId}}];
""", [1100, 0]))
    connect(connections, "Manager Agent", "Format Response")

    # 8. Send Response
    nodes.append({
        "parameters": {
            "chatId": "={{ $json.chatId }}",
            "text": "={{ $json.html }}",
            "additionalFields": {
                "appendAttribution": False,
                "parse_mode": "HTML",
            },
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [1400, 0],
        "id": uid(),
        "name": "Send Response",
        "credentials": ORUN_TELEGRAM_CRED,
    })
    connect(connections, "Format Response", "Send Response")

    return {
        "name": "Manager Agent - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris"},
    }


# ════════════════════════════════════════════════════════════════════
# COUCHE 3b v2 — NEW ARCHITECTURE
# Classifier + Switch + executeWorkflow (deterministic routing)
# ════════════════════════════════════════════════════════════════════

def create_web_search_subworkflow():
    """Shared Web Search sub-workflow: Agent + Claude LM + SerpAPI + Wikipedia.
    Called via toolWorkflow by strategy-advisor and opportunity-scout."""
    nodes = []
    connections = {}

    # 1. Execute Trigger (receives {query} from toolWorkflow or executeWorkflow)
    nodes.append(execute_workflow_trigger_node("Trigger", [0, 0]))

    # 2. Extract Query
    nodes.append(code_node("Extract Query", EXTRACT_QUERY_JS, [300, 0]))
    connect(connections, "Trigger", "Extract Query")

    # 3. Search Agent
    nodes.append(agent_node(
        "Search Agent",
        """Tu es un assistant de recherche web. Utilise Google Search et Wikipedia pour trouver des informations pertinentes.
Synthetise les resultats de maniere concise et factuelle.
- Cite les sources
- Si Google ne donne rien, essaie Wikipedia
- Max 300 mots
- Francais""",
        "={{ $json.query }}",
        [600, 0],
    ))
    connect(connections, "Extract Query", "Search Agent")

    # 4. Claude LM (ai_languageModel -> Search Agent)
    nodes.append(lm_chat_anthropic_node("Claude LM", MODEL_ID, [500, 300]))
    connect_ai(connections, "Claude LM", "Search Agent", "ai_languageModel")

    # 5. SerpAPI (ai_tool -> Search Agent)
    nodes.append(serp_api_node("Google Search", [700, 300]))
    connect_ai(connections, "Google Search", "Search Agent", "ai_tool")

    # 6. Wikipedia (ai_tool -> Search Agent)
    nodes.append(wikipedia_node("Wikipedia", [900, 300]))
    connect_ai(connections, "Wikipedia", "Search Agent", "ai_tool")

    # 7. Return Response
    nodes.append(code_node("Return Response", """
const response = $json.output || $json.text || JSON.stringify($json);
return [{json: {response}}];
""", [900, 0]))
    connect(connections, "Search Agent", "Return Response")

    return {
        "name": "Sub: Web Search - Couche 3b v2",
        "nodes": nodes,
        "connections": connections,
        "settings": SUB_WORKFLOW_SETTINGS,
    }


def create_sub_strategy_advisor_v2(web_search_id):
    """Strategy Advisor v2: Agent with Claude + Web Search toolWorkflow."""
    nodes = []
    connections = {}

    # 1. Trigger
    nodes.append(execute_workflow_trigger_node("Trigger", [0, 0]))

    # 2. Extract Query
    nodes.append(code_node("Extract Query", EXTRACT_QUERY_JS, [300, 0]))
    connect(connections, "Trigger", "Extract Query")

    # 3. Get Goals
    nodes.append(notion_get_all_node(
        "Get Goals", GOALS_DB_API, "Goals", [], [600, 0],
    ))
    connect(connections, "Extract Query", "Get Goals")

    # 4. Aggregate Goals
    nodes.append(code_node("Aggregate Goals", """
const query = $('Extract Query').first().json.query;
const goals = $input.all().map(item => ({
  name: item.json.name || 'Unknown',
  status: item.json.property_Status || item.json.property_status || '',
  priority: item.json.property_Priority || item.json.property_priority || '',
  category: item.json.property_Category || item.json.property_category || '',
  progress: item.json.property_Progress || item.json['property_Progress %'] || item.json.property_progress || 0,
  strategicScore: item.json.property_Strategic_Score || item.json['property_Strategic Score'] || item.json.property_strategic_score || '',
  targetDate: item.json.property_Target_Date || item.json['property_Target Date'] || item.json.property_target_date || '',
  revenuePotential: item.json.property_Revenue_Potential || item.json['property_Revenue Potential'] || item.json.property_revenue_potential || 0,
}));
return [{json: {goals, query}}];
""", [900, 0]))
    connect(connections, "Get Goals", "Aggregate Goals")

    # 5. Get Decisions (no Wait — executeWorkflow context)
    nodes.append(notion_get_all_node(
        "Get Decisions", DECISIONS_DB_API, "Decision Log", [], [1200, 0],
    ))
    connect(connections, "Aggregate Goals", "Get Decisions")

    # 6. Build Context
    nodes.append(code_node("Build Context", """
const query = $('Aggregate Goals').first().json.query;
const goals = $('Aggregate Goals').first().json.goals;
const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
const decisions = $input.all()
  .map(item => ({
    decision: item.json.name || 'Unknown',
    date: item.json.property_Date || item.json.property_date || '',
    impact: item.json.property_Impact || item.json.property_impact || '',
    optionChoisie: item.json.property_Option_choisie || item.json['property_Option choisie'] || item.json.property_option_choisie || '',
    learnings: item.json.property_Learnings || item.json.property_learnings || '',
  }))
  .filter(d => {
    if (!d.date) return true;
    const dDate = new Date(typeof d.date === 'object' ? d.date.start : d.date);
    return dDate >= thirtyDaysAgo;
  });

const today = new Date().toISOString().split('T')[0];
const contextText = `QUESTION: ${query}

Date: ${today}

=== OBJECTIFS (tous domaines) ===
${goals.map(g => `- [${g.status}] ${g.name} | Cat: ${g.category} | Score: ${g.strategicScore} | Progress: ${Math.round((g.progress || 0) * 100)}% | Revenue: ${g.revenuePotential}EUR | Target: ${g.targetDate}`).join('\\n')}

=== DECISIONS RECENTES (30j) ===
${decisions.map(d => `- ${d.decision} | Impact: ${d.impact} | Learnings: ${d.learnings}`).join('\\n') || 'Aucune'}

Si tu as besoin d informations externes pour repondre, utilise l outil Web Search.`;

return [{json: {contextText}}];
""", [1500, 0]))
    connect(connections, "Get Decisions", "Build Context")

    # 7. Strategy Agent (with Claude LM + Web Search tool)
    system_prompt = """Tu es Orun, conseiller strategique de Chris. Tu analyses TOUS les domaines de vie (business, sport, spirituel, relationnel, apprentissage).

Contexte : Adaptive Logic, agence d'automatisation IA a Avignon, cible TPE/PME. Objectif : 2000 EUR CA d'ici fin mars 2026.

Ton role :
1. Analyse la situation basee sur les donnees Notion
2. Reponds a la question posee
3. Si necessaire, recherche des informations externes via Web Search
4. Propose 2-3 actions concretes avec impact et effort
5. Challenge les angles morts

Regles :
- Tutoiement, ton direct, zero bullshit
- Si une idee est mauvaise, dis-le cash
- Actions concretes, pas de generalites
- Chiffres quand possible (EUR, %, deadlines)
- Max 400 mots
- Francais"""

    nodes.append(agent_node(
        "Strategy Agent", system_prompt,
        "={{ $json.contextText }}", [2100, 0],
    ))
    connect(connections, "Build Context", "Strategy Agent")

    # 9. Claude LM (ai_languageModel -> Strategy Agent)
    nodes.append(lm_chat_anthropic_node("Claude LM", MODEL_ID, [2000, 300]))
    connect_ai(connections, "Claude LM", "Strategy Agent", "ai_languageModel")

    # 10. Web Search tool (toolWorkflow -> Strategy Agent)
    nodes.append(tool_workflow_node(
        "Web Search", "web_search", web_search_id,
        "Recherche web : Google Search et Wikipedia. Passe ta question en parametre.",
        [2200, 300],
    ))
    connect_ai(connections, "Web Search", "Strategy Agent", "ai_tool")

    # 11. Return Response
    nodes.append(code_node("Return Response", """
const response = $json.output || $json.text || JSON.stringify($json);
return [{json: {response}}];
""", [2400, 0]))
    connect(connections, "Strategy Agent", "Return Response")

    return {
        "name": "Sub: Strategy Advisor v2 - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": SUB_WORKFLOW_SETTINGS,
    }


def create_sub_opportunity_scout_v2(web_search_id):
    """Opportunity Scout v2: Agent with Claude + Web Search toolWorkflow."""
    nodes = []
    connections = {}

    # 1. Trigger
    nodes.append(execute_workflow_trigger_node("Trigger", [0, 0]))

    # 2. Extract Query
    nodes.append(code_node("Extract Query", EXTRACT_QUERY_JS, [300, 0]))
    connect(connections, "Trigger", "Extract Query")

    # 3. Get Goals
    nodes.append(notion_get_all_node(
        "Get Goals", GOALS_DB_API, "Goals", [], [600, 0],
    ))
    connect(connections, "Extract Query", "Get Goals")

    # 4. Build Context
    nodes.append(code_node("Build Context", """
const query = $('Extract Query').first().json.query;
const goals = $input.all()
  .filter(item => {
    const cat = item.json.property_Category || item.json.property_category || '';
    const status = item.json.property_Status || item.json.property_status || '';
    return status !== 'Archive' && status !== 'Abandoned';
  })
  .map(item => ({
    name: item.json.name || 'Unknown',
    status: item.json.property_Status || item.json.property_status || '',
    revenuePotential: item.json.property_Revenue_Potential || item.json['property_Revenue Potential'] || item.json.property_revenue_potential || 0,
  }));

const today = new Date().toISOString().split('T')[0];
const text = `RECHERCHE: ${query}

Date: ${today}
Objectifs business actifs: ${goals.map(g => g.name).join(', ')}

Utilise Web Search pour trouver des prospects concrets.`;

return [{json: {text}}];
""", [900, 0]))
    connect(connections, "Get Goals", "Build Context")

    # 5. Scout Agent (with Claude LM + Web Search tool)
    system_prompt = """Tu es l'eclaireur commercial d'Adaptive Logic. Ton job : trouver des prospects TPE/PME dans la zone Avignon/Vaucluse.

Solutions disponibles :
- Review Autopilot : restaurants/hotels/commerces avec avis Google (150-300 EUR/mois)
- Client Magnet : artisans/agences immo sans lead gen (200-400 EUR/mois)
- Competitor Analysis : surveillance concurrence (100-200 EUR/mois)

Pour chaque prospect trouve :
- Nom du business
- Secteur + localisation
- Probleme identifie (concret, visible)
- Solution Adaptive Logic recommandee
- Revenu estime EUR/mois
- Prochaine action

Regles :
- UTILISE Web Search pour chaque recherche
- Cherche : avis negatifs Google, sites web obsoletes, absence reseaux sociaux
- Priorise les problemes VISIBLES (mauvais avis, pas de site)
- Zone : Avignon > Grand Avignon > Vaucluse
- Focus TPE/PME independantes, pas de chaines
- Tutoiement, ton direct
- Max 500 mots
- Francais"""

    nodes.append(agent_node(
        "Scout Agent", system_prompt,
        "={{ $json.text }}", [1200, 0],
    ))
    connect(connections, "Build Context", "Scout Agent")

    # 6. Claude LM (ai_languageModel -> Scout Agent)
    nodes.append(lm_chat_anthropic_node("Claude LM", MODEL_ID, [1100, 300]))
    connect_ai(connections, "Claude LM", "Scout Agent", "ai_languageModel")

    # 7. Web Search tool (toolWorkflow -> Scout Agent)
    nodes.append(tool_workflow_node(
        "Web Search", "web_search", web_search_id,
        "Recherche web : Google Search et Wikipedia. Passe ta question en parametre.",
        [1300, 300],
    ))
    connect_ai(connections, "Web Search", "Scout Agent", "ai_tool")

    # 8. Return Response
    nodes.append(code_node("Return Response", """
const response = $json.output || $json.text || JSON.stringify($json);
return [{json: {response}}];
""", [1500, 0]))
    connect(connections, "Scout Agent", "Return Response")

    return {
        "name": "Sub: Opportunity Scout v2 - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": SUB_WORKFLOW_SETTINGS,
    }


def create_manager_agent_v2(sub_workflow_ids):
    """Manager Agent v2: Classifier + Switch + executeWorkflow (deterministic routing).
    Includes voice message support via HuggingFace Whisper transcription.

    Args:
        sub_workflow_ids: dict mapping agent names to n8n workflow IDs.
            Keys: strategy, prioritize, decision, progress, prospect, search
    """
    nodes = []
    connections = {}

    # 1. Telegram Trigger
    nodes.append(telegram_trigger_node(
        "Telegram Trigger", [0, 0], ORUN_TELEGRAM_CRED,
    ))

    # 2. Extract & Detect (detects voice vs text, extracts chatId/firstName)
    nodes.append(code_node("Extract & Detect", """
const msg = $json.message || {};
const text = msg.text || msg.caption || '';
const chatId = String(msg.chat?.id || '');
const firstName = msg.from?.first_name || 'Chris';
const voice = msg.voice || msg.audio || null;

return [{json: {
  text: text || (voice ? '[audio]' : '[message non-texte]'),
  chatId,
  firstName,
  isVoice: !!voice,
  voiceFileId: voice?.file_id || ''
}}];
""", [250, 0]))
    connect(connections, "Telegram Trigger", "Extract & Detect")

    # 3. Is Voice? (If node — routes voice to transcription pipeline)
    nodes.append(if_node("Is Voice?", "={{ $json.isVoice ? 1 : 0 }}", [500, 0]))
    connect(connections, "Extract & Detect", "Is Voice?")

    # ── Voice pipeline (output 0 = true) ──────────────────────────────

    # 4a. Download Voice file via Telegram API (native node)
    nodes.append({
        "parameters": {
            "resource": "file",
            "fileId": "={{ $json.voiceFileId }}",
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [700, 400],
        "id": uid(),
        "name": "Download Voice",
        "credentials": ORUN_TELEGRAM_CRED,
    })
    connect(connections, "Is Voice?", "Download Voice", from_output=0)

    # 4b. Whisper Transcribe via OpenAI (native node)
    nodes.append({
        "parameters": {
            "resource": "audio",
            "operation": "transcribe",
            "options": {},
        },
        "type": "@n8n/n8n-nodes-langchain.openAi",
        "typeVersion": 1.8,
        "position": [950, 400],
        "id": uid(),
        "name": "Whisper Transcribe",
        "credentials": OPENAI_CRED,
    })
    connect(connections, "Download Voice", "Whisper Transcribe")

    # 4c. Set Transcription (format output like text path: {text, chatId, firstName})
    nodes.append(code_node("Set Transcription", """
const transcription = $json.text || '';
const chatId = $('Extract & Detect').first().json.chatId;
const firstName = $('Extract & Detect').first().json.firstName;

if (!transcription) {
  return [{json: {text: '[Audio recu - transcription echouee]', chatId, firstName}}];
}

return [{json: {text: transcription, chatId, firstName}}];
""", [1200, 400]))
    connect(connections, "Whisper Transcribe", "Set Transcription")

    # ── Both paths merge at Classifier ─────────────────────────────────

    # 5. Intent Classifier (Anthropic direct call)
    classifier_prompt = """Tu classifies les messages de Chris. Retourne UNIQUEMENT du JSON valide, rien d'autre.

Categories :
- "strategy" : analyse strategique, scenarios, conseil, direction (business ET vie perso)
- "prioritize" : scorer objectifs, prioriser goals, classement WICE
- "decision" : logger une decision, mettre a jour resultat d'une decision
- "progress" : bilan, diagnostic progression, velocite, ou j'en suis
- "prospect" : trouver clients, prospects, restaurants, commerces Avignon
- "search" : recherche internet generique, verifier une info, chercher quelque chose
- "greeting" : salutations, bonjour, salut, hors-scope

Raccourcis : /strategy=strategy, /score=prioritize, /decision=decision, /bilan=progress, /prospect=prospect, /search=search

Reponds en JSON : {"agent": "...", "query": "...", "greeting": "..."}
- agent : nom de la categorie
- query : le message original de Chris (ne pas reformuler)
- greeting : si agent=greeting, une reponse courte et sympa. Sinon vide."""

    nodes.append(anthropic_node(
        "Classifier", classifier_prompt,
        "={{ $json.text }}", [1400, 0],
    ))
    connect(connections, "Is Voice?", "Classifier", from_output=1)   # text path (false)
    connect(connections, "Set Transcription", "Classifier")           # voice path

    # 6. Parse Intent (extract JSON from Classifier response)
    nodes.append(code_node("Parse Intent", """
const raw = $json.content?.[0]?.text || $json.output || $json.text || '';
let parsed;
try {
  const jsonMatch = raw.match(/\\{[\\s\\S]*\\}/);
  parsed = JSON.parse(jsonMatch ? jsonMatch[0] : raw);
} catch (e) {
  parsed = {agent: 'greeting', query: raw, greeting: 'Hmm, je n\\'ai pas compris. Reformule ?'};
}

return [{json: {
  agent: parsed.agent || 'greeting',
  query: parsed.query || $('Extract & Detect').first().json.text,
  greeting: parsed.greeting || ''
}}];
""", [1700, 0]))
    connect(connections, "Classifier", "Parse Intent")

    # 7. Router (Switch v3.2 — 7 branches)
    rules = [
        ("strategy", "={{ $json.agent }}", "strategy"),
        ("prioritize", "={{ $json.agent }}", "prioritize"),
        ("decision", "={{ $json.agent }}", "decision"),
        ("progress", "={{ $json.agent }}", "progress"),
        ("prospect", "={{ $json.agent }}", "prospect"),
        ("search", "={{ $json.agent }}", "search"),
        ("greeting", "={{ $json.agent }}", "greeting"),
    ]
    nodes.append(switch_node("Router", rules, [2000, 0], fallback="extra"))
    connect(connections, "Parse Intent", "Router")

    # 8. executeWorkflow nodes (one per agent, connected from Switch outputs)
    exec_agents = [
        ("Exec: strategy", sub_workflow_ids.get("strategy"), 0, [2300, -600]),
        ("Exec: prioritize", sub_workflow_ids.get("prioritize"), 1, [2300, -400]),
        ("Exec: decision", sub_workflow_ids.get("decision"), 2, [2300, -200]),
        ("Exec: progress", sub_workflow_ids.get("progress"), 3, [2300, 0]),
        ("Exec: prospect", sub_workflow_ids.get("prospect"), 4, [2300, 200]),
        ("Exec: search", sub_workflow_ids.get("search"), 5, [2300, 400]),
    ]

    for exec_name, wf_id, switch_output, pos in exec_agents:
        if wf_id:
            nodes.append(execute_workflow_node(exec_name, wf_id, pos))
            connect(connections, "Router", exec_name, from_output=switch_output)
            connect(connections, exec_name, "Format Response")

    # 9. Greeting Response (direct — no sub-workflow needed)
    nodes.append(code_node("Greeting Response", """
const greeting = $json.greeting || 'Salut ! Je suis Orun, ton assistant strategique. Comment je peux t\\'aider ?';
return [{json: {response: greeting}}];
""", [2300, 600]))
    connect(connections, "Router", "Greeting Response", from_output=6)
    connect(connections, "Greeting Response", "Format Response")

    # Fallback (output 7) also goes to Greeting Response
    connect(connections, "Router", "Greeting Response", from_output=7)

    # 10. Format Response (Telegram HTML — strict sanitization)
    nodes.append(code_node("Format Response", """
const response = $json.response || $json.output || $json.text || JSON.stringify($json);

let html = response
  .replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
  .replace(/(?<!\\w)\\*([^*]+?)\\*(?!\\w)/g, '<i>$1</i>')
  .replace(/^#{1,3}\\s*(.+)$/gm, '<b>$1</b>')
  .replace(/`([^`]+)`/g, '<code>$1</code>')
  .replace(/^-{3,}$/gm, '')
  .replace(/^>\\s?/gm, '')
  .replace(/<(?!\\/?(?:b|i|u|s|code|pre|a)[ >\\/])[^>]*>/gi, '');

if (html.length > 4000) {
  html = html.substring(0, 3997) + '...';
}

const chatId = $('Extract & Detect').first().json.chatId;
return [{json: {html, chatId}}];
""", [2600, 0]))

    # 11. Send Response (Telegram)
    nodes.append({
        "parameters": {
            "chatId": "={{ $json.chatId }}",
            "text": "={{ $json.html }}",
            "additionalFields": {
                "appendAttribution": False,
                "parse_mode": "HTML",
            },
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [2900, 0],
        "id": uid(),
        "name": "Send Response",
        "credentials": ORUN_TELEGRAM_CRED,
    })
    connect(connections, "Format Response", "Send Response")

    return {
        "name": "Manager Agent v2 - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris"},
    }


# ════════════════════════════════════════════════════════════════════
# Knowledge Sub-Workflow (GitHub session logs, competences, portfolio)
# ════════════════════════════════════════════════════════════════════
def create_knowledge_subworkflow():
    """Sub-workflow: Read Chris's personal data from GitHub repos.

    Reads SESSION_INDEX.md and COMPETENCES.md from automation-projects repo.
    Input: query (what info is needed)
    Output: {response: "relevant data from repos"}
    """
    nodes = []
    connections = {}

    # 1. Trigger
    nodes.append(execute_workflow_trigger_node("Trigger", [0, 0]))

    # 2. Extract query
    nodes.append(code_node("Extract Query", """
const input = $input.first().json;
const query = input.query || input.chatInput || input.text || JSON.stringify(input);
return [{json: {query}}];
""", [250, 0]))
    connect(connections, "Trigger", "Extract Query")

    # 3. Fetch Session Index from GitHub (sequential chain)
    nodes.append({
        "parameters": {
            "url": "https://raw.githubusercontent.com/prinsechris/automation-projects/main/docs/sessions/SESSION_INDEX.md",
            "options": {"timeout": 10000},
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [500, 0],
        "id": uid(),
        "name": "Fetch Sessions",
    })
    connect(connections, "Extract Query", "Fetch Sessions")

    # 4. Fetch Competences from GitHub (chained after Sessions)
    nodes.append({
        "parameters": {
            "url": "https://raw.githubusercontent.com/prinsechris/automation-projects/main/docs/COMPETENCES.md",
            "options": {"timeout": 10000},
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [750, 0],
        "id": uid(),
        "name": "Fetch Competences",
    })
    connect(connections, "Fetch Sessions", "Fetch Competences")

    # 5. Build Context (both fetches done — access via $('NodeName'))
    nodes.append(code_node("Build Context", """
const query = $('Extract Query').first().json.query;

// Access both HTTP responses by node name
const sessionsRaw = $('Fetch Sessions').first().json;
const compRaw = $input.first().json;

// Extract text — HTTP Request v4.2 returns data as string or in .data/.body
const sessions = typeof sessionsRaw === 'string' ? sessionsRaw
  : (sessionsRaw.data || sessionsRaw.body || JSON.stringify(sessionsRaw));
const competences = typeof compRaw === 'string' ? compRaw
  : (compRaw.data || compRaw.body || JSON.stringify(compRaw));

const response = `== REQUETE ==
${query}

== SESSION LOGS (index des 20+ sessions) ==
${typeof sessions === 'string' ? sessions.substring(0, 3000) : JSON.stringify(sessions).substring(0, 3000)}

== COMPETENCES ==
${typeof competences === 'string' ? competences.substring(0, 5000) : JSON.stringify(competences).substring(0, 5000)}
`;

return [{json: {response: response.substring(0, 8000)}}];
""", [1000, 0]))
    connect(connections, "Fetch Competences", "Build Context")

    return {
        "name": "Sub: Knowledge Base - Couche 3b v3",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }


# ════════════════════════════════════════════════════════════════════
# Jina Scraper Sub-Workflow
# ════════════════════════════════════════════════════════════════════
def create_scraper_subworkflow():
    """Sub-workflow: Hybrid scraper — Jina AI Reader + custom API (31.97.54.26).

    Routing logic:
    - Keywords "reddit", "spillbox", "tiktok", "pipeline", "stats" → custom API
    - URL detected → Jina AI Reader
    - Fallback → custom API health check + error message

    Input: query (URL or command like "scrape reddit", "spillbox stats")
    Output: {response: "scraped content"}
    """
    nodes = []
    connections = {}
    CUSTOM_API = "http://31.97.54.26:8000"

    # 1. Trigger
    nodes.append(execute_workflow_trigger_node("Trigger", [0, 0]))

    # 2. Route: detect if custom API or Jina
    nodes.append(code_node("Route Request", f"""
const input = $input.first().json;
const text = (input.query || input.chatInput || input.text || '').toLowerCase();

// Custom API keywords
const customKeywords = ['reddit', 'spillbox', 'tiktok', 'pipeline', 'stats', 'stock', 'notion', 'render', 'background'];
const isCustom = customKeywords.some(k => text.includes(k));

// URL detection
const urlMatch = text.match(/https?:\\/\\/[^\\s"'<>]+/i);

// Custom API endpoint mapping
let apiEndpoint = '';
let apiMethod = 'GET';
let apiBody = null;

if (isCustom) {{
  if (text.includes('reddit')) {{
    apiEndpoint = '/scraper/reddit/scrape';
    apiMethod = 'POST';
    apiBody = {{}};
  }} else if (text.includes('spillbox') && text.includes('scrape')) {{
    apiEndpoint = '/scraper/spillbox/scrape';
    apiMethod = 'POST';
    apiBody = {{min_stock: 5}};
  }} else if (text.includes('spillbox') && text.includes('production')) {{
    apiEndpoint = '/pipeline/spillbox/production';
    apiMethod = 'POST';
    apiBody = {{}};
  }} else if (text.includes('stats')) {{
    apiEndpoint = '/pipeline/stats';
    apiMethod = 'GET';
  }} else if (text.includes('stock')) {{
    apiEndpoint = '/notion/stock';
    apiMethod = 'GET';
  }} else if (text.includes('tiktok')) {{
    apiEndpoint = '/scraper/tiktok/download';
    apiMethod = 'POST';
    apiBody = {{}};
  }} else if (text.includes('background')) {{
    apiEndpoint = '/scraper/background/scrape';
    apiMethod = 'POST';
    apiBody = {{}};
  }} else {{
    apiEndpoint = '/health';
    apiMethod = 'GET';
  }}
}}

return [{{json: {{
  mode: isCustom ? 'custom' : (urlMatch ? 'jina' : 'custom'),
  url: urlMatch ? urlMatch[0] : '',
  apiEndpoint,
  apiMethod,
  apiBody: apiBody ? JSON.stringify(apiBody) : '',
  apiUrl: '{CUSTOM_API}' + apiEndpoint,
  originalQuery: text,
  isCustom: isCustom ? 1 : 0,
}}}}];
""", [250, 0]))
    connect(connections, "Trigger", "Route Request")

    # 3. Switch: custom API vs Jina
    nodes.append(if_node("Is Custom?", "={{ $json.isCustom }}", [500, 0]))
    connect(connections, "Route Request", "Is Custom?")

    # 4a. Custom API call (output 0 = true)
    nodes.append({
        "parameters": {
            "url": "={{ $json.apiUrl }}",
            "method": "={{ $json.apiMethod }}",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.apiBody || '{}' }}",
            "options": {"timeout": 120000},
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                ],
            },
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [750, -150],
        "id": uid(),
        "name": "Custom API",
    })
    connect(connections, "Is Custom?", "Custom API", from_output=0)

    # 4b. Jina Fetch (output 1 = false)
    nodes.append({
        "parameters": {
            "url": "=https://r.jina.ai/{{ $('Route Request').first().json.url }}",
            "options": {"timeout": 30000},
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Accept", "value": "text/markdown"},
                ],
            },
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [750, 150],
        "id": uid(),
        "name": "Jina Fetch",
    })
    connect(connections, "Is Custom?", "Jina Fetch", from_output=1)

    # 5. Format Response (handles both paths)
    nodes.append(code_node("Return Response", """
const data = $json.data || $json.body || $json;
let text;

if (typeof data === 'string') {
  text = data;
} else if (data.content) {
  text = data.content;
} else {
  text = JSON.stringify(data, null, 2);
}

// Limit to 8000 chars
if (text.length > 8000) {
  text = text.substring(0, 8000) + '\\n\\n[... contenu tronque a 8000 caracteres]';
}

return [{json: {response: text}}];
""", [1050, 0]))
    connect(connections, "Custom API", "Return Response")
    connect(connections, "Jina Fetch", "Return Response")

    return {
        "name": "Sub: Web Scraper (Jina + Custom) - Couche 3b v3",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }


# ════════════════════════════════════════════════════════════════════
# Manager Agent v3 — LangChain Agent + toolWorkflow (multi-agent chaining)
# ════════════════════════════════════════════════════════════════════
def create_manager_agent_v3(sub_workflow_ids, pg_cred=None):
    """Manager Agent v3: LangChain Agent orchestrator with toolWorkflow sub-agents.

    The agent autonomously decides which tools to call and in what order,
    enabling multi-agent chaining (e.g. prioritize then strategy).

    Args:
        sub_workflow_ids: dict mapping tool names to n8n workflow IDs.
            Keys: strategy, prioritize, decision, progress, prospect, search, scrape
        pg_cred: optional Postgres credential dict {"postgres": {"id": "...", "name": "..."}}
            If provided, adds Postgres Chat Memory to the agent.
    """
    nodes = []
    connections = {}

    # 1. Telegram Trigger
    nodes.append(telegram_trigger_node(
        "Telegram Trigger", [0, 0], ORUN_TELEGRAM_CRED,
    ))

    # 2. Extract & Detect (voice vs text, chatId, firstName)
    nodes.append(code_node("Extract & Detect", """
const msg = $json.message || {};
const text = msg.text || msg.caption || '';
const chatId = String(msg.chat?.id || '');
const firstName = msg.from?.first_name || 'Chris';
const voice = msg.voice || msg.audio || null;

return [{json: {
  text: text || (voice ? '[audio]' : '[message non-texte]'),
  chatId,
  firstName,
  isVoice: !!voice,
  voiceFileId: voice?.file_id || ''
}}];
""", [250, 0]))
    connect(connections, "Telegram Trigger", "Extract & Detect")

    # 3. Is Voice?
    nodes.append(if_node("Is Voice?", "={{ $json.isVoice ? 1 : 0 }}", [500, 0]))
    connect(connections, "Extract & Detect", "Is Voice?")

    # ── Voice pipeline (output 0 = true) ──────────────────────────────

    # 4. Download Voice
    nodes.append({
        "parameters": {
            "resource": "file",
            "fileId": "={{ $json.voiceFileId }}",
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [700, 400],
        "id": uid(),
        "name": "Download Voice",
        "credentials": ORUN_TELEGRAM_CRED,
    })
    connect(connections, "Is Voice?", "Download Voice", from_output=0)

    # 5. Whisper Transcribe
    nodes.append({
        "parameters": {
            "resource": "audio",
            "operation": "transcribe",
            "options": {},
        },
        "type": "@n8n/n8n-nodes-langchain.openAi",
        "typeVersion": 1.8,
        "position": [950, 400],
        "id": uid(),
        "name": "Whisper Transcribe",
        "credentials": OPENAI_CRED,
    })
    connect(connections, "Download Voice", "Whisper Transcribe")

    # 6. Set Transcription
    nodes.append(code_node("Set Transcription", """
const transcription = $json.text || '';
const chatId = $('Extract & Detect').first().json.chatId;
const firstName = $('Extract & Detect').first().json.firstName;

if (!transcription) {
  return [{json: {text: '[Audio recu - transcription echouee]', chatId, firstName}}];
}

return [{json: {text: transcription, chatId, firstName}}];
""", [1200, 400]))
    connect(connections, "Whisper Transcribe", "Set Transcription")

    # ── Both paths merge at Agent Orchestrator ─────────────────────────

    # 7. Agent Orchestrator (LangChain Tools Agent v2)
    nodes.append(agent_node(
        "Agent Orchestrator",
        MANAGER_V3_PROMPT,
        "={{ $json.text }}",
        [1500, 0],
    ))
    connect(connections, "Is Voice?", "Agent Orchestrator", from_output=1)  # text path
    connect(connections, "Set Transcription", "Agent Orchestrator")          # voice path

    # 8. Claude LM (Anthropic chat model for the agent)
    nodes.append(lm_chat_anthropic_node(
        "Claude LM", MODEL_ID, [1300, 300], max_tokens=4096,
    ))
    connect_ai(connections, "Claude LM", "Agent Orchestrator", "ai_languageModel")

    # 8b. Memory — Postgres (persistent) or Window Buffer (in-execution)
    if pg_cred:
        memory_node = {
            "parameters": {
                "sessionIdType": "customKey",
                "sessionKey": "={{ $json.chatId || 'default' }}",
                "tableName": "n8n_chat_histories",
                "contextWindowLength": 40,
            },
            "type": "@n8n/n8n-nodes-langchain.memoryPostgresChat",
            "typeVersion": 1.1,
            "position": [1300, 200],
            "id": uid(),
            "name": "Memory",
            "credentials": pg_cred,
        }
        nodes.append(memory_node)
        connect_ai(connections, "Memory", "Agent Orchestrator", "ai_memory")
    else:
        # Window Buffer Memory — keeps last N messages within a single execution
        # Helps the agent remember tool results during multi-agent chaining
        memory_node = {
            "parameters": {
                "sessionIdType": "customKey",
                "sessionKey": "={{ $json.chatId || 'default' }}",
                "contextWindowLength": 40,
            },
            "type": "@n8n/n8n-nodes-langchain.memoryBufferWindow",
            "typeVersion": 1.3,
            "position": [1300, 200],
            "id": uid(),
            "name": "Memory",
        }
        nodes.append(memory_node)
        connect_ai(connections, "Memory", "Agent Orchestrator", "ai_memory")

    # 9+. Tool: sub-workflows
    tools = [
        ("Tool: strategy",   "strategy",   sub_workflow_ids.get("strategy"),   [1100, 500]),
        ("Tool: prioritize", "prioritize", sub_workflow_ids.get("prioritize"), [1300, 500]),
        ("Tool: decision",   "decision",   sub_workflow_ids.get("decision"),   [1500, 500]),
        ("Tool: progress",   "progress",   sub_workflow_ids.get("progress"),   [1700, 500]),
        ("Tool: prospect",   "prospect",   sub_workflow_ids.get("prospect"),   [1900, 500]),
        ("Tool: search",     "search",     sub_workflow_ids.get("search"),     [2100, 500]),
        ("Tool: scrape",     "scrape",     sub_workflow_ids.get("scrape"),     [2300, 500]),
        ("Tool: knowledge",  "knowledge",  sub_workflow_ids.get("knowledge"),  [2500, 500]),
    ]

    for node_name, tool_name, wf_id, pos in tools:
        if wf_id:
            description = TOOL_DESCRIPTIONS_V3.get(tool_name, f"Outil {tool_name}")
            nodes.append(tool_workflow_node(node_name, tool_name, wf_id, description, pos))
            connect_ai(connections, node_name, "Agent Orchestrator", "ai_tool")

    # 15. Format Response (extract agent output → Telegram HTML, with tag balancing)
    nodes.append(code_node("Format Response", """
const response = $json.output || $json.text || $json.response || JSON.stringify($json);

// Step 1: Basic markdown → HTML
let html = response
  .replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
  .replace(/(?<!\\w)\\*([^*]+?)\\*(?!\\w)/g, '<i>$1</i>')
  .replace(/^#{1,3}\\s*(.+)$/gm, '<b>$1</b>')
  .replace(/`([^`]+)`/g, '<code>$1</code>')
  .replace(/^-{3,}$/gm, '')
  .replace(/^>\\s?/gm, '');

// Step 2: Strip any HTML tags NOT allowed by Telegram
html = html.replace(/<(?!\\/?(?:b|i|u|s|code|pre|a)[ >\\/])[^>]*>/gi, '');

// Step 3: Balance tags — ensure every open tag has a matching close tag
const allowedTags = ['b', 'i', 'u', 's', 'code', 'pre'];
for (const tag of allowedTags) {
  const openRe = new RegExp('<' + tag + '(?:\\\\s[^>]*)?' + '>', 'gi');
  const closeRe = new RegExp('</' + tag + '>', 'gi');
  const opens = (html.match(openRe) || []).length;
  const closes = (html.match(closeRe) || []).length;
  if (opens > closes) {
    for (let j = 0; j < opens - closes; j++) html += '</' + tag + '>';
  } else if (closes > opens) {
    // Remove excess closing tags from the end
    for (let j = 0; j < closes - opens; j++) {
      const idx = html.lastIndexOf('</' + tag + '>');
      if (idx >= 0) html = html.substring(0, idx) + html.substring(idx + tag.length + 3);
    }
  }
}

// Step 4: Escape unmatched < and > that are not part of valid tags
html = html.replace(/<(?!\\/?(?:b|i|u|s|code|pre|a)[ >\\/])/gi, '&lt;');

if (html.length > 4000) {
  html = html.substring(0, 3990) + '...';
  // Re-balance after truncation
  for (const tag of allowedTags) {
    const openRe = new RegExp('<' + tag + '(?:\\\\s[^>]*)?' + '>', 'gi');
    const closeRe = new RegExp('</' + tag + '>', 'gi');
    const opens = (html.match(openRe) || []).length;
    const closes = (html.match(closeRe) || []).length;
    if (opens > closes) {
      for (let j = 0; j < opens - closes; j++) html += '</' + tag + '>';
    }
  }
}

const chatId = $('Extract & Detect').first().json.chatId;
return [{json: {html, chatId}}];
""", [1900, 0]))
    connect(connections, "Agent Orchestrator", "Format Response")

    # 16. Send Response (Telegram)
    nodes.append({
        "parameters": {
            "chatId": "={{ $json.chatId }}",
            "text": "={{ $json.html }}",
            "additionalFields": {
                "appendAttribution": False,
                "parse_mode": "HTML",
            },
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [2200, 0],
        "id": uid(),
        "name": "Send Response",
        "credentials": ORUN_TELEGRAM_CRED,
    })
    connect(connections, "Format Response", "Send Response")

    return {
        "name": "Manager Agent v3 - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris"},
    }


# ════════════════════════════════════════════════════════════════════
# API helpers and Main
# ════════════════════════════════════════════════════════════════════
def create_workflow(workflow_data):
    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow_data,
        timeout=30,
    )
    if resp.status_code in (200, 201):
        result = resp.json()
        return result.get("id"), result.get("name")
    else:
        print(f"  ERROR {resp.status_code}: {resp.text[:500]}")
        return None, None


def activate_workflow(wf_id):
    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS,
        timeout=15,
    )
    return resp.status_code in (200, 201)


def deactivate_workflow(wf_id):
    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows/{wf_id}/deactivate",
        headers=HEADERS,
        timeout=15,
    )
    return resp.status_code in (200, 201)


def delete_workflow(wf_id):
    """Delete a workflow by ID."""
    resp = requests.delete(
        f"{N8N_URL}/api/v1/workflows/{wf_id}",
        headers=HEADERS,
        timeout=15,
    )
    return resp.status_code in (200, 204)


def update_workflow(wf_id, workflow_data):
    """Update an existing workflow by ID (PUT)."""
    resp = requests.put(
        f"{N8N_URL}/api/v1/workflows/{wf_id}",
        headers=HEADERS,
        json=workflow_data,
        timeout=30,
    )
    if resp.status_code in (200, 201):
        result = resp.json()
        return result.get("id"), result.get("name")
    else:
        print(f"  ERROR {resp.status_code}: {resp.text[:500]}")
        return None, None


def find_postgres_credential():
    """Search for an existing Postgres credential in n8n."""
    try:
        resp = requests.get(
            f"{N8N_URL}/api/v1/credentials",
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            creds = resp.json().get("data", [])
            for cred in creds:
                if cred.get("type") == "postgres":
                    return {"postgres": {"id": cred["id"], "name": cred["name"]}}
    except Exception as e:
        print(f"  Warning: Could not list credentials: {e}")
    return None


def main_couche2():
    """Create Couche 2 workflows (original behavior)."""
    workflows = [
        ("Morning Brief", create_morning_brief),
        ("Strategy Advisor", create_strategy_advisor),
        ("Weekly Progress Review", create_weekly_progress),
        ("Decision Review Reminder", create_decision_review),
    ]

    created = []
    for name, builder in workflows:
        print(f"\n{'='*50}")
        print(f"Creating: {name}")
        wf_data = builder()
        wf_id, wf_name = create_workflow(wf_data)
        if wf_id:
            print(f"  OK: id={wf_id}, name={wf_name}")
            created.append((wf_id, wf_name))
        else:
            print(f"  FAILED to create {name}")
        time.sleep(1)

    print(f"\n{'='*50}")
    print(f"Created {len(created)}/{len(workflows)} workflows")

    if "--activate" in sys.argv:
        print("\nActivating workflows...")
        for wf_id, wf_name in created:
            ok = activate_workflow(wf_id)
            print(f"  {'OK' if ok else 'FAIL'}: {wf_name} ({wf_id})")
            time.sleep(0.5)

    return created


def main_couche3b():
    """Create Couche 3b Manager Agent + sub-agents."""
    global POSTGRES_CRED

    print("=" * 60)
    print("COUCHE 3b — Manager Agent Deployment")
    print("=" * 60)

    # Step 0: Find Postgres credential
    print("\n[Step 0] Searching for Postgres credential...")
    pg_cred = find_postgres_credential()
    if pg_cred:
        POSTGRES_CRED.update(pg_cred["postgres"])
        print(f"  Found: {pg_cred['postgres']['id']} ({pg_cred['postgres']['name']})")
    else:
        print("  WARNING: No Postgres credential found!")
        print("  The Manager Agent will be created but memory won't work.")
        print("  Create a Postgres credential in n8n UI pointing to the local DB,")
        print("  then update the Manager workflow manually.")
        print("  (Check DB_POSTGRESDB_* env vars on Hostinger for connection details)")
        if "--force" not in sys.argv:
            resp = input("  Continue without Postgres memory? (y/N): ")
            if resp.lower() != "y":
                print("  Aborted.")
                return []

    # Step 1: Create 5 sub-agent workflows
    print("\n[Step 1] Creating sub-agent workflows...")
    sub_agents = [
        ("strategy-advisor", create_sub_strategy_advisor),
        ("prioritizer", create_sub_prioritizer),
        ("decision-logger", create_sub_decision_logger),
        ("progress-tracker", create_sub_progress_tracker),
        ("opportunity-scout", create_sub_opportunity_scout),
    ]

    sub_workflow_ids = {}
    created = []
    for tool_name, builder in sub_agents:
        print(f"\n  Creating: {tool_name}")
        wf_data = builder()
        wf_id, wf_name = create_workflow(wf_data)
        if wf_id:
            print(f"    OK: id={wf_id}")
            sub_workflow_ids[tool_name] = wf_id
            created.append((wf_id, wf_name))
        else:
            print(f"    FAILED to create {tool_name}")
        time.sleep(1)

    if len(sub_workflow_ids) < 5:
        print(f"\n  WARNING: Only {len(sub_workflow_ids)}/5 sub-agents created.")
        print("  Manager will only have tools for created sub-agents.")

    # Step 2: Create Manager Agent with sub-agent IDs
    print("\n[Step 2] Creating Manager Agent...")
    manager_data = create_manager_agent(sub_workflow_ids)
    manager_id, manager_name = create_workflow(manager_data)
    if manager_id:
        print(f"  OK: id={manager_id}")
        created.append((manager_id, manager_name))
    else:
        print("  FAILED to create Manager Agent!")
        return created

    # Step 3: Deactivate Couche 2 Strategy Advisor (frees the Telegram webhook)
    print(f"\n[Step 3] Deactivating Couche 2 Strategy Advisor ({COUCHE2_STRATEGY_ADVISOR_ID})...")
    if deactivate_workflow(COUCHE2_STRATEGY_ADVISOR_ID):
        print("  OK: Couche 2 Strategy Advisor deactivated")
    else:
        print("  WARNING: Could not deactivate Couche 2 Strategy Advisor")
        print("  You may need to deactivate it manually before activating the Manager")

    time.sleep(3)  # Wait for webhook cleanup

    # Step 4: Activate Manager Agent
    if "--activate" in sys.argv:
        print(f"\n[Step 4] Activating Manager Agent ({manager_id})...")
        if activate_workflow(manager_id):
            print("  OK: Manager Agent activated!")
        else:
            print("  FAILED to activate Manager Agent")
            print("  Try activating manually in n8n UI")
    else:
        print(f"\n[Step 4] Skipped (use --activate to auto-activate)")
        print(f"  Manager ID: {manager_id}")

    # Summary
    print(f"\n{'='*60}")
    print("COUCHE 3b — Deployment Summary")
    print(f"{'='*60}")
    print(f"\nSub-agent workflows:")
    for tool_name, wf_id in sub_workflow_ids.items():
        print(f"  {tool_name}: {wf_id}")
    print(f"\nManager Agent: {manager_id}")
    print(f"Postgres Memory: {'configured' if pg_cred else 'NOT configured (TBD)'}")
    print(f"\nCouche 2 Strategy Advisor ({COUCHE2_STRATEGY_ADVISOR_ID}): deactivated")
    print(f"Couche 2 schedules (Morning Brief, Weekly, Decision Review): unchanged")

    return created


def main_couche3b_v2():
    """Deploy Couche 3b v2: delete old, create new architecture."""
    print("=" * 60)
    print("COUCHE 3b v2 — Manager Agent Refonte")
    print("=" * 60)

    created = []

    # Step 1: Deactivate and delete v1 workflows
    print("\n[Step 1] Cleaning up v1 workflows...")

    v1_to_delete = [
        ("Manager v1", V1_MANAGER_ID),
        ("Strategy Advisor v1", V1_STRATEGY_ADVISOR_ID),
        ("Opportunity Scout v1", V1_OPPORTUNITY_SCOUT_ID),
    ]

    for name, wf_id in v1_to_delete:
        print(f"  Deactivating {name} ({wf_id})...")
        deactivate_workflow(wf_id)
        time.sleep(1)
        print(f"  Deleting {name}...")
        if delete_workflow(wf_id):
            print(f"    OK: {name} deleted")
        else:
            print(f"    WARNING: Could not delete {name} (may not exist)")
        time.sleep(0.5)

    # Step 2: Create Web Search shared sub-workflow
    print("\n[Step 2] Creating Web Search sub-workflow...")
    ws_data = create_web_search_subworkflow()
    ws_id, ws_name = create_workflow(ws_data)
    if ws_id:
        print(f"  OK: id={ws_id}")
        created.append((ws_id, ws_name))
    else:
        print("  FAILED to create Web Search workflow!")
        print("  Cannot continue — strategy and scout need this.")
        return created
    time.sleep(1)

    # Step 3: Create Strategy Advisor v2 and Opportunity Scout v2
    print("\n[Step 3] Creating Strategy Advisor v2...")
    strat_data = create_sub_strategy_advisor_v2(ws_id)
    strat_id, strat_name = create_workflow(strat_data)
    if strat_id:
        print(f"  OK: id={strat_id}")
        created.append((strat_id, strat_name))
    else:
        print("  FAILED to create Strategy Advisor v2!")
    time.sleep(1)

    print("\n  Creating Opportunity Scout v2...")
    scout_data = create_sub_opportunity_scout_v2(ws_id)
    scout_id, scout_name = create_workflow(scout_data)
    if scout_id:
        print(f"  OK: id={scout_id}")
        created.append((scout_id, scout_name))
    else:
        print("  FAILED to create Opportunity Scout v2!")
    time.sleep(1)

    # Step 4: Build sub-workflow ID map for Manager v2
    sub_workflow_ids = {
        "strategy": strat_id,
        "prioritize": EXISTING_PRIORITIZER_ID,
        "decision": EXISTING_DECISION_LOGGER_ID,
        "progress": EXISTING_PROGRESS_TRACKER_ID,
        "prospect": scout_id,
        "search": ws_id,
    }

    # Check all IDs are present
    missing = [k for k, v in sub_workflow_ids.items() if not v]
    if missing:
        print(f"\n  WARNING: Missing sub-workflow IDs for: {', '.join(missing)}")
        print("  Manager will be created without those branches.")

    # Step 5: Create Manager Agent v2
    print("\n[Step 4] Creating Manager Agent v2...")
    manager_data = create_manager_agent_v2(sub_workflow_ids)
    manager_id, manager_name = create_workflow(manager_data)
    if manager_id:
        print(f"  OK: id={manager_id}")
        created.append((manager_id, manager_name))
    else:
        print("  FAILED to create Manager Agent v2!")
        return created

    # Step 6: Activation
    if "--activate" in sys.argv:
        print(f"\n[Step 5] Activating Manager Agent v2 ({manager_id})...")
        time.sleep(2)
        if activate_workflow(manager_id):
            print("  OK: Manager Agent v2 activated!")
        else:
            print("  FAILED to activate via API")
            print("  >>> Activate manually in n8n UI (webhook Telegram bug)")
    else:
        print(f"\n[Step 5] Skipped activation (use --activate)")
        print(f"  >>> Activate in n8n UI: {N8N_URL}")
        print(f"  >>> Manager ID: {manager_id}")

    # Summary
    print(f"\n{'='*60}")
    print("COUCHE 3b v2 — Deployment Summary")
    print(f"{'='*60}")
    print(f"\nNew workflows created:")
    print(f"  Web Search (shared):     {ws_id}")
    print(f"  Strategy Advisor v2:     {strat_id}")
    print(f"  Opportunity Scout v2:    {scout_id}")
    print(f"  Manager Agent v2:        {manager_id}")
    print(f"\nExisting sub-agents kept:")
    print(f"  Prioritizer:             {EXISTING_PRIORITIZER_ID}")
    print(f"  Decision Logger:         {EXISTING_DECISION_LOGGER_ID}")
    print(f"  Progress Tracker:        {EXISTING_PROGRESS_TRACKER_ID}")
    print(f"\nDeleted v1 workflows:")
    for name, wf_id in v1_to_delete:
        print(f"  {name}: {wf_id}")
    print(f"\nNext: Activate Manager v2 in n8n UI, then test with Telegram.")

    return created


def rebuild_manager():
    """Rebuild Manager Agent v2 with voice support (keeps sub-workflows intact)."""
    print("=" * 60)
    print("REBUILD Manager Agent v2 — Adding Voice Support")
    print("=" * 60)

    # Step 1: Deactivate current Manager
    print(f"\n[Step 1] Deactivating Manager ({CURRENT_MANAGER_ID})...")
    deactivate_workflow(CURRENT_MANAGER_ID)
    time.sleep(2)

    # Step 2: Delete current Manager
    print(f"[Step 2] Deleting Manager ({CURRENT_MANAGER_ID})...")
    if delete_workflow(CURRENT_MANAGER_ID):
        print("  OK: deleted")
    else:
        print("  WARNING: could not delete (may already be gone)")
    time.sleep(1)

    # Step 3: Recreate with voice support
    print("[Step 3] Creating Manager v2 with voice support...")
    sub_workflow_ids = {
        "strategy": CURRENT_STRATEGY_ID,
        "prioritize": EXISTING_PRIORITIZER_ID,
        "decision": EXISTING_DECISION_LOGGER_ID,
        "progress": EXISTING_PROGRESS_TRACKER_ID,
        "prospect": CURRENT_SCOUT_ID,
        "search": CURRENT_WEB_SEARCH_ID,
    }

    manager_data = create_manager_agent_v2(sub_workflow_ids)
    manager_id, manager_name = create_workflow(manager_data)
    if manager_id:
        print(f"  OK: id={manager_id}, name={manager_name}")
    else:
        print("  FAILED to create Manager!")
        return []

    print(f"\n{'='*60}")
    print(f"Manager v2 rebuilt: {manager_id}")
    print(f"New nodes: Extract & Detect, Is Voice?, Get File Info,")
    print(f"           Download Audio, Transcribe Audio, Set Transcription")
    print(f"\n>>> Activate from n8n UI: {N8N_URL}")
    return [(manager_id, manager_name)]


def main_couche3b_v3():
    """Deploy Couche 3b v3: LangChain Agent orchestrator replacing v2 Classifier+Switch."""
    print("=" * 60)
    print("COUCHE 3b v3 — Manager Agent (LangChain Orchestrator)")
    print("=" * 60)

    created = []

    # Step 1: Deactivate and delete Manager v2
    print(f"\n[Step 1] Deactivating Manager v2 ({CURRENT_MANAGER_ID})...")
    deactivate_workflow(CURRENT_MANAGER_ID)
    time.sleep(2)

    print(f"  Deleting Manager v2...")
    if delete_workflow(CURRENT_MANAGER_ID):
        print(f"  OK: Manager v2 deleted")
    else:
        print(f"  WARNING: Could not delete Manager v2 (may already be gone)")
    time.sleep(1)

    # Step 2: Build sub-workflow ID map (all existing, unchanged)
    sub_workflow_ids = {
        "strategy": CURRENT_STRATEGY_ID,
        "prioritize": EXISTING_PRIORITIZER_ID,
        "decision": EXISTING_DECISION_LOGGER_ID,
        "progress": EXISTING_PROGRESS_TRACKER_ID,
        "prospect": CURRENT_SCOUT_ID,
        "search": CURRENT_WEB_SEARCH_ID,
    }

    missing = [k for k, v in sub_workflow_ids.items() if not v]
    if missing:
        print(f"\n  WARNING: Missing sub-workflow IDs for: {', '.join(missing)}")

    print(f"\n  Sub-workflows (unchanged):")
    for name, wf_id in sub_workflow_ids.items():
        print(f"    {name}: {wf_id}")

    # Step 3: Create Manager Agent v3
    print(f"\n[Step 2] Creating Manager Agent v3...")
    manager_data = create_manager_agent_v3(sub_workflow_ids)
    manager_id, manager_name = create_workflow(manager_data)
    if manager_id:
        print(f"  OK: id={manager_id}")
        created.append((manager_id, manager_name))
    else:
        print("  FAILED to create Manager Agent v3!")
        return created

    # Summary
    print(f"\n{'='*60}")
    print("COUCHE 3b v3 — Deployment Summary")
    print(f"{'='*60}")
    print(f"\nManager Agent v3: {manager_id}")
    print(f"  Architecture: LangChain Agent + 6 toolWorkflow")
    print(f"  Features: multi-agent chaining, voice support, direct greetings")
    print(f"\nSub-workflows (unchanged):")
    for name, wf_id in sub_workflow_ids.items():
        print(f"  {name}: {wf_id}")
    print(f"\nDeleted: Manager v2 ({CURRENT_MANAGER_ID})")
    print(f"\n>>> Activate from n8n UI: {N8N_URL}")
    print(f">>> Manager ID: {manager_id}")

    return created


# Current v3 deployed ID (for upgrades)
CURRENT_MANAGER_V3_ID = "aGWUyr5oDb20I1zE"
CURRENT_JINA_SCRAPER_ID = "gNAlXq3Jx5RDRpvu"
CURRENT_KNOWLEDGE_ID = "Z5SkxVoXLGQERTHO"


def upgrade_v3():
    """Upgrade Manager v3: Memory + Hybrid Scraper + Knowledge Base.

    Searches for Postgres credential — if found, uses persistent memory.
    Otherwise falls back to Window Buffer Memory (in-execution, 40 messages).
    """
    print("=" * 60)
    print("UPGRADE v3 — Memory + Scraper + Knowledge")
    print("=" * 60)

    created = []

    # Step 1: Find Postgres credential (optional)
    print("\n[Step 1] Searching for Postgres credential...")
    pg_cred = find_postgres_credential()
    if pg_cred:
        print(f"  Found: {pg_cred['postgres']['id']} ({pg_cred['postgres']['name']})")
    else:
        print("  No Postgres credential → Window Buffer Memory (40 msgs)")

    # Step 2a: Create Hybrid Scraper sub-workflow (Jina + custom API)
    print("\n[Step 2a] Creating Hybrid Scraper sub-workflow...")
    scraper_data = create_scraper_subworkflow()
    scraper_id, scraper_name = create_workflow(scraper_data)
    if scraper_id:
        print(f"  OK: id={scraper_id}")
        created.append((scraper_id, scraper_name))
    else:
        print("  FAILED to create Scraper!")
        scraper_id = None
    time.sleep(1)

    # Step 2b: Create Knowledge Base sub-workflow
    print("[Step 2b] Creating Knowledge Base sub-workflow...")
    knowledge_data = create_knowledge_subworkflow()
    knowledge_id, knowledge_name = create_workflow(knowledge_data)
    if knowledge_id:
        print(f"  OK: id={knowledge_id}")
        created.append((knowledge_id, knowledge_name))
    else:
        print("  FAILED to create Knowledge Base!")
        knowledge_id = None
    time.sleep(1)

    # Step 3: Delete old scraper + old Manager v3
    print(f"\n[Step 3] Cleaning up old workflows...")
    # Delete old scraper if it exists
    if CURRENT_JINA_SCRAPER_ID:
        delete_workflow(CURRENT_JINA_SCRAPER_ID)
        print(f"  Deleted old scraper ({CURRENT_JINA_SCRAPER_ID})")
    # Delete old knowledge if it exists
    if CURRENT_KNOWLEDGE_ID:
        delete_workflow(CURRENT_KNOWLEDGE_ID)
        print(f"  Deleted old knowledge ({CURRENT_KNOWLEDGE_ID})")

    print(f"  Replacing Manager v3 ({CURRENT_MANAGER_V3_ID})...")
    deactivate_workflow(CURRENT_MANAGER_V3_ID)
    time.sleep(2)
    if delete_workflow(CURRENT_MANAGER_V3_ID):
        print(f"  OK: Manager v3 deleted")
    else:
        print(f"  WARNING: Could not delete (may already be gone)")
    time.sleep(1)

    # Step 4: Create upgraded Manager v3
    sub_workflow_ids = {
        "strategy": CURRENT_STRATEGY_ID,
        "prioritize": EXISTING_PRIORITIZER_ID,
        "decision": EXISTING_DECISION_LOGGER_ID,
        "progress": EXISTING_PROGRESS_TRACKER_ID,
        "prospect": CURRENT_SCOUT_ID,
        "search": CURRENT_WEB_SEARCH_ID,
    }
    if scraper_id:
        sub_workflow_ids["scrape"] = scraper_id
    if knowledge_id:
        sub_workflow_ids["knowledge"] = knowledge_id

    print(f"\n[Step 4] Creating Manager v3 upgraded...")
    memory_type = "Postgres" if pg_cred else "Window Buffer"
    tools_list = ', '.join(sub_workflow_ids.keys())
    print(f"  Memory: {memory_type} | Tools: {tools_list}")

    manager_data = create_manager_agent_v3(sub_workflow_ids, pg_cred=pg_cred)
    manager_id, manager_name = create_workflow(manager_data)
    if manager_id:
        print(f"  OK: id={manager_id}")
        created.append((manager_id, manager_name))
    else:
        print("  FAILED to create Manager!")
        return created

    # Step 5: Activate Manager
    print(f"\n[Step 5] Activating Manager v3 ({manager_id})...")
    time.sleep(2)
    if activate_workflow(manager_id):
        print("  OK: Manager v3 activated!")
    else:
        print("  FAILED to activate via API")
        print(f"  >>> Activate manually in n8n UI: {N8N_URL}")

    # Summary
    print(f"\n{'='*60}")
    print("UPGRADE v3 — Summary")
    print(f"{'='*60}")
    memory_type = "Postgres (persistent)" if pg_cred else "Window Buffer (in-execution, 40 msgs)"
    print(f"\nManager v3 upgraded: {manager_id}")
    print(f"  Memory: {memory_type}")
    print(f"  Scraper (Jina + Custom): {'YES (' + scraper_id + ')' if scraper_id else 'NO'}")
    print(f"  Knowledge Base: {'YES (' + knowledge_id + ')' if knowledge_id else 'NO'}")
    print(f"  Tools ({len(sub_workflow_ids)}): {', '.join(sub_workflow_ids.keys())}")
    print(f"\nDeleted: previous Manager v3 ({CURRENT_MANAGER_V3_ID})")
    if CURRENT_JINA_SCRAPER_ID:
        print(f"  + old Jina scraper ({CURRENT_JINA_SCRAPER_ID})")

    return created


def main():
    if "--upgrade-v3" in sys.argv:
        return upgrade_v3()
    elif "--couche3b-v3" in sys.argv:
        return main_couche3b_v3()
    elif "--rebuild-manager" in sys.argv:
        return rebuild_manager()
    elif "--couche3b-v2" in sys.argv:
        return main_couche3b_v2()
    elif "--couche3b" in sys.argv:
        return main_couche3b()
    else:
        return main_couche2()


if __name__ == "__main__":
    created = main()
