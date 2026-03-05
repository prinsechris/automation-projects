#!/usr/bin/env python3
"""Update Daily Time Blocking workflow with sport constraints.

Changes:
1. Update Claude prompt to enforce sport time constraints
2. Muscu: only before 8h or after 20h
3. Course: preferably evening (after work)
4. Work hours: 9h-21h45 (soon 8h-20h)
5. Beeminder goals: 4x muscu/week, 5x course/week
"""

import json
import requests
import os

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

DAILY_TB_WF_ID = "rpAOAx7bQMAalZI4"


def update_workflow():
    # Fetch current workflow
    resp = requests.get(
        f"{N8N_URL}/api/v1/workflows/{DAILY_TB_WF_ID}",
        headers=HEADERS,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch workflow: {resp.status_code}")
        return

    data = resp.json()

    # Find the Build Claude Prompt node and update its system prompt
    for node in data["nodes"]:
        if node.get("name") == "Build Claude Prompt":
            old_code = node["parameters"]["jsCode"]

            # Replace the system prompt in the code
            new_system_prompt = """Tu es un assistant de planification quotidienne pour Chris, entrepreneur et employe a Avignon.
Cree un planning heure par heure optimise pour sa journee.

REGLES STRICTES:
- Ne JAMAIS planifier sur les creneaux bloques (travail, RDV, etc.)

CONTRAINTES SPORT (TRES IMPORTANT):
- MUSCULATION: UNIQUEMENT avant 8h du matin OU apres 20h le soir. JAMAIS entre 8h et 20h. Chris fait de la muscu soit a la salle soit a la maison.
- COURSE A PIED: De preference le soir (apres le travail, vers 20h-21h). Sinon tres tot le matin (6h-7h). JAMAIS pendant les heures de travail.
- Chris travaille de 9h a 21h45 (bientot 8h-20h). Le sport se fait AVANT ou APRES le travail, JAMAIS PENDANT.
- Objectifs hebdo: 4x musculation/semaine + 5x course/semaine (Beeminder)
- Conseil optimal: Musculation le MATIN (avant travail) + Course le SOIR (apres travail)
- Si jour de repos sport, ne pas forcer

REGLES PLANNING:
- Taches business Critical/High en debut de journee quand l'energie est haute
- Pause de 15min entre les blocs de travail de 2h+
- Dejeuner entre 12h-14h (30min minimum) sauf si creneau bloque
- Taches faciles/admin en fin de journee
- Si peu de temps libre (<3h), garder UNIQUEMENT Critical/High + sport
- Arrondir les heures a 00, 15, 30, 45 minutes
- Retourne UNIQUEMENT un JSON valide, rien d'autre

FORMAT DE SORTIE (JSON strict):
{
  "timeBlocks": [
    {"start": "HH:MM", "end": "HH:MM", "activity": "Nom", "type": "sport|task|habit|break|meal", "priority": "Critical|High|Medium|Low", "details": "Note courte"}
  ],
  "summary": "Resume de la journee en 1 phrase",
  "tip": "Conseil motivant pour la journee"
}"""

            # Replace the old system prompt
            new_code = old_code.replace(
                old_code[old_code.index("const systemPrompt = `"):old_code.index("`;", old_code.index("const systemPrompt = `")) + 2],
                f"const systemPrompt = `{new_system_prompt}`;"
            )

            node["parameters"]["jsCode"] = new_code
            print(f"[OK] Build Claude Prompt updated")
            break
    else:
        print("[WARN] Build Claude Prompt node not found")

    # Remove read-only fields
    for key in ["updatedAt", "createdAt", "isArchived", "id", "staticData",
                 "meta", "pinData", "versionId", "activeVersionId",
                 "versionCounter", "triggerCount", "shared", "tags",
                 "activeVersion", "description", "active"]:
        data.pop(key, None)

    resp = requests.put(
        f"{N8N_URL}/api/v1/workflows/{DAILY_TB_WF_ID}",
        headers=HEADERS,
        json=data,
        timeout=30,
    )
    if resp.status_code == 200:
        print(f"[OK] Daily Time Blocking workflow updated")
    else:
        print(f"[ERROR] Update failed: {resp.status_code}")
        print(resp.text[:500])


if __name__ == "__main__":
    update_workflow()
