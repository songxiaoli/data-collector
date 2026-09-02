#!/usr/bin/env python3
"""
Enrich eq_children_books_v2.csv with Google Books metadata:
- isbn (ISBN-13)
- description (truncated to 400 chars)
- cover_url (thumbnail)
- rating (averageRating)
- ratings_count

Output: eq_children_books_v3.csv
"""

import csv
import time
import json
import urllib.request
import urllib.parse
import urllib.error

# ── CONFIG ──────────────────────────────────────────────────────────────────
API_KEY = "AIzaSyCUU2i1X2gDzd6o45YKfjgzfHlLOdLaJRU"
INPUT_CSV  = "eq_children_books_v2.csv"
OUTPUT_CSV = "eq_children_books_v3.csv"
DELAY = 1.0          # seconds between API calls (≤1000/day free quota)
MAX_RETRIES = 3      # retry on 503 with exponential backoff
MAX_DESC_LEN = 400   # truncate descriptions at this length
# ────────────────────────────────────────────────────────────────────────────

def query_google_books(title, author):
    """
    Search Google Books API. Returns dict with isbn, description,
    cover_url, rating, ratings_count — or empty strings on failure.
    """
    empty = {"isbn": "", "description": "", "cover_url": "", "rating": "", "ratings_count": ""}

    # Build query: title + author
    q = f'intitle:"{title}" inauthor:"{author}"'
    params = urllib.parse.urlencode({
        "q": q,
        "maxResults": 1,
        "printType": "books",
        "key": API_KEY,
    })
    url = f"https://www.googleapis.com/books/v1/volumes?{params}"

    def fetch_with_retry(fetch_url):
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(fetch_url, headers={"User-Agent": "BookEnricher/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 503 and attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt * 2  # 2s, 4s, 8s
                    print(f"  ⚠ 503 for '{title}', retrying in {wait}s…")
                    time.sleep(wait)
                else:
                    print(f"  ⚠ API error for '{title}': {e}")
                    return None
            except Exception as e:
                print(f"  ⚠ API error for '{title}': {e}")
                return None
        return None

    data = fetch_with_retry(url)
    if data is None:
        return empty

    items = data.get("items", [])
    if not items:
        # Retry with title only (some books have ambiguous author spellings)
        params2 = urllib.parse.urlencode({
            "q": f'intitle:"{title}"',
            "maxResults": 1,
            "printType": "books",
            "key": API_KEY,
        })
        url2 = f"https://www.googleapis.com/books/v1/volumes?{params2}"
        data2 = fetch_with_retry(url2)
        if data2:
            items = data2.get("items", [])

    if not items:
        return empty

    vol = items[0]["volumeInfo"]

    # ISBN-13 preferred, fall back to ISBN-10
    isbn = ""
    for id_obj in vol.get("industryIdentifiers", []):
        if id_obj.get("type") == "ISBN_13":
            isbn = id_obj["identifier"]
            break
    if not isbn:
        for id_obj in vol.get("industryIdentifiers", []):
            if id_obj.get("type") == "ISBN_10":
                isbn = id_obj["identifier"]
                break

    # Description — strip HTML-ish tags crudely and truncate
    desc = vol.get("description", "")
    desc = desc.replace("<br>", " ").replace("<p>", " ").replace("</p>", " ")
    if len(desc) > MAX_DESC_LEN:
        desc = desc[:MAX_DESC_LEN].rsplit(" ", 1)[0] + "…"

    # Cover URL — prefer "thumbnail", upgrade to "zoom=1" for slightly larger
    image_links = vol.get("imageLinks", {})
    cover = image_links.get("thumbnail", image_links.get("smallThumbnail", ""))
    # Switch http → https and remove curl parameter
    cover = cover.replace("http://", "https://")

    rating = str(vol.get("averageRating", ""))
    ratings_count = str(vol.get("ratingsCount", ""))

    return {
        "isbn": isbn,
        "description": desc,
        "cover_url": cover,
        "rating": rating,
        "ratings_count": ratings_count,
    }


def main():
    # Read existing books
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        books = list(reader)

    print(f"Loaded {len(books)} books from {INPUT_CSV}")
    print(f"Starting enrichment (delay={DELAY}s between calls)…\n")

    fieldnames = [
        "title", "author", "age_range", "book_type", "audience",
        "casel_domain", "problem_tags", "source",
        "isbn", "description", "cover_url", "rating", "ratings_count",
    ]

    # Resume support: load already-enriched rows by title key
    already_done = {}
    try:
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                already_done[row["title"].lower().strip()] = row
        if already_done:
            print(f"Resuming — {len(already_done)} books already enriched, skipping them.\n")
    except FileNotFoundError:
        pass

    enriched = list(already_done.values())
    hits = sum(1 for r in enriched if r.get("isbn") or r.get("description") or r.get("cover_url"))
    misses = len(enriched) - hits

    for i, book in enumerate(books, 1):
        title  = book["title"].strip()
        author = book["author"].strip()
        key    = title.lower().strip()

        # Skip if already enriched in a previous run
        if key in already_done:
            print(f"[{i:3}/{len(books)}] – {title[:55]} (skipped)")
            continue

        meta = query_google_books(title, author)

        got = bool(meta["isbn"] or meta["description"] or meta["cover_url"])
        if got:
            hits += 1
            marker = "✓"
        else:
            misses += 1
            marker = "✗"

        print(f"[{i:3}/{len(books)}] {marker} {title[:55]}")

        enriched.append({**book, **meta})

        # Write incrementally so progress survives a crash
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(enriched)

        time.sleep(DELAY)

    # Write enriched CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched)

    print(f"\n{'='*60}")
    print(f"Done! {hits}/{len(books)} books enriched ({misses} missed).")
    print(f"Output: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
