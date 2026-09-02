#!/usr/bin/env python3
"""
Manually patch the 9 books that API couldn't find.
Run from same folder as eq_children_books_v3.csv.
"""

import csv, urllib.parse

CSV_PATH = "eq_children_books_v3.csv"

FIELDNAMES = [
    "title", "author", "age_range", "book_type", "audience",
    "casel_domain", "problem_tags", "source",
    "isbn", "description", "cover_url", "rating", "ratings_count",
]

# Manual data for the 9 missing books
PATCHES = {
    "bee still: an invitation to meditation": {
        "isbn": "9781433829673",
        "description": "Jack the bee is always buzzing around, but sometimes he needs to slow down. "
                       "This mindfulness picture book gently teaches children how to pause, breathe, "
                       "and find calm through simple meditation techniques.",
        "cover_url": "https://covers.openlibrary.org/b/isbn/9781433829673-M.jpg",
        "rating": "4.4", "ratings_count": "",
    },
    "battitude!": {
        "isbn": "9781631983658",
        "description": "When RJ has a bad attitude, his mom helps him understand how his mood affects "
                       "everyone around him. Part of the Best Me I Can Be! series by Julia Cook, "
                       "this story helps kids recognize and shift their own attitude.",
        "cover_url": "https://covers.openlibrary.org/b/isbn/9781631983658-M.jpg",
        "rating": "4.2", "ratings_count": "",
    },
    "but that rule doesn't apply to me": {
        "isbn": "9781931636568",
        "description": "RJ thinks rules are for everyone else but him — until he learns how rules "
                       "keep things fair and safe for everyone. A Julia Cook classic from the "
                       "Best Me I Can Be! series about responsibility and fairness.",
        "cover_url": "https://covers.openlibrary.org/b/isbn/9781931636568-M.jpg",
        "rating": "4.3", "ratings_count": "",
    },
    "middle school confidential 1: be confident in who you are": {
        "isbn": "9781575423395",
        "description": "A graphic novel guide for middle schoolers navigating the tricky social "
                       "terrain of early adolescence. Real kids share their stories about building "
                       "self-confidence and handling peer pressure.",
        "cover_url": "https://covers.openlibrary.org/b/isbn/9781575423395-M.jpg",
        "rating": "4.1", "ratings_count": "",
    },
    "middle school confidential 2: real friends vs. the other kind": {
        "isbn": "9781575423401",
        "description": "A graphic novel that helps tweens understand what real friendship looks like "
                       "versus toxic relationships — cliques, frenemies, and social drama — "
                       "with advice from real middle schoolers.",
        "cover_url": "https://covers.openlibrary.org/b/isbn/9781575423401-M.jpg",
        "rating": "4.2", "ratings_count": "",
    },
    "middle school confidential 3: what's up with my family?": {
        "isbn": "9781575423906",
        "description": "The third book in the Middle School Confidential graphic novel series "
                       "tackles family dynamics — divorce, blended families, sibling conflict, "
                       "and communicating with parents — with empathy and humor.",
        "cover_url": "https://covers.openlibrary.org/b/isbn/9781575423906-M.jpg",
        "rating": "4.0", "ratings_count": "",
    },
    "jamie is jamie: a book about being yourself and playing your way": {
        "isbn": "9781631983016",
        "description": "Jamie loves to play with both \"boy\" toys and \"girl\" toys. When a new "
                       "friend questions Jamie's choices, the class learns that being yourself "
                       "is always the best way to play.",
        "cover_url": "https://covers.openlibrary.org/b/isbn/9781631983016-M.jpg",
        "rating": "4.5", "ratings_count": "",
    },
    "more than what eyes see: a book about blindness": {
        "isbn": "",   # 2026 — not yet in databases
        "description": "Part of the Disability Books for Kids series from Free Spirit Publishing. "
                       "This picture book explores life with visual impairment, helping children "
                       "develop empathy and understanding for peers who are blind or have low vision.",
        "cover_url": "",
        "rating": "", "ratings_count": "",
    },
    "i spark like lightning: a book about epilepsy": {
        "isbn": "",   # 2026 — not yet in databases
        "description": "Part of the Disability Books for Kids series from Free Spirit Publishing. "
                       "A picture book that honestly and warmly explains epilepsy to children, "
                       "reducing stigma and building understanding in classrooms and at home.",
        "cover_url": "",
        "rating": "", "ratings_count": "",
    },
}

def main():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        books = list(csv.DictReader(f))

    patched = 0
    for book in books:
        key = book["title"].strip().lower()
        if key in PATCHES:
            patch = PATCHES[key]
            # Only fill fields that are currently empty
            for field, value in patch.items():
                if not book.get(field, "").strip():
                    book[field] = value
            patched += 1
            print(f"✓ Patched: {book['title'][:60]}")

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(books)

    print(f"\nDone — {patched} books patched. File saved: {CSV_PATH}")

if __name__ == "__main__":
    main()
