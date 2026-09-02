#!/usr/bin/env python3
"""
Fetch YouTube SEL (Social Emotional Learning) videos for children using YouTube Data API v3.

Setup:
  pip3 install google-api-python-client

Usage:
  YOUTUBE_API_KEY=your_key python3 fetch_youtube_sel.py

Output: eq_children_youtube_v2.csv
"""

import csv, os, sys, time, re

try:
    from googleapiclient.discovery import build
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "google-api-python-client", "-q"])
    from googleapiclient.discovery import build

# ── CONFIG ────────────────────────────────────────────────────────────────────
API_KEY   = os.environ.get("YOUTUBE_API_KEY", "")
OUT_CSV   = "eq_children_youtube_v2.csv"
MAX_PER_Q = 50   # max results per search query (API max = 50)
DELAY     = 0.5  # seconds between API calls
# ─────────────────────────────────────────────────────────────────────────────

if not API_KEY:
    print("ERROR: set YOUTUBE_API_KEY environment variable.")
    sys.exit(1)

FIELDNAMES = [
    "title", "channel_name", "youtube_url", "video_id",
    "content_type", "category", "description",
    "casel_domain", "problem_tags",
    "age_min", "age_max", "audience",
    "published_at", "duration", "view_count", "like_count",
    "thumbnail_url", "language",
]

# ── SEARCH QUERIES ────────────────────────────────────────────────────────────
# Each entry: (query_string, category, casel_domain, problem_tags, age_min, age_max, audience)
QUERIES = [
    # ── Self-Awareness / Emotions ─────────────────────────────────────────────
    ("social emotional learning children emotions feelings",
     "children_video", "Self-Awareness", "emotions,feelings,emotional-literacy", 4, 10, "children"),
    ("anger management kids children self regulation",
     "children_video", "Self-Management", "anger,anger-management,self-regulation", 5, 11, "children"),
    ("anxiety worry kids children coping strategies",
     "children_video", "Self-Management", "anxiety,worry,coping-skills,calm", 5, 12, "children"),
    ("self control impulse control kids children",
     "children_video", "Self-Management", "self-control,impulse-control,self-regulation", 5, 10, "children"),
    ("growth mindset children kids fixed mindset",
     "sel_course", "Self-Awareness", "growth-mindset,perseverance,resilience,learning", 5, 12, "children,educators"),
    ("mindfulness meditation children kids breathing calm",
     "children_video", "Self-Management", "mindfulness,breathing,calm,stress,focus", 4, 12, "children"),
    ("zones of regulation SEL children elementary",
     "sel_course", "Self-Management", "zones-of-regulation,self-regulation,emotional-regulation", 5, 11, "children,educators"),
    ("feelings emotions read aloud picture book children",
     "read_aloud", "Self-Awareness", "emotions,feelings,emotional-literacy", 3, 8, "children"),
    ("confidence self esteem children kids",
     "children_video", "Self-Awareness", "confidence,self-esteem,identity", 6, 12, "children"),
    # ── Social-Awareness / Empathy ────────────────────────────────────────────
    ("empathy kindness children kids social skills",
     "children_video", "Social-Awareness", "empathy,kindness,compassion", 5, 11, "children"),
    ("bullying prevention upstander kids children",
     "children_video", "Responsible-Decision-Making", "bullying,bullying-prevention,courage,bystander", 6, 13, "children"),
    ("diversity inclusion acceptance children kids",
     "children_video", "Social-Awareness", "diversity,inclusion,acceptance", 4, 11, "children"),
    ("disability acceptance inclusion children picture book",
     "read_aloud", "Social-Awareness", "disability,inclusion,empathy,acceptance", 5, 11, "children"),
    # ── Relationship Skills ───────────────────────────────────────────────────
    ("friendship social skills children elementary school",
     "children_video", "Relationship-Skills", "friendship,social-skills,kindness", 5, 11, "children"),
    ("conflict resolution problem solving kids elementary",
     "children_video", "Relationship-Skills", "conflict-resolution,problem-solving,compromise", 5, 11, "children"),
    ("teamwork cooperation collaboration children kids",
     "children_video", "Relationship-Skills", "teamwork,cooperation,collaboration", 5, 12, "children"),
    ("kindness read aloud children picture book SEL",
     "read_aloud", "Relationship-Skills", "kindness,friendship,empathy", 3, 9, "children"),
    # ── Responsible Decision Making ───────────────────────────────────────────
    ("responsible decision making consequences kids",
     "sel_course", "Responsible-Decision-Making", "decision-making,consequences,responsibility", 7, 13, "children"),
    ("digital citizenship online safety kids children",
     "parent_guide", "Responsible-Decision-Making", "digital-literacy,online-safety,cyberbullying", 8, 14, "children,educators"),
    # ── Parent / Educator ─────────────────────────────────────────────────────
    ("social emotional learning SEL classroom elementary teacher",
     "sel_course", "Self-Awareness", "social-emotional-learning,classroom,CASEL", 5, 13, "educators"),
    ("parenting child emotional regulation tantrums big feelings",
     "parent_guide", "Self-Management", "parenting,big-feelings,emotional-regulation,tantrums", 3, 12, "parents"),
    ("child anxiety worry parenting strategies",
     "parent_guide", "Self-Management", "anxiety,parenting,coping-skills,worry", 4, 12, "parents"),
    ("child anger meltdown parenting calm response",
     "parent_guide", "Self-Management", "anger,parenting,self-regulation,meltdown", 3, 12, "parents"),
    # ── Read Aloud channels / SEL books ──────────────────────────────────────
    ("read aloud SEL social emotional learning book children",
     "read_aloud", "Self-Awareness", "emotions,read-aloud,empathy,friendship", 3, 9, "children,parents"),
    ("children book read aloud empathy diversity classroom",
     "read_aloud", "Social-Awareness", "empathy,diversity,inclusion", 4, 10, "children,parents"),
    # ── Specific topics ───────────────────────────────────────────────────────
    ("sadness grief loss children kids how to cope",
     "children_video", "Self-Awareness", "sadness,grief,loss,coping-skills", 5, 11, "children"),
    ("jealousy envy kids children how to handle",
     "children_video", "Self-Awareness", "jealousy,envy,emotions", 5, 10, "children"),
    ("loneliness making friends children school new student",
     "children_video", "Relationship-Skills", "loneliness,friendship,new-school,social-skills", 5, 11, "children"),
    ("perseverance grit resilience children kids story",
     "children_video", "Self-Management", "perseverance,grit,resilience,growth-mindset", 5, 12, "children"),
    ("gratitude appreciation children kids activity",
     "children_video", "Self-Awareness", "gratitude,appreciation,kindness", 5, 11, "children"),

    # ══ NEW QUERIES ═══════════════════════════════════════════════════════════

    # ── More specific emotions ────────────────────────────────────────────────
    ("frustration disappointment children kids manage feelings",
     "children_video", "Self-Management", "frustration,disappointment,emotions,coping-skills", 4, 11, "children"),
    ("embarrassment shame children kids feelings",
     "children_video", "Self-Awareness", "embarrassment,shame,emotions,self-awareness", 5, 11, "children"),
    ("fear scared children kids how to cope brave",
     "children_video", "Self-Management", "fear,brave,courage,coping-skills,anxiety", 4, 10, "children"),
    ("Daniel Tiger emotions feelings PBS kids",
     "children_video", "Self-Awareness", "emotions,feelings,emotional-literacy,self-regulation", 2, 7, "children"),
    ("Sesame Street emotions feelings kids",
     "children_video", "Self-Awareness", "emotions,feelings,emotional-literacy", 2, 7, "children"),

    # ── Family changes & transitions ─────────────────────────────────────────
    ("divorce separation children kids feelings cope",
     "children_video", "Self-Management", "divorce,family-change,big-feelings,coping-skills", 5, 12, "children,parents"),
    ("new baby sibling jealousy children kids adjust",
     "children_video", "Self-Awareness", "jealousy,new-sibling,family-change,emotions", 3, 8, "children,parents"),
    ("moving new school anxiety children transition",
     "children_video", "Self-Management", "moving,new-school,transition,anxiety,worry", 5, 11, "children"),
    ("death grief loss children kids picture book read aloud",
     "read_aloud", "Self-Awareness", "grief,loss,death,sadness,coping-skills", 4, 10, "children,parents"),

    # ── Special needs & neurodiversity ────────────────────────────────────────
    ("ADHD children self regulation focus attention kids",
     "children_video", "Self-Management", "ADHD,focus,self-regulation,attention,impulse-control", 5, 12, "children,parents"),
    ("autism social skills children kids understanding",
     "children_video", "Relationship-Skills", "autism,social-skills,neurodiversity,inclusion", 5, 13, "children,parents,educators"),
    ("sensory processing children kids feelings calm",
     "children_video", "Self-Management", "sensory,self-regulation,calm,big-feelings", 4, 10, "children,parents"),

    # ── Tweens / Middle school ────────────────────────────────────────────────
    ("social emotional learning middle school tweens",
     "sel_course", "Self-Awareness", "social-emotional-learning,middle-school,tweens", 10, 14, "children,educators"),
    ("peer pressure middle school tweens decision making",
     "children_video", "Responsible-Decision-Making", "peer-pressure,decision-making,middle-school,tweens", 10, 14, "children"),
    ("teen anxiety stress middle school coping skills",
     "children_video", "Self-Management", "anxiety,stress,middle-school,coping-skills,tweens", 10, 14, "children,parents"),

    # ── Popular SEL channels ─────────────────────────────────────────────────
    ("GoNoodle kids movement mindfulness social emotional",
     "children_video", "Self-Management", "mindfulness,movement,calm,focus,self-regulation", 4, 10, "children"),
    ("Cosmic Kids Yoga mindfulness children calm",
     "children_video", "Self-Management", "yoga,mindfulness,calm,breathing,focus", 4, 12, "children"),
    ("The Learning Station children songs emotions feelings",
     "children_video", "Self-Awareness", "emotions,feelings,songs,emotional-literacy", 3, 8, "children"),

    # ── More read-alouds ─────────────────────────────────────────────────────
    ("anger read aloud picture book children feelings",
     "read_aloud", "Self-Management", "anger,big-feelings,self-regulation,emotions", 3, 8, "children"),
    ("anxiety worry read aloud picture book children",
     "read_aloud", "Self-Management", "anxiety,worry,fear,coping-skills", 3, 9, "children"),
    ("growth mindset read aloud picture book children",
     "read_aloud", "Self-Awareness", "growth-mindset,perseverance,resilience", 4, 9, "children"),
    ("self esteem confidence read aloud picture book children",
     "read_aloud", "Self-Awareness", "self-esteem,confidence,identity", 4, 9, "children"),
    ("friendship read aloud picture book children school",
     "read_aloud", "Relationship-Skills", "friendship,kindness,social-skills", 3, 9, "children"),

    # ── Educator resources ────────────────────────────────────────────────────
    ("SEL morning meeting classroom activities elementary",
     "sel_course", "Relationship-Skills", "morning-meeting,classroom,social-emotional-learning,community", 5, 11, "educators"),
    ("trauma informed teaching children classroom strategies",
     "sel_course", "Self-Management", "trauma-informed,classroom,self-regulation,educator", 4, 12, "educators"),
    ("positive behavior support classroom children strategies",
     "sel_course", "Responsible-Decision-Making", "positive-behavior,classroom,self-regulation,strategies", 4, 11, "educators"),

    # ── Spanish language ─────────────────────────────────────────────────────
    ("emociones niños infantil aprender sentimientos",
     "children_video", "Self-Awareness", "emotions,feelings,emotional-literacy,spanish", 3, 9, "children"),
    ("inteligencia emocional niños cuentos educacion",
     "children_video", "Self-Awareness", "social-emotional-learning,emotions,spanish", 4, 10, "children,parents"),
]

# ─────────────────────────────────────────────────────────────────────────────

def get_video_details(youtube, video_ids):
    """Fetch duration, view count, like count for a list of video IDs."""
    if not video_ids:
        return {}
    resp = youtube.videos().list(
        part="contentDetails,statistics",
        id=",".join(video_ids)
    ).execute()
    details = {}
    for item in resp.get("items", []):
        vid = item["id"]
        dur = item.get("contentDetails", {}).get("duration", "")
        m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', dur)
        if m:
            h, mi, s = (int(x or 0) for x in m.groups())
            if h:
                dur_str = f"{h}:{mi:02d}:{s:02d}"
            else:
                dur_str = f"{mi}:{s:02d}"
        else:
            dur_str = ""
        stats = item.get("statistics", {})
        details[vid] = {
            "duration":   dur_str,
            "view_count": stats.get("viewCount", ""),
            "like_count": stats.get("likeCount", ""),
        }
    return details


def search_and_collect(youtube, query_info):
    query, category, casel_domain, problem_tags, age_min, age_max, audience = query_info
    print(f"  Searching: {query[:65]}…")
    try:
        resp = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=MAX_PER_Q,
            relevanceLanguage="en",
            videoCaption="any",
        ).execute()
    except Exception as e:
        print(f"    ⚠ Error: {e}")
        return []

    items = resp.get("items", [])
    video_ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
    details = get_video_details(youtube, video_ids)

    rows = []
    for it in items:
        vid = it.get("id", {}).get("videoId", "")
        if not vid:
            continue
        sn = it.get("snippet", {})
        title   = sn.get("title", "").strip()
        channel = sn.get("channelTitle", "").strip()
        desc    = sn.get("description", "").strip()[:300]
        pub     = sn.get("publishedAt", "")[:10]
        thumb   = sn.get("thumbnails", {}).get("medium", {}).get("url", "")
        d       = details.get(vid, {})
        rows.append({
            "title":        title,
            "channel_name": channel,
            "youtube_url":  f"https://www.youtube.com/watch?v={vid}",
            "video_id":     vid,
            "content_type": "video",
            "category":     category,
            "description":  desc,
            "casel_domain": casel_domain,
            "problem_tags": problem_tags,
            "age_min":      age_min,
            "age_max":      age_max,
            "audience":     audience,
            "published_at": pub,
            "duration":     d.get("duration", ""),
            "view_count":   d.get("view_count", ""),
            "like_count":   d.get("like_count", ""),
            "thumbnail_url": thumb,
            "language":     "English",
        })
    return rows


def dedupe(rows):
    """Remove duplicate video_ids, keep first occurrence."""
    seen = set()
    out = []
    for r in rows:
        vid = r.get("video_id", "") or r.get("youtube_url", "")
        if vid not in seen:
            seen.add(vid)
            out.append(r)
    return out


def main():
    youtube = build("youtube", "v3", developerKey=API_KEY)

    all_rows = []
    total_queries = len(QUERIES)
    for i, q_info in enumerate(QUERIES, 1):
        print(f"[{i}/{total_queries}]", end=" ")
        rows = search_and_collect(youtube, q_info)
        all_rows.extend(rows)
        print(f"    → {len(rows)} videos (total so far: {len(all_rows)})")
        time.sleep(DELAY)

    all_rows = dedupe(all_rows)
    print(f"\nAfter deduplication: {len(all_rows)} unique videos")

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"✓ Saved {len(all_rows)} videos → {OUT_CSV}")

    used = total_queries * 101
    print(f"\nEstimated quota used: ~{used} / 10,000 units")


if __name__ == "__main__":
    main()
