#!/usr/bin/env python3
"""Create n8n workflow: Daily Quest Generator.

Every morning at 7h00 CET, generates a personalized daily quest list combining
habits due today + priority tasks, sends it via Telegram, and updates the
Command Center TODAY'S FOCUS callout.

Flow:
  1. Schedule Trigger (7h00 CET)
  2. Date Context (Code) — today, dayOfWeek, dayName in French
  3. Query Habits Due Today (HTTP Request → Notion API)
  4. Query Priority Tasks (HTTP Request → Notion API)
  5. Query Player Stats (HTTP Request → Notion API)
  6. Build Quest List (Code) — combine, score, format
  7. Update Command Center (HTTP Request → Notion API v3)
  8. Send Quests (Telegram)
"""

import json
import requests
from pathlib import Path

# --- Configuration ---
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9."
    "sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
)
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Notion DB page IDs (for official API: POST /v1/databases/{id}/query)
HABITS_DB_PAGE_ID = "305da200-b2d6-8139-b19f-d2a0d46cf7e6"
PROJECTS_TASKS_DB_PAGE_ID = "305da200-b2d6-8145-bc16-eaee02925a14"
PLAYER_STATS_PAGE_ID = "310da200-b2d6-8005-aeb9-e410436b48cf"

# Command Center block IDs (for API v3 saveTransactions)
COMMAND_CENTER_PAGE_ID = "306da200-b2d6-819c-8863-cf78f61ae670"
TODAYS_FOCUS_TITLE_BLOCK = "221933b9-7445-4e16-8110-e5da2936e8d0"
TODAYS_FOCUS_CONTENT_BLOCK = "8527fdd4-c139-4348-9436-bb8e63016b65"
SPACE_ID = "eba9b7f4-a4f9-4b63-a58c-b40e79eb44c7"

# Notion token for API v3
NOTION_TOKEN = (Path.home() / ".notion-token").read_text().strip()

# Telegram
TELEGRAM_CHAT_ID = "7342622615"

# Credential references
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}

# =====================================================================
# Workflow definition
# =====================================================================

workflow = {
    "name": "Daily Quest Generator",
    "nodes": [
        # ==============================================================
        # 1. Schedule Trigger — 7h00 CET every day
        # ==============================================================
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {
                            "field": "cronExpression",
                            "expression": "0 7 * * *"
                        }
                    ]
                }
            },
            "id": "schedule-quest",
            "name": "Every Morning 7AM",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 300],
        },

        # ==============================================================
        # 2. Date Context — compute today, dayOfWeek, dayName (French)
        # ==============================================================
        {
            "parameters": {
                "jsCode": """// Compute date context for quest generation
const now = new Date();

// Get CET date parts
const cetFormatter = new Intl.DateTimeFormat('fr-FR', {
  timeZone: 'Europe/Paris',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  weekday: 'long',
  hour12: false
});

const parts = cetFormatter.formatToParts(now);
const year = parts.find(p => p.type === 'year').value;
const month = parts.find(p => p.type === 'month').value;
const day = parts.find(p => p.type === 'day').value;
const dayName = parts.find(p => p.type === 'weekday').value;

const today = `${year}-${month}-${day}`;

// Day of week: 0=Sunday, 1=Monday, ..., 6=Saturday
// Use Paris timezone to get correct day
const cetDate = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Paris' }));
const dayOfWeek = cetDate.getDay();

// Capitalize first letter of dayName
const dayNameCapitalized = dayName.charAt(0).toUpperCase() + dayName.slice(1);

// Compute today+2 for task urgency filter
const twoDaysLater = new Date(cetDate.getTime() + 2 * 24 * 60 * 60 * 1000);
const todayPlus2 = twoDaysLater.toISOString().split('T')[0];

return [{json: {
  today,
  todayPlus2,
  dayOfWeek,
  dayName: dayNameCapitalized,
  month: parseInt(month),
  year: parseInt(year)
}}];
"""
            },
            "id": "date-context",
            "name": "Date Context",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [240, 300],
        },

        # ==============================================================
        # 3. Query Habits (HTTP Request → Notion API)
        #    Get ALL habits, filter due-today in the Code node later
        # ==============================================================
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{HABITS_DB_PAGE_ID}/query",
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
                "jsonBody": json.dumps({
                    "filter": {
                        "property": "Active",
                        "checkbox": {"equals": True}
                    },
                    "page_size": 100
                }),
                "options": {}
            },
            "id": "query-habits",
            "name": "Query Habits",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [520, 100],
            "credentials": {**NOTION_CRED},
            "onError": "continueRegularOutput",
        },

        # ==============================================================
        # 4. Query Priority Tasks (HTTP Request → Notion API)
        #    Status IN (In Progress, Ready To Start)
        #    AND (Due Date <= today+2 OR Priority IN (Critical, High))
        # ==============================================================
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.notion.com/v1/databases/{PROJECTS_TASKS_DB_PAGE_ID}/query",
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
                "jsonBody": "=" + json.dumps({
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
                                    {"property": "Type", "select": {"equals": "Sub-task"}}
                                ]
                            },
                            {
                                "or": [
                                    {"property": "Due Date", "date": {"on_or_before": "{{$json.todayPlus2}}"}},
                                    {"property": "Priority", "select": {"equals": "Critical"}},
                                    {"property": "Priority", "select": {"equals": "High"}}
                                ]
                            }
                        ]
                    },
                    "sorts": [
                        {"property": "Priority", "direction": "ascending"},
                        {"property": "Due Date", "direction": "ascending"}
                    ],
                    "page_size": 10
                }),
                "options": {}
            },
            "id": "query-tasks",
            "name": "Query Priority Tasks",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [520, 300],
            "credentials": {**NOTION_CRED},
            "onError": "continueRegularOutput",
        },

        # ==============================================================
        # 5. Query Player Stats (HTTP Request → Notion API)
        #    Read Level, XP, Gold from player stats page
        # ==============================================================
        {
            "parameters": {
                "method": "GET",
                "url": f"https://api.notion.com/v1/pages/{PLAYER_STATS_PAGE_ID}",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "notionApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Notion-Version", "value": "2022-06-28"}
                    ]
                },
                "options": {}
            },
            "id": "query-player",
            "name": "Query Player Stats",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [520, 500],
            "credentials": {**NOTION_CRED},
            "onError": "continueRegularOutput",
        },

        # ==============================================================
        # 6. Build Quest List (Code)
        #    Combine habits + tasks, score, format Telegram + CC text
        # ==============================================================
        {
            "parameters": {
                "jsCode": r"""// Build Daily Quest List
// Access parallel query results via $('NodeName')

const ctx = $('Date Context').first().json;
const today = ctx.today;
const dayOfWeek = ctx.dayOfWeek; // 0=Sun, 1=Mon, ..., 6=Sat
const dayName = ctx.dayName;
const currentMonth = ctx.month;

// ========================================
// Parse Habits
// ========================================
let habitsRaw = [];
try {
  habitsRaw = $('Query Habits').first().json.results || [];
} catch(e) { habitsRaw = []; }

// Helper: get property value from Notion page
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
    case 'number':
      return prop.number;
    case 'checkbox':
      return prop.checkbox;
    case 'date':
      return prop.date ? prop.date.start : null;
    default:
      return null;
  }
}

// Determine which habits are due today based on Frequency
const habitsDueToday = [];

for (const habit of habitsRaw) {
  const name = getProp(habit, 'Name', 'title') || getProp(habit, 'Habit', 'title') || 'Sans nom';
  const frequency = getProp(habit, 'Frequency', 'select') || '';
  const difficulty = getProp(habit, 'Difficulty', 'select') || 'Moderate';
  const completedThisMonth = getProp(habit, 'Completed This Month', 'number') || 0;
  const totalThisMonth = getProp(habit, 'Total This Month', 'number') || 0;
  const streak = getProp(habit, 'Current Streak', 'number') || 0;

  let isDue = false;

  if (frequency.startsWith('1') || frequency.toLowerCase().includes('daily')) {
    // Daily habits are always due
    isDue = true;
  } else if (frequency.startsWith('7') || frequency.toLowerCase().includes('weekly')) {
    // Weekly habits are due on Monday (dayOfWeek=1)
    // Or if not yet completed this week
    isDue = (dayOfWeek === 1);
  } else if (frequency.startsWith('3') || frequency.toLowerCase().includes('3x')) {
    // 3x/week: due Mon, Wed, Fri (1, 3, 5)
    isDue = [1, 3, 5].includes(dayOfWeek);
  } else if (frequency.startsWith('5') || frequency.toLowerCase().includes('5x')) {
    // 5x/week: due Mon-Fri (1-5)
    isDue = (dayOfWeek >= 1 && dayOfWeek <= 5);
  } else if (frequency.startsWith('2') || frequency.toLowerCase().includes('2x')) {
    // 2x/week: due Mon and Thu (1, 4)
    isDue = [1, 4].includes(dayOfWeek);
  } else {
    // Fallback: check if completed count < expected count for the month
    // Parse target from frequency (e.g., "14 - 14x/month" -> 14)
    const match = frequency.match(/(\d+)/);
    if (match) {
      const target = parseInt(match[1]);
      // Get day of month
      const dayOfMonth = parseInt(today.split('-')[2]);
      const daysInMonth = new Date(parseInt(today.split('-')[0]), parseInt(today.split('-')[1]), 0).getDate();
      // Expected completions by today
      const expectedByToday = Math.ceil((target / daysInMonth) * dayOfMonth);
      isDue = (completedThisMonth < expectedByToday);
    } else {
      // Unknown frequency, assume due
      isDue = true;
    }
  }

  if (isDue) {
    // XP reward based on difficulty
    let xp = 25;
    if (difficulty === 'Easy' || difficulty.includes('Easy')) xp = 10;
    else if (difficulty === 'Moderate' || difficulty.includes('Moderate')) xp = 25;
    else if (difficulty === 'Hard' || difficulty.includes('Hard')) xp = 50;

    habitsDueToday.push({
      name,
      type: 'Habit',
      difficulty,
      xp,
      frequency,
      streak,
      priority: 'habit'
    });
  }
}

// ========================================
// Parse Priority Tasks
// ========================================
let tasksRaw = [];
try {
  tasksRaw = $('Query Priority Tasks').first().json.results || [];
} catch(e) { tasksRaw = []; }

const priorityTasks = [];
const PRIORITY_ORDER = { 'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3 };

for (const task of tasksRaw) {
  const name = getProp(task, 'Name', 'title') || 'Sans nom';
  const priority = getProp(task, 'Priority', 'select') || 'Medium';
  const status = getProp(task, 'Status', 'status') || '';
  const dueDate = getProp(task, 'Due Date', 'date');
  const difficulty = getProp(task, 'Difficulty', 'select') || 'Moderate';
  const type = getProp(task, 'Type', 'select') || 'Task';

  // XP reward based on difficulty (tasks get slightly more XP)
  let xp = 35;
  if (difficulty === 'Easy' || difficulty.includes('Easy')) xp = 15;
  else if (difficulty === 'Moderate' || difficulty.includes('Moderate')) xp = 35;
  else if (difficulty === 'Hard' || difficulty.includes('Hard')) xp = 75;

  // Priority sort value
  const prioValue = PRIORITY_ORDER[priority] !== undefined ? PRIORITY_ORDER[priority] : 3;

  priorityTasks.push({
    name,
    type: 'Task',
    difficulty,
    xp,
    priority,
    prioValue,
    status,
    dueDate,
    taskType: type
  });
}

// Sort tasks by priority then due date
priorityTasks.sort((a, b) => {
  if (a.prioValue !== b.prioValue) return a.prioValue - b.prioValue;
  if (a.dueDate && b.dueDate) return a.dueDate.localeCompare(b.dueDate);
  if (a.dueDate) return -1;
  if (b.dueDate) return 1;
  return 0;
});

// ========================================
// Parse Player Stats
// ========================================
let level = '?', xpTotal = '?', gold = '?';
try {
  const playerData = $('Query Player Stats').first().json;
  const props = playerData.properties || {};

  // Try common property names for Level, XP, Gold
  const levelProp = props['Level'] || props['Niveau'] || {};
  level = levelProp.number != null ? levelProp.number : '?';

  const xpProp = props['XP'] || props['Total XP'] || props['Experience'] || {};
  xpTotal = xpProp.number != null ? xpProp.number : '?';

  const goldProp = props['Gold'] || props['Or'] || props['Coins'] || {};
  gold = goldProp.number != null ? goldProp.number : '?';
} catch(e) {
  // Player stats unavailable, use defaults
}

// ========================================
// Build Telegram Message (HTML)
// ========================================
const totalHabitXP = habitsDueToday.reduce((sum, h) => sum + h.xp, 0);
const totalTaskXP = priorityTasks.reduce((sum, t) => sum + t.xp, 0);
const totalXP = totalHabitXP + totalTaskXP;

let msg = '';
msg += `<b>\u2694\ufe0f DAILY QUESTS \u2014 ${dayName} ${today}</b>\n`;
msg += `Level ${level} | ${xpTotal} XP | ${gold} Gold\n`;

// Habits section
msg += `\n<b>\ud83c\udfaf HABITS (${habitsDueToday.length})</b>\n`;
if (habitsDueToday.length === 0) {
  msg += `<i>Aucune habitude due aujourd'hui</i>\n`;
} else {
  for (const h of habitsDueToday) {
    let streakInfo = '';
    if (h.streak > 0) streakInfo = ` \ud83d\udd25${h.streak}`;
    msg += `\u25fb ${h.name} (+${h.xp}XP)${streakInfo}\n`;
  }
}

// Priority Tasks section
msg += `\n<b>\u26a1 PRIORITY TASKS (${priorityTasks.length})</b>\n`;
if (priorityTasks.length === 0) {
  msg += `<i>Aucune tache prioritaire</i>\n`;
} else {
  for (const t of priorityTasks) {
    const prioIcon = t.priority === 'Critical' ? '\ud83d\udd34' :
                     t.priority === 'High' ? '\ud83d\udfe0' :
                     t.priority === 'Medium' ? '\ud83d\udfe1' : '\u26aa';
    let duePart = '';
    if (t.dueDate) {
      const due = new Date(t.dueDate + 'T00:00:00Z');
      const tod = new Date(today + 'T00:00:00Z');
      const diff = Math.floor((due - tod) / (1000 * 60 * 60 * 24));
      if (diff < 0) duePart = ` \u26a0\ufe0f${Math.abs(diff)}j retard`;
      else if (diff === 0) duePart = ' \u23f0auj.';
      else if (diff === 1) duePart = ' demain';
      else if (diff === 2) duePart = ' J+2';
    }
    msg += `\u25fb ${prioIcon} ${t.name} [${t.priority}] (+${t.xp}XP)${duePart}\n`;
  }
}

// Summary
msg += `\n<b>\ud83d\udcb0 Potentiel: +${totalXP} XP aujourd'hui</b>\n`;
if (habitsDueToday.length > 0) {
  msg += `\ud83d\udd25 Bonus streak dispo si toutes les habitudes sont completees !`;
}

// ========================================
// Build Command Center focus text
// ========================================
// Title array for Notion API v3
const titleArray = [
  ["\ud83c\udfaf TODAY'S QUESTS", [["b"]]],
  [" \u2014 " + dayName + " " + today]
];

// Content: top quests summary
const focusLines = [];

// Top 3 habits
const topHabits = habitsDueToday.slice(0, 3);
for (const h of topHabits) {
  focusLines.push(`\u25fb ${h.name} (+${h.xp}XP)`);
}

// Top 3 tasks
const topTasks = priorityTasks.slice(0, 3);
for (const t of topTasks) {
  const prioTag = t.priority === 'Critical' ? '\u2757' :
                  t.priority === 'High' ? '\ud83d\udd34' : '\ud83d\udfe0';
  focusLines.push(`${prioTag} ${t.name} [${t.priority}]`);
}

if (focusLines.length === 0) {
  focusLines.push('Aucune quete pour le moment.');
}

// Summary line
const summaryLine = `${habitsDueToday.length} habitudes + ${priorityTasks.length} taches | Potentiel: +${totalXP} XP`;

// Build content segments for Notion API v3
const contentSegments = [];
contentSegments.push([focusLines[0]]);
for (let i = 1; i < focusLines.length; i++) {
  contentSegments.push(["\n"]);
  contentSegments.push([focusLines[i]]);
}
contentSegments.push(["\n"]);
contentSegments.push([summaryLine, [["i"]]]);

return [{json: {
  message: msg,
  titleArray: JSON.stringify(titleArray),
  contentArray: JSON.stringify(contentSegments),
  habitsCount: habitsDueToday.length,
  tasksCount: priorityTasks.length,
  totalXP,
  level,
  dayName,
  today
}}];
"""
            },
            "id": "build-quests",
            "name": "Build Quest List",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [840, 300],
        },

        # ==============================================================
        # 7. Update Command Center — Title block (Notion API v3)
        # ==============================================================
        {
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
                "jsonBody": '={{ JSON.stringify({ '
                    + 'requestId: "quest-title-" + Date.now(), '
                    + 'transactions: [{ '
                    + '  id: "quest-title-tx-" + Date.now(), '
                    + f'  spaceId: "{SPACE_ID}", '
                    + '  operations: [{ '
                    + '    pointer: { table: "block", '
                    + f'    id: "{TODAYS_FOCUS_TITLE_BLOCK}" '
                    + '    }, '
                    + '    path: ["properties", "title"], '
                    + '    command: "set", '
                    + '    args: JSON.parse($json.titleArray) '
                    + '  }] '
                    + '}] '
                    + '}) }}',
                "options": {}
            },
            "id": "update-cc-title",
            "name": "Update CC Title",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1120, 160],
            "onError": "continueRegularOutput",
        },

        # ==============================================================
        # 8. Update Command Center — Content block (Notion API v3)
        # ==============================================================
        {
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
                "jsonBody": '={{ JSON.stringify({ '
                    + 'requestId: "quest-content-" + Date.now(), '
                    + 'transactions: [{ '
                    + '  id: "quest-content-tx-" + Date.now(), '
                    + f'  spaceId: "{SPACE_ID}", '
                    + '  operations: [{ '
                    + '    pointer: { table: "block", '
                    + f'    id: "{TODAYS_FOCUS_CONTENT_BLOCK}" '
                    + '    }, '
                    + '    path: ["properties", "title"], '
                    + '    command: "set", '
                    + '    args: JSON.parse($json.contentArray) '
                    + '  }] '
                    + '}] '
                    + '}) }}',
                "options": {}
            },
            "id": "update-cc-content",
            "name": "Update CC Content",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1360, 160],
            "onError": "continueRegularOutput",
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
            "position": [1120, 440],
        },

        # ==============================================================
        # 9b. Send Quests via Telegram
        # ==============================================================
        {
            "parameters": {
                "chatId": TELEGRAM_CHAT_ID,
                "text": "={{ $json.text }}",
                "additionalFields": {
                    "parse_mode": "HTML"
                },
            },
            "id": "send-telegram",
            "name": "Send Quests",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [1360, 440],
            "credentials": {**TELEGRAM_CRED},
        },
    ],
    "connections": {
        # 1 -> 2: Schedule -> Date Context
        "Every Morning 7AM": {
            "main": [[{"node": "Date Context", "type": "main", "index": 0}]]
        },
        # 2 -> 3,4,5: Date Context -> 3 parallel queries
        "Date Context": {
            "main": [
                [
                    {"node": "Query Habits", "type": "main", "index": 0},
                    {"node": "Query Priority Tasks", "type": "main", "index": 0},
                    {"node": "Query Player Stats", "type": "main", "index": 0},
                ]
            ]
        },
        # 3,4,5 -> 6: All queries merge into Build Quest List
        "Query Habits": {
            "main": [[{"node": "Build Quest List", "type": "main", "index": 0}]]
        },
        "Query Priority Tasks": {
            "main": [[{"node": "Build Quest List", "type": "main", "index": 0}]]
        },
        "Query Player Stats": {
            "main": [[{"node": "Build Quest List", "type": "main", "index": 0}]]
        },
        # 6 -> 7,9a: Build Quest List -> Update CC Title + Split for Telegram (parallel)
        "Build Quest List": {
            "main": [
                [
                    {"node": "Update CC Title", "type": "main", "index": 0},
                    {"node": "Split for Telegram", "type": "main", "index": 0},
                ]
            ]
        },
        # 9a -> 9b: Split -> Send
        "Split for Telegram": {
            "main": [[{"node": "Send Quests", "type": "main", "index": 0}]]
        },
        # 7 -> 8: Update CC Title -> Update CC Content (sequential for rate limit)
        "Update CC Title": {
            "main": [[{"node": "Update CC Content", "type": "main", "index": 0}]]
        },
    },
    "settings": {
        "executionOrder": "v1",
        "timezone": "Europe/Paris",
    },
}


def main():
    """Create and activate the Daily Quest Generator workflow."""

    print("=" * 60)
    print("  Daily Quest Generator — Creation Script")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Fetch existing credentials to verify IDs
    # ------------------------------------------------------------------
    print("\n1. Fetching existing credentials...")
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
                print(f"   Notion cred: {c['id']} -- {cname}")
            if ctype == "telegramApi" or "telegram" in cname.lower():
                telegram_cred_id = c["id"]
                telegram_cred_name = cname
                print(f"   Telegram cred: {c['id']} -- {cname}")
    else:
        print(f"   WARNING: Could not fetch credentials: {resp.status_code}")

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
    print("\n2. Updating credential references...")
    for node in workflow["nodes"]:
        if "credentials" in node:
            if "notionApi" in node["credentials"]:
                node["credentials"]["notionApi"] = {
                    "id": str(notion_cred_id),
                    "name": notion_cred_name,
                }
                print(f"   {node['name']}: notionApi -> {notion_cred_id}")
            if "telegramApi" in node["credentials"]:
                node["credentials"]["telegramApi"] = {
                    "id": str(telegram_cred_id),
                    "name": telegram_cred_name,
                }
                print(f"   {node['name']}: telegramApi -> {telegram_cred_id}")

    # ------------------------------------------------------------------
    # 3. Check for existing workflow with same name and remove it
    # ------------------------------------------------------------------
    print("\n3. Checking for existing workflow...")
    resp = requests.get(f"{N8N_URL}/api/v1/workflows", headers=HEADERS)
    if resp.ok:
        existing = resp.json().get("data", [])
        for wf in existing:
            if wf.get("name") == workflow["name"]:
                wf_id = wf["id"]
                print(f"   Found existing workflow: {wf_id} -- deleting...")
                del_resp = requests.delete(
                    f"{N8N_URL}/api/v1/workflows/{wf_id}",
                    headers=HEADERS,
                )
                if del_resp.ok:
                    print(f"   Deleted old workflow {wf_id}")
                else:
                    print(f"   WARNING: Could not delete: {del_resp.status_code}")

    # ------------------------------------------------------------------
    # 4. Create the workflow
    # ------------------------------------------------------------------
    print("\n4. Creating Daily Quest Generator workflow...")
    resp = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow,
    )

    if not resp.ok:
        print(f"   ERROR: Creation failed: {resp.status_code}")
        print(f"   Response: {resp.text[:500]}")
        return None

    data = resp.json()
    wf_id = data.get("id")
    print(f"   Created: {data.get('name')} (ID: {wf_id})")

    # ------------------------------------------------------------------
    # 5. Activate the workflow
    # ------------------------------------------------------------------
    print("\n5. Activating workflow...")
    resp2 = requests.post(
        f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS,
    )

    if resp2.ok:
        print("   ACTIVE -- runs daily at 7h00 CET")
    else:
        print(f"   Activation failed: {resp2.status_code}")
        print(f"   Response: {resp2.text[:200]}")

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("DAILY QUEST GENERATOR")
    print("=" * 60)
    print(f"Workflow ID:     {wf_id}")
    print(f"Schedule:        0 7 * * * (7h00 CET)")
    print(f"Timezone:        Europe/Paris")
    print(f"Habits DB:       {HABITS_DB_PAGE_ID}")
    print(f"Tasks DB:        {PROJECTS_TASKS_DB_PAGE_ID}")
    print(f"Player Stats:    {PLAYER_STATS_PAGE_ID}")
    print(f"Command Center:  {COMMAND_CENTER_PAGE_ID}")
    print(f"Telegram chat:   {TELEGRAM_CHAT_ID}")
    print()
    print("Flow:")
    print("  1. Every Morning 7AM (Schedule Trigger, CRON 0 7 * * *)")
    print("  2. Date Context (today, dayOfWeek, dayName in French)")
    print("  3-5. Parallel queries:")
    print("     - Query Habits (all active, filter due-today in code)")
    print("     - Query Priority Tasks (In Progress/Ready, urgent/high prio)")
    print("     - Query Player Stats (Level, XP, Gold)")
    print("  6. Build Quest List (combine, XP scoring, Telegram HTML + CC text)")
    print("  7-8. Update Command Center (API v3 saveTransactions):")
    print(f"     - Title block: {TODAYS_FOCUS_TITLE_BLOCK}")
    print(f"     - Content block: {TODAYS_FOCUS_CONTENT_BLOCK}")
    print("  9. Send Quests (Telegram, HTML parse mode)")
    print()
    print("Notes:")
    print("  - Runs BEFORE Morning Brief (8h)")
    print("  - Overwrites 6h CRON TODAY'S FOCUS with full quest context")
    print("  - onError: continueRegularOutput on all Notion queries")
    print("=" * 60)
    print(f"\nOpen: {N8N_URL}/workflow/{wf_id}")

    return wf_id


if __name__ == "__main__":
    wf_id = main()
    if wf_id:
        print(f"\nDone! Workflow ID: {wf_id}")
    else:
        print("\nFailed to create workflow.")
        exit(1)
