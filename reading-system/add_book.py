#!/usr/bin/env python3
"""Add a book to the Notion Books database via internal API (token_v2)."""

import json
import os
import sys
import uuid
import requests
from notion_cover_upload import upload_cover

TOKEN = open(os.path.expanduser("~/.notion-token")).read().strip()
BOOKS_COLLECTION = "2917d8ba-b3e4-419f-bc32-602c837acda1"
API = "https://www.notion.so/api/v3"


def get_schema():
    """Get Books collection schema to map property names to IDs."""
    resp = requests.post(f"{API}/syncRecordValues",
        cookies={"token_v2": TOKEN},
        headers={"Content-Type": "application/json"},
        json={"requests": [{"pointer": {"table": "collection", "id": BOOKS_COLLECTION}, "version": -1}]},
        timeout=15)
    data = resp.json()
    collection = data.get("recordMap", {}).get("collection", {}).get(BOOKS_COLLECTION, {}).get("value", {})
    schema = collection.get("schema", {})
    return {info.get("name", ""): prop_id for prop_id, info in schema.items()}


def add_book(title, author="", book_format="Physical", lang="EN", total_pages=0, cover_url="", today="", genre=None):
    """Create a book page in the Books collection."""
    if not today:
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")

    page_id = str(uuid.uuid4())
    name_to_id = get_schema()

    # Step 1: Create the page
    requests.post(f"{API}/submitTransaction",
        cookies={"token_v2": TOKEN},
        headers={"Content-Type": "application/json"},
        json={
            "requestId": str(uuid.uuid4()),
            "transactions": [{"id": str(uuid.uuid4()), "operations": [
                {"id": page_id, "table": "block", "path": [], "command": "set",
                 "args": {"type": "page", "id": page_id,
                          "parent_id": BOOKS_COLLECTION, "parent_table": "collection",
                          "alive": True, "properties": {"title": [[title]]}}},
                {"table": "collection", "id": BOOKS_COLLECTION,
                 "path": ["pages"], "command": "listAfter", "args": {"id": page_id}},
            ]}]
        }, timeout=15)

    # Step 2: Set properties
    ops = []
    ops.append({"pointer": {"table": "block", "id": page_id},
                "path": ["properties", "title"], "command": "set", "args": [[title]]})

    if author and name_to_id.get("Author"):
        ops.append({"pointer": {"table": "block", "id": page_id},
                    "path": ["properties", name_to_id["Author"]], "command": "set", "args": [[author]]})

    if name_to_id.get("Format"):
        ops.append({"pointer": {"table": "block", "id": page_id},
                    "path": ["properties", name_to_id["Format"]], "command": "set", "args": [[book_format]]})

    if name_to_id.get("Status"):
        ops.append({"pointer": {"table": "block", "id": page_id},
                    "path": ["properties", name_to_id["Status"]], "command": "set", "args": [["Reading"]]})

    if name_to_id.get("Language"):
        ops.append({"pointer": {"table": "block", "id": page_id},
                    "path": ["properties", name_to_id["Language"]], "command": "set", "args": [[lang]]})

    if total_pages and name_to_id.get("Total Pages"):
        ops.append({"pointer": {"table": "block", "id": page_id},
                    "path": ["properties", name_to_id["Total Pages"]], "command": "set", "args": [[str(total_pages)]]})

    if name_to_id.get("Pages Read"):
        ops.append({"pointer": {"table": "block", "id": page_id},
                    "path": ["properties", name_to_id["Pages Read"]], "command": "set", "args": [["0"]]})

    if cover_url and name_to_id.get("Cover URL"):
        ops.append({"pointer": {"table": "block", "id": page_id},
                    "path": ["properties", name_to_id["Cover URL"]], "command": "set", "args": [[cover_url]]})

    if genre and name_to_id.get("Genre"):
        # multi_select: format is [["tag1"], [","], ["tag2"]]
        genre_list = genre if isinstance(genre, list) else [genre]
        genre_args = []
        for i, g in enumerate(genre_list):
            if i > 0:
                genre_args.append([","])
            genre_args.append([g])
        ops.append({"pointer": {"table": "block", "id": page_id},
                    "path": ["properties", name_to_id["Genre"]], "command": "set", "args": genre_args})

    if name_to_id.get("Date Started"):
        ops.append({"pointer": {"table": "block", "id": page_id},
                    "path": ["properties", name_to_id["Date Started"]],
                    "command": "set", "args": [["‣", [["d", {"type": "date", "start_date": today}]]]]})

    if ops:
        requests.post(f"{API}/submitTransaction",
            cookies={"token_v2": TOKEN},
            headers={"Content-Type": "application/json"},
            json={"requestId": str(uuid.uuid4()),
                  "transactions": [{"id": str(uuid.uuid4()), "operations": ops}]},
            timeout=15)

    # Step 3: Upload cover
    cover_ok = False
    if cover_url:
        try:
            result = upload_cover(page_id, image_url=cover_url)
            cover_ok = result.get("status") == "success"
        except Exception as e:
            print(f"Cover upload error: {e}", file=sys.stderr)

    return {"page_id": page_id, "cover_uploaded": cover_ok}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_book.py '<json>'")
        print('Example: python add_book.py \'{"title":"Atomic Habits","author":"James Clear","pages":320}\'')
        sys.exit(1)

    data = json.loads(sys.argv[1])
    result = add_book(
        title=data.get("title", ""),
        author=data.get("author", ""),
        book_format=data.get("format", "Physical"),
        lang=data.get("lang", "EN"),
        total_pages=data.get("pages", 0),
        cover_url=data.get("cover_url", ""),
        genre=data.get("genre"),
    )
    print(json.dumps(result, ensure_ascii=False))
