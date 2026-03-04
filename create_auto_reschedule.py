#!/usr/bin/env python3
"""Create n8n workflow: Auto-Rescheduler (Motion-like).

Trigger: Every 15 minutes (polls for completed tasks)
Pipeline:
1. Schedule Trigger (every 15 min)
2. Query Time Blocks with Status=Done for today that were tasks
3. Query remaining Time Blocks for today (Status=Planned, type=Task)
4. Query unscheduled high-priority tasks from Projects & Tasks
5. If a completed block freed up time, shift remaining blocks and insert new task
6. Update Time Blocks DB
7. Send Telegram notification (optional, only if rescheduling happened)

Motion-like behavior:
- When you complete a task block early, the freed time gets filled
- Unscheduled priority tasks get auto-assigned to free slots
- Existing blocks shift to fill gaps
"""

import json
import os
import uuid

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = os.environ.get("N8N_API_KEY", open(os.path.expanduser("~/.n8n-api-key")).read().strip() if os.path.exists(os.path.expanduser("~/.n8n-api-key")) else "")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}

TIME_BLOCKS_DB = "51eceb13-346a-4f7e-a07f-724b6d8b2c81"
PROJECTS_TASKS_DB = "305da200-b2d6-8145-bc16-eaee02925a14"
TELEGRAM_CHAT_ID = "7342622615"
WORKFLOW_NAME = "Auto-Rescheduler"


def uid():
    return str(uuid.uuid4())


def build_workflow():
    trigger_id = uid()
    date_ctx_id = uid()
    query_done_id = uid()
    query_planned_id = uid()
    query_backlog_id = uid()
    reschedule_id = uid()
    has_changes_id = uid()
    split_updates_id = uid()
    update_block_id = uid()
    create_new_id = uid()
    build_tg_id = uid()
    send_tg_id = uid()

    trigger = {
        "id": trigger_id,
        "name": "Every 15 min",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 300],
        "parameters": {
            "rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}
        },
    }

    date_ctx = {
        "id": date_ctx_id,
        "name": "Today Context",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 300],
        "parameters": {
            "jsCode": """
const now = new Date(new Date().toLocaleString('en-US', {timeZone: 'Europe/Paris'}));
const year = now.getFullYear();
const month = String(now.getMonth() + 1).padStart(2, '0');
const day = String(now.getDate()).padStart(2, '0');
const today = year + '-' + month + '-' + day;
const currentTime = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
return [{json: {today, currentTime}}];
"""
        },
    }

    # Query completed blocks today
    query_done = {
        "id": query_done_id,
        "name": "Query Done Blocks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 150],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{TIME_BLOCKS_DB}/query",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({"filter":{"and":[{"property":"Status","status":{"equals":"Done"}},{"property":"Start","date":{"equals":"' + '{{$json.today}}' + '"}}]}}) }}',
        },
    }

    # Query planned blocks today (not yet done)
    query_planned = {
        "id": query_planned_id,
        "name": "Query Planned Blocks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 300],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{TIME_BLOCKS_DB}/query",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({"filter":{"and":[{"or":[{"property":"Status","status":{"equals":"Not started"}},{"property":"Status","status":{"equals":"In progress"}}]},{"property":"Start","date":{"equals":"' + '{{$json.today}}' + '"}},{"property":"Type","select":{"does_not_equal":"Meeting"}}]},"sorts":[{"property":"Start","direction":"ascending"}]}) }}',
        },
    }

    # Query unscheduled priority tasks
    query_backlog = {
        "id": query_backlog_id,
        "name": "Query Backlog Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 450],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{PROJECTS_TASKS_DB}/query",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({"filter":{"and":[{"or":[{"property":"Status","status":{"equals":"Ready To Start"}},{"property":"Status","status":{"equals":"In Progress"}}]},{"or":[{"property":"Due Date","date":{"equals":"' + '{{$json.today}}' + '"}},{"property":"Due Date","date":{"before":"' + '{{$json.today}}' + '"}}]},{"property":"Status","status":{"does_not_equal":"Complete"}},{"or":[{"property":"Type","select":{"equals":"Task"}},{"property":"Type","select":{"equals":"Sub-task"}}]}]},"sorts":[{"property":"Priority","direction":"ascending"}],"page_size":10}) }}',
        },
    }

    # Core rescheduling logic
    reschedule = {
        "id": reschedule_id,
        "name": "Reschedule Logic",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [740, 300],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """
const ctx = $('Today Context').first().json;
const today = ctx.today;
const currentTime = ctx.currentTime;

// Parse done blocks
let doneBlocks = [];
try {
    doneBlocks = ($('Query Done Blocks').first().json.results || []).map(p => {
        const props = p.properties || {};
        return {
            id: p.id,
            name: (props['Block']?.title || []).map(t => t.plain_text).join(''),
            start: props['Start']?.date?.start || '',
            end: props['End']?.date?.start || '',
            type: props['Type']?.select?.name || '',
        };
    });
} catch(e) {}

// Parse planned blocks (future ones only)
let plannedBlocks = [];
try {
    plannedBlocks = ($('Query Planned Blocks').first().json.results || []).map(p => {
        const props = p.properties || {};
        const start = props['Start']?.date?.start || '';
        const startTime = start.includes('T') ? start.split('T')[1].substring(0,5) : '23:59';
        return {
            id: p.id,
            name: (props['Block']?.title || []).map(t => t.plain_text).join(''),
            start: start,
            end: props['End']?.date?.start || '',
            startTime: startTime,
            duration: props['Duration']?.number || 60,
            type: props['Type']?.select?.name || '',
            priority: props['Priority']?.select?.name || 'Medium',
        };
    }).filter(b => b.startTime >= currentTime); // Only future blocks
} catch(e) {}

// Parse backlog tasks (not yet in Time Blocks)
let backlogTasks = [];
try {
    const taskResults = $('Query Backlog Tasks').first().json.results || [];
    // Get IDs of tasks already in time blocks (via Source Task relation)
    const scheduledTaskIds = new Set();
    for (const b of [...doneBlocks, ...plannedBlocks]) {
        // We can't easily check this without Source Task data
        // For now, we match by name
    }

    const priorityOrder = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3};
    backlogTasks = taskResults.map(p => {
        const props = p.properties || {};
        const name = (props['Name']?.title || []).map(t => t.plain_text).join('') || '?';
        const priority = props['Priority']?.select?.name || 'Medium';
        const difficulty = props['Difficulty']?.select?.name || 'Moderate';
        let duration = 60;
        if (difficulty === 'Easy' || difficulty === 'Trivial') duration = 30;
        else if (difficulty === 'Hard' || difficulty === 'Expert') duration = 120;
        return {id: p.id, name, priority, duration, priorityScore: priorityOrder[priority] || 2};
    }).sort((a, b) => a.priorityScore - b.priorityScore);
} catch(e) {}

// Find free slots between planned blocks (after current time)
const dayEnd = 22 * 60; // 22:00
let freeSlots = [];

// Build timeline of occupied slots
const occupied = plannedBlocks.map(b => {
    const [sH, sM] = b.startTime.split(':').map(Number);
    const startMin = sH * 60 + sM;
    return {start: startMin, end: startMin + b.duration, block: b};
}).sort((a, b) => a.start - b.start);

const [cH, cM] = currentTime.split(':').map(Number);
let cursor = cH * 60 + cM;
// Round up to next 15 min
cursor = Math.ceil(cursor / 15) * 15;

for (const occ of occupied) {
    if (occ.start > cursor + 15) { // At least 15 min gap
        freeSlots.push({startMin: cursor, endMin: occ.start, duration: occ.start - cursor});
    }
    cursor = Math.max(cursor, occ.end);
}
if (cursor < dayEnd) {
    freeSlots.push({startMin: cursor, endMin: dayEnd, duration: dayEnd - cursor});
}

// Fill free slots with backlog tasks
const newBlocks = [];
let taskIdx = 0;

for (const slot of freeSlots) {
    if (taskIdx >= backlogTasks.length) break;
    if (slot.duration < 30) continue; // Skip tiny slots

    const task = backlogTasks[taskIdx];
    const taskDuration = Math.min(task.duration, slot.duration);

    const startH = String(Math.floor(slot.startMin / 60)).padStart(2, '0');
    const startM = String(slot.startMin % 60).padStart(2, '0');
    const endMin = slot.startMin + taskDuration;
    const endH = String(Math.floor(endMin / 60)).padStart(2, '0');
    const endM = String(endMin % 60).padStart(2, '0');

    // Check this task isn't already in a planned block (by name)
    const alreadyPlanned = plannedBlocks.some(b => b.name.toLowerCase().includes(task.name.toLowerCase().substring(0, 20)));
    if (alreadyPlanned) {
        taskIdx++;
        continue;
    }

    newBlocks.push({
        block: task.name,
        type: 'Task',
        startISO: today + 'T' + startH + ':' + startM + ':00',
        endISO: today + 'T' + endH + ':' + endM + ':00',
        duration: taskDuration,
        priority: task.priority,
        sourceTaskId: task.id,
        notes: 'Auto-planifie par rescheduler',
    });

    taskIdx++;
    // If task didn't fill the slot, next task can use remaining time
    // For simplicity, move to next slot
}

const hasChanges = newBlocks.length > 0;

return [{json: {
    hasChanges,
    newBlocks,
    totalNew: newBlocks.length,
    freeSlots: freeSlots.length,
    backlogCount: backlogTasks.length,
    plannedCount: plannedBlocks.length,
    doneCount: doneBlocks.length,
}}];
"""
        },
    }

    has_changes = {
        "id": has_changes_id,
        "name": "Has Changes?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [960, 300],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [{
                    "id": uid(),
                    "leftValue": "={{$json.hasChanges}}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "equals", "singleValue": True},
                }],
                "combinator": "and",
            }
        },
    }

    split_updates = {
        "id": split_updates_id,
        "name": "Split New Blocks",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1200, 200],
        "parameters": {
            "jsCode": """
const data = $json;
return data.newBlocks.map(b => ({json: b}));
"""
        },
    }

    create_new = {
        "id": create_new_id,
        "name": "Create Block",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1420, 200],
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
            "jsonBody": '={{ JSON.stringify({parent: {database_id: "' + TIME_BLOCKS_DB + '"}, properties: {"Block": {title: [{text: {content: $json.block}}]}, "Type": {select: {name: $json.type}}, "Start": {date: {start: $json.startISO}}, "End": {date: {start: $json.endISO}}, "Duration": {number: $json.duration}, "Recurrence": {select: {name: "None"}}, ...($json.priority ? {"Priority": {select: {name: $json.priority}}} : {}), "Notes": {rich_text: [{text: {content: $json.notes || ""}}]}}}) }}',
        },
    }

    build_tg = {
        "id": build_tg_id,
        "name": "Build Notification",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1640, 200],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """
const items = $input.all();
let msg = '<b>Auto-replanification</b>\\n\\n';
msg += items.length + ' nouveau(x) bloc(s) ajoute(s):\\n';
for (const item of items) {
    const b = item.json;
    const start = (b.startISO || '').split('T')[1]?.substring(0,5) || '?';
    const end = (b.endISO || '').split('T')[1]?.substring(0,5) || '?';
    msg += '  ' + start + '-' + end + ' ' + (b.block || b.properties?.Block?.title?.[0]?.plain_text || '?') + '\\n';
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
        "position": [1860, 200],
        "credentials": TELEGRAM_CRED,
        "parameters": {
            "chatId": TELEGRAM_CHAT_ID,
            "text": "={{$json.text}}",
            "additionalFields": {"parse_mode": "HTML"},
        },
    }

    connections = {
        "Every 15 min": {"main": [[{"node": "Today Context", "type": "main", "index": 0}]]},
        "Today Context": {"main": [[
            {"node": "Query Done Blocks", "type": "main", "index": 0},
            {"node": "Query Planned Blocks", "type": "main", "index": 0},
            {"node": "Query Backlog Tasks", "type": "main", "index": 0},
        ]]},
        "Query Done Blocks": {"main": [[{"node": "Reschedule Logic", "type": "main", "index": 0}]]},
        "Query Planned Blocks": {"main": [[{"node": "Reschedule Logic", "type": "main", "index": 0}]]},
        "Query Backlog Tasks": {"main": [[{"node": "Reschedule Logic", "type": "main", "index": 0}]]},
        "Reschedule Logic": {"main": [[{"node": "Has Changes?", "type": "main", "index": 0}]]},
        "Has Changes?": {"main": [
            [{"node": "Split New Blocks", "type": "main", "index": 0}],
            []
        ]},
        "Split New Blocks": {"main": [[{"node": "Create Block", "type": "main", "index": 0}]]},
        "Create Block": {"main": [[{"node": "Build Notification", "type": "main", "index": 0}]]},
        "Build Notification": {"main": [[{"node": "Send Telegram", "type": "main", "index": 0}]]},
    }

    return {
        "name": WORKFLOW_NAME,
        "nodes": [trigger, date_ctx, query_done, query_planned, query_backlog, reschedule, has_changes, split_updates, create_new, build_tg, send_tg],
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
            act = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS, timeout=10)
            print(f"[OK] Active: {act.status_code == 200}")
        else:
            print(f"[ERROR] {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[ERROR] {e}")
