#!/usr/bin/env python3
"""
Fill in the 58 missing books in eq_children_books_v3.csv.
Strategy:
  1. Try Google Books API again (quota may have reset)
  2. If still missing, fall back to Open Library API (free, no key needed)

Run from the same folder as eq_children_books_v3.csv.
Output: overwrites eq_children_books_v3.csv in place.
"""

import csv
import time
import json
import urllib.request
import urllib.parse
import urllib.error

# ── CONFIG ──────────────────────────────────────────────────────────────────
API_KEY      = "AIzaSyCUU2i1X2gDzd6o45YKfjgzfHlLOdLaJRU"
CSV_PATH     = "eq_children_books_v3.csv"
DELAY        = 1.2           # seconds between Google Books calls
MAX_RETRIES  = 3
MAX_DESC_LEN = 400
# ────────────────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "title", "author", "age_range", "book_type", "audience",
    "casel_domain", "problem_tags", "source",
    "isbn", "description", "cover_url", "rating", "ratings_count",
]


# ── helpers ──────────────────────────────────────────────────────────────────

def truncate(text, length=MAX_DESC_LEN):
    text = text.replace("<br>", " ").replace("<p>", " ").replace("</p>", " ").strip()
    if len(text) > length:
        text = text[:length].rsplit(" ", 1)[0] + "…"
    return text


def safe_fetch(url, label=""):
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BookEnricher/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (503,) and attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt * 2
                print(f"    ↩ {e.code} retry in {wait}s…")
                time.sleep(wait)
            else:
                print(f"    ✗ HTTP {e.code}: {label}")
                return None
        except Exception as e:
            print(f"    ✗ Error: {e} ({label})")
            return None
    return None


# ── Google Books ──────────────────────────────────────────────────────────────

def from_google(title, author):
    empty = {"isbn": "", "description": "", "cover_url": "", "rating": "", "ratings_count": ""}

    def search(q):
        params = urllib.parse.urlencode({
            "q": q, "maxResults": 1, "printType": "books", "key": API_KEY,
        })
        return safe_fetch(
            f"https://www.googleapis.com/books/v1/volumes?{params}",
            label=title,
        )

    data = search(f'intitle:"{title}" inauthor:"{author}"')
    items = (data or {}).get("items", [])

    if not items:
        data2 = search(f'intitle:"{title}"')
        items = (data2 or {}).get("items", [])

    if not items:
        return empty

    vol = items[0]["volumeInfo"]

    isbn = ""
    for id_obj in vol.get("industryIdentifiers", []):
        if id_obj.get("type") == "ISBN_13":
            isbn = id_obj["identifier"]; break
    if not isbn:
        for id_obj in vol.get("industryIdentifiers", []):
            if id_obj.get("type") == "ISBN_10":
                isbn = id_obj["identifier"]; break

    image_links = vol.get("imageLinks", {})
    cover = image_links.get("thumbnail", image_links.get("smallThumbnail", ""))
    cover = cover.replace("http://", "https://")

    return {
        "isbn":          isbn,
        "description":   truncate(vol.get("description", "")),
        "cover_url":     cover,
        "rating":        str(vol.get("averageRating", "")),
        "ratings_count": str(vol.get("ratingsCount", "")),
    }


# ── Open Library ──────────────────────────────────────────────────────────────

def from_open_library(title, author):
    empty = {"isbn": "", "description": "", "cover_url": "", "rating": "", "ratings_count": ""}

    # Search by title + author
    q = urllib.parse.urlencode({"title": title, "author": author, "limit": 1})
    data = safe_fetch(f"https://openlibrary.org/search.json?{q}", label=title)

    if not data:
        # Retry title-only
        q2 = urllib.parse.urlencode({"title": title, "limit": 1})
        data = safe_fetch(f"https://openlibrary.org/search.json?{q2}", label=title)

    docs = (data or {}).get("docs", [])
    if not docs:
        return empty

    doc = docs[0]

    # ISBN — prefer ISBN-13 (13 digits)
    isbn = ""
    for candidate in doc.get("isbn", []):
        if len(candidate) == 13:
            isbn = candidate; break
    if not isbn:
        candidates = doc.get("isbn", [])
        isbn = candidates[0] if candidates else ""

    # Description — Open Library stores it on the work record
    desc = ""
    work_key = doc.get("key", "")  # e.g. "/works/OL12345W"
    if work_key:
        work = safe_fetch(f"https://openlibrary.org{work_key}.json", label=title)
        if work:
            raw = work.get("description", "")
            if isinstance(raw, dict):
                raw = raw.get("value", "")
            desc = truncate(raw)

    # Cover image via OLID or ISBN
    cover = ""
    cover_i = doc.get("cover_i")
    if cover_i:
        cover = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
    elif isbn:
        cover = f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"

    return {
        "isbn":          isbn,
        "description":   desc,
        "cover_url":     cover,
        "rating":        "",   # Open Library doesn't expose ratings
        "ratings_count": "",
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        books = list(csv.DictReader(f))

    missing = [
        b for b in books
        if not (b.get("isbn") or b.get("description") or b.get("cover_url"))
    ]
    print(f"Loaded {len(books)} books — {len(missing)} need enrichment.\n")

    updates = 0
    for i, book in enumerate(missing, 1):
        title  = book["title"].strip()
        author = book["author"].strip()
        print(f"[{i:2}/{len(missing)}] {title[:60]}")

        # 1) Google Books
        meta = from_google(title, author)
        source_used = "Google"
        time.sleep(DELAY)

        # 2) Open Library fallback
        if not (meta["isbn"] or meta["description"] or meta["cover_url"]):
            print(f"         → trying Open Library…")
            meta = from_open_library(title, author)
            source_used = "OpenLib"
            time.sleep(0.5)

        got = bool(meta["isbn"] or meta["description"] or meta["cover_url"])
        marker = f"✓ ({source_used})" if got else "✗ still missing"
        print(f"         → {marker}")

        if got:
            # Update in-place
            for b in books:
                if b["title"].strip().lower() == title.lower():
                    b.update(meta)
                    updates += 1
                    break

        # Save after every book
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(books)

    print(f"\n{'='*60}")
    print(f"Done — {updates}/{len(missing)} previously-missing books enriched.")
    print(f"File updated: {CSV_PATH}")


if __name__ == "__main__":
    main()
