#!/usr/bin/env python3
"""
Fetch Goodreads ratings via ISBN direct URL.
Strategy: goodreads.com/book/isbn/{isbn}  (most reliable, no search needed)
Fallback: goodreads.com/search?q={title}

Requirements: pip3 install requests beautifulsoup4
Run from same folder as eq_children_books_v3.csv.
"""

import csv, time, re, sys, json, random
import urllib.parse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4", "-q"])
    import requests
    from bs4 import BeautifulSoup

# ── CONFIG ───────────────────────────────────────────────────────────────────
CSV_PATH   = "eq_children_books_v3.csv"
MIN_DELAY  = 3.0    # min seconds between requests
MAX_DELAY  = 5.0    # max seconds (random jitter avoids pattern detection)
# ─────────────────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "title", "author", "age_range", "book_type", "audience",
    "casel_domain", "problem_tags", "source",
    "isbn", "description", "cover_url", "rating", "ratings_count",
    "goodreads_rating", "goodreads_ratings_count", "goodreads_url",
]

# Rotate user agents to look more human
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    })
    return s


session = make_session()


def sleep():
    t = random.uniform(MIN_DELAY, MAX_DELAY)
    time.sleep(t)


def extract_rating(html, url):
    """Try multiple patterns to extract Goodreads rating."""
    soup = BeautifulSoup(html, "html.parser")

    # Check for bot-detection / empty page
    if len(html) < 5000:
        return None, None, url

    # Method 1: JSON-LD (most reliable across design versions)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            agg = data.get("aggregateRating", {})
            rv = agg.get("ratingValue")
            rc = agg.get("ratingCount", "")
            if rv:
                return str(round(float(rv), 2)), str(rc), url
        except Exception:
            pass

    # Method 2: itemprop
    rv_tag = soup.find(itemprop="ratingValue")
    rc_tag = soup.find(itemprop="ratingCount")
    if rv_tag:
        return rv_tag.get_text(strip=True), (rc_tag.get_text(strip=True) if rc_tag else ""), url

    # Method 3: React data in __NEXT_DATA__ or window.__initialProps__
    for script in soup.find_all("script"):
        text = script.string or ""
        m = re.search(r'"averageRating"\s*:\s*"?(\d+\.\d+)"?', text)
        if m:
            mc = re.search(r'"ratingsCount"\s*:\s*(\d+)', text)
            return m.group(1), (mc.group(1) if mc else ""), url

    # Method 4: visible text patterns
    m = re.search(r'(\d\.\d{1,2})\s*avg rating', html)
    if m:
        mc = re.search(r'([\d,]+)\s*rating', html)
        count = mc.group(1).replace(",", "") if mc else ""
        return m.group(1), count, url

    return None, None, url


def fetch_page(url):
    """Fetch a URL, rotating User-Agent on each call."""
    session.headers["User-Agent"] = random.choice(USER_AGENTS)
    try:
        r = session.get(url, timeout=20, allow_redirects=True)
        return r.status_code, r.text, r.url
    except Exception as e:
        print(f"    ⚠ request failed: {e}")
        return None, "", url


def get_rating(isbn, title, author):
    """Try ISBN first, then title search."""

    # --- ISBN direct lookup ---
    if isbn:
        url = f"https://www.goodreads.com/book/isbn/{isbn}"
        status, html, final_url = fetch_page(url)
        if status == 200:
            rating, count, gr_url = extract_rating(html, final_url)
            if rating:
                return rating, count, gr_url
        elif status == 404:
            pass   # book not found by ISBN, try search
        elif status == 429:
            print("    ⚠ Rate limited (429) — waiting 30s…")
            time.sleep(30)
            return None, None, None

    # --- Title search fallback ---
    q = urllib.parse.quote_plus(f"{title} {author}")
    search_url = f"https://www.goodreads.com/search?q={q}&search_type=books"
    status, html, _ = fetch_page(search_url)

    if status != 200:
        return None, None, None

    soup = BeautifulSoup(html, "html.parser")

    # Find first book result link — try multiple selectors
    link = (
        soup.select_one("a.bookTitle") or
        soup.select_one(".BookListBook__title a") or
        soup.select_one("td.title a") or
        soup.select_one("a[href*='/book/show/']")
    )

    if not link:
        return None, None, None

    href = link.get("href", "")
    if not href.startswith("http"):
        href = "https://www.goodreads.com" + href

    sleep()
    status2, html2, final_url = fetch_page(href)
    if status2 == 200:
        return extract_rating(html2, final_url)

    return None, None, None


def main():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        books = list(csv.DictReader(f))

    for book in books:
        for col in ("goodreads_rating", "goodreads_ratings_count", "goodreads_url"):
            if col not in book:
                book[col] = ""

    todo = [b for b in books if not b.get("goodreads_rating", "").strip()]
    done_count = len(books) - len(todo)
    print(f"Loaded {len(books)} books — {len(todo)} need rating ({done_count} already done).\n")

    hits = 0
    for i, book in enumerate(todo, 1):
        title  = book["title"].strip()
        author = book["author"].strip()
        isbn   = book.get("isbn", "").strip()

        print(f"[{i:3}/{len(todo)}] {title[:55]}")

        rating, count, gr_url = get_rating(isbn, title, author)

        if rating:
            book["goodreads_rating"]        = rating
            book["goodreads_ratings_count"] = count or ""
            book["goodreads_url"]           = gr_url or ""
            hits += 1
            print(f"         ✓ {rating}  ({count} ratings)")
        else:
            print(f"         ✗ not found")

        # Save after every book
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(books)

        sleep()

    print(f"\n{'='*60}")
    print(f"Done — {hits}/{len(todo)} Goodreads ratings added.")


if __name__ == "__main__":
    main()
