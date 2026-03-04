"""
Deploy Project Update System for n8n + Notion.

Part 1: Create 'Sub: Project Update' workflow (Option A — Telegram commands)
Part 2: Add it as tool #10 to Manager Agent v3
Part 3: Extend Monitoring workflow with auto-tracking (Option B)
"""

import json
import requests
import sys

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9."
    "sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
)
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# IDs
PROJECTS_DB_ID = "305da200b2d68145bc16eaee02925a14"
NOTION_CRED = {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}
MANAGER_WF_ID = "614eolE935GVV5sT"
MONITORING_WF_ID = "3znSLoSlI0XggV4l"


# ── Part 1: Sub: Project Update workflow ─────────────────────────────────

def create_project_update_workflow():
    """Create a dedicated workflow for project status updates via Telegram."""

    parse_input_js = r"""
// Parse input from Manager Agent
// The Agent sends a query string like:
//   "update Review Autopilot | In Progress | teste en prod avec vrais avis"
//   "list"
//   "status Review Autopilot"
const raw = $json.query || $json.chatInput || $json.text || '';
const input = raw.trim();

if (!input) {
  return [{ json: { action: 'error', message: 'Aucune commande recue.' } }];
}

const lower = input.toLowerCase();

// Action: list
if (lower === 'list' || lower.startsWith('liste') || lower.startsWith('tous les projets')) {
  return [{ json: { action: 'list', searchTerm: '', newStatus: '', note: '' } }];
}

// Action: status check
if (lower.startsWith('status ') || lower.startsWith('statut ')) {
  const project = input.substring(input.indexOf(' ') + 1).trim();
  return [{ json: { action: 'status', searchTerm: project, newStatus: '', note: '' } }];
}

// Action: update (default)
// Parse: "update PROJECT | STATUS | NOTE" or "PROJECT | STATUS | NOTE"
let text = input;
if (lower.startsWith('update ') || lower.startsWith('maj ') || lower.startsWith('mettre a jour ')) {
  text = text.substring(text.indexOf(' ') + 1).trim();
}

// Split by | or —
const parts = text.split(/\s*[\|—]\s*/);
const projectName = (parts[0] || '').trim();

// Map French/English status names to Notion values
const STATUS_MAP = {
  'backlog': 'Backlog',
  'ready': 'Ready To Start',
  'ready to start': 'Ready To Start',
  'pret': 'Ready To Start',
  'in progress': 'In Progress',
  'en cours': 'In Progress',
  'blocked': 'Blocked',
  'bloque': 'Blocked',
  'complete': 'Complete',
  'termine': 'Complete',
  'fini': 'Complete',
  'done': 'Complete',
  'archive': 'Archive'
};

let newStatus = '';
let note = '';

if (parts.length >= 2) {
  const statusRaw = parts[1].trim().toLowerCase();
  newStatus = STATUS_MAP[statusRaw] || '';
  // If not a known status, treat as note
  if (!newStatus) {
    note = parts[1].trim();
  }
}
if (parts.length >= 3) {
  note = parts.slice(2).join(' | ').trim();
}

// If no status found but got a percentage, map it
const pctMatch = text.match(/(\d+)\s*%/);
if (pctMatch && !newStatus) {
  const pct = parseInt(pctMatch[1]);
  if (pct >= 100) newStatus = 'Complete';
  else if (pct > 0) newStatus = 'In Progress';
}

return [{ json: {
  action: projectName ? 'update' : 'list',
  searchTerm: projectName,
  newStatus,
  note
}}];
"""

    process_results_js = r"""
// Process Notion search results and prepare update
const input = $('Parse Input').first().json;
const results = $json.results || [];

if (input.action === 'list') {
  // Format all projects as a list
  if (results.length === 0) {
    return [{ json: { found: false, message: 'Aucun projet trouve dans la base.' } }];
  }
  let msg = 'PROJETS ACTIFS :\n\n';
  for (const page of results) {
    const props = page.properties || {};
    const name = props.Name?.title?.[0]?.text?.content || 'Sans nom';
    const status = props.Status?.status?.name || '?';
    const category = props.Category?.select?.name || '';
    const type = props.Type?.select?.name || '';
    msg += `• ${name}\n  Status: ${status} | ${category} ${type}\n`;
  }
  return [{ json: { found: true, needsUpdate: false, message: msg } }];
}

// Find best match for the search term
const searchLower = input.searchTerm.toLowerCase();
let bestMatch = null;
let bestScore = 0;

for (const page of results) {
  const props = page.properties || {};
  const name = (props.Name?.title?.[0]?.text?.content || '').toLowerCase();

  // Exact match
  if (name === searchLower) {
    bestMatch = page;
    bestScore = 100;
    break;
  }

  // Contains match
  if (name.includes(searchLower) || searchLower.includes(name)) {
    const score = Math.min(name.length, searchLower.length) / Math.max(name.length, searchLower.length) * 80;
    if (score > bestScore) {
      bestScore = score;
      bestMatch = page;
    }
  }

  // Word overlap match
  const searchWords = searchLower.split(/\s+/);
  const nameWords = name.split(/\s+/);
  const overlap = searchWords.filter(w => nameWords.some(nw => nw.includes(w) || w.includes(nw))).length;
  const overlapScore = (overlap / Math.max(searchWords.length, 1)) * 60;
  if (overlapScore > bestScore) {
    bestScore = overlapScore;
    bestMatch = page;
  }
}

if (!bestMatch || bestScore < 20) {
  // List available projects for the user
  const names = results.map(p => p.properties?.Name?.title?.[0]?.text?.content || '?').join(', ');
  return [{ json: {
    found: false,
    needsUpdate: false,
    message: `Projet "${input.searchTerm}" non trouve. Projets disponibles : ${names}`
  }}];
}

const matchedName = bestMatch.properties?.Name?.title?.[0]?.text?.content || '';
const currentStatus = bestMatch.properties?.Status?.status?.name || '?';
const currentDesc = bestMatch.properties?.Description?.rich_text?.[0]?.text?.content || '';

if (input.action === 'status') {
  const desc = currentDesc ? `\nDescription: ${currentDesc}` : '';
  return [{ json: {
    found: true,
    needsUpdate: false,
    message: `Projet: ${matchedName}\nStatus: ${currentStatus}${desc}`
  }}];
}

// Prepare update payload
const updateProps = {};
if (input.newStatus) {
  updateProps.Status = { status: { name: input.newStatus } };
}
if (input.note) {
  // Append note to existing description
  const now = new Date().toLocaleString('fr-FR', { timeZone: 'Europe/Paris' });
  const newDesc = currentDesc
    ? `${currentDesc}\n[${now}] ${input.note}`
    : `[${now}] ${input.note}`;
  updateProps.Description = {
    rich_text: [{ text: { content: newDesc.substring(0, 2000) } }]
  };
}

if (Object.keys(updateProps).length === 0) {
  return [{ json: {
    found: true,
    needsUpdate: false,
    message: `Projet "${matchedName}" trouve (${currentStatus}) mais rien a mettre a jour. Precise un status ou une note.`
  }}];
}

return [{ json: {
  found: true,
  needsUpdate: true,
  pageId: bestMatch.id,
  matchedName,
  previousStatus: currentStatus,
  newStatus: input.newStatus || currentStatus,
  updatePayload: { properties: updateProps },
  message: ''
}}];
"""

    format_response_js = r"""
// Format final response for Manager Agent
const processed = $('Process Results').first().json;

if (!processed.needsUpdate) {
  // Already has a message from Process Results
  return [{ json: { response: processed.message } }];
}

// Update was attempted
const updateResult = $json;
if (updateResult.id) {
  // Success
  let msg = `Projet "${processed.matchedName}" mis a jour :\n`;
  if (processed.previousStatus !== processed.newStatus) {
    msg += `  Status: ${processed.previousStatus} → ${processed.newStatus}\n`;
  }
  const note = $('Parse Input').first().json.note;
  if (note) {
    msg += `  Note ajoutee: ${note}\n`;
  }
  return [{ json: { response: msg } }];
} else {
  return [{ json: { response: `Erreur lors de la mise a jour: ${JSON.stringify(updateResult).substring(0, 200)}` } }];
}
"""

    workflow = {
        "name": "Sub: Project Update - Couche 3b",
        "nodes": [
            # 1. Execute Workflow Trigger
            {
                "parameters": {},
                "id": "trigger",
                "name": "Execute Workflow Trigger",
                "type": "n8n-nodes-base.executeWorkflowTrigger",
                "typeVersion": 1,
                "position": [0, 0],
            },
            # 2. Parse Input
            {
                "parameters": {"jsCode": parse_input_js},
                "id": "parse_input",
                "name": "Parse Input",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [220, 0],
            },
            # 3. HTTP Request: Search Notion DB
            {
                "parameters": {
                    "method": "POST",
                    "url": f"https://api.notion.com/v1/databases/{PROJECTS_DB_ID}/query",
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
                    "jsonBody": '={{ JSON.stringify($json.searchTerm ? {filter: {and: [{property: "Type", select: {equals: "Project"}}, {property: "Name", title: {contains: $json.searchTerm}}]}} : {filter: {property: "Type", select: {equals: "Project"}}}) }}',
                },
                "id": "search_notion",
                "name": "Search Projects",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [440, 0],
                "credentials": {"notionApi": NOTION_CRED},
            },
            # 4. Process Results
            {
                "parameters": {"jsCode": process_results_js},
                "id": "process_results",
                "name": "Process Results",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [660, 0],
            },
            # 5. IF: Needs Update?
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "conditions": [
                            {
                                "id": "update_check",
                                "leftValue": "={{ $json.needsUpdate }}",
                                "rightValue": True,
                                "operator": {
                                    "type": "boolean",
                                    "operation": "equals",
                                    "singleValue": True,
                                },
                            }
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if_update",
                "name": "Needs Update?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [880, 0],
            },
            # 6. HTTP Request: Update Notion Page (true branch)
            {
                "parameters": {
                    "method": "PATCH",
                    "url": "={{ 'https://api.notion.com/v1/pages/' + $json.pageId }}",
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
                    "jsonBody": "={{ JSON.stringify($json.updatePayload) }}",
                },
                "id": "update_notion",
                "name": "Update Project",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1100, -80],
                "credentials": {"notionApi": NOTION_CRED},
            },
            # 7. Format Response (merges both branches)
            {
                "parameters": {"jsCode": format_response_js},
                "id": "format_response",
                "name": "Format Response",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1320, 0],
            },
        ],
        "connections": {
            "Execute Workflow Trigger": {
                "main": [[{"node": "Parse Input", "type": "main", "index": 0}]]
            },
            "Parse Input": {
                "main": [[{"node": "Search Projects", "type": "main", "index": 0}]]
            },
            "Search Projects": {
                "main": [[{"node": "Process Results", "type": "main", "index": 0}]]
            },
            "Process Results": {
                "main": [[{"node": "Needs Update?", "type": "main", "index": 0}]]
            },
            "Needs Update?": {
                "main": [
                    [{"node": "Update Project", "type": "main", "index": 0}],
                    [{"node": "Format Response", "type": "main", "index": 0}],
                ]
            },
            "Update Project": {
                "main": [[{"node": "Format Response", "type": "main", "index": 0}]]
            },
        },
        "settings": {"executionOrder": "v1"},
    }

    print("Part 1: Creating Sub: Project Update workflow...")
    resp = requests.post(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, json=workflow)
    if resp.ok:
        data = resp.json()
        wf_id = data.get("id")
        print(f"  Created: {data.get('name')} (ID: {wf_id})")
        return wf_id
    else:
        print(f"  FAILED: {resp.status_code} — {resp.text[:300]}")
        return None


# ── Part 2: Add tool to Manager Agent ───────────────────────────────────

def add_tool_to_manager(project_wf_id):
    """Add the project-update tool as tool #10 to Manager Agent v3."""

    print(f"\nPart 2: Adding project tool to Manager Agent...")

    # Fetch current workflow
    resp = requests.get(f"{N8N_URL}/api/v1/workflows/{MANAGER_WF_ID}", headers=HEADERS)
    if not resp.ok:
        print(f"  FAILED to fetch Manager Agent: {resp.status_code}")
        return False

    wf = resp.json()
    nodes = wf.get("nodes", [])
    connections = wf.get("connections", {})

    # 1. Add the new tool node
    new_tool_node = {
        "parameters": {
            "name": "project",
            "description": (
                "Gestion des projets dans Notion (Projects & Tasks DB). "
                "Actions disponibles :\n"
                "- 'update NOM_PROJET | STATUS | NOTE' : Met a jour le statut et ajoute une note. "
                "Status valides: Backlog, Ready To Start, In Progress, Blocked, Complete, Archive. "
                "Aliases FR: pret, en cours, bloque, termine, fini.\n"
                "- 'list' : Liste tous les projets actifs avec leur statut.\n"
                "- 'status NOM_PROJET' : Verifie le statut d'un projet.\n"
                "Exemples: 'update Review Autopilot | In Progress | teste en prod', "
                "'update Site | 80% | landing page terminee', 'list', 'status Review Autopilot'"
            ),
            "workflowId": {
                "__rl": True,
                "value": project_wf_id,
                "mode": "id",
            },
        },
        "id": "tool_project",
        "name": "Tool: project",
        "type": "@n8n/n8n-nodes-langchain.toolWorkflow",
        "typeVersion": 2,
        "position": [440, 800],  # Below existing tools
    }

    nodes.append(new_tool_node)

    # 2. Connect new tool to Agent Orchestrator
    agent_node_name = "Agent Orchestrator"
    if agent_node_name not in connections:
        # Find the actual agent node name
        for node in nodes:
            if node.get("type") == "@n8n/n8n-nodes-langchain.agent":
                agent_node_name = node["name"]
                break

    # Add ai_tool connection from new tool to Agent
    tool_name = "Tool: project"
    connections[tool_name] = {
        "ai_tool": [[{"node": agent_node_name, "type": "ai_tool", "index": 0}]]
    }

    # 3. Update system prompt to include project management
    for node in nodes:
        if node.get("type") == "@n8n/n8n-nodes-langchain.agent":
            current_prompt = node["parameters"]["options"]["systemMessage"]

            # Add project tool to the tools section
            project_section = """
10. project : Gestion des projets. Mettre a jour le statut, ajouter des notes, lister les projets.
   Commandes: 'update NOM | STATUS | NOTE', 'list', 'status NOM'.
   Status: Backlog, Ready To Start, In Progress, Blocked, Complete, Archive."""

            # Insert after line 9 (notion tool description)
            prompt_lines = current_prompt.split('\n')
            insert_idx = None
            for i, line in enumerate(prompt_lines):
                if line.strip().startswith('9. notion'):
                    # Find the end of the notion description
                    for j in range(i + 1, len(prompt_lines)):
                        if prompt_lines[j].strip().startswith('==') or (prompt_lines[j].strip() and not prompt_lines[j].startswith('   ')):
                            insert_idx = j
                            break
                    break

            if insert_idx:
                prompt_lines.insert(insert_idx, project_section)
            else:
                # Fallback: append before RACCOURCIS section
                for i, line in enumerate(prompt_lines):
                    if '== RACCOURCIS ==' in line:
                        prompt_lines.insert(i, project_section + '\n')
                        break

            # Add shortcut
            for i, line in enumerate(prompt_lines):
                if '/notion->notion' in line:
                    prompt_lines[i] = line + ', /projet->project, /project->project'
                    break

            # Add chaining example
            for i, line in enumerate(prompt_lines):
                if '"Quelles sont mes forces ?"' in line:
                    prompt_lines.insert(i + 1,
                        '- "Mets a jour Review Autopilot" -> project avec le statut/note\n'
                        '- "Ou en sont mes projets ?" -> project (list), puis strategy si pertinent')
                    break

            node["parameters"]["options"]["systemMessage"] = '\n'.join(prompt_lines)
            break

    # 4. Push updated workflow (without 'active' field)
    update_payload = {
        "name": wf.get("name"),
        "nodes": nodes,
        "connections": connections,
        "settings": wf.get("settings", {}),
    }

    resp = requests.put(
        f"{N8N_URL}/api/v1/workflows/{MANAGER_WF_ID}",
        headers=HEADERS,
        json=update_payload,
    )
    if resp.ok:
        print(f"  Manager Agent updated with project tool (workflow: {project_wf_id})")
        # Re-activate
        resp2 = requests.post(
            f"{N8N_URL}/api/v1/workflows/{MANAGER_WF_ID}/activate", headers=HEADERS
        )
        if resp2.ok:
            print(f"  Manager Agent re-activated")
        return True
    else:
        print(f"  FAILED to update Manager Agent: {resp.status_code}")
        print(f"  Response: {resp.text[:400]}")
        return False


# ── Part 3: Extend Monitoring with auto-tracking ────────────────────────

def extend_monitoring():
    """Add automatic project tracking to the monitoring workflow."""

    print(f"\nPart 3: Extending monitoring workflow with auto-tracking...")

    # Fetch current monitoring workflow
    resp = requests.get(f"{N8N_URL}/api/v1/workflows/{MONITORING_WF_ID}", headers=HEADERS)
    if not resp.ok:
        print(f"  FAILED to fetch Monitoring workflow: {resp.status_code}")
        return False

    wf = resp.json()
    nodes = wf.get("nodes", [])
    connections = wf.get("connections", {})

    # New nodes to add for auto-tracking
    auto_track_js = r"""
// Map workflow executions to projects for auto-tracking
const data = $('Fetch Executions').first().json;
const logs = data.logs || [];
const stats = data.stats;

// Workflow-to-Project mapping (keyword-based)
const PROJECT_KEYWORDS = {
  "Deployer Review Autopilot en production": ["review", "autopilot"],
  "Creer le site vitrine Adaptive Logic (v1)": ["site", "vitrine", "adaptive"],
  "Contacter les 10 premiers prospects": ["prospect", "opportunity", "scout"],
  "Lister 20 commerces cibles a Avignon": ["prospect", "commerces"],
  "Preparer le pitch et la demo Review Autopilot": ["review", "pitch", "demo"],
};

// Group executions by related project
const projectUpdates = {};

for (const log of logs) {
  const wfNameLower = (log.workflow || '').toLowerCase();

  for (const [project, keywords] of Object.entries(PROJECT_KEYWORDS)) {
    const matches = keywords.some(kw => wfNameLower.includes(kw));
    if (matches) {
      if (!projectUpdates[project]) {
        projectUpdates[project] = { success: 0, error: 0, total: 0, lastExec: '' };
      }
      projectUpdates[project].total++;
      if (log.status === 'Error') projectUpdates[project].error++;
      else projectUpdates[project].success++;
      if (!projectUpdates[project].lastExec || log.startedAt > projectUpdates[project].lastExec) {
        projectUpdates[project].lastExec = log.startedAt;
      }
    }
  }
}

// Build update items
const items = [];
for (const [project, info] of Object.entries(projectUpdates)) {
  const now = new Date().toLocaleString('fr-FR', { timeZone: 'Europe/Paris' });
  const statusEmoji = info.error > 0 ? '⚠️' : '✅';
  const note = `${statusEmoji} [Auto ${now}] ${info.total} exec (${info.success} OK, ${info.error} err)`;

  items.push({
    json: {
      projectName: project,
      autoNote: note,
      hasErrors: info.error > 0
    }
  });
}

// If no project-related executions, skip
if (items.length === 0) {
  return [{ json: { skip: true } }];
}

return items;
"""

    auto_search_js = r"""
// For each project that had executions, search in Notion
const projectName = $json.projectName;
const autoNote = $json.autoNote;

// We'll pass the search term and note to the HTTP Request node
return [{ json: {
  searchTerm: projectName,
  autoNote: autoNote,
  queryBody: {
    filter: {
      and: [
        { property: "Type", select: { equals: "Project" } },
        { property: "Name", title: { contains: projectName.substring(0, 30) } }
      ]
    },
    page_size: 5
  }
}}];
"""

    auto_update_js = r"""
// Process search results and update the project description
const searchInput = $('Auto: Prepare Search').first().json;
const results = $json.results || [];

if (results.length === 0) {
  return [{ json: { skip: true } }];
}

// Find best match
const target = searchInput.searchTerm.toLowerCase();
let bestMatch = results[0]; // Default to first result

for (const page of results) {
  const name = (page.properties?.Name?.title?.[0]?.text?.content || '').toLowerCase();
  if (name.includes(target) || target.includes(name)) {
    bestMatch = page;
    break;
  }
}

// Get current description and append auto note
const currentDesc = bestMatch.properties?.Description?.rich_text?.[0]?.text?.content || '';
const lines = currentDesc.split('\n');

// Remove previous auto-update lines (keep only the latest)
const cleanLines = lines.filter(l => !l.includes('[Auto '));
cleanLines.push(searchInput.autoNote);
const newDesc = cleanLines.join('\n').substring(0, 2000);

return [{ json: {
  pageId: bestMatch.id,
  updatePayload: {
    properties: {
      Description: {
        rich_text: [{ text: { content: newDesc } }]
      }
    }
  }
}}];
"""

    # Add new nodes
    new_nodes = [
        # Auto-track: Map executions to projects
        {
            "parameters": {"jsCode": auto_track_js},
            "id": "auto_track",
            "name": "Auto: Map to Projects",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1540, 0],
        },
        # Auto-track: IF not skip
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "auto_skip",
                            "leftValue": "={{ $json.skip }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "notEquals",
                                "singleValue": True,
                            },
                        }
                    ],
                    "combinator": "and",
                },
            },
            "id": "auto_if_skip",
            "name": "Auto: Has Updates?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [1760, 0],
        },
        # Auto-track: Prepare search for each project
        {
            "parameters": {"jsCode": auto_search_js},
            "id": "auto_prepare_search",
            "name": "Auto: Prepare Search",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1980, -60],
        },
        # Auto-track: Search Notion for the project
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{PROJECTS_DB_ID}/query",
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
                "jsonBody": "={{ JSON.stringify($json.queryBody) }}",
            },
            "id": "auto_search_notion",
            "name": "Auto: Search Project",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2200, -60],
            "credentials": {"notionApi": NOTION_CRED},
        },
        # Auto-track: Process and prepare update
        {
            "parameters": {"jsCode": auto_update_js},
            "id": "auto_process",
            "name": "Auto: Process Update",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2420, -60],
        },
        # Auto-track: Update Notion page
        {
            "parameters": {
                "method": "PATCH",
                "url": "={{ 'https://api.notion.com/v1/pages/' + $json.pageId }}",
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
                "jsonBody": "={{ JSON.stringify($json.updatePayload) }}",
            },
            "id": "auto_update_notion",
            "name": "Auto: Update Project",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2640, -60],
            "credentials": {"notionApi": NOTION_CRED},
            "onError": "continueRegularOutput",
        },
    ]

    nodes.extend(new_nodes)

    # Add connections for auto-tracking
    # The auto-track chain starts after "Update Dashboard" node
    connections["Update Dashboard"] = {
        "main": [[{"node": "Auto: Map to Projects", "type": "main", "index": 0}]]
    }
    connections["Auto: Map to Projects"] = {
        "main": [[{"node": "Auto: Has Updates?", "type": "main", "index": 0}]]
    }
    connections["Auto: Has Updates?"] = {
        "main": [
            [{"node": "Auto: Prepare Search", "type": "main", "index": 0}],
            [],  # false branch — skip
        ]
    }
    connections["Auto: Prepare Search"] = {
        "main": [[{"node": "Auto: Search Project", "type": "main", "index": 0}]]
    }
    connections["Auto: Search Project"] = {
        "main": [[{"node": "Auto: Process Update", "type": "main", "index": 0}]]
    }
    connections["Auto: Process Update"] = {
        "main": [[{"node": "Auto: Update Project", "type": "main", "index": 0}]]
    }

    # Push updated workflow
    update_payload = {
        "name": wf.get("name"),
        "nodes": nodes,
        "connections": connections,
        "settings": wf.get("settings", {}),
    }

    resp = requests.put(
        f"{N8N_URL}/api/v1/workflows/{MONITORING_WF_ID}",
        headers=HEADERS,
        json=update_payload,
    )
    if resp.ok:
        print(f"  Monitoring workflow extended with 6 auto-tracking nodes")
        # Re-activate
        resp2 = requests.post(
            f"{N8N_URL}/api/v1/workflows/{MONITORING_WF_ID}/activate", headers=HEADERS
        )
        if resp2.ok:
            print(f"  Monitoring workflow re-activated")
        return True
    else:
        print(f"  FAILED: {resp.status_code}")
        print(f"  Response: {resp.text[:400]}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DEPLOYING PROJECT UPDATE SYSTEM")
    print("=" * 60)

    # Part 1: Create Sub: Project Update workflow
    project_wf_id = create_project_update_workflow()
    if not project_wf_id:
        print("\nABORTED: Could not create project update workflow.")
        sys.exit(1)

    # Part 2: Add tool to Manager Agent
    ok = add_tool_to_manager(project_wf_id)
    if not ok:
        print("\nWARNING: Manager Agent update failed. Tool created but not connected.")

    # Part 3: Extend monitoring with auto-tracking
    ok2 = extend_monitoring()
    if not ok2:
        print("\nWARNING: Monitoring extension failed.")

    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE")
    print("=" * 60)
    print(f"\nProject Update workflow: {project_wf_id}")
    print("Manager Agent: tool #10 'project' added")
    print("Monitoring: auto-tracking enabled")
    print("\nUsage via Telegram:")
    print("  /projet Review Autopilot | In Progress | teste en prod")
    print("  /projet list")
    print("  /projet status Review Autopilot")
    print("\nAuto-tracking: updates project descriptions hourly based on workflow executions")


if __name__ == "__main__":
    main()
