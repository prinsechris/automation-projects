#!/usr/bin/env python3
"""Create n8n workflow: Hevy Sport Tracker
Polls Hevy API for new workouts, logs to Notion + Beeminder + Telegram.
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
    "name": "Hevy Sport Tracker",
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
                "jsCode": """
// Get static data to track last processed workout
const staticData = $getWorkflowStaticData('global');
const lastCheckTime = staticData.lastCheckTime || '2026-03-01T00:00:00Z';
const lastWorkoutId = staticData.lastWorkoutId || '';

return [{
  json: {
    lastCheckTime,
    lastWorkoutId
  }
}];
"""
            },
            "id": "get_last_check",
            "name": "Get Last Check",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [220, 0]
        },
        {
            "parameters": {
                "url": "https://api.hevyapp.com/v1/workouts",
                "sendQuery": True,
                "queryParameters": {
                    "parameters": [
                        {"name": "page", "value": "1"},
                        {"name": "pageSize", "value": "10"}
                    ]
                },
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "api-key", "value": "911e8793-2c5f-4616-8b7b-ef055576e7c3"}
                    ]
                },
                "options": {}
            },
            "id": "fetch_hevy",
            "name": "Fetch Hevy Workouts",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [440, 0]
        },
        {
            "parameters": {
                "jsCode": """
const input = $input.all();
const hevyData = input[0].json;
const workouts = hevyData.workouts || [];

// Get last check info from previous node chain
const staticData = $getWorkflowStaticData('global');
const lastCheckTime = staticData.lastCheckTime || '2026-03-01T00:00:00Z';
const lastWorkoutId = staticData.lastWorkoutId || '';

// Filter new workouts (after lastCheckTime and not the same ID)
const newWorkouts = workouts.filter(w => {
  const wTime = new Date(w.start_time).getTime();
  const checkTime = new Date(lastCheckTime).getTime();
  return wTime > checkTime && w.id !== lastWorkoutId;
});

if (newWorkouts.length === 0) {
  return [{ json: { hasNew: false, count: 0 } }];
}

// Process each new workout
const results = newWorkouts.map(w => {
  let totalReps = 0;
  let totalSets = 0;
  let totalVolume = 0;
  const exerciseNames = [];

  for (const ex of w.exercises || []) {
    exerciseNames.push(ex.title);
    for (const s of ex.sets || []) {
      totalSets++;
      if (s.reps) totalReps += s.reps;
      if (s.weight_kg && s.reps) totalVolume += s.weight_kg * s.reps;
    }
  }

  const startTime = new Date(w.start_time);
  const endTime = new Date(w.end_time);
  const durationMin = Math.round((endTime - startTime) / 60000);

  return {
    json: {
      hasNew: true,
      workoutId: w.id,
      title: w.title || 'Workout',
      startTime: w.start_time,
      endTime: w.end_time,
      durationMin,
      exerciseCount: (w.exercises || []).length,
      exerciseNames: exerciseNames.join(', '),
      totalSets,
      totalReps,
      totalVolume: Math.round(totalVolume),
      description: w.description || '',
      // For Notion task name
      taskName: `${w.title || 'Workout'} (${durationMin}min, ${totalSets} sets)`,
      // For Beeminder comment
      beeminderComment: `${w.title}: ${exerciseNames.slice(0,3).join(', ')} — ${totalReps} reps, ${durationMin}min`,
      // For Telegram
      telegramMsg: `🏋️ *Nouvelle seance Hevy detectee !*\\n\\n` +
        `*${w.title || 'Workout'}*\\n` +
        `⏱ ${durationMin} min\\n` +
        `💪 ${(w.exercises || []).length} exercices, ${totalSets} series, ${totalReps} reps\\n` +
        `📋 ${exerciseNames.join(', ')}\\n` +
        (totalVolume > 0 ? `🏗 Volume: ${Math.round(totalVolume)} kg\\n` : '') +
        `\\n✅ Tache Notion creee + Beeminder poste`
    }
  };
});

// Update static data with most recent workout
const newest = newWorkouts[0];
staticData.lastCheckTime = newest.start_time;
staticData.lastWorkoutId = newest.id;

return results;
"""
            },
            "id": "process_workouts",
            "name": "Process Workouts",
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
            "name": "Has New Workouts?",
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
                        {
                            "key": "Category|select",
                            "selectValue": "🏠 Perso"
                        },
                        {
                            "key": "Status|status",
                            "statusValue": "Complete"
                        },
                        {
                            "key": "Type|select",
                            "selectValue": "Task"
                        },
                        {
                            "key": "Description|rich_text",
                            "textValue": "={{ $json.exerciseNames }} — {{ $json.totalReps }} reps, {{ $json.totalSets }} sets, {{ $json.durationMin }}min. [Auto-logged from Hevy]"
                        }
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
                "notionApi": {
                    "id": "FPqqVYnRbUnwRzrY",
                    "name": "Notion account"
                }
            }
        },
        {
            "parameters": {
                "url": "=https://www.beeminder.com/api/v1/users/prinsechris/goals/habitudes/datapoints.json",
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
                "additionalFields": {
                    "parse_mode": "Markdown"
                }
            },
            "id": "telegram_send",
            "name": "Telegram Recap",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [1120, 300],
            "credentials": {
                "telegramApi": {
                    "id": "37SeOsuQW7RBmQTl",
                    "name": "Orun Telegram Bot"
                }
            }
        },
        {
            "parameters": {},
            "id": "noop",
            "name": "No New Workouts",
            "type": "n8n-nodes-base.noOp",
            "typeVersion": 1,
            "position": [1120, 500]
        }
    ],
    "connections": {
        "Schedule Trigger": {
            "main": [[{"node": "Get Last Check", "type": "main", "index": 0}]]
        },
        "Get Last Check": {
            "main": [[{"node": "Fetch Hevy Workouts", "type": "main", "index": 0}]]
        },
        "Fetch Hevy Workouts": {
            "main": [[{"node": "Process Workouts", "type": "main", "index": 0}]]
        },
        "Process Workouts": {
            "main": [[{"node": "Has New Workouts?", "type": "main", "index": 0}]]
        },
        "Has New Workouts?": {
            "main": [
                [
                    {"node": "Create Notion Task", "type": "main", "index": 0},
                    {"node": "Post Beeminder", "type": "main", "index": 0},
                    {"node": "Telegram Recap", "type": "main", "index": 0}
                ],
                [
                    {"node": "No New Workouts", "type": "main", "index": 0}
                ]
            ]
        }
    },
    "settings": {
        "executionOrder": "v1"
    }
}

# Create workflow
resp = requests.post(
    f"{N8N_URL}/api/v1/workflows",
    headers=HEADERS,
    json=workflow
)

if resp.status_code in (200, 201):
    data = resp.json()
    wf_id = data["id"]
    print(f"Workflow cree: {wf_id}")
    print(f"Nom: {data['name']}")
    
    # Activate it
    resp2 = requests.patch(
        f"{N8N_URL}/api/v1/workflows/{wf_id}",
        headers=HEADERS,
        json={"active": True}
    )
    if resp2.status_code == 200:
        print(f"Workflow ACTIVE")
    else:
        print(f"Activation failed: {resp2.status_code} — {resp2.text[:200]}")
else:
    print(f"Error: {resp.status_code}")
    print(resp.text[:500])
