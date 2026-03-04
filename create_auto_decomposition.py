#!/usr/bin/env python3
"""Create n8n workflow: Auto-Decomposition de Projets.

Schedule (30min) -> Query Projects sans enfants -> Claude decompose -> Create tasks Notion
-> Update project status -> Telegram notification.

Workflow:
1. Schedule Trigger (every 30 min)
2. Query Projects & Tasks DB: Type=Project, Status IN (Backlog, Ready To Start),
   Downstream relation is_empty (no child tasks yet)
3. For each project, call Claude (Anthropic API) to decompose into 3-8 tasks
4. Create each task in Notion with Upstream = project ID
5. Update project status to "Ready To Start" if was "Backlog"
6. Send Telegram recap

Uses Notion official API via HTTP Request nodes with notionApi credential.
Uses Anthropic API via HTTP Request for structured JSON output.
"""

import json
import requests

# ─── n8n API ──────────────────────────────────────────────────────────────────
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9."
    "sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
)
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# ─── Notion IDs ───────────────────────────────────────────────────────────────
# Page ID (for official API queries)
PROJECTS_DB_PAGE_ID = "305da200-b2d6-8145-bc16-eaee02925a14"
# Collection / data source ID (for creating pages — parent.database_id)
PROJECTS_DB_COLLECTION_ID = "305da200-b2d6-818e-bad3-000b048788f1"

# ─── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_CHAT_ID = "7342622615"

# ─── Credential references ───────────────────────────────────────────────────
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}
ANTHROPIC_CRED_ID = "sE8nBT8crViDOv1E"

# ─── Claude prompt (French) ──────────────────────────────────────────────────
CLAUDE_SYSTEM_PROMPT = r"""Tu es un expert en gestion de projet pour Adaptive Logic, une agence d'automatisation IA.
Ton role est de decomposer un projet en taches actionnables et specifiques.

Regles :
- Genere entre 3 et 8 taches par projet
- Chaque tache doit etre actionnable, specifique et mesurable
- Inclus les dependances entre taches (quelles taches bloquent quelles autres)
- Estime la difficulte et la duree de chaque tache
- Les taches doivent suivre un ordre logique d'execution
- Adapte le niveau de detail au contexte business / automatisation / perso

Retourne UNIQUEMENT un JSON valide (pas de texte autour, pas de ```json) avec cette structure :
{
  "tasks": [
    {
      "name": "Nom court et actionnable de la tache",
      "description": "Description detaillee de ce qu'il faut faire",
      "priority": "Critical" | "High" | "Medium" | "Low",
      "difficulty": "1 - Easy" | "2 - Moderate" | "3 - Hard",
      "duration": "15min" | "30min" | "45min" | "1h" | "1h30" | "2h",
      "order": 1,
      "blocked_by": []
    },
    {
      "name": "Tache 2",
      "description": "...",
      "priority": "High",
      "difficulty": "2 - Moderate",
      "duration": "1h",
      "order": 2,
      "blocked_by": [1]
    }
  ],
  "summary": "Resume en 1-2 phrases de la decomposition"
}

Notes sur les valeurs :
- priority: Critical (urgent + important), High (important), Medium (normal), Low (nice-to-have)
- difficulty: "1 - Easy" (< 30min, simple), "2 - Moderate" (30min-1h30, necessite reflexion), "3 - Hard" (> 1h30, complexe)
- duration: estime le temps reel de travail
- blocked_by: liste des numeros "order" des taches qui doivent etre completees avant
- order: numero sequentiel de la tache (1, 2, 3...)"""

# ─── Notion query filter ─────────────────────────────────────────────────────
QUERY_FILTER = json.dumps({
    "filter": {
        "and": [
            {"property": "Type", "select": {"equals": "Project"}},
            {
                "or": [
                    {"property": "Status", "status": {"equals": "Backlog"}},
                    {"property": "Status", "status": {"equals": "Ready To Start"}}
                ]
            },
            {"property": "Downstream", "relation": {"is_empty": True}}
        ]
    },
    "page_size": 10
})

# ─────────────────────────────────────────────────────────────────────────────
#  WORKFLOW DEFINITION
# ─────────────────────────────────────────────────────────────────────────────
workflow = {
    "name": "Auto-Decomposition Projets",
    "nodes": [
        # ─────────────────────────────────────────────────────────────────
        # 1. Schedule Trigger — every 30 minutes
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "rule": {
                    "interval": [{"field": "minutes", "minutesInterval": 30}]
                }
            },
            "id": "schedule-trigger",
            "name": "Every 30min",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 300]
        },

        # ─────────────────────────────────────────────────────────────────
        # 2. Query Projects — Type=Project, Status=Backlog|Ready To Start,
        #    Downstream is_empty (no child tasks)
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{PROJECTS_DB_PAGE_ID}/query",
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
                "jsonBody": QUERY_FILTER,
                "options": {}
            },
            "id": "query-projects",
            "name": "Query New Projects",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [240, 300],
            "credentials": NOTION_CRED
        },

        # ─────────────────────────────────────────────────────────────────
        # 3. Extract Projects — parse Notion results into clean items
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "jsCode": r"""// Extract project data from Notion API response
const response = $input.first().json;
const results = response.results || [];

if (results.length === 0) {
  return [{json: {skip: true, reason: 'Aucun nouveau projet a decomposer'}}];
}

const projects = results.map(page => {
  const props = page.properties || {};
  const name = props.Name?.title?.[0]?.plain_text || '(sans nom)';
  const status = props.Status?.status?.name || 'Backlog';
  const category = props.Category?.select?.name || '';
  const description = (props.Description?.rich_text || [])
    .map(rt => rt.plain_text)
    .join('') || '';
  const goalRelation = props.Goal?.relation || [];
  const goalId = goalRelation.length > 0 ? goalRelation[0].id : null;

  return {
    json: {
      projectId: page.id,
      projectName: name,
      projectStatus: status,
      projectCategory: category,
      projectDescription: description,
      projectGoalId: goalId,
      projectUrl: page.url || ''
    }
  };
});

return projects;
"""
            },
            "id": "extract-projects",
            "name": "Extract Projects",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [460, 300]
        },

        # ─────────────────────────────────────────────────────────────────
        # 4. Check if skip (no projects found)
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict"
                    },
                    "conditions": [
                        {
                            "id": "skip-check",
                            "leftValue": "={{ $json.skip }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "equals"
                            }
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "if-skip",
            "name": "Has Projects?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [680, 300]
        },

        # ─────────────────────────────────────────────────────────────────
        # 5. Build Claude Prompt — prepare the user message for each project
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "jsCode": "// Build the Claude user prompt for this project\n"
                    "const project = $input.first().json;\n"
                    "\n"
                    "const userPrompt = 'Decompose ce projet en taches actionnables :\\n\\n'"
                    " + '**Projet** : ' + project.projectName + '\\n'"
                    " + '**Categorie** : ' + (project.projectCategory || 'Non definie') + '\\n'"
                    " + '**Description** : ' + (project.projectDescription || 'Pas de description fournie') + '\\n\\n'"
                    " + 'Contexte : Ce projet fait partie du systeme Adaptive Logic (agence automatisation IA pour TPE/PME).\\n'"
                    " + (project.projectCategory === 'Business' ? 'Ce projet a un impact direct sur le chiffre d\\'affaires.\\n' : '')"
                    " + (project.projectCategory === 'Automatisation' ? 'Ce projet concerne l\\'infrastructure technique et les automatisations.\\n' : '')"
                    " + '\\nGenere les taches avec leurs dependances, priorites, difficultes et durees estimees.';\n"
                    "\n"
                    "const systemPrompt = " + json.dumps(CLAUDE_SYSTEM_PROMPT) + ";\n"
                    "\n"
                    "return [{json: {\n"
                    "  ...project,\n"
                    "  userPrompt,\n"
                    "  systemPrompt\n"
                    "}}];\n"
            },
            "id": "build-prompt",
            "name": "Build Claude Prompt",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [900, 200]
        },

        # ─────────────────────────────────────────────────────────────────
        # 6. Claude Decomposition — call Anthropic API
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.anthropic.com/v1/messages",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "anthropicApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "anthropic-version", "value": "2023-06-01"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '={"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "system": {{ JSON.stringify($json.systemPrompt) }}, "messages": [{"role": "user", "content": {{ JSON.stringify($json.userPrompt) }}}]}',
                "options": {}
            },
            "id": "claude-decompose",
            "name": "Claude Decomposition",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1120, 200],
            "credentials": {"anthropicApi": {"id": ANTHROPIC_CRED_ID, "name": "Anthropic account"}}
        },

        # ─────────────────────────────────────────────────────────────────
        # 7. Parse Claude Response — extract tasks JSON
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "jsCode": r"""// Parse Claude's decomposition response
const claudeResponse = $input.first().json;
const project = $('Build Claude Prompt').first().json;
const content = claudeResponse.content?.[0]?.text || '{}';

let decomposition;
try {
  // Try to extract JSON from response (handle potential markdown wrapping)
  const jsonMatch = content.match(/\{[\s\S]*\}/);
  decomposition = JSON.parse(jsonMatch ? jsonMatch[0] : content);
} catch (e) {
  return [{json: {
    error: true,
    errorMsg: `Erreur parsing Claude pour "${project.projectName}": ${e.message}`,
    raw: content.substring(0, 500),
    projectId: project.projectId,
    projectName: project.projectName,
    tasks: []
  }}];
}

const tasks = decomposition.tasks || [];
const summary = decomposition.summary || 'Decomposition terminee';

if (tasks.length === 0) {
  return [{json: {
    error: true,
    errorMsg: `Claude n'a genere aucune tache pour "${project.projectName}"`,
    projectId: project.projectId,
    projectName: project.projectName,
    tasks: []
  }}];
}

// Return individual items for each task, keeping project context
const items = tasks.map((task, i) => ({
  json: {
    // Project context
    projectId: project.projectId,
    projectName: project.projectName,
    projectStatus: project.projectStatus,
    projectCategory: project.projectCategory,
    projectGoalId: project.projectGoalId,
    // Task data
    taskName: task.name,
    taskDescription: task.description || '',
    taskPriority: task.priority || 'Medium',
    taskDifficulty: task.difficulty || '2 - Moderate',
    taskDuration: task.duration || '1h',
    taskOrder: task.order || (i + 1),
    taskBlockedBy: task.blocked_by || [],
    // Metadata
    taskIndex: i,
    totalTasks: tasks.length,
    decompositionSummary: summary
  }
}));

return items;
"""
            },
            "id": "parse-claude",
            "name": "Parse Tasks",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1340, 200]
        },

        # ─────────────────────────────────────────────────────────────────
        # 8. Check for errors
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict"
                    },
                    "conditions": [
                        {
                            "id": "error-check",
                            "leftValue": "={{ $json.error }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "equals"
                            }
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "if-error",
            "name": "Error?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [1560, 200]
        },

        # ─────────────────────────────────────────────────────────────────
        # 9. Create Task in Notion — POST /v1/pages for each task
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.notion.com/v1/pages",
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
                "jsonBody": """={
  "parent": {"database_id": \"""" + PROJECTS_DB_PAGE_ID + """"},
  "properties": {
    "Name": {"title": [{"text": {"content": "{{ $json.taskName }}"}}]},
    "Type": {"select": {"name": "Task"}},
    "Status": {"status": {"name": "Backlog"}},
    "Category": {"select": {"name": "{{ $json.projectCategory || 'Perso' }}"}},
    "Priority": {"select": {"name": "{{ $json.taskPriority }}"}},
    "Difficulty": {"select": {"name": "{{ $json.taskDifficulty }}"}},
    "Duration": {"select": {"name": "{{ $json.taskDuration }}"}},
    "Description": {"rich_text": [{"text": {"content": "{{ $json.taskDescription.substring(0, 2000) }}"}}]},
    "Upstream": {"relation": [{"id": "{{ $json.projectId }}"}]}
  }
}""",
                "options": {}
            },
            "id": "create-task",
            "name": "Create Task Notion",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1780, 100],
            "credentials": NOTION_CRED,
            "onError": "continueRegularOutput"
        },

        # ─────────────────────────────────────────────────────────────────
        # 10. Collect Created Tasks — aggregate results for recap
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "jsCode": r"""// Collect all created tasks and group by project
const allItems = $input.all();
const parseItems = $('Parse Tasks').all();

// Group tasks by project
const projectMap = {};

for (const item of parseItems) {
  const j = item.json;
  if (j.error) continue;

  const pid = j.projectId;
  if (!projectMap[pid]) {
    projectMap[pid] = {
      projectId: pid,
      projectName: j.projectName,
      projectStatus: j.projectStatus,
      projectCategory: j.projectCategory,
      summary: j.decompositionSummary,
      tasks: [],
      totalTasks: j.totalTasks
    };
  }
  projectMap[pid].tasks.push({
    name: j.taskName,
    priority: j.taskPriority,
    difficulty: j.taskDifficulty,
    duration: j.taskDuration,
    order: j.taskOrder
  });
}

const projects = Object.values(projectMap);

if (projects.length === 0) {
  return [{json: {skip: true, reason: 'Aucune tache creee'}}];
}

// Return one item per project for status update
return projects.map(p => ({json: p}));
"""
            },
            "id": "collect-tasks",
            "name": "Collect Results",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2000, 100]
        },

        # ─────────────────────────────────────────────────────────────────
        # 11. Update Project Status — if Backlog → Ready To Start
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "method": "PATCH",
                "url": "=https://api.notion.com/v1/pages/{{ $json.projectId }}",
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
                "jsonBody": '={\n  "properties": {\n    "Status": {"status": {"name": "{{ $json.projectStatus === \'Backlog\' ? \'Ready To Start\' : $json.projectStatus }}"}}\n  }\n}',
                "options": {}
            },
            "id": "update-project",
            "name": "Update Project Status",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2220, 100],
            "credentials": NOTION_CRED,
            "onError": "continueRegularOutput"
        },

        # ─────────────────────────────────────────────────────────────────
        # 12. Build Telegram Recap
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "jsCode": r"""// Build Telegram recap message
const allProjects = $input.all();
const errors = $('Parse Tasks').all().filter(i => i.json.error);

let msg = `*Auto-Decomposition Projets*\n\n`;

for (const item of allProjects) {
  const p = item.json;
  if (p.skip) continue;

  msg += `*${p.projectName}*`;
  if (p.projectCategory) msg += ` (${p.projectCategory})`;
  msg += `\n`;
  msg += `${p.summary}\n\n`;

  // Sort tasks by order
  const sortedTasks = (p.tasks || []).sort((a, b) => a.order - b.order);
  for (const t of sortedTasks) {
    const priorityIcon = {
      'Critical': '🔴',
      'High': '🟠',
      'Medium': '🟡',
      'Low': '🟢'
    }[t.priority] || '⚪';
    msg += `${priorityIcon} ${t.order}. ${t.name} (${t.difficulty}, ${t.duration})\n`;
  }

  const statusChange = p.projectStatus === 'Backlog' ? ' | Backlog → Ready To Start' : '';
  msg += `\n${p.totalTasks} taches creees${statusChange}\n`;
  msg += `---\n`;
}

if (errors.length > 0) {
  msg += `\n*Erreurs :*\n`;
  for (const e of errors) {
    msg += `- ${e.json.errorMsg}\n`;
  }
}

const totalTasks = allProjects.reduce((sum, i) => sum + (i.json.tasks?.length || 0), 0);
const totalProjects = allProjects.filter(i => !i.json.skip).length;
msg += `\n*Total : ${totalProjects} projet(s), ${totalTasks} tache(s) creee(s)*`;

return [{json: {recap: msg}}];
"""
            },
            "id": "build-recap",
            "name": "Build Recap",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2440, 100]
        },

        # ─────────────────────────────────────────────────────────────────
        # 13a. Split for Telegram (4096 char limit)
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "jsCode": """// Split long messages for Telegram (4096 char limit)
const fullMsg = $json.recap;
const MAX = 4000;

if (fullMsg.length <= MAX) {
    return [{json: {text: fullMsg}}];
}

const sections = fullMsg.split(/\\n\\n/);
const parts = [];
let current = '';

for (const section of sections) {
    if (current.length + section.length + 2 > MAX) {
        if (current) parts.push(current.trim());
        if (section.length > MAX) {
            const lines = section.split('\\n');
            let chunk = '';
            for (const line of lines) {
                if (chunk.length + line.length + 1 > MAX) {
                    if (chunk) parts.push(chunk.trim());
                    chunk = line;
                } else {
                    chunk += (chunk ? '\\n' : '') + line;
                }
            }
            current = chunk;
        } else {
            current = section;
        }
    } else {
        current += (current ? '\\n\\n' : '') + section;
    }
}
if (current) parts.push(current.trim());

// Merge small consecutive parts to avoid tiny messages
const merged = [];
for (const part of parts) {
    if (merged.length > 0 && merged[merged.length - 1].length + part.length + 2 <= MAX) {
        merged[merged.length - 1] += '\\n\\n' + part;
    } else {
        merged.push(part);
    }
}

// Ensure first part isn't tiny (merge into second if < 200 chars)
if (merged.length > 1 && merged[0].length < 200) {
    merged[1] = merged[0] + '\\n\\n' + merged[1];
    merged.shift();
}

if (merged.length === 1) return [{json: {text: merged[0]}}];
return merged.map((p, i) => ({json: {text: '[' + (i+1) + '/' + merged.length + ']\\n' + p}}));
"""
            },
            "id": "split-telegram",
            "name": "Split for Telegram",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2660, 100]
        },

        # ─────────────────────────────────────────────────────────────────
        # 13b. Send Telegram Notification
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "chatId": TELEGRAM_CHAT_ID,
                "text": "={{ $json.text }}",
                "additionalFields": {"parse_mode": "Markdown"}
            },
            "id": "telegram-notif",
            "name": "Telegram Notification",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [2880, 100],
            "credentials": TELEGRAM_CRED
        },

        # ─────────────────────────────────────────────────────────────────
        # 14. Error Telegram — notify on parse errors
        # ─────────────────────────────────────────────────────────────────
        {
            "parameters": {
                "chatId": TELEGRAM_CHAT_ID,
                "text": "=*Auto-Decomposition — Erreur*\n\n{{ $json.errorMsg }}\n\nRaw: {{ ($json.raw || '').substring(0, 200) }}",
                "additionalFields": {"parse_mode": "Markdown"}
            },
            "id": "telegram-error",
            "name": "Telegram Error",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [1780, 300],
            "credentials": TELEGRAM_CRED
        }
    ],
    "connections": {
        "Every 30min": {
            "main": [[{"node": "Query New Projects", "type": "main", "index": 0}]]
        },
        "Query New Projects": {
            "main": [[{"node": "Extract Projects", "type": "main", "index": 0}]]
        },
        "Extract Projects": {
            "main": [[{"node": "Has Projects?", "type": "main", "index": 0}]]
        },
        "Has Projects?": {
            "main": [
                # True = skip (no projects) → do nothing
                [],
                # False = has projects → build prompt
                [{"node": "Build Claude Prompt", "type": "main", "index": 0}]
            ]
        },
        "Build Claude Prompt": {
            "main": [[{"node": "Claude Decomposition", "type": "main", "index": 0}]]
        },
        "Claude Decomposition": {
            "main": [[{"node": "Parse Tasks", "type": "main", "index": 0}]]
        },
        "Parse Tasks": {
            "main": [[{"node": "Error?", "type": "main", "index": 0}]]
        },
        "Error?": {
            "main": [
                # True = error → Telegram error
                [{"node": "Telegram Error", "type": "main", "index": 0}],
                # False = no error → create task
                [{"node": "Create Task Notion", "type": "main", "index": 0}]
            ]
        },
        "Create Task Notion": {
            "main": [[{"node": "Collect Results", "type": "main", "index": 0}]]
        },
        "Collect Results": {
            "main": [[{"node": "Update Project Status", "type": "main", "index": 0}]]
        },
        "Update Project Status": {
            "main": [[{"node": "Build Recap", "type": "main", "index": 0}]]
        },
        "Build Recap": {
            "main": [[{"node": "Split for Telegram", "type": "main", "index": 0}]]
        },
        "Split for Telegram": {
            "main": [[{"node": "Telegram Notification", "type": "main", "index": 0}]]
        }
    },
    "settings": {
        "executionOrder": "v1"
    }
}


def main():
    """Deploy the Auto-Decomposition workflow to n8n."""

    # ── Check existing credentials ────────────────────────────────────
    print("Checking existing credentials in n8n...")
    r = requests.get(f"{N8N_URL}/api/v1/credentials", headers=HEADERS)
    creds = r.json().get("data", [])

    notion_cred_id = None
    telegram_cred_id = None
    anthropic_cred_id = None

    for c in creds:
        ctype = c.get("type", "")
        cname = c.get("name", "").lower()
        if ctype == "notionApi" or "notion" in cname:
            notion_cred_id = c["id"]
            print(f"  Notion: {c['name']} (id={c['id']})")
        if ctype == "telegramApi" or "telegram" in cname:
            telegram_cred_id = c["id"]
            print(f"  Telegram: {c['name']} (id={c['id']})")
        if ctype == "anthropicApi" or "anthropic" in cname:
            anthropic_cred_id = c["id"]
            print(f"  Anthropic: {c['name']} (id={c['id']})")

    if not notion_cred_id:
        print("  WARNING: Notion credential not found!")
    if not telegram_cred_id:
        print("  WARNING: Telegram credential not found!")
    if not anthropic_cred_id:
        print("  WARNING: Anthropic credential not found!")

    # ── Patch credential IDs in workflow nodes ────────────────────────
    for node in workflow["nodes"]:
        node_creds = node.get("credentials", {})
        if "notionApi" in node_creds and notion_cred_id:
            node_creds["notionApi"]["id"] = str(notion_cred_id)
        if "telegramApi" in node_creds and telegram_cred_id:
            node_creds["telegramApi"]["id"] = str(telegram_cred_id)
        if "anthropicApi" in node_creds and anthropic_cred_id:
            node_creds["anthropicApi"]["id"] = str(anthropic_cred_id)

    # ── Check for existing workflow with same name ────────────────────
    print("\nChecking for existing 'Auto-Decomposition Projets' workflow...")
    r = requests.get(f"{N8N_URL}/api/v1/workflows", headers=HEADERS)
    existing_workflows = r.json().get("data", [])

    existing_id = None
    for wf in existing_workflows:
        if wf["name"] == "Auto-Decomposition Projets":
            existing_id = wf["id"]
            print(f"  Found existing: {existing_id} (active={wf.get('active', False)})")
            break

    # ── Create or update workflow ─────────────────────────────────────
    if existing_id:
        print(f"\nUpdating existing workflow {existing_id}...")
        r = requests.put(
            f"{N8N_URL}/api/v1/workflows/{existing_id}",
            headers=HEADERS,
            json=workflow
        )
    else:
        print("\nCreating new Auto-Decomposition Projets workflow...")
        r = requests.post(
            f"{N8N_URL}/api/v1/workflows",
            headers=HEADERS,
            json=workflow
        )

    if r.status_code in (200, 201):
        wf = r.json()
        wf_id = wf["id"]
        action = "Updated" if existing_id else "Created"
        print(f"  {action}: {wf_id}")

        # ── Activate ──────────────────────────────────────────────────
        print("Activating workflow...")
        r2 = requests.post(
            f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
            headers=HEADERS
        )
        if r2.status_code == 200:
            print("  Activated!")
        else:
            print(f"  Activation: {r2.status_code} — {r2.text[:200]}")

        # ── Verify ────────────────────────────────────────────────────
        print("\nVerifying workflow...")
        r3 = requests.get(f"{N8N_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
        wf_data = r3.json()
        print(f"  Name: {wf_data['name']}")
        print(f"  Active: {wf_data['active']}")
        print(f"  Nodes ({len(wf_data['nodes'])}):")
        for n in wf_data["nodes"]:
            c = n.get("credentials", {})
            c_info = ""
            if c:
                c_info = " — " + ", ".join(f"{k}={v.get('id', '?')}" for k, v in c.items())
            print(f"    - {n['name']} ({n['type']}){c_info}")

        print(f"\n{'='*60}")
        print(f"Workflow ID: {wf_id}")
        print(f"Schedule: Every 30 minutes")
        print(f"{'='*60}")
        print(f"\nLogic:")
        print(f"  1. Query Notion for Projects with no child tasks")
        print(f"  2. Send each to Claude for decomposition (3-8 tasks)")
        print(f"  3. Create tasks in Notion with Upstream link")
        print(f"  4. Update project status (Backlog -> Ready To Start)")
        print(f"  5. Send Telegram recap")
        return wf_id
    else:
        print(f"  Error: {r.status_code}")
        print(f"  {r.text[:500]}")
        return None


if __name__ == "__main__":
    main()
