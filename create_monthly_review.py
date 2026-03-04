#!/usr/bin/env python3
"""Create the Monthly Review & Retrospective workflow in n8n.

Schedule: 1st of each month at 20h00 (Europe/Paris)
Sequence: Monthly Review (20h) -> [user reads it] -> Monthly Reset (00h next night)

Pipeline:
1.  Schedule Trigger (CRON 0 20 1 * *)
2.  Month Context (Code: previous month name, date range)
3.  Query Habits Performance (HTTP -> Notion)
4.  Query Month's Activity Log (HTTP -> Notion)
5.  Query Completed Tasks (HTTP -> Notion)
6.  Query Goals Progress (HTTP -> Notion)
7.  Query Revenue (HTTP -> Notion)
8.  Query Player Stats (HTTP -> Notion)
9.  Aggregate All Data (Code)
10. Claude Retrospective (HTTP -> Anthropic)
11. Build Telegram Message (Code)
12. Send Monthly Review (Telegram)

Queries 3-8 run in parallel from node 2 for speed.
"""

import json
import requests
import uuid

# -- Config ----------------------------------------------------------------
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

# Notion Database IDs
HABITS_DB = "305da200-b2d6-8139-b19f-d2a0d46cf7e6"
ACTIVITY_LOG_DB = "305da200-b2d6-819f-915f-d35f51386aa8"
PROJECTS_TASKS_DB = "305da200-b2d6-8145-bc16-eaee02925a14"
GOALS_DB = "bc88ee5f-f09b-4f45-adb9-faae179aa276"
REVENUE_LOG_DB = "b960493b-3982-455b-aa8e-3b6f348d3e85"
PLAYER_STATS_PAGE = "310da200-b2d6-8005-aeb9-e410436b48cf"

# Telegram
TELEGRAM_CHAT_ID = "7342622615"

# Existing Monthly Reset workflow
MONTHLY_RESET_WF = "aUG16a4xQ10hnYgP"

WORKFLOW_NAME = "Monthly Review & Retrospective"


def uid():
    return str(uuid.uuid4())


def notion_query_node(node_id, name, db_id, json_body, position, cred=None):
    """Helper to build an HTTP Request node that queries a Notion database."""
    return {
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": position,
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{db_id}/query",
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
            "jsonBody": json_body,
            "options": {}
        },
        "credentials": cred or NOTION_CRED,
        "onError": "continueRegularOutput"
    }


def build_workflow():
    """Build the Monthly Review & Retrospective workflow."""

    # Node IDs
    trigger_id = uid()
    month_ctx_id = uid()
    query_habits_id = uid()
    query_activity_id = uid()
    query_tasks_id = uid()
    query_goals_id = uid()
    query_revenue_id = uid()
    query_player_id = uid()
    aggregate_id = uid()
    claude_retro_id = uid()
    build_msg_id = uid()
    send_telegram_id = uid()

    # =====================================================================
    # Node 1: Schedule Trigger -- 1st of month at 20h00
    # =====================================================================
    trigger = {
        "id": trigger_id,
        "name": "1er du Mois 20h",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 400],
        "parameters": {
            "rule": {
                "interval": [
                    {
                        "field": "cronExpression",
                        "expression": "0 20 1 * *"
                    }
                ]
            }
        }
    }

    # =====================================================================
    # Node 2: Month Context -- compute previous month name & date range
    # =====================================================================
    month_ctx_code = r"""
// Compute the CURRENT month that is about to end
// This workflow runs on the 1st at 20h, BEFORE the midnight reset.
// So we capture THIS month's data (which is actually the previous calendar month
// from the 1st's perspective, but since we run at 20h on the 1st,
// the "month about to end" is last month).

const now = new Date();

// Previous month: the month that just ended
const prevMonthDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
const prevYear = prevMonthDate.getFullYear();
const prevMonth = prevMonthDate.getMonth(); // 0-indexed

// First day of previous month
const firstDay = new Date(prevYear, prevMonth, 1);
const firstDayISO = firstDay.toISOString().split('T')[0];

// Last day of previous month
const lastDay = new Date(prevYear, prevMonth + 1, 0);
const lastDayISO = lastDay.toISOString().split('T')[0];

// French month names
const moisFR = [
    'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre'
];
const monthNameFR = moisFR[prevMonth];
const monthLabel = `${monthNameFR} ${prevYear}`;

// Also compute current month info (the new month starting)
const currentMonthName = moisFR[now.getMonth()];
const currentMonthLabel = `${currentMonthName} ${now.getFullYear()}`;

return [{json: {
    monthLabel,
    monthNameFR,
    year: prevYear,
    month: prevMonth + 1,
    firstDay: firstDayISO,
    lastDay: lastDayISO,
    currentMonthLabel,
    runDate: now.toISOString().split('T')[0]
}}];
"""

    month_ctx = {
        "id": month_ctx_id,
        "name": "Month Context",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [240, 400],
        "parameters": {"jsCode": month_ctx_code}
    }

    # =====================================================================
    # Node 3: Query Habits Performance
    # Gets all habits with their current month stats (before reset)
    # =====================================================================
    query_habits = {
        "id": query_habits_id,
        "name": "Query Habits",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [520, 0],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{HABITS_DB}/query",
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
                "page_size": 100
            }),
            "options": {}
        },
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # =====================================================================
    # Node 4: Query Activity Log (filter by month date range)
    # =====================================================================
    query_activity_body = (
        '={\n'
        '  "filter": {\n'
        '    "and": [\n'
        '      {"property": "Date", "date": {"on_or_after": "{{ $json.firstDay }}"}},\n'
        '      {"property": "Date", "date": {"on_or_before": "{{ $json.lastDay }}"}}\n'
        '    ]\n'
        '  },\n'
        '  "page_size": 100\n'
        '}'
    )

    query_activity = notion_query_node(
        query_activity_id,
        "Query Activity Log",
        ACTIVITY_LOG_DB,
        query_activity_body,
        [520, 160]
    )

    # =====================================================================
    # Node 5: Query Completed Tasks
    # =====================================================================
    query_tasks_body = (
        '={\n'
        '  "filter": {\n'
        '    "and": [\n'
        '      {"property": "Status", "status": {"equals": "Complete"}},\n'
        '      {"property": "Completed On", "date": {"on_or_after": "{{ $json.firstDay }}"}},\n'
        '      {"property": "Completed On", "date": {"on_or_before": "{{ $json.lastDay }}"}}\n'
        '    ]\n'
        '  },\n'
        '  "sorts": [{"property": "Completed On", "direction": "descending"}],\n'
        '  "page_size": 100\n'
        '}'
    )

    query_tasks = notion_query_node(
        query_tasks_id,
        "Query Completed Tasks",
        PROJECTS_TASKS_DB,
        query_tasks_body,
        [520, 320]
    )

    # =====================================================================
    # Node 6: Query Goals Progress
    # =====================================================================
    query_goals = notion_query_node(
        query_goals_id,
        "Query Goals Progress",
        GOALS_DB,
        json.dumps({
            "filter": {
                "property": "Status",
                "status": {"equals": "In Progress"}
            },
            "page_size": 100
        }),
        [520, 480]
    )

    # =====================================================================
    # Node 7: Query Revenue
    # =====================================================================
    query_revenue_body = (
        '={\n'
        '  "filter": {\n'
        '    "and": [\n'
        '      {"property": "Date", "date": {"on_or_after": "{{ $json.firstDay }}"}},\n'
        '      {"property": "Date", "date": {"on_or_before": "{{ $json.lastDay }}"}}\n'
        '    ]\n'
        '  },\n'
        '  "page_size": 100\n'
        '}'
    )

    query_revenue = notion_query_node(
        query_revenue_id,
        "Query Revenue",
        REVENUE_LOG_DB,
        query_revenue_body,
        [520, 640]
    )

    # =====================================================================
    # Node 8: Query Player Stats (single page, not a DB query)
    # =====================================================================
    query_player = {
        "id": query_player_id,
        "name": "Query Player Stats",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [520, 800],
        "parameters": {
            "method": "GET",
            "url": f"https://api.notion.com/v1/pages/{PLAYER_STATS_PAGE}",
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
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # =====================================================================
    # Node 9: Aggregate All Data
    # =====================================================================
    aggregate_code = r"""
// ------------------------------------------------------------------
// Aggregate all parallel query results into a single summary
// ------------------------------------------------------------------

const monthCtx = $('Month Context').first().json;

// --- Helper functions ---
function getTitle(page) {
    const props = page.properties || {};
    for (const key of Object.keys(props)) {
        const p = props[key];
        if (p.type === 'title' && p.title && p.title.length > 0) {
            return p.title.map(t => t.plain_text || '').join('');
        }
    }
    return 'Sans titre';
}

function getSelectValue(page, propName) {
    const p = (page.properties || {})[propName];
    if (!p) return null;
    if (p.type === 'select' && p.select) return p.select.name;
    if (p.type === 'status' && p.status) return p.status.name;
    return null;
}

function getNumber(page, propName) {
    const p = (page.properties || {})[propName];
    if (!p) return 0;
    if (p.type === 'number') return p.number || 0;
    if (p.type === 'formula') {
        const f = p.formula;
        if (f.type === 'number') return f.number || 0;
    }
    if (p.type === 'rollup') {
        const r = p.rollup;
        if (r.type === 'number') return r.number || 0;
    }
    return 0;
}

function getCheckbox(page, propName) {
    const p = (page.properties || {})[propName];
    if (!p) return false;
    if (p.type === 'checkbox') return p.checkbox || false;
    return false;
}

function getDate(page, propName) {
    const p = (page.properties || {})[propName];
    if (!p) return null;
    if (p.type === 'date' && p.date) return p.date.start || null;
    return null;
}

// ========== 1. HABITS ==========
const habitsRaw = $('Query Habits').first().json;
const habits = (habitsRaw.results || []);

let totalCompletedThisMonth = 0;
let totalTargetThisMonth = 0;
const habitDetails = [];

for (const h of habits) {
    const name = getTitle(h);
    const completedMonth = getNumber(h, 'Completed This Month');
    const totalMonth = getNumber(h, 'Total This Month');
    const streak = getNumber(h, 'Streak Days');
    const difficulty = getSelectValue(h, 'Difficulty') || 'Medium';
    const active = getCheckbox(h, 'Active');

    // Only count active habits (or all if no Active property)
    if (active === false && habits.some(x => getCheckbox(x, 'Active'))) continue;

    const completionPct = totalMonth > 0
        ? Math.round((completedMonth / totalMonth) * 100)
        : 0;

    habitDetails.push({
        name,
        completedMonth,
        totalMonth,
        completionPct,
        streak,
        difficulty
    });

    totalCompletedThisMonth += completedMonth;
    totalTargetThisMonth += totalMonth;
}

// Sort habits by completion %
habitDetails.sort((a, b) => b.completionPct - a.completionPct);

const habitCompletionRate = totalTargetThisMonth > 0
    ? Math.round((totalCompletedThisMonth / totalTargetThisMonth) * 100)
    : 0;

const topHabits = habitDetails.slice(0, 3);
const bottomHabits = habitDetails.filter(h => h.completionPct < 100)
    .sort((a, b) => a.completionPct - b.completionPct)
    .slice(0, 3);

// ========== 2. ACTIVITY LOG ==========
const activityRaw = $('Query Activity Log').first().json;
const activities = (activityRaw.results || []);

let totalXP = 0;
let totalGold = 0;
let totalHP = 0;

for (const a of activities) {
    totalXP += getNumber(a, 'XP') || 0;
    totalGold += getNumber(a, 'Gold') || 0;
    totalHP += getNumber(a, 'HP') || 0;
}

// ========== 3. COMPLETED TASKS ==========
const tasksRaw = $('Query Completed Tasks').first().json;
const tasks = (tasksRaw.results || []);

const completedTasks = [];
const tasksByCategory = {};

for (const t of tasks) {
    const name = getTitle(t);
    const category = getSelectValue(t, 'Category') || 'Autre';
    const priority = getSelectValue(t, 'Priority') || 'Medium';
    const type = getSelectValue(t, 'Type') || 'Task';

    completedTasks.push({ name, category, priority, type });

    if (!tasksByCategory[category]) tasksByCategory[category] = 0;
    tasksByCategory[category]++;
}

// ========== 4. GOALS ==========
const goalsRaw = $('Query Goals Progress').first().json;
const goals = (goalsRaw.results || []);

const activeGoals = goals.map(g => ({
    name: getTitle(g),
    type: getSelectValue(g, 'Type') || 'Unknown',
    progress: getNumber(g, 'Progress %'),
    targetDate: getDate(g, 'Target Date'),
    status: getSelectValue(g, 'Status')
}));

// ========== 5. REVENUE ==========
const revenueRaw = $('Query Revenue').first().json;
const revenueEntries = (revenueRaw.results || []);

let totalRevenue = 0;
const revenueBySource = {};

for (const r of revenueEntries) {
    const amount = getNumber(r, 'Amount') || getNumber(r, 'Montant') || getNumber(r, 'Revenue') || 0;
    totalRevenue += amount;

    const source = getSelectValue(r, 'Source') || getSelectValue(r, 'Client') || 'Autre';
    if (!revenueBySource[source]) revenueBySource[source] = 0;
    revenueBySource[source] += amount;
}

// ========== 6. PLAYER STATS ==========
const playerRaw = $('Query Player Stats').first().json;
const playerProps = playerRaw.properties || {};

const playerLevel = getNumber(playerRaw, 'Level') || getNumber(playerRaw, 'Niveau') || 0;
const playerXP = getNumber(playerRaw, 'XP') || getNumber(playerRaw, 'Total XP') || 0;
const playerGold = getNumber(playerRaw, 'Gold') || getNumber(playerRaw, 'Total Gold') || 0;

// ========== BUILD SUMMARY ==========
const summary = {
    // Month info
    monthLabel: monthCtx.monthLabel,
    firstDay: monthCtx.firstDay,
    lastDay: monthCtx.lastDay,
    currentMonthLabel: monthCtx.currentMonthLabel,

    // Habits
    habitCompletionRate,
    totalCompletedThisMonth,
    totalTargetThisMonth,
    habitCount: habitDetails.length,
    topHabits,
    bottomHabits,
    allHabits: habitDetails,

    // Activity / Gamification
    totalXP,
    totalGold,
    totalHP,
    activityCount: activities.length,

    // Tasks
    tasksCompletedCount: completedTasks.length,
    tasksByCategory,
    completedTasks: completedTasks.slice(0, 20), // Limit for Claude context

    // Goals
    activeGoals,
    goalCount: activeGoals.length,

    // Revenue
    totalRevenue,
    revenueEntryCount: revenueEntries.length,
    revenueBySource,

    // Player
    playerLevel,
    playerXP,
    playerGold
};

return [{json: summary}];
"""

    aggregate = {
        "id": aggregate_id,
        "name": "Aggregate All Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [820, 400],
        "parameters": {"jsCode": aggregate_code}
    }

    # =====================================================================
    # Node 10: Claude Retrospective
    # =====================================================================
    claude_retro = {
        "id": claude_retro_id,
        "name": "Claude Retrospective",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1080, 400],
        "parameters": {
            "method": "POST",
            "url": "https://api.anthropic.com/v1/messages",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "anthropicApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "x-api-key", "value": "={{ $credentials.anthropicApi.apiKey }}"},
                    {"name": "anthropic-version", "value": "2023-06-01"},
                    {"name": "content-type", "value": "application/json"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": """={
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 3000,
  "system": "Tu es Orun, le coach IA de Chris. Genere une retrospective mensuelle en analysant les donnees. Sois direct, honnete, et actionnable. Structure: 1) Resume du mois (2-3 phrases), 2) Top wins (3 max), 3) Points d'amelioration (3 max), 4) Habitudes: analyse completion rate et tendances, 5) Business: CA, clients, pipeline, 6) Recommandations pour le mois prochain (3 actions concretes). Reponds en JSON: {resume, wins:[], ameliorations:[], habits_analysis, business_analysis, recommendations:[]}",
  "messages": [
    {
      "role": "user",
      "content": "Voici le bilan du mois de {{ $json.monthLabel }} pour Chris (Adaptive Logic, agence d'automatisation IA a Avignon). Objectif principal: 2000 EUR de CA d'ici fin mars 2026.\n\n## Habitudes\n- Taux de completion global: {{ $json.habitCompletionRate }}% ({{ $json.totalCompletedThisMonth }}/{{ $json.totalTargetThisMonth }})\n- Top 3 habitudes: {{ JSON.stringify($json.topHabits) }}\n- Habitudes a ameliorer: {{ JSON.stringify($json.bottomHabits) }}\n- Toutes les habitudes: {{ JSON.stringify($json.allHabits) }}\n\n## Taches completees: {{ $json.tasksCompletedCount }}\n- Par categorie: {{ JSON.stringify($json.tasksByCategory) }}\n- Details (top 20): {{ JSON.stringify($json.completedTasks) }}\n\n## Objectifs actifs ({{ $json.goalCount }})\n{{ JSON.stringify($json.activeGoals) }}\n\n## Revenus\n- CA total du mois: {{ $json.totalRevenue }} EUR ({{ $json.revenueEntryCount }} entrees)\n- Par source: {{ JSON.stringify($json.revenueBySource) }}\n\n## Gamification\n- XP gagnes: {{ $json.totalXP }}\n- Gold gagne: {{ $json.totalGold }}\n- HP gagnes: {{ $json.totalHP }}\n- Activites enregistrees: {{ $json.activityCount }}\n- Niveau actuel: {{ $json.playerLevel }}\n\nGenere la retrospective en JSON uniquement, sans markdown."
    }
  ]
}""",
            "options": {}
        },
        "credentials": ANTHROPIC_CRED
    }

    # =====================================================================
    # Node 11: Build Telegram Message
    # =====================================================================
    build_msg_code = r"""
// ------------------------------------------------------------------
// Parse Claude's response and build rich HTML Telegram message
// ------------------------------------------------------------------

const aggregated = $('Aggregate All Data').first().json;
const claudeResponse = $('Claude Retrospective').first().json;

// Parse Claude JSON response
let retro = {
    resume: '',
    wins: [],
    ameliorations: [],
    habits_analysis: '',
    business_analysis: '',
    recommendations: []
};

try {
    const text = claudeResponse.content[0].text;
    // Try direct JSON parse
    retro = JSON.parse(text);
} catch (e) {
    try {
        // Try to extract JSON from text
        const raw = claudeResponse.content[0].text;
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
            retro = JSON.parse(jsonMatch[0]);
        }
    } catch (e2) {
        retro.resume = 'Erreur de parsing de la retrospective Claude.';
    }
}

// --- Build progress bars ---
function progressBar(pct) {
    const filled = Math.round(pct / 10);
    const empty = 10 - filled;
    return '\u2588'.repeat(filled) + '\u2591'.repeat(empty) + ` ${pct}%`;
}

// --- Build habit leaderboard ---
let habitBoard = '';
const allHabits = aggregated.allHabits || [];
for (const h of allHabits) {
    const bar = progressBar(h.completionPct);
    habitBoard += `  ${h.name}: ${bar} (${h.completedMonth}/${h.totalMonth})\n`;
    if (h.streak > 0) {
        habitBoard += `    Streak: ${h.streak}j\n`;
    }
}

// --- Build goals section ---
let goalsSection = '';
for (const g of (aggregated.activeGoals || [])) {
    const bar = progressBar(g.progress || 0);
    const deadline = g.targetDate ? ` | Echeance: ${g.targetDate}` : '';
    goalsSection += `  ${g.name}: ${bar}${deadline}\n`;
}

// --- Format wins ---
let winsText = '';
for (let i = 0; i < (retro.wins || []).length; i++) {
    winsText += `  ${i + 1}. ${retro.wins[i]}\n`;
}

// --- Format ameliorations ---
let amelioText = '';
for (let i = 0; i < (retro.ameliorations || []).length; i++) {
    amelioText += `  ${i + 1}. ${retro.ameliorations[i]}\n`;
}

// --- Format recommendations ---
let recoText = '';
for (let i = 0; i < (retro.recommendations || []).length; i++) {
    recoText += `  ${i + 1}. ${retro.recommendations[i]}\n`;
}

// --- Tasks by category ---
let taskCatText = '';
const cats = aggregated.tasksByCategory || {};
for (const [cat, count] of Object.entries(cats).sort((a, b) => b[1] - a[1])) {
    taskCatText += `  ${cat}: ${count}\n`;
}

// --- Revenue by source ---
let revSourceText = '';
const sources = aggregated.revenueBySource || {};
for (const [src, amount] of Object.entries(sources).sort((a, b) => b[1] - a[1])) {
    revSourceText += `  ${src}: ${amount} EUR\n`;
}

// --- Build full HTML message ---
const msg = [
    `<b>RETROSPECTIVE MENSUELLE</b>`,
    `<b>${aggregated.monthLabel}</b>`,
    ``,
    `<b>RESUME</b>`,
    retro.resume || 'N/A',
    ``,
    `<b>TOP WINS</b>`,
    winsText || '  Aucun',
    ``,
    `<b>POINTS D'AMELIORATION</b>`,
    amelioText || '  Aucun',
    ``,
    `<b>HABITUDES</b> (${aggregated.habitCompletionRate}% global)`,
    habitBoard || '  Aucune donnee',
    retro.habits_analysis ? `\n<i>${retro.habits_analysis}</i>` : '',
    ``,
    `<b>TACHES COMPLETEES</b>: ${aggregated.tasksCompletedCount}`,
    taskCatText || '  Aucune',
    ``,
    `<b>OBJECTIFS</b>`,
    goalsSection || '  Aucun objectif actif',
    ``,
    `<b>BUSINESS</b>`,
    `  CA du mois: <b>${aggregated.totalRevenue} EUR</b>`,
    revSourceText,
    retro.business_analysis ? `<i>${retro.business_analysis}</i>` : '',
    ``,
    `<b>GAMIFICATION</b>`,
    `  Niveau: ${aggregated.playerLevel}`,
    `  XP: +${aggregated.totalXP} | Gold: +${aggregated.totalGold} | HP: +${aggregated.totalHP}`,
    `  Activites: ${aggregated.activityCount}`,
    ``,
    `<b>RECOMMANDATIONS POUR ${aggregated.currentMonthLabel.toUpperCase()}</b>`,
    recoText || '  Aucune',
    ``,
    `<i>Le Monthly Reset s'executera a minuit.</i>`,
    `<i>Bonne lecture!</i>`
].join('\n');

// --- Split for Telegram (4096 char limit) ---
function splitForTelegram(text, maxChars) {
    maxChars = maxChars || 4000;
    if (text.length <= maxChars) return [text];

    // Split at double newlines (section boundaries)
    const sections = text.split(/\n\n/);
    const parts = [];
    let current = '';

    for (const section of sections) {
        if (current.length + section.length + 2 > maxChars) {
            if (current) parts.push(current.trim());
            // If single section exceeds limit, split at newlines
            if (section.length > maxChars) {
                const lines = section.split('\n');
                let chunk = '';
                for (const line of lines) {
                    if (chunk.length + line.length + 1 > maxChars) {
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
        if (merged.length > 0 && merged[merged.length - 1].length + part.length + 2 <= maxChars) {
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
    return merged;
}

const msgParts = splitForTelegram(msg);

if (msgParts.length === 1) {
    return [{json: { telegramMessage: msg, retro, aggregated }}];
} else {
    return msgParts.map((part, i) => ({
        json: {
            telegramMessage: `[${i + 1}/${msgParts.length}] ${part}`,
            retro: i === 0 ? retro : null,
            aggregated: i === 0 ? aggregated : null
        }
    }));
}
"""

    build_msg = {
        "id": build_msg_id,
        "name": "Build Telegram Message",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1340, 400],
        "parameters": {"jsCode": build_msg_code}
    }

    # =====================================================================
    # Node 12: Send Monthly Review via Telegram
    # =====================================================================
    send_telegram = {
        "id": send_telegram_id,
        "name": "Send Monthly Review",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [1580, 400],
        "parameters": {
            "chatId": TELEGRAM_CHAT_ID,
            "text": "={{ $json.telegramMessage }}",
            "additionalFields": {
                "parse_mode": "HTML"
            }
        },
        "credentials": TELEGRAM_CRED
    }

    # =====================================================================
    # Assemble all nodes
    # =====================================================================
    nodes = [
        trigger,
        month_ctx,
        query_habits,
        query_activity,
        query_tasks,
        query_goals,
        query_revenue,
        query_player,
        aggregate,
        claude_retro,
        build_msg,
        send_telegram,
    ]

    # =====================================================================
    # Connections
    # =====================================================================
    # Trigger -> Month Context -> 6 parallel queries -> Aggregate -> Claude -> Build -> Send
    connections = {
        "1er du Mois 20h": {
            "main": [[
                {"node": "Month Context", "type": "main", "index": 0}
            ]]
        },
        "Month Context": {
            "main": [[
                {"node": "Query Habits", "type": "main", "index": 0},
                {"node": "Query Activity Log", "type": "main", "index": 0},
                {"node": "Query Completed Tasks", "type": "main", "index": 0},
                {"node": "Query Goals Progress", "type": "main", "index": 0},
                {"node": "Query Revenue", "type": "main", "index": 0},
                {"node": "Query Player Stats", "type": "main", "index": 0},
            ]]
        },
        "Query Habits": {
            "main": [[
                {"node": "Aggregate All Data", "type": "main", "index": 0}
            ]]
        },
        "Query Activity Log": {
            "main": [[
                {"node": "Aggregate All Data", "type": "main", "index": 0}
            ]]
        },
        "Query Completed Tasks": {
            "main": [[
                {"node": "Aggregate All Data", "type": "main", "index": 0}
            ]]
        },
        "Query Goals Progress": {
            "main": [[
                {"node": "Aggregate All Data", "type": "main", "index": 0}
            ]]
        },
        "Query Revenue": {
            "main": [[
                {"node": "Aggregate All Data", "type": "main", "index": 0}
            ]]
        },
        "Query Player Stats": {
            "main": [[
                {"node": "Aggregate All Data", "type": "main", "index": 0}
            ]]
        },
        "Aggregate All Data": {
            "main": [[
                {"node": "Claude Retrospective", "type": "main", "index": 0}
            ]]
        },
        "Claude Retrospective": {
            "main": [[
                {"node": "Build Telegram Message", "type": "main", "index": 0}
            ]]
        },
        "Build Telegram Message": {
            "main": [[
                {"node": "Send Monthly Review", "type": "main", "index": 0}
            ]]
        },
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
    print("  Monthly Review & Retrospective -- n8n Workflow Creator")
    print("=" * 60)

    workflow = build_workflow()

    # ------------------------------------------------------------------
    # 1. Check for existing workflow with same name
    # ------------------------------------------------------------------
    print("\n1. Checking existing workflows...")
    r = requests.get(f"{N8N_URL}/api/v1/workflows", headers=HEADERS)
    if r.status_code == 200:
        existing = r.json().get("data", [])
        for wf in existing:
            if wf.get("name") == WORKFLOW_NAME:
                wf_id = wf["id"]
                print(f"   Found existing: {wf_id} (active={wf.get('active')})")
                print(f"   Deactivating...")
                requests.post(
                    f"{N8N_URL}/api/v1/workflows/{wf_id}/deactivate",
                    headers=HEADERS
                )
                print(f"   Updating with new definition...")
                r2 = requests.put(
                    f"{N8N_URL}/api/v1/workflows/{wf_id}",
                    headers=HEADERS,
                    json=workflow
                )
                if r2.status_code == 200:
                    print(f"   Updated successfully!")
                    r3 = requests.post(
                        f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
                        headers=HEADERS
                    )
                    if r3.status_code == 200:
                        print(f"   Activated!")
                    else:
                        print(f"   Activation: {r3.status_code} {r3.text[:200]}")
                    print_summary(wf_id, workflow)
                    return wf_id
                else:
                    print(f"   Update error: {r2.status_code} {r2.text[:300]}")
                    print(f"   Falling through to create new...")

    # ------------------------------------------------------------------
    # 2. Create workflow
    # ------------------------------------------------------------------
    print("\n2. Creating Monthly Review & Retrospective workflow...")
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
        print("\n3. Activating workflow...")
        r2 = requests.post(
            f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
            headers=HEADERS
        )
        if r2.status_code == 200:
            print(f"   Activated!")
        else:
            print(f"   Activation: {r2.status_code} {r2.text[:200]}")

        print_summary(wf_id, workflow)
        return wf_id
    else:
        print(f"   Error: {r.status_code}")
        print(f"   {r.text[:500]}")
        return None


def print_summary(wf_id, workflow):
    """Print a summary of the created workflow."""
    print(f"\n{'=' * 60}")
    print(f"  MONTHLY REVIEW & RETROSPECTIVE")
    print(f"{'=' * 60}")
    print(f"  Workflow ID:  {wf_id}")
    print(f"  Schedule:     1er du mois a 20h00 (Europe/Paris)")
    print(f"  CRON:         0 20 1 * *")
    print(f"  Nodes:        {len(workflow['nodes'])}")
    print(f"  Timezone:     Europe/Paris")
    print(f"{'=' * 60}")
    print(f"\n  Pipeline:")
    print(f"  1.  Schedule Trigger (1er du mois, 20h)")
    print(f"  2.  Month Context (mois precedent, dates)")
    print(f"  3.  Query Habits Performance         [PARALLEL]")
    print(f"  4.  Query Activity Log (XP/Gold/HP)  [PARALLEL]")
    print(f"  5.  Query Completed Tasks             [PARALLEL]")
    print(f"  6.  Query Goals Progress              [PARALLEL]")
    print(f"  7.  Query Revenue                     [PARALLEL]")
    print(f"  8.  Query Player Stats                [PARALLEL]")
    print(f"  9.  Aggregate All Data")
    print(f"  10. Claude Retrospective (claude-sonnet-4-20250514)")
    print(f"  11. Build Telegram Message (HTML)")
    print(f"  12. Send Monthly Review")
    print(f"\n  Sequence:")
    print(f"  Monthly Review (20h) -> [user reads] -> Monthly Reset (00h)")
    print(f"  Monthly Reset workflow: {MONTHLY_RESET_WF}")
    print(f"\n  Notion DBs:")
    print(f"  - Habits:          {HABITS_DB}")
    print(f"  - Activity Log:    {ACTIVITY_LOG_DB}")
    print(f"  - Projects/Tasks:  {PROJECTS_TASKS_DB}")
    print(f"  - Goals:           {GOALS_DB}")
    print(f"  - Revenue Log:     {REVENUE_LOG_DB}")
    print(f"  - Player Stats:    {PLAYER_STATS_PAGE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    wf_id = main()
    if wf_id:
        print(f"\nDone! Workflow ID: {wf_id}")
    else:
        print("\nFailed to create workflow.")
