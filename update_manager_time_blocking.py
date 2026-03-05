#!/usr/bin/env python3
"""Add time_blocking tool to Manager Bot and update system prompt."""

import json
import requests
import os

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

MANAGER_WF_ID = "614eolE935GVV5sT"
TIME_BLOCKING_WF_ID = "RJeiCCV0UjPCPK3b"


def update_manager():
    # Fetch current workflow
    resp = requests.get(
        f"{N8N_URL}/api/v1/workflows/{MANAGER_WF_ID}",
        headers=HEADERS,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch Manager Bot: {resp.status_code}")
        return

    data = resp.json()

    # 1. Add time_blocking tool node
    new_tool_node = {
        "id": "tb-tool-node-001",
        "name": "Tool: time_blocking",
        "type": "@n8n/n8n-nodes-langchain.toolWorkflow",
        "typeVersion": 2,
        "position": [1300, 900],
        "parameters": {
            "name": "time_blocking",
            "description": (
                "Gestion du planning et des blocs de temps (Time Blocks DB). "
                "Actions disponibles:\n"
                "- 'read_today' : Voir le planning du jour\n"
                "- 'read_date YYYY-MM-DD' : Voir le planning d'une date\n"
                "- 'create HH:MM HH:MM Nom | Type | Priority' : Creer un bloc (Types: Task, Sport, Routine, Meeting, Break, Personal)\n"
                "- 'modify BLOCK_ID field value' : Modifier un bloc (fields: nom, type, priority, notes, time HH:MM-HH:MM, recurrence)\n"
                "- 'delete BLOCK_ID' : Supprimer un bloc\n"
                "- 'reschedule [contrainte]' : Reorganiser le planning du jour selon les contraintes sport\n\n"
                "REGLES SPORT: Muscu uniquement avant 8h ou apres 20h. Course de preference le soir. "
                "JAMAIS de sport pendant les heures de travail (9h-21h45)."
            ),
            "workflowId": {
                "__rl": True,
                "value": TIME_BLOCKING_WF_ID,
                "mode": "id",
            },
        },
    }

    data["nodes"].append(new_tool_node)

    # 2. Add connection from new tool to Agent Orchestrator
    tool_connection_name = "Tool: time_blocking"
    data["connections"][tool_connection_name] = {
        "ai_tool": [
            [{"node": "Agent Orchestrator", "type": "ai_tool", "index": 0}]
        ]
    }

    # 3. Update system prompt to include time_blocking info
    for node in data["nodes"]:
        if node.get("type") == "@n8n/n8n-nodes-langchain.agent":
            old_prompt = node["parameters"]["options"]["systemMessage"]

            # Add time_blocking to the tools section
            old_prompt = old_prompt.replace(
                '10. project : Gestion projets (update statut, notes, lister). Format: "update [nom] | [status] | [note]"',
                '10. project : Gestion projets (update statut, notes, lister). Format: "update [nom] | [status] | [note]"\n'
                '11. time_blocking : Lire/creer/modifier/supprimer des blocs de temps. Voir le planning du jour ou d\'une date. Reorganiser le planning. UTILISE-LE quand Chris demande son planning, veut decaler un bloc, ou a un empechement.\n'
                '12. sport_coach : Coach sport IA (calisthenics, muscu, course, nutrition, recuperation).'
            )

            # Add time_blocking to shortcuts
            old_prompt = old_prompt.replace(
                '/knowledge\u2192knowledge, /notion\u2192notion, /projet\u2192project',
                '/knowledge\u2192knowledge, /notion\u2192notion, /projet\u2192project, /planning\u2192time_blocking'
            )

            # Add time blocking rules
            time_blocking_rules = """

== PLANNING & TIME BLOCKING ==
Chris a un systeme de Time Blocking dans Notion (Time Blocks DB).
- Quand il demande son planning : utilise time_blocking (read_today)
- Quand il veut modifier/decaler un bloc : utilise time_blocking (modify ou reschedule)
- Quand il a un empechement : utilise time_blocking (reschedule + la contrainte)
- Le matin (avec le Daily CRON 6h30), le planning est auto-genere et envoye sur Telegram

CONTRAINTES SPORT STRICTES:
- Heures de travail Chris : 9h-21h45 (bientot 8h-20h)
- Musculation : UNIQUEMENT avant le travail (avant 8h) ou apres le travail (apres 20h). JAMAIS pendant la journee.
- Course a pied : de preference le soir (apres le travail). Sinon tres tot le matin.
- Objectifs Beeminder : 4x musculation/semaine + 5x course/semaine
- Si Chris demande quand faire du sport, respecte ces contraintes."""

            old_prompt = old_prompt.replace(
                "== TON ==",
                time_blocking_rules + "\n\n== TON =="
            )

            # Also add chaining example
            old_prompt = old_prompt.replace(
                '- "Regarde ce que j\'ai fait sur GitHub" \u2192 knowledge \u2192 project (update les taches correspondantes)',
                '- "Regarde ce que j\'ai fait sur GitHub" \u2192 knowledge \u2192 project (update les taches correspondantes)\n'
                '- "C\'est quoi mon planning ?" \u2192 time_blocking (read_today)\n'
                '- "Decale ma muscu" \u2192 time_blocking (reschedule decaler musculation)\n'
                '- "J\'ai un empechement a 14h" \u2192 time_blocking (reschedule empechement 14h)'
            )

            node["parameters"]["options"]["systemMessage"] = old_prompt
            print(f"[OK] System prompt updated ({len(old_prompt)} chars)")
            break

    # 4. Save updated workflow
    # Remove fields that shouldn't be in PUT request
    for key in ["updatedAt", "createdAt", "isArchived", "id", "staticData",
                 "meta", "pinData", "versionId", "activeVersionId",
                 "versionCounter", "triggerCount", "shared", "tags",
                 "activeVersion", "description", "active"]:
        data.pop(key, None)

    resp = requests.put(
        f"{N8N_URL}/api/v1/workflows/{MANAGER_WF_ID}",
        headers=HEADERS,
        json=data,
        timeout=30,
    )
    if resp.status_code == 200:
        print(f"[OK] Manager Bot updated with time_blocking tool")
    else:
        print(f"[ERROR] Update failed: {resp.status_code}")
        print(resp.text[:500])


if __name__ == "__main__":
    update_manager()
