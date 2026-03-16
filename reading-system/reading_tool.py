#!/usr/bin/env python3
"""
Reading System Tool for Orun v2.
Handles: book search, session logging, quiz generation, flashcard creation.

Usage in Orun:
    /lecture <titre du livre> [chapitre X] [pages Y-Z]
    /flashcards  → cards due today
    /livre <search query>  → search and add a book
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

# Import local modules
sys.path.insert(0, os.path.dirname(__file__))
from book_search import search_google_books, search_open_library, get_table_of_contents
from sm2 import sm2

# Notion config
NOTION_CREDENTIAL = "FPqqVYnRbUnwRzrY"
N8N_BASE = "https://n8n.srv842982.hstgr.cloud"

# Collection IDs
BOOKS_COLLECTION = "2917d8ba-b3e4-419f-bc32-602c837acda1"
SESSIONS_COLLECTION = "fa8558cd-bf7a-498a-b3de-d0a8c787dcb1"
QUOTES_COLLECTION = "9a8e0a22-9cf3-4715-abbc-c2810ad829f4"
FLASHCARDS_COLLECTION = "e5467f7c-81c2-4a6e-8c61-aa4bb3ee841c"


def notion_query(collection_id, filter_obj=None, sorts=None, limit=50):
    """Query Notion database via n8n webhook."""
    payload = {
        "action": "query",
        "collection_id": collection_id,
        "filter": filter_obj or {},
        "sorts": sorts or [],
        "limit": limit,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{N8N_BASE}/webhook/notion-query",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Notion query error: {e}", file=sys.stderr)
        return {}


def notion_create(collection_id, properties):
    """Create Notion page via n8n webhook."""
    payload = {
        "action": "create",
        "collection_id": collection_id,
        "properties": properties,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{N8N_BASE}/webhook/notion-create-task",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Notion create error: {e}", file=sys.stderr)
        return {}


def search_and_add_book(query):
    """Search for a book and return metadata for Notion."""
    google_results = search_google_books(query, max_results=1)
    ol_results = search_open_library(query, max_results=1)

    if not google_results and not ol_results:
        return {"error": "Aucun livre trouve"}

    # Merge best result
    book = {}
    if google_results:
        g = google_results[0]
        book = {
            "title": g["title"],
            "author": ", ".join(g["authors"]),
            "page_count": g["page_count"],
            "language": g["language"].upper() if g["language"] else "FR",
            "isbn": g["isbn_13"] or g["isbn_10"],
            "cover_url": g["cover_url"],
            "description": g["description"],
            "categories": g["categories"],
        }

    # Get TOC from Open Library
    toc = []
    if ol_results:
        o = ol_results[0]
        if not book.get("page_count"):
            book["page_count"] = o["page_count"]
        for ek in o.get("edition_keys", [])[:3]:
            toc = get_table_of_contents(ek)
            if toc:
                break

    book["table_of_contents"] = toc
    return book


def generate_quiz(book_title, chapter, description="", toc=None):
    """Generate quiz questions about a chapter using Claude-style prompts.
    Returns a prompt that Orun can send to Claude for quiz generation."""

    context_parts = [f"Livre: {book_title}"]
    if chapter:
        context_parts.append(f"Chapitre: {chapter}")
    if description:
        context_parts.append(f"Description du livre: {description[:500]}")
    if toc:
        toc_text = "\n".join(f"- {ch['title']}" for ch in toc[:20])
        context_parts.append(f"Table des matieres:\n{toc_text}")

    context = "\n".join(context_parts)

    prompt = f"""Tu es un professeur qui teste la comprehension de lecture d'un etudiant.

{context}

Genere exactement 5 questions sur ce chapitre/section du livre:
1. Une question factuelle (rappel direct)
2. Une question conceptuelle (comprendre le pourquoi)
3. Une question d'application (comment utiliser dans la vie reelle)
4. Un texte a trous (cloze deletion)
5. Une question de comparaison ou mise en relation

Format ta reponse en JSON:
{{
    "questions": [
        {{
            "type": "Factual|Conceptual|Application|Cloze",
            "question": "...",
            "answer": "...",
            "difficulty": 1-5
        }}
    ]
}}

IMPORTANT: Les questions doivent tester la COMPREHENSION, pas la memorisation de details insignifiants.
L'etudiant doit prouver qu'il a vraiment lu et compris le contenu."""

    return prompt


def generate_flashcards_from_quiz(quiz_results, book_title, chapter):
    """Convert quiz results into flashcard format for Notion."""
    flashcards = []
    today = datetime.now().date().isoformat()

    for q in quiz_results.get("questions", []):
        flashcards.append({
            "Front": q["question"],
            "Back": q["answer"],
            "Type": q.get("type", "Factual"),
            "Difficulty": str(q.get("difficulty", 3)),
            "Chapter": chapter or "",
            "Quality": 0,
            "Repetitions": 0,
            "Ease Factor": 2.5,
            "Interval Days": 0,
            "Status": "New",
            # Book relation would be set via Notion API
        })

    return flashcards


def get_due_flashcards():
    """Get flashcards due for review today."""
    today = datetime.now().date().isoformat()

    # Query flashcards where Next Review <= today or Next Review is empty
    result = notion_query(FLASHCARDS_COLLECTION, limit=100)

    if not result:
        return []

    due = []
    cards = result if isinstance(result, list) else result.get("results", [])
    for card in cards:
        props = card.get("properties", {})
        next_review = props.get("Next Review", {}).get("date", {}).get("start")

        if not next_review or next_review <= today:
            due.append({
                "id": card.get("id"),
                "front": props.get("Front", {}).get("title", [{}])[0].get("plain_text", ""),
                "back": props.get("Back", {}).get("rich_text", [{}])[0].get("plain_text", ""),
                "type": props.get("Type", {}).get("select", {}).get("name", "Factual"),
                "chapter": props.get("Chapter", {}).get("rich_text", [{}])[0].get("plain_text", ""),
                "repetitions": props.get("Repetitions", {}).get("number", 0) or 0,
                "ease_factor": props.get("Ease Factor", {}).get("number", 2.5) or 2.5,
                "interval_days": props.get("Interval Days", {}).get("number", 0) or 0,
            })

    return due


def format_session_summary(book_title, chapter, start_page, end_page, quiz_score, flashcards_count):
    """Format a Telegram-friendly session summary."""
    pages = f"{end_page - start_page} pages" if start_page and end_page else ""
    parts = [
        f"Session de lecture enregistree",
        f"Livre: {book_title}",
    ]
    if chapter:
        parts.append(f"Chapitre: {chapter}")
    if pages:
        parts.append(f"Pages: {start_page} → {end_page} ({pages})")
    if quiz_score is not None:
        parts.append(f"Quiz: {quiz_score}/5")
    if flashcards_count:
        parts.append(f"{flashcards_count} flashcards generees")

    return "\n".join(parts)


if __name__ == "__main__":
    # Test
    print("=== Test Book Search ===")
    result = search_and_add_book("Atomic Habits James Clear")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n=== Test Quiz Prompt ===")
    prompt = generate_quiz("Atomic Habits", "Chapter 1 - The Surprising Power of Atomic Habits",
                          description="A book about building good habits and breaking bad ones")
    print(prompt[:500] + "...")

    print("\n=== Test SM-2 ===")
    r = sm2(4, 0, 2.5, 0)
    print(f"First review (quality=4): {r}")
    r = sm2(5, r['repetitions'], r['ease_factor'], r['interval_days'])
    print(f"Second review (quality=5): {r}")
