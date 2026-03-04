#!/usr/bin/env python3
"""Create n8n workflow: Persistent Nudge System.

Sends escalating Telegram reminders for overdue/stalled tasks and goals.
Schedule: 4x/day during work hours (8h, 12h, 16h, 20h CET).

- 8h:  Morning scan — list all overdue + due today (informational)
- 12h: Midday check — remind about tasks due today not yet started
- 16h: Afternoon push — warn about overdue, suggest actions
- 20h: Evening recap — summary of what's still pending, set expectations

Nodes 3-6 (queries) run in parallel from node 2, then merge in node 7.
Uses $('NodeName') syntax to reference parallel branches in the merge node.
"""

import json
import requests

# --- Configuration ---
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9."
    "sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
)
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Notion IDs
TASKS_DB_PAGE_ID = "305da200-b2d6-8145-bc16-eaee02925a14"
GOALS_DB_PAGE_ID = "bc88ee5f-f09b-4f45-adb9-faae179aa276"

# Telegram
TELEGRAM_CHAT_ID = "7342622615"

# Credential references
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}

# =====================================================================
# Notion API filter bodies (pre-serialized for n8n HTTP Request nodes)
# =====================================================================

# Overdue tasks: Due Date < today AND Status NOT in (Complete, Archive)
OVERDUE_TASKS_FILTER = json.dumps({
    "filter": {
        "and": [
            {
                "property": "Due Date",
                "date": {"before": "{{$json.today}}"}
            },
            {
                "property": "Due Date",
                "date": {"is_not_empty": True}
            },
            {
                "property": "Status",
                "status": {"does_not_equal": "Complete"}
            },
            {
                "property": "Status",
                "status": {"does_not_equal": "Archive"}
            },
            {
                "or": [
                    {"property": "Type", "select": {"equals": "Task"}},
                    {"property": "Type", "select": {"equals": "Sub-task"}},
                    {"property": "Type", "select": {"equals": "Project"}}
                ]
            }
        ]
    },
    "sorts": [
        {"property": "Due Date", "direction": "ascending"}
    ],
    "page_size": 20
})

# Stalled tasks: Status = "In Progress" AND last edited > 3 days ago
STALLED_TASKS_FILTER = json.dumps({
    "filter": {
        "and": [
            {
                "property": "Status",
                "status": {"equals": "In Progress"}
            },
            {
                "timestamp": "last_edited_time",
                "last_edited_time": {"before": "{{$json.threeDaysAgo}}"}
            },
            {
                "or": [
                    {"property": "Type", "select": {"equals": "Task"}},
                    {"property": "Type", "select": {"equals": "Sub-task"}},
                    {"property": "Type", "select": {"equals": "Project"}}
                ]
            }
        ]
    },
    "sorts": [
        {"timestamp": "last_edited_time", "direction": "ascending"}
    ],
    "page_size": 20
})

# Due today: Due Date = today AND Status NOT Complete/Archive
DUE_TODAY_FILTER = json.dumps({
    "filter": {
        "and": [
            {
                "property": "Due Date",
                "date": {"equals": "{{$json.today}}"}
            },
            {
                "property": "Status",
                "status": {"does_not_equal": "Complete"}
            },
            {
                "property": "Status",
                "status": {"does_not_equal": "Archive"}
            },
            {
                "or": [
                    {"property": "Type", "select": {"equals": "Task"}},
                    {"property": "Type", "select": {"equals": "Sub-task"}},
                    {"property": "Type", "select": {"equals": "Project"}}
                ]
            }
        ]
    },
    "page_size": 20
})

# Goals at risk: In Progress with deadline approaching
GOALS_AT_RISK_FILTER = json.dumps({
    "filter": {
        "and": [
            {
                "property": "Status",
                "select": {"equals": "In Progress"}
            },
            {
                "property": "Deadline",
                "date": {"is_not_empty": True}
            }
        ]
    },
    "page_size": 20
})

# =====================================================================
# Workflow definition
# =====================================================================

workflow = {
    "name": "Persistent Nudge",
    "nodes": [
        # ==============================================================
        # 1. Schedule Trigger — 4x/day at 8h, 12h, 16h, 20h CET
        # ==============================================================
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {
                            "field": "cronExpression",
                            "expression": "0 8,12,16,20 * * *"
                        }
                    ]
                }
            },
            "id": "schedule-nudge",
            "name": "Schedule Trigger",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 300],
        },

        # ==============================================================
        # 2. Time Context — compute today, urgency level, time slot
        # ==============================================================
        {
            "parameters": {
                "jsCode": """// Compute time context for nudge system
const now = new Date();

// CET/CEST offset: UTC+1 in winter, UTC+2 in summer
// Use Intl to get the actual CET hour
const cetFormatter = new Intl.DateTimeFormat('fr-FR', {
  timeZone: 'Europe/Paris',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  hour12: false
});

const parts = cetFormatter.formatToParts(now);
const year = parts.find(p => p.type === 'year').value;
const month = parts.find(p => p.type === 'month').value;
const day = parts.find(p => p.type === 'day').value;
const hour = parseInt(parts.find(p => p.type === 'hour').value);

const today = `${year}-${month}-${day}`;

// 3 days ago for stalled detection
const threeDaysAgoDate = new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000);
const threeDaysAgo = threeDaysAgoDate.toISOString().split('T')[0];

// 14 days from now for goal deadline warning
const twoWeeksFromNow = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000);
const deadlineWarning = twoWeeksFromNow.toISOString().split('T')[0];

// Determine time slot and urgency
let timeSlot, urgencyLevel, greeting;

if (hour <= 9) {
  timeSlot = 'morning';
  urgencyLevel = 1;
  greeting = 'Bonjour ! Voici ton scan du matin.';
} else if (hour <= 13) {
  timeSlot = 'midday';
  urgencyLevel = 2;
  greeting = 'Check de mi-journee.';
} else if (hour <= 17) {
  timeSlot = 'afternoon';
  urgencyLevel = 3;
  greeting = 'Push de l\\'apres-midi.';
} else {
  timeSlot = 'evening';
  urgencyLevel = 4;
  greeting = 'Recap du soir.';
}

return [{
  json: {
    today,
    threeDaysAgo,
    deadlineWarning,
    currentHour: hour,
    timeSlot,
    urgencyLevel,
    greeting,
    timestamp: now.toISOString()
  }
}];
"""
            },
            "id": "time-context",
            "name": "Time Context",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [240, 300],
        },

        # ==============================================================
        # 3. Query Overdue Tasks — HTTP Request to Notion API
        # ==============================================================
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{TASKS_DB_PAGE_ID}/query",
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
                "jsonBody": f"={OVERDUE_TASKS_FILTER}",
                "options": {}
            },
            "id": "query-overdue",
            "name": "Query Overdue Tasks",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [520, 60],
            "credentials": {**NOTION_CRED},
            "onError": "continueRegularOutput",
        },

        # ==============================================================
        # 4. Query Stalled Tasks — In Progress, last edited > 3 days ago
        # ==============================================================
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{TASKS_DB_PAGE_ID}/query",
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
                "jsonBody": f"={STALLED_TASKS_FILTER}",
                "options": {}
            },
            "id": "query-stalled",
            "name": "Query Stalled Tasks",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [520, 240],
            "credentials": {**NOTION_CRED},
            "onError": "continueRegularOutput",
        },

        # ==============================================================
        # 5. Query Due Today — tasks due today, not complete
        # ==============================================================
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{TASKS_DB_PAGE_ID}/query",
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
                "jsonBody": f"={DUE_TODAY_FILTER}",
                "options": {}
            },
            "id": "query-due-today",
            "name": "Query Due Today",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [520, 420],
            "credentials": {**NOTION_CRED},
            "onError": "continueRegularOutput",
        },

        # ==============================================================
        # 6. Query Goals At Risk — In Progress with approaching deadline
        # ==============================================================
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{GOALS_DB_PAGE_ID}/query",
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
                "jsonBody": f"={GOALS_AT_RISK_FILTER}",
                "options": {}
            },
            "id": "query-goals-risk",
            "name": "Query Goals At Risk",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [520, 600],
            "credentials": {**NOTION_CRED},
            "onError": "continueRegularOutput",
        },

        # ==============================================================
        # 7. Build Nudge Message — merge all queries, format by time slot
        # ==============================================================
        {
            "parameters": {
                "jsCode": r"""// Build Nudge Message — merge all parallel query results
// Access parallel branches using $('NodeName') syntax

const ctx = $('Time Context').first().json;
const timeSlot = ctx.timeSlot;
const urgencyLevel = ctx.urgencyLevel;
const today = ctx.today;
const greeting = ctx.greeting;

// ---- Helper: extract task info from Notion page ----
function extractTask(page) {
  const props = page.properties || {};

  // Name/title
  const titleProp = props['Name'] || props['name'] || {};
  const titleArr = titleProp.title || [];
  const name = titleArr.map(t => t.plain_text || '').join('') || 'Sans nom';

  // Status
  const statusProp = props['Status'] || {};
  const statusObj = statusProp.status || statusProp.select || {};
  const status = statusObj.name || 'Unknown';

  // Due Date
  const dueProp = props['Due Date'] || {};
  const dueDate = (dueProp.date || {}).start || null;

  // Priority
  const prioProp = props['Priority'] || {};
  const priority = (prioProp.select || {}).name || null;

  // Type
  const typeProp = props['Type'] || {};
  const type = (typeProp.select || {}).name || 'Task';

  // Days overdue
  let daysOverdue = 0;
  if (dueDate) {
    const due = new Date(dueDate + 'T00:00:00Z');
    const tod = new Date(today + 'T00:00:00Z');
    daysOverdue = Math.floor((tod - due) / (1000 * 60 * 60 * 24));
  }

  // Last edited
  const lastEdited = page.last_edited_time || null;
  let daysSinceEdit = 0;
  if (lastEdited) {
    const edited = new Date(lastEdited);
    daysSinceEdit = Math.floor((new Date() - edited) / (1000 * 60 * 60 * 24));
  }

  return { name, status, dueDate, priority, type, daysOverdue, daysSinceEdit };
}

// ---- Helper: extract goal info ----
function extractGoal(page) {
  const props = page.properties || {};

  const titleProp = props['Name'] || props['name'] || {};
  const titleArr = titleProp.title || [];
  const name = titleArr.map(t => t.plain_text || '').join('') || 'Sans nom';

  const progressProp = props['Progress %'] || props['Progress'] || {};
  const progress = progressProp.number != null ? Math.round(progressProp.number) : null;

  const deadlineProp = props['Deadline'] || {};
  const deadline = (deadlineProp.date || {}).start || null;

  let daysUntilDeadline = null;
  if (deadline) {
    const dl = new Date(deadline + 'T00:00:00Z');
    const tod = new Date(today + 'T00:00:00Z');
    daysUntilDeadline = Math.floor((dl - tod) / (1000 * 60 * 60 * 24));
  }

  // Goal is "at risk" if deadline <= 14 days AND progress < 70%
  const atRisk = daysUntilDeadline !== null
    && daysUntilDeadline <= 14
    && (progress === null || progress < 70);

  return { name, progress, deadline, daysUntilDeadline, atRisk };
}

// ---- Parse all query results ----
let overdueRaw, stalledRaw, dueTodayRaw, goalsRaw;

try { overdueRaw = $('Query Overdue Tasks').first().json.results || []; }
catch(e) { overdueRaw = []; }

try { stalledRaw = $('Query Stalled Tasks').first().json.results || []; }
catch(e) { stalledRaw = []; }

try { dueTodayRaw = $('Query Due Today').first().json.results || []; }
catch(e) { dueTodayRaw = []; }

try { goalsRaw = $('Query Goals At Risk').first().json.results || []; }
catch(e) { goalsRaw = []; }

const overdue = overdueRaw.map(extractTask);
const stalled = stalledRaw.map(extractTask);
const dueToday = dueTodayRaw.map(extractTask);
const goalsAtRisk = goalsRaw.map(extractGoal).filter(g => g.atRisk);

// ---- Check if there's anything to nudge ----
const totalItems = overdue.length + stalled.length + dueToday.length + goalsAtRisk.length;

if (totalItems === 0) {
  return [{ json: { hasNudge: false, message: '' } }];
}

// ---- Priority emoji ----
function prioIcon(p) {
  if (p === 'Critical') return '🔴';
  if (p === 'High') return '🟠';
  if (p === 'Medium') return '🟡';
  return '⚪';
}

// ---- Build message per time slot ----
let msg = '';
const MAX_ITEMS = 10;

// =============================================
// MORNING (8h) — Informational scan
// =============================================
if (timeSlot === 'morning') {
  msg += `<b>☀️ Scan du matin</b>\n`;
  msg += `${greeting}\n\n`;

  if (dueToday.length > 0) {
    msg += `<b>📅 A faire aujourd'hui (${dueToday.length})</b>\n`;
    for (const t of dueToday.slice(0, MAX_ITEMS)) {
      msg += `  ${prioIcon(t.priority)} ${t.name}`;
      if (t.status) msg += ` <i>[${t.status}]</i>`;
      msg += `\n`;
    }
    msg += `\n`;
  }

  if (overdue.length > 0) {
    msg += `<b>⚠️ En retard (${overdue.length})</b>\n`;
    for (const t of overdue.slice(0, MAX_ITEMS)) {
      msg += `  ${prioIcon(t.priority)} ${t.name} — <b>${t.daysOverdue}j</b> de retard\n`;
    }
    msg += `\n`;
  }

  if (stalled.length > 0) {
    msg += `<b>🧊 En stagnation (${stalled.length})</b>\n`;
    for (const t of stalled.slice(0, 5)) {
      msg += `  ${t.name} — pas touche depuis ${t.daysSinceEdit}j\n`;
    }
    msg += `\n`;
  }

  if (goalsAtRisk.length > 0) {
    msg += `<b>🎯 Objectifs a risque</b>\n`;
    for (const g of goalsAtRisk) {
      msg += `  ${g.name}: ${g.progress ?? '?'}%`;
      if (g.daysUntilDeadline !== null) msg += ` — deadline dans ${g.daysUntilDeadline}j`;
      msg += `\n`;
    }
  }
}

// =============================================
// MIDDAY (12h) — Focus on today's tasks
// =============================================
else if (timeSlot === 'midday') {
  msg += `<b>🕛 Check de mi-journee</b>\n\n`;

  const notStarted = dueToday.filter(t =>
    t.status !== 'In Progress' && t.status !== 'Complete' && t.status !== 'Done'
  );

  if (notStarted.length > 0) {
    msg += `<b>⏳ Pas encore demarrees aujourd'hui (${notStarted.length})</b>\n`;
    for (const t of notStarted.slice(0, MAX_ITEMS)) {
      msg += `  ${prioIcon(t.priority)} ${t.name} <i>[${t.status}]</i>\n`;
    }
    msg += `\nIl est midi — c'est le moment de s'y mettre !\n`;
  } else if (dueToday.length > 0) {
    msg += `Toutes les taches du jour sont en cours. Continue comme ca !\n`;
  }

  if (overdue.length > 0) {
    msg += `\n<b>⚠️ Rappel: ${overdue.length} tache(s) en retard</b>\n`;
    const worst = overdue.slice(0, 3);
    for (const t of worst) {
      msg += `  ${prioIcon(t.priority)} ${t.name} — <b>${t.daysOverdue}j</b> de retard\n`;
    }
  }
}

// =============================================
// AFTERNOON (16h) — Urgent push
// =============================================
else if (timeSlot === 'afternoon') {
  msg += `<b>⚡ Push de l'apres-midi</b>\n\n`;

  if (overdue.length > 0) {
    msg += `<b>🚨 ATTENTION: ${overdue.length} tache(s) en retard</b>\n`;
    for (const t of overdue.slice(0, MAX_ITEMS)) {
      msg += `  ${prioIcon(t.priority)} <b>${t.name}</b> — ${t.daysOverdue}j de retard`;
      if (t.priority === 'Critical' || t.priority === 'High') {
        msg += ` ← ACTION REQUISE`;
      }
      msg += `\n`;
    }
    msg += `\n`;
  }

  if (stalled.length > 0) {
    msg += `<b>🧊 Bloquees depuis trop longtemps (${stalled.length})</b>\n`;
    for (const t of stalled.slice(0, 5)) {
      msg += `  ${t.name} — ${t.daysSinceEdit}j sans activite\n`;
    }
    msg += `Suggestion: abandonne ou replanifie ces taches.\n\n`;
  }

  const stillDueToday = dueToday.filter(t =>
    t.status !== 'Complete' && t.status !== 'Done'
  );
  if (stillDueToday.length > 0) {
    msg += `<b>⏰ Encore a finir aujourd'hui (${stillDueToday.length})</b>\n`;
    for (const t of stillDueToday.slice(0, 5)) {
      msg += `  ${prioIcon(t.priority)} ${t.name}\n`;
    }
  }

  if (goalsAtRisk.length > 0) {
    msg += `\n<b>🎯 Objectifs en danger</b>\n`;
    for (const g of goalsAtRisk) {
      msg += `  ${g.name}: ${g.progress ?? '?'}%`;
      if (g.daysUntilDeadline !== null && g.daysUntilDeadline <= 7) {
        msg += ` — <b>DEADLINE DANS ${g.daysUntilDeadline}j</b>`;
      } else if (g.daysUntilDeadline !== null) {
        msg += ` — deadline dans ${g.daysUntilDeadline}j`;
      }
      msg += `\n`;
    }
  }
}

// =============================================
// EVENING (20h) — Recap + tomorrow expectations
// =============================================
else if (timeSlot === 'evening') {
  msg += `<b>🌙 Recap du soir</b>\n\n`;

  // Summary stats
  msg += `<b>Bilan de la journee :</b>\n`;
  msg += `  📅 Taches du jour restantes: ${dueToday.filter(t => t.status !== 'Complete' && t.status !== 'Done').length}/${dueToday.length}\n`;
  msg += `  ⚠️ Taches en retard: ${overdue.length}\n`;
  msg += `  🧊 Taches en stagnation: ${stalled.length}\n`;

  if (goalsAtRisk.length > 0) {
    msg += `  🎯 Objectifs a risque: ${goalsAtRisk.length}\n`;
  }
  msg += `\n`;

  // What's still overdue
  if (overdue.length > 0) {
    msg += `<b>A traiter demain en priorite :</b>\n`;
    // Sort by priority: Critical > High > Medium > Low
    const prioOrder = { 'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3 };
    const sorted = [...overdue].sort((a, b) =>
      (prioOrder[a.priority] ?? 4) - (prioOrder[b.priority] ?? 4)
    );
    for (const t of sorted.slice(0, 5)) {
      msg += `  ${prioIcon(t.priority)} ${t.name} (${t.daysOverdue}j retard)\n`;
    }
    if (sorted.length > 5) {
      msg += `  ... et ${sorted.length - 5} autres\n`;
    }
    msg += `\n`;
  }

  if (goalsAtRisk.length > 0) {
    msg += `<b>Objectifs a surveiller :</b>\n`;
    for (const g of goalsAtRisk) {
      msg += `  ${g.name}: ${g.progress ?? '?'}%`;
      if (g.daysUntilDeadline !== null) msg += ` (J-${g.daysUntilDeadline})`;
      msg += `\n`;
    }
    msg += `\n`;
  }

  msg += `Bonne nuit. Demain on avance. 💪`;
}

return [{ json: { hasNudge: true, message: msg, totalItems, timeSlot, urgencyLevel } }];
"""
            },
            "id": "build-nudge",
            "name": "Build Nudge Message",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [840, 300],
        },

        # ==============================================================
        # 8. Should Nudge? — IF hasNudge is true and message is non-empty
        # ==============================================================
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
                            "id": "has-nudge",
                            "leftValue": "={{ $json.hasNudge }}",
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
            "id": "if-should-nudge",
            "name": "Should Nudge?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [1080, 300],
        },

        # ==============================================================
        # 9a. Split for Telegram (4096 char limit)
        # ==============================================================
        {
            "parameters": {
                "jsCode": """// Split long messages for Telegram (4096 char limit)
const fullMsg = $json.message;
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
            "position": [1320, 200],
        },

        # ==============================================================
        # 9b. Send Nudge — Telegram message
        # ==============================================================
        {
            "parameters": {
                "chatId": TELEGRAM_CHAT_ID,
                "text": "={{ $json.text }}",
                "additionalFields": {
                    "parse_mode": "HTML"
                },
            },
            "id": "send-nudge",
            "name": "Send Nudge",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [1560, 200],
            "credentials": {**TELEGRAM_CRED},
        },
    ],
    "connections": {
        # Schedule -> Time Context
        "Schedule Trigger": {
            "main": [[{"node": "Time Context", "type": "main", "index": 0}]]
        },
        # Time Context -> 4 parallel queries
        "Time Context": {
            "main": [
                [
                    {"node": "Query Overdue Tasks", "type": "main", "index": 0},
                    {"node": "Query Stalled Tasks", "type": "main", "index": 0},
                    {"node": "Query Due Today", "type": "main", "index": 0},
                    {"node": "Query Goals At Risk", "type": "main", "index": 0},
                ]
            ]
        },
        # All 4 queries -> Build Nudge Message
        "Query Overdue Tasks": {
            "main": [[{"node": "Build Nudge Message", "type": "main", "index": 0}]]
        },
        "Query Stalled Tasks": {
            "main": [[{"node": "Build Nudge Message", "type": "main", "index": 0}]]
        },
        "Query Due Today": {
            "main": [[{"node": "Build Nudge Message", "type": "main", "index": 0}]]
        },
        "Query Goals At Risk": {
            "main": [[{"node": "Build Nudge Message", "type": "main", "index": 0}]]
        },
        # Build -> Should Nudge?
        "Build Nudge Message": {
            "main": [[{"node": "Should Nudge?", "type": "main", "index": 0}]]
        },
        # Should Nudge? true -> Split -> Send, false -> nothing
        "Should Nudge?": {
            "main": [
                [{"node": "Split for Telegram", "type": "main", "index": 0}],
                [],
            ]
        },
        "Split for Telegram": {
            "main": [
                [{"node": "Send Nudge", "type": "main", "index": 0}]
            ]
        },
    },
    "settings": {
        "executionOrder": "v1",
    },
}


def main():
    """Create and activate the Persistent Nudge workflow."""

    # ------------------------------------------------------------------
    # 1. Fetch existing credentials to get correct IDs
    # ------------------------------------------------------------------
    print("Fetching existing credentials...")
    resp = requests.get(f"{N8N_URL}/api/v1/credentials", headers=HEADERS)
    notion_cred_id = None
    notion_cred_name = None
    telegram_cred_id = None
    telegram_cred_name = None

    if resp.ok:
        creds = resp.json().get("data", [])
        for c in creds:
            ctype = c.get("type", "")
            cname = c.get("name", "")
            if ctype == "notionApi" or "notion" in cname.lower():
                notion_cred_id = c["id"]
                notion_cred_name = cname
                print(f"  Notion cred: {c['id']} -- {cname}")
            if ctype == "telegramApi" or "telegram" in cname.lower():
                telegram_cred_id = c["id"]
                telegram_cred_name = cname
                print(f"  Telegram cred: {c['id']} -- {cname}")
    else:
        print(f"  WARNING: Could not fetch credentials: {resp.status_code}")
        print("  Using default credential IDs from spec")

    # Use found creds or fall back to known IDs
    if not notion_cred_id:
        notion_cred_id = "FPqqVYnRbUnwRzrY"
        notion_cred_name = "Notion account"
    if not telegram_cred_id:
        telegram_cred_id = "37SeOsuQW7RBmQTl"
        telegram_cred_name = "Orun Telegram Bot"

    # ------------------------------------------------------------------
    # 2. Update credential references in all nodes
    # ------------------------------------------------------------------
    print("\nUpdating credential references...")
    for node in workflow["nodes"]:
        if "credentials" in node:
            if "notionApi" in node["credentials"]:
                node["credentials"]["notionApi"] = {
                    "id": str(notion_cred_id),
                    "name": notion_cred_name,
                }
                print(f"  {node['name']}: notionApi -> {notion_cred_id}")
            if "telegramApi" in node["credentials"]:
                node["credentials"]["telegramApi"] = {
                    "id": str(telegram_cred_id),
                    "name": telegram_cred_name,
                }
                print(f"  {node['name']}: telegramApi -> {telegram_cred_id}")

    # ------------------------------------------------------------------
    # 3. Check for existing workflow with same name and remove it
    # ------------------------------------------------------------------
    print("\nChecking for existing workflow...")
    resp = requests.get(f"{N8N_URL}/api/v1/workflows", headers=HEADERS)
    if resp.ok:
        existing = resp.json().get("data", [])
        for wf in existing:
            if wf.get("name") == workflow["name"]:
                wf_id = wf["id"]
                print(f"  Found existing workflow: {wf_id} -- deleting...")
                del_resp = requests.delete(
                    f"{N8N_URL}/api/v1/workflows/{wf_id}",
                    headers=HEADERS,
                )
                if del_resp.ok:
                    print(f"  Deleted old workflow {wf_id}")
                else:
                    print(f"  WARNING: Could not delete: {del_resp.status_code}")

    # ------------------------------------------------------------------
    # 4. Create the workflow
    # ------------------------------------------------------------------
    print("\nCreating Persistent Nudge workflow...")
    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow,
    )

    if not resp.ok:
        print(f"  ERROR: Creation failed: {resp.status_code}")
        print(f"  Response: {resp.text[:500]}")
        return None

    data = resp.json()
    wf_id = data.get("id")
    print(f"  Created: {data.get('name')} (ID: {wf_id})")

    # ------------------------------------------------------------------
    # 5. Activate the workflow (POST /activate, NOT PATCH)
    # ------------------------------------------------------------------
    print("\nActivating workflow...")
    resp2 = requests.post(
        f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS,
    )

    if resp2.ok:
        print("  ACTIVE -- runs at 8h, 12h, 16h, 20h CET")
    else:
        print(f"  Activation failed: {resp2.status_code}")
        print(f"  Response: {resp2.text[:200]}")

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PERSISTENT NUDGE SYSTEM")
    print("=" * 60)
    print(f"Workflow ID:     {wf_id}")
    print(f"Schedule:        0 8,12,16,20 * * * (CET)")
    print(f"Tasks DB:        {TASKS_DB_PAGE_ID}")
    print(f"Goals DB:        {GOALS_DB_PAGE_ID}")
    print(f"Telegram chat:   {TELEGRAM_CHAT_ID}")
    print()
    print("Flow:")
    print("  1. Schedule Trigger (4x/day: 8h, 12h, 16h, 20h)")
    print("  2. Time Context (compute today, urgency level)")
    print("  3-6. Parallel queries:")
    print("     - Overdue tasks (Due Date < today, not Complete/Archive)")
    print("     - Stalled tasks (In Progress, no edit 3+ days)")
    print("     - Due today (Due Date = today, not Complete)")
    print("     - Goals at risk (deadline <= 14 days, progress < 70%)")
    print("  7. Build Nudge Message (format by time slot)")
    print("     - 8h:  Morning scan (informational)")
    print("     - 12h: Midday check (tasks not started)")
    print("     - 16h: Afternoon push (urgent warnings)")
    print("     - 20h: Evening recap (summary + tomorrow)")
    print("  8. Should Nudge? (skip if nothing to report)")
    print("  9. Send Nudge (Telegram, HTML parse mode)")
    print("=" * 60)

    return wf_id


if __name__ == "__main__":
    wf_id = main()
    if wf_id:
        print(f"\nDone! Workflow ID: {wf_id}")
    else:
        print("\nFailed to create workflow.")
