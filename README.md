# EQ Children — SEL Resource Database

A curated database of Social-Emotional Learning (SEL) resources for children, including YouTube videos and picture books, designed to power a recommendation system for parents and educators.

## What's in the database

| Resource type | Count | Table |
|---|---|---|
| YouTube videos | 2,427 | `videos` |
| Picture books | 365 | `books` |

## Classification system

**Category** (4 types):
- `children_video` — SEL animations and stories for children to watch directly
- `read_aloud` — Picture book read-aloud videos
- `sel_course` — Classroom curriculum, TEDx talks, educator resources
- `parent_guide` — Parenting advice and strategies for adults

**CASEL domains** (5):
- Self-Awareness
- Self-Management
- Social-Awareness
- Relationship-Skills
- Responsible-Decision-Making

**Problem tags** — ~70 emotion/topic tags (e.g. `anger`, `anxiety`, `friendship`, `growth-mindset`)

**Age range** — `age_min` / `age_max` (years, typically 2–14)

**Audience** — `children`, `parents`, `educators`

## Repository structure

```
data-collector/
├── data/
│   ├── scripts/
│   │   ├── fetch_youtube_sel.py      # YouTube Data API v3 collector (55 queries × 50 results)
│   │   ├── retag.py                  # Rule-based re-tagger (keyword regex)
│   │   ├── retag_llm.py              # LLM re-tagger (Claude Haiku, batches of 20)
│   │   └── import_videos_v3.py       # Supabase upsert importer
│   └── sql/
│       ├── schema_videos.sql          # Full table schema with GIN indexes and RLS
│       └── add_low_quality_flag.sql   # Migration: adds low_quality_flag boolean column
├── docs/
│   └── process-guide.html            # Full process documentation (bilingual)
├── .gitignore                         # Excludes *.csv and *.json data files
└── README.md
```

## Data pipeline

```
YouTube API → v2.csv (raw) → retag.py → v3.csv → Supabase (videos table)
                                      → retag_llm.py → v4.csv (in progress)
```

## How to run

### 1. Collect YouTube videos (run locally on Mac — not in cloud containers)

```bash
YOUTUBE_API_KEY=your_key python3 data/scripts/fetch_youtube_sel.py
# Output: eq_children_youtube_v2.csv (~2,400 videos, ~5,800 API quota units)
```

### 2. Rule-based re-tagging

```bash
python3 data/scripts/retag.py
# Input:  eq_children_youtube_v2.csv
# Output: eq_children_youtube_v3.csv
```

### 3. LLM re-tagging (optional, higher accuracy)

```bash
# Run inside a Claude session — uses the `claude` CLI
python3 data/scripts/retag_llm.py
# Resumes automatically from retag_llm_progress.json if interrupted
# Input:  eq_children_youtube_v2.csv → Output: eq_children_youtube_v4.csv
```

### 4. Import to Supabase

```bash
SUPABASE_URL=https://your-project.supabase.co \
SUPABASE_KEY=your_service_role_key \
CSV_PATH=eq_children_youtube_v3.csv \
python3 data/scripts/import_videos_v3.py
# Uses upsert on_conflict=video_id — safe to re-run
```

## Supabase schema highlights

- `problem_tags text[]` — GIN index for fast array containment queries (`@>`, `&&`)
- `audience text[]` — GIN index
- `low_quality_flag boolean` — marks videos older than 1 year with <500 views and 0 likes
- Row Level Security: public SELECT, service_role full access

### Example query — recommend videos by emotion tag + age

```sql
SELECT title, youtube_url, casel_domain, view_count
FROM videos
WHERE problem_tags @> ARRAY['anxiety']
  AND age_min <= 7 AND age_max >= 5
  AND low_quality_flag = false
ORDER BY view_count DESC
LIMIT 10;
```

## YouTube API quota

Each full run of `fetch_youtube_sel.py` uses approximately **5,858 / 10,000** daily quota units (resets at midnight Pacific time).

## Data quality

Videos are flagged (not deleted) as low quality when all three conditions are met:
- Published more than 1 year ago
- `view_count < 500`
- `like_count = 0`

Filter them out in queries with `WHERE low_quality_flag = false`.

## Full process documentation

See [`docs/process-guide.html`](docs/process-guide.html) for the complete bilingual (Chinese/English) guide covering every step, schema details, query examples, and instructions for adding new resources.
