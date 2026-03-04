#!/usr/bin/env python3
"""
Fix Gamification System — Complete overhaul
============================================
Fixes:
  1. Solo Leveling: Build Log Entry writes XP/Gold/HP + Judgment detects completions via Activity Log
  2. Solo Leveling: Updates Last Completed + Streak Days on habits after judgment
  3. NEW workflow: Task Completion Rewards (15min CRON, XP/Gold/HP for completed tasks)
  4. Backfill: Patch existing Activity Log entries that have XP=0

Usage:
  python3 fix_gamification_complete.py               # Deploy all fixes
  python3 fix_gamification_complete.py --dry-run      # Preview changes without deploying
  python3 fix_gamification_complete.py --fix 1        # Deploy only fix 1
  python3 fix_gamification_complete.py --fix 1,2,3    # Deploy fixes 1, 2, 3
  python3 fix_gamification_complete.py --fix 4 --dry-run  # Preview backfill only
"""

import argparse
import json
import requests
import time
import sys
import copy

# =====================================================
# CONFIG
# =====================================================
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = "***N8N_API_KEY***"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}
ALLOWED_PUT_FIELDS = ['name', 'nodes', 'connections', 'settings', 'staticData']

# Notion credentials (for n8n nodes)
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}
CHRIS_CHAT_ID = "7342622615"

# Database IDs (no dashes for API URLs)
HABITS_DB = "305da200b2d68139b19fd2a0d46cf7e6"
ACTIVITY_LOG_DB = "305da200b2d6819f915fd35f51386aa8"
TASKS_DB = "305da200b2d68145bc16eaee02925a14"
LEADERBOARD_COLLECTION = "305da200b2d681f181450006fd7b000"

# Page IDs
CHRIS_LEADERBOARD_PAGE = "310da200-b2d6-8005-aeb9-e410436b48cf"

# Workflow IDs
SOLO_LEVELING_ID = "q2QmGHq17YIxzHzy"

# =====================================================
# n8n API HELPERS
# =====================================================
def get_workflow(wf_id):
    r = requests.get(f"{N8N_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def put_workflow(wf_id, wf_data):
    body = {k: wf_data[k] for k in ALLOWED_PUT_FIELDS if k in wf_data}
    r = requests.put(f"{N8N_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=body)
    if r.status_code != 200:
        print(f"  PUT error: {r.status_code} - {r.text[:500]}")
    r.raise_for_status()
    return r.json()


def create_workflow(wf_data):
    r = requests.post(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, json=wf_data)
    if r.status_code not in (200, 201):
        print(f"  POST error: {r.status_code} - {r.text[:500]}")
    r.raise_for_status()
    return r.json()


def activate_workflow(wf_id):
    r = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS)
    return r.status_code == 200


def deactivate_workflow(wf_id):
    r = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/deactivate", headers=HEADERS)
    return r.status_code == 200


def find_node(wf, name):
    for node in wf.get('nodes', []):
        if node['name'] == name:
            return node
    return None


def deploy_workflow(wf_id, wf_data, name):
    """Deactivate, update, reactivate a workflow."""
    print(f"\n  Deploying: {name}")

    print("    1. Deactivating...")
    deactivate_workflow(wf_id)
    time.sleep(1)

    print("    2. Updating workflow...")
    result = put_workflow(wf_id, wf_data)
    time.sleep(1)

    print("    3. Activating...")
    ok = activate_workflow(wf_id)
    if ok:
        print("    Active: True")
    else:
        print("    WARNING: Activation failed")
    return ok


# =====================================================
# Notion API (for backfill - direct API calls)
# =====================================================
NOTION_API = "https://api.notion.com/v1"
NOTION_TOKEN = None


def load_notion_token():
    global NOTION_TOKEN
    if NOTION_TOKEN:
        return NOTION_TOKEN
    try:
        with open("/home/claude-agent/.notion-token", "r") as f:
            NOTION_TOKEN = f.read().strip()
    except FileNotFoundError:
        print("  WARNING: ~/.notion-token not found, using n8n webhook fallback")
        NOTION_TOKEN = None
    return NOTION_TOKEN


def notion_headers():
    """Headers for Notion API calls via n8n webhook proxy."""
    return {
        "Content-Type": "application/json"
    }


# Use n8n webhook to proxy Notion API calls (has the official token)
N8N_NOTION_QUERY_URL = f"{N8N_URL}/webhook/notion-query"


def notion_query_db(db_id, filter_obj=None, sorts=None, page_size=100):
    """Query a Notion DB via n8n webhook proxy (uses n8n's Notion credential)."""
    body = {"database_id": db_id, "page_size": page_size}
    if filter_obj:
        body["filter"] = filter_obj
    if sorts:
        body["sorts"] = sorts
    # Use n8n Notion Query Helper webhook
    r = requests.post(
        f"{N8N_URL}/webhook/notion-query-db",
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=30
    )
    if r.status_code != 200:
        # Fallback: try creating a temporary execution via n8n API
        print(f"    Webhook not available ({r.status_code}), using direct n8n execution...")
        return notion_query_via_n8n_exec(db_id, filter_obj, sorts, page_size)
    return r.json().get("results", [])


def notion_query_via_n8n_exec(db_id, filter_obj=None, sorts=None, page_size=100):
    """Fallback: query Notion DB by creating & executing a temporary n8n workflow."""
    query_body = {"page_size": page_size}
    if filter_obj:
        query_body["filter"] = filter_obj
    if sorts:
        query_body["sorts"] = sorts

    # Create a minimal workflow that queries Notion
    wf = {
        "name": "__temp_notion_query",
        "nodes": [
            {
                "parameters": {},
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [0, 0],
                "id": "tq-trigger",
                "name": "Manual Trigger"
            },
            {
                "parameters": {
                    "method": "POST",
                    "url": f"https://api.notion.com/v1/databases/{db_id}/query",
                    "authentication": "predefinedCredentialType",
                    "nodeCredentialType": "notionApi",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": json.dumps(query_body),
                    "options": {}
                },
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [300, 0],
                "id": "tq-query",
                "name": "Query DB",
                "credentials": NOTION_CRED
            }
        ],
        "connections": {
            "Manual Trigger": {"main": [[{"node": "Query DB", "type": "main", "index": 0}]]}
        },
        "settings": {"executionOrder": "v1"}
    }

    # Create, execute, get results, delete
    r = requests.post(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, json=wf)
    if r.status_code not in (200, 201):
        print(f"    Failed to create temp workflow: {r.status_code}")
        return []
    wf_id = r.json()["id"]

    try:
        r = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/execute", headers=HEADERS, json={})
        if r.status_code != 200:
            print(f"    Failed to execute temp workflow: {r.status_code}")
            return []

        exec_data = r.json().get("data", {})
        result_data = exec_data.get("resultData", {}).get("runData", {})
        query_output = result_data.get("Query DB", [{}])
        if query_output and len(query_output) > 0:
            items = query_output[0].get("data", {}).get("main", [[]])
            if items and len(items) > 0 and len(items[0]) > 0:
                return items[0][0].get("json", {}).get("results", [])
        return []
    finally:
        # Clean up temp workflow
        requests.delete(f"{N8N_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)


def notion_patch_page(page_id, properties):
    """Patch a Notion page via a temporary n8n execution."""
    wf = {
        "name": "__temp_notion_patch",
        "nodes": [
            {
                "parameters": {},
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [0, 0],
                "id": "tp-trigger",
                "name": "Manual Trigger"
            },
            {
                "parameters": {
                    "method": "PATCH",
                    "url": f"https://api.notion.com/v1/pages/{page_id}",
                    "authentication": "predefinedCredentialType",
                    "nodeCredentialType": "notionApi",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": json.dumps({"properties": properties}),
                    "options": {}
                },
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [300, 0],
                "id": "tp-patch",
                "name": "Patch Page",
                "credentials": NOTION_CRED
            }
        ],
        "connections": {
            "Manual Trigger": {"main": [[{"node": "Patch Page", "type": "main", "index": 0}]]}
        },
        "settings": {"executionOrder": "v1"}
    }

    r = requests.post(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, json=wf)
    if r.status_code not in (200, 201):
        print(f"    Failed to create temp patch workflow: {r.status_code}")
        return False
    wf_id = r.json()["id"]

    try:
        r = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/execute", headers=HEADERS, json={})
        return r.status_code == 200
    finally:
        requests.delete(f"{N8N_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)


# =====================================================
# FIX 1 & 2: Solo Leveling — Full Rebuild
# =====================================================
def fix_solo_leveling(dry_run=False):
    """
    Rebuild Solo Leveling to:
    - Fetch today's Activity Log entries to detect completed habits
    - Calculate XP/Gold/HP properly
    - Write XP/Gold/HP to the Build Log Entry
    - Update Last Completed + Streak Days on completed habits
    """
    print("\n" + "=" * 60)
    print("FIX 1+2: Solo Leveling — Activity Log Detection + XP/Gold/HP")
    print("=" * 60)

    # --- Node definitions ---

    trigger = {
        "parameters": {
            "rule": {"interval": [{"triggerAtHour": 23, "triggerAtMinute": 45}]}
        },
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 0],
        "id": "sl-trigger",
        "name": "23h45 - Judgment Time"
    }

    fetch_habits = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{HABITS_DB}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({
                "filter": {
                    "property": "Frequency",
                    "select": {"equals": "1 - Daily"}
                }
            }),
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [300, 0],
        "id": "sl-fetch-habits",
        "name": "Fetch Daily Habits",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput",
        "retryOnFail": True,
        "maxTries": 2,
        "waitBetweenTries": 2000
    }

    wait1 = {
        "parameters": {"amount": 1, "unit": "seconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [500, 0],
        "id": "sl-wait1",
        "name": "Wait 1s"
    }

    # NEW: Fetch today's Activity Log entries to detect hand-ins
    fetch_today_activities = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{ACTIVITY_LOG_DB}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ filter: { property: "Date", date: { on_or_after: new Date(new Date().getTime() + 3600000).toISOString().split("T")[0] } }, sorts: [{ property: "Date", direction: "descending" }], page_size: 100 }) }}',
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [700, 0],
        "id": "sl-fetch-activities",
        "name": "Fetch Today Activities",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    wait2 = {
        "parameters": {"amount": 1, "unit": "seconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [900, 0],
        "id": "sl-wait2",
        "name": "Wait 1s (2)"
    }

    fetch_player = {
        "parameters": {
            "method": "GET",
            "url": f"https://api.notion.com/v1/pages/{CHRIS_LEADERBOARD_PAGE.replace('-', '')}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1100, 0],
        "id": "sl-player",
        "name": "Fetch Player Stats",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # --- Judgment Engine: now cross-references Activity Log ---
    judgment_code = r"""// Solo Leveling System - Quest Judgment (v2 - Activity Log Detection)
// Detects completed habits via Activity Log entries (Hand In button)

const habitsResponse = $('Fetch Daily Habits').first().json;
const activitiesResponse = $('Fetch Today Activities').first().json;
const playerResponse = $json; // from Fetch Player Stats

// Handle API errors
if (habitsResponse.error || habitsResponse.object === 'error') {
  return [{json: {
    date: new Date().toISOString().split('T')[0],
    message: 'SYSTEM ERROR: Impossible de recuperer les habits. ' + (habitsResponse.message || ''),
    error: true, xpEarned: 0, goldLost: 0, hpGained: 0, hpLost: 0,
    completed: 0, failed: 0, completedHabitIds: [], failedHabitIds: []
  }}];
}

const habits = habitsResponse.results || [];
const activities = (activitiesResponse.results || []);
const now = new Date(new Date().getTime() + 3600000); // UTC+1
const today = now.toISOString().split('T')[0];

// Build set of habit IDs that appear in today's Activity Log entries (via Habits relation)
const completedHabitIdSet = new Set();
for (const act of activities) {
  const habitRels = act.properties?.Habits?.relation || [];
  for (const rel of habitRels) {
    completedHabitIdSet.add(rel.id);
  }
}

const results = [];
let completedCount = 0;
let failedCount = 0;
let totalXP = 0;
let totalGoldLost = 0;
let totalHpGained = 0;
let totalHpLost = 0;
let maxStreak = 0;
const completedHabitIds = [];
const failedHabitIds = [];

for (const habit of habits) {
  const props = habit.properties || {};
  const habitId = habit.id;
  const lastCompleted = props['Last Completed']?.date?.start || null;
  const habitName = props['Name']?.title?.[0]?.plain_text || 'Unknown Quest';
  const difficulty = props['Difficulty']?.select?.name || '1 - Easy';
  const streakDays = props['Streak Days']?.number || 0;

  const xpMap = { '1 - Easy': 10, '2 - Moderate': 25, '3 - Hard': 50 };
  const baseXP = xpMap[difficulty] || 10;

  // Check completion: either Last Completed == today, or habit ID in today's Activity Log
  const completed = (lastCompleted === today) || completedHabitIdSet.has(habitId);

  if (completed) {
    completedCount++;
    completedHabitIds.push(habitId);
    const streakBonus = Math.floor(streakDays / 7) * 5;
    const xpEarned = baseXP + streakBonus;
    totalXP += xpEarned;
    totalHpGained += 2; // +2 HP per completed habit
    if (streakDays > maxStreak) maxStreak = streakDays;
    results.push({
      quest: habitName, habitId, status: 'COMPLETED',
      xp: xpEarned, streak: streakDays + 1, penalty: 0
    });
  } else {
    failedCount++;
    failedHabitIds.push(habitId);
    const goldPenalty = baseXP * 2;
    totalGoldLost += goldPenalty;
    totalHpLost += 5; // -5 HP per failed habit
    results.push({
      quest: habitName, habitId, status: 'FAILED',
      xp: 0, streak: 0, penalty: goldPenalty
    });
  }
}

// Perfect day bonus
const allCompleted = failedCount === 0;
const total = completedCount + failedCount;
if (allCompleted && total > 0) {
  totalXP += Math.floor(totalXP * 0.1);
}

// Streak milestones
const streakMilestones = [7, 14, 21, 30, 50, 100];

// Player stats for level-up detection
const playerProps = playerResponse.properties || {};
function getFormula(p) {
  if (!p) return null;
  if (p.type === 'formula') {
    if (p.formula?.type === 'number') return p.formula.number;
    if (p.formula?.type === 'string') return p.formula.string;
  }
  if (p.type === 'number') return p.number;
  return null;
}
const currentLevel = getFormula(playerProps['Level']);
const currentGold = getFormula(playerProps['Gold']);
const currentHP = getFormula(playerProps['Health']);

// Build Telegram message
let msg = '<b>SOLO LEVELING SYSTEM</b>\n';
msg += '<b>Daily Quest Judgment</b>\n';
msg += `Date: ${today}\n\n`;

if (allCompleted && total > 0) {
  msg += 'QUEST COMPLETE - All daily quests fulfilled.\n\n';
} else if (total === 0) {
  msg += 'NO QUESTS FOUND - Check your Habits database.\n\n';
} else {
  msg += `QUEST FAILED - ${failedCount}/${total} quest(s) incomplete.\n\n`;
}

for (const r of results) {
  if (r.status === 'COMPLETED') {
    msg += `  ${r.quest} | +${r.xp} XP | Streak: ${r.streak}j\n`;
  } else {
    msg += `  ${r.quest} | -${r.penalty} Gold | -5 HP | Streak RESET\n`;
  }
}

msg += `\n<b>SUMMARY</b>\n`;
msg += `Quests: ${completedCount}/${total}\n`;
msg += `XP Earned: +${totalXP}\n`;
msg += `Gold Lost: -${totalGoldLost}\n`;
msg += `HP: +${totalHpGained} / -${totalHpLost}\n`;
if (currentLevel != null) msg += `Level: ${currentLevel} | Gold: ${currentGold} | HP: ${currentHP}\n`;

for (const r of results) {
  if (r.status === 'COMPLETED' && streakMilestones.includes(r.streak)) {
    msg += `\nSTREAK MILESTONE: ${r.quest} - ${r.streak} DAYS!\n`;
  }
}

if (allCompleted && total > 0) {
  msg += `\nPerfect Day! +${Math.floor(totalXP * 0.1)} bonus XP\n`;
}

if (!allCompleted && failedCount > 0) {
  msg += `\nThe System does not forgive. Your streaks have been reset.\n`;
}

// Level-up detection
const staticData = $getWorkflowStaticData('global');
const prevLevel = staticData.lastLevel || 0;
if (currentLevel != null && prevLevel > 0 && currentLevel > prevLevel) {
  msg += `\n\nLEVEL UP! ${prevLevel} -> ${currentLevel}\nYou have ascended, Hunter.\n`;
}
if (currentLevel != null) {
  staticData.lastLevel = currentLevel;
}

return [{json: {
  date: today,
  message: msg,
  xpEarned: totalXP,
  goldLost: totalGoldLost,
  hpGained: totalHpGained,
  hpLost: totalHpLost,
  completed: completedCount,
  failed: failedCount,
  total,
  allCompleted,
  results,
  completedHabitIds,
  failedHabitIds,
  error: false,
  logEntry: {
    timestamp: new Date().toISOString(),
    type: 'DAILY_JUDGMENT',
    checksum: Buffer.from(JSON.stringify(results) + new Date().toISOString()).toString('base64')
  }
}}];"""

    # --- Build Log Entry: now includes XP/Gold/HP + Leaderboard relation ---
    log_code = r"""const d = $json;
if (d.error) {
  return [{json: {skip: true}}];
}

// Calculate net HP: gained from completed - lost from failed
const netHP = (d.hpGained || 0) - (d.hpLost || 0);

const logBody = {
  parent: { database_id: '""" + ACTIVITY_LOG_DB + r"""' },
  properties: {
    Name: { title: [{ text: { content: d.date + ' - Daily Judgment (' + d.completed + '/' + d.total + ')' } }] },
    Date: { date: { start: d.date + 'T23:45:00.000+01:00' } },
    XP: { number: d.xpEarned || 0 },
    Gold: { number: d.goldLost ? -d.goldLost : 0 },
    HP: { number: netHP },
    Leaderboard: { relation: [{ id: '""" + CHRIS_LEADERBOARD_PAGE + r"""' }] }
  }
};

return [{json: {logBody: JSON.stringify(logBody)}}];"""

    build_log = {
        "parameters": {"jsCode": log_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1500, -200],
        "id": "sl-buildlog",
        "name": "Build Log Entry"
    }

    log_node = {
        "parameters": {
            "method": "POST",
            "url": "https://api.notion.com/v1/pages",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.logBody }}",
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1800, -200],
        "id": "sl-log",
        "name": "Log to Activity Log",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    send_telegram = {
        "parameters": {
            "chatId": CHRIS_CHAT_ID,
            "text": "={{ $('Judgment Engine v2').first().json.message }}",
            "additionalFields": {
                "appendAttribution": False,
                "parse_mode": "HTML"
            }
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [1500, 200],
        "id": "sl-telegram",
        "name": "Send Verdict",
        "credentials": TELEGRAM_CRED
    }

    # --- NEW: Update Completed Habits (Last Completed + Streak Days) ---
    update_habits_code = r"""const d = $('Judgment Engine v2').first().json;
if (d.error || !d.results || d.results.length === 0) {
  return [{json: {skip: true, updates: []}}];
}

const today = d.date;
const updates = [];

for (const r of d.results) {
  if (r.status === 'COMPLETED' && r.habitId) {
    updates.push({
      habitId: r.habitId,
      quest: r.quest,
      newStreak: r.streak,
      lastCompleted: today
    });
  } else if (r.status === 'FAILED' && r.habitId) {
    // Reset streak to 0 for failed habits
    updates.push({
      habitId: r.habitId,
      quest: r.quest,
      newStreak: 0,
      lastCompleted: null // don't update Last Completed for failed
    });
  }
}

return [{json: {updates, total: updates.length}}];"""

    build_habit_updates = {
        "parameters": {"jsCode": update_habits_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1500, 0],
        "id": "sl-build-habit-updates",
        "name": "Build Habit Updates"
    }

    # SplitInBatches to iterate over habit updates
    split_habits = {
        "parameters": {
            "batchSize": 1,
            "options": {}
        },
        "type": "n8n-nodes-base.splitInBatches",
        "typeVersion": 3,
        "position": [1800, 0],
        "id": "sl-split-habits",
        "name": "Split Habit Updates"
    }

    # Code node to extract current item for the HTTP Request
    extract_habit_update = {
        "parameters": {
            "jsCode": r"""const allUpdates = $('Build Habit Updates').first().json.updates;
const idx = $('Split Habit Updates').first().json._batchIndex || 0;
const u = allUpdates[idx];
if (!u) return [{json: {skip: true}}];

const props = {
  'Streak Days': { number: u.newStreak }
};
if (u.lastCompleted) {
  props['Last Completed'] = { date: { start: u.lastCompleted } };
}

return [{json: {
  habitId: u.habitId,
  quest: u.quest,
  patchBody: JSON.stringify({ properties: props })
}}];"""
        },
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2000, 0],
        "id": "sl-extract-habit",
        "name": "Extract Habit Update"
    }

    # PATCH each habit
    patch_habit = {
        "parameters": {
            "method": "PATCH",
            "url": "=https://api.notion.com/v1/pages/{{ $json.habitId }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.patchBody }}",
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2200, 0],
        "id": "sl-patch-habit",
        "name": "Update Habit",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    wait_habit = {
        "parameters": {"amount": 500, "unit": "milliseconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [2400, 0],
        "id": "sl-wait-habit",
        "name": "Wait 500ms"
    }

    judgment = {
        "parameters": {"jsCode": judgment_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1300, 0],
        "id": "sl-judgment",
        "name": "Judgment Engine v2"
    }

    nodes = [
        trigger, fetch_habits, wait1, fetch_today_activities, wait2,
        fetch_player, judgment,
        build_log, log_node, send_telegram,
        build_habit_updates, split_habits, extract_habit_update, patch_habit, wait_habit
    ]

    connections = {
        "23h45 - Judgment Time": {"main": [
            [{"node": "Fetch Daily Habits", "type": "main", "index": 0}]
        ]},
        "Fetch Daily Habits": {"main": [
            [{"node": "Wait 1s", "type": "main", "index": 0}]
        ]},
        "Wait 1s": {"main": [
            [{"node": "Fetch Today Activities", "type": "main", "index": 0}]
        ]},
        "Fetch Today Activities": {"main": [
            [{"node": "Wait 1s (2)", "type": "main", "index": 0}]
        ]},
        "Wait 1s (2)": {"main": [
            [{"node": "Fetch Player Stats", "type": "main", "index": 0}]
        ]},
        "Fetch Player Stats": {"main": [
            [{"node": "Judgment Engine v2", "type": "main", "index": 0}]
        ]},
        "Judgment Engine v2": {"main": [
            [
                {"node": "Build Log Entry", "type": "main", "index": 0},
                {"node": "Send Verdict", "type": "main", "index": 0},
                {"node": "Build Habit Updates", "type": "main", "index": 0}
            ]
        ]},
        "Build Log Entry": {"main": [
            [{"node": "Log to Activity Log", "type": "main", "index": 0}]
        ]},
        "Build Habit Updates": {"main": [
            [{"node": "Split Habit Updates", "type": "main", "index": 0}]
        ]},
        "Split Habit Updates": {"main": [
            [{"node": "Extract Habit Update", "type": "main", "index": 0}],
            []  # done output
        ]},
        "Extract Habit Update": {"main": [
            [{"node": "Update Habit", "type": "main", "index": 0}]
        ]},
        "Update Habit": {"main": [
            [{"node": "Wait 500ms", "type": "main", "index": 0}]
        ]},
        "Wait 500ms": {"main": [
            [{"node": "Split Habit Updates", "type": "main", "index": 0}]
        ]}
    }

    wf_data = {
        "name": "Solo Leveling System - Daily Quest Check",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Paris",
            "saveManualExecutions": True
        }
    }

    if dry_run:
        print("  [DRY RUN] Would rebuild Solo Leveling workflow with:")
        print(f"    - {len(nodes)} nodes (was ~8, now includes Activity Log fetch + habit updates)")
        print("    - Judgment Engine v2: cross-references Activity Log for completion detection")
        print("    - Build Log Entry: writes XP, Gold (negative), HP (net) + Leaderboard relation")
        print("    - NEW: Build Habit Updates + Split + PATCH loop for Last Completed + Streak Days")
        return True

    return deploy_workflow(SOLO_LEVELING_ID, wf_data, "Solo Leveling v2")


# =====================================================
# FIX 3: Task Completion Rewards (NEW WORKFLOW)
# =====================================================
def create_task_completion_workflow(dry_run=False):
    """
    New workflow: every 15min, find tasks marked Complete this week,
    skip already-rewarded ones (have Log relation), calculate XP/Gold/HP,
    create Activity Log entry, notify via Telegram.
    """
    print("\n" + "=" * 60)
    print("FIX 3: Task Completion Rewards (NEW WORKFLOW)")
    print("=" * 60)

    trigger = {
        "parameters": {
            "rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}
        },
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 0],
        "id": "tc-trigger",
        "name": "Every 15 Minutes"
    }

    # Query tasks: Status=Complete, Completed On >= start of week, Type != Project
    fetch_tasks_code = r"""const now = new Date(new Date().getTime() + 3600000); // UTC+1
const dayOfWeek = now.getDay();
const monday = new Date(now);
monday.setDate(now.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1));
const weekStart = monday.toISOString().split('T')[0];

const filter = {
  and: [
    { property: 'Status', status: { equals: 'Complete' } },
    { property: 'Completed On', date: { on_or_after: weekStart } },
    { property: 'Type', select: { does_not_equal: 'Project' } }
  ]
};

return [{json: {
  queryBody: JSON.stringify({
    filter,
    sorts: [{ property: 'Completed On', direction: 'descending' }],
    page_size: 50
  }),
  weekStart
}}];"""

    build_query = {
        "parameters": {"jsCode": fetch_tasks_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [250, 0],
        "id": "tc-build-query",
        "name": "Build Tasks Query"
    }

    fetch_tasks = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{TASKS_DB}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.queryBody }}",
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [500, 0],
        "id": "tc-fetch-tasks",
        "name": "Fetch Complete Tasks",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # Filter + calculate rewards
    calc_rewards_code = r"""const response = $json;
const tasks = (response.results || []);
const rewards = [];

for (const task of tasks) {
  const props = task.properties || {};

  // IDEMPOTENCE: skip if task already has a Log relation
  const logRel = props['Log']?.relation || [];
  if (logRel.length > 0) continue;

  const name = props['Name']?.title?.[0]?.plain_text || 'Unknown Task';
  const difficulty = props['Difficulty']?.select?.name || '2 - Moderate';
  const priority = props['Priority']?.select?.name || 'Medium';
  const revenueImpact = props['Revenue Impact']?.select?.name || '';
  const completedOn = props['Completed On']?.date?.start || new Date().toISOString().split('T')[0];

  // Base XP by difficulty
  const diffXP = { '1 - Easy': 15, '2 - Moderate': 35, '3 - Hard': 75 };
  let baseXP = diffXP[difficulty] || 35;

  // Priority multiplier
  const prioMult = { 'Critical': 3, 'High': 2, 'Medium': 1, 'Low': 0.5 };
  baseXP = Math.round(baseXP * (prioMult[priority] || 1));

  // Revenue Impact bonus
  let bonus = 0;
  if (revenueImpact.includes('Direct')) bonus = 50;
  else if (revenueImpact.includes('Indirect')) bonus = 20;

  const xp = baseXP + bonus;
  const gold = Math.round(xp * 0.5);
  const hp = Math.round(xp * 0.2);

  rewards.push({
    taskId: task.id,
    name,
    difficulty,
    priority,
    revenueImpact,
    completedOn,
    xp, gold, hp
  });
}

return [{json: {rewards, count: rewards.length}}];"""

    calc_rewards = {
        "parameters": {"jsCode": calc_rewards_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [750, 0],
        "id": "tc-calc-rewards",
        "name": "Calculate Rewards"
    }

    # Check if there are tasks to reward
    check_empty = {
        "parameters": {
            "jsCode": r"""const data = $json;
if (!data.rewards || data.rewards.length === 0) {
  return []; // stop execution — no items
}
return [{json: data}];"""
        },
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1000, 0],
        "id": "tc-check",
        "name": "Skip If Empty"
    }

    # Process each task: create Activity Log entry + link back
    split_tasks = {
        "parameters": {
            "batchSize": 1,
            "options": {}
        },
        "type": "n8n-nodes-base.splitInBatches",
        "typeVersion": 3,
        "position": [1250, 0],
        "id": "tc-split",
        "name": "Process Each Task"
    }

    # Build Activity Log entry for current task
    build_log_code = r"""const allRewards = $('Skip If Empty').first().json.rewards;
const idx = $('Process Each Task').first().json._batchIndex || 0;
const r = allRewards[idx];
if (!r) return [{json: {skip: true}}];

const logBody = {
  parent: { database_id: '""" + ACTIVITY_LOG_DB + r"""' },
  properties: {
    Name: { title: [{ text: { content: r.completedOn + ' - ' + r.name } }] },
    Date: { date: { start: r.completedOn + 'T12:00:00.000+01:00' } },
    XP: { number: r.xp },
    Gold: { number: r.gold },
    HP: { number: r.hp },
    Quests: { relation: [{ id: r.taskId }] },
    Leaderboard: { relation: [{ id: '""" + CHRIS_LEADERBOARD_PAGE + r"""' }] }
  }
};

return [{json: {
  logBody: JSON.stringify(logBody),
  taskId: r.taskId,
  name: r.name,
  xp: r.xp,
  gold: r.gold,
  hp: r.hp
}}];"""

    build_log_entry = {
        "parameters": {"jsCode": build_log_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1500, 0],
        "id": "tc-build-log",
        "name": "Build Log Entry"
    }

    # POST to create Activity Log entry
    create_log = {
        "parameters": {
            "method": "POST",
            "url": "https://api.notion.com/v1/pages",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $('Build Log Entry').first().json.logBody }}",
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1750, 0],
        "id": "tc-create-log",
        "name": "Create Activity Log",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    wait_after_create = {
        "parameters": {"amount": 1, "unit": "seconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [2000, 0],
        "id": "tc-wait-create",
        "name": "Wait 1s"
    }

    # Link back: PATCH the task with Log relation pointing to the new Activity Log entry
    link_back_code = r"""const newPageId = $('Create Activity Log').first().json.id;
const taskId = $('Build Log Entry').first().json.taskId;

if (!newPageId || !taskId) {
  return [{json: {skip: true}}];
}

const patchBody = {
  properties: {
    Log: { relation: [{ id: newPageId }] }
  }
};

return [{json: {
  taskId,
  patchBody: JSON.stringify(patchBody),
  logPageId: newPageId
}}];"""

    build_link_back = {
        "parameters": {"jsCode": link_back_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2250, 0],
        "id": "tc-build-link",
        "name": "Build Link Back"
    }

    patch_task = {
        "parameters": {
            "method": "PATCH",
            "url": "=https://api.notion.com/v1/pages/{{ $json.taskId }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.patchBody }}",
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2500, 0],
        "id": "tc-patch-task",
        "name": "Link Task to Log",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    wait_after_patch = {
        "parameters": {"amount": 500, "unit": "milliseconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [2750, 0],
        "id": "tc-wait-patch",
        "name": "Wait 500ms"
    }

    # Telegram notification after all tasks processed
    telegram_summary_code = r"""const data = $('Skip If Empty').first().json;
const rewards = data.rewards || [];
if (rewards.length === 0) return [{json: {skip: true}}];

let totalXP = 0, totalGold = 0, totalHP = 0;
let lines = [];
for (const r of rewards) {
  totalXP += r.xp;
  totalGold += r.gold;
  totalHP += r.hp;
  lines.push(`  ${r.name} | +${r.xp} XP | +${r.gold} Gold | +${r.hp} HP`);
}

let msg = '<b>QUEST COMPLETION REWARDS</b>\n\n';
msg += lines.join('\n');
msg += `\n\n<b>TOTAL: +${totalXP} XP | +${totalGold} Gold | +${totalHP} HP</b>`;

return [{json: {message: msg}}];"""

    build_telegram = {
        "parameters": {"jsCode": telegram_summary_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1250, 300],
        "id": "tc-build-telegram",
        "name": "Build Telegram Summary"
    }

    send_telegram = {
        "parameters": {
            "chatId": CHRIS_CHAT_ID,
            "text": "={{ $json.message }}",
            "additionalFields": {
                "appendAttribution": False,
                "parse_mode": "HTML"
            }
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [1500, 300],
        "id": "tc-telegram",
        "name": "Send Rewards Notification",
        "credentials": TELEGRAM_CRED
    }

    nodes = [
        trigger, build_query, fetch_tasks, calc_rewards, check_empty,
        split_tasks, build_log_entry, create_log, wait_after_create,
        build_link_back, patch_task, wait_after_patch,
        build_telegram, send_telegram
    ]

    connections = {
        "Every 15 Minutes": {"main": [
            [{"node": "Build Tasks Query", "type": "main", "index": 0}]
        ]},
        "Build Tasks Query": {"main": [
            [{"node": "Fetch Complete Tasks", "type": "main", "index": 0}]
        ]},
        "Fetch Complete Tasks": {"main": [
            [{"node": "Calculate Rewards", "type": "main", "index": 0}]
        ]},
        "Calculate Rewards": {"main": [
            [{"node": "Skip If Empty", "type": "main", "index": 0}]
        ]},
        "Skip If Empty": {"main": [
            [
                {"node": "Process Each Task", "type": "main", "index": 0},
                {"node": "Build Telegram Summary", "type": "main", "index": 0}
            ]
        ]},
        "Process Each Task": {"main": [
            [{"node": "Build Log Entry", "type": "main", "index": 0}],
            []  # done output
        ]},
        "Build Log Entry": {"main": [
            [{"node": "Create Activity Log", "type": "main", "index": 0}]
        ]},
        "Create Activity Log": {"main": [
            [{"node": "Wait 1s", "type": "main", "index": 0}]
        ]},
        "Wait 1s": {"main": [
            [{"node": "Build Link Back", "type": "main", "index": 0}]
        ]},
        "Build Link Back": {"main": [
            [{"node": "Link Task to Log", "type": "main", "index": 0}]
        ]},
        "Link Task to Log": {"main": [
            [{"node": "Wait 500ms", "type": "main", "index": 0}]
        ]},
        "Wait 500ms": {"main": [
            [{"node": "Process Each Task", "type": "main", "index": 0}]
        ]},
        "Build Telegram Summary": {"main": [
            [{"node": "Send Rewards Notification", "type": "main", "index": 0}]
        ]}
    }

    wf_data = {
        "name": "Task Completion Rewards",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Paris",
            "saveManualExecutions": True
        }
    }

    if dry_run:
        print("  [DRY RUN] Would create NEW workflow 'Task Completion Rewards':")
        print(f"    - {len(nodes)} nodes")
        print("    - Trigger: every 15 minutes")
        print("    - Query: Status=Complete, Completed On >= week start, Type != Project")
        print("    - Idempotence: skip tasks with existing Log relation")
        print("    - XP: Easy=15, Moderate=35, Hard=75 * Priority multiplier + Revenue bonus")
        print("    - Gold: 50% of XP, HP: 20% of XP")
        print("    - Creates Activity Log entry + links back to task")
        print("    - Telegram: summary notification")
        return True

    # Check if workflow already exists
    r = requests.get(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, params={"limit": 100})
    existing = r.json().get("data", [])
    existing_wf = None
    for w in existing:
        if w.get("name") == "Task Completion Rewards":
            existing_wf = w
            break

    if existing_wf:
        print(f"  Found existing workflow: {existing_wf['id']}")
        return deploy_workflow(existing_wf['id'], wf_data, "Task Completion Rewards")
    else:
        print("  Creating new workflow...")
        result = create_workflow(wf_data)
        wf_id = result.get("id")
        print(f"  Created: {wf_id}")
        time.sleep(1)
        ok = activate_workflow(wf_id)
        print(f"  Active: {ok}")
        return ok


# =====================================================
# FIX 4: Backfill Activity Log entries
# =====================================================
def backfill_activity_log(dry_run=False):
    """
    Patch existing Activity Log entries that have XP=0:
    - Hand In entries: set XP=15, Gold=8, HP=5
    - Skip Daily Judgment entries (penalties were disabled, don't retroact)
    """
    print("\n" + "=" * 60)
    print("FIX 4: Backfill Activity Log Entries")
    print("=" * 60)

    load_notion_token()
    if not NOTION_TOKEN:
        print("  ERROR: No Notion token available, cannot backfill")
        return False

    # Fetch Activity Log entries linked to Chris's Leaderboard page
    print("  Fetching Activity Log entries linked to Chris...")
    entries = notion_query_db(
        ACTIVITY_LOG_DB,
        filter_obj={
            "property": "Leaderboard",
            "relation": {"contains": CHRIS_LEADERBOARD_PAGE}
        },
        sorts=[{"property": "Date", "direction": "descending"}],
        page_size=100
    )

    print(f"  Found {len(entries)} entries linked to Chris")

    patched = 0
    skipped = 0
    for entry in entries:
        props = entry.get("properties", {})
        name_parts = props.get("Name", {}).get("title", [])
        name = name_parts[0]["plain_text"] if name_parts else "?"
        xp = props.get("XP", {}).get("number")
        gold = props.get("Gold", {}).get("number")
        hp = props.get("HP", {}).get("number")

        # Skip Daily Judgment entries (penalties were disabled, don't retroact)
        if "Daily Judgment" in name:
            if xp is None or xp == 0:
                print(f"    SKIP (Daily Judgment, no retroactive penalty): {name}")
                skipped += 1
            else:
                print(f"    OK (already has XP={xp}): {name}")
            continue

        # Check if XP is missing or zero
        if xp is not None and xp > 0:
            print(f"    OK (XP={xp}, Gold={gold}, HP={hp}): {name}")
            continue

        # This is a Hand In entry with no XP — patch it
        new_xp = 15
        new_gold = 8
        new_hp = 5

        # Check for difficulty hints in name
        if "Hard" in name or "Musculation" in name or "Sport" in name:
            new_xp = 30
            new_gold = 15
            new_hp = 10
        elif "Moderate" in name:
            new_xp = 20
            new_gold = 10
            new_hp = 8

        if dry_run:
            print(f"    [DRY RUN] Would PATCH: {name} -> XP={new_xp}, Gold={new_gold}, HP={new_hp}")
            patched += 1
            continue

        ok = notion_patch_page(entry["id"], {
            "XP": {"number": new_xp},
            "Gold": {"number": new_gold},
            "HP": {"number": new_hp}
        })
        if ok:
            print(f"    PATCHED: {name} -> XP={new_xp}, Gold={new_gold}, HP={new_hp}")
            patched += 1
        else:
            print(f"    FAILED: {name}")
        time.sleep(0.5)  # Rate limit

    print(f"\n  Summary: {patched} patched, {skipped} skipped (Daily Judgment)")
    return True


# =====================================================
# MAIN
# =====================================================
def main():
    parser = argparse.ArgumentParser(description="Fix Gamification System")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without deploying")
    parser.add_argument("--fix", type=str, default="1,2,3,4", help="Comma-separated fix numbers (1-4)")
    args = parser.parse_args()

    fixes = [int(x.strip()) for x in args.fix.split(",")]
    dry_run = args.dry_run

    print("=" * 60)
    print("FIX GAMIFICATION SYSTEM — COMPLETE")
    print(f"Mode: {'DRY RUN' if dry_run else 'DEPLOY'}")
    print(f"Fixes: {fixes}")
    print("=" * 60)

    results = {}

    # Fix 1+2 are combined in the Solo Leveling rebuild
    if 1 in fixes or 2 in fixes:
        results["Fix 1+2 (Solo Leveling)"] = fix_solo_leveling(dry_run)

    if 3 in fixes:
        results["Fix 3 (Task Completion)"] = create_task_completion_workflow(dry_run)

    if 4 in fixes:
        results["Fix 4 (Backfill)"] = backfill_activity_log(dry_run)

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {name}: {status}")

    all_ok = all(results.values())
    if all_ok and not dry_run:
        print("\nAll fixes deployed!")
        print("Next steps:")
        print("  1. Trigger Solo Leveling manually in n8n to verify")
        print("  2. Check Activity Log for XP/Gold/HP values")
        print("  3. Mark a task Complete and wait 15min for rewards")
        print("  4. Check Leaderboard page for updated rollups")
    elif dry_run:
        print("\nDry run complete. Run without --dry-run to deploy.")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
