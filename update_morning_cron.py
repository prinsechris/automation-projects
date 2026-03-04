#!/usr/bin/env python3
"""
Update Morning CRON workflow (EGzaElc2JwWUCBK2) to add TODAY'S FOCUS auto-update.

Adds a parallel branch after "Today Info" that:
1. Queries Projects & Tasks DB for active tasks (In Progress, Ready To Start)
2. Queries Goals DB for active goals
3. Picks top 3 focus items based on priority + due date urgency
4. Updates the Command Center TODAY'S FOCUS callout via Notion API v3

Preserves all existing nodes and connections (habits/streaks branch).
"""

import json
import requests
import time
import uuid
from pathlib import Path

# --- Configuration ---
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9."
    "sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
)
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}
WORKFLOW_ID = "EGzaElc2JwWUCBK2"

# Notion IDs
PROJECTS_TASKS_DB = "305da200-b2d6-818e-bad3-000b048788f1"  # data source / collection ID
PROJECTS_TASKS_DB_API = "305da200b2d6818ebad3000b048788f1"  # for official API (no dashes)
GOALS_DB_API = "affa9ce1a3d74182a87d8cbabf6fa983"
COMMAND_CENTER_ID = "306da200-b2d6-819c-8863-cf78f61ae670"

# Command Center block IDs (verified from inspection)
TODAYS_FOCUS_CALLOUT_ID = "7149701d-765e-422c-86f5-cb556c06604b"
TODAYS_FOCUS_TITLE_BLOCK = "221933b9-7445-4e16-8110-e5da2936e8d0"
TODAYS_FOCUS_CONTENT_BLOCK = "8527fdd4-c139-4348-9436-bb8e63016b65"

# Notion token for API v3
NOTION_TOKEN = (Path.home() / ".notion-token").read_text().strip()

# Notion credentials for n8n nodes
NOTION_CREDENTIAL = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}


def new_id():
    return str(uuid.uuid4())


def build_new_nodes():
    """Build the new nodes for the TODAY'S FOCUS branch."""

    # =========================================================
    # Node 1: Get Active Tasks (HTTP Request to Notion API)
    # =========================================================
    # Query the Projects & Tasks DB for tasks/sub-tasks that are
    # In Progress or Ready To Start, with priority Critical/High/Medium
    get_tasks_body = json.dumps({
        "filter": {
            "and": [
                {
                    "or": [
                        {"property": "Status", "status": {"equals": "In Progress"}},
                        {"property": "Status", "status": {"equals": "Ready To Start"}}
                    ]
                },
                {
                    "or": [
                        {"property": "Type", "select": {"equals": "Task"}},
                        {"property": "Type", "select": {"equals": "Sub-task"}},
                        {"property": "Type", "select": {"equals": "Project"}}
                    ]
                },
                {
                    "or": [
                        {"property": "Priority", "select": {"equals": "Critical"}},
                        {"property": "Priority", "select": {"equals": "High"}},
                        {"property": "Priority", "select": {"equals": "Medium"}}
                    ]
                }
            ]
        },
        "sorts": [
            {"property": "Priority", "direction": "ascending"},
            {"property": "Due Date", "direction": "ascending"}
        ],
        "page_size": 20
    })

    get_tasks = {
        "id": new_id(),
        "name": "Get Active Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [500, -200],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{PROJECTS_TASKS_DB_API}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": get_tasks_body,
            "options": {}
        },
        "credentials": NOTION_CREDENTIAL
    }

    # =========================================================
    # Node 2: Wait 1s (rate limiting between Notion API calls)
    # =========================================================
    wait_focus = {
        "id": new_id(),
        "name": "Wait Focus 1s",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [720, -200],
        "parameters": {"amount": 1, "unit": "seconds"},
        "webhookId": "wait-focus-1"
    }

    # =========================================================
    # Node 3: Get Active Goals (HTTP Request to Notion API)
    # =========================================================
    get_goals_body = json.dumps({
        "filter": {
            "and": [
                {
                    "or": [
                        {"property": "Status", "select": {"equals": "\ud83d\udd25 In Progress"}},
                        {"property": "Status", "select": {"equals": "\ud83d\udcad Not Started"}}
                    ]
                },
                {
                    "or": [
                        {"property": "Type", "select": {"equals": "\ud83d\uddd3\ufe0f Quarterly Goal"}},
                        {"property": "Type", "select": {"equals": "\ud83d\udcc6 Monthly Goal"}}
                    ]
                }
            ]
        },
        "sorts": [
            {"property": "Type", "direction": "ascending"}
        ],
        "page_size": 10
    })

    get_goals = {
        "id": new_id(),
        "name": "Get Active Goals",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [940, -200],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{GOALS_DB_API}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": get_goals_body,
            "options": {}
        },
        "credentials": NOTION_CREDENTIAL
    }

    # =========================================================
    # Node 4: Pick Top 3 Focus Items (Code node)
    # =========================================================
    pick_focus_code = r"""
// Get data from previous nodes
const tasksData = $('Get Active Tasks').first().json;
const goalsData = $('Get Active Goals').first().json;
const todayInfo = $('Today Info').first().json;
const today = todayInfo.today; // YYYY-MM-DD

const tasks = (tasksData.results || []);
const goals = (goalsData.results || []);

// Priority weights
const PRIORITY_WEIGHT = {
    'Critical': 4,
    'High': 3,
    'Medium': 2,
    'Low': 1
};

// Helper: extract property values from Notion API response
function getProp(page, name, type) {
    const prop = (page.properties || {})[name];
    if (!prop) return null;

    switch (type) {
        case 'title':
            return (prop.title || []).map(t => t.plain_text || '').join('') || null;
        case 'rich_text':
            return (prop.rich_text || []).map(t => t.plain_text || '').join('') || null;
        case 'select':
            return prop.select ? prop.select.name : null;
        case 'status':
            return prop.status ? prop.status.name : null;
        case 'date':
            return prop.date ? prop.date.start : null;
        case 'number':
            return prop.number;
        default:
            return null;
    }
}

// Score each task
const scoredItems = [];

for (const task of tasks) {
    const name = getProp(task, 'Name', 'title') || getProp(task, 'Task', 'title') || 'Sans nom';
    const priority = getProp(task, 'Priority', 'select') || 'Medium';
    const status = getProp(task, 'Status', 'status') || '';
    const dueDate = getProp(task, 'Due Date', 'date');
    const type = getProp(task, 'Type', 'select') || 'Task';
    const category = getProp(task, 'Category', 'select') || '';

    // Base score from priority
    let score = PRIORITY_WEIGHT[priority] || 2;

    // Due date urgency bonus
    if (dueDate) {
        const due = new Date(dueDate);
        const now = new Date(today);
        const diffDays = Math.floor((due - now) / (1000 * 60 * 60 * 24));

        if (diffDays < 0) {
            score += 3; // Overdue
        } else if (diffDays === 0) {
            score += 2; // Due today
        } else if (diffDays <= 7) {
            score += 1; // Due this week
        }
    }

    // Type preference: Tasks > Sub-tasks > Projects
    if (type === 'Task') {
        score += 0.3;
    } else if (type === 'Sub-task') {
        score += 0.2;
    } else if (type === 'Project') {
        score += 0.1;
    }

    // In Progress gets a slight boost over Ready To Start
    if (status === 'In Progress') {
        score += 0.5;
    }

    scoredItems.push({
        id: task.id,
        name: name,
        priority: priority,
        type: type,
        status: status,
        dueDate: dueDate,
        category: category,
        score: score,
        kind: 'task'
    });
}

// Also score quarterly/monthly goals as context
for (const goal of goals) {
    const name = getProp(goal, 'Name', 'title') || 'Sans nom';
    const goalType = getProp(goal, 'Type', 'select') || '';
    const targetDate = getProp(goal, 'Target Date', 'date');
    const progress = getProp(goal, 'Progress %', 'number') || 0;
    const status = getProp(goal, 'Status', 'select') || '';

    // Goals get lower base score (context, not direct actions)
    let score = 1.5;

    // Quarterly goals with deadline urgency
    if (targetDate) {
        const target = new Date(targetDate);
        const now = new Date(today);
        const diffDays = Math.floor((target - now) / (1000 * 60 * 60 * 24));

        if (diffDays < 0) {
            score += 2;
        } else if (diffDays <= 7) {
            score += 1.5;
        } else if (diffDays <= 30) {
            score += 0.5;
        }
    }

    // Low progress = more urgent
    if (progress < 0.3) {
        score += 0.5;
    }

    scoredItems.push({
        id: goal.id,
        name: name,
        priority: goalType,
        type: 'Goal',
        status: status,
        dueDate: targetDate,
        category: '',
        score: score,
        progress: Math.round(progress * 100),
        kind: 'goal'
    });
}

// Sort by score descending
scoredItems.sort((a, b) => b.score - a.score);

// Pick top 3
const top3 = scoredItems.slice(0, 3);

// Build the focus text for the callout
const priorityEmoji = {
    'Critical': '\u2757',   // exclamation
    'High': '\ud83d\udd34', // red circle
    'Medium': '\ud83d\udfe0', // orange circle
    'Low': '\ud83d\udfe2',   // green circle
};

const typeEmoji = {
    'Task': '\u2705',       // check
    'Sub-task': '\u25ab\ufe0f', // white square
    'Project': '\ud83d\udcc1',  // folder
    'Goal': '\ud83c\udfaf',    // target
};

let focusLines = [];
for (let i = 0; i < top3.length; i++) {
    const item = top3[i];
    const pEmoji = priorityEmoji[item.priority] || '\ud83d\udfe1';
    const tEmoji = typeEmoji[item.type] || '\u25aa\ufe0f';

    let duePart = '';
    if (item.dueDate) {
        const due = new Date(item.dueDate);
        const now = new Date(today);
        const diffDays = Math.floor((due - now) / (1000 * 60 * 60 * 24));
        if (diffDays < 0) {
            duePart = ` | \u26a0\ufe0f ${Math.abs(diffDays)}j en retard`;
        } else if (diffDays === 0) {
            duePart = ' | \u23f0 Aujourd\'hui';
        } else if (diffDays <= 7) {
            duePart = ` | \ud83d\udcc5 dans ${diffDays}j`;
        }
    }

    let progressPart = '';
    if (item.kind === 'goal' && item.progress !== undefined) {
        progressPart = ` (${item.progress}%)`;
    }

    focusLines.push(`${i + 1}. ${pEmoji} ${item.name}${progressPart}${duePart}`);
}

// If no items found
if (focusLines.length === 0) {
    focusLines = ['Aucune tache prioritaire trouvee.', 'Toutes les taches sont completees ou en Backlog.'];
}

// Build title line
const titleLine = `TODAY'S FOCUS \u2014 ${today}`;

// Count by type for summary
const taskCount = top3.filter(i => i.kind === 'task').length;
const goalCount = top3.filter(i => i.kind === 'goal').length;
let summaryParts = [];
if (taskCount > 0) summaryParts.push(`${taskCount} tache${taskCount > 1 ? 's' : ''}`);
if (goalCount > 0) summaryParts.push(`${goalCount} objectif${goalCount > 1 ? 's' : ''}`);
const summaryLine = summaryParts.length > 0
    ? `${summaryParts.join(' + ')} | Tri auto par priorite + deadline`
    : 'Aucun item prioritaire';

// Full text for the content block
const focusText = focusLines.join('\n');

// Build Notion API v3 title arrays for the blocks
// Title block: "TODAY'S FOCUS — 2026-02-27"
const titleArray = [
    ["\ud83c\udfaf TODAY'S FOCUS", [["b"]]],
    [" \u2014 " + today]
];

// Content block: the focus items
const contentSegments = [];
contentSegments.push([focusLines[0]]);
for (let i = 1; i < focusLines.length; i++) {
    contentSegments.push(["\n"]);
    contentSegments.push([focusLines[i]]);
}
contentSegments.push(["\n"]);
contentSegments.push([summaryLine, [["i"]]]);

return [{json: {
    titleArray: JSON.stringify(titleArray),
    contentArray: JSON.stringify(contentSegments),
    focusText: focusText,
    summaryLine: summaryLine,
    titleLine: titleLine,
    top3: top3,
    totalCandidates: scoredItems.length
}}];
""".strip()

    pick_focus = {
        "id": new_id(),
        "name": "Pick Top 3 Focus",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1160, -200],
        "parameters": {"jsCode": pick_focus_code}
    }

    # =========================================================
    # Node 5: Wait before update (rate limiting)
    # =========================================================
    wait_update = {
        "id": new_id(),
        "name": "Wait Focus 2s",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [1380, -200],
        "parameters": {"amount": 2, "unit": "seconds"},
        "webhookId": "wait-focus-2"
    }

    # =========================================================
    # Node 6: Update Focus Title (Notion API v3 submitTransaction)
    # =========================================================
    # Updates the title text block inside the TODAY'S FOCUS callout
    update_title = {
        "id": new_id(),
        "name": "Update Focus Title",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1600, -300],
        "parameters": {
            "method": "POST",
            "url": "https://www.notion.so/api/v3/saveTransactions",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Cookie", "value": f"token_v2={NOTION_TOKEN}"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ requestId: "focus-title-" + Date.now(), transactions: [{ id: "focus-title-tx-" + Date.now(), spaceId: "' + _get_space_id() + '", operations: [{ pointer: { table: "block", id: "' + TODAYS_FOCUS_TITLE_BLOCK + '" }, path: ["properties", "title"], command: "set", args: JSON.parse($json.titleArray) }] }] }) }}',
            "options": {}
        }
    }

    # =========================================================
    # Node 7: Wait 1s between updates
    # =========================================================
    wait_between = {
        "id": new_id(),
        "name": "Wait Focus 3s",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [1820, -300],
        "parameters": {"amount": 1, "unit": "seconds"},
        "webhookId": "wait-focus-3"
    }

    # =========================================================
    # Node 8: Update Focus Content (Notion API v3 submitTransaction)
    # =========================================================
    # Updates the content text block with the top 3 items
    update_content = {
        "id": new_id(),
        "name": "Update Focus Content",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2040, -300],
        "parameters": {
            "method": "POST",
            "url": "https://www.notion.so/api/v3/saveTransactions",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Cookie", "value": f"token_v2={NOTION_TOKEN}"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ requestId: "focus-content-" + Date.now(), transactions: [{ id: "focus-content-tx-" + Date.now(), spaceId: "' + _get_space_id() + '", operations: [{ pointer: { table: "block", id: "' + TODAYS_FOCUS_CONTENT_BLOCK + '" }, path: ["properties", "title"], command: "set", args: JSON.parse($json.contentArray) }] }] }) }}',
            "options": {}
        }
    }

    return [get_tasks, wait_focus, get_goals, pick_focus, wait_update,
            update_title, wait_between, update_content]


def _get_space_id():
    """Fetch the space_id from Command Center via Notion API v3."""
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"token_v2={NOTION_TOKEN}"
    }
    resp = requests.post("https://www.notion.so/api/v3/loadPageChunk", headers=headers, json={
        "pageId": COMMAND_CENTER_ID,
        "limit": 1,
        "cursor": {"stack": []},
        "chunkNumber": 0,
        "verticalColumns": False,
    })
    resp.raise_for_status()
    data = resp.json()
    blocks = data.get("recordMap", {}).get("block", {})
    page = blocks.get(COMMAND_CENTER_ID, {}).get("value", {})
    space_id = page.get("space_id", "")
    if not space_id:
        raise ValueError("Could not fetch space_id from Command Center page")
    return space_id


def build_new_connections(new_nodes):
    """Build the connection entries for the new focus branch.

    Returns a dict of {node_name: connection_spec} to merge into existing connections.
    """
    return {
        # From Get Active Tasks → Wait Focus 1s
        "Get Active Tasks": {
            "main": [[{"node": "Wait Focus 1s", "type": "main", "index": 0}]]
        },
        # From Wait Focus 1s → Get Active Goals
        "Wait Focus 1s": {
            "main": [[{"node": "Get Active Goals", "type": "main", "index": 0}]]
        },
        # From Get Active Goals → Pick Top 3 Focus
        "Get Active Goals": {
            "main": [[{"node": "Pick Top 3 Focus", "type": "main", "index": 0}]]
        },
        # From Pick Top 3 Focus → Wait Focus 2s
        "Pick Top 3 Focus": {
            "main": [[{"node": "Wait Focus 2s", "type": "main", "index": 0}]]
        },
        # From Wait Focus 2s → Update Focus Title
        "Wait Focus 2s": {
            "main": [[{"node": "Update Focus Title", "type": "main", "index": 0}]]
        },
        # From Update Focus Title → Wait Focus 3s
        "Update Focus Title": {
            "main": [[{"node": "Wait Focus 3s", "type": "main", "index": 0}]]
        },
        # From Wait Focus 3s → Update Focus Content
        "Wait Focus 3s": {
            "main": [[{"node": "Update Focus Content", "type": "main", "index": 0}]]
        },
    }


def main():
    print("=" * 60)
    print("  Update Morning CRON — Add TODAY'S FOCUS auto-update")
    print("=" * 60)

    # Step 0: Get space_id from Notion
    print("\n0. Fetching Notion space_id...")
    try:
        space_id = _get_space_id()
        print(f"   Space ID: {space_id}")
    except Exception as e:
        print(f"   ERROR: {e}")
        return False

    # Step 1: Fetch current workflow
    print("\n1. Fetching current workflow...")
    r = requests.get(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=HEADERS,
    )
    if r.status_code != 200:
        print(f"   ERROR: HTTP {r.status_code} — {r.text[:300]}")
        return False

    workflow = r.json()
    current_nodes = workflow.get("nodes", [])
    current_connections = workflow.get("connections", {})
    current_settings = workflow.get("settings", {})

    print(f"   Name: {workflow.get('name')}")
    print(f"   Nodes: {len(current_nodes)}")
    print(f"   Active: {workflow.get('active')}")

    # Verify expected nodes exist
    node_names = [n["name"] for n in current_nodes]
    expected = ["Every Morning 6AM", "Today Info", "Get All Active Habits",
                "Check Streaks", "Streak Broken?", "Reset Streak to 0",
                "Create Habits Stats Entry"]
    missing = [n for n in expected if n not in node_names]
    if missing:
        print(f"   WARNING: Missing expected nodes: {missing}")

    # Check we haven't already added the focus nodes
    if "Get Active Tasks" in node_names:
        print("   ERROR: Focus nodes already exist! Aborting to avoid duplicates.")
        return False

    print(f"   Existing node names: {node_names}")

    # Step 2: Build new nodes
    print("\n2. Building new focus nodes...")
    new_nodes = build_new_nodes()
    for n in new_nodes:
        print(f"   + {n['name']} ({n['type'].split('.')[-1]})")

    # Step 3: Merge nodes
    print("\n3. Merging nodes...")
    merged_nodes = current_nodes + new_nodes
    print(f"   Total nodes: {len(current_nodes)} existing + {len(new_nodes)} new = {len(merged_nodes)}")

    # Step 4: Update connections
    print("\n4. Updating connections...")

    # The key change: "Today Info" currently connects only to "Get All Active Habits"
    # We need it to ALSO connect to "Get Active Tasks" (parallel branch)
    # In n8n, parallel connections = multiple entries in the same output array

    # Current: "Today Info" -> [{"node": "Get All Active Habits"}]
    # New:     "Today Info" -> [{"node": "Get All Active Habits"}, {"node": "Get Active Tasks"}]

    today_info_connections = current_connections.get("Today Info", {}).get("main", [[]])
    if today_info_connections and len(today_info_connections) > 0:
        # Add the new branch to the existing output
        today_info_connections[0].append(
            {"node": "Get Active Tasks", "type": "main", "index": 0}
        )
    else:
        today_info_connections = [[
            {"node": "Get All Active Habits", "type": "main", "index": 0},
            {"node": "Get Active Tasks", "type": "main", "index": 0}
        ]]

    current_connections["Today Info"] = {"main": today_info_connections}

    # Add the new branch connections
    new_connections = build_new_connections(new_nodes)
    current_connections.update(new_connections)

    print(f"   Updated 'Today Info' to fork into 2 branches")
    print(f"   Added {len(new_connections)} new connection entries")
    print(f"   Connection map:")
    for src, conns in current_connections.items():
        targets = []
        for output in conns.get("main", []):
            for conn in output:
                targets.append(conn["node"])
        print(f"     {src} -> {', '.join(targets)}")

    # Step 5: Build the updated workflow payload
    print("\n5. Preparing update payload...")
    update_payload = {
        "name": workflow.get("name", "Gamify -- Daily Morning CRON"),
        "nodes": merged_nodes,
        "connections": current_connections,
        "settings": current_settings,
    }

    # Step 6: Deactivate workflow before update
    print("\n6. Deactivating workflow...")
    r = requests.post(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}/deactivate",
        headers=HEADERS
    )
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        print(f"   WARNING: Could not deactivate: {r.text[:200]}")
    time.sleep(2)

    # Step 7: PUT the updated workflow
    print("\n7. Updating workflow...")
    r = requests.put(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=HEADERS,
        json=update_payload,
    )
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        print(f"   ERROR: {r.text[:500]}")
        # Try to reactivate anyway
        requests.post(
            f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}/activate",
            headers=HEADERS
        )
        return False

    updated = r.json()
    print(f"   Updated nodes: {len(updated.get('nodes', []))}")
    print(f"   Version: {updated.get('versionId', 'N/A')}")

    time.sleep(2)

    # Step 8: Reactivate workflow
    print("\n8. Reactivating workflow...")
    r = requests.post(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}/activate",
        headers=HEADERS
    )
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        print(f"   ERROR: {r.text[:200]}")
        return False

    time.sleep(2)

    # Step 9: Verify
    print("\n9. Verifying...")
    r = requests.get(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=HEADERS,
    )
    if r.status_code == 200:
        verified = r.json()
        v_nodes = [n["name"] for n in verified.get("nodes", [])]
        print(f"   Active: {verified.get('active')}")
        print(f"   Nodes ({len(v_nodes)}): {v_nodes}")

        # Check new nodes are present
        focus_nodes = ["Get Active Tasks", "Get Active Goals", "Pick Top 3 Focus",
                       "Update Focus Title", "Update Focus Content"]
        all_present = all(n in v_nodes for n in focus_nodes)
        print(f"   Focus nodes present: {all_present}")

        # Check connections
        v_conns = verified.get("connections", {})
        today_targets = []
        for output in v_conns.get("Today Info", {}).get("main", []):
            for conn in output:
                today_targets.append(conn["node"])
        print(f"   'Today Info' connects to: {today_targets}")

        if all_present and "Get Active Tasks" in today_targets:
            print("\n   [SUCCESS] Morning CRON updated with TODAY'S FOCUS branch!")
        else:
            print("\n   [WARNING] Some elements may be missing. Check in n8n UI.")
    else:
        print(f"   Could not verify: HTTP {r.status_code}")

    print(f"\n   Open: {N8N_URL}/workflow/{WORKFLOW_ID}")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = main()
    if not success:
        print("\n[FAILED] See errors above.")
        exit(1)
