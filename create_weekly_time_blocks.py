#!/usr/bin/env python3
"""Create n8n workflow: Weekly Time Blocks Generator.

Schedule: Every Sunday at 20h00 (Europe/Paris)
Pipeline:
1. Schedule Trigger (CRON 0 20 * * 0)
2. Compute next week dates (Monday-Sunday)
3. Query recurring templates from Time Blocks DB (Recurrence != None)
4. Generate new blocks for next week (duplicate templates with new dates)
5. Also query Google Calendar for next week events (blocked slots)
6. Create blocks in Time Blocks DB via Notion API
7. Send Telegram recap

This ensures the Time Blocks DB is pre-populated each week with recurring items.
"""

import json
import os
import uuid

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = os.environ.get("N8N_API_KEY", open(os.path.expanduser("~/.n8n-api-key")).read().strip() if os.path.exists(os.path.expanduser("~/.n8n-api-key")) else "")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}
GCAL_CRED = {"googleCalendarOAuth2Api": {"id": "FWTcCAao2jLUtxOl", "name": "Google Calendar account"}}

TIME_BLOCKS_DB = "51eceb13-346a-4f7e-a07f-724b6d8b2c81"
TELEGRAM_CHAT_ID = "7342622615"
WORKFLOW_NAME = "Weekly Time Blocks Generator"


def uid():
    return str(uuid.uuid4())


def build_workflow():
    trigger_id = uid()
    week_ctx_id = uid()
    query_gcal_id = uid()
    query_tasks_id = uid()
    generate_blocks_id = uid()
    split_blocks_id = uid()
    create_block_id = uid()
    build_recap_id = uid()
    send_tg_id = uid()

    trigger = {
        "id": trigger_id,
        "name": "Sunday 20h",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 300],
        "parameters": {
            "rule": {"interval": [{"field": "cronExpression", "expression": "0 20 * * 0"}]}
        },
    }

    week_ctx = {
        "id": week_ctx_id,
        "name": "Next Week Context",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 300],
        "parameters": {
            "jsCode": """
const now = new Date(new Date().toLocaleString('en-US', {timeZone: 'Europe/Paris'}));
// Next Monday
const dayOfWeek = now.getDay(); // 0=Sun
const daysUntilMon = dayOfWeek === 0 ? 1 : (8 - dayOfWeek);
const monday = new Date(now);
monday.setDate(now.getDate() + daysUntilMon);

const dates = [];
const dayNames = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    const iso = d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
    dates.push({date: iso, dayName: dayNames[i], dayOfWeek: i + 1}); // 1=Mon
}

const weekStart = dates[0].date;
const weekEnd = dates[6].date;

return [{json: {dates, weekStart, weekEnd, weekStartISO: weekStart + 'T00:00:00+01:00', weekEndISO: weekEnd + 'T23:59:59+01:00'}}];
"""
        },
    }

    query_gcal = {
        "id": query_gcal_id,
        "name": "Google Calendar Next Week",
        "type": "n8n-nodes-base.googleCalendar",
        "typeVersion": 1,
        "position": [480, 400],
        "credentials": GCAL_CRED,
        "parameters": {
            "operation": "getAll",
            "calendarId": "primary",
            "returnAll": True,
            "options": {
                "singleEvents": True,
                "timeMin": "={{$json.weekStartISO}}",
                "timeMax": "={{$json.weekEndISO}}",
                "orderBy": "startTime",
            },
        },
        "onError": "continueRegularOutput",
        "continueOnFail": True,
    }

    query_tasks = {
        "id": query_tasks_id,
        "name": "Query Priority Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 200],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": "https://api.notion.com/v1/databases/305da200-b2d6-8145-bc16-eaee02925a14/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({
                "filter": {
                    "and": [
                        {"property": "Type", "select": {"equals": "Task"}},
                        {"property": "Status", "status": {"equals": "In Progress"}},
                    ]
                },
                "sorts": [
                    {"property": "Priority", "direction": "ascending"},
                ],
                "page_size": 20,
            }),
        },
    }

    generate_blocks = {
        "id": generate_blocks_id,
        "name": "Generate Week Blocks",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [740, 300],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """
const ctx = $('Next Week Context').first().json;
const dates = ctx.dates; // [{date, dayName, dayOfWeek}] 1=Mon..7=Sun
const dayKeys = ['', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

// --- Parse Google Calendar shifts (McDo etc.) ---
let shifts = [];
try {
    const gcalItems = $('Google Calendar Next Week').all();
    for (const item of gcalItems) {
        const d = item.json;
        if (d.error || !d.start) continue;
        const startTime = d.start?.dateTime || d.start?.date;
        const endTime = d.end?.dateTime || d.end?.date;
        if (!startTime) continue;
        shifts.push({
            date: startTime.substring(0, 10),
            start: startTime,
            end: endTime,
            title: (d.summary || '').toLowerCase(),
        });
    }
} catch(e) {}

// Helper: add minutes to HH:MM
function addMin(hhmm, mins) {
    const total = parseInt(hhmm.split(':')[0]) * 60 + parseInt(hhmm.split(':')[1]) + mins;
    return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
}
function toMin(hhmm) {
    return parseInt(hhmm.split(':')[0]) * 60 + parseInt(hhmm.split(':')[1]);
}

// --- TEMPLATE (embedded from weekly_template.json) ---
const dailyBlocks = [
    {nom: 'Routine Matin', type: 'Routine', time: '07:00', dur: 30, priority: 'Medium', notes: 'Reveil, hygiene, petit-dej', weekdayOverride: {sat: '09:00'}, skipDays: []},
    {nom: 'Course a pied', type: 'Sport', time: '07:30', dur: 30, priority: 'High', notes: 'Run/walk reprise progressive', weekdayOverride: {}, skipDays: ['sat']},
    {nom: 'Dejeuner', type: 'Break', time: '13:00', dur: 60, priority: null, notes: '', weekdayOverride: {}, skipDays: []},
    {nom: 'Stretching', type: 'Sport', time: '15:00', dur: 30, priority: null, notes: 'Etirements, grand ecart', weekdayOverride: {}, skipDays: []},
    {nom: 'Routine Soir', type: 'Routine', time: '21:00', dur: 60, priority: null, notes: '', weekdayOverride: {}, skipDays: ['sat']},
];

const weeklyBlocks = [
    {nom: 'Musculation Push', type: 'Sport', day: 'mon', time: '14:00', dur: 60, priority: 'High', notes: 'Push: pompes, dips, OHP'},
    {nom: 'Musculation Pull', type: 'Sport', day: 'tue', time: '14:30', dur: 60, priority: 'High', notes: 'Pull: tractions, rows, biceps'},
    {nom: 'Musculation Legs', type: 'Sport', day: 'wed', time: '14:30', dur: 60, priority: 'High', notes: 'Legs + plyo: squats, fentes, box jumps'},
    {nom: 'Grasse matinee + Routine', type: 'Routine', day: 'sat', time: '09:00', dur: 30, priority: null, notes: 'Repos, petit-dej tranquille'},
    {nom: 'Active Recovery', type: 'Sport', day: 'sat', time: '10:00', dur: 45, priority: 'Medium', notes: 'Marche, yoga, foam rolling'},
    {nom: 'Meal prep semaine', type: 'Personal', day: 'sat', time: '11:00', dur: 90, priority: null, notes: 'Prep repas semaine prochaine'},
    {nom: 'Weekly Review', type: 'Routine', day: 'sat', time: '20:00', dur: 60, priority: 'High', notes: 'Bilan semaine, planifier la suivante'},
];

const newBlocks = [];

function pushBlock(nom, type, date, time, dur, priority, notes) {
    const startISO = date + 'T' + time + ':00';
    const endISO = date + 'T' + addMin(time, dur) + ':00';
    newBlocks.push({block: nom, type, startISO, endISO, recurrence: 'Template', priority, notes});
}

// --- 1. Fixed daily blocks ---
for (const dayInfo of dates) {
    const dk = dayKeys[dayInfo.dayOfWeek];
    for (const db of dailyBlocks) {
        if (db.skipDays.includes(dk)) continue;
        const time = db.weekdayOverride?.[dk] || db.time;

        // If shift conflicts, adjust: dejeuner shifts after shift end
        const dayShifts = shifts.filter(s => s.date === dayInfo.date);
        let finalTime = time;

        if (db.nom === 'Dejeuner' && dayShifts.length > 0) {
            // Place dejeuner 30min after last shift ends
            for (const sh of dayShifts) {
                const shEnd = sh.end?.substring(11, 16) || '';
                if (shEnd && toMin(shEnd) > toMin(finalTime) - 30) {
                    finalTime = addMin(shEnd, 30);
                }
            }
        }

        // Skip if conflicts with a shift
        const blockStart = toMin(finalTime);
        const blockEnd = blockStart + db.dur;
        const conflicts = dayShifts.some(sh => {
            const ss = toMin(sh.start?.substring(11, 16) || '00:00');
            const se = toMin(sh.end?.substring(11, 16) || '00:00');
            return ss < blockEnd && se > blockStart;
        });

        if (!conflicts) {
            pushBlock(db.nom, db.type, dayInfo.date, finalTime, db.dur, db.priority, db.notes);
        }
    }
}

// --- 2. Fixed weekly blocks ---
for (const wb of weeklyBlocks) {
    const dayInfo = dates.find(d => dayKeys[d.dayOfWeek] === wb.day);
    if (!dayInfo) continue;
    pushBlock(wb.nom, wb.type, dayInfo.date, wb.time, wb.dur, wb.priority, wb.notes);
}

// --- 3. Prep/trajet around each shift ---
for (const sh of shifts) {
    const shStart = sh.start?.substring(11, 16) || '';
    const shEnd = sh.end?.substring(11, 16) || '';
    if (!shStart || !shEnd) continue;

    // 30min prep before shift
    const prepTime = addMin(shStart, -30);
    pushBlock('Prep + trajet McDo', 'Personal', sh.date, prepTime, 30, null, 'Trajet a pied');

    // 30min trajet after shift
    pushBlock('Trajet retour', 'Personal', sh.date, shEnd, 30, null, 'Trajet retour a pied');
}

// --- 4. Parse priority tasks from Notion ---
let tasks = [];
try {
    const data = $('Query Priority Tasks').first().json;
    const results = data.results || [];
    for (const t of results) {
        const props = t.properties || {};
        const name = (props['Nom']?.title || []).map(x => x.plain_text).join('') || '?';
        const priority = props['Priority']?.select?.name || 'Medium';
        const category = props['Category']?.select?.name || '';
        tasks.push({name, priority, category});
    }
} catch(e) {}

// --- 5. Deep Work in free morning/afternoon slots, assigned to real tasks ---
let taskIdx = 0;
for (const dayInfo of dates) {
    const dk = dayKeys[dayInfo.dayOfWeek];
    if (dk === 'sat' || dk === 'sun') continue;

    const dayShifts = shifts.filter(s => s.date === dayInfo.date);

    const existing = newBlocks.filter(b => b.startISO.startsWith(dayInfo.date));
    const occupied = [
        ...existing.map(b => ({s: toMin(b.startISO.substring(11,16)), e: toMin(b.endISO.substring(11,16))})),
        ...dayShifts.map(sh => ({s: toMin(sh.start?.substring(11,16)||'0:0'), e: toMin(sh.end?.substring(11,16)||'0:0')})),
    ];

    function findSlot(windowStart, windowEnd, minDur) {
        for (let t = windowStart; t + minDur <= windowEnd; t += 15) {
            const free = !occupied.some(o => o.s < t + minDur && o.e > t);
            if (free) return t;
        }
        return -1;
    }

    // Try to fill 1-2 deep work slots per day
    for (let attempt = 0; attempt < 2; attempt++) {
        let slot = findSlot(toMin('08:00'), toMin('12:00'), 90);
        if (slot < 0) slot = findSlot(toMin('15:30'), toMin('19:00'), 90);
        if (slot < 0) break;

        let dur = 120;
        while (dur > 90 && occupied.some(o => o.s < slot + dur && o.e > slot)) dur -= 15;

        // Assign real task name if available
        const task = tasks[taskIdx] || null;
        const blockName = task ? 'Deep Work: ' + task.name : 'Deep Work';
        const blockPriority = task ? task.priority : 'Critical';
        const blockNotes = task ? task.category : '';
        if (task) taskIdx++;

        const slotTime = String(Math.floor(slot/60)).padStart(2,'0') + ':' + String(slot%60).padStart(2,'0');
        pushBlock(blockName, 'Task', dayInfo.date, slotTime, dur, blockPriority, blockNotes);
        occupied.push({s: slot, e: slot + dur});
    }
}

// Sort by date and time
newBlocks.sort((a, b) => a.startISO.localeCompare(b.startISO));

return [{json: {blocks: newBlocks, totalBlocks: newBlocks.length, weekStart: ctx.weekStart, weekEnd: ctx.weekEnd}}];
"""
        },
    }

    split_blocks = {
        "id": split_blocks_id,
        "name": "Split Blocks",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [960, 300],
        "parameters": {
            "jsCode": """
const data = $json;
const blocks = data.blocks || [];
// Return each block as a separate item for batch creation
return blocks.map(b => ({json: {...b, weekStart: data.weekStart, weekEnd: data.weekEnd, totalBlocks: data.totalBlocks}}));
"""
        },
    }

    create_block = {
        "id": create_block_id,
        "name": "Create Time Block",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1180, 300],
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
            "jsonBody": '={{ JSON.stringify({parent: {database_id: "' + TIME_BLOCKS_DB + '"}, properties: {"Nom": {title: [{text: {content: $json.block}}]}, "Type": {select: {name: $json.type}}, "Date": {date: {start: $json.startISO, end: $json.endISO}}, "Recurrence": {select: {name: $json.recurrence}}, ...($json.priority ? {"Priority": {select: {name: $json.priority}}} : {}), "Notes": {rich_text: [{text: {content: $json.notes || ""}}]}}}) }}',
        },
        "executeOnce": False,
    }

    build_recap = {
        "id": build_recap_id,
        "name": "Build Recap",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1400, 300],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """
const items = $input.all();
const first = items[0]?.json || {};
const total = first.totalBlocks || items.length;
const weekStart = first.weekStart || '?';
const weekEnd = first.weekEnd || '?';

let msg = '<b>Planning semaine genere</b>\\n';
msg += 'Semaine du ' + weekStart + ' au ' + weekEnd + '\\n\\n';
msg += total + ' blocs crees dans Time Blocks\\n';

// Count by type
const types = {};
for (const item of items) {
    const t = item.json.type || '?';
    types[t] = (types[t] || 0) + 1;
}
for (const [t, count] of Object.entries(types)) {
    msg += '  ' + t + ': ' + count + '\\n';
}

return [{json: {text: msg}}];
"""
        },
    }

    send_tg = {
        "id": send_tg_id,
        "name": "Send Telegram",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [1620, 300],
        "credentials": TELEGRAM_CRED,
        "parameters": {
            "chatId": TELEGRAM_CHAT_ID,
            "text": "={{$json.text}}",
            "additionalFields": {"parse_mode": "HTML"},
        },
    }

    connections = {
        "Sunday 20h": {"main": [[{"node": "Next Week Context", "type": "main", "index": 0}]]},
        "Next Week Context": {"main": [[
            {"node": "Google Calendar Next Week", "type": "main", "index": 0},
            {"node": "Query Priority Tasks", "type": "main", "index": 0},
        ]]},
        "Google Calendar Next Week": {"main": [[{"node": "Generate Week Blocks", "type": "main", "index": 0}]]},
        "Query Priority Tasks": {"main": [[{"node": "Generate Week Blocks", "type": "main", "index": 0}]]},
        "Generate Week Blocks": {"main": [[{"node": "Split Blocks", "type": "main", "index": 0}]]},
        "Split Blocks": {"main": [[{"node": "Create Time Block", "type": "main", "index": 0}]]},
        "Create Time Block": {"main": [[{"node": "Build Recap", "type": "main", "index": 0}]]},
        "Build Recap": {"main": [[{"node": "Send Telegram", "type": "main", "index": 0}]]},
    }

    return {
        "name": WORKFLOW_NAME,
        "nodes": [trigger, week_ctx, query_gcal, query_tasks, generate_blocks, split_blocks, create_block, build_recap, send_tg],
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "Europe/Paris", "saveManualExecutions": True},
    }


if __name__ == "__main__":
    import requests
    print(f"Building workflow: {WORKFLOW_NAME}")
    wf = build_workflow()

    try:
        resp = requests.post(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, json=wf, timeout=30)
        if resp.status_code in (200, 201):
            data = resp.json()
            wf_id = data.get("id", "?")
            print(f"[OK] Created: {wf_id}")
            # Activate
            act = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS, timeout=10)
            print(f"[OK] Active: {act.status_code == 200}")
        else:
            print(f"[ERROR] {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[ERROR] {e}")
