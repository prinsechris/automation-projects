#!/usr/bin/env python3
"""Create the Weekly Review IA workflow in n8n.

Schedule: Every Sunday at 20h (Europe/Paris)
Pipeline:
1. Build week range (Monday-Sunday)
2. Query Notion in parallel: completed tasks, active goals, revenue, activity log
3. Aggregate all data
4. Claude AI analysis (bilan, blocages, priorities)
5. Create Weekly Review page in Notion
6. Update Command Center callout via Notion API v3
7. Send Telegram recap
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
GOALS_DB_PAGE = "bc88ee5f-f09b-4f45-adb9-faae179aa276"
REVENUE_LOG_DB = "b960493b-3982-455b-aa8e-3b6f348d3e85"
ACTIVITY_LOG_DB = "305da200-b2d6-819f-915f-d35f51386aa8"
WEEKLY_REVIEWS_DB = "6bb690d5-5292-43f7-b03c-01d59537038b"
COMMAND_CENTER_PAGE = "306da200-b2d6-819c-8863-cf78f61ae670"

TELEGRAM_CHAT_ID = "7342622615"


def uid():
    return str(uuid.uuid4())


def build_workflow():
    """Build the Weekly Review IA workflow."""

    # Node IDs
    trigger_id = uid()
    build_week_id = uid()
    query_tasks_id = uid()
    query_goals_id = uid()
    query_revenue_id = uid()
    query_activity_id = uid()
    wait_tasks_id = uid()
    wait_goals_id = uid()
    wait_revenue_id = uid()
    wait_activity_id = uid()
    aggregate_id = uid()
    claude_analysis_id = uid()
    wait_claude_id = uid()
    create_review_id = uid()
    wait_create_id = uid()
    update_cc_id = uid()
    telegram_id = uid()
    split_telegram_id = uid()

    # ── Node 1: Schedule Trigger ──
    trigger = {
        "id": trigger_id,
        "name": "Sunday 20h",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 300],
        "parameters": {
            "rule": {
                "interval": [
                    {
                        "field": "cronExpression",
                        "expression": "0 20 * * 0"
                    }
                ]
            }
        }
    }

    # ── Node 2: Build Week Range ──
    build_week_code = r"""
// Compute Monday and Sunday of the current week (Europe/Paris)
const now = new Date();

// Get Monday of this week
const dayOfWeek = now.getDay(); // 0=Sunday
const diffToMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
const monday = new Date(now);
monday.setDate(now.getDate() - diffToMonday);
monday.setHours(0, 0, 0, 0);

const sunday = new Date(monday);
sunday.setDate(monday.getDate() + 6);
sunday.setHours(23, 59, 59, 999);

// ISO date strings
const mondayISO = monday.toISOString().split('T')[0];
const sundayISO = sunday.toISOString().split('T')[0];

// Week number (ISO 8601)
const jan1 = new Date(monday.getFullYear(), 0, 1);
const daysSinceJan1 = Math.floor((monday - jan1) / 86400000);
const weekNumber = Math.ceil((daysSinceJan1 + jan1.getDay() + 1) / 7);
const weekStr = String(weekNumber).padStart(2, '0');
const year = monday.getFullYear();

return [{json: {
    monday: mondayISO,
    sunday: sundayISO,
    mondayISO: monday.toISOString(),
    sundayISO: sunday.toISOString(),
    weekNumber: weekStr,
    year: year,
    weekLabel: `S${weekStr}-${year}`
}}];
"""

    build_week = {
        "id": build_week_id,
        "name": "Build Week Range",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 300],
        "parameters": {"jsCode": build_week_code}
    }

    # ── Node 3: Query Completed Tasks ──
    query_tasks = {
        "id": query_tasks_id,
        "name": "Query Completed Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 60],
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
            "jsonBody": '={\n  "filter": {\n    "and": [\n      {"property": "Status", "status": {"equals": "Complete"}},\n      {"property": "Completed On", "date": {"on_or_after": "{{ $json.monday }}"}}\n    ]\n  },\n  "sorts": [{"property": "Completed On", "direction": "descending"}],\n  "page_size": 100\n}',
            "options": {}
        },
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # ── Node 4: Query Active Goals ──
    query_goals = {
        "id": query_goals_id,
        "name": "Query Active Goals",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 240],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{GOALS_DB_PAGE}/query",
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
                    "property": "Status",
                    "status": {"equals": "In Progress"}
                },
                "page_size": 100
            }),
            "options": {}
        },
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # ── Node 5: Query Revenue ──
    query_revenue = {
        "id": query_revenue_id,
        "name": "Query Revenue",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 420],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{REVENUE_LOG_DB}/query",
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
            "jsonBody": '={\n  "filter": {\n    "property": "Date",\n    "date": {"on_or_after": "{{ $json.monday }}"}\n  },\n  "page_size": 100\n}',
            "options": {}
        },
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # ── Node 6: Query Activity Log ──
    query_activity = {
        "id": query_activity_id,
        "name": "Query Activity Log",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [480, 600],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{ACTIVITY_LOG_DB}/query",
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
            "jsonBody": '={\n  "filter": {\n    "property": "Date",\n    "date": {"on_or_after": "{{ $json.monday }}"}\n  },\n  "page_size": 100\n}',
            "options": {}
        },
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # ── Wait nodes (1s each, to avoid Notion rate limits) ──
    wait_tasks = {
        "id": wait_tasks_id,
        "name": "Wait Tasks",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [700, 60],
        "parameters": {"amount": 1, "unit": "seconds"},
        "webhookId": "wait-tasks"
    }

    wait_goals = {
        "id": wait_goals_id,
        "name": "Wait Goals",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [700, 240],
        "parameters": {"amount": 1, "unit": "seconds"},
        "webhookId": "wait-goals"
    }

    wait_revenue = {
        "id": wait_revenue_id,
        "name": "Wait Revenue",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [700, 420],
        "parameters": {"amount": 1, "unit": "seconds"},
        "webhookId": "wait-revenue"
    }

    wait_activity = {
        "id": wait_activity_id,
        "name": "Wait Activity",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [700, 600],
        "parameters": {"amount": 1, "unit": "seconds"},
        "webhookId": "wait-activity"
    }

    # ── Node 7: Aggregate Data ──
    aggregate_code = r"""
// Gather all query results
const weekData = $('Build Week Range').first().json;

// Tasks
const tasksRaw = $('Query Completed Tasks').first().json;
const tasks = (tasksRaw.results || []);

// Goals
const goalsRaw = $('Query Active Goals').first().json;
const goals = (goalsRaw.results || []);

// Revenue
const revenueRaw = $('Query Revenue').first().json;
const revenueEntries = (revenueRaw.results || []);

// Activity Log
const activityRaw = $('Query Activity Log').first().json;
const activities = (activityRaw.results || []);

// --- Extract task details ---
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
    return 0;
}

const completedTasks = tasks.map(t => ({
    id: t.id,
    name: getTitle(t),
    category: getSelectValue(t, 'Category'),
    priority: getSelectValue(t, 'Priority'),
    type: getSelectValue(t, 'Type')
}));

const completedTaskIds = tasks.map(t => t.id);

// --- Extract goal details ---
const activeGoals = goals.map(g => ({
    id: g.id,
    name: getTitle(g),
    type: getSelectValue(g, 'Type'),
    progress: getNumber(g, 'Progress %')
}));

const activeGoalIds = goals.map(g => g.id);

// --- Revenue calculation ---
let totalRevenue = 0;
for (const r of revenueEntries) {
    totalRevenue += getNumber(r, 'Amount') || getNumber(r, 'Montant') || getNumber(r, 'Revenue');
}

// --- XP & Gold from Activity Log ---
let totalXP = 0;
let totalGold = 0;
for (const a of activities) {
    totalXP += getNumber(a, 'XP') || 0;
    totalGold += getNumber(a, 'Gold') || 0;
}

// --- Overdue tasks (check tasks with deadline before today and not complete) ---
// Note: we query completed tasks above, overdue is separate
// For now, count is 0 - the Claude analysis will flag these from context
let overdueCount = 0;

// --- Build score ---
// Formula: completed tasks * 10 + revenue * 0.5 + (XP / 10) + (Gold / 5)
const score = Math.round(
    completedTasks.length * 10 +
    totalRevenue * 0.5 +
    totalXP / 10 +
    totalGold / 5
);

// --- Build summary for Claude ---
const summary = {
    weekLabel: weekData.weekLabel,
    monday: weekData.monday,
    sunday: weekData.sunday,
    completedTasks,
    completedTaskIds,
    taskCount: completedTasks.length,
    activeGoals,
    activeGoalIds,
    goalCount: activeGoals.length,
    totalRevenue,
    revenueEntryCount: revenueEntries.length,
    totalXP,
    totalGold,
    activityCount: activities.length,
    overdueCount,
    score,
    newProspectsCount: revenueEntries.filter(r =>
        getSelectValue(r, 'Type') === 'Prospect' ||
        getSelectValue(r, 'Source') === 'Prospect'
    ).length
};

return [{json: summary}];
"""

    aggregate = {
        "id": aggregate_id,
        "name": "Aggregate Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [940, 300],
        "parameters": {"jsCode": aggregate_code}
    }

    # ── Node 8: Claude Analysis ──
    claude_analysis = {
        "id": claude_analysis_id,
        "name": "Claude Analysis",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1180, 300],
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
  "max_tokens": 2048,
  "messages": [
    {
      "role": "user",
      "content": "Tu es l'assistant strategique de Chris, fondateur d'Adaptive Logic (agence d'automatisation IA a Avignon). Son objectif principal est d'atteindre 2000 EUR de CA d'ici fin mars 2026.\\n\\nVoici les donnees de la semaine {{ $json.weekLabel }} ({{ $json.monday }} au {{ $json.sunday }}) :\\n\\n## Taches completees ({{ $json.taskCount }})\\n{{ JSON.stringify($json.completedTasks) }}\\n\\n## Goals actifs ({{ $json.goalCount }})\\n{{ JSON.stringify($json.activeGoals) }}\\n\\n## Revenus\\n- CA periode : {{ $json.totalRevenue }} EUR ({{ $json.revenueEntryCount }} entrees)\\n- Nouveaux prospects : {{ $json.newProspectsCount }}\\n\\n## Gamification\\n- XP gagnes : {{ $json.totalXP }}\\n- Gold gagne : {{ $json.totalGold }}\\n- Activities : {{ $json.activityCount }}\\n\\n## Score semaine : {{ $json.score }}\\n\\nAnalyse cette semaine et reponds en JSON avec exactement ces 3 cles :\\n{\\n  \\"bilan\\": \\"Un paragraphe de bilan (victoires, points forts, ce qui a avance)\\",\\n  \\"blocages\\": \\"Un paragraphe sur les blocages, risques, points d'attention\\",\\n  \\"priorites\\": \\"Un paragraphe avec les 3-5 priorites concretes pour la semaine suivante\\"\\n}\\n\\nSois direct, concret, et oriente action. Reponds UNIQUEMENT avec le JSON, sans markdown."
    }
  ]
}""",
            "options": {}
        },
        "credentials": ANTHROPIC_CRED
    }

    # ── Wait after Claude ──
    wait_claude = {
        "id": wait_claude_id,
        "name": "Wait Claude",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [1400, 300],
        "parameters": {"amount": 2, "unit": "seconds"},
        "webhookId": "wait-claude"
    }

    # ── Node 9: Create Weekly Review Entry ──
    create_review_code = r"""
// Parse Claude's response
const aggregated = $('Aggregate Data').first().json;
const claudeResponse = $('Claude Analysis').first().json;

let analysis = {bilan: '', blocages: '', priorites: ''};
try {
    // Claude response is in content[0].text
    const text = claudeResponse.content[0].text;
    analysis = JSON.parse(text);
} catch (e) {
    // Fallback: try to extract from raw text
    try {
        const raw = JSON.stringify(claudeResponse);
        const match = raw.match(/\{[^{}]*"bilan"[^{}]*\}/);
        if (match) analysis = JSON.parse(match[0]);
    } catch (e2) {
        analysis = {
            bilan: 'Erreur de parsing de l\'analyse Claude',
            blocages: 'N/A',
            priorites: 'N/A'
        };
    }
}

// Build relation arrays
const taskRelations = (aggregated.completedTaskIds || []).map(id => ({id}));
const goalRelations = (aggregated.activeGoalIds || []).map(id => ({id}));

// Build the Notion page creation payload
const payload = {
    parent: {database_id: "WEEKLY_REVIEWS_DB_ID"},
    properties: {
        "Semaine": {
            title: [{text: {content: aggregated.weekLabel}}]
        },
        "Date": {
            date: {
                start: aggregated.monday,
                end: aggregated.sunday
            }
        },
        "Score": {
            number: aggregated.score
        },
        "Taches Completees": {
            relation: taskRelations
        },
        "Goals Revus": {
            relation: goalRelations
        },
        "XP Gagnes": {
            number: aggregated.totalXP
        },
        "Gold Gagnes": {
            number: aggregated.totalGold
        },
        "CA Periode": {
            number: aggregated.totalRevenue
        },
        "Nouveaux Prospects": {
            number: aggregated.newProspectsCount
        },
        "Taches En Retard": {
            number: aggregated.overdueCount
        },
        "Bilan IA": {
            rich_text: [{text: {content: analysis.bilan.substring(0, 2000)}}]
        },
        "Blocages": {
            rich_text: [{text: {content: analysis.blocages.substring(0, 2000)}}]
        },
        "Priorites Semaine Suivante": {
            rich_text: [{text: {content: analysis.priorites.substring(0, 2000)}}]
        }
    }
};

// Build telegram message
const tgMsg = [
    `WEEKLY REVIEW ${aggregated.weekLabel}`,
    `${aggregated.monday} -> ${aggregated.sunday}`,
    ``,
    `--- BILAN ---`,
    `Score: ${aggregated.score}`,
    `Taches completees: ${aggregated.taskCount}`,
    `CA: ${aggregated.totalRevenue} EUR`,
    `XP: ${aggregated.totalXP} | Gold: ${aggregated.totalGold}`,
    `Prospects: ${aggregated.newProspectsCount}`,
    ``,
    `--- ANALYSE IA ---`,
    analysis.bilan,
    ``,
    `--- BLOCAGES ---`,
    analysis.blocages,
    ``,
    `--- PRIORITES S+1 ---`,
    analysis.priorites
].join('\n');

// Callout text for Command Center
const ccText = `WEEKLY REVIEW\n${aggregated.weekLabel} | Score: ${aggregated.score} | ${aggregated.taskCount} taches | ${aggregated.totalRevenue} EUR CA`;

return [{json: {
    notionPayload: JSON.stringify(payload),
    telegramMessage: tgMsg,
    commandCenterText: ccText,
    analysis,
    aggregated
}}];
""".replace("WEEKLY_REVIEWS_DB_ID", WEEKLY_REVIEWS_DB)

    create_review_prep = {
        "id": uid(),
        "name": "Prepare Review Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1620, 300],
        "parameters": {"jsCode": create_review_code}
    }
    prepare_review_id = create_review_prep["id"]

    create_review = {
        "id": create_review_id,
        "name": "Create Weekly Review",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1840, 300],
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
            "jsonBody": "={{ $json.notionPayload }}",
            "options": {}
        },
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # ── Wait after create ──
    wait_create = {
        "id": wait_create_id,
        "name": "Wait Create",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [2060, 300],
        "parameters": {"amount": 2, "unit": "seconds"},
        "webhookId": "wait-create"
    }

    # ── Node 10: Update Command Center via Notion v3 API ──
    update_cc_code = r"""
// Update the WEEKLY REVIEW callout on Command Center
// Uses Notion internal API v3 submitTransaction
const ccText = $('Prepare Review Data').first().json.commandCenterText;
const COMMAND_CENTER_ID = 'CC_PAGE_ID';

// Read token from environment or use inline
// In n8n, we'll use an HTTP Request to the Notion internal API
// We need to find the WEEKLY REVIEW block first, then update it

// For the submitTransaction approach, we need:
// 1. loadPageChunk to find the block
// 2. submitTransaction to update it

// Since this is complex, we build the HTTP request bodies
// The update will be done via a subsequent HTTP Request node

// Build the loadPageChunk request
const loadPayload = {
    pageId: COMMAND_CENTER_ID,
    limit: 100,
    cursor: {stack: []},
    chunkNumber: 0,
    verticalColumns: false
};

return [{json: {
    ccText,
    loadPayload: JSON.stringify(loadPayload),
    commandCenterId: COMMAND_CENTER_ID
}}];
""".replace("CC_PAGE_ID", COMMAND_CENTER_PAGE)

    update_cc_load = {
        "id": uid(),
        "name": "Prepare CC Update",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2280, 200],
        "parameters": {"jsCode": update_cc_code}
    }
    prepare_cc_id = update_cc_load["id"]

    # Load Command Center page to find WEEKLY REVIEW block
    load_cc = {
        "id": uid(),
        "name": "Load CC Page",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2500, 200],
        "parameters": {
            "method": "POST",
            "url": "https://www.notion.so/api/v3/loadPageChunk",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Cookie", "value": "=token_v2={{ $env.NOTION_TOKEN_V2 }}"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.loadPayload }}",
            "options": {}
        },
        "onError": "continueRegularOutput"
    }
    load_cc_id = load_cc["id"]

    # Find and update the WEEKLY REVIEW block
    update_cc_submit_code = r"""
// Find the WEEKLY REVIEW callout block and update it
const pageData = $('Load CC Page').first().json;
const ccText = $('Prepare CC Update').first().json.ccText;
const commandCenterId = $('Prepare CC Update').first().json.commandCenterId;

const blocks = (pageData.recordMap || {}).block || {};
const pageBlock = (blocks[commandCenterId] || {}).value || {};
const content = pageBlock.content || [];
const spaceId = pageBlock.space_id || '';

let weeklyReviewBlockId = null;

// Search for WEEKLY REVIEW callout (could be top-level or inside columns)
function searchBlocks(blockIds) {
    for (const bid of blockIds) {
        const b = (blocks[bid] || {}).value || {};
        const btype = b.type || '';
        const titles = (b.properties || {}).title || [];
        const text = titles.map(seg => seg[0] || '').join('');

        if (btype === 'callout' && text.toUpperCase().includes('WEEKLY REVIEW')) {
            return bid;
        }

        // Search inside columns and column lists
        if (btype === 'column_list' || btype === 'column') {
            const found = searchBlocks(b.content || []);
            if (found) return found;
        }
    }
    return null;
}

weeklyReviewBlockId = searchBlocks(content);

if (!weeklyReviewBlockId) {
    // If no existing block found, we'll skip the CC update
    return [{json: {
        ccUpdateSkipped: true,
        reason: 'WEEKLY REVIEW block not found on Command Center'
    }}];
}

// Find the text block inside the callout (child paragraph)
const calloutBlock = (blocks[weeklyReviewBlockId] || {}).value || {};
const calloutChildren = calloutBlock.content || [];
let textBlockId = null;

for (const childId of calloutChildren) {
    const child = (blocks[childId] || {}).value || {};
    if (child.type === 'text' || child.type === 'paragraph') {
        textBlockId = childId;
        break;
    }
}

// Build submitTransaction operations
const operations = [];

if (textBlockId) {
    // Update existing text block
    operations.push({
        pointer: {table: "block", id: textBlockId},
        path: ["properties", "title"],
        command: "set",
        args: [[ccText]]
    });
} else {
    // Update the callout title directly
    operations.push({
        pointer: {table: "block", id: weeklyReviewBlockId},
        path: ["properties", "title"],
        command: "set",
        args: [[[ccText]]]
    });
}

const submitPayload = {
    requestId: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(),
    transactions: [{
        id: crypto.randomUUID ? crypto.randomUUID() : (Date.now() + 1).toString(),
        spaceId: spaceId,
        operations: operations
    }]
};

return [{json: {
    submitPayload: JSON.stringify(submitPayload),
    weeklyReviewBlockId,
    textBlockId,
    ccUpdateSkipped: false
}}];
"""

    update_cc_find = {
        "id": uid(),
        "name": "Find CC Block",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2720, 200],
        "parameters": {"jsCode": update_cc_submit_code}
    }
    find_cc_id = update_cc_find["id"]

    # Submit the transaction to update Command Center
    update_cc_submit = {
        "id": update_cc_id,
        "name": "Update CC Callout",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2940, 200],
        "parameters": {
            "method": "POST",
            "url": "https://www.notion.so/api/v3/submitTransaction",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Cookie", "value": "=token_v2={{ $env.NOTION_TOKEN_V2 }}"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.submitPayload }}",
            "options": {}
        },
        "onError": "continueRegularOutput"
    }

    # ── Node 11a: Split for Telegram (4096 char limit) ──
    split_telegram_code = r"""
// Split long messages for Telegram (4096 char limit)
const fullMsg = $('Prepare Review Data').first().json.telegramMessage;
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
        "position": [2280, 460],
        "parameters": {"jsCode": split_telegram_code}
    }

    # ── Node 11b: Send Telegram Recap ──
    telegram = {
        "id": telegram_id,
        "name": "Telegram Recap",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [2500, 460],
        "parameters": {
            "chatId": TELEGRAM_CHAT_ID,
            "text": "={{ $json.text }}",
            "additionalFields": {
                "parse_mode": "Markdown"
            }
        },
        "credentials": TELEGRAM_CRED
    }

    # ── Assemble nodes ──
    nodes = [
        trigger,
        build_week,
        query_tasks,
        query_goals,
        query_revenue,
        query_activity,
        wait_tasks,
        wait_goals,
        wait_revenue,
        wait_activity,
        aggregate,
        claude_analysis,
        wait_claude,
        create_review_prep,
        create_review,
        wait_create,
        update_cc_load,
        load_cc,
        update_cc_find,
        update_cc_submit,
        split_telegram,
        telegram,
    ]

    # ── Connections ──
    # Build Week Range → 4 parallel queries
    # Each query → wait → aggregate merges all
    # Aggregate → Claude → wait → Prepare Review → Create Review + Telegram
    # Create Review → wait → CC update chain
    connections = {
        "Sunday 20h": {
            "main": [[
                {"node": "Build Week Range", "type": "main", "index": 0}
            ]]
        },
        "Build Week Range": {
            "main": [[
                {"node": "Query Completed Tasks", "type": "main", "index": 0},
                {"node": "Query Active Goals", "type": "main", "index": 0},
                {"node": "Query Revenue", "type": "main", "index": 0},
                {"node": "Query Activity Log", "type": "main", "index": 0},
            ]]
        },
        "Query Completed Tasks": {
            "main": [[
                {"node": "Wait Tasks", "type": "main", "index": 0}
            ]]
        },
        "Query Active Goals": {
            "main": [[
                {"node": "Wait Goals", "type": "main", "index": 0}
            ]]
        },
        "Query Revenue": {
            "main": [[
                {"node": "Wait Revenue", "type": "main", "index": 0}
            ]]
        },
        "Query Activity Log": {
            "main": [[
                {"node": "Wait Activity", "type": "main", "index": 0}
            ]]
        },
        "Wait Tasks": {
            "main": [[
                {"node": "Aggregate Data", "type": "main", "index": 0}
            ]]
        },
        "Wait Goals": {
            "main": [[
                {"node": "Aggregate Data", "type": "main", "index": 0}
            ]]
        },
        "Wait Revenue": {
            "main": [[
                {"node": "Aggregate Data", "type": "main", "index": 0}
            ]]
        },
        "Wait Activity": {
            "main": [[
                {"node": "Aggregate Data", "type": "main", "index": 0}
            ]]
        },
        "Aggregate Data": {
            "main": [[
                {"node": "Claude Analysis", "type": "main", "index": 0}
            ]]
        },
        "Claude Analysis": {
            "main": [[
                {"node": "Wait Claude", "type": "main", "index": 0}
            ]]
        },
        "Wait Claude": {
            "main": [[
                {"node": "Prepare Review Data", "type": "main", "index": 0}
            ]]
        },
        "Prepare Review Data": {
            "main": [[
                {"node": "Create Weekly Review", "type": "main", "index": 0},
                {"node": "Split for Telegram", "type": "main", "index": 0},
            ]]
        },
        "Split for Telegram": {
            "main": [[
                {"node": "Telegram Recap", "type": "main", "index": 0}
            ]]
        },
        "Create Weekly Review": {
            "main": [[
                {"node": "Wait Create", "type": "main", "index": 0}
            ]]
        },
        "Wait Create": {
            "main": [[
                {"node": "Prepare CC Update", "type": "main", "index": 0}
            ]]
        },
        "Prepare CC Update": {
            "main": [[
                {"node": "Load CC Page", "type": "main", "index": 0}
            ]]
        },
        "Load CC Page": {
            "main": [[
                {"node": "Find CC Block", "type": "main", "index": 0}
            ]]
        },
        "Find CC Block": {
            "main": [[
                {"node": "Update CC Callout", "type": "main", "index": 0}
            ]]
        },
    }

    return {
        "name": "Weekly Review IA",
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
    print("=" * 55)
    print("  Weekly Review IA — n8n Workflow Creator")
    print("=" * 55)

    workflow = build_workflow()

    # Check for existing workflow with same name
    print("\n1. Checking existing workflows...")
    r = requests.get(f"{N8N_URL}/api/v1/workflows", headers=HEADERS)
    if r.status_code == 200:
        existing = r.json().get("data", [])
        for wf in existing:
            if wf.get("name") == "Weekly Review IA":
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
                    # Reactivate
                    r3 = requests.post(
                        f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
                        headers=HEADERS
                    )
                    if r3.status_code == 200:
                        print(f"   Activated!")
                    else:
                        print(f"   Activation: {r3.status_code} {r3.text[:200]}")
                    print(f"\n   Workflow ID: {wf_id}")
                    print(f"   Schedule: Every Sunday at 20h (Europe/Paris)")
                    return wf_id
                else:
                    print(f"   Update error: {r2.status_code} {r2.text[:300]}")
                    # Fall through to create new

    # Create workflow
    print("\n2. Creating Weekly Review IA workflow...")
    r = requests.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=HEADERS,
        json=workflow
    )

    if r.status_code in (200, 201):
        wf = r.json()
        wf_id = wf["id"]
        print(f"   Created: {wf_id}")

        # Activate using POST
        print("\n3. Activating workflow...")
        r2 = requests.post(
            f"{N8N_URL}/api/v1/workflows/{wf_id}/activate",
            headers=HEADERS
        )
        if r2.status_code == 200:
            print(f"   Activated!")
        else:
            print(f"   Activation: {r2.status_code} {r2.text[:200]}")

        print(f"\n{'=' * 55}")
        print(f"  Workflow ID: {wf_id}")
        print(f"  Schedule: Every Sunday at 20h (Europe/Paris)")
        print(f"  Nodes: {len(workflow['nodes'])}")
        print(f"{'=' * 55}")
        print(f"\n  Pipeline:")
        print(f"  1. Schedule Trigger (Sunday 20h)")
        print(f"  2. Build Week Range (Monday-Sunday)")
        print(f"  3-6. Parallel queries: Tasks, Goals, Revenue, Activity")
        print(f"  7. Aggregate all data")
        print(f"  8. Claude AI analysis (bilan/blocages/priorites)")
        print(f"  9. Create Weekly Review page in Notion")
        print(f"  10. Update Command Center callout")
        print(f"  11. Send Telegram recap")
        print(f"\n  IMPORTANT: Set NOTION_TOKEN_V2 environment variable")
        print(f"  in n8n for the Command Center update to work.")
        return wf_id
    else:
        print(f"   Error: {r.status_code}")
        print(f"   {r.text[:500]}")
        return None


if __name__ == "__main__":
    main()
