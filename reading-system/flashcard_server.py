#!/usr/bin/env python3
"""Serveur local pour l'interface Flashcards — sert l'HTML et fait le pont avec Notion."""

import json
import os
import uuid
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timedelta
import requests

_token_path = os.environ.get("NOTION_TOKEN_FILE", os.path.expanduser("~/.notion-token"))
TOKEN = open(_token_path).read().strip()
_anthropic_path = os.environ.get("ANTHROPIC_KEY_FILE", os.path.expanduser("~/.anthropic-key"))
ANTHROPIC_KEY = open(_anthropic_path).read().strip()
API = "https://www.notion.so/api/v3"
FLASHCARDS_COLLECTION = "e5467f7c-81c2-4a6e-8c61-aa4bb3ee841c"
FLASHCARDS_DB_PAGE = "08822a47-99fd-47ee-9f13-2ecc6043e63b"
PORT = 8765

_view_id_cache = None

def get_view_id():
    """Get the first view ID of the Flashcards database."""
    global _view_id_cache
    if _view_id_cache:
        return _view_id_cache
    resp = requests.post(f"{API}/syncRecordValues",
        cookies={"token_v2": TOKEN},
        headers={"Content-Type": "application/json"},
        json={"requests": [{"pointer": {"table": "block", "id": FLASHCARDS_DB_PAGE}, "version": -1}]},
        timeout=15)
    data = resp.json()
    block = data.get("recordMap", {}).get("block", {}).get(FLASHCARDS_DB_PAGE, {}).get("value", {})
    view_ids = block.get("view_ids", [])
    _view_id_cache = view_ids[0] if view_ids else ""
    return _view_id_cache


def get_schema():
    """Get Flashcards collection schema."""
    resp = requests.post(f"{API}/syncRecordValues",
        cookies={"token_v2": TOKEN},
        headers={"Content-Type": "application/json"},
        json={"requests": [{"pointer": {"table": "collection", "id": FLASHCARDS_COLLECTION}, "version": -1}]},
        timeout=15)
    data = resp.json()
    coll = data.get("recordMap", {}).get("collection", {}).get(FLASHCARDS_COLLECTION, {}).get("value", {})
    schema = coll.get("schema", {})
    return {info.get("name", ""): pid for pid, info in schema.items()}


def query_flashcards():
    """Get all flashcards from Notion."""
    view_id = get_view_id()
    resp = requests.post(f"{API}/queryCollection",
        cookies={"token_v2": TOKEN},
        headers={"Content-Type": "application/json"},
        json={
            "collection": {"id": FLASHCARDS_COLLECTION},
            "collectionView": {"id": view_id},
            "loader": {
                "type": "reducer",
                "reducers": {
                    "results": {
                        "type": "results",
                        "limit": 200,
                    }
                },
                "searchQuery": "",
                "userTimeZone": "Europe/Paris",
            }
        },
        timeout=15)
    data = resp.json()

    name_to_id = get_schema()
    id_to_name = {v: k for k, v in name_to_id.items()}

    result_ids = data.get("result", {}).get("reducerResults", {}).get("results", {}).get("blockIds", [])

    # Fetch full data for each card via syncRecordValues
    if result_ids:
        reqs = [{"pointer": {"table": "block", "id": rid}, "version": -1} for rid in result_ids]
        sync_resp = requests.post(f"{API}/syncRecordValues",
            cookies={"token_v2": TOKEN},
            headers={"Content-Type": "application/json"},
            json={"requests": reqs},
            timeout=15)
        blocks = sync_resp.json().get("recordMap", {}).get("block", {})
    else:
        blocks = {}

    cards = []

    for block_id in result_ids:
        block_data = blocks.get(block_id, {})
        value = block_data.get("value", {})
        if not value.get("alive", True):
            continue

        props = value.get("properties", {})

        # Parse properties
        def get_text(prop_id):
            val = props.get(prop_id, [[""]])
            if val and val[0]:
                return val[0][0] if isinstance(val[0], list) else str(val[0])
            return ""

        def get_number(prop_id):
            val = get_text(prop_id)
            try:
                return float(val) if val else 0
            except (ValueError, TypeError):
                return 0

        def get_date(prop_id):
            val = props.get(prop_id)
            if not val:
                return ""
            # Notion date format: [["‣", [["d", {"type": "date", "start_date": "2026-03-16"}]]]]
            try:
                for item in val:
                    if isinstance(item, list):
                        for sub in item:
                            if isinstance(sub, list) and len(sub) >= 2 and sub[0] == "d":
                                return sub[1].get("start_date", "")
            except (TypeError, IndexError, KeyError):
                pass
            return ""

        front = get_text("title")
        back = get_text(name_to_id.get("Back", ""))
        card_type = get_text(name_to_id.get("Type", ""))
        difficulty = get_text(name_to_id.get("Difficulty", ""))
        chapter = get_text(name_to_id.get("Chapter", ""))
        status = get_text(name_to_id.get("Status", ""))
        quality = get_number(name_to_id.get("Quality", ""))
        repetitions = get_number(name_to_id.get("Repetitions", ""))
        ease_factor = get_number(name_to_id.get("Ease Factor", ""))
        interval_days = get_number(name_to_id.get("Interval Days", ""))
        next_review = get_date(name_to_id.get("Next Review", ""))
        last_reviewed = get_date(name_to_id.get("Last Reviewed", ""))

        if not front:
            continue

        cards.append({
            "id": block_id,
            "front": front,
            "back": back,
            "type": card_type or "Factual",
            "difficulty": difficulty or "3",
            "chapter": chapter,
            "status": status or "New",
            "quality": quality,
            "repetitions": int(repetitions),
            "ease_factor": ease_factor or 2.5,
            "interval_days": int(interval_days),
            "next_review": next_review,
            "last_reviewed": last_reviewed,
        })

    return cards


def update_flashcard(card_id, quality, repetitions, ease_factor, interval_days, next_review, status):
    """Update a flashcard in Notion after review."""
    name_to_id = get_schema()
    today = datetime.now().strftime("%Y-%m-%d")

    ops = []
    if name_to_id.get("Quality"):
        ops.append({"pointer": {"table": "block", "id": card_id},
                    "path": ["properties", name_to_id["Quality"]], "command": "set",
                    "args": [[str(quality)]]})
    if name_to_id.get("Repetitions"):
        ops.append({"pointer": {"table": "block", "id": card_id},
                    "path": ["properties", name_to_id["Repetitions"]], "command": "set",
                    "args": [[str(repetitions)]]})
    if name_to_id.get("Ease Factor"):
        ops.append({"pointer": {"table": "block", "id": card_id},
                    "path": ["properties", name_to_id["Ease Factor"]], "command": "set",
                    "args": [[str(round(ease_factor, 2))]]})
    if name_to_id.get("Interval Days"):
        ops.append({"pointer": {"table": "block", "id": card_id},
                    "path": ["properties", name_to_id["Interval Days"]], "command": "set",
                    "args": [[str(interval_days)]]})
    if name_to_id.get("Status"):
        ops.append({"pointer": {"table": "block", "id": card_id},
                    "path": ["properties", name_to_id["Status"]], "command": "set",
                    "args": [[status]]})
    if name_to_id.get("Last Reviewed"):
        ops.append({"pointer": {"table": "block", "id": card_id},
                    "path": ["properties", name_to_id["Last Reviewed"]], "command": "set",
                    "args": [["‣", [["d", {"type": "date", "start_date": today}]]]]})
    if name_to_id.get("Next Review"):
        ops.append({"pointer": {"table": "block", "id": card_id},
                    "path": ["properties", name_to_id["Next Review"]], "command": "set",
                    "args": [["‣", [["d", {"type": "date", "start_date": next_review}]]]]})

    if ops:
        requests.post(f"{API}/submitTransaction",
            cookies={"token_v2": TOKEN},
            headers={"Content-Type": "application/json"},
            json={"requestId": str(uuid.uuid4()),
                  "transactions": [{"id": str(uuid.uuid4()), "operations": ops}]},
            timeout=15)


def check_answer_ai(question, correct_answer, user_answer):
    """Use Claude Haiku to compare user answer vs correct answer. Returns score 0-100 and verdict."""
    try:
        resp = requests.post("https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 150,
                "messages": [{"role": "user", "content": f"""Compare la reponse de l'etudiant avec la bonne reponse. Reponds UNIQUEMENT en JSON.

Question: {question}
Bonne reponse: {correct_answer}
Reponse etudiant: {user_answer}

JSON: {{"score": 0-100, "verdict": "correct|partial|wrong", "feedback": "1 phrase courte"}}"""}],
            },
            timeout=10)
        data = resp.json()
        text = data.get("content", [{}])[0].get("text", "")
        # Parse JSON from response
        import re
        match = re.search(r'\{[^}]+\}', text)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return None


class FlashcardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.path = "/flashcards_app.html"
            return SimpleHTTPRequestHandler.do_GET(self)
        elif self.path == "/api/cards":
            cards = query_flashcards()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(cards, ensure_ascii=False).encode())
        elif self.path == "/api/due":
            cards = query_flashcards()
            today = datetime.now().strftime("%Y-%m-%d")
            due = [c for c in cards if not c["next_review"] or c["next_review"] <= today]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(due, ensure_ascii=False).encode())
        else:
            SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        if self.path == "/api/check":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            result = check_answer_ai(body.get("question", ""), body.get("correct", ""), body.get("answer", ""))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result or {"score": 0, "verdict": "error", "feedback": "Erreur IA"}, ensure_ascii=False).encode())
            return
        elif self.path == "/api/review":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))

            card_id = body.get("id", "")
            quality = body.get("quality", 3)
            reps = body.get("repetitions", 0)
            ef = body.get("ease_factor", 2.5)
            interval = body.get("interval_days", 0)
            next_review = body.get("next_review", "")
            status = body.get("status", "Learning")

            update_flashcard(card_id, quality, reps, ef, interval, next_review, status)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Silence logs


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = HTTPServer(("0.0.0.0", PORT), FlashcardHandler)
    print(f"Flashcard server running on http://localhost:{PORT}")
    server.serve_forever()
