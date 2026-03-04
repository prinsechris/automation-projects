#!/usr/bin/env python3
"""Fix all Phase 2b workflow bugs identified during testing.

Fixes applied:
1. Daily Quest Generator (q6T5r24RoJlQoNXe):
   - Remove non-existent "Active" checkbox filter from Habits query
   - Change "Current Streak" (formula) to "Streak Days" (number)
   - Fix Player Stats: use formula access for Level/Gold, correct XP property name

2. Monthly Review (6sB9qU8ONHLMLb8U):
   - Fix Revenue query: "Date" -> "Date Paiement"
   - Fix Revenue property paths: Montant, Client (rich_text), Description (title)
   - Fix Player Stats: correct XP property name (EXP to Next Level)

3. Auto-Scheduling (3BQFEQBnBQV4Tzqe):
   - Add Sub-task to Type filter in all 3 query nodes
   - Deduplicate overdue tasks from dayLoad in Merge Queries
"""

import json
import requests
import sys

# ─── n8n API ──────────────────────────────────────────────────────────────────
N8N_URL = "https://n8n.srv842982.hstgr.cloud"
N8N_API_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJlZDRhYjhiOS0xNDM5LTQ4NGQtYjc3NS1kNDc5ZTVkZWY2ZWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQzMTUzLCJleHAiOjE3NzY3MjI0MDB9."
    "sPuCFUx8Sf8wZxgycyTrpHgF3QA9mtTF94rmAVZg8C4"
)
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def get_workflow(wf_id: str) -> dict:
    r = requests.get(f"{N8N_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def update_workflow(wf_id: str, data: dict) -> dict:
    # n8n API PUT requires: name, nodes, connections, settings
    payload = {
        "name": data["name"],
        "nodes": data["nodes"],
        "connections": data["connections"],
        "settings": data.get("settings", {}),
    }
    r = requests.put(f"{N8N_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
    if r.status_code >= 400:
        print(f"  [ERROR] PUT {wf_id}: {r.status_code} - {r.text[:200]}")
    r.raise_for_status()
    return r.json()


def find_node(nodes: list, name: str) -> dict | None:
    for n in nodes:
        if n["name"] == name:
            return n
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1: Daily Quest Generator
# ═══════════════════════════════════════════════════════════════════════════════
def fix_quest_generator() -> None:
    WF_ID = "q6T5r24RoJlQoNXe"
    print(f"\n{'='*60}")
    print(f"FIX 1: Daily Quest Generator ({WF_ID})")
    print(f"{'='*60}")

    wf = get_workflow(WF_ID)
    nodes = wf["nodes"]
    fixes = 0

    # --- Fix 1a: Remove "Active" checkbox filter from Habits query ---
    node = find_node(nodes, "Query Habits")
    if node:
        old_body = node["parameters"].get("jsonBody", "")
        if '"Active"' in old_body:
            node["parameters"]["jsonBody"] = '{"page_size": 100}'
            print("  [OK] Query Habits: removed non-existent 'Active' filter")
            fixes += 1
        else:
            print("  [SKIP] Query Habits: 'Active' filter already removed")

    # --- Fix 1b: Fix Build Quest List code ---
    node = find_node(nodes, "Build Quest List")
    if node:
        code = node["parameters"].get("jsCode", "")
        changed = False

        # Fix: "Current Streak" -> "Streak Days"
        if "'Current Streak'" in code:
            code = code.replace("'Current Streak'", "'Streak Days'")
            print("  [OK] Build Quest List: 'Current Streak' -> 'Streak Days'")
            changed = True
            fixes += 1

        # Fix: Player Stats formula access
        # Replace the entire Player Stats section
        old_player_block = """let level = '?', xpTotal = '?', gold = '?';
try {
  const playerData = $('Query Player Stats').first().json;
  const props = playerData.properties || {};

  // Try common property names for Level, XP, Gold
  const levelProp = props['Level'] || props['Niveau'] || {};
  level = levelProp.number != null ? levelProp.number : '?';

  const xpProp = props['XP'] || props['Total XP'] || props['Experience'] || {};
  xpTotal = xpProp.number != null ? xpProp.number : '?';

  const goldProp = props['Gold'] || props['Or'] || props['Coins'] || {};
  gold = goldProp.number != null ? goldProp.number : '?';
} catch(e) {
  // Player stats unavailable, use defaults
}"""

        new_player_block = """let level = '?', xpTotal = '?', gold = '?';
try {
  const playerData = $('Query Player Stats').first().json;
  const props = playerData.properties || {};

  // Helper: read formula or number property
  function getFormulaOrNumber(p) {
    if (!p) return null;
    if (p.type === 'formula' && p.formula) {
      if (p.formula.type === 'number') return p.formula.number;
      if (p.formula.type === 'string') return p.formula.string;
    }
    if (p.type === 'number') return p.number;
    return null;
  }

  // Level is a formula property
  const lv = getFormulaOrNumber(props['Level']);
  level = lv != null ? lv : '?';

  // EXP to Next Level is a number property (no XP/Total XP on Player Stats)
  const xp = getFormulaOrNumber(props['EXP to Next Level']);
  xpTotal = xp != null ? xp : '?';

  // Gold is a formula property
  const gv = getFormulaOrNumber(props['Gold']);
  gold = gv != null ? gv : '?';
} catch(e) {
  // Player stats unavailable, use defaults
}"""

        if old_player_block in code:
            code = code.replace(old_player_block, new_player_block)
            print("  [OK] Build Quest List: fixed Player Stats formula access + property names")
            changed = True
            fixes += 1
        else:
            print("  [WARN] Build Quest List: Player Stats block not found (may need manual fix)")

        if changed:
            node["parameters"]["jsCode"] = code

    # Save
    if fixes > 0:
        update_workflow(WF_ID, wf)
        print(f"  >>> Saved {fixes} fixes to Daily Quest Generator")
    else:
        print("  >>> No fixes needed")


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2: Monthly Review
# ═══════════════════════════════════════════════════════════════════════════════
def fix_monthly_review() -> None:
    WF_ID = "6sB9qU8ONHLMLb8U"
    print(f"\n{'='*60}")
    print(f"FIX 2: Monthly Review ({WF_ID})")
    print(f"{'='*60}")

    wf = get_workflow(WF_ID)
    nodes = wf["nodes"]
    fixes = 0

    # --- Fix 2a: Revenue query date property ---
    node = find_node(nodes, "Query Revenue")
    if node:
        body = node["parameters"].get("jsonBody", "")
        if '"Date"' in body and '"Date Paiement"' not in body:
            body = body.replace('"Date"', '"Date Paiement"')
            node["parameters"]["jsonBody"] = body
            print("  [OK] Query Revenue: 'Date' -> 'Date Paiement'")
            fixes += 1
        else:
            print("  [SKIP] Query Revenue: already using 'Date Paiement'")

    # --- Fix 2b: Aggregate All Data code ---
    node = find_node(nodes, "Aggregate All Data")
    if node:
        code = node["parameters"].get("jsCode", "")
        changed = False

        # Fix Revenue amount property: prioritize Montant
        old_amount = "const amount = getNumber(r, 'Amount') || getNumber(r, 'Montant') || getNumber(r, 'Revenue') || 0;"
        new_amount = "const amount = getNumber(r, 'Montant') || getNumber(r, 'Amount') || 0;"
        if old_amount in code:
            code = code.replace(old_amount, new_amount)
            print("  [OK] Aggregate: Revenue amount -> 'Montant' first")
            changed = True
            fixes += 1

        # Fix Revenue source: Client is rich_text, not select
        old_source = "const source = getSelectValue(r, 'Source') || getSelectValue(r, 'Client') || 'Autre';"
        new_source = """// Client is rich_text in Revenue Log, not select
    const clientText = ((r.properties || {})['Client']?.rich_text || []).map(t => t.plain_text || '').join('') || '';
    const source = getSelectValue(r, 'Service') || clientText || 'Autre';"""
        if old_source in code:
            code = code.replace(old_source, new_source)
            print("  [OK] Aggregate: Revenue source -> read Client as rich_text, use Service as primary")
            changed = True
            fixes += 1

        # Fix Player Stats XP property name
        old_xp = "const playerXP = getNumber(playerRaw, 'XP') || getNumber(playerRaw, 'Total XP') || 0;"
        new_xp = "const playerXP = getNumber(playerRaw, 'EXP to Next Level') || 0;"
        if old_xp in code:
            code = code.replace(old_xp, new_xp)
            print("  [OK] Aggregate: Player Stats XP -> 'EXP to Next Level'")
            changed = True
            fixes += 1

        # Fix Player Stats Gold property
        old_gold = "const playerGold = getNumber(playerRaw, 'Gold') || getNumber(playerRaw, 'Total Gold') || 0;"
        new_gold = "const playerGold = getNumber(playerRaw, 'Gold') || 0;"
        if old_gold in code:
            code = code.replace(old_gold, new_gold)
            print("  [OK] Aggregate: Player Stats Gold -> 'Gold' only")
            changed = True
            fixes += 1

        if changed:
            node["parameters"]["jsCode"] = code

    # Save
    if fixes > 0:
        update_workflow(WF_ID, wf)
        print(f"  >>> Saved {fixes} fixes to Monthly Review")
    else:
        print("  >>> No fixes needed")


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 3: Auto-Scheduling
# ═══════════════════════════════════════════════════════════════════════════════
def fix_auto_scheduling() -> None:
    WF_ID = "3BQFEQBnBQV4Tzqe"
    print(f"\n{'='*60}")
    print(f"FIX 3: Auto-Scheduling ({WF_ID})")
    print(f"{'='*60}")

    wf = get_workflow(WF_ID)
    nodes = wf["nodes"]
    fixes = 0

    # --- Fix 3a: Add Sub-task to Type filter in all query nodes ---
    type_task_only = '"Type", "select": {"equals": "Task"}'
    type_task_or_subtask = '"or": [{"property": "Type", "select": {"equals": "Task"}}, {"property": "Type", "select": {"equals": "Sub-task"}}]'

    for node_name in ["Query Unscheduled Tasks", "Query Scheduled This Week", "Query Overdue Tasks"]:
        node = find_node(nodes, node_name)
        if not node:
            print(f"  [SKIP] {node_name}: node not found")
            continue

        body = node["parameters"].get("jsonBody", "")
        old_type_filter = '{"property": "Type", "select": {"equals": "Task"}}'
        new_type_filter = '{"or": [{"property": "Type", "select": {"equals": "Task"}}, {"property": "Type", "select": {"equals": "Sub-task"}}]}'

        if old_type_filter in body:
            body = body.replace(old_type_filter, new_type_filter)
            node["parameters"]["jsonBody"] = body
            print(f"  [OK] {node_name}: added Sub-task to Type filter")
            fixes += 1
        else:
            print(f"  [SKIP] {node_name}: Type filter already updated or not found")

    # --- Fix 3b: Deduplicate overdue in Merge Queries ---
    node = find_node(nodes, "Merge Queries")
    if node:
        code = node["parameters"].get("jsCode", "")

        # Add deduplication: remove overdue tasks that are already in scheduled
        old_total = "const totalToSchedule = unscheduled.length + overdue.length;"
        new_total = """// Deduplicate: remove overdue tasks already in scheduled (same week overlap)
const scheduledIds = new Set(scheduled.map(t => t.id));
const dedupedOverdue = overdue.filter(t => !scheduledIds.has(t.id));

const totalToSchedule = unscheduled.length + dedupedOverdue.length;"""

        if old_total in code:
            code = code.replace(old_total, new_total)

            # Also update the return to use dedupedOverdue
            code = code.replace(
                "  overdue,\n  dayLoad,",
                "  overdue: dedupedOverdue,\n  dayLoad,"
            )
            node["parameters"]["jsCode"] = code
            print("  [OK] Merge Queries: added overdue deduplication")
            fixes += 1

    # Save
    if fixes > 0:
        update_workflow(WF_ID, wf)
        print(f"  >>> Saved {fixes} fixes to Auto-Scheduling")
    else:
        print("  >>> No fixes needed")


def _replace_type_filter(filter_obj: dict) -> None:
    """Recursively replace Type=Task with Type IN (Task, Sub-task) in Notion filter."""
    if not isinstance(filter_obj, dict):
        return

    # Check if this is the Type filter
    if filter_obj.get("property") == "Type" and "select" in filter_obj:
        sel = filter_obj["select"]
        if isinstance(sel, dict) and sel.get("equals") == "Task":
            # Can't modify in place to "or" at this level, need to handle at parent
            pass

    # Recurse into "and" / "or" arrays
    for key in ["and", "or"]:
        if key in filter_obj and isinstance(filter_obj[key], list):
            for i, item in enumerate(filter_obj[key]):
                if (isinstance(item, dict) and
                    item.get("property") == "Type" and
                    isinstance(item.get("select"), dict) and
                    item["select"].get("equals") == "Task"):
                    # Replace with "or" containing Task and Sub-task
                    filter_obj[key][i] = {
                        "or": [
                            {"property": "Type", "select": {"equals": "Task"}},
                            {"property": "Type", "select": {"equals": "Sub-task"}}
                        ]
                    }
                else:
                    _replace_type_filter(item)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Phase 2b Workflow Fixes")
    print("=" * 60)

    try:
        fix_quest_generator()
        fix_monthly_review()
        fix_auto_scheduling()
        print(f"\n{'='*60}")
        print("ALL FIXES APPLIED SUCCESSFULLY")
        print(f"{'='*60}")
    except requests.HTTPError as e:
        print(f"\nERROR: {e}")
        print(f"Response: {e.response.text if e.response else 'N/A'}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
