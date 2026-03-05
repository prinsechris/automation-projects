#!/usr/bin/env python3
"""Update Weekly Time Blocks Generator with sport time constraints.

Changes to Build Week Claude Prompt:
- Muscu: only before 8h or after 20h (never during work hours)
- Course: preferably evening after work, or very early morning
- Work hours: 9h-21h45 (soon 8h-20h)
- Beeminder goals: 4x muscu/week, 5x course/week
"""

import json
import requests
import os

N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

WEEKLY_TB_WF_ID = "FCYOYGOYaE0vT5Oj"


def update_workflow():
    resp = requests.get(
        f"{N8N_URL}/api/v1/workflows/{WEEKLY_TB_WF_ID}",
        headers=HEADERS,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch: {resp.status_code}")
        return

    data = resp.json()

    # Update Build Week Claude Prompt
    for node in data["nodes"]:
        if node.get("name") == "Build Week Claude Prompt":
            code = node["parameters"]["jsCode"]

            # Replace the system prompt
            old_rules = """REGLES:
1. Les blocs SPORT sont deja planifies par le Sport Coach AI. Integre-les tels quels dans le planning, ne les modifie pas.
2. Place les taches business dans les creneaux LIBRES (pas de conflit avec calendrier Google ni sport).
3. Deep Work le matin (8h-12h), meetings/admin apres-midi, habitudes soir.
4. Blocs de 30min minimum, 2h maximum. Pauses 15min entre blocs intenses.
5. Priorise: Critical > High > Medium > Low.
6. Estime la duree si non specifiee (60min par defaut).
7. Au moins 1 jour avec charge reduite (samedi ou dimanche)."""

            new_rules = """REGLES:
1. Les blocs SPORT sont deja planifies par le Sport Coach AI. Integre-les dans le planning.
2. Place les taches business dans les creneaux LIBRES (pas de conflit avec calendrier Google ni sport).
3. Deep Work le matin (9h-12h), meetings/admin apres-midi, habitudes soir.
4. Blocs de 30min minimum, 2h maximum. Pauses 15min entre blocs intenses.
5. Priorise: Critical > High > Medium > Low.
6. Estime la duree si non specifiee (60min par defaut).
7. Au moins 1 jour avec charge reduite (samedi ou dimanche).

CONTRAINTES HORAIRES SPORT (TRES IMPORTANT):
- Chris travaille de 9h a 21h45 (bientot 8h-20h). JAMAIS de sport pendant le travail.
- MUSCULATION: UNIQUEMENT avant 8h du matin OU apres 20h le soir. 4 seances/semaine.
- COURSE A PIED: De preference le soir (20h-21h) apres le travail. Sinon tot le matin (6h-7h30). 5 seances/semaine.
- Conseil optimal: Musculation le MATIN (6h-7h45) + Course le SOIR (20h-21h).
- Si le Sport Coach AI propose des horaires pendant les heures de travail, DECALE-LES aux creneaux autorises.
- Les blocs sport doivent respecter Beeminder: 4x muscu/sem + 5x course/sem minimum."""

            if old_rules in code:
                code = code.replace(old_rules, new_rules)
                node["parameters"]["jsCode"] = code
                print("[OK] Build Week Claude Prompt updated with sport constraints")
            else:
                print("[WARN] Could not find exact rules text to replace")
                # Try a softer approach - add constraints after the existing rules
                insert_point = code.find("FORMAT JSON STRICT:")
                if insert_point > 0:
                    sport_constraints = """
CONTRAINTES HORAIRES SPORT (TRES IMPORTANT):
- Chris travaille de 9h a 21h45 (bientot 8h-20h). JAMAIS de sport pendant le travail.
- MUSCULATION: UNIQUEMENT avant 8h du matin OU apres 20h le soir. 4 seances/semaine.
- COURSE A PIED: De preference le soir (20h-21h) apres le travail. Sinon tot le matin (6h-7h30). 5 seances/semaine.
- Conseil optimal: Musculation le MATIN (6h-7h45) + Course le SOIR (20h-21h).
- Si le Sport Coach AI propose des horaires pendant les heures de travail, DECALE-LES aux creneaux autorises.

"""
                    code = code[:insert_point] + sport_constraints + code[insert_point:]
                    node["parameters"]["jsCode"] = code
                    print("[OK] Sport constraints inserted before FORMAT section")
                else:
                    print("[ERROR] Cannot find insertion point")
            break

    # Remove read-only fields
    for key in ["updatedAt", "createdAt", "isArchived", "id", "staticData",
                 "meta", "pinData", "versionId", "activeVersionId",
                 "versionCounter", "triggerCount", "shared", "tags",
                 "activeVersion", "description", "active"]:
        data.pop(key, None)

    resp = requests.put(
        f"{N8N_URL}/api/v1/workflows/{WEEKLY_TB_WF_ID}",
        headers=HEADERS,
        json=data,
        timeout=30,
    )
    if resp.status_code == 200:
        print(f"[OK] Weekly Time Blocks Generator updated")
    else:
        print(f"[ERROR] Update failed: {resp.status_code}")
        print(resp.text[:500])


if __name__ == "__main__":
    update_workflow()
