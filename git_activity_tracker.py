#!/usr/bin/env python3
"""Git Activity Tracker v3 — Autonomous project tracking with velocity predictions.

Pipeline:
1. Fetch commits from GitHub repos
2. Query Notion tasks + goals
3. Claude analyzes commits vs tasks
4. Update tasks (complete/start)
5. Propagate: task → project status → goal progress %
6. Check deadlines
7. Velocity tracking + delivery predictions
8. Send intelligent Telegram recap

Run via cron every 6h + post-push hooks.
"""

import argparse
import fcntl
import json
import os
import re
import sys
import requests
from datetime import datetime, timedelta, timezone

# --- Configuration ---
def _load_secret(path: str) -> str:
    with open(os.path.expanduser(path)) as f:
        return f.read().strip()

GITHUB_TOKEN = _load_secret("~/.github-token")
ANTHROPIC_KEY = _load_secret("~/.anthropic-key")

N8N_BASE = "https://n8n.srv842982.hstgr.cloud/webhook"
SESSION_CLOSER_URL = f"{N8N_BASE}/session-close"
NOTION_QUERY_URL = f"{N8N_BASE}/notion-query"
NOTION_GOALS_URL = f"{N8N_BASE}/notion-goals"
NOTION_UPDATE_URL = f"{N8N_BASE}/notion-update"
NOTION_CREATE_URL = f"{N8N_BASE}/notion-create-task"

REPOS = [
    "prinsechris/AI-Business-Automation-Suite",
    "prinsechris/tiktok-automation-pro",
    "prinsechris/automation-projects",
]

HOURS_WINDOW = 7
LOCKFILE = "/tmp/git_activity_tracker.lock"
VELOCITY_FILE = "/home/claude-agent/n8n-workflows/velocity_history.json"
CHANGELOG_FILE = "/home/claude-agent/n8n-workflows/CHANGELOG.md"

GH_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "git-activity-tracker",
}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# --- Data Fetching ---

def fetch_commits(repo: str, since: str) -> list[dict]:
    """Fetch commits from a GitHub repo since a given time."""
    url = f"https://api.github.com/repos/{repo}/commits"
    try:
        r = requests.get(url, headers=GH_HEADERS, params={"since": since, "per_page": 50}, timeout=15)
        if r.status_code == 200:
            return r.json()
        log(f"  [{repo.split('/')[-1]}] HTTP {r.status_code}")
        return []
    except Exception as e:
        log(f"  [{repo.split('/')[-1]}] Error: {e}")
        return []


def fetch_notion_tasks() -> list[dict]:
    """Fetch active tasks with relations from Notion."""
    try:
        r = requests.post(NOTION_QUERY_URL, json={}, timeout=30)
        if r.status_code != 200:
            log(f"  Notion tasks HTTP {r.status_code}")
            return []
        return r.json().get("tasks", [])
    except Exception as e:
        log(f"  Notion tasks error: {e}")
        return []


def fetch_notion_goals() -> list[dict]:
    """Fetch active goals from Notion."""
    try:
        r = requests.post(NOTION_GOALS_URL, json={}, timeout=30)
        if r.status_code != 200:
            log(f"  Notion goals HTTP {r.status_code}")
            return []
        return r.json().get("goals", [])
    except Exception as e:
        log(f"  Notion goals error: {e}")
        return []


def update_notion_page(page_id: str, properties: dict) -> bool:
    """Update any Notion page's properties via webhook."""
    try:
        r = requests.post(NOTION_UPDATE_URL, json={
            "page_id": page_id,
            "properties": properties
        }, timeout=15)
        return r.status_code == 200
    except Exception as e:
        log(f"  Update error ({page_id[:8]}): {e}")
        return False


def create_notion_task(task: dict) -> bool:
    """Create a new task in Notion."""
    category_map = {
        "Business": "\U0001f4bc Business",
        "Automatisation": "\U0001f916 Automatisation",
        "Perso": "\U0001f3e0 Perso",
    }
    payload = {
        "name": task["name"],
        "type": task.get("type", "Task"),
        "status": task.get("status", "Backlog"),
        "category": category_map.get(task.get("category", "Business"), "\U0001f4bc Business"),
    }
    try:
        r = requests.post(NOTION_CREATE_URL, json=payload, timeout=15)
        return r.status_code == 200
    except Exception as e:
        log(f"  Create error: {e}")
        return False


# --- Summaries ---

def build_git_summary(all_commits: dict[str, list]) -> tuple[str, int]:
    """Build a human-readable git summary."""
    summary = ""
    total = 0
    for repo, commits in all_commits.items():
        if not commits:
            continue
        short_name = repo.split("/")[-1]
        summary += f"\n## {short_name} ({len(commits)} commits)\n"
        for c in commits:
            msg = c.get("commit", {}).get("message", "(no message)").split("\n")[0]
            date = c.get("commit", {}).get("author", {}).get("date", "")[:16]
            sha = c.get("sha", "")[:7]
            summary += f"- [{sha}] {date} — {msg}\n"
            total += 1
    return summary, total


def build_notion_summary(tasks: list[dict]) -> str:
    """Build a summary of current Notion tasks for Claude."""
    summary = "\n## Current Notion Tasks\n"
    for t in tasks:
        upstream_info = f" | Parent: {t['upstream'][0][:8]}" if t.get("upstream") else ""
        summary += (
            f"- [{t['id']}] {t['name']} | Type: {t['type']} | "
            f"Status: {t['status']} | Category: {t['category']}{upstream_info}\n"
        )
    return summary


# --- Claude Analysis ---

def analyze_with_claude(git_summary: str, notion_summary: str) -> dict:
    """Send data to Claude for analysis."""
    prompt = f"""Tu es un assistant de tracking de projets. Analyse les commits Git recents et compare-les avec les taches Notion existantes.

# Commits Git recents
{git_summary}

# Taches Notion actuelles
{notion_summary}

Analyse et retourne un JSON STRICT (pas de texte autour, pas de ```json```) avec cette structure :
{{
  "summary": "Resume en 1-2 phrases de l'activite",
  "tasks_completed": ["notion-page-id-1"],
  "tasks_started": ["notion-page-id-2"],
  "tasks_to_create": [
    {{
      "name": "nouvelle tache detectee",
      "type": "Task",
      "status": "In Progress",
      "category": "Business",
      "reason": "pourquoi creer"
    }}
  ]
}}

Regles :
- tasks_completed : IDs de taches dont les commits montrent clairement que le travail est FINI
- tasks_started : IDs de taches qui ont du travail en cours mais pas fini
- tasks_to_create : nouvelles taches SEULEMENT si le travail ne correspond a AUCUNE tache existante. Sois TRES conservateur — prefere mapper a une tache existante plutot que creer un doublon.
- Si aucun changement : retourne des arrays vides
- IMPORTANT : retourne UNIQUEMENT le JSON brut, rien d'autre"""

    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60,
        )
        if r.status_code == 200:
            content = r.json().get("content", [{}])[0].get("text", "{}")
            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                return json.loads(match.group(0))
            return json.loads(content)
        log(f"  Claude HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log(f"  Claude error: {e}")
    return {"tasks_completed": [], "tasks_started": [], "tasks_to_create": [], "summary": "Error"}


# --- AI Changelog ---

def generate_changelog(git_summary: str, analysis: dict) -> str | None:
    """Generate a professional changelog entry from commits using Claude."""
    prompt = f"""Tu es un redacteur de changelog technique. A partir des commits Git ci-dessous,
genere une entree de changelog claire et professionnelle en francais.

# Commits
{git_summary}

# Contexte
Resume de l'analyse : {analysis.get('summary', 'N/A')}

Genere UNIQUEMENT le contenu markdown de l'entree (pas de date, je l'ajoute moi-meme).
Format :
### Categorie (ex: Fonctionnalites, Corrections, Infrastructure, Documentation)
- Description claire de chaque changement significatif
- Ignore les commits de merge, test, ou chore trivials
- Regroupe les commits lies en un seul point

Si les commits sont uniquement du test/chore sans valeur, retourne juste "Maintenance et tests mineurs."
Sois concis — max 10 lignes."""

    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        if r.status_code == 200:
            return r.json().get("content", [{}])[0].get("text", "").strip()
        log(f"  Changelog Claude HTTP {r.status_code}")
    except Exception as e:
        log(f"  Changelog error: {e}")
    return None


def save_changelog(entry: str, total_commits: int) -> None:
    """Append a changelog entry to CHANGELOG.md."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")
    header = f"\n## [{date_str}] — {total_commits} commits\n\n"

    # Create file with title if it doesn't exist
    if not os.path.exists(CHANGELOG_FILE):
        with open(CHANGELOG_FILE, "w") as f:
            f.write("# Changelog — Adaptive Logic\n\nGenere automatiquement par Git Activity Tracker v3.\n\n---\n")

    with open(CHANGELOG_FILE, "a") as f:
        f.write(header + entry + "\n\n---\n")


# --- Weighted Rollup ---

# Weight multipliers by priority, difficulty, and revenue impact
PRIORITY_WEIGHTS = {
    "Critical": 4.0,
    "High": 3.0,
    "Medium": 2.0,
    "Low": 1.0,
    None: 1.5,  # unset = assume medium-ish
}

DIFFICULTY_WEIGHTS = {
    "3 - Hard": 3.0,
    "2 - Moderate": 2.0,
    "1 - Easy": 1.0,
    None: 1.5,
}

REVENUE_WEIGHTS = {
    "Direct": 2.0,    # stripped emoji prefix
    "Indirect": 1.5,
    "None": 1.0,
    None: 1.0,
}


def _task_weight(task: dict) -> float:
    """Calculate combined weight for a task based on priority, difficulty, revenue impact."""
    p = PRIORITY_WEIGHTS.get(task.get("priority"), 1.5)
    d = DIFFICULTY_WEIGHTS.get(task.get("difficulty"), 1.5)
    # Revenue impact has emoji prefix, strip it
    rev_raw = task.get("revenue_impact") or None
    rev_key = rev_raw.split(" ")[-1] if rev_raw else None
    r = REVENUE_WEIGHTS.get(rev_key, 1.0)
    # Combined weight = priority * sqrt(difficulty) * revenue
    # Using sqrt for difficulty so a hard task counts more but doesn't dominate
    return p * (d ** 0.5) * r


# --- Hierarchical Propagation ---

def propagate_to_projects(tasks: list[dict], completed_ids: list[str], started_ids: list[str]) -> list[dict]:
    """Check if project status should change based on weighted child task completions.

    Uses priority, difficulty, and revenue impact to weight each task's contribution.
    Returns list of project updates.
    """
    task_by_id = {t["id"]: t for t in tasks}
    projects = {t["id"]: t for t in tasks if t["type"] == "Project"}

    project_children: dict[str, list[str]] = {pid: [] for pid in projects}
    for t in tasks:
        if t["type"] != "Project":
            for parent_id in t.get("upstream", []):
                if parent_id in project_children:
                    project_children[parent_id].append(t["id"])

    updates = []
    for pid, children in project_children.items():
        if not children:
            continue
        project = projects[pid]

        total_weight = 0
        completed_weight = 0
        in_progress_weight = 0
        completed_count = 0
        in_progress_count = 0

        for cid in children:
            child = task_by_id.get(cid)
            if not child:
                continue
            w = _task_weight(child)
            total_weight += w

            if cid in completed_ids or child["status"] == "Complete":
                completed_weight += w
                completed_count += 1
            elif cid in started_ids or child["status"] == "In Progress":
                in_progress_weight += w * 0.5
                in_progress_count += 1

        total = len(children)
        # Weighted progress
        progress = (completed_weight + in_progress_weight) / total_weight if total_weight > 0 else 0

        old_status = project["status"]
        if completed_count == total:
            new_status = "Complete"
        elif completed_count > 0 or in_progress_count > 0:
            new_status = "In Progress"
        else:
            new_status = old_status

        if new_status != old_status or progress > 0:
            updates.append({
                "id": pid,
                "name": project["name"],
                "old_status": old_status,
                "new_status": new_status,
                "progress": progress,
                "completed": completed_count,
                "total": total,
                "weighted": True,
            })

    return updates


def propagate_to_goals(tasks: list[dict], goals: list[dict], project_updates: list[dict]) -> list[dict]:
    """Update goal progress based on weighted linked projects/tasks.

    Returns list of goal updates.
    """
    goal_children: dict[str, list[str]] = {g["id"]: [] for g in goals}
    for t in tasks:
        for gid in t.get("goals", []):
            if gid in goal_children:
                goal_children[gid].append(t["id"])

    project_update_map = {u["id"]: u for u in project_updates}
    task_by_id = {t["id"]: t for t in tasks}

    updates = []
    for goal in goals:
        children = goal_children.get(goal["id"], [])
        if not children:
            continue

        total_weight = 0
        completed_weight = 0

        for cid in children:
            task = task_by_id.get(cid)
            if not task:
                continue
            w = _task_weight(task)
            total_weight += w

            if cid in project_update_map and project_update_map[cid]["new_status"] == "Complete":
                completed_weight += w
            elif task["status"] == "Complete":
                completed_weight += w

        calculated = completed_weight / total_weight if total_weight > 0 else 0
        old_progress = goal.get("progress", 0)
        new_progress = max(calculated, old_progress)

        if new_progress - old_progress > 0.01:
            updates.append({
                "id": goal["id"],
                "name": goal["name"],
                "old_progress": old_progress,
                "new_progress": new_progress,
                "completed_items": int(completed_weight),
                "total_items": int(total_weight),
                "weighted": True,
            })

    return updates


def check_deadlines(tasks: list[dict], goals: list[dict]) -> list[dict]:
    """Check for overdue or upcoming deadlines."""
    today = datetime.now(timezone.utc).date()
    alerts = []

    for t in tasks:
        due = t.get("due_date")
        if not due or t["status"] in ("Complete", "Archive"):
            continue
        try:
            due_date = datetime.fromisoformat(due.replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            continue
        days_left = (due_date - today).days
        if days_left < 0:
            alerts.append({"type": "overdue", "name": t["name"], "days": abs(days_left), "kind": "task"})
        elif days_left <= 2:
            alerts.append({"type": "soon", "name": t["name"], "days": days_left, "kind": "task"})

    for g in goals:
        target = g.get("target_date")
        if not target or g["status"] in ("✅ Achieved", "❌ Abandoned"):
            continue
        try:
            target_date = datetime.fromisoformat(target.replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            continue
        days_left = (target_date - today).days
        if days_left < 0:
            alerts.append({"type": "overdue", "name": g["name"], "days": abs(days_left), "kind": "goal"})
        elif days_left <= 3:
            alerts.append({"type": "soon", "name": g["name"], "days": days_left, "kind": "goal"})

    return alerts


# --- Velocity Tracking & Predictions ---

def load_velocity_history() -> dict:
    """Load velocity history from JSON file."""
    if os.path.exists(VELOCITY_FILE):
        try:
            with open(VELOCITY_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"runs": []}


def save_velocity_history(history: dict) -> None:
    """Save velocity history to JSON file. Keep last 90 days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    history["runs"] = [r for r in history["runs"] if r.get("timestamp", "") > cutoff]
    with open(VELOCITY_FILE, "w") as f:
        json.dump(history, f, indent=2, default=str)


def record_velocity(
    history: dict,
    total_commits: int,
    tasks: list[dict],
    goals: list[dict],
    completed_ids: list[str],
    started_ids: list[str],
    created_count: int,
    source: str,
) -> None:
    """Record a velocity data point."""
    # Snapshot project progress
    project_snapshots = {}
    for t in tasks:
        if t["type"] == "Project":
            children = [c for c in tasks if t["id"] in c.get("upstream", []) and c["type"] != "Project"]
            done = sum(1 for c in children if c["status"] == "Complete" or c["id"] in completed_ids)
            total = len(children)
            project_snapshots[t["id"]] = {
                "name": t["name"],
                "status": t["status"],
                "tasks_done": done,
                "tasks_total": total,
                "progress": done / total if total > 0 else 0,
            }

    # Snapshot goal progress
    goal_snapshots = {}
    for g in goals:
        goal_snapshots[g["id"]] = {
            "name": g["name"],
            "progress": g.get("progress", 0),
            "target_date": g.get("target_date"),
            "status": g.get("status", ""),
        }

    history["runs"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "commits": total_commits,
        "tasks_completed": len(completed_ids),
        "tasks_started": len(started_ids),
        "tasks_created": created_count,
        "total_active_tasks": len([t for t in tasks if t["type"] != "Project"]),
        "project_snapshots": project_snapshots,
        "goal_snapshots": goal_snapshots,
    })


def calculate_velocity(history: dict, days: int = 7) -> dict:
    """Calculate velocity metrics over the last N days.

    Returns: {
        "tasks_per_day": float,
        "commits_per_day": float,
        "data_points": int,
        "days_covered": int,
    }
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    recent = [r for r in history["runs"] if r.get("timestamp", "") > cutoff]

    if not recent:
        return {"tasks_per_day": 0, "commits_per_day": 0, "data_points": 0, "days_covered": 0}

    total_tasks = sum(r.get("tasks_completed", 0) for r in recent)
    total_commits = sum(r.get("commits", 0) for r in recent)

    # Calculate actual days covered
    timestamps = [r["timestamp"] for r in recent]
    try:
        first = datetime.fromisoformat(min(timestamps))
        last = datetime.fromisoformat(max(timestamps))
        days_covered = max((last - first).total_seconds() / 86400, 1)
    except (ValueError, TypeError):
        days_covered = days

    return {
        "tasks_per_day": total_tasks / days_covered if days_covered > 0 else 0,
        "commits_per_day": total_commits / days_covered if days_covered > 0 else 0,
        "data_points": len(recent),
        "days_covered": round(days_covered, 1),
    }


def predict_deliveries(
    history: dict,
    tasks: list[dict],
    goals: list[dict],
    completed_ids: list[str],
) -> list[dict]:
    """Predict delivery dates for projects and goals.

    Returns list of predictions with on-track/behind/ahead status.
    """
    today = datetime.now(timezone.utc).date()
    predictions = []

    # Calculate velocity over different windows
    v7 = calculate_velocity(history, 7)
    v14 = calculate_velocity(history, 14)
    v30 = calculate_velocity(history, 30)

    # Use the best available velocity (prefer 14-day, fallback to 7 or 30)
    if v14["data_points"] >= 3:
        velocity = v14
        window_label = "14j"
    elif v7["data_points"] >= 2:
        velocity = v7
        window_label = "7j"
    elif v30["data_points"] >= 2:
        velocity = v30
        window_label = "30j"
    else:
        # Not enough data yet
        return predictions

    tasks_per_day = velocity["tasks_per_day"]

    # --- Project predictions ---
    for t in tasks:
        if t["type"] != "Project" or t["status"] in ("Complete", "Archive"):
            continue

        # Find children tasks
        children = [c for c in tasks if t["id"] in c.get("upstream", []) and c["type"] != "Project"]
        if not children:
            continue

        remaining = sum(
            1 for c in children
            if c["status"] not in ("Complete",) and c["id"] not in completed_ids
        )
        total = len(children)
        done = total - remaining

        if remaining == 0:
            continue  # Already complete

        # Find deadline from linked goals or task due_date
        deadline = None
        deadline_source = None
        if t.get("due_date"):
            try:
                deadline = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00")).date()
                deadline_source = "project"
            except (ValueError, AttributeError):
                pass

        # Also check linked goals for deadline
        for g in goals:
            goal_children = [c for c in tasks if g["id"] in c.get("goals", [])]
            if t["id"] in [c["id"] for c in goal_children] and g.get("target_date"):
                try:
                    goal_deadline = datetime.fromisoformat(g["target_date"].replace("Z", "+00:00")).date()
                    if deadline is None or goal_deadline < deadline:
                        deadline = goal_deadline
                        deadline_source = g["name"]
                except (ValueError, AttributeError):
                    pass

        # Predict
        if tasks_per_day > 0:
            days_needed = remaining / tasks_per_day
            predicted_date = today + timedelta(days=days_needed)
        else:
            days_needed = float("inf")
            predicted_date = None

        pred = {
            "name": t["name"],
            "kind": "project",
            "done": done,
            "remaining": remaining,
            "total": total,
            "tasks_per_day": round(tasks_per_day, 2),
            "days_needed": round(days_needed, 1) if days_needed != float("inf") else None,
            "predicted_date": predicted_date.isoformat() if predicted_date else None,
            "velocity_window": window_label,
        }

        if deadline:
            days_left = (deadline - today).days
            pred["deadline"] = deadline.isoformat()
            pred["deadline_source"] = deadline_source
            pred["days_left"] = days_left
            if predicted_date:
                margin = days_left - days_needed
                if margin >= 3:
                    pred["status"] = "EN AVANCE"
                elif margin >= 0:
                    pred["status"] = "SERRE"
                else:
                    pred["status"] = "EN RETARD"
                    pred["days_over"] = round(abs(margin), 1)
            else:
                pred["status"] = "BLOQUE" if tasks_per_day == 0 else "INCONNU"
        else:
            pred["status"] = "PAS DE DEADLINE"

        predictions.append(pred)

    # --- Goal predictions (based on progress velocity) ---
    for g in goals:
        if g.get("status") in ("Achieved", "Abandoned"):
            continue
        target = g.get("target_date")
        if not target:
            continue
        try:
            deadline = datetime.fromisoformat(target.replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            continue

        current_progress = g.get("progress", 0)
        remaining_progress = 1.0 - current_progress
        if remaining_progress <= 0:
            continue

        days_left = (deadline - today).days
        if days_left <= 0:
            continue  # Already handled by deadline alerts

        # Calculate progress velocity from history
        progress_velocity = _calc_progress_velocity(history, g["id"], days=14)

        if progress_velocity > 0:
            days_to_100 = remaining_progress / progress_velocity
            predicted_date = today + timedelta(days=days_to_100)
            margin = days_left - days_to_100

            if margin >= 7:
                status = "EN AVANCE"
            elif margin >= 0:
                status = "SERRE"
            else:
                status = "EN RETARD"

            predictions.append({
                "name": g["name"],
                "kind": "goal",
                "progress": round(current_progress * 100, 1),
                "progress_per_day": round(progress_velocity * 100, 2),
                "days_needed": round(days_to_100, 1),
                "predicted_date": predicted_date.isoformat(),
                "deadline": deadline.isoformat(),
                "days_left": days_left,
                "status": status,
                "days_over": round(abs(margin), 1) if margin < 0 else None,
            })
        elif days_left > 0:
            predictions.append({
                "name": g["name"],
                "kind": "goal",
                "progress": round(current_progress * 100, 1),
                "progress_per_day": 0,
                "days_needed": None,
                "predicted_date": None,
                "deadline": deadline.isoformat(),
                "days_left": days_left,
                "status": "PAS ASSEZ DE DONNEES",
            })

    return predictions


def _calc_progress_velocity(history: dict, goal_id: str, days: int = 14) -> float:
    """Calculate how fast a goal's progress is changing (per day)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    recent = [r for r in history["runs"] if r.get("timestamp", "") > cutoff]

    # Find snapshots for this goal
    snapshots = []
    for r in recent:
        gs = r.get("goal_snapshots", {}).get(goal_id)
        if gs and gs.get("progress") is not None:
            snapshots.append((r["timestamp"], gs["progress"]))

    if len(snapshots) < 2:
        return 0

    snapshots.sort(key=lambda x: x[0])
    first_time = datetime.fromisoformat(snapshots[0][0])
    last_time = datetime.fromisoformat(snapshots[-1][0])
    first_progress = snapshots[0][1]
    last_progress = snapshots[-1][1]

    elapsed_days = (last_time - first_time).total_seconds() / 86400
    if elapsed_days < 0.1:
        return 0

    delta = last_progress - first_progress
    if delta <= 0:
        return 0

    return delta / elapsed_days


# --- Telegram Recap ---

def build_smart_recap(
    analysis: dict,
    total_commits: int,
    project_updates: list[dict],
    goal_updates: list[dict],
    deadline_alerts: list[dict],
    predictions: list[dict] | None = None,
    velocity: dict | None = None,
) -> list[str]:
    """Build an intelligent Telegram recap with project/goal context."""
    highlights = []

    # Commits
    highlights.append(f"{total_commits} commits sur {len(REPOS)} repos")

    # Tasks
    completed = analysis.get("tasks_completed", [])
    started = analysis.get("tasks_started", [])
    created = analysis.get("tasks_to_create", [])
    if completed:
        highlights.append(f"{len(completed)} taches completees")
    if started:
        highlights.append(f"{len(started)} taches demarrees")
    if created:
        highlights.append(f"{len(created)} nouvelles taches")

    # Velocity
    if velocity and velocity.get("tasks_per_day", 0) > 0:
        tpd = velocity["tasks_per_day"]
        cpd = velocity["commits_per_day"]
        highlights.append(f"Velocite : {tpd:.1f} taches/jour, {cpd:.1f} commits/jour ({velocity.get('days_covered', 0)}j)")

    # Projects
    for pu in project_updates:
        pct = int(pu["progress"] * 100)
        if pu["new_status"] == "Complete":
            highlights.append(f"PROJET TERMINE : {pu['name']}")
        elif pu["new_status"] != pu["old_status"]:
            highlights.append(f"{pu['name']} : {pct}% ({pu['completed']}/{pu['total']} taches)")

    # Goals
    for gu in goal_updates:
        old_pct = int(gu["old_progress"] * 100)
        new_pct = int(gu["new_progress"] * 100)
        highlights.append(f"Goal {gu['name']} : {old_pct}% -> {new_pct}%")

    # Predictions
    if predictions:
        for pred in predictions:
            if pred["status"] == "PAS ASSEZ DE DONNEES":
                continue
            name = pred["name"]
            if pred["kind"] == "project":
                remaining = pred["remaining"]
                total = pred["total"]
                if pred["status"] == "EN RETARD":
                    highlights.append(
                        f"PREDICTION {name} : {remaining}/{total} restantes, "
                        f"retard de {pred.get('days_over', '?')}j"
                    )
                elif pred["status"] == "SERRE":
                    highlights.append(
                        f"PREDICTION {name} : {remaining}/{total} restantes, "
                        f"~{pred.get('days_needed', '?')}j necessaires (serre)"
                    )
                elif pred["status"] == "EN AVANCE":
                    highlights.append(
                        f"PREDICTION {name} : {remaining}/{total} restantes, en avance"
                    )
            elif pred["kind"] == "goal":
                pct = pred.get("progress", 0)
                if pred["status"] == "EN RETARD":
                    highlights.append(
                        f"PREDICTION {name} ({pct}%) : retard de {pred.get('days_over', '?')}j "
                        f"a {pred.get('progress_per_day', 0)}%/jour"
                    )
                elif pred["status"] == "SERRE":
                    highlights.append(
                        f"PREDICTION {name} ({pct}%) : serre, "
                        f"~{pred.get('days_needed', '?')}j pour 100%"
                    )
                elif pred["status"] == "EN AVANCE":
                    highlights.append(
                        f"PREDICTION {name} ({pct}%) : en avance"
                    )

    # Deadlines
    for alert in deadline_alerts:
        if alert["type"] == "overdue":
            highlights.append(f"EN RETARD ({alert['days']}j) : {alert['name']}")
        else:
            highlights.append(f"Deadline dans {alert['days']}j : {alert['name']}")

    return highlights


def send_recap(analysis: dict, total_commits: int, highlights: list[str],
               completed_ids: list[str], started_ids: list[str]) -> bool:
    """Send recap via Session Closer webhook."""
    payload = {
        "session_number": 0,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": f"[Auto] {analysis.get('summary', 'Git Activity Tracker')}",
        "highlights": highlights,
        "tasks_completed": completed_ids,
        "tasks_started": started_ids,
        "files_changed": total_commits,
        "workflows_modified": 0,
        "duration_hours": 0,
    }
    try:
        r = requests.post(SESSION_CLOSER_URL, json=payload, timeout=30)
        return r.status_code == 200
    except Exception as e:
        log(f"  Session Closer error: {e}")
        return False


# --- Main ---

def main(source: str = "cron") -> dict:
    log("=== Git Activity Tracker v3 ===")

    # 1. Time window
    since = (datetime.now(timezone.utc) - timedelta(hours=HOURS_WINDOW)).isoformat()
    log(f"Window: last {HOURS_WINDOW}h")

    # 2. Fetch commits
    log("Fetching commits...")
    all_commits = {}
    for repo in REPOS:
        commits = fetch_commits(repo, since)
        all_commits[repo] = commits
        log(f"  {repo.split('/')[-1]}: {len(commits)} commits")

    git_summary, total_commits = build_git_summary(all_commits)

    if total_commits == 0:
        log("No commits. Checking deadlines only...")
        tasks = fetch_notion_tasks()
        goals = fetch_notion_goals()
        alerts = check_deadlines(tasks, goals)

        # Record velocity snapshot even without commits
        history = load_velocity_history()
        record_velocity(history, 0, tasks, goals, [], [], 0, source=source)
        save_velocity_history(history)
        log(f"  Velocity snapshot saved ({len(history['runs'])} total points)")

        overdue = [a for a in alerts if a["type"] == "overdue"]
        if overdue:
            log(f"  {len(overdue)} overdue, {len(alerts) - len(overdue)} upcoming")
            highlights = []
            for a in overdue:
                highlights.append(f"EN RETARD ({a['days']}j) : {a['name']}")
            for a in alerts:
                if a["type"] == "soon":
                    highlights.append(f"Deadline dans {a['days']}j : {a['name']}")
            ok = send_recap(
                {"summary": f"Pas de commits — {len(overdue)} taches en retard"},
                0, highlights, [], []
            )
            log(f"  Telegram alert: {'OK' if ok else 'FAIL'}")
        else:
            log(f"  {len(alerts)} upcoming deadlines, no overdue. Skipping Telegram.")
        return {"status": "no_commits", "deadline_alerts": len(alerts)}

    log(f"Total: {total_commits} commits")

    # 3. Fetch Notion data
    log("Fetching Notion tasks...")
    tasks = fetch_notion_tasks()
    log(f"  {len(tasks)} active tasks/projects")

    log("Fetching Notion goals...")
    goals = fetch_notion_goals()
    log(f"  {len(goals)} active goals")

    notion_summary = build_notion_summary(tasks)

    # 4. Claude analysis
    log("Analyzing with Claude...")
    analysis = analyze_with_claude(git_summary, notion_summary)
    log(f"  Summary: {analysis.get('summary', 'N/A')}")
    completed_ids = analysis.get("tasks_completed", [])
    started_ids = analysis.get("tasks_started", [])
    to_create = analysis.get("tasks_to_create", [])
    log(f"  Completed: {len(completed_ids)} | Started: {len(started_ids)} | New: {len(to_create)}")

    # 4b. Generate changelog
    log("Generating changelog...")
    changelog_entry = generate_changelog(git_summary, analysis)
    if changelog_entry:
        save_changelog(changelog_entry, total_commits)
        # Extract first line for recap
        changelog_oneliner = changelog_entry.split("\n")[0].strip("# ").strip("-").strip()
        log(f"  Saved: {changelog_oneliner[:80]}")
    else:
        changelog_oneliner = None
        log("  Skipped (no meaningful changes)")

    # 5. Create new tasks
    for task in to_create:
        ok = create_notion_task(task)
        log(f"  Created '{task['name']}': {'OK' if ok else 'FAIL'}")

    # 6. Propagate task → project
    log("Propagating to projects...")
    project_updates = propagate_to_projects(tasks, completed_ids, started_ids)
    for pu in project_updates:
        props = {"Status": {"status": {"name": pu["new_status"]}}}
        if pu["new_status"] == "Complete":
            props["Completed On"] = {"date": {"start": datetime.now(timezone.utc).isoformat()}}
        ok = update_notion_page(pu["id"], props)
        pct = int(pu["progress"] * 100)
        log(f"  {pu['name']}: {pu['old_status']} -> {pu['new_status']} ({pct}%) {'OK' if ok else 'FAIL'}")

    # 7. Propagate project → goal
    log("Propagating to goals...")
    goal_updates = propagate_to_goals(tasks, goals, project_updates)
    for gu in goal_updates:
        props = {"Progress %": {"number": round(gu["new_progress"], 2)}}
        # Auto-set goal status
        if gu["new_progress"] >= 1.0:
            props["Status"] = {"select": {"name": "✅ Achieved"}}
        elif gu["new_progress"] > 0 and gu.get("old_progress", 0) == 0:
            props["Status"] = {"select": {"name": "🔥 In Progress"}}
        ok = update_notion_page(gu["id"], props)
        old_pct = int(gu["old_progress"] * 100)
        new_pct = int(gu["new_progress"] * 100)
        log(f"  {gu['name']}: {old_pct}% -> {new_pct}% {'OK' if ok else 'FAIL'}")

    if not goal_updates:
        log("  No goal changes")

    # 8. Check deadlines
    log("Checking deadlines...")
    deadline_alerts = check_deadlines(tasks, goals)
    if deadline_alerts:
        for a in deadline_alerts:
            tag = "OVERDUE" if a["type"] == "overdue" else f"in {a['days']}d"
            log(f"  [{tag}] {a['name']}")
    else:
        log("  No deadline alerts")

    # 9. Velocity tracking & predictions
    log("Velocity tracking...")
    history = load_velocity_history()
    record_velocity(
        history, total_commits, tasks, goals,
        completed_ids, started_ids, len(to_create),
        source=source,
    )
    save_velocity_history(history)

    v14 = calculate_velocity(history, 14)
    log(f"  Velocity (14j): {v14['tasks_per_day']:.2f} taches/jour, "
        f"{v14['commits_per_day']:.1f} commits/jour ({v14['data_points']} points)")

    log("Predicting deliveries...")
    predictions = predict_deliveries(history, tasks, goals, completed_ids)
    for pred in predictions:
        if pred["status"] == "PAS ASSEZ DE DONNEES":
            log(f"  [{pred['kind']}] {pred['name']}: pas assez de donnees")
        elif pred["kind"] == "project":
            dl = f", deadline dans {pred.get('days_left', '?')}j" if pred.get("deadline") else ""
            log(f"  [{pred['status']}] {pred['name']}: "
                f"{pred['remaining']}/{pred['total']} restantes, "
                f"~{pred.get('days_needed', '?')}j necessaires{dl}")
        elif pred["kind"] == "goal":
            dl = f", deadline dans {pred.get('days_left', '?')}j" if pred.get("deadline") else ""
            log(f"  [{pred['status']}] {pred['name']}: "
                f"{pred.get('progress', 0)}%, "
                f"+{pred.get('progress_per_day', 0)}%/jour{dl}")

    if not predictions:
        log("  Pas assez d'historique pour predire (besoin de quelques jours)")

    # 10. Build smart recap and send
    log("Sending recap...")
    highlights = build_smart_recap(
        analysis, total_commits, project_updates, goal_updates,
        deadline_alerts, predictions, v14,
    )
    if changelog_oneliner:
        highlights.append(f"Changelog: {changelog_oneliner}")
    ok = send_recap(analysis, total_commits, highlights, completed_ids, started_ids)
    log(f"  Telegram: {'OK' if ok else 'FAIL'}")

    result = {
        "status": "ok",
        "total_commits": total_commits,
        "tasks_checked": len(tasks),
        "goals_checked": len(goals),
        "completed": len(completed_ids),
        "started": len(started_ids),
        "created": len(to_create),
        "projects_updated": len(project_updates),
        "goals_updated": len(goal_updates),
        "deadline_alerts": len(deadline_alerts),
        "predictions": len(predictions),
    }
    log(f"=== Done === {json.dumps(result)}")
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Git Activity Tracker v2")
    parser.add_argument("--window", type=int, default=HOURS_WINDOW,
                        help=f"Hours to look back (default: {HOURS_WINDOW})")
    parser.add_argument("--repo", type=str, default=None,
                        help="Only check this repo (e.g. 'AI-Business-Automation-Suite')")
    parser.add_argument("--source", type=str, default="cron",
                        help="Trigger source for logging (cron/push-hook)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Lock to prevent concurrent runs
    lock_fd = open(LOCKFILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Another tracker is running. Skipping.")
        sys.exit(0)

    # Apply CLI overrides
    if args.window != HOURS_WINDOW:
        HOURS_WINDOW = args.window

    if args.repo:
        # Filter repos to only the one specified
        matches = [r for r in REPOS if args.repo in r]
        if matches:
            REPOS[:] = matches
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Repo '{args.repo}' not found in {REPOS}")
            sys.exit(1)

    log(f"[source={args.source}]")
    main(source=args.source)

    # Release lock
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    lock_fd.close()
    os.unlink(LOCKFILE)
