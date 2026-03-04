#!/usr/bin/env python3
"""Create n8n workflow: Auto-Scheduling Hebdomadaire.

Schedule: Every Monday at 7h00 (Europe/Paris)
Pipeline:
1. Schedule Trigger (CRON 0 7 * * 1)
2. Compute week context (Monday-Sunday dates, daily capacity)
3. Query unscheduled tasks (Status IN Ready To Start/In Progress/Backlog, Due Date empty)
4. Query already scheduled tasks (Due Date this week, Status NOT Complete/Archive)
5. Query overdue tasks (Due Date < today, Status NOT Complete/Archive)
6. Claude intelligent scheduling (balance workload, respect priorities/difficulty)
7. Parse schedule + fallback round-robin if Claude fails
8. Update each task Due Date in Notion (+ Backlog -> Ready To Start)
9. Build week planning recap
10. Send Telegram notification

Uses Notion official API via HTTP Request nodes with notionApi credential.
Uses Anthropic API via HTTP Request for intelligent scheduling.
"""

import json
import requests
import uuid

# ── Config ──────────────────────────────────────────────────────────
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYi"
    "LCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQz"
    "MTUzLCJleHAiOjE3NzY3MjI0MDB9."
    "sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
)
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Credentials
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}
ANTHROPIC_CRED = {"anthropicApi": {"id": "sE8nBT8crViDOv1E", "name": "Anthropic account"}}

# Notion IDs
PROJECTS_TASKS_DB = "305da200-b2d6-8145-bc16-eaee02925a14"

# Telegram
TELEGRAM_CHAT_ID = "7342622615"

WORKFLOW_NAME = "Auto-Scheduling Hebdomadaire"


def uid():
    return str(uuid.uuid4())


# ── Claude system prompt ────────────────────────────────────────────
CLAUDE_SYSTEM_PROMPT = (
    "Tu es un planificateur de taches intelligent. "
    "Assigne des dates aux taches non planifiees et replanifie les taches en retard. "
    "Regles: max 3 taches Critical/High par jour, max 6 total par jour, "
    "repartir equitablement sur la semaine, prioriser Critical > High > Medium > Low, "
    "taches Hard pas le meme jour qu'une autre Hard, weekend plus leger."
)


def build_workflow():
    """Build the Auto-Scheduling Hebdomadaire workflow."""

    # Node IDs
    trigger_id = uid()
    week_context_id = uid()
    query_unscheduled_id = uid()
    query_scheduled_id = uid()
    query_overdue_id = uid()
    merge_queries_id = uid()
    check_tasks_id = uid()
    build_claude_prompt_id = uid()
    claude_scheduling_id = uid()
    parse_schedule_id = uid()
    split_updates_id = uid()
    update_task_id = uid()
    collect_results_id = uid()
    build_recap_id = uid()
    telegram_id = uid()
    telegram_empty_id = uid()
    split_telegram_id = uid()

    # ── Node 1: Schedule Trigger ── Monday 7h00 Europe/Paris
    trigger = {
        "id": trigger_id,
        "name": "Monday 7h",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 300],
        "parameters": {
            "rule": {
                "interval": [
                    {
                        "field": "cronExpression",
                        "expression": "0 7 * * 1"
                    }
                ]
            }
        }
    }

    # ── Node 2: Week Context ── Compute Monday-Sunday dates + capacity
    week_context_code = r"""
// Compute this week's Monday-Sunday dates (Europe/Paris)
const now = new Date();

// Get Monday of this week
const dayOfWeek = now.getDay(); // 0=Sunday, 1=Monday, ...
const diffToMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
const monday = new Date(now);
monday.setDate(now.getDate() - diffToMonday);
monday.setHours(0, 0, 0, 0);

// Build array of 7 days (Mon-Sun)
const days = [];
const dayNames = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];

for (let i = 0; i < 7; i++) {
  const d = new Date(monday);
  d.setDate(monday.getDate() + i);
  const iso = d.toISOString().split('T')[0];
  const isWeekend = i >= 5; // Sat=5, Sun=6

  days.push({
    date: iso,
    name: dayNames[i],
    isWeekend: isWeekend,
    maxCriticalHigh: isWeekend ? 1 : 3,  // max Critical/High tasks
    maxTotal: isWeekend ? 3 : 6            // max total tasks
  });
}

const mondayISO = days[0].date;
const sundayISO = days[6].date;
const todayISO = now.toISOString().split('T')[0];

// Week number (ISO 8601)
const jan1 = new Date(monday.getFullYear(), 0, 1);
const daysSinceJan1 = Math.floor((monday - jan1) / 86400000);
const weekNumber = Math.ceil((daysSinceJan1 + jan1.getDay() + 1) / 7);

return [{json: {
  monday: mondayISO,
  sunday: sundayISO,
  today: todayISO,
  weekNumber: weekNumber,
  year: monday.getFullYear(),
  days: days
}}];
"""

    week_context = {
        "id": week_context_id,
        "name": "Week Context",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [240, 300],
        "parameters": {"jsCode": week_context_code}
    }

    # ── Node 3: Query Unscheduled Tasks ──
    # Status IN (Ready To Start, In Progress, Backlog), Due Date is_empty, Type=Task
    query_unscheduled_filter = json.dumps({
        "filter": {
            "and": [
                {
                    "or": [
                        {"property": "Status", "status": {"equals": "Ready To Start"}},
                        {"property": "Status", "status": {"equals": "In Progress"}},
                        {"property": "Status", "status": {"equals": "Backlog"}}
                    ]
                },
                {"property": "Due Date", "date": {"is_empty": True}},
                {"property": "Type", "select": {"equals": "Task"}}
            ]
        },
        "sorts": [
            {"property": "Priority", "direction": "ascending"}
        ],
        "page_size": 100
    })

    query_unscheduled = {
        "id": query_unscheduled_id,
        "name": "Query Unscheduled Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [520, 100],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{PROJECTS_TASKS_DB}/query",
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
            "jsonBody": query_unscheduled_filter,
            "options": {}
        },
        "credentials": {**NOTION_CRED}
    }

    # ── Node 4: Query Already Scheduled Tasks ──
    # Due Date between Monday and Sunday, Status NOT Complete/Archive
    query_scheduled_body = (
        '={\n'
        '  "filter": {\n'
        '    "and": [\n'
        '      {"property": "Due Date", "date": {"on_or_after": "{{ $("Week Context").first().json.monday }}"}},\n'
        '      {"property": "Due Date", "date": {"on_or_before": "{{ $("Week Context").first().json.sunday }}"}},\n'
        '      {"property": "Status", "status": {"does_not_equal": "Complete"}},\n'
        '      {"property": "Status", "status": {"does_not_equal": "Archive"}},\n'
        '      {"property": "Type", "select": {"equals": "Task"}}\n'
        '    ]\n'
        '  },\n'
        '  "page_size": 100\n'
        '}'
    )

    query_scheduled = {
        "id": query_scheduled_id,
        "name": "Query Scheduled This Week",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [520, 300],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{PROJECTS_TASKS_DB}/query",
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
            "jsonBody": query_scheduled_body,
            "options": {}
        },
        "credentials": {**NOTION_CRED}
    }

    # ── Node 5: Query Overdue Tasks ──
    # Due Date < today, Status NOT Complete/Archive
    query_overdue_body = (
        '={\n'
        '  "filter": {\n'
        '    "and": [\n'
        '      {"property": "Due Date", "date": {"before": "{{ $("Week Context").first().json.today }}"}},\n'
        '      {"property": "Status", "status": {"does_not_equal": "Complete"}},\n'
        '      {"property": "Status", "status": {"does_not_equal": "Archive"}},\n'
        '      {"property": "Type", "select": {"equals": "Task"}}\n'
        '    ]\n'
        '  },\n'
        '  "sorts": [{"property": "Priority", "direction": "ascending"}],\n'
        '  "page_size": 100\n'
        '}'
    )

    query_overdue = {
        "id": query_overdue_id,
        "name": "Query Overdue Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [520, 500],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{PROJECTS_TASKS_DB}/query",
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
            "jsonBody": query_overdue_body,
            "options": {}
        },
        "credentials": {**NOTION_CRED}
    }

    # ── Node 6: Merge Queries ── Aggregate the 3 query results
    merge_queries_code = r"""
// Merge the 3 Notion query results into a single object
const weekContext = $('Week Context').first().json;
const unscheduledRaw = $('Query Unscheduled Tasks').first().json;
const scheduledRaw = $('Query Scheduled This Week').first().json;
const overdueRaw = $('Query Overdue Tasks').first().json;

// Helper: extract task data from Notion page
function extractTask(page) {
  const props = page.properties || {};
  const name = props.Name?.title?.[0]?.plain_text || '(sans nom)';
  const status = props.Status?.status?.name || '';
  const priority = props.Priority?.select?.name || 'Medium';
  const difficulty = props.Difficulty?.select?.name || '2 - Moderate';
  const category = props.Category?.select?.name || '';
  const dueDate = props['Due Date']?.date?.start || null;
  const duration = props.Duration?.select?.name || '1h';
  const description = (props.Description?.rich_text || [])
    .map(rt => rt.plain_text).join('').substring(0, 200) || '';

  return {
    id: page.id,
    name,
    status,
    priority,
    difficulty,
    category,
    dueDate,
    duration,
    description,
    url: page.url || ''
  };
}

const unscheduled = (unscheduledRaw.results || []).map(extractTask);
const scheduled = (scheduledRaw.results || []).map(extractTask);
const overdue = (overdueRaw.results || []).map(extractTask);

// Build per-day load from already scheduled tasks
const dayLoad = {};
for (const day of weekContext.days) {
  dayLoad[day.date] = {
    totalCount: 0,
    criticalHighCount: 0,
    hasHard: false,
    tasks: []
  };
}

for (const task of scheduled) {
  if (task.dueDate && dayLoad[task.dueDate]) {
    const dl = dayLoad[task.dueDate];
    dl.totalCount++;
    if (['Critical', 'High'].includes(task.priority)) dl.criticalHighCount++;
    if (task.difficulty && task.difficulty.startsWith('3')) dl.hasHard = true;
    dl.tasks.push(task.name);
  }
}

const totalToSchedule = unscheduled.length + overdue.length;

return [{json: {
  weekContext,
  unscheduled,
  scheduled,
  overdue,
  dayLoad,
  totalToSchedule,
  hasTasksToSchedule: totalToSchedule > 0
}}];
"""

    merge_queries = {
        "id": merge_queries_id,
        "name": "Merge Queries",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [800, 300],
        "parameters": {"jsCode": merge_queries_code}
    }

    # ── Node 7: Check if there are tasks to schedule ──
    check_tasks = {
        "id": check_tasks_id,
        "name": "Has Tasks?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [1040, 300],
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict"
                },
                "conditions": [
                    {
                        "id": "has-tasks-check",
                        "leftValue": "={{ $json.hasTasksToSchedule }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "equals"
                        }
                    }
                ],
                "combinator": "and"
            }
        }
    }

    # ── Node 8: Build Claude Prompt ── Prepare the scheduling request
    build_claude_prompt_code = r"""
// Build the Claude scheduling prompt with all context
const data = $input.first().json;
const wc = data.weekContext;

const userMessage = {
  week: {
    monday: wc.monday,
    sunday: wc.sunday,
    today: wc.today,
    weekNumber: wc.weekNumber,
    days: wc.days
  },
  unscheduled_tasks: data.unscheduled.map(t => ({
    id: t.id,
    name: t.name,
    priority: t.priority,
    difficulty: t.difficulty,
    status: t.status,
    category: t.category,
    duration: t.duration,
    description: t.description
  })),
  overdue_tasks: data.overdue.map(t => ({
    id: t.id,
    name: t.name,
    priority: t.priority,
    difficulty: t.difficulty,
    status: t.status,
    category: t.category,
    duration: t.duration,
    originalDueDate: t.dueDate
  })),
  current_day_load: data.dayLoad,
  instructions: [
    "Assigne une date (YYYY-MM-DD) entre " + wc.monday + " et " + wc.sunday + " a chaque tache.",
    "Les taches en retard (overdue) doivent etre replanifiees en priorite aux premiers creneaux disponibles.",
    "Respecte les capacites max par jour (voir days.maxCriticalHigh et days.maxTotal).",
    "Tiens compte du current_day_load pour ne pas surcharger les jours deja planifies.",
    "Pas deux taches '3 - Hard' le meme jour.",
    "Weekend (samedi/dimanche) plus leger : max 1 Critical/High, max 3 total.",
    "Retourne UNIQUEMENT un JSON valide: {\"schedule\": [{\"taskId\": \"...\", \"dueDate\": \"YYYY-MM-DD\", \"reason\": \"...\"}], \"summary\": \"...\"}"
  ]
};

return [{json: {
  ...data,
  userPrompt: JSON.stringify(userMessage, null, 2),
  systemPrompt: """ + json.dumps(CLAUDE_SYSTEM_PROMPT) + r"""
}}];
"""

    build_claude_prompt = {
        "id": build_claude_prompt_id,
        "name": "Build Claude Prompt",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1300, 200],
        "parameters": {"jsCode": build_claude_prompt_code}
    }

    # ── Node 9: Claude Scheduling ── Call Anthropic API
    claude_scheduling = {
        "id": claude_scheduling_id,
        "name": "Claude Scheduling",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1540, 200],
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
            "jsonBody": (
                '={"model": "claude-sonnet-4-20250514", "max_tokens": 4096, '
                '"system": {{ JSON.stringify($json.systemPrompt) }}, '
                '"messages": [{"role": "user", "content": {{ JSON.stringify($json.userPrompt) }}}]}'
            ),
            "options": {}
        },
        "credentials": {**ANTHROPIC_CRED},
        "onError": "continueRegularOutput"
    }

    # ── Node 10: Parse Schedule ── Parse Claude response + fallback round-robin
    parse_schedule_code = r"""
// Parse Claude's scheduling response
// Fallback: simple round-robin by priority if Claude fails
const data = $('Build Claude Prompt').first().json;
const claudeResponse = $input.first().json;
const wc = data.weekContext;

let schedule = [];
let usedFallback = false;
let summary = '';

try {
  // Try parsing Claude's response
  const content = claudeResponse.content?.[0]?.text || '';
  const jsonMatch = content.match(/\{[\s\S]*\}/);
  const parsed = JSON.parse(jsonMatch ? jsonMatch[0] : content);
  schedule = parsed.schedule || [];
  summary = parsed.summary || '';

  // Validate: all dates must be within the week
  const validDates = wc.days.map(d => d.date);
  schedule = schedule.filter(s => {
    if (!s.taskId || !s.dueDate) return false;
    if (!validDates.includes(s.dueDate)) return false;
    return true;
  });

  if (schedule.length === 0) {
    throw new Error('No valid schedule entries from Claude');
  }
} catch (e) {
  // ── FALLBACK: round-robin by priority ──
  usedFallback = true;
  summary = 'Fallback round-robin utilise (Claude indisponible ou erreur parsing)';

  // Combine unscheduled + overdue, sorted by priority
  const priorityOrder = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3};
  const allTasks = [...data.overdue, ...data.unscheduled].sort((a, b) => {
    return (priorityOrder[a.priority] || 3) - (priorityOrder[b.priority] || 3);
  });

  // Copy dayLoad to track capacity
  const load = JSON.parse(JSON.stringify(data.dayLoad));
  const days = wc.days;

  for (const task of allTasks) {
    // Find first available day
    let assigned = false;
    for (const day of days) {
      const dl = load[day.date];
      if (!dl) continue;

      const isCritHigh = ['Critical', 'High'].includes(task.priority);
      const isHard = task.difficulty && task.difficulty.startsWith('3');

      // Check capacity
      if (dl.totalCount >= day.maxTotal) continue;
      if (isCritHigh && dl.criticalHighCount >= day.maxCriticalHigh) continue;
      if (isHard && dl.hasHard) continue;

      // Assign
      schedule.push({
        taskId: task.id,
        dueDate: day.date,
        reason: 'Fallback round-robin (priorite ' + task.priority + ')'
      });

      dl.totalCount++;
      if (isCritHigh) dl.criticalHighCount++;
      if (isHard) dl.hasHard = true;
      assigned = true;
      break;
    }

    if (!assigned) {
      // If all days full, assign to least loaded weekday
      let minDay = days[0];
      let minLoad = Infinity;
      for (const day of days.slice(0, 5)) { // weekdays only
        const dl = load[day.date];
        if (dl && dl.totalCount < minLoad) {
          minLoad = dl.totalCount;
          minDay = day;
        }
      }
      schedule.push({
        taskId: task.id,
        dueDate: minDay.date,
        reason: 'Overflow — jour le moins charge'
      });
      if (load[minDay.date]) load[minDay.date].totalCount++;
    }
  }
}

// Build a lookup of task info for the recap
const allTasksMap = {};
for (const t of [...data.unscheduled, ...data.overdue]) {
  allTasksMap[t.id] = t;
}

// Enrich schedule with task names
const enrichedSchedule = schedule.map(s => ({
  ...s,
  taskName: allTasksMap[s.taskId]?.name || '?',
  taskPriority: allTasksMap[s.taskId]?.priority || 'Medium',
  taskDifficulty: allTasksMap[s.taskId]?.difficulty || '2 - Moderate',
  taskStatus: allTasksMap[s.taskId]?.status || '',
  isOverdue: data.overdue.some(t => t.id === s.taskId)
}));

return [{json: {
  schedule: enrichedSchedule,
  usedFallback,
  summary,
  totalScheduled: enrichedSchedule.length,
  weekContext: wc
}}];
"""

    parse_schedule = {
        "id": parse_schedule_id,
        "name": "Parse Schedule",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1780, 200],
        "parameters": {"jsCode": parse_schedule_code}
    }

    # ── Node 11: Split Updates ── One item per task to update
    split_updates_code = r"""
// Split schedule into individual task update items
const data = $input.first().json;
const schedule = data.schedule || [];

if (schedule.length === 0) {
  return [{json: {skip: true, reason: 'Aucune tache a planifier'}}];
}

return schedule.map(s => ({
  json: {
    taskId: s.taskId,
    dueDate: s.dueDate,
    reason: s.reason,
    taskName: s.taskName,
    taskPriority: s.taskPriority,
    taskDifficulty: s.taskDifficulty,
    taskStatus: s.taskStatus,
    isOverdue: s.isOverdue,
    // Keep global context for the recap node
    _totalScheduled: data.totalScheduled,
    _usedFallback: data.usedFallback,
    _summary: data.summary,
    _weekContext: data.weekContext
  }
}));
"""

    split_updates = {
        "id": split_updates_id,
        "name": "Split Updates",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2020, 200],
        "parameters": {"jsCode": split_updates_code}
    }

    # ── Node 12: Update Task Due Date ── PATCH each task in Notion
    # Also update Status from Backlog -> Ready To Start
    update_task = {
        "id": update_task_id,
        "name": "Update Task Due Date",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2260, 200],
        "parameters": {
            "method": "PATCH",
            "url": "=https://api.notion.com/v1/pages/{{ $json.taskId }}",
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
            "jsonBody": (
                '={\n'
                '  "properties": {\n'
                '    "Due Date": {"date": {"start": "{{ $json.dueDate }}"}},\n'
                '    "Status": {"status": {"name": "{{ $json.taskStatus === \'Backlog\' ? \'Ready To Start\' : $json.taskStatus }}"}}\n'
                '  }\n'
                '}'
            ),
            "options": {}
        },
        "credentials": {**NOTION_CRED},
        "onError": "continueRegularOutput"
    }

    # ── Node 13: Collect Results ── Aggregate all updates for recap
    collect_results_code = r"""
// Collect all update results
const splitItems = $('Split Updates').all();
const parseData = $('Parse Schedule').first().json;

const updates = [];
const errors = [];

for (const item of splitItems) {
  const j = item.json;
  if (j.skip) continue;
  updates.push({
    taskId: j.taskId,
    taskName: j.taskName,
    dueDate: j.dueDate,
    reason: j.reason,
    priority: j.taskPriority,
    difficulty: j.taskDifficulty,
    isOverdue: j.isOverdue
  });
}

return [{json: {
  updates,
  errors,
  totalScheduled: parseData.totalScheduled,
  usedFallback: parseData.usedFallback,
  summary: parseData.summary,
  weekContext: parseData.weekContext
}}];
"""

    collect_results = {
        "id": collect_results_id,
        "name": "Collect Results",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2500, 200],
        "parameters": {"jsCode": collect_results_code}
    }

    # ── Node 14: Build Recap ── Format week planning summary
    build_recap_code = r"""
// Build week planning recap grouped by day
const data = $input.first().json;
const updates = data.updates || [];
const wc = data.weekContext;

if (updates.length === 0) {
  return [{json: {
    recap: '<b>Auto-Scheduling Hebdomadaire</b>\n\nAucune tache a planifier cette semaine.',
    hasRecap: false
  }}];
}

const priorityIcon = {
  'Critical': '🔴',
  'High': '🟠',
  'Medium': '🟡',
  'Low': '🟢'
};

// Group updates by day
const byDay = {};
for (const u of updates) {
  if (!byDay[u.dueDate]) byDay[u.dueDate] = [];
  byDay[u.dueDate].push(u);
}

let msg = '<b>Auto-Scheduling Hebdomadaire</b>\n';
msg += `<b>Semaine ${wc.weekNumber} — ${wc.monday} au ${wc.sunday}</b>\n\n`;

if (data.usedFallback) {
  msg += '⚠️ <i>Mode fallback (round-robin) utilise</i>\n\n';
}

if (data.summary) {
  msg += `<i>${data.summary}</i>\n\n`;
}

const dayNames = {
  0: 'Lundi', 1: 'Mardi', 2: 'Mercredi', 3: 'Jeudi',
  4: 'Vendredi', 5: 'Samedi', 6: 'Dimanche'
};

for (const day of wc.days) {
  const dayTasks = byDay[day.date] || [];
  if (dayTasks.length === 0) continue;

  msg += `<b>${day.name} ${day.date.substring(5)}</b>\n`;

  // Sort by priority within day
  const pOrder = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3};
  dayTasks.sort((a, b) => (pOrder[a.priority] || 3) - (pOrder[b.priority] || 3));

  for (const t of dayTasks) {
    const icon = priorityIcon[t.priority] || '⚪';
    const overdueTag = t.isOverdue ? ' [RETARD]' : '';
    msg += `  ${icon} ${t.taskName} (${t.priority})${overdueTag}\n`;
  }
  msg += '\n';
}

// Stats
const overdueCount = updates.filter(u => u.isOverdue).length;
const newCount = updates.length - overdueCount;
msg += `<b>Total :</b> ${updates.length} tache(s) planifiee(s)`;
if (overdueCount > 0) msg += ` (dont ${overdueCount} replanifiee(s))`;
if (newCount > 0 && overdueCount > 0) msg += `, ${newCount} nouvelle(s)`;

return [{json: {
  recap: msg,
  hasRecap: true
}}];
"""

    build_recap = {
        "id": build_recap_id,
        "name": "Build Recap",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2740, 200],
        "parameters": {"jsCode": build_recap_code}
    }

    # ── Node 14b: Split for Telegram (4096 char limit) ──
    split_telegram_code = r"""
// Split long messages for Telegram (4096 char limit)
const fullMsg = $json.recap;
const MAX = 4000;

if (fullMsg.length <= MAX) {
    return [{json: {text: fullMsg}}];
}

const sections = fullMsg.split(/\n\n/);
const parts = [];
let current = '';

for (const section of sections) {
    if (current.length + section.length + 2 > MAX) {
        if (current) parts.push(current.trim());
        if (section.length > MAX) {
            const lines = section.split('\n');
            let chunk = '';
            for (const line of lines) {
                if (chunk.length + line.length + 1 > MAX) {
                    if (chunk) parts.push(chunk.trim());
                    chunk = line;
                } else {
                    chunk += (chunk ? '\n' : '') + line;
                }
            }
            current = chunk;
        } else {
            current = section;
        }
    } else {
        current += (current ? '\n\n' : '') + section;
    }
}
if (current) parts.push(current.trim());

// Merge small consecutive parts to avoid tiny messages
const merged = [];
for (const part of parts) {
    if (merged.length > 0 && merged[merged.length - 1].length + part.length + 2 <= MAX) {
        merged[merged.length - 1] += '\n\n' + part;
    } else {
        merged.push(part);
    }
}

// Ensure first part isn't tiny (merge into second if < 200 chars)
if (merged.length > 1 && merged[0].length < 200) {
    merged[1] = merged[0] + '\n\n' + merged[1];
    merged.shift();
}

if (merged.length === 1) return [{json: {text: merged[0]}}];
return merged.map((p, i) => ({json: {text: `[${i+1}/${merged.length}]\n${p}`}}));
"""

    split_telegram = {
        "id": split_telegram_id,
        "name": "Split for Telegram",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2980, 200],
        "parameters": {"jsCode": split_telegram_code}
    }

    # ── Node 15: Send Telegram ── Week plan notification
    telegram = {
        "id": telegram_id,
        "name": "Telegram Schedule",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [3220, 200],
        "parameters": {
            "chatId": TELEGRAM_CHAT_ID,
            "text": "={{ $json.text }}",
            "additionalFields": {
                "parse_mode": "HTML"
            }
        },
        "credentials": {**TELEGRAM_CRED}
    }

    # ── Node 16: Telegram Empty ── Notify if nothing to schedule
    telegram_empty = {
        "id": telegram_empty_id,
        "name": "Telegram Rien a Planifier",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [1300, 450],
        "parameters": {
            "chatId": TELEGRAM_CHAT_ID,
            "text": (
                "<b>Auto-Scheduling Hebdomadaire</b>\n\n"
                "Aucune tache a planifier cette semaine. "
                "Toutes les taches ont deja une date ou sont completees."
            ),
            "additionalFields": {
                "parse_mode": "HTML"
            }
        },
        "credentials": {**TELEGRAM_CRED}
    }

    # ── Assemble nodes ──
    nodes = [
        trigger,
        week_context,
        query_unscheduled,
        query_scheduled,
        query_overdue,
        merge_queries,
        check_tasks,
        build_claude_prompt,
        claude_scheduling,
        parse_schedule,
        split_updates,
        update_task,
        collect_results,
        build_recap,
        split_telegram,
        telegram,
        telegram_empty,
    ]

    # ── Connections ──
    connections = {
        "Monday 7h": {
            "main": [[
                {"node": "Week Context", "type": "main", "index": 0}
            ]]
        },
        "Week Context": {
            "main": [[
                {"node": "Query Unscheduled Tasks", "type": "main", "index": 0},
                {"node": "Query Scheduled This Week", "type": "main", "index": 0},
                {"node": "Query Overdue Tasks", "type": "main", "index": 0},
            ]]
        },
        "Query Unscheduled Tasks": {
            "main": [[
                {"node": "Merge Queries", "type": "main", "index": 0}
            ]]
        },
        "Query Scheduled This Week": {
            "main": [[
                {"node": "Merge Queries", "type": "main", "index": 0}
            ]]
        },
        "Query Overdue Tasks": {
            "main": [[
                {"node": "Merge Queries", "type": "main", "index": 0}
            ]]
        },
        "Merge Queries": {
            "main": [[
                {"node": "Has Tasks?", "type": "main", "index": 0}
            ]]
        },
        "Has Tasks?": {
            "main": [
                # True = has tasks to schedule → build prompt
                [{"node": "Build Claude Prompt", "type": "main", "index": 0}],
                # False = nothing to schedule → notify
                [{"node": "Telegram Rien a Planifier", "type": "main", "index": 0}]
            ]
        },
        "Build Claude Prompt": {
            "main": [[
                {"node": "Claude Scheduling", "type": "main", "index": 0}
            ]]
        },
        "Claude Scheduling": {
            "main": [[
                {"node": "Parse Schedule", "type": "main", "index": 0}
            ]]
        },
        "Parse Schedule": {
            "main": [[
                {"node": "Split Updates", "type": "main", "index": 0}
            ]]
        },
        "Split Updates": {
            "main": [[
                {"node": "Update Task Due Date", "type": "main", "index": 0}
            ]]
        },
        "Update Task Due Date": {
            "main": [[
                {"node": "Collect Results", "type": "main", "index": 0}
            ]]
        },
        "Collect Results": {
            "main": [[
                {"node": "Build Recap", "type": "main", "index": 0}
            ]]
        },
        "Build Recap": {
            "main": [[
                {"node": "Split for Telegram", "type": "main", "index": 0}
            ]]
        },
        "Split for Telegram": {
            "main": [[
                {"node": "Telegram Schedule", "type": "main", "index": 0}
            ]]
        }
    }

    return {
        "name": WORKFLOW_NAME,
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "saveExecutionProgress": True,
            "callerPolicy": "workflowsFromSameOwner",
            "timezone": "Europe/Paris"
        }
    }


def main():
    print("=" * 60)
    print("  Auto-Scheduling Hebdomadaire — n8n Workflow Creator")
    print("=" * 60)

    workflow = build_workflow()

    # ── 1. Check existing credentials ──
    print("\n1. Checking existing credentials...")
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
            print(f"   Notion: {c['name']} (id={c['id']})")
        if ctype == "telegramApi" or "telegram" in cname:
            telegram_cred_id = c["id"]
            print(f"   Telegram: {c['name']} (id={c['id']})")
        if ctype == "anthropicApi" or "anthropic" in cname:
            anthropic_cred_id = c["id"]
            print(f"   Anthropic: {c['name']} (id={c['id']})")

    if not notion_cred_id:
        print("   WARNING: Notion credential not found!")
    if not telegram_cred_id:
        print("   WARNING: Telegram credential not found!")
    if not anthropic_cred_id:
        print("   WARNING: Anthropic credential not found!")

    # ── Patch credential IDs in workflow nodes ──
    for node in workflow["nodes"]:
        node_creds = node.get("credentials", {})
        if "notionApi" in node_creds and notion_cred_id:
            node_creds["notionApi"]["id"] = str(notion_cred_id)
        if "telegramApi" in node_creds and telegram_cred_id:
            node_creds["telegramApi"]["id"] = str(telegram_cred_id)
        if "anthropicApi" in node_creds and anthropic_cred_id:
            node_creds["anthropicApi"]["id"] = str(anthropic_cred_id)

    # ── 2. Check for existing workflow with same name ──
    print(f"\n2. Checking for existing '{WORKFLOW_NAME}' workflow...")
    r = requests.get(f"{N8N_URL}/api/v1/workflows", headers=HEADERS)
    if r.status_code == 200:
        existing = r.json().get("data", [])
        for wf in existing:
            if wf.get("name") == WORKFLOW_NAME:
                wf_id = wf["id"]
                print(f"   Found existing: {wf_id} (active={wf.get('active')})")
                print("   Deactivating...")
                requests.post(
                    f"{N8N_URL}/api/v1/workflows/{wf_id}/deactivate",
                    headers=HEADERS
                )
                print("   Updating with new definition...")
                r2 = requests.put(
                    f"{N8N_URL}/api/v1/workflows/{wf_id}",
                    headers=HEADERS,
                    json=workflow
                )
                if r2.status_code == 200:
                    print("   Updated successfully!")
                    # Reactivate
                    r3 = requests.post(
                        f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
                        headers=HEADERS
                    )
                    if r3.status_code == 200:
                        print("   Activated!")
                    else:
                        print(f"   Activation: {r3.status_code} {r3.text[:200]}")
                    _print_summary(wf_id, workflow)
                    return wf_id
                else:
                    print(f"   Update error: {r2.status_code} {r2.text[:300]}")
                    # Fall through to create new

    # ── 3. Create workflow ──
    print(f"\n3. Creating {WORKFLOW_NAME} workflow...")
    r = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow
    )

    if r.status_code in (200, 201):
        wf = r.json()
        wf_id = wf["id"]
        print(f"   Created: {wf_id}")

        # Activate
        print("\n4. Activating workflow...")
        r2 = requests.post(
            f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
            headers=HEADERS
        )
        if r2.status_code == 200:
            print("   Activated!")
        else:
            print(f"   Activation: {r2.status_code} {r2.text[:200]}")

        _print_summary(wf_id, workflow)
        return wf_id
    else:
        print(f"   Error: {r.status_code}")
        print(f"   {r.text[:500]}")
        return None


def _print_summary(wf_id, workflow):
    """Print final summary."""
    print(f"\n{'=' * 60}")
    print(f"  Workflow ID: {wf_id}")
    print(f"  Schedule: Every Monday at 7h00 (Europe/Paris)")
    print(f"  CRON: 0 7 * * 1")
    print(f"  Nodes: {len(workflow['nodes'])}")
    print(f"{'=' * 60}")
    print(f"\n  Pipeline:")
    print(f"  1. Schedule Trigger (Monday 7h)")
    print(f"  2. Week Context (Mon-Sun dates + daily capacity)")
    print(f"  3-5. Parallel queries: Unscheduled / Scheduled / Overdue")
    print(f"  6. Merge Queries (aggregate + day load)")
    print(f"  7. Check if tasks to schedule")
    print(f"  8. Build Claude Prompt (tasks + context)")
    print(f"  9. Claude Scheduling (Anthropic API)")
    print(f"  10. Parse Schedule (+ fallback round-robin)")
    print(f"  11. Split into individual updates")
    print(f"  12. Update Task Due Dates (Notion PATCH)")
    print(f"  13. Collect Results")
    print(f"  14. Build Recap (grouped by day)")
    print(f"  15. Telegram Notification (HTML)")
    print(f"\n  Capacity rules:")
    print(f"  - Mon-Fri: max 3 Critical/High, max 6 total per day")
    print(f"  - Sat-Sun: max 1 Critical/High, max 3 total per day")
    print(f"  - No two '3 - Hard' tasks on the same day")
    print(f"  - Overdue tasks rescheduled first")
    print(f"  - Fallback: round-robin if Claude fails")


if __name__ == "__main__":
    main()
