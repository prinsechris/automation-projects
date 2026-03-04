#!/usr/bin/env python3
"""Create n8n workflow: Sport Coach AI Agent.

Sub-workflow called by Weekly Time Blocks Generator.
Uses Claude as a sport specialist to generate weekly training programs.

Features:
- Musculation 4x/week: calisthenics + force (athletic, combat sports, flexibility)
- Course a pied 5x/week: progressive overload for beginner restart
- 2 rest days (no running), 3 rest days (no musculation)
- Never overlap muscu + course on same session (can be same day, different times)
- Periodization: progressive week over week
- Detailed sessions: exercises, sets, reps, rest times
- Adapts to available equipment (home + gym mix)
"""

import json
import os
import uuid

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = open(os.path.expanduser("~/.n8n-api-key")).read().strip()
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

ANTHROPIC_CRED = {"httpCustomAuth": {"id": "sE8nBT8crViDOv1E", "name": "Anthropic account"}}
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}

TELEGRAM_CHAT_ID = "7342622615"
TIME_BLOCKS_DB = "51eceb13-346a-4f7e-a07f-724b6d8b2c81"

WORKFLOW_NAME = "Sport Coach AI"

SPORT_SYSTEM_PROMPT = r"""Tu es un coach sportif expert en calisthenics, musculation fonctionnelle, force athletique et course a pied.

PROFIL DE L'ATHLETE:
- Chris, 20+ ans, homme, Avignon
- Niveau: DEBUTANT EN REPRISE apres longue pause
- Objectifs: etre fort, athletique, souple, endurant. Pret pour sports de combat, parkour, tout sport.
- Equipement: mix maison (barre de traction, sol) + salle de sport (machines, barres, halteres)
- Approche: calisthenics prioritaire + force avec charges pour la base

PROGRAMME MUSCULATION (4 seances/semaine):
- Split recommande: Upper/Lower ou Push/Pull/Legs adapte
- Base calisthenics: pompes (variantes), tractions (variantes), dips, muscle-ups (progressions), L-sit, handstand
- Base force: squat, deadlift, overhead press, rowing
- Mobilite/souplesse: 10min stretching chaque seance
- Progression: ajouter 1-2 reps ou une variante plus dure chaque semaine
- Temps de seance: 60-75min (echauffement inclus)

PROGRAMME COURSE A PIED (5 seances/semaine, 2 jours repos):
- REPRISE PROGRESSIVE: commencer par run/walk alternance
- Semaine 1-2: 20-25min (2min course / 1min marche)
- Semaine 3-4: 25-30min (3min course / 1min marche)
- Semaine 5-6: 30min (5min course / 1min marche)
- Semaine 7+: 30-35min course continue
- Varier: endurance facile (80%), tempo (10%), intervalles (10%)
- Temps de seance: 30-45min (echauffement + retour au calme inclus)

REGLES DE PLANNING:
- JAMAIS muscu + course dans la meme seance
- Peut etre le meme jour si espace de 6h+ entre les deux
- Jours de repos COMPLET: au moins 1 jour/semaine sans rien
- Apres une seance jambes intense, pas de course le lendemain
- Alterner intensites: jour dur / jour facile

FORMAT JSON STRICT:
{
  "weekNumber": 1,
  "sessions": [
    {
      "day": "Lundi",
      "date": "2026-03-10",
      "type": "musculation|course|repos",
      "title": "Upper Body — Push Focus",
      "duration": 70,
      "warmup": "5min mobilite epaules + 2min jumping jacks",
      "exercises": [
        {"name": "Pompes diamant", "sets": 3, "reps": "8-10", "rest": "90s", "notes": "Si trop dur: pompes genoux"},
        {"name": "Tractions pronation", "sets": 3, "reps": "max (objectif 5+)", "rest": "2min", "notes": "Bande elastique si besoin"}
      ],
      "cooldown": "10min stretching upper body",
      "intensity": "moderate",
      "notes": "Focus forme, pas charge. Temps sous tension."
    },
    {
      "day": "Lundi",
      "date": "2026-03-10",
      "type": "course",
      "title": "Course facile — Reprise",
      "duration": 25,
      "warmup": "5min marche rapide",
      "exercises": [
        {"name": "Alternance course/marche", "sets": 8, "reps": "2min course + 1min marche", "rest": "-", "notes": "Rythme conversationnel"}
      ],
      "cooldown": "5min marche + stretching jambes",
      "intensity": "easy",
      "notes": "L'objectif est de FINIR, pas d'aller vite"
    }
  ],
  "weekSummary": "Semaine 1 de reprise: focus technique et volume bas",
  "progression": "Semaine prochaine: ajouter 1 rep sur chaque exercice muscu, ajouter 30s aux intervals course"
}"""


def uid():
    return str(uuid.uuid4())


def build_workflow():
    trigger_id = uid()
    week_ctx_id = uid()
    get_history_id = uid()
    build_prompt_id = uid()
    claude_id = uid()
    parse_id = uid()
    split_id = uid()
    create_block_id = uid()
    build_tg_id = uid()
    send_tg_id = uid()

    # Trigger: called by Weekly Planner OR manual
    trigger = {
        "id": trigger_id,
        "name": "Trigger",
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [0, 300],
        "parameters": {},
    }

    # Also add manual trigger for testing
    manual_trigger_id = uid()
    manual_trigger = {
        "id": manual_trigger_id,
        "name": "Manual Test",
        "type": "n8n-nodes-base.manualTrigger",
        "typeVersion": 1,
        "position": [0, 500],
        "parameters": {},
    }

    # Week context (from parent or compute locally)
    week_ctx = {
        "id": week_ctx_id,
        "name": "Week Context",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [240, 400],
        "parameters": {
            "jsCode": """
// Get dates from parent workflow or compute for next week
const input = $json || {};
let weekStart = input.weekStart || '';
let weekEnd = input.weekEnd || '';
let calEvents = input.calEvents || [];

if (!weekStart) {
    // Compute next week
    const now = new Date(new Date().toLocaleString('en-US', {timeZone: 'Europe/Paris'}));
    const dayOfWeek = now.getDay();
    const daysUntilMon = dayOfWeek === 0 ? 1 : (8 - dayOfWeek);
    const monday = new Date(now);
    monday.setDate(now.getDate() + daysUntilMon);

    const dates = [];
    const dayNames = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
    for (let i = 0; i < 7; i++) {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        const iso = d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
        dates.push({date: iso, dayName: dayNames[i]});
    }
    weekStart = dates[0].date;
    weekEnd = dates[6].date;
}

// Compute week number since start of program (for periodization)
const programStart = '2026-03-04'; // Adjust as needed
const daysSinceStart = Math.floor((new Date(weekStart) - new Date(programStart)) / (1000*60*60*24));
const weekNumber = Math.max(1, Math.floor(daysSinceStart / 7) + 1);

return [{json: {weekStart, weekEnd, calEvents, weekNumber}}];
"""
        },
    }

    # Build Claude prompt
    build_prompt = {
        "id": build_prompt_id,
        "name": "Build Sport Prompt",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [480, 400],
        "parameters": {
            "jsCode": """
const d = $json;
const systemPrompt = `""" + SPORT_SYSTEM_PROMPT.replace('`', '\\`') + """`;

let userMsg = 'Genere le programme sportif pour la SEMAINE ' + d.weekNumber + ' (du ' + d.weekStart + ' au ' + d.weekEnd + ').\\n\\n';

if (d.calEvents && d.calEvents.length > 0) {
    userMsg += 'CRENEAUX BLOQUES (Google Calendar — ne pas planifier de sport ici):\\n';
    for (const e of d.calEvents) {
        userMsg += '- ' + e.date + ' ' + e.start + '-' + e.end + ': ' + e.title + '\\n';
    }
    userMsg += '\\n';
}

userMsg += 'Musculation: 4 seances cette semaine\\n';
userMsg += 'Course: 5 seances cette semaine (2 jours de repos course)\\n';
userMsg += 'Au moins 1 jour de repos COMPLET (ni muscu ni course)\\n\\n';
userMsg += 'Genere le JSON avec les seances detaillees.';

return [{json: {...d, systemPrompt, userMsg}}];
"""
        },
    }

    # Claude API call
    claude = {
        "id": claude_id,
        "name": "Claude Sport Coach",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [720, 400],
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
            "jsonBody": '={{ JSON.stringify({"model":"claude-sonnet-4-20250514","max_tokens":8000,"system":$json.systemPrompt,"messages":[{"role":"user","content":$json.userMsg}]}) }}',
        },
        "credentials": ANTHROPIC_CRED,
    }

    # Parse response
    parse = {
        "id": parse_id,
        "name": "Parse Sport Plan",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [960, 400],
        "parameters": {
            "jsCode": r"""
const prev = $('Build Sport Prompt').first().json;
let plan = null;

try {
    const content = $json.content?.[0]?.text || '';
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (jsonMatch) plan = JSON.parse(jsonMatch[0]);
} catch(e) {}

if (!plan || !plan.sessions) {
    return [{json: {blocks: [], totalBlocks: 0, error: 'Parse failed', weekStart: prev.weekStart}}];
}

// Convert sessions to Time Blocks format
const blocks = [];
for (const session of plan.sessions) {
    if (session.type === 'repos') continue;

    // Build exercise description for the block notes
    let exerciseList = '';
    if (session.exercises) {
        for (const ex of session.exercises) {
            exerciseList += ex.name + ': ' + ex.sets + 'x' + ex.reps;
            if (ex.rest && ex.rest !== '-') exerciseList += ' (repos ' + ex.rest + ')';
            exerciseList += '\n';
        }
    }

    const notesText = (session.warmup ? 'Echauffement: ' + session.warmup + '\n' : '') +
                      exerciseList +
                      (session.cooldown ? 'Retour au calme: ' + session.cooldown + '\n' : '') +
                      (session.notes ? '\n' + session.notes : '');

    blocks.push({
        block: session.title,
        type: session.type === 'course' ? 'Sport' : 'Sport',
        date: session.date,
        duration: session.duration || 60,
        intensity: session.intensity || 'moderate',
        notes: notesText.substring(0, 2000),
        sportType: session.type,
    });
}

// Build Telegram recap
let tgMsg = '<b>Programme Sport — Semaine ' + (plan.weekNumber || '?') + '</b>\n';
tgMsg += prev.weekStart + ' au ' + prev.weekEnd + '\n\n';

const dayOrder = ['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'];
for (const day of dayOrder) {
    const daySessions = plan.sessions.filter(s => s.day === day);
    if (daySessions.length === 0) continue;

    for (const s of daySessions) {
        if (s.type === 'repos') {
            tgMsg += '<i>' + day + ': REPOS</i>\n';
        } else {
            const icon = s.type === 'course' ? '\u{1F3C3}' : '\u{1F4AA}';
            tgMsg += icon + ' <b>' + day + '</b>: ' + s.title + ' (' + s.duration + 'min)\n';
            if (s.exercises) {
                for (const ex of s.exercises.slice(0, 4)) {
                    tgMsg += '  ' + ex.name + ' ' + ex.sets + 'x' + ex.reps + '\n';
                }
                if (s.exercises.length > 4) tgMsg += '  +' + (s.exercises.length - 4) + ' exercices...\n';
            }
        }
    }
}

if (plan.weekSummary) tgMsg += '\n' + plan.weekSummary;
if (plan.progression) tgMsg += '\n\n<i>Prochaine semaine: ' + plan.progression + '</i>';

return [{json: {blocks, totalBlocks: blocks.length, tgMsg, weekStart: prev.weekStart, weekEnd: prev.weekEnd, plan}}];
"""
        },
    }

    # Split blocks
    split = {
        "id": split_id,
        "name": "Split Sessions",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1200, 300],
        "parameters": {
            "jsCode": """
const data = $json;
if (!data.blocks || data.blocks.length === 0) return [{json: {skip: true}}];
return data.blocks.map(b => ({json: {...b, weekStart: data.weekStart, tgMsg: data.tgMsg}}));
"""
        },
    }

    # Create time blocks in Notion
    create_block = {
        "id": create_block_id,
        "name": "Create Sport Block",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1420, 300],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": "https://api.notion.com/v1/pages",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Notion-Version", "value": "2022-06-28"},
                {"name": "Content-Type", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({parent: {database_id: "' + TIME_BLOCKS_DB + '"}, properties: {"Block": {title: [{text: {content: $json.block}}]}, "Type": {select: {name: "Sport"}}, "Start": {date: {start: $json.date + "T07:00:00"}}, "Duration": {number: $json.duration}, "Priority": {select: {name: "High"}}, "Notes": {rich_text: [{text: {content: ($json.notes || "").substring(0, 2000)}}]}}}) }}',
        },
    }

    # Build Telegram recap
    build_tg = {
        "id": build_tg_id,
        "name": "Prep Telegram",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1640, 300],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """
const first = $input.all()[0]?.json || {};
const tgMsg = first.tgMsg || 'Programme sport genere.';
// Split if too long
const MAX = 4096;
const chunks = [];
let current = tgMsg;
while (current.length > MAX) {
    let cut = current.lastIndexOf('\\n', MAX);
    if (cut <= 0) cut = MAX;
    chunks.push(current.slice(0, cut));
    current = current.slice(cut);
}
chunks.push(current);
return chunks.map(c => ({json: {text: c}}));
"""
        },
    }

    # Send Telegram
    send_tg = {
        "id": send_tg_id,
        "name": "Send Sport Plan",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [1860, 300],
        "credentials": TELEGRAM_CRED,
        "parameters": {
            "chatId": TELEGRAM_CHAT_ID,
            "text": "={{$json.text}}",
            "additionalFields": {"parse_mode": "HTML"},
        },
    }

    connections = {
        "Trigger": {"main": [[{"node": "Week Context", "type": "main", "index": 0}]]},
        "Manual Test": {"main": [[{"node": "Week Context", "type": "main", "index": 0}]]},
        "Week Context": {"main": [[{"node": "Build Sport Prompt", "type": "main", "index": 0}]]},
        "Build Sport Prompt": {"main": [[{"node": "Claude Sport Coach", "type": "main", "index": 0}]]},
        "Claude Sport Coach": {"main": [[{"node": "Parse Sport Plan", "type": "main", "index": 0}]]},
        "Parse Sport Plan": {"main": [[{"node": "Split Sessions", "type": "main", "index": 0}]]},
        "Split Sessions": {"main": [[{"node": "Create Sport Block", "type": "main", "index": 0}]]},
        "Create Sport Block": {"main": [[{"node": "Prep Telegram", "type": "main", "index": 0}]]},
        "Prep Telegram": {"main": [[{"node": "Send Sport Plan", "type": "main", "index": 0}]]},
    }

    return {
        "name": WORKFLOW_NAME,
        "nodes": [trigger, manual_trigger, week_ctx, build_prompt, claude, parse, split, create_block, build_tg, send_tg],
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris", "saveManualExecutions": True},
    }


if __name__ == "__main__":
    import requests
    print(f"Building workflow: {WORKFLOW_NAME}")
    wf = build_workflow()

    resp = requests.post(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, json=wf, timeout=30)
    if resp.status_code in (200, 201):
        data = resp.json()
        wf_id = data.get("id", "?")
        print(f"[OK] Created: {wf_id}")
        act = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS, timeout=10)
        print(f"[OK] Active: {act.status_code == 200}")
    else:
        print(f"[ERROR] {resp.status_code}: {resp.text[:300]}")
