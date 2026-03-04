#!/usr/bin/env python3
"""Create n8n workflow: Strava Sport Tracker
Polls Strava API for new activities, logs to Notion + Beeminder + Telegram.
Auto-refreshes OAuth2 tokens.
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
TELEGRAM_CHAT_ID = "7342622615"

workflow = {
    "name": "Strava Sport Tracker",
    "nodes": [
        {
            "parameters": {
                "rule": {
                    "interval": [{"field": "hours", "hoursInterval": 6}]
                }
            },
            "id": "schedule",
            "name": "Schedule Trigger",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 0]
        },
        {
            "parameters": {
                "jsCode": '''
// Refresh Strava access token using stored refresh token
const staticData = $getWorkflowStaticData('global');

// Initial tokens
if (!staticData.refreshToken) {
  staticData.refreshToken = '%s';
}
if (!staticData.lastCheckTime) {
  staticData.lastCheckTime = Math.floor(Date.now() / 1000) - 86400; // 24h ago
}

const resp = await $http.request({
  method: 'POST',
  url: 'https://www.strava.com/oauth/token',
  body: {
    client_id: '207859',
    client_secret: '3491bbae29373e6f1e9106d94ca9fb951fff8002',
    grant_type: 'refresh_token',
    refresh_token: staticData.refreshToken
  },
  json: true
});

// Save new tokens
staticData.refreshToken = resp.refresh_token;
staticData.accessToken = resp.access_token;

return [{
  json: {
    accessToken: resp.access_token,
    lastCheckTime: staticData.lastCheckTime
  }
}];
''' % REFRESH_TOKEN
            },
            "id": "refresh_token",
            "name": "Refresh Strava Token",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [220, 0]
        },
        {
            "parameters": {
                "url": "=https://www.strava.com/api/v3/athlete/activities",
                "sendQuery": True,
                "queryParameters": {
                    "parameters": [
                        {"name": "per_page", "value": "10"},
                        {"name": "after", "value": "={{ $json.lastCheckTime }}"}
                    ]
                },
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": "=Bearer {{ $json.accessToken }}"}
                    ]
                },
                "options": {}
            },
            "id": "fetch_strava",
            "name": "Fetch Strava Activities",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [440, 0]
        },
        {
            "parameters": {
                "jsCode": '''
const input = $input.all();
const activities = Array.isArray(input[0].json) ? input[0].json : 
                   (input[0].json.data ? input[0].json.data : [input[0].json]);

// Handle case where response is array wrapped in items
const allActivities = [];
for (const item of input) {
  if (item.json && item.json.id) {
    allActivities.push(item.json);
  }
}

const acts = allActivities.length > 0 ? allActivities : activities;

if (!acts || acts.length === 0 || !acts[0].id) {
  return [{ json: { hasNew: false, count: 0 } }];
}

const staticData = $getWorkflowStaticData('global');

const results = acts.map(a => {
  const distKm = ((a.distance || 0) / 1000).toFixed(2);
  const durationMin = Math.round((a.moving_time || 0) / 60);
  const elevGain = Math.round(a.total_elevation_gain || 0);
  const avgSpeed = a.average_speed ? (a.average_speed * 3.6).toFixed(1) : '0';
  const calories = a.calories || 0;
  const type = a.type || 'Activity';
  
  const typeEmoji = {
    'Run': '🏃',
    'Ride': '🚴',
    'Swim': '🏊',
    'Walk': '🚶',
    'Hike': '🥾',
    'Workout': '💪'
  }[type] || '🏃';

  return {
    json: {
      hasNew: true,
      activityId: a.id,
      name: a.name || type,
      type,
      distKm,
      durationMin,
      elevGain,
      avgSpeed,
      calories,
      startDate: a.start_date_local || a.start_date,
      taskName: type + ': ' + (a.name || 'Activity') + ' (' + distKm + 'km, ' + durationMin + 'min)',
      beeminderComment: type + ': ' + (a.name || 'Activity') + ' - ' + distKm + 'km, ' + durationMin + 'min',
      telegramMsg: typeEmoji + ' *Nouvelle activite Strava !*\n\n' +
        '*' + (a.name || type) + '*\n' +
        '📏 ' + distKm + ' km\n' +
        '⏱ ' + durationMin + ' min\n' +
        '⚡ ' + avgSpeed + ' km/h\n' +
        (elevGain > 0 ? '⛰ D+ ' + elevGain + 'm\n' : '') +
        (calories > 0 ? '🔥 ' + calories + ' cal\n' : '') +
        '\n✅ Notion + Beeminder poste'
    }
  };
});

// Update last check time
staticData.lastCheckTime = Math.floor(Date.now() / 1000);

return results;
'''
            },
            "id": "process_activities",
            "name": "Process Activities",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [660, 0]
        },
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "has_new",
                            "leftValue": "={{ $json.hasNew }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "equals",
                                "name": "filter.operator.equals"
                            }
                        }
                    ],
                    "combinator": "and"
                },
                "options": {}
            },
            "id": "if_new",
            "name": "Has New Activities?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [880, 0]
        },
        {
            "parameters": {
                "resource": "databasePage",
                "operation": "create",
                "databaseId": {"__rl": True, "mode": "id", "value": "305da200-b2d6-8145-bc16-eaee02925a14"},
                "title": "={{ $json.taskName }}",
                "propertiesUi": {
                    "propertyValues": [
                        {"key": "Category|select", "selectValue": "🏠 Perso"},
                        {"key": "Status|status", "statusValue": "Complete"},
                        {"key": "Type|select", "selectValue": "Task"},
                        {"key": "Description|rich_text", "textValue": "={{ $json.type }}: {{ $json.distKm }}km, {{ $json.durationMin }}min, {{ $json.avgSpeed }}km/h. [Auto-logged from Strava]"}
                    ]
                },
                "options": {}
            },
            "id": "notion_create",
            "name": "Create Notion Task",
            "type": "n8n-nodes-base.notion",
            "typeVersion": 2.2,
            "position": [1120, -100],
            "credentials": {
                "notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}
            }
        },
        {
            "parameters": {
                "url": "https://www.beeminder.com/api/v1/users/prinsechris/goals/habitudes/datapoints.json",
                "sendBody": True,
                "bodyParameters": {
                    "parameters": [
                        {"name": "auth_token", "value": "28f1_C1a-W6ZPtA1joXN"},
                        {"name": "value", "value": "1"},
                        {"name": "comment", "value": "={{ $json.beeminderComment }}"}
                    ]
                },
                "options": {},
                "method": "POST"
            },
            "id": "beeminder_post",
            "name": "Post Beeminder",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1120, 100]
        },
        {
            "parameters": {
                "chatId": TELEGRAM_CHAT_ID,
                "text": "={{ $json.telegramMsg }}",
                "additionalFields": {"parse_mode": "Markdown"}
            },
            "id": "telegram_send",
            "name": "Telegram Recap",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [1120, 300],
            "credentials": {
                "telegramApi": {"id": "37SeOsuQW7RBmQTl", "name": "Orun Telegram Bot"}
            }
        },
        {
            "parameters": {},
            "id": "noop",
            "name": "No New Activities",
            "type": "n8n-nodes-base.noOp",
            "typeVersion": 1,
            "position": [1120, 500]
        }
    ],
    "connections": {
        "Schedule Trigger": {
            "main": [[{"node": "Refresh Strava Token", "type": "main", "index": 0}]]
        },
        "Refresh Strava Token": {
            "main": [[{"node": "Fetch Strava Activities", "type": "main", "index": 0}]]
        },
        "Fetch Strava Activities": {
            "main": [[{"node": "Process Activities", "type": "main", "index": 0}]]
        },
        "Process Activities": {
            "main": [[{"node": "Has New Activities?", "type": "main", "index": 0}]]
        },
        "Has New Activities?": {
            "main": [
                [
                    {"node": "Create Notion Task", "type": "main", "index": 0},
                    {"node": "Post Beeminder", "type": "main", "index": 0},
                    {"node": "Telegram Recap", "type": "main", "index": 0}
                ],
                [
                    {"node": "No New Activities", "type": "main", "index": 0}
                ]
            ]
        }
    },
    "settings": {"executionOrder": "v1"}
}

# Create workflow
resp = requests.post(f"{N8N_URL}/api/v1/workflows", headers=HEADERS, json=workflow)
if resp.status_code in (200, 201):
    data = resp.json()
    wf_id = data["id"]
    print(f"Workflow cree: {wf_id}")
    
    # Activate
    resp2 = requests.post(f"{N8N_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS)
    if resp2.status_code == 200:
        print(f"Workflow ACTIVE")
    else:
        print(f"Activation: {resp2.status_code} {resp2.text[:200]}")
else:
    print(f"Error: {resp.status_code}")
    print(resp.text[:500])
