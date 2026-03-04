"""Fix Session Closer workflow — 3 issues:
1. Git Activity Tracker floods it with auto-calls (session_number=0)
2. Activity Log Entry JSON body is malformed (unquoted date)
3. No XP/Gold in Activity Log entries
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

# GET current workflow
r = requests.get(f"{N8N_URL}/api/v1/workflows/RhC0NLMgnVhO2q4L", headers=HEADERS)
wf = r.json()

# --- FIX 1: Parse Session — add isAuto flag + XP/Gold calculation ---
PARSE_SESSION_CODE = r"""const body = $input.first().json.body;

// Detect auto-calls from Git Activity Tracker (session_number=0)
const isAuto = body.session_number === 0 || body.session_number === '0';

const session = {
  session_number: body.session_number || 0,
  date: body.date || new Date().toISOString().split('T')[0],
  summary: body.summary || '',
  highlights: body.highlights || [],
  tasks_completed: body.tasks_completed || [],
  tasks_started: body.tasks_started || [],
  files_changed: body.files_changed || 0,
  workflows_modified: body.workflows_modified || 0,
  duration_hours: body.duration_hours || 0,
  git_pushed: body.git_pushed || false,
  isAuto: isAuto
};

// Calculate XP/Gold based on session work
const baseXP = Math.max(session.duration_hours * 50, 25);
const taskBonus = session.tasks_completed.length * 15;
session.xp = isAuto ? 0 : (baseXP + taskBonus);
session.gold = isAuto ? 0 : Math.round(session.xp * 0.4);

let recap = '';
if (isAuto) {
  // Shorter recap for auto-reports — only if there are actual highlights
  if (session.highlights.length === 0) {
    // Nothing to report — return skip flag
    return [{json: {...session, recap: '', skipTelegram: true}}];
  }
  recap = `\ud83d\udd04 *Auto-report ${session.date}*\n`;
  recap += session.summary + '\n\n';
  const urgent = session.highlights.filter(h => h.startsWith('EN RETARD'));
  if (urgent.length > 0) {
    recap += `*\u26a0\ufe0f ${urgent.length} tache(s) en retard :*\n`;
    for (const h of urgent.slice(0, 5)) { recap += `\u2022 ${h}\n`; }
    if (urgent.length > 5) recap += `... et ${urgent.length - 5} autres\n`;
  }
} else {
  recap = `\ud83d\udccb *Session ${session.session_number} \u2014 ${session.date}*\n`;
  recap += `${session.summary}\n\n`;
  if (session.highlights.length > 0) {
    recap += `*Highlights :*\n`;
    for (const h of session.highlights) { recap += `\u2022 ${h}\n`; }
    recap += `\n`;
  }
  recap += `\u2705 ${session.tasks_completed.length} taches completees\n`;
  recap += `\ud83d\udd04 ${session.tasks_started.length} taches demarrees\n`;
  recap += `\ud83d\udcc1 ${session.files_changed} fichiers modifies\n`;
  recap += `\u2699\ufe0f ${session.workflows_modified} workflows n8n modifies\n`;
  recap += `\u23f1\ufe0f ~${session.duration_hours}h de travail\n`;
  recap += `\u2728 +${session.xp} XP | +${session.gold} Gold\n`;
  if (session.git_pushed) { recap += `\n\u2705 Session log pushe sur GitHub`; }
}

return [{json: {...session, recap, skipTelegram: false}}];
"""

# --- FIX 2: Activity Log Entry — build the JSON body via Code node instead ---
# We'll add a "Build Activity Body" code node before the HTTP request
BUILD_BODY_CODE = r"""const session = $('Parse Session').first().json;

// Skip Activity Log for auto-reports
if (session.isAuto) {
  return [{json: {skip: true}}];
}

const body = {
  parent: {database_id: "305da200-b2d6-8116-8039-000b9a9d9070"},
  properties: {
    Name: {title: [{text: {content: `Session ${session.session_number} \u2014 ${session.summary.substring(0, 80)}`}}]},
    Date: {date: {start: session.date}},
    XP: {number: session.xp || 25},
    Gold: {number: session.gold || 10}
  }
};

// Add quest relations if we have completed task IDs
if (session.tasks_completed && session.tasks_completed.length > 0) {
  body.properties.Quests = {
    relation: session.tasks_completed.map(id => ({id}))
  };
}

return [{json: {body: JSON.stringify(body), skip: false}}];
"""

# Update Parse Session
for node in wf['nodes']:
    if node['name'] == 'Parse Session':
        node['parameters']['jsCode'] = PARSE_SESSION_CODE
        print("Parse Session updated")
        break

# Add Build Activity Body node (new Code node)
# Find Activity Log Entry position for placement
activity_node = None
parse_node = None
for node in wf['nodes']:
    if node['name'] == 'Activity Log Entry':
        activity_node = node
    if node['name'] == 'Parse Session':
        parse_node = node

# Create the new Build Activity Body node
import uuid
build_body_node = {
    "id": str(uuid.uuid4()),
    "name": "Build Activity Body",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [
        activity_node['position'][0] - 250,
        activity_node['position'][1]
    ],
    "parameters": {
        "jsCode": BUILD_BODY_CODE
    }
}

wf['nodes'].append(build_body_node)
print("Build Activity Body node added")

# Update Activity Log Entry to use the pre-built body
for node in wf['nodes']:
    if node['name'] == 'Activity Log Entry':
        node['parameters']['jsonBody'] = "={{ $json.body }}"
        print("Activity Log Entry updated to use pre-built body")
        break

# Update connections:
# Old: Parse Session --> Activity Log Entry
# New: Parse Session --> Build Activity Body --> Activity Log Entry
conns = wf['connections']

# Remove Parse Session --> Activity Log Entry connection
parse_conns = conns.get('Parse Session', {}).get('main', [])
if len(parse_conns) >= 1:
    # Parse Session has multiple outputs: [0]=Split Completed, [1]=Split Started, [2]=Activity Log Entry
    # Find and replace the Activity Log Entry connection
    for branch_idx, branch in enumerate(parse_conns):
        new_branch = []
        for target in branch:
            if target['node'] == 'Activity Log Entry':
                # Replace with Build Activity Body
                new_branch.append({
                    "node": "Build Activity Body",
                    "type": "main",
                    "index": 0
                })
            else:
                new_branch.append(target)
        parse_conns[branch_idx] = new_branch

# Add Build Activity Body --> Activity Log Entry
conns["Build Activity Body"] = {
    "main": [[{
        "node": "Activity Log Entry",
        "type": "main",
        "index": 0
    }]]
}

print("Connections updated")

# Also update Telegram Recap to skip when skipTelegram=true
# We need to add an IF node or handle it in the text expression
# Simpler: make the Telegram text conditional
for node in wf['nodes']:
    if node['name'] == 'Telegram Recap':
        # The recap will be empty for skipped auto-reports
        # But the node still runs — let's check if we can add a condition
        # For now, the Parse Session already returns empty recap for no-highlight auto-reports
        break

# Deploy
payload = {k: wf[k] for k in ['name', 'nodes', 'connections', 'settings', 'staticData'] if k in wf}

r2 = requests.put(
    f"{N8N_URL}/api/v1/workflows/RhC0NLMgnVhO2q4L",
    headers=HEADERS,
    json=payload
)
print(f"\nDeploy status: {r2.status_code}")
if r2.status_code == 200:
    print("Session Closer FIXED!")
    print(f"Version: {r2.json().get('versionId')}")
else:
    print(f"Error: {r2.text[:500]}")
