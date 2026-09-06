"""
Fetch Google Places ratings for therapists and update Supabase.

Before running, add two columns in Supabase SQL Editor:
  ALTER TABLE therapists
    ADD COLUMN IF NOT EXISTS google_rating NUMERIC(2,1),
    ADD COLUMN IF NOT EXISTS google_review_count INTEGER;

Then run:
  python3 enrich_google_ratings.py
"""

import json, time, urllib.request, urllib.parse, sys

SUPABASE_URL = "https://nhdswigpkiwbgtxugtmw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5oZHN3aWdwa2l3Ymd0eHVndG13Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgyMjQ5NTAsImV4cCI6MjEwMzgwMDk1MH0.MCKdc8uhnLVkc8tO8mtDm504zCYRp0azfcMj0a_yXIM"
GOOGLE_KEY   = "AIzaSyCvM3ry2_ZeX8Ui6VRF_3WCxuz2fc73srw"
SERVICE_KEY  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5oZHN3aWdwa2l3Ymd0eHVndG13Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODIyNDk1MCwiZXhwIjoyMTAzODAwOTUwfQ.FHOAh0j76uJL6ODO3M7qB-WDwCwLfk49jTKhTjqle7w"

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

# Service role key for writes (bypasses RLS)
SB_WRITE_HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

def sb_get(path):
    req = urllib.request.Request(f"{SUPABASE_URL}{path}", headers=SB_HEADERS)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def sb_patch(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}{path}", data=body, headers=SB_WRITE_HEADERS, method="PATCH")
    with urllib.request.urlopen(req) as r:
        return r.status

def google_search(name, city):
    """Text search for therapist, return (rating, review_count) or (None, None)."""
    q = urllib.parse.quote(f"{name} therapist {city} CA")
    url = (f"https://maps.googleapis.com/maps/api/place/textsearch/json"
           f"?query={q}&type=health&key={GOOGLE_KEY}")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read())
    results = data.get("results", [])
    if not results:
        return None, None
    top = results[0]
    return top.get("rating"), top.get("user_ratings_total")

def main():
    print("Fetching therapists from Supabase...")
    therapists = sb_get("/rest/v1/therapists?select=id,name,city&limit=500")
    print(f"  {len(therapists)} therapists found")

    updated = skipped = errors = 0
    for i, t in enumerate(therapists):
        tid  = t["id"]
        name = t.get("name", "")
        city = t.get("city", "")
        try:
            rating, review_count = google_search(name, city)
            if rating is not None:
                sb_patch(f"/rest/v1/therapists?id=eq.{tid}",
                         {"google_rating": rating, "google_review_count": review_count})
                print(f"  [{i+1}/{len(therapists)}] {name}: ⭐ {rating} ({review_count} reviews)")
                updated += 1
            else:
                print(f"  [{i+1}/{len(therapists)}] {name}: not found on Google")
                skipped += 1
        except Exception as e:
            print(f"  [{i+1}/{len(therapists)}] {name}: ERROR — {e}")
            errors += 1
        time.sleep(0.1)   # stay well within quota

    print(f"\nDone. Updated: {updated}  Skipped: {skipped}  Errors: {errors}")

if __name__ == "__main__":
    main()
