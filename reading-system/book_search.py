#!/usr/bin/env python3
"""Book search script using Google Books + Open Library APIs.
Searches by title/author/ISBN, returns metadata + table of contents when available."""

import sys
import json
import urllib.request
import urllib.parse
import urllib.error


def search_google_books(query, max_results=5):
    """Search Google Books API for book metadata."""
    params = urllib.parse.urlencode({"q": query, "maxResults": max_results, "langRestrict": ""})
    url = f"https://www.googleapis.com/books/v1/volumes?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ReadingSystem/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"[Google Books] Erreur: {e}", file=sys.stderr)
        return []

    results = []
    for item in data.get("items", []):
        info = item.get("volumeInfo", {})
        identifiers = {i["type"]: i["identifier"] for i in info.get("industryIdentifiers", [])}
        results.append({
            "source": "google",
            "title": info.get("title", ""),
            "subtitle": info.get("subtitle", ""),
            "authors": info.get("authors", []),
            "publisher": info.get("publisher", ""),
            "published_date": info.get("publishedDate", ""),
            "description": info.get("description", ""),
            "page_count": info.get("pageCount", 0),
            "categories": info.get("categories", []),
            "language": info.get("language", ""),
            "average_rating": info.get("averageRating", None),
            "isbn_13": identifiers.get("ISBN_13", ""),
            "isbn_10": identifiers.get("ISBN_10", ""),
            "cover_url": info.get("imageLinks", {}).get("thumbnail", ""),
            "preview_link": info.get("previewLink", ""),
        })
    return results


def search_open_library(query, max_results=5):
    """Search Open Library for book metadata + table of contents."""
    params = urllib.parse.urlencode({"q": query, "limit": max_results, "fields": "key,title,author_name,first_publish_year,isbn,number_of_pages_median,subject,cover_i,edition_key"})
    url = f"https://openlibrary.org/search.json?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ReadingSystem/1.0 (contact: prinsechris)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"[Open Library] Erreur: {e}", file=sys.stderr)
        return []

    results = []
    for doc in data.get("docs", [])[:max_results]:
        cover_id = doc.get("cover_i")
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else ""

        results.append({
            "source": "openlibrary",
            "title": doc.get("title", ""),
            "authors": doc.get("author_name", []),
            "first_publish_year": doc.get("first_publish_year", ""),
            "page_count": doc.get("number_of_pages_median", 0),
            "subjects": doc.get("subject", [])[:10],
            "isbn": (doc.get("isbn") or [""])[0],
            "cover_url": cover_url,
            "ol_key": doc.get("key", ""),
            "edition_keys": doc.get("edition_key", [])[:3],
        })
    return results


def get_table_of_contents(edition_key):
    """Fetch table of contents from Open Library edition."""
    url = f"https://openlibrary.org/books/{edition_key}.json"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ReadingSystem/1.0 (contact: prinsechris)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return []

    toc = data.get("table_of_contents", [])
    chapters = []
    for entry in toc:
        if isinstance(entry, dict):
            chapters.append({
                "title": entry.get("title", ""),
                "level": entry.get("level", 0),
                "pagenum": entry.get("pagenum", ""),
            })
        elif isinstance(entry, str):
            chapters.append({"title": entry, "level": 0, "pagenum": ""})
    return chapters


def search_book(query):
    """Combined search: Google Books + Open Library + TOC."""
    print(f"Recherche: '{query}'...\n")

    # Search both APIs
    google_results = search_google_books(query, max_results=3)
    ol_results = search_open_library(query, max_results=3)

    # Display Google Books results
    if google_results:
        print("=== Google Books ===")
        for i, book in enumerate(google_results, 1):
            print(f"\n[{i}] {book['title']}")
            if book['subtitle']:
                print(f"    Sous-titre: {book['subtitle']}")
            print(f"    Auteur(s): {', '.join(book['authors'])}")
            print(f"    Pages: {book['page_count']}")
            print(f"    Langue: {book['language']}")
            print(f"    ISBN-13: {book['isbn_13']}")
            if book['categories']:
                print(f"    Categories: {', '.join(book['categories'])}")
            if book['cover_url']:
                print(f"    Couverture: {book['cover_url']}")
            if book['description']:
                desc = book['description'][:200] + "..." if len(book['description']) > 200 else book['description']
                print(f"    Description: {desc}")

    # Display Open Library results + TOC
    if ol_results:
        print("\n=== Open Library ===")
        for i, book in enumerate(ol_results, 1):
            print(f"\n[{i}] {book['title']}")
            print(f"    Auteur(s): {', '.join(book['authors'])}")
            print(f"    Pages: {book['page_count']}")
            print(f"    ISBN: {book['isbn']}")
            print(f"    Premiere publication: {book['first_publish_year']}")
            if book['cover_url']:
                print(f"    Couverture: {book['cover_url']}")

            # Try to get TOC from editions
            for ek in book.get("edition_keys", []):
                toc = get_table_of_contents(ek)
                if toc:
                    print(f"    Table des matieres ({ek}):")
                    for ch in toc:
                        indent = "      " + "  " * ch.get("level", 0)
                        page = f" (p.{ch['pagenum']})" if ch.get('pagenum') else ""
                        print(f"{indent}- {ch['title']}{page}")
                    break

    # Return combined results as JSON for programmatic use
    return {
        "google": google_results,
        "openlibrary": ol_results,
    }


def search_book_json(query):
    """Return search results as JSON (for use by Orun/webhooks)."""
    google_results = search_google_books(query, max_results=3)
    ol_results = search_open_library(query, max_results=3)

    # Try to get TOC for first OL result
    toc = []
    if ol_results and ol_results[0].get("edition_keys"):
        for ek in ol_results[0]["edition_keys"]:
            toc = get_table_of_contents(ek)
            if toc:
                break

    # Merge best result
    best = {}
    if google_results:
        g = google_results[0]
        best = {
            "title": g["title"],
            "authors": g["authors"],
            "page_count": g["page_count"],
            "language": g["language"],
            "isbn": g["isbn_13"] or g["isbn_10"],
            "cover_url": g["cover_url"],
            "description": g["description"],
            "categories": g["categories"],
        }
    if ol_results:
        o = ol_results[0]
        if not best.get("page_count"):
            best["page_count"] = o["page_count"]
        if not best.get("cover_url"):
            best["cover_url"] = o["cover_url"]
        best["subjects"] = o.get("subjects", [])

    best["table_of_contents"] = toc
    return json.dumps(best, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python book_search.py <titre du livre>")
        print("       python book_search.py --json <titre du livre>")
        sys.exit(1)

    if sys.argv[1] == "--json":
        query = " ".join(sys.argv[2:])
        print(search_book_json(query))
    else:
        query = " ".join(sys.argv[1:])
        search_book(query)
