#!/usr/bin/env python3
"""
Import eq_children_youtube_v2.csv into Supabase videos table.

Setup:
  pip3 install supabase

Usage:
  SUPABASE_URL=https://xxxx.supabase.co \
  SUPABASE_KEY=your_service_role_key \
  python3 import_videos_to_supabase.py
"""

import csv, os, sys, re

try:
    from supabase import create_client
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "supabase", "-q"])
    from supabase import create_client

# ── CONFIG ────────────────────────────────────────────────────
CSV_PATH      = "eq_children_youtube_v2.csv"
SUPABASE_URL  = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "")   # use service_role key
BATCH_SIZE    = 50
# ─────────────────────────────────────────────────────────────

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: set SUPABASE_URL and SUPABASE_KEY environment variables.")
    sys.exit(1)


def parse_tags(tags_str):
    if not tags_str:
        return []
    return [t.strip() for t in tags_str.split(",") if t.strip()]


def parse_int(val):
    try:
        return int(str(val).replace(",", "")) if val and str(val).strip() else None
    except ValueError:
        return None


def parse_date(val):
    """'2021-08-01' → keep as-is; empty → None"""
    if val and val.strip():
        return val.strip()
    return None


def transform(row):
    return {
        "title":          row["title"].strip(),
        "channel_name":   row.get("channel_name", "").strip() or None,
        "youtube_url":    row["youtube_url"].strip(),
        "video_id":       row["video_id"].strip(),
        "content_type":   row.get("content_type", "video").strip() or "video",
        "category":       row.get("category", "").strip() or None,
        "description":    row.get("description", "").strip() or None,
        "casel_domain":   row.get("casel_domain", "").strip() or None,
        "problem_tags":   parse_tags(row.get("problem_tags", "")),
        "age_min":        parse_int(row.get("age_min")),
        "age_max":        parse_int(row.get("age_max")),
        "audience":       parse_tags(row.get("audience", "")),
        "published_at":   parse_date(row.get("published_at")),
        "duration":       row.get("duration", "").strip() or None,
        "view_count":     parse_int(row.get("view_count")),
        "like_count":     parse_int(row.get("like_count")),
        "thumbnail_url":  row.get("thumbnail_url", "").strip() or None,
        "language":       row.get("language", "English").strip() or "English",
    }


def main():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        raw = list(csv.DictReader(f))

    rows = [transform(r) for r in raw]
    print(f"Loaded {len(rows)} videos. Connecting to Supabase…")

    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    inserted = 0
    errors = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        try:
            client.table("videos") \
                  .upsert(batch, on_conflict="video_id") \
                  .execute()
            inserted += len(batch)
            print(f"  Uploaded {inserted}/{len(rows)}…")
        except Exception as e:
            print(f"  ⚠ Batch {i//BATCH_SIZE + 1} error: {e}")
            errors += len(batch)

    print(f"\n✓ Done — {inserted} videos imported, {errors} errors.")
    print(f"  Table: videos")
    print(f"  URL:   {SUPABASE_URL}")


if __name__ == "__main__":
    main()
