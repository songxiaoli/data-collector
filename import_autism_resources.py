#!/usr/bin/env python3
"""Import data/raw/autism_resources_v3.json -> Supabase `autism_resources`.

Run data/sql/schema_autism_resources.sql in the Supabase SQL editor first.

The service key is read from the environment, never hardcoded:

    export SUPABASE_SERVICE_KEY='...'
    python3 import_autism_resources.py            # import
    python3 import_autism_resources.py --dry-run  # derive stages, print counts, write nothing
"""
import json, os, sys
from pathlib import Path
from collections import Counter

def load_service_key():
    """Environment first, then .env beside this file. The value is never printed."""
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if key:
        return key.strip()
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("SUPABASE_SERVICE_KEY="):
                return line.split("=", 1)[1].strip().strip("\'\"")
    return None

SUPABASE_URL = "https://nhdswigpkiwbgtxugtmw.supabase.co"
JSON_PATH    = Path(__file__).parent / "data" / "raw" / "autism_resources_v3.json"
BATCH        = 50

# ── Matching axis 2 ─────────────────────────────────────────────────────────
# The SEL finder has one axis. This library needs a second: where the family
# is in the process. Stage is derived from need tags rather than stored by
# hand, so it stays consistent as the library grows. A resource can belong to
# several stages — these are not a partition.
STAGE_RULES = {
    "suspecting": {
        "understanding-autism", "seeking-diagnosis", "explaining-to-others",
    },
    "assessment": {
        "seeking-diagnosis", "insurance-funding", "co-occurring",
    },
    "newly-diagnosed": {
        "just-diagnosed", "understanding-autism", "caregiver-burnout",
        "siblings", "explaining-to-others",
    },
    "school-years": {
        "iep-504", "school-advocacy", "classroom-strategies", "transitions-routines",
        "meltdowns-shutdowns", "sensory-processing", "self-regulation", "stimming",
        "nonspeaking-aac", "speech-language", "social-communication", "echolalia",
        "friendship-peers", "bullying", "sleep", "toileting", "feeding-eating",
        "safety-elopement", "daily-living-skills", "professional-training",
    },
    "teen-years": {
        "puberty-body", "identity-self-esteem", "masking-burnout", "anxiety",
        "depression-mood", "friendship-peers", "bullying", "screen-time",
    },
    "adulthood": {
        "transition-planning", "daily-living-skills", "identity-self-esteem",
        "masking-burnout", "insurance-funding",
    },
}
# Age bands narrow the stages a resource can plausibly serve.
AGE_STAGE_GUARD = {
    "early":      {"suspecting", "assessment", "newly-diagnosed", "school-years"},
    "elementary": {"assessment", "newly-diagnosed", "school-years"},
    "teen":       {"school-years", "teen-years", "adulthood"},
    "adult":      {"teen-years", "adulthood"},
}

def derive_stages(rec):
    needs = set(rec.get("needs") or [])
    bands = set(rec.get("age_band") or [])
    stages = {s for s, keys in STAGE_RULES.items() if needs & keys}
    if bands and "all" not in bands:
        allowed = set()
        for b in bands:
            allowed |= AGE_STAGE_GUARD.get(b, set())
        if allowed:
            stages &= allowed
    return sorted(stages) or ["newly-diagnosed"]

def to_row(rec):
    year = rec.get("year")
    try:
        year = int(year) if year not in (None, "") else None
    except (TypeError, ValueError):
        year = None
    return {
        "slug":              rec["id"],
        "resource_type":     rec["type"],
        "also_types":        rec.get("also_types") or [],
        "title":             rec.get("title"),
        "creator":           rec.get("creator"),
        "publisher":         rec.get("publisher"),
        "year":              year,
        "isbn":              rec.get("isbn"),
        "url":               rec.get("url"),
        "secondary_url":     rec.get("secondary_url"),
        "needs":             rec.get("needs") or [],
        "audience":          rec.get("audience") or [],
        "age_band":          rec.get("age_band") or [],
        "stages":            derive_stages(rec),
        "stance":            rec.get("stance") or "unreviewed",
        "stance_note":       rec.get("stance_note"),
        "autistic_authored": bool(rec.get("autistic_authored")),
        "access":            rec.get("access"),
        "region":            rec.get("region"),
        "summary":           rec.get("summary"),
        "why_it_helps":      rec.get("why_it_helps"),
        "source_authority":  rec.get("source_authority"),
        "confidence":        rec.get("confidence"),
        "publish_status":    rec.get("publish_status"),
    }

def report(rows):
    print(f"\n{len(rows):,} records\n")
    def tally(label, values):
        print(f"  {label}")
        for k, n in Counter(values).most_common():
            print(f"    {k or '(none)':22s} {n:4d}")
        print()
    tally("stage (a resource can span several)", [s for r in rows for s in r["stages"]])
    tally("resource_type", [r["resource_type"] for r in rows])
    tally("stance",        [r["stance"] for r in rows])
    tally("access",        [r["access"] for r in rows])
    held = [r for r in rows if r["publish_status"]]
    print(f"  held from release: {len(held)}")
    for r in held:
        print(f"    {r['slug']} — {r['publish_status']}")
    print(f"\n  California entries: {sum(1 for r in rows if (r['region'] or '').startswith('CA'))}")
    print(f"  autistic-authored : {sum(1 for r in rows if r['autistic_authored'])}")
    print(f"  free              : {sum(1 for r in rows if r['access'] == 'free')}")

def check(key):
    """Confirm the table exists and report what is already in it."""
    from supabase import create_client
    client = create_client(SUPABASE_URL, key)
    try:
        res = client.table("autism_resources").select("slug", count="exact").limit(1).execute()
    except Exception as e:
        msg = str(e)
        if "does not exist" in msg or "PGRST205" in msg or "42P01" in msg:
            print("Table `autism_resources` does not exist yet.")
            print("Run data/sql/schema_autism_resources.sql in the Supabase SQL editor first.")
        else:
            print(f"Could not reach the table: {msg}")
        return False
    print(f"Table `autism_resources` exists. Rows currently in it: {res.count}")
    return True

def main():
    dry = "--dry-run" in sys.argv
    if not JSON_PATH.exists():
        sys.exit(f"Missing {JSON_PATH}")
    records = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    rows = [to_row(r) for r in records]

    slugs = Counter(r["slug"] for r in rows)
    dupes = [s for s, n in slugs.items() if n > 1]
    if dupes:
        sys.exit(f"Duplicate slugs, refusing to import: {dupes}")

    if "--check" in sys.argv:
        key = load_service_key()
        if not key:
            sys.exit("No SUPABASE_SERVICE_KEY found in the environment or in .env")
        sys.exit(0 if check(key) else 1)

    report(rows)
    if dry:
        print("\nDry run — nothing written.")
        return

    key = load_service_key()
    if not key:
        sys.exit("No SUPABASE_SERVICE_KEY found in the environment or in .env")
    if not check(key):
        sys.exit(1)

    from supabase import create_client
    client = create_client(SUPABASE_URL, key)
    imported = errors = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        try:
            client.table("autism_resources").upsert(batch, on_conflict="slug").execute()
            imported += len(batch)
            print(f"  Imported {imported:,}/{len(rows):,}...")
        except Exception as e:
            print(f"  Error at batch {i}: {e}")
            errors += 1
    print(f"\nDone. Imported {imported:,}, {errors} batch errors.")

if __name__ == "__main__":
    main()
