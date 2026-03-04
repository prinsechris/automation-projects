#!/usr/bin/env python3
"""Create n8n workflow: Daily Time Blocking.

Schedule: Every day at 6h30 (Europe/Paris)
Pipeline:
1. Schedule Trigger (CRON 30 6 * * *)
2. Compute date context (today, dayName, free window 7h-22h)
3. Query Google Calendar events for today (blocked slots: McDo, RDV, etc.)
4. Query today's Notion tasks (due today + overdue + in progress)
5. Query active habits (filter which are due today based on frequency)
6. Merge all data + compute free slots
7. Claude AI generates optimized time-blocked schedule
8. Parse schedule + fallback round-robin if Claude fails
9. Build Telegram message (formatted table)
10. Send Telegram
11. Create/update Notion page with today's planning

CRON position in the daily sequence:
  06:00  Daily Morning CRON
  06:30  Daily Time Blocking (this workflow)
  07:00  Daily Quest Generator
  08:00  Persistent Nudge (morning)
"""

import json
import requests
import uuid
import sys
import os

# ── Config ──────────────────────────────────────────────────────────
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Credentials
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}
ANTHROPIC_CRED = {"httpCustomAuth": {"id": "sE8nBT8crViDOv1E", "name": "Anthropic account"}}
# Google Calendar credential — must be created in n8n UI first
GCAL_CRED = {"googleCalendarOAuth2Api": {"id": "FWTcCAao2jLUtxOl", "name": "Google Calendar account"}}

# Notion IDs
PROJECTS_TASKS_DB = "305da200-b2d6-8145-bc16-eaee02925a14"
HABITS_DB = "305da200-b2d6-8139-b19f-d2a0d46cf7e6"

# Telegram
TELEGRAM_CHAT_ID = "7342622615"

WORKFLOW_NAME = "Daily Time Blocking"


def uid():
    return str(uuid.uuid4())


def build_workflow():
    """Build the Daily Time Blocking workflow."""

    # Node IDs
    trigger_id = uid()
    date_ctx_id = uid()
    gcal_id = uid()
    query_tasks_id = uid()
    query_habits_id = uid()
    merge_id = uid()
    build_prompt_id = uid()
    claude_id = uid()
    parse_id = uid()
    build_tg_id = uid()
    split_tg_id = uid()
    send_tg_id = uid()
    build_notion_id = uid()
    create_notion_id = uid()
    no_tasks_id = uid()

    # ── Node 1: Schedule Trigger ── 6h30 Europe/Paris
    trigger = {
        "id": trigger_id,
        "name": "Daily 6h30",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 300],
        "parameters": {
            "rule": {
                "interval": [
                    {
                        "field": "cronExpression",
                        "expression": "30 6 * * *"
                    }
                ]
            }
        },
    }

    # ── Node 2: Date Context ──
    date_ctx = {
        "id": date_ctx_id,
        "name": "Date Context",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 300],
        "parameters": {
            "jsCode": """
const now = new Date();
// Force Europe/Paris
const parisOffset = new Date().toLocaleString('en-US', {timeZone: 'Europe/Paris'});
const paris = new Date(parisOffset);

const year = paris.getFullYear();
const month = String(paris.getMonth() + 1).padStart(2, '0');
const day = String(paris.getDate()).padStart(2, '0');
const today = `${year}-${month}-${day}`;

const dayNames = ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'];
const dayName = dayNames[paris.getDay()];
const dayOfWeek = paris.getDay(); // 0=Sunday

// Google Calendar time range (full day)
const todayStart = `${today}T00:00:00+01:00`;
const todayEnd = `${today}T23:59:59+01:00`;

// Tomorrow for Notion date filter
const tomorrow = new Date(paris);
tomorrow.setDate(tomorrow.getDate() + 1);
const tYear = tomorrow.getFullYear();
const tMonth = String(tomorrow.getMonth() + 1).padStart(2, '0');
const tDay = String(tomorrow.getDate()).padStart(2, '0');
const tomorrowStr = `${tYear}-${tMonth}-${tDay}`;

return [{json: {today, dayName, dayOfWeek, todayStart, todayEnd, tomorrow: tomorrowStr}}];
"""
        },
    }

    # ── Node 3: Query Google Calendar ──
    gcal = {
        "id": gcal_id,
        "name": "Google Calendar Events",
        "type": "n8n-nodes-base.googleCalendar",
        "typeVersion": 1,
        "position": [480, 100],
        "credentials": GCAL_CRED,
        "parameters": {
            "operation": "getAll",
            "calendarId": "primary",
            "returnAll": True,
            "options": {
                "singleEvents": True,
                "timeMin": "={{$json.todayStart}}",
                "timeMax": "={{$json.todayEnd}}",
                "orderBy": "startTime",
            },
        },
        "onError": "continueRegularOutput",
        "continueOnFail": True,
    }

    # ── Node 4: Query Today's Tasks ──
    query_tasks = {
        "id": query_tasks_id,
        "name": "Query Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 300],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{PROJECTS_TASKS_DB}/query",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({"filter":{"and":[{"or":[{"property":"Due Date","date":{"equals":"' + '{{$json.today}}' + '"}},{"property":"Due Date","date":{"before":"' + '{{$json.today}}' + '"}},{"property":"Status","status":{"equals":"In Progress"}}]},{"property":"Status","status":{"does_not_equal":"Complete"}},{"property":"Status","status":{"does_not_equal":"Archive"}},{"or":[{"property":"Type","select":{"equals":"Task"}},{"property":"Type","select":{"equals":"Sub-task"}}]}]},"sorts":[{"property":"Priority","direction":"ascending"}],"page_size":20}) }}',
        },
    }

    # ── Node 5: Query Habits ──
    query_habits = {
        "id": query_habits_id,
        "name": "Query Habits",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 500],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{HABITS_DB}/query",
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
                    "property": "Status",
                    "status": {"equals": "In Progress"}
                },
                "page_size": 30
            }),
        },
    }

    # ── Node 6: Merge & Compute Free Slots ──
    merge = {
        "id": merge_id,
        "name": "Merge & Free Slots",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [740, 300],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """
// Get inputs from all 3 branches
const dateCtx = $input.all().find(i => i.json.today) || $('Date Context').first();
const ctx = dateCtx.json;

// ── Parse Google Calendar events ──
let calEvents = [];
try {
    const gcalItems = $('Google Calendar Events').all();
    for (const item of gcalItems) {
        const d = item.json;
        // Skip if error (continueOnFail)
        if (d.error || !d.start) continue;
        const startTime = d.start?.dateTime || d.start?.date;
        const endTime = d.end?.dateTime || d.end?.date;
        if (!startTime || !endTime) continue;
        const sH = new Date(startTime).toLocaleTimeString('fr-FR', {timeZone:'Europe/Paris', hour:'2-digit', minute:'2-digit', hour12:false});
        const eH = new Date(endTime).toLocaleTimeString('fr-FR', {timeZone:'Europe/Paris', hour:'2-digit', minute:'2-digit', hour12:false});
        calEvents.push({
            start: sH,
            end: eH,
            title: d.summary || 'Evenement',
            type: 'blocked'
        });
    }
} catch(e) {
    // No calendar data — full day available
    calEvents = [];
}

// ── Parse Notion tasks ──
let tasks = [];
try {
    const taskData = $('Query Tasks').first().json;
    const results = taskData.results || [];
    for (const page of results) {
        const props = page.properties || {};
        const name = props['Name']?.title?.[0]?.plain_text || props['Task Name']?.title?.[0]?.plain_text || 'Tache sans nom';
        const priority = props['Priority']?.select?.name || 'Medium';
        const difficulty = props['Difficulty']?.select?.name || 'Moderate';
        const category = props['Category']?.select?.name || '';
        const dueDate = props['Due Date']?.date?.start || '';
        const status = props['Status']?.status?.name || '';

        // Estimate duration from difficulty
        let durationMin = 60;
        if (difficulty === 'Easy' || difficulty === 'Trivial') durationMin = 30;
        else if (difficulty === 'Hard' || difficulty === 'Expert') durationMin = 120;
        else durationMin = 60; // Moderate

        const isOverdue = dueDate && dueDate < ctx.today;

        tasks.push({name, priority, difficulty, category, dueDate, status, durationMin, isOverdue});
    }
} catch(e) {
    tasks = [];
}

// ── Parse Habits due today ──
let habits = [];
try {
    const habitData = $('Query Habits').first().json;
    const results = habitData.results || [];
    const dayOfWeek = ctx.dayOfWeek; // 0=Sun

    for (const page of results) {
        const props = page.properties || {};
        const name = props['Name']?.title?.[0]?.plain_text || props['Habit']?.title?.[0]?.plain_text || '';
        if (!name) continue;

        const freqRaw = props['Frequency']?.select?.name || '1 - Daily';
        const freqNum = parseInt(freqRaw) || 1;

        // Determine if habit is due today
        let isDueToday = false;
        if (freqNum === 1) {
            isDueToday = true; // Daily
        } else if (freqNum === 7) {
            // Weekly — check specific days or default to certain days
            // Mon/Wed/Fri for 3x/week type habits
            isDueToday = [1, 3, 5].includes(dayOfWeek);
        } else if (freqNum === 2) {
            isDueToday = [1, 4].includes(dayOfWeek); // Mon, Thu
        } else if (freqNum === 3) {
            isDueToday = [1, 3, 5].includes(dayOfWeek); // Mon, Wed, Fri
        } else if (freqNum === 4) {
            isDueToday = [1, 2, 4, 5].includes(dayOfWeek); // Mon-Fri minus Wed
        } else if (freqNum === 5) {
            isDueToday = [1, 2, 3, 4, 5].includes(dayOfWeek); // Weekdays
        } else if (freqNum === 6) {
            isDueToday = dayOfWeek !== 0; // All except Sunday
        }

        if (!isDueToday) continue;

        // Estimate duration based on habit name
        let durationMin = 15;
        const nameLower = name.toLowerCase();
        if (nameLower.includes('muscul') || nameLower.includes('muscu') || nameLower.includes('gym')) {
            durationMin = 90;
        } else if (nameLower.includes('course') || nameLower.includes('running') || nameLower.includes('jogging') || nameLower.includes('cardio')) {
            durationMin = 45;
        } else if (nameLower.includes('meditation') || nameLower.includes('lecture') || nameLower.includes('read')) {
            durationMin = 30;
        } else if (nameLower.includes('stretching') || nameLower.includes('yoga')) {
            durationMin = 30;
        }

        const isSport = nameLower.includes('muscul') || nameLower.includes('muscu') || nameLower.includes('course') || nameLower.includes('running') || nameLower.includes('cardio') || nameLower.includes('gym') || nameLower.includes('sport');

        habits.push({name, frequency: freqRaw, durationMin, type: isSport ? 'sport' : 'habit'});
    }
} catch(e) {
    habits = [];
}

// ── Compute free slots ──
// Day window: 7:00 - 22:00
const dayStart = 7 * 60; // minutes from midnight
const dayEnd = 22 * 60;

// Convert calendar events to minute ranges
const blocked = calEvents.map(e => {
    const [sH, sM] = e.start.split(':').map(Number);
    const [eH, eM] = e.end.split(':').map(Number);
    return {start: sH * 60 + sM, end: eH * 60 + eM, title: e.title};
}).sort((a, b) => a.start - b.start);

// Compute free slots
let freeSlots = [];
let cursor = dayStart;
for (const b of blocked) {
    if (b.start > cursor) {
        freeSlots.push({
            start: `${String(Math.floor(cursor/60)).padStart(2,'0')}:${String(cursor%60).padStart(2,'0')}`,
            end: `${String(Math.floor(b.start/60)).padStart(2,'0')}:${String(b.start%60).padStart(2,'0')}`,
            durationMin: b.start - cursor
        });
    }
    cursor = Math.max(cursor, b.end);
}
if (cursor < dayEnd) {
    freeSlots.push({
        start: `${String(Math.floor(cursor/60)).padStart(2,'0')}:${String(cursor%60).padStart(2,'0')}`,
        end: `${String(Math.floor(dayEnd/60)).padStart(2,'0')}:${String(dayEnd%60).padStart(2,'0')}`,
        durationMin: dayEnd - cursor
    });
}

const totalFreeMin = freeSlots.reduce((s, f) => s + f.durationMin, 0);
const totalFreeHours = Math.round(totalFreeMin / 60 * 10) / 10;

return [{json: {
    ...ctx,
    calEvents,
    blocked: blocked.map(b => ({...b, start: calEvents.find(c => c.title === b.title)?.start, end: calEvents.find(c => c.title === b.title)?.end})),
    calEventsFormatted: calEvents,
    tasks,
    habits,
    freeSlots,
    totalFreeHours,
    totalTasks: tasks.length,
    totalHabits: habits.length,
    hasTasks: tasks.length > 0 || habits.length > 0
}}];
"""
        },
    }

    # ── Node 6b: Check if anything to schedule ──
    check_tasks = {
        "id": no_tasks_id,
        "name": "Has Tasks?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [960, 300],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{$json.hasTasks}}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "equals", "singleValue": True},
                    }
                ],
                "combinator": "and",
            }
        },
    }

    # ── Node 7: Build Claude Prompt ──
    build_prompt = {
        "id": build_prompt_id,
        "name": "Build Claude Prompt",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1200, 200],
        "parameters": {
            "jsCode": """
const d = $json;

const systemPrompt = `Tu es un assistant de planification quotidienne pour Chris, entrepreneur et employe McDonald's a Avignon.
Cree un planning heure par heure optimise pour sa journee.

REGLES STRICTES:
- Ne JAMAIS planifier sur les creneaux bloques (McDo, RDV, etc.)
- Sport (muscu/course): matin de preference, ou soir. JAMAIS juste avant un shift McDo.
- Taches business Critical/High en debut de journee quand l'energie est haute
- Pause de 15min entre les blocs de travail de 2h+
- Dejeuner entre 12h-14h (30min minimum) sauf si creneau bloque
- Taches faciles/admin en fin de journee
- Si peu de temps libre (<3h), garder UNIQUEMENT Critical/High + sport
- Arrondir les heures a 00, 15, 30, 45 minutes
- Retourne UNIQUEMENT un JSON valide, rien d'autre

FORMAT DE SORTIE (JSON strict):
{
  "timeBlocks": [
    {"start": "HH:MM", "end": "HH:MM", "activity": "Nom", "type": "sport|task|habit|break|meal", "priority": "Critical|High|Medium|Low", "details": "Note courte"}
  ],
  "summary": "Resume de la journee en 1 phrase",
  "tip": "Conseil motivant pour la journee"
}`;

let userMsg = `PLANNING POUR: ${d.dayName} ${d.today}

CRENEAUX BLOQUES (ne PAS toucher):
`;

if (d.calEventsFormatted && d.calEventsFormatted.length > 0) {
    for (const e of d.calEventsFormatted) {
        userMsg += `- ${e.start} - ${e.end}: ${e.title}\\n`;
    }
} else {
    userMsg += '- Aucun creneau bloque (journee libre)\\n';
}

userMsg += `
CRENEAUX LIBRES:
`;
for (const f of d.freeSlots) {
    userMsg += `- ${f.start} - ${f.end} (${f.durationMin} min libres)\\n`;
}

userMsg += `\\nTOTAL TEMPS LIBRE: ${d.totalFreeHours}h

TACHES A PLANIFIER (par priorite):
`;
if (d.tasks.length > 0) {
    for (const t of d.tasks) {
        const overdue = t.isOverdue ? ' [EN RETARD]' : '';
        userMsg += `- ${t.name} | Priorite: ${t.priority} | Difficulte: ${t.difficulty} | Duree estimee: ${t.durationMin}min${overdue}\\n`;
    }
} else {
    userMsg += '- Aucune tache\\n';
}

userMsg += `
HABITUDES/SPORT DU JOUR:
`;
if (d.habits.length > 0) {
    for (const h of d.habits) {
        userMsg += `- ${h.name} (${h.type}) | Duree: ${h.durationMin}min\\n`;
    }
} else {
    userMsg += '- Aucune habitude\\n';
}

userMsg += `
Genere le planning optimal en JSON.`;

return [{json: {...d, systemPrompt, userMsg}}];
"""
        },
    }

    # ── Node 8: Claude API ──
    claude = {
        "id": claude_id,
        "name": "Claude Time Block",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1440, 200],
        "parameters": {
            "method": "POST",
            "url": "https://api.anthropic.com/v1/messages",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "httpCustomAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "anthropic-version", "value": "2023-06-01"},
                    {"name": "content-type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({"model":"claude-sonnet-4-20250514","max_tokens":4096,"system":$json.systemPrompt,"messages":[{"role":"user","content":$json.userMsg}]}) }}',
        },
        "credentials": ANTHROPIC_CRED,
    }

    # ── Node 9: Parse Schedule + Fallback ──
    parse = {
        "id": parse_id,
        "name": "Parse Schedule",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1680, 200],
        "parameters": {
            "jsCode": """
const prev = $('Build Claude Prompt').first().json;
let schedule = null;
let usedFallback = false;

try {
    const content = $json.content?.[0]?.text || $json.content || '';
    // Extract JSON from response
    const jsonMatch = content.match(/\\{[\\s\\S]*\\}/);
    if (jsonMatch) {
        schedule = JSON.parse(jsonMatch[0]);
    }
} catch(e) {
    // fallback
}

if (!schedule || !schedule.timeBlocks || schedule.timeBlocks.length === 0) {
    // ── FALLBACK: Round-robin scheduling ──
    usedFallback = true;
    const blocks = [];
    const freeSlots = [...prev.freeSlots];

    // Sort: sport first, then tasks by priority
    const priorityOrder = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3};
    const sportHabits = prev.habits.filter(h => h.type === 'sport');
    const otherHabits = prev.habits.filter(h => h.type !== 'sport');
    const sortedTasks = [...prev.tasks].sort((a, b) => (priorityOrder[a.priority] || 2) - (priorityOrder[b.priority] || 2));

    const allItems = [
        ...sportHabits.map(h => ({name: h.name, duration: h.durationMin, type: h.type, priority: 'High'})),
        ...sortedTasks.map(t => ({name: t.name, duration: t.durationMin, type: 'task', priority: t.priority})),
        ...otherHabits.map(h => ({name: h.name, duration: h.durationMin, type: 'habit', priority: 'Medium'})),
    ];

    let slotIdx = 0;
    let slotCursor = 0; // minutes into current slot

    for (const item of allItems) {
        if (slotIdx >= freeSlots.length) break;
        const slot = freeSlots[slotIdx];
        const [sH, sM] = slot.start.split(':').map(Number);
        const slotStartMin = sH * 60 + sM;
        const currentStart = slotStartMin + slotCursor;
        const currentEnd = currentStart + item.duration;

        const [eH, eM] = slot.end.split(':').map(Number);
        const slotEndMin = eH * 60 + eM;

        if (currentEnd <= slotEndMin) {
            blocks.push({
                start: `${String(Math.floor(currentStart/60)).padStart(2,'0')}:${String(currentStart%60).padStart(2,'0')}`,
                end: `${String(Math.floor(currentEnd/60)).padStart(2,'0')}:${String(currentEnd%60).padStart(2,'0')}`,
                activity: item.name,
                type: item.type,
                priority: item.priority,
                details: ''
            });
            slotCursor += item.duration + 15; // 15min break
            // Check if remaining slot is too small
            if (slotStartMin + slotCursor >= slotEndMin) {
                slotIdx++;
                slotCursor = 0;
            }
        } else {
            slotIdx++;
            slotCursor = 0;
            // retry this item in next slot (simple approach)
        }
    }

    schedule = {
        timeBlocks: blocks,
        summary: `Planning auto-genere: ${blocks.length} blocs planifies.`,
        tip: 'Planning genere en fallback. Ajuste selon ton energie!'
    };
}

// Add calendar events as blocked entries for display
const allBlocks = [
    ...prev.calEventsFormatted.map(e => ({start: e.start, end: e.end, activity: e.title, type: 'blocked', priority: '', details: 'Creneau bloque'})),
    ...schedule.timeBlocks
].sort((a, b) => a.start.localeCompare(b.start));

return [{json: {
    ...prev,
    schedule: {...schedule, timeBlocks: allBlocks},
    usedFallback,
    summary: schedule.summary,
    tip: schedule.tip
}}];
"""
        },
    }

    # ── Node 10: Build Telegram Message ──
    build_tg = {
        "id": build_tg_id,
        "name": "Build Telegram",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1920, 100],
        "parameters": {
            "jsCode": """
const d = $json;
const blocks = d.schedule.timeBlocks || [];

const typeIcons = {
    'blocked': '\\u2B1B',
    'sport': '\\u26A1',
    'task': '\\u2705',
    'habit': '\\u2728',
    'break': '\\u2615',
    'meal': '\\u2615'
};

let msg = `<b>PLANNING DU JOUR</b> — ${d.dayName} ${d.today}\\n\\n`;

for (const b of blocks) {
    const icon = typeIcons[b.type] || '\\u25AA';
    const prio = (b.priority && b.type === 'task') ? ` [${b.priority}]` : '';
    const blocked = b.type === 'blocked' ? ' (bloque)' : '';
    msg += `<code>${b.start}-${b.end}</code>  ${icon} ${b.activity}${prio}${blocked}\\n`;
}

const taskCount = blocks.filter(b => b.type === 'task').length;
const sportCount = blocks.filter(b => b.type === 'sport').length;
const habitCount = blocks.filter(b => b.type === 'habit').length;

msg += `\\n<b>${taskCount} taches</b> | <b>${sportCount} sport</b> | <b>${habitCount} habitudes</b>`;
msg += `\\n${d.totalFreeHours}h de temps libre`;

if (d.summary) msg += `\\n\\n${d.summary}`;
if (d.tip) msg += `\\n\\n<i>${d.tip}</i>`;
if (d.usedFallback) msg += `\\n\\n<i>⚠ Planning genere en mode fallback</i>`;

return [{json: {message: msg, ...d}}];
"""
        },
    }

    # ── Node 11: Split Telegram ──
    split_tg = {
        "id": split_tg_id,
        "name": "Split Message",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2140, 100],
        "parameters": {
            "jsCode": """
const msg = $json.message;
const MAX = 4096;
const chunks = [];
let current = msg;
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

    # ── Node 12: Send Telegram ──
    send_tg = {
        "id": send_tg_id,
        "name": "Send Telegram",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [2360, 100],
        "credentials": TELEGRAM_CRED,
        "parameters": {
            "chatId": TELEGRAM_CHAT_ID,
            "text": "={{$json.text}}",
            "additionalFields": {
                "parse_mode": "HTML",
            },
        },
    }

    # ── Node 13: Build Notion Page ──
    build_notion = {
        "id": build_notion_id,
        "name": "Build Notion Page",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1920, 350],
        "parameters": {
            "jsCode": """
const d = $json;
const blocks = d.schedule.timeBlocks || [];

let content = '';
for (const b of blocks) {
    const prio = (b.priority && b.type === 'task') ? ` [${b.priority}]` : '';
    const blocked = b.type === 'blocked' ? ' (bloque)' : '';
    content += `**${b.start} - ${b.end}** | ${b.activity}${prio}${blocked}\\n\\n`;
}

if (d.summary) content += `---\\n\\n${d.summary}\\n\\n`;
if (d.tip) content += `*${d.tip}*\\n`;

const title = `Planning ${d.dayName} ${d.today}`;

// Create page via Notion API
const pageData = {
    parent: {database_id: '""" + PROJECTS_TASKS_DB + """'},
    properties: {
        'Name': {title: [{text: {content: title}}]},
        'Type': {select: {name: 'Sub-task'}},
        'Status': {status: {name: 'Ready To Start'}},
        'Due Date': {date: {start: d.today}},
        'Category': {select: {name: 'Personal'}},
    },
    children: []
};

// Build children blocks (paragraphs)
for (const b of blocks) {
    const prio = (b.priority && b.type === 'task') ? ` [${b.priority}]` : '';
    const blocked = b.type === 'blocked' ? ' (bloque)' : '';
    const text = `${b.start} - ${b.end} | ${b.activity}${prio}${blocked}`;

    pageData.children.push({
        object: 'block',
        type: 'paragraph',
        paragraph: {
            rich_text: [{
                type: 'text',
                text: {content: text},
                annotations: {bold: b.type === 'blocked'}
            }]
        }
    });
}

if (d.summary) {
    pageData.children.push({
        object: 'block', type: 'divider', divider: {}
    });
    pageData.children.push({
        object: 'block',
        type: 'paragraph',
        paragraph: {rich_text: [{type: 'text', text: {content: d.summary}}]}
    });
}

return [{json: {pageData: JSON.stringify(pageData), ...d}}];
"""
        },
    }

    # ── Node 14: Create Notion Page ──
    create_notion = {
        "id": create_notion_id,
        "name": "Create Planning Page",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2140, 350],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": "https://api.notion.com/v1/pages",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{$json.pageData}}",
        },
    }

    # ── Connections ──
    connections = {
        "Daily 6h30": {"main": [[{"node": "Date Context", "type": "main", "index": 0}]]},
        "Date Context": {"main": [[
            {"node": "Google Calendar Events", "type": "main", "index": 0},
            {"node": "Query Tasks", "type": "main", "index": 0},
            {"node": "Query Habits", "type": "main", "index": 0},
        ]]},
        "Google Calendar Events": {"main": [[{"node": "Merge & Free Slots", "type": "main", "index": 0}]]},
        "Query Tasks": {"main": [[{"node": "Merge & Free Slots", "type": "main", "index": 0}]]},
        "Query Habits": {"main": [[{"node": "Merge & Free Slots", "type": "main", "index": 0}]]},
        "Merge & Free Slots": {"main": [[{"node": "Has Tasks?", "type": "main", "index": 0}]]},
        "Has Tasks?": {"main": [
            [{"node": "Build Claude Prompt", "type": "main", "index": 0}],
            []  # false = nothing to schedule
        ]},
        "Build Claude Prompt": {"main": [[{"node": "Claude Time Block", "type": "main", "index": 0}]]},
        "Claude Time Block": {"main": [[{"node": "Parse Schedule", "type": "main", "index": 0}]]},
        "Parse Schedule": {"main": [[
            {"node": "Build Telegram", "type": "main", "index": 0},
            {"node": "Build Notion Page", "type": "main", "index": 0},
        ]]},
        "Build Telegram": {"main": [[{"node": "Split Message", "type": "main", "index": 0}]]},
        "Split Message": {"main": [[{"node": "Send Telegram", "type": "main", "index": 0}]]},
        "Build Notion Page": {"main": [[{"node": "Create Planning Page", "type": "main", "index": 0}]]},
    }

    workflow = {
        "name": WORKFLOW_NAME,
        "nodes": [
            trigger, date_ctx, gcal, query_tasks, query_habits,
            merge, check_tasks, build_prompt, claude, parse,
            build_tg, split_tg, send_tg, build_notion, create_notion,
        ],
        "connections": connections,
        # "active": False — set via separate PATCH call
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Paris",
            "saveManualExecutions": True,
        },
    }

    return workflow


def deploy_workflow(workflow):
    """Deploy to n8n or save as JSON file."""
    if not N8N_API_KEY:
        # Save as JSON for manual import
        output_path = os.path.join(os.path.dirname(__file__), "daily_time_blocking_workflow.json")
        with open(output_path, "w") as f:
            json.dump(workflow, f, indent=2, ensure_ascii=False)
        print(f"[INFO] No API key. Workflow saved to: {output_path}")
        print("[INFO] Import manually in n8n: Workflows > Import from File")
        return None

    # Try API deployment
    try:
        resp = requests.post(
            f"{N8N_URL}/api/v1/workflows",
            headers=HEADERS,
            json=workflow,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            wf_id = data.get("id", "unknown")
            print(f"[OK] Workflow created: {WORKFLOW_NAME} (ID: {wf_id})")

            # Activate
            act_resp = requests.patch(
                f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
                headers=HEADERS,
                timeout=10,
            )
            if act_resp.status_code == 200:
                print(f"[OK] Workflow activated")
            else:
                print(f"[WARN] Activation failed: {act_resp.status_code}")

            return wf_id
        elif resp.status_code == 401:
            print("[ERROR] API key expired/invalid (401). Saving as JSON instead.")
            output_path = os.path.join(os.path.dirname(__file__), "daily_time_blocking_workflow.json")
            with open(output_path, "w") as f:
                json.dump(workflow, f, indent=2, ensure_ascii=False)
            print(f"[INFO] Workflow saved to: {output_path}")
            return None
        else:
            print(f"[ERROR] API returned {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"[ERROR] {e}")
        return None


if __name__ == "__main__":
    print(f"Building workflow: {WORKFLOW_NAME}")
    wf = build_workflow()
    deploy_workflow(wf)
