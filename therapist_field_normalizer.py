#!/usr/bin/env python3
"""Repair the two field-level defects in the enriched Psychology Today data.

1. Concatenated specialties. The scraper joins adjacent DOM text nodes with no
   separator, so a therapist's specialties arrive as one run-on string:

       "Top Specialties TransgenderLGBTQ+Autism"
       "Expertise ADHDAdoptionAnxietyAutismBehavioral Issues"

   218 of 287 enriched California rows look like this. The practical cost is
   that the field cannot be filtered on — only substring-matched — so there is
   no way to build a reliable "autism specialist" facet, which is exactly what
   an autism library needs from this table.

2. City casing. 122 of 287 rows carry a lowercase city ("los angeles",
   "palo alto"), so grouping or joining by city splits into two buckets.

Read-only by default:

    python3 therapist_field_normalizer.py            # report what would change
    python3 therapist_field_normalizer.py --write    # apply to Supabase

The service key comes from the environment or .env, never from this file.
"""
import json, os, re, sys
from pathlib import Path
from collections import Counter

SUPABASE_URL = "https://nhdswigpkiwbgtxugtmw.supabase.co"

# Vocabulary Psychology Today actually uses. Longest first so that
# "Autism" never eats the front of "Autism Spectrum Disorder".
KNOWN = sorted([
 "ADHD","Adoption","Alcohol Use","Anger Management","Antisocial Personality","Anxiety",
 "Asperger's Syndrome","Autism","Behavioral Issues","Bipolar Disorder","Body Image",
 "Borderline Personality","Career Counseling","Child","Chronic Illness","Chronic Impulsivity",
 "Chronic Pain","Chronic Relapse","Codependency","Coping Skills","Depression","Developmental Disorders",
 "Divorce","Domestic Abuse","Domestic Violence","Drug Abuse","Dual Diagnosis","Eating Disorders",
 "Education and Learning Disabilities","Emotional Disturbance","Emotional Regulation","Family Conflict",
 "Gambling","Grief","Hoarding","Impulse Control Disorders","Infertility","Infidelity",
 "Intellectual Disability","Internet Addiction","Learning Disabilities","LGBTQ+","Life Coaching",
 "Life Transitions","Marital and Premarital","Medication Management","Men's Issues","Obesity",
 "Obsessive-Compulsive (OCD)","Parenting","Peer Relationships","Pregnancy, Prenatal, Postpartum",
 "Racial Identity","Relationship Issues","School Issues","Self Esteem","Self-Harming","Sexual Abuse",
 "Sexual Addiction","Sleep or Insomnia","Spirituality","Sports Performance","Stress","Substance Use",
 "Suicidal Ideation","Teen Violence","Testing and Evaluation","Transgender","Trauma and PTSD",
 "Traumatic Brain Injury (TBI)","Video Game Addiction","Weight Loss","Women's Issues",
 # found by running this script against the live data and reading the leftovers
 "Mood Disorders","Addiction","Oppositional Defiance (ODD)","Bisexual","Lesbian","Gay",
 "Womens Issues","Personality Disorders","Polyamory & ENM","Neurodivergence",
 "Thinking Disorders","Psychosis","Autism Spectrum Disorder","Sex Therapy",
 "Somatic","Attachment Issues","Dissociative Disorders (DID)","Family of Origin",
 "First Responders","Military and Veterans","Open Relationships Non-Monogamy",
 "Sexual Concerns","Sexuality","Social Anxiety","Trichotillomania","Weight Management",
], key=len, reverse=True)

LABEL   = re.compile(r'^\s*(Top Specialties|Expertise|Issues)\s*', re.I)
# the same words reappear mid-string where PT starts a new section
SECTION = re.compile(r'\s*,?\s*(Top Specialties|Expertise)\s+(?=[A-Z])', re.I)

def split_specialties(raw):
    """Run-on string -> ordered list of recognized specialties.

    Unrecognized remainder is kept rather than dropped, so nothing silently
    disappears and the leftovers can be inspected and added to KNOWN.
    """
    if not raw: return [], ''
    s = SECTION.sub(', ', LABEL.sub('', str(raw))).strip(' ,')
    found, i = [], 0
    while i < len(s):
        for term in KNOWN:
            if s.startswith(term, i):
                found.append(term); i += len(term); break
        else:
            j = i + 1
            while j < len(s) and not any(s.startswith(t, j) for t in KNOWN): j += 1
            leftover = s[i:j].strip(' ,;')
            if leftover: found.append(leftover)
            i = j
    # de-dupe, keep order
    seen, out = set(), []
    for f in found:
        if f.lower() not in seen: seen.add(f.lower()); out.append(f)
    unknown = ', '.join(f for f in out if f not in KNOWN)
    return out, unknown

SMALL = {'of','the','and','de','la','del','on','in','at','by'}
def title_city(c):
    if not c: return c
    parts = str(c).strip().split()
    return ' '.join(p if p.isupper() and len(p) <= 3 else
                    (p.lower() if i and p.lower() in SMALL else p.capitalize())
                    for i, p in enumerate(parts))

def load_key():
    k = os.environ.get("SUPABASE_SERVICE_KEY")
    if k: return k.strip()
    p = Path(__file__).parent / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("SUPABASE_SERVICE_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None

def main():
    write = "--write" in sys.argv
    key = load_key()
    if not key: sys.exit("No SUPABASE_SERVICE_KEY in environment or .env")
    from supabase import create_client
    c = create_client(SUPABASE_URL, key)

    rows, page = [], 0
    while True:
        r = c.table("therapists").select(
            "id,city,top_specialties,expertise"
        ).not_.is_("top_specialties", "null").range(page*1000, page*1000+999).execute()
        rows += r.data
        if len(r.data) < 1000: break
        page += 1
    print(f"{len(rows)} enriched rows\n")

    updates, leftovers = [], Counter()
    city_fixed = spec_fixed = 0
    for row in rows:
        patch = {}
        city = title_city(row.get("city"))
        if city and city != row.get("city"):
            patch["city"] = city; city_fixed += 1
        for field in ("top_specialties", "expertise"):
            terms, unknown = split_specialties(row.get(field))
            if terms:
                joined = "; ".join(terms)
                if joined != (row.get(field) or ""):
                    patch[field] = joined; spec_fixed += 1
                for u in (unknown.split(", ") if unknown else []):
                    if u: leftovers[u] += 1
        if patch: updates.append((row["id"], patch))

    print(f"  city casing to fix     : {city_fixed}")
    print(f"  specialty fields to fix: {spec_fixed}")
    print(f"  rows to update         : {len(updates)}")
    if leftovers:
        print(f"\n  unrecognized fragments (add to KNOWN if they are real terms):")
        for t, n in leftovers.most_common(12): print(f"    {n:4d}  {t[:70]}")
    print("\n  sample:")
    for rid, patch in updates[:4]:
        for k, v in patch.items(): print(f"    {k}: {str(v)[:110]}")
        print()

    if not write:
        print("Read-only. Re-run with --write to apply."); return
    for i, (rid, patch) in enumerate(updates, 1):
        c.table("therapists").update(patch).eq("id", rid).execute()
        if i % 50 == 0 or i == len(updates): print(f"  updated {i}/{len(updates)}")
    print("Done.")

if __name__ == "__main__":
    main()
