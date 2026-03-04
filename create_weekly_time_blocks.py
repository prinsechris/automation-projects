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
    query_templates_id = uid()
    query_gcal_id = uid()
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

    query_templates = {
        "id": query_templates_id,
        "name": "Query Recurring Templates",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 200],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{TIME_BLOCKS_DB}/query",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({
                "filter": {
                    "property": "Recurrence",
                    "select": {"does_not_equal": "None"}
                }
            }),
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
const dates = ctx.dates; // [{date, dayName, dayOfWeek}]

// Parse templates
let templates = [];
try {
    const data = $('Query Recurring Templates').first().json;
    templates = data.results || [];
} catch(e) { templates = []; }

// Parse Google Calendar events
let calEvents = [];
try {
    const gcalItems = $('Google Calendar Next Week').all();
    for (const item of gcalItems) {
        const d = item.json;
        if (d.error || !d.start) continue;
        const startTime = d.start?.dateTime || d.start?.date;
        const endTime = d.end?.dateTime || d.end?.date;
        if (!startTime) continue;
        const startDate = startTime.substring(0, 10);
        calEvents.push({
            date: startDate,
            start: startTime,
            end: endTime,
            title: d.summary || 'Evenement',
        });
    }
} catch(e) {}

// Generate blocks for each day
const newBlocks = [];

// Add Google Calendar events as Meeting blocks
for (const ev of calEvents) {
    const startDT = new Date(ev.start);
    const endDT = new Date(ev.end);
    const duration = Math.round((endDT - startDT) / 60000);
    newBlocks.push({
        block: ev.title,
        type: 'Meeting',
        startISO: ev.start,
        endISO: ev.end,
        duration: duration,
        recurrence: 'None',
        priority: null,
        notes: 'Import Google Calendar',
    });
}

// Process recurring templates
for (const tpl of templates) {
    const props = tpl.properties || {};
    const name = (props['Block']?.title || []).map(t => t.plain_text).join('') || 'Bloc';
    const type = props['Type']?.select?.name || 'Task';
    const recurrence = props['Recurrence']?.select?.name || 'None';
    const duration = props['Duration']?.number || 60;
    const priority = props['Priority']?.select?.name || null;
    const notes = (props['Notes']?.rich_text || []).map(t => t.plain_text).join('') || '';

    // Get original time from Start property
    const origStart = props['Start']?.date?.start || '';
    let timeStr = '09:00';
    if (origStart.includes('T')) {
        timeStr = origStart.split('T')[1].substring(0, 5);
    }

    // Get original day of week
    const origDate = new Date(origStart.substring(0, 10) + 'T12:00:00');
    const origDow = origDate.getDay(); // 0=Sun, 1=Mon...

    // Determine which days to create blocks
    let targetDays = [];

    if (recurrence === 'Daily') {
        targetDays = [1, 2, 3, 4, 5, 6, 7]; // All week
    } else if (recurrence === 'Weekly') {
        // Check notes for specific days (e.g., "Lundi / Mercredi / Vendredi")
        const notesLower = notes.toLowerCase();
        const dayMap = {'lundi':1, 'mardi':2, 'mercredi':3, 'jeudi':4, 'vendredi':5, 'samedi':6, 'dimanche':7};
        for (const [dayName, dayNum] of Object.entries(dayMap)) {
            if (notesLower.includes(dayName)) {
                targetDays.push(dayNum);
            }
        }
        // If no specific days found, use the original day
        if (targetDays.length === 0) {
            const mappedDow = origDow === 0 ? 7 : origDow; // Convert to 1=Mon
            targetDays = [mappedDow];
        }
    } else if (recurrence === 'Bi-Weekly') {
        // Every other week — check if this is the right week
        const weekNum = Math.ceil(new Date(dates[0].date).getDate() / 7);
        if (weekNum % 2 === 0) {
            const mappedDow = origDow === 0 ? 7 : origDow;
            targetDays = [mappedDow];
        }
    }

    // Create blocks for target days
    for (const dayNum of targetDays) {
        const dayInfo = dates.find(d => d.dayOfWeek === dayNum);
        if (!dayInfo) continue;

        const startISO = dayInfo.date + 'T' + timeStr + ':00';
        // Calculate end time
        const startMin = parseInt(timeStr.split(':')[0]) * 60 + parseInt(timeStr.split(':')[1]);
        const endMin = startMin + duration;
        const endH = String(Math.floor(endMin / 60)).padStart(2, '0');
        const endM = String(endMin % 60).padStart(2, '0');
        const endISO = dayInfo.date + 'T' + endH + ':' + endM + ':00';

        // Check for conflicts with calendar events
        const hasConflict = calEvents.some(ev => {
            return ev.date === dayInfo.date &&
                   ev.start < endISO && ev.end > startISO;
        });

        if (!hasConflict) {
            newBlocks.push({
                block: name,
                type: type,
                startISO: startISO,
                endISO: endISO,
                duration: duration,
                recurrence: recurrence,
                priority: priority,
                notes: notes,
            });
        }
    }
}

// Sort by date and start time
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
            "jsonBody": '={{ JSON.stringify({parent: {database_id: "' + TIME_BLOCKS_DB + '"}, properties: {"Block": {title: [{text: {content: $json.block}}]}, "Type": {select: {name: $json.type}}, "Start": {date: {start: $json.startISO}}, "End": {date: {start: $json.endISO}}, "Duration": {number: $json.duration}, "Recurrence": {select: {name: $json.recurrence}}, ...($json.priority ? {"Priority": {select: {name: $json.priority}}} : {}), "Notes": {rich_text: [{text: {content: $json.notes || ""}}]}}}) }}',
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
            {"node": "Query Recurring Templates", "type": "main", "index": 0},
            {"node": "Google Calendar Next Week", "type": "main", "index": 0},
        ]]},
        "Query Recurring Templates": {"main": [[{"node": "Generate Week Blocks", "type": "main", "index": 0}]]},
        "Google Calendar Next Week": {"main": [[{"node": "Generate Week Blocks", "type": "main", "index": 0}]]},
        "Generate Week Blocks": {"main": [[{"node": "Split Blocks", "type": "main", "index": 0}]]},
        "Split Blocks": {"main": [[{"node": "Create Time Block", "type": "main", "index": 0}]]},
        "Create Time Block": {"main": [[{"node": "Build Recap", "type": "main", "index": 0}]]},
        "Build Recap": {"main": [[{"node": "Send Telegram", "type": "main", "index": 0}]]},
    }

    return {
        "name": WORKFLOW_NAME,
        "nodes": [trigger, week_ctx, query_templates, query_gcal, generate_blocks, split_blocks, create_block, build_recap, send_tg],
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
