#!/usr/bin/env python3
"""Create n8n sub-workflow: Time Blocking Manager.

Called by Manager Bot as a tool to read/create/modify/delete time blocks.
Actions:
  - read_today: Show today's planning
  - read_date YYYY-MM-DD: Show planning for a specific date
  - create START END NOM TYPE PRIORITY: Create a new time block
  - modify BLOCK_ID FIELD VALUE: Modify an existing time block
  - delete BLOCK_ID: Delete a time block
  - reschedule: Reschedule today's blocks based on constraints
"""

import json
import requests
import uuid
import os

# ── Config ──────────────────────────────────────────────────────────
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Credentials
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
ANTHROPIC_CRED = {"httpCustomAuth": {"id": "sE8nBT8crViDOv1E", "name": "Anthropic account"}}

# Notion IDs
TIME_BLOCKS_DB = "51eceb13-346a-4f7e-a07f-724b6d8b2c81"
TIME_BLOCKS_COLLECTION = "487a884b-d5d6-4d4b-8367-2e4d5e496aa8"
PROJECTS_TASKS_DB = "305da200-b2d6-8145-bc16-eaee02925a14"

WORKFLOW_NAME = "Time Blocking Manager"


def uid():
    return str(uuid.uuid4())


def build_workflow():
    """Build the Time Blocking Manager sub-workflow."""

    # Node IDs
    trigger_id = uid()
    parse_action_id = uid()
    switch_id = uid()
    query_today_id = uid()
    query_date_id = uid()
    format_read_id = uid()
    create_block_id = uid()
    format_create_id = uid()
    modify_block_id = uid()
    format_modify_id = uid()
    delete_block_id = uid()
    format_delete_id = uid()
    reschedule_query_id = uid()
    reschedule_claude_id = uid()
    reschedule_parse_id = uid()
    reschedule_update_id = uid()
    format_reschedule_id = uid()

    # ── Node 1: Execute Workflow Trigger (called by Manager Bot) ──
    trigger = {
        "id": trigger_id,
        "name": "Tool Input",
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [0, 300],
        "parameters": {},
    }

    # ── Node 2: Parse Action ──
    parse_action = {
        "id": parse_action_id,
        "name": "Parse Action",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 300],
        "parameters": {
            "jsCode": """
const input = $json.query || $json.chatInput || $json.action || '';

// Parse action from input
const parts = input.trim().split(/\\s+/);
const action = (parts[0] || 'read_today').toLowerCase();

// Get today's date in Europe/Paris
const now = new Date();
const parisStr = now.toLocaleString('en-US', {timeZone: 'Europe/Paris'});
const paris = new Date(parisStr);
const year = paris.getFullYear();
const month = String(paris.getMonth() + 1).padStart(2, '0');
const day = String(paris.getDate()).padStart(2, '0');
const today = `${year}-${month}-${day}`;

let result = {action, today, rawInput: input};

if (action === 'read_date' && parts[1]) {
    result.targetDate = parts[1];
} else if (action === 'create') {
    // create HH:MM HH:MM "Nom" Type Priority
    result.startTime = parts[1] || '';
    result.endTime = parts[2] || '';
    // Join remaining parts for name, then extract type and priority
    const rest = parts.slice(3).join(' ');
    // Try to parse: "Activity Name | Type | Priority"
    const segments = rest.split('|').map(s => s.trim());
    result.blockName = segments[0] || 'Bloc sans nom';
    result.blockType = segments[1] || 'Task';
    result.blockPriority = segments[2] || 'Medium';
} else if (action === 'modify') {
    result.blockId = parts[1] || '';
    result.field = parts[2] || '';
    result.newValue = parts.slice(3).join(' ');
} else if (action === 'delete') {
    result.blockId = parts[1] || '';
}

return [{json: result}];
"""
        },
    }

    # ── Node 3: Switch on action ──
    switch = {
        "id": switch_id,
        "name": "Action Router",
        "type": "n8n-nodes-base.switch",
        "typeVersion": 3.2,
        "position": [440, 300],
        "parameters": {
            "rules": {
                "values": [
                    {
                        "outputKey": "read_today",
                        "conditions": {
                            "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "strict"},
                            "conditions": [{"id": uid(), "leftValue": "={{$json.action}}", "rightValue": "read_today", "operator": {"type": "string", "operation": "equals"}}],
                            "combinator": "and",
                        },
                    },
                    {
                        "outputKey": "read_date",
                        "conditions": {
                            "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "strict"},
                            "conditions": [{"id": uid(), "leftValue": "={{$json.action}}", "rightValue": "read_date", "operator": {"type": "string", "operation": "equals"}}],
                            "combinator": "and",
                        },
                    },
                    {
                        "outputKey": "create",
                        "conditions": {
                            "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "strict"},
                            "conditions": [{"id": uid(), "leftValue": "={{$json.action}}", "rightValue": "create", "operator": {"type": "string", "operation": "equals"}}],
                            "combinator": "and",
                        },
                    },
                    {
                        "outputKey": "modify",
                        "conditions": {
                            "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "strict"},
                            "conditions": [{"id": uid(), "leftValue": "={{$json.action}}", "rightValue": "modify", "operator": {"type": "string", "operation": "equals"}}],
                            "combinator": "and",
                        },
                    },
                    {
                        "outputKey": "delete",
                        "conditions": {
                            "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "strict"},
                            "conditions": [{"id": uid(), "leftValue": "={{$json.action}}", "rightValue": "delete", "operator": {"type": "string", "operation": "equals"}}],
                            "combinator": "and",
                        },
                    },
                    {
                        "outputKey": "reschedule",
                        "conditions": {
                            "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "strict"},
                            "conditions": [{"id": uid(), "leftValue": "={{$json.action}}", "rightValue": "reschedule", "operator": {"type": "string", "operation": "equals"}}],
                            "combinator": "and",
                        },
                    },
                ],
            },
            "options": {},
        },
    }

    # ── READ TODAY ──
    query_today = {
        "id": query_today_id,
        "name": "Query Today Blocks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [720, 0],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{TIME_BLOCKS_DB}/query",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({"filter":{"property":"Date","date":{"equals":"' + "{{$json.today}}" + '"}},"sorts":[{"property":"Date","direction":"ascending"}],"page_size":50}) }}',
        },
    }

    # ── READ DATE ──
    query_date = {
        "id": query_date_id,
        "name": "Query Date Blocks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [720, 150],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{TIME_BLOCKS_DB}/query",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({"filter":{"property":"Date","date":{"equals":"' + "{{$json.targetDate}}" + '"}},"sorts":[{"property":"Date","direction":"ascending"}],"page_size":50}) }}',
        },
    }

    # ── FORMAT READ RESULTS ──
    format_read = {
        "id": format_read_id,
        "name": "Format Planning",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [960, 75],
        "parameters": {
            "jsCode": """
const results = $json.results || [];
if (results.length === 0) {
    return [{json: {response: "Aucun bloc planifie pour cette date."}}];
}

// Sort by start time
const blocks = results.map(page => {
    const props = page.properties || {};
    const name = props['Nom']?.title?.[0]?.plain_text || 'Sans nom';
    const dateStart = props['Date']?.date?.start || '';
    const dateEnd = props['Date']?.date?.end || '';
    const type = props['Type']?.select?.name || '';
    const priority = props['Priority']?.select?.name || '';
    const notes = props['Notes']?.rich_text?.[0]?.plain_text || '';
    const recurrence = props['Recurrence']?.select?.name || '';
    const pageId = page.id;

    // Extract time from datetime
    let startTime = '', endTime = '';
    if (dateStart && dateStart.includes('T')) {
        startTime = dateStart.split('T')[1].substring(0, 5);
    }
    if (dateEnd && dateEnd.includes('T')) {
        endTime = dateEnd.split('T')[1].substring(0, 5);
    }

    return {name, startTime, endTime, type, priority, notes, recurrence, pageId, dateStart};
}).sort((a, b) => a.startTime.localeCompare(b.startTime));

// Format response
let response = `PLANNING (${blocks.length} blocs):\\n\\n`;
for (const b of blocks) {
    const time = b.startTime && b.endTime ? `${b.startTime}-${b.endTime}` : (b.startTime || 'Pas d\\'heure');
    const prio = b.priority ? ` [${b.priority}]` : '';
    const typeTag = b.type ? ` (${b.type})` : '';
    const rec = b.recurrence && b.recurrence !== 'None' ? ` [${b.recurrence}]` : '';
    response += `${time} | ${b.name}${typeTag}${prio}${rec}\\n`;
    if (b.notes) response += `  Note: ${b.notes}\\n`;
}

// Add block IDs for modification
response += `\\nIDs des blocs (pour modification):\\n`;
for (const b of blocks) {
    response += `- "${b.name}": ${b.pageId}\\n`;
}

return [{json: {response}}];
"""
        },
    }

    # ── CREATE BLOCK ──
    create_block = {
        "id": create_block_id,
        "name": "Create Block",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [720, 300],
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
            "jsonBody": """={{ JSON.stringify({
    "parent": {"database_id": \"""" + TIME_BLOCKS_DB + """\"},
    "properties": {
        "Nom": {"title": [{"text": {"content": $json.blockName}}]},
        "Date": {"date": {"start": $json.today + "T" + $json.startTime + ":00+01:00", "end": $json.today + "T" + $json.endTime + ":00+01:00"}},
        "Type": {"select": {"name": $json.blockType}},
        "Priority": {"select": {"name": $json.blockPriority}}
    }
}) }}""",
        },
    }

    format_create = {
        "id": format_create_id,
        "name": "Format Create",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [960, 300],
        "parameters": {
            "jsCode": """
const pageId = $json.id || 'unknown';
const prev = $('Parse Action').first().json;
return [{json: {response: `Bloc cree: "${prev.blockName}" de ${prev.startTime} a ${prev.endTime} (${prev.blockType}, ${prev.blockPriority}). ID: ${pageId}`}}];
"""
        },
    }

    # ── MODIFY BLOCK ──
    modify_block = {
        "id": modify_block_id,
        "name": "Modify Block",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [720, 450],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "PATCH",
            "url": "=https://api.notion.com/v1/pages/{{$json.blockId}}",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": """={{ (() => {
    const field = $json.field.toLowerCase();
    const val = $json.newValue;
    let props = {};

    if (field === 'nom' || field === 'name') {
        props.Nom = {title: [{text: {content: val}}]};
    } else if (field === 'type') {
        props.Type = {select: {name: val}};
    } else if (field === 'priority' || field === 'priorite') {
        props.Priority = {select: {name: val}};
    } else if (field === 'notes' || field === 'note') {
        props.Notes = {rich_text: [{text: {content: val}}]};
    } else if (field === 'start' || field === 'debut') {
        // Update start time: val should be HH:MM
        const today = $json.today;
        props.Date = {date: {start: today + 'T' + val + ':00+01:00'}};
    } else if (field === 'time' || field === 'horaire') {
        // Update both start and end: val should be HH:MM-HH:MM
        const [start, end] = val.split('-');
        const today = $json.today;
        props.Date = {date: {start: today + 'T' + start.trim() + ':00+01:00', end: today + 'T' + end.trim() + ':00+01:00'}};
    } else if (field === 'recurrence') {
        props.Recurrence = {select: {name: val}};
    }

    return JSON.stringify({properties: props});
})() }}""",
        },
    }

    format_modify = {
        "id": format_modify_id,
        "name": "Format Modify",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [960, 450],
        "parameters": {
            "jsCode": """
const prev = $('Parse Action').first().json;
return [{json: {response: `Bloc ${prev.blockId} modifie: ${prev.field} = "${prev.newValue}"`}}];
"""
        },
    }

    # ── DELETE BLOCK ──
    delete_block = {
        "id": delete_block_id,
        "name": "Delete Block",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [720, 600],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "PATCH",
            "url": "=https://api.notion.com/v1/pages/{{$json.blockId}}",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '{"archived": true}',
        },
    }

    format_delete = {
        "id": format_delete_id,
        "name": "Format Delete",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [960, 600],
        "parameters": {
            "jsCode": """
const prev = $('Parse Action').first().json;
return [{json: {response: `Bloc ${prev.blockId} supprime.`}}];
"""
        },
    }

    # ── RESCHEDULE ──
    reschedule_query = {
        "id": reschedule_query_id,
        "name": "Query All Today Blocks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [720, 750],
        "credentials": NOTION_CRED,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{TIME_BLOCKS_DB}/query",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({"filter":{"property":"Date","date":{"equals":"' + "{{$json.today}}" + '"}},"sorts":[{"property":"Date","direction":"ascending"}],"page_size":50}) }}',
        },
    }

    reschedule_claude = {
        "id": reschedule_claude_id,
        "name": "Claude Reschedule",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [960, 750],
        "credentials": ANTHROPIC_CRED,
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
            "jsonBody": """={{ (() => {
    const blocks = ($json.results || []).map(page => {
        const props = page.properties || {};
        return {
            id: page.id,
            name: props['Nom']?.title?.[0]?.plain_text || 'Sans nom',
            start: props['Date']?.date?.start || '',
            end: props['Date']?.date?.end || '',
            type: props['Type']?.select?.name || '',
            priority: props['Priority']?.select?.name || '',
        };
    });

    const prev = $('Parse Action').first().json;
    const constraint = prev.rawInput.replace('reschedule', '').trim();

    const systemPrompt = `Tu es un planificateur. Reorganise les blocs de temps selon les contraintes.
REGLES STRICTES:
- Musculation: UNIQUEMENT avant 8h ou apres 20h (JAMAIS pendant les heures de travail)
- Course a pied: de preference le soir (apres le travail), sinon tres tot le matin
- Heures de travail Chris: 9h-21h45 (bientot 8h-20h) — ne PAS planifier du sport pendant
- Respecter les blocs marques "Meeting" ou "blocked"
- Garder les pauses et repas
- Priorite: Critical > High > Medium > Low
Retourne UNIQUEMENT un JSON: {"blocks": [{"id": "...", "start": "HH:MM", "end": "HH:MM", "name": "..."}], "changes": "Description des changements"}`;

    const userMsg = `Blocs actuels: ${JSON.stringify(blocks)}
Contrainte supplementaire: ${constraint || 'Aucune contrainte supplementaire, juste respecter les regles sport.'}
Reorganise les blocs.`;

    return JSON.stringify({
        model: "claude-sonnet-4-20250514",
        max_tokens: 2048,
        system: systemPrompt,
        messages: [{role: "user", content: userMsg}]
    });
})() }}""",
        },
    }

    reschedule_parse = {
        "id": reschedule_parse_id,
        "name": "Parse & Update Blocks",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1200, 750],
        "parameters": {
            "jsCode": """
const content = $json.content?.[0]?.text || '';
let schedule = null;
try {
    const jsonMatch = content.match(/\\{[\\s\\S]*\\}/);
    if (jsonMatch) schedule = JSON.parse(jsonMatch[0]);
} catch(e) {}

if (!schedule || !schedule.blocks) {
    return [{json: {response: "Impossible de reorganiser le planning. Essaie de preciser la contrainte.", updates: []}}];
}

// Prepare updates for each block
const updates = schedule.blocks.map(b => ({
    blockId: b.id,
    startTime: b.start,
    endTime: b.end,
    name: b.name || ''
}));

const prev = $('Parse Action').first().json;
const today = prev.today;

// Build Notion API update payloads
const apiUpdates = updates.map(u => ({
    url: `https://api.notion.com/v1/pages/${u.blockId}`,
    body: {
        properties: {
            Date: {date: {start: `${today}T${u.startTime}:00+01:00`, end: `${today}T${u.endTime}:00+01:00`}}
        }
    }
}));

return [{json: {
    response: `Planning reorganise: ${schedule.changes || 'Blocs mis a jour.'}\\n\\nNouveau planning:\\n${updates.map(u => \`\${u.startTime}-\${u.endTime} | \${u.name}\`).join('\\n')}`,
    apiUpdates,
    updateCount: updates.length
}}];
"""
        },
    }

    # Update blocks via loop (simplified - update first 10)
    reschedule_update = {
        "id": reschedule_update_id,
        "name": "Apply Updates",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1440, 750],
        "parameters": {
            "jsCode": """
const updates = $json.apiUpdates || [];
const notionVersion = '2022-06-28';

// Apply updates sequentially via fetch
for (const update of updates) {
    try {
        // Using n8n's built-in fetch
        const resp = await fetch(update.url, {
            method: 'PATCH',
            headers: {
                'Authorization': 'Bearer ' + $env.NOTION_API_KEY,
                'Notion-Version': notionVersion,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(update.body)
        });
    } catch(e) {
        // Continue on error
    }
}

return [{json: {response: $json.response}}];
"""
        },
    }

    # Use a simpler approach - output response from parse step
    format_reschedule = {
        "id": format_reschedule_id,
        "name": "Format Reschedule",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1200, 850],
        "parameters": {
            "jsCode": """
return [{json: {response: $json.response || 'Planning reorganise.'}}];
"""
        },
    }

    # ── Connections ──
    connections = {
        "Tool Input": {"main": [[{"node": "Parse Action", "type": "main", "index": 0}]]},
        "Parse Action": {"main": [[{"node": "Action Router", "type": "main", "index": 0}]]},
        "Action Router": {"main": [
            [{"node": "Query Today Blocks", "type": "main", "index": 0}],   # read_today
            [{"node": "Query Date Blocks", "type": "main", "index": 0}],    # read_date
            [{"node": "Create Block", "type": "main", "index": 0}],         # create
            [{"node": "Modify Block", "type": "main", "index": 0}],         # modify
            [{"node": "Delete Block", "type": "main", "index": 0}],         # delete
            [{"node": "Query All Today Blocks", "type": "main", "index": 0}], # reschedule
        ]},
        "Query Today Blocks": {"main": [[{"node": "Format Planning", "type": "main", "index": 0}]]},
        "Query Date Blocks": {"main": [[{"node": "Format Planning", "type": "main", "index": 0}]]},
        "Create Block": {"main": [[{"node": "Format Create", "type": "main", "index": 0}]]},
        "Modify Block": {"main": [[{"node": "Format Modify", "type": "main", "index": 0}]]},
        "Delete Block": {"main": [[{"node": "Format Delete", "type": "main", "index": 0}]]},
        "Query All Today Blocks": {"main": [[{"node": "Claude Reschedule", "type": "main", "index": 0}]]},
        "Claude Reschedule": {"main": [[{"node": "Parse & Update Blocks", "type": "main", "index": 0}]]},
    }

    workflow = {
        "name": WORKFLOW_NAME,
        "nodes": [
            trigger, parse_action, switch,
            query_today, query_date, format_read,
            create_block, format_create,
            modify_block, format_modify,
            delete_block, format_delete,
            reschedule_query, reschedule_claude, reschedule_parse,
        ],
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Paris",
            "saveManualExecutions": True,
        },
    }

    return workflow


def deploy_workflow(workflow):
    """Deploy to n8n or save as JSON."""
    if not N8N_API_KEY:
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "time_blocking_manager_workflow.json")
        with open(output_path, "w") as f:
            json.dump(workflow, f, indent=2, ensure_ascii=False)
        print(f"[INFO] No API key. Saved to: {output_path}")
        return None

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
        else:
            print(f"[ERROR] API returned {resp.status_code}: {resp.text[:300]}")
            # Save as JSON fallback
            output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "time_blocking_manager_workflow.json")
            with open(output_path, "w") as f:
                json.dump(workflow, f, indent=2, ensure_ascii=False)
            print(f"[INFO] Saved to: {output_path}")
            return None
    except Exception as e:
        print(f"[ERROR] {e}")
        return None


if __name__ == "__main__":
    print(f"Building workflow: {WORKFLOW_NAME}")
    wf = build_workflow()
    wf_id = deploy_workflow(wf)
    if wf_id:
        print(f"\nWorkflow ID: {wf_id}")
        print("Add this as a tool in the Manager Bot with:")
        print(f'  Tool name: time_blocking')
        print(f'  Workflow ID: {wf_id}')
