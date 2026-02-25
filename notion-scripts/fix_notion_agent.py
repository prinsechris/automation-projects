#!/usr/bin/env python3
"""
Fix: Sub: Notion Agent - Couche 3b
Problem: When Claude hallucinates a block/page ID, the HTTP Request node
crashes the entire sub-workflow with no error handling.

Fixes:
1. HTTP Request Notion: add onError=continueRegularOutput (don't crash)
2. Build Request: also route 'error' operations to direct result path
3. IF condition: also check error != true AND operation != 'error'
4. Format API Result: detect API errors and return friendly message
"""

import json
import requests
import time

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9.sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

WORKFLOW_ID = "3dYkcNR1hikb45hR"


def build_workflow():
    """Build the fixed Notion Agent workflow."""

    # -- Trigger (unchanged) --
    trigger = {
        "parameters": {"inputSource": "passthrough"},
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [0, 0],
        "id": "4fd6e6ac-f2eb-4873-baf4-892c53705629",
        "name": "Trigger"
    }

    # -- Extract Query (unchanged) --
    extract_query = {
        "parameters": {
            "jsCode": "\nconst input = $input.first().json;\nconst query = input.query || input.chatInput || input.text || JSON.stringify(input);\nreturn [{json: {query}}];\n"
        },
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [300, 0],
        "id": "3696cdf1-9d43-4e1c-833c-2e4290793c75",
        "name": "Extract Query"
    }

    # -- Claude Notion Agent (unchanged) --
    # Read the system prompt from the existing workflow
    with open("/tmp/notion_agent_wf.json") as f:
        existing = json.load(f)
    claude_node = None
    for n in existing["nodes"]:
        if n["name"] == "Claude Notion Agent":
            claude_node = n
            break

    # -- Build Request (FIXED: also detect error and block invalid endpoints) --
    build_request_code = r"""
const raw = $json.content?.[0]?.text || $json.output || $json.text || '';

// Extract JSON from Claude's response (handle markdown code blocks)
let jsonStr = raw;
const jsonMatch = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
if (jsonMatch) {
  jsonStr = jsonMatch[1].trim();
} else {
  const objMatch = raw.match(/\{[\s\S]*\}/);
  if (objMatch) jsonStr = objMatch[0];
}

let parsed;
try {
  parsed = JSON.parse(jsonStr);
} catch (e) {
  return [{json: {
    operation: 'error',
    method: null,
    endpoint: null,
    body: null,
    summary: 'Erreur de parsing JSON: ' + e.message + ' — Raw: ' + raw.substring(0, 500),
    error: true
  }}];
}

const operation = parsed.operation || 'unknown';
const endpoint = parsed.endpoint || '';

// Validate endpoint format for operations that need API calls
if (['query', 'create', 'update', 'get', 'search'].includes(operation)) {
  if (!endpoint || !endpoint.startsWith('/v1/')) {
    return [{json: {
      operation: 'error',
      method: null,
      endpoint: null,
      body: null,
      summary: 'Endpoint invalide genere par Claude: "' + endpoint + '" — Requete: ' + $('Extract Query').first().json.query.substring(0, 200),
      error: true
    }}];
  }
}

return [{json: {
  operation,
  method: parsed.method || 'GET',
  endpoint,
  body: parsed.body || {},
  summary: parsed.summary || '',
  error: false
}}];
"""

    build_request = {
        "parameters": {"jsCode": build_request_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [900, 0],
        "id": "146d4129-c27d-498d-b4cd-784700f0bbd7",
        "name": "Build Request"
    }

    # -- IF Needs API Call (FIXED: also check error != true AND operation not in error/list_schemas) --
    if_node = {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "loose",
                    "version": 2
                },
                "conditions": [
                    {
                        "id": "cond-not-list-schemas",
                        "leftValue": "={{ $json.operation }}",
                        "rightValue": "list_schemas",
                        "operator": {"type": "string", "operation": "notEquals"}
                    },
                    {
                        "id": "cond-not-error-op",
                        "leftValue": "={{ $json.operation }}",
                        "rightValue": "error",
                        "operator": {"type": "string", "operation": "notEquals"}
                    },
                    {
                        "id": "cond-no-error-flag",
                        "leftValue": "={{ $json.error }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "notEquals"}
                    }
                ],
                "combinator": "and"
            },
            "options": {}
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [1200, 0],
        "id": "78b05b36-0205-42e9-a9ab-b14af092eebc",
        "name": "IF Needs API Call"
    }

    # -- HTTP Request Notion (FIXED: add onError + retry) --
    http_request = {
        "parameters": {
            "method": "={{ $json.method }}",
            "url": "=https://api.notion.com{{ $json.endpoint }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.body || {}) }}",
            "options": {
                "response": {
                    "response": {
                        "fullResponse": False
                    }
                }
            }
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1500, -100],
        "id": "83c96ca9-28fa-4c60-99d1-30f5688c62b3",
        "name": "HTTP Request Notion",
        "credentials": {
            "notionApi": {"id": "FPqqVYnRbUnwRzrY", "name": "Notion account"}
        },
        # KEY FIX: continue on error instead of crashing
        "onError": "continueRegularOutput",
        "retryOnFail": True,
        "maxTries": 2,
        "waitBetweenTries": 2000
    }

    # -- Format API Result (FIXED: handle API errors gracefully) --
    format_api_code = r"""
const operation = $('Build Request').first().json.operation;
const summary = $('Build Request').first().json.summary;
const apiResult = $json;

// Check if the HTTP request returned an error
if (apiResult.error || apiResult.status === 'error' || apiResult.object === 'error') {
  const errMsg = apiResult.message || apiResult.error?.message || apiResult.error || 'Erreur inconnue';
  const errStatus = apiResult.status || apiResult.code || '';
  return [{json: {
    response: 'Erreur API Notion: ' + errMsg + (errStatus ? ' (status: ' + errStatus + ')' : '') + '\n\nRequete: ' + summary
  }}];
}

// Check if node had execution error (continueOnFail data)
if (apiResult.$error) {
  return [{json: {
    response: 'Erreur API Notion: ' + (apiResult.$error.message || 'Erreur inconnue') + '\n\nRequete: ' + summary
  }}];
}

let response = summary + '\n\n';

if (operation === 'query') {
  const results = apiResult.results || [];
  if (results.length === 0) {
    response += 'Aucun resultat trouve.';
  } else {
    response += results.length + ' resultat(s) :\n';
    for (const page of results) {
      const props = page.properties || {};
      const title = Object.values(props).find(p => p.type === 'title');
      const name = title?.title?.[0]?.plain_text || page.id;
      const status = Object.values(props).find(p => p.type === 'select' && p.select);
      const statusType = Object.values(props).find(p => p.type === 'status' && p.status);
      response += '- ' + name;
      if (status?.select?.name) response += ' [' + status.select.name + ']';
      if (statusType?.status?.name) response += ' [' + statusType.status.name + ']';
      response += ' (id: ' + page.id.substring(0, 8) + '...)\n';
    }
  }
} else if (operation === 'create') {
  response += 'Page creee avec succes. ID: ' + (apiResult.id || 'inconnu');
} else if (operation === 'update') {
  response += 'Page mise a jour avec succes. ID: ' + (apiResult.id || 'inconnu');
} else if (operation === 'search') {
  const results = apiResult.results || [];
  if (results.length === 0) {
    response += 'Aucun resultat pour cette recherche.';
  } else {
    response += results.length + ' resultat(s) :\n';
    for (const page of results) {
      const props = page.properties || {};
      const title = Object.values(props).find(p => p.type === 'title');
      const name = title?.title?.[0]?.plain_text || page.id;
      response += '- ' + name + ' (id: ' + page.id.substring(0, 8) + '...)\n';
    }
  }
} else if (operation === 'get') {
  const props = apiResult.properties || {};
  response += 'Page: ' + (apiResult.id || 'inconnu') + '\n';
  for (const [key, val] of Object.entries(props)) {
    if (val.type === 'title') {
      response += key + ': ' + (val.title?.[0]?.plain_text || '') + '\n';
    } else if (val.type === 'select') {
      response += key + ': ' + (val.select?.name || '') + '\n';
    } else if (val.type === 'status') {
      response += key + ': ' + (val.status?.name || '') + '\n';
    } else if (val.type === 'number') {
      response += key + ': ' + (val.number ?? '') + '\n';
    } else if (val.type === 'date') {
      response += key + ': ' + (val.date?.start || '') + '\n';
    } else if (val.type === 'rich_text') {
      response += key + ': ' + (val.rich_text?.[0]?.plain_text || '') + '\n';
    } else if (val.type === 'formula') {
      response += key + ': ' + (val.formula?.number ?? val.formula?.string ?? '') + '\n';
    } else if (val.type === 'multi_select') {
      const vals = (val.multi_select || []).map(v => v.name).join(', ');
      response += key + ': ' + vals + '\n';
    } else if (val.type === 'relation') {
      response += key + ': ' + (val.relation || []).length + ' relation(s)\n';
    } else if (val.type === 'rollup') {
      const r = val.rollup;
      if (r?.type === 'number') response += key + ': ' + (r.number ?? '') + '\n';
    }
  }
} else {
  response += JSON.stringify(apiResult).substring(0, 2000);
}

return [{json: {response}}];
"""

    format_api = {
        "parameters": {"jsCode": format_api_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1800, -100],
        "id": "96a88cdc-a6e1-4958-a49e-8b7037d8e8da",
        "name": "Format API Result"
    }

    # -- Format Direct Result (unchanged) --
    format_direct = {
        "parameters": {
            "jsCode": "\nconst data = $json;\nif (data.error) {\n  return [{json: {response: 'Erreur: ' + data.summary}}];\n}\nreturn [{json: {response: data.summary}}];\n"
        },
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1500, 200],
        "id": "671bfb35-2367-4d84-b88c-0494a8a6199c",
        "name": "Format Direct Result"
    }

    nodes = [trigger, extract_query, claude_node, build_request,
             if_node, http_request, format_api, format_direct]

    connections = {
        "Trigger": {"main": [[{"node": "Extract Query", "type": "main", "index": 0}]]},
        "Extract Query": {"main": [[{"node": "Claude Notion Agent", "type": "main", "index": 0}]]},
        "Claude Notion Agent": {"main": [[{"node": "Build Request", "type": "main", "index": 0}]]},
        "Build Request": {"main": [[{"node": "IF Needs API Call", "type": "main", "index": 0}]]},
        "IF Needs API Call": {
            "main": [
                [{"node": "HTTP Request Notion", "type": "main", "index": 0}],
                [{"node": "Format Direct Result", "type": "main", "index": 0}]
            ]
        },
        "HTTP Request Notion": {"main": [[{"node": "Format API Result", "type": "main", "index": 0}]]}
    }

    return {
        "name": "Sub: Notion Agent - Couche 3b",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Paris",
            "callerPolicy": "workflowsFromSameOwner"
        }
    }


def main():
    workflow = build_workflow()

    # Deactivate first
    print("1. Deactivating workflow...")
    r = requests.post(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}/deactivate",
        headers=HEADERS
    )
    print(f"   Status: {r.status_code}")
    time.sleep(2)

    # Update
    print("2. Updating workflow with error handling...")
    r = requests.put(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=HEADERS,
        json=workflow
    )
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        print(f"   Error: {r.text[:500]}")
        return False

    time.sleep(2)

    # Reactivate
    print("3. Reactivating workflow...")
    r = requests.post(
        f"{N8N_URL}/api/v1/workflows/{WORKFLOW_ID}/activate",
        headers=HEADERS
    )
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"   Active: {data.get('active')}")
    else:
        print(f"   Error: {r.text[:300]}")
        return False

    print("\nDone! Changes:")
    print("  - HTTP Request Notion: onError=continueRegularOutput (no more crashes)")
    print("  - Build Request: validates endpoints, routes errors to direct result")
    print("  - IF: 3 conditions (not list_schemas AND not error AND error!=true)")
    print("  - Format API Result: handles API errors + status type + multi_select + rollup")
    return True


if __name__ == "__main__":
    main()
