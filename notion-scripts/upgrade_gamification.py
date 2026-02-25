#!/usr/bin/env python3
"""
Upgrade Gamification System:
1. Fix Solo Leveling Daily (proper credentials, better logging, streak notifications)
2. Extend Live Stats (CE MOIS + ALL TIME + level-up detection)
3. Add streak milestones + level-up Telegram notifications
"""

import json
import requests
import time

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9.sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Workflow IDs
SOLO_LEVELING_ID = "q2QmGHq17YIxzHzy"
LIVE_STATS_ID = "XCoyGKYl0y8r3Geg"

# Credentials
NOTION_CRED = {"notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}}
TELEGRAM_CRED = {"telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}}
CHRIS_CHAT_ID = "7342622615"

# Database IDs
HABITS_DB = "305da200-b2d6-8139-b19f-d2a0d46cf7e6"
ACTIVITY_LOG_DB = "305da200-b2d6-819f-915f-d35f51386aa8"
DAILY_SUMMARY_DB = "8559b19c-86a5-4034-bc4d-ea45459ef6bd"

# Block IDs for Live Stats
CETTE_SEMAINE_BLOCK = "88b71720-6678-4d99-ae1c-eacad65f01b4"
CE_MOIS_BLOCK = "444af0ec-800f-4f3f-b582-51b8b6a634e5"
ALL_TIME_BLOCK = "51a77758-829e-4151-999f-af7467163e89"
PLAYER_STATS_BLOCK = "46f38215-9555-4aac-8416-d2063a6edc95"

# Leaderboard page ID (the single page in the Leaderboard DB)
LEADERBOARD_PAGE = "305da200-b2d6-81f1-9d1e-c0b7a9399619"


def build_solo_leveling():
    """Build fixed Solo Leveling Daily workflow."""

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
            "url": f"https://api.notion.com/v1/databases/{HABITS_DB.replace('-','')}/query",
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
        "id": "sl-fetch",
        "name": "Fetch Daily Habits",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput",
        "retryOnFail": True,
        "maxTries": 2,
        "waitBetweenTries": 2000
    }

    wait_between = {
        "parameters": {"amount": 1, "unit": "seconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [500, 0],
        "id": "sl-wait1",
        "name": "Wait 1s"
    }

    # Fetch player stats sequentially (after habits)
    fetch_player = {
        "parameters": {
            "method": "GET",
            "url": f"https://api.notion.com/v1/pages/{LEADERBOARD_PAGE.replace('-','')}",
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
        "position": [700, 0],
        "id": "sl-player",
        "name": "Fetch Player Stats",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    judgment_code = r"""// Solo Leveling System - Quest Judgment
// Ce code est IMMUTABLE - il ne pardonne pas

const habitsResponse = $('Fetch Daily Habits').first().json;
const playerResponse = $json; // comes directly from Fetch Player Stats

// Handle API errors
if (habitsResponse.error || habitsResponse.object === 'error') {
  return [{json: {
    date: new Date().toISOString().split('T')[0],
    message: 'SYSTEM ERROR: Impossible de recuperer les habits. ' + (habitsResponse.message || ''),
    error: true,
    xpEarned: 0, goldLost: 0, completed: 0, failed: 0
  }}];
}

const habits = habitsResponse.results || [];
const now = new Date(new Date().getTime() + 3600000); // UTC+1
const today = now.toISOString().split('T')[0];
const results = [];
let completedCount = 0;
let failedCount = 0;
let totalXP = 0;
let totalGoldLost = 0;
let maxStreak = 0;

for (const habit of habits) {
  const props = habit.properties || {};

  const lastCompleted = props['Last Completed']?.date?.start || null;
  const habitName = props['Name']?.title?.[0]?.plain_text || 'Unknown Quest';
  const difficulty = props['Difficulty']?.select?.name || '1 - Easy';
  const streakDays = props['Streak Days']?.number || props['Current Streak']?.number || 0;

  const xpMap = { '1 - Easy': 10, '2 - Moderate': 25, '3 - Hard': 50 };
  const baseXP = xpMap[difficulty] || 10;

  const completed = lastCompleted === today;

  if (completed) {
    completedCount++;
    const streakBonus = Math.floor(streakDays / 7) * 5;
    totalXP += baseXP + streakBonus;
    if (streakDays > maxStreak) maxStreak = streakDays;
    results.push({
      quest: habitName, status: 'COMPLETED',
      xp: baseXP + streakBonus, streak: streakDays + 1, penalty: 0
    });
  } else {
    failedCount++;
    const goldPenalty = baseXP * 2;
    totalGoldLost += goldPenalty;
    results.push({
      quest: habitName, status: 'FAILED',
      xp: 0, streak: 0, penalty: goldPenalty
    });
  }
}

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
const currentLevel = getFormula(playerProps['Level'] || playerProps['level']);
const currentXP = getFormula(playerProps['XP'] || playerProps['xp']);
const currentGold = getFormula(playerProps['Gold'] || playerProps['gold']);

// Build message
const allCompleted = failedCount === 0;
const total = completedCount + failedCount;

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
    msg += `  ${r.quest} | -${r.penalty} Gold | Streak RESET\n`;
  }
}

msg += `\n<b>SUMMARY</b>\n`;
msg += `Quests: ${completedCount}/${total}\n`;
msg += `XP Earned: +${totalXP}\n`;
msg += `Gold Lost: -${totalGoldLost}\n`;
if (currentLevel != null) msg += `Level: ${currentLevel} | XP: ${currentXP} | Gold: ${currentGold}\n`;

// Streak milestones
const streakMilestones = [7, 14, 21, 30, 50, 100];
for (const r of results) {
  if (r.status === 'COMPLETED' && streakMilestones.includes(r.streak)) {
    msg += `\nSTREAK MILESTONE: ${r.quest} - ${r.streak} DAYS!\n`;
  }
}

// Perfect day bonus
if (allCompleted && total > 0) {
  msg += `\nPerfect Day! +${Math.floor(totalXP * 0.1)} bonus XP\n`;
  totalXP += Math.floor(totalXP * 0.1);
}

if (!allCompleted && failedCount > 0) {
  msg += `\nThe System does not forgive. Your streaks have been reset.\n`;
}

// Level-up detection via staticData
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
  completed: completedCount,
  failed: failedCount,
  total,
  allCompleted,
  results,
  error: false,
  logEntry: {
    timestamp: new Date().toISOString(),
    type: 'DAILY_JUDGMENT',
    checksum: Buffer.from(JSON.stringify(results) + new Date().toISOString()).toString('base64')
  }
}}];"""

    judgment = {
        "parameters": {"jsCode": judgment_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [900, 0],
        "id": "sl-judgment",
        "name": "Judgment Engine (Immutable)"
    }

    # Log to Activity Log with full data
    log_code = r"""const d = $json;
if (d.error) {
  // Don't log if we had an API error
  return [{json: {skip: true}}];
}

const logBody = {
  parent: { database_id: '""" + ACTIVITY_LOG_DB.replace('-','') + r"""' },
  properties: {
    Name: { title: [{ text: { content: d.date + ' - Daily Judgment (' + d.completed + '/' + d.total + ')' } }] },
    Date: { date: { start: d.date + 'T23:45:00.000+01:00' } }
  }
};

return [{json: {logBody: JSON.stringify(logBody)}}];"""

    build_log = {
        "parameters": {"jsCode": log_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1200, -100],
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
        "position": [1500, -100],
        "id": "sl-log",
        "name": "Log to Activity Log",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    send_telegram = {
        "parameters": {
            "chatId": CHRIS_CHAT_ID,
            "text": "={{ $('Judgment Engine (Immutable)').first().json.message }}",
            "additionalFields": {
                "appendAttribution": False,
                "parse_mode": "HTML"
            }
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [1200, 200],
        "id": "sl-telegram",
        "name": "Send Verdict",
        "credentials": TELEGRAM_CRED
    }

    nodes = [trigger, fetch_habits, wait_between, fetch_player, judgment,
             build_log, log_node, send_telegram]

    # Sequential flow: Trigger → Habits → Wait → Player → Judgment → (Log + Telegram)
    connections = {
        "23h45 - Judgment Time": {"main": [
            [{"node": "Fetch Daily Habits", "type": "main", "index": 0}]
        ]},
        "Fetch Daily Habits": {"main": [
            [{"node": "Wait 1s", "type": "main", "index": 0}]
        ]},
        "Wait 1s": {"main": [
            [{"node": "Fetch Player Stats", "type": "main", "index": 0}]
        ]},
        "Fetch Player Stats": {"main": [
            [{"node": "Judgment Engine (Immutable)", "type": "main", "index": 0}]
        ]},
        "Judgment Engine (Immutable)": {"main": [
            [
                {"node": "Build Log Entry", "type": "main", "index": 0},
                {"node": "Send Verdict", "type": "main", "index": 0}
            ]
        ]},
        "Build Log Entry": {"main": [
            [{"node": "Log to Activity Log", "type": "main", "index": 0}]
        ]}
    }

    return {
        "name": "Solo Leveling System - Daily Quest Check",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Paris",
            "saveManualExecutions": True
        }
    }


def build_live_stats():
    """Build extended Live Stats workflow with CE MOIS + ALL TIME."""

    trigger = {
        "parameters": {
            "rule": {"interval": [{"field": "hours", "hoursInterval": 2}]}
        },
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 0],
        "id": "ls-trigger",
        "name": "Every 2 Hours"
    }

    get_player = {
        "parameters": {
            "method": "GET",
            "url": f"https://api.notion.com/v1/pages/{LEADERBOARD_PAGE.replace('-','')}",
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
        "position": [250, 0],
        "id": "ls-player",
        "name": "Get Player Stats",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    wait1 = {
        "parameters": {"amount": 1, "unit": "seconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [450, 0],
        "id": "ls-w1",
        "name": "Wait 1s"
    }

    # Weekly activities from Activity Log
    get_weekly = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{ACTIVITY_LOG_DB.replace('-','')}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ filter: { property: 'Date', date: { on_or_after: new Date(new Date().getTime() + 3600000 - new Date().getDay() * 86400000 + (new Date().getDay() === 0 ? -6 : 1) * 86400000).toISOString().split('T')[0] } }, sorts: [{ property: 'Date', direction: 'descending' }] }) }}",
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [650, 0],
        "id": "ls-weekly",
        "name": "Get Weekly Activities",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    wait2 = {
        "parameters": {"amount": 1, "unit": "seconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [850, 0],
        "id": "ls-w2",
        "name": "Wait 1s (2)"
    }

    # Monthly activities
    get_monthly = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{ACTIVITY_LOG_DB.replace('-','')}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ filter: { property: 'Date', date: { on_or_after: new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0] } }, sorts: [{ property: 'Date', direction: 'descending' }] }) }}",
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1050, 0],
        "id": "ls-monthly",
        "name": "Get Monthly Activities",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    wait3 = {
        "parameters": {"amount": 1, "unit": "seconds"},
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [1250, 0],
        "id": "ls-w3",
        "name": "Wait 1s (3)"
    }

    # Daily Summary for active days count
    get_daily_summary = {
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{DAILY_SUMMARY_DB.replace('-','')}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ sorts: [{ property: 'Date', direction: 'descending' }], page_size: 100 }) }}",
            "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1450, 0],
        "id": "ls-summary",
        "name": "Get Daily Summary",
        "credentials": NOTION_CRED,
        "onError": "continueRegularOutput"
    }

    # Build ALL updates (week + month + all time + player stats)
    build_code = r"""// Gather all data
const playerPage = $('Get Player Stats').first().json;
const weeklyData = $('Get Weekly Activities').first().json;
const monthlyData = $('Get Monthly Activities').first().json;
const summaryData = $('Get Daily Summary').first().json;

const props = playerPage.properties || {};
const weekActivities = weeklyData.results || [];
const monthActivities = monthlyData.results || [];
const allDays = summaryData.results || [];

function getFormula(prop) {
    if (!prop) return null;
    if (prop.type === 'formula') {
        const f = prop.formula;
        if (f.type === 'number') return f.number;
        if (f.type === 'string') return f.string;
    }
    if (prop.type === 'number') return prop.number;
    return null;
}

function progressBar(current, max, width = 10) {
    if (!max || max === 0) return '\u2591'.repeat(width);
    const pct = Math.min(current / max, 1);
    const filled = Math.round(pct * width);
    return '\u2588'.repeat(filled) + '\u2591'.repeat(width - filled);
}

function sumProp(items, propName) {
    let total = 0;
    for (const item of items) {
        const p = item.properties || {};
        const val = getFormula(p[propName]);
        if (typeof val === 'number') total += val;
    }
    return total;
}

function countHabits(items) {
    let count = 0;
    for (const item of items) {
        const p = item.properties || {};
        const rel = p['Habits'] || p['habits'];
        if (rel && rel.type === 'relation' && (rel.relation || []).length > 0) count++;
    }
    return count;
}

// Player stats
const level = getFormula(props['Level'] || props['level']) || 1;
const gold = getFormula(props['Gold'] || props['gold']) || 0;
const health = getFormula(props['Health'] || props['health']) || 100;
const totalHabitsCount = getFormula(props['Habits'] || props['habits']) || 0;
const xpTotal = getFormula(props['XP'] || props['xp']) || 0;
const xpNext = getFormula(props['XP to Next Level'] || props['xp_to_next_level']) || 200;

// === CETTE SEMAINE ===
const weekXP = sumProp(weekActivities, 'XP') || sumProp(weekActivities, 'xp');
const weekGold = sumProp(weekActivities, 'Gold') || sumProp(weekActivities, 'gold');
const weekHabits = countHabits(weekActivities);

// Count active days this week
const now = new Date(new Date().getTime() + 3600000);
const monday = new Date(now);
monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
monday.setHours(0, 0, 0, 0);
const mondayStr = monday.toISOString().split('T')[0];
let weekDays = 0;
for (const d of allDays) {
    const date = d.properties?.['Date']?.date?.start;
    if (date && date >= mondayStr) weekDays++;
}

const weekText = `\ud83d\udd25 CETTE SEMAINE\n\u2b50 XP: ${weekXP}/500 ${progressBar(weekXP, 500)}\n\ud83d\udcb0 Gold: ${weekGold} | \u2764\ufe0f Streak: ${weekDays}j\n\ud83d\udcd3 Habits: ${weekHabits}/35 ${progressBar(weekHabits, 35)}\n\ud83d\udcc5 ${weekActivities.length} activities | \ud83d\udd52 Auto`;

// === CE MOIS ===
const monthXP = sumProp(monthActivities, 'XP') || sumProp(monthActivities, 'xp');
const monthGold = sumProp(monthActivities, 'Gold') || sumProp(monthActivities, 'gold');
const monthHabits = countHabits(monthActivities);

const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
let monthDays = 0;
for (const d of allDays) {
    const date = d.properties?.['Date']?.date?.start;
    if (date && date >= firstOfMonth) monthDays++;
}
const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
const habitsMonthTarget = daysInMonth * 5;

const monthText = `\ud83d\udcc6 CE MOIS\n\u2b50 XP: ${monthXP}/2000 ${progressBar(monthXP, 2000)}\n\ud83d\udcb0 Gold: ${monthGold} | \ud83d\udcc5 ${monthDays}j actifs\n\ud83d\udcd3 Habits: ${monthHabits}/${habitsMonthTarget} ${progressBar(monthHabits, habitsMonthTarget)}\n\ud83d\udcca ${monthActivities.length} activities total`;

// === ALL TIME ===
const pctLevel = xpNext > 0 ? Math.round((xpTotal / xpNext) * 100) : 0;

// Find best streak from daily summaries
let bestStreak = 0;
let currentStreak = 0;
const sortedDays = allDays.map(d => d.properties?.['Date']?.date?.start).filter(Boolean).sort().reverse();
for (let i = 0; i < sortedDays.length; i++) {
    if (i === 0) { currentStreak = 1; continue; }
    const prev = new Date(sortedDays[i-1]);
    const curr = new Date(sortedDays[i]);
    const diff = (prev - curr) / 86400000;
    if (diff <= 1.5) {
        currentStreak++;
    } else {
        if (currentStreak > bestStreak) bestStreak = currentStreak;
        currentStreak = 1;
    }
}
if (currentStreak > bestStreak) bestStreak = currentStreak;

let totalHabitsAll = 0;
for (const item of allDays) {
    const r = item.properties?.['Habits Completed'] || item.properties?.['habits_completed'];
    if (r) {
        const v = getFormula(r);
        if (typeof v === 'number') totalHabitsAll += v;
    }
}
if (totalHabitsAll === 0) totalHabitsAll = countHabits(monthActivities); // fallback

const totalQuests = allDays.length;

const allTimeText = `\ud83c\udfc6 ALL TIME\n\u2b50 Level ${level} ${progressBar(xpTotal, xpNext)} ${pctLevel}%\n\ud83d\udcb0 Gold: ${gold} | \ud83d\udd25 Best: ${bestStreak}j\n\ud83d\udcd3 Habits: ${totalHabitsAll} total\n\ud83c\udfae ${totalQuests} days played`;

// === PLAYER STATS ===
const playerText = `PLAYER STATS \u2192 Stats & Analytics\n\u2b50 Level: ${level}\n${pctLevel}% ${progressBar(xpTotal, xpNext)} ${xpTotal}/${xpNext} | \ud83d\udcb0 Gold: ${gold}\n\u2764\ufe0f Health: ${health} HP | \ud83d\udcd3 Habits: ${weekHabits}/${totalHabitsCount || 5}`;

function patchBody(text) {
    return JSON.stringify({
        paragraph: {
            rich_text: [{type: "text", text: {content: text}}]
        }
    });
}

return [{json: {
    cetteSemaineBody: patchBody(weekText),
    ceMoisBody: patchBody(monthText),
    allTimeBody: patchBody(allTimeText),
    playerStatsBody: patchBody(playerText),
    cetteSemaineBlockId: '""" + CETTE_SEMAINE_BLOCK + r"""',
    ceMoisBlockId: '""" + CE_MOIS_BLOCK + r"""',
    allTimeBlockId: '""" + ALL_TIME_BLOCK + r"""',
    playerStatsBlockId: '""" + PLAYER_STATS_BLOCK + r"""'
}}];"""

    build_updates = {
        "parameters": {"jsCode": build_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1650, 0],
        "id": "ls-build",
        "name": "Build All Updates"
    }

    # Update nodes (4 blocks, with waits between)
    def make_update_node(name, block_expr, body_expr, pos_x, node_id):
        return {
            "parameters": {
                "method": "PATCH",
                "url": f"=https://api.notion.com/v1/blocks/{block_expr}",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "notionApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": f"={{{{ $('Build All Updates').first().json.{body_expr} }}}}",
                "options": {}
            },
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [pos_x, 0],
            "id": node_id,
            "name": name,
            "credentials": NOTION_CRED,
            "onError": "continueRegularOutput"
        }

    def make_wait(pos_x, node_id, name):
        return {
            "parameters": {"amount": 1, "unit": "seconds"},
            "type": "n8n-nodes-base.wait",
            "typeVersion": 1.1,
            "position": [pos_x, 0],
            "id": node_id,
            "name": name
        }

    upd_semaine = make_update_node("Update Cette Semaine",
        "{{ $json.cetteSemaineBlockId }}", "cetteSemaineBody", 1850, "ls-u1")
    w4 = make_wait(2050, "ls-w4", "Wait 1s (4)")
    upd_mois = make_update_node("Update Ce Mois",
        "{{ $json.ceMoisBlockId }}", "ceMoisBody", 2250, "ls-u2")
    w5 = make_wait(2450, "ls-w5", "Wait 1s (5)")
    upd_alltime = make_update_node("Update All Time",
        "{{ $json.allTimeBlockId }}", "allTimeBody", 2650, "ls-u3")
    w6 = make_wait(2850, "ls-w6", "Wait 1s (6)")
    upd_player = make_update_node("Update Player Stats",
        "{{ $json.playerStatsBlockId }}", "playerStatsBody", 3050, "ls-u4")

    nodes = [trigger, get_player, wait1, get_weekly, wait2, get_monthly,
             wait3, get_daily_summary, build_updates,
             upd_semaine, w4, upd_mois, w5, upd_alltime, w6, upd_player]

    connections = {
        "Every 2 Hours": {"main": [[{"node": "Get Player Stats", "type": "main", "index": 0}]]},
        "Get Player Stats": {"main": [[{"node": "Wait 1s", "type": "main", "index": 0}]]},
        "Wait 1s": {"main": [[{"node": "Get Weekly Activities", "type": "main", "index": 0}]]},
        "Get Weekly Activities": {"main": [[{"node": "Wait 1s (2)", "type": "main", "index": 0}]]},
        "Wait 1s (2)": {"main": [[{"node": "Get Monthly Activities", "type": "main", "index": 0}]]},
        "Get Monthly Activities": {"main": [[{"node": "Wait 1s (3)", "type": "main", "index": 0}]]},
        "Wait 1s (3)": {"main": [[{"node": "Get Daily Summary", "type": "main", "index": 0}]]},
        "Get Daily Summary": {"main": [[{"node": "Build All Updates", "type": "main", "index": 0}]]},
        "Build All Updates": {"main": [[{"node": "Update Cette Semaine", "type": "main", "index": 0}]]},
        "Update Cette Semaine": {"main": [[{"node": "Wait 1s (4)", "type": "main", "index": 0}]]},
        "Wait 1s (4)": {"main": [[{"node": "Update Ce Mois", "type": "main", "index": 0}]]},
        "Update Ce Mois": {"main": [[{"node": "Wait 1s (5)", "type": "main", "index": 0}]]},
        "Wait 1s (5)": {"main": [[{"node": "Update All Time", "type": "main", "index": 0}]]},
        "Update All Time": {"main": [[{"node": "Wait 1s (6)", "type": "main", "index": 0}]]},
        "Wait 1s (6)": {"main": [[{"node": "Update Player Stats", "type": "main", "index": 0}]]}
    }

    return {
        "name": "Command Center \u2014 Live Stats",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Paris",
            "saveManualExecutions": True
        }
    }


def deploy_workflow(workflow_id, workflow_data, name):
    """Deactivate, update, reactivate a workflow."""
    print(f"\n{'='*50}")
    print(f"Deploying: {name}")
    print(f"{'='*50}")

    # Deactivate
    print("  1. Deactivating...")
    r = requests.post(f"{N8N_URL}/api/v1/workflows/{workflow_id}/deactivate", headers=HEADERS)
    print(f"     Status: {r.status_code}")
    time.sleep(2)

    # Update
    print("  2. Updating workflow...")
    r = requests.put(
        f"{N8N_URL}/api/v1/workflows/{workflow_id}",
        headers=HEADERS,
        json=workflow_data
    )
    print(f"     Status: {r.status_code}")
    if r.status_code != 200:
        print(f"     Error: {r.text[:500]}")
        return False
    time.sleep(2)

    # Activate
    print("  3. Activating...")
    r = requests.post(f"{N8N_URL}/api/v1/workflows/{workflow_id}/activate", headers=HEADERS)
    print(f"     Status: {r.status_code}")
    if r.status_code == 200:
        print(f"     Active: {r.json().get('active')}")
    else:
        print(f"     Error: {r.text[:300]}")
        return False

    return True


def main():
    print("=== GAMIFICATION SYSTEM UPGRADE ===\n")

    # 1. Solo Leveling
    solo = build_solo_leveling()
    ok1 = deploy_workflow(SOLO_LEVELING_ID, solo, "Solo Leveling Daily")
    if ok1:
        print("\n  Changes:")
        print("  - Notion credentials: proper notionApi auth")
        print("  - Telegram: uses n8n Telegram node with Orun bot")
        print("  - Fetches player stats for level info in verdict")
        print("  - Streak milestones: 7/14/21/30/50/100 day alerts")
        print("  - Perfect day bonus: +10% XP")
        print("  - Error handling: continueRegularOutput on all HTTP nodes")

    # 2. Live Stats
    stats = build_live_stats()
    ok2 = deploy_workflow(LIVE_STATS_ID, stats, "Live Stats (Extended)")
    if ok2:
        print("\n  Changes:")
        print("  - NEW: CE MOIS callout (monthly XP, Gold, active days)")
        print("  - NEW: ALL TIME callout (level, best streak, total quests)")
        print("  - 4 blocks updated every 2h instead of 2")
        print("  - Monthly activities query added")
        print("  - Daily Summary query for streak/active days calculation")
        print("  - Error handling on all HTTP nodes")

    print(f"\n{'='*50}")
    print(f"RESULT: Solo Leveling {'OK' if ok1 else 'FAILED'} | Live Stats {'OK' if ok2 else 'FAILED'}")
    print(f"{'='*50}")

    if ok1 and ok2:
        print("\nGamification system upgraded!")
        print("Active workflows:")
        print("  - Solo Leveling Daily: 23h45 judgment + penalties + streaks")
        print("  - Live Stats: 4 callouts updated every 2h")
        print("  - Activity Router: routes activities to Activity Log")
        print("  - Task Completion: XP/Gold on task complete")
        print("  - Sports Bridge: sports -> Activity Log")
        print("  - Daily Morning CRON: daily init")
        print("  - Monthly Reset: monthly metrics reset")


if __name__ == "__main__":
    main()
