#!/usr/bin/env python3
"""Import psychologytoday_ca_560.csv (basic scrape) into Supabase therapists table."""

import csv, sys
from pathlib import Path

try:
    from supabase import create_client
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "supabase", "--break-system-packages", "-q"])
    from supabase import create_client

SUPABASE_URL = "https://nhdswigpkiwbgtxugtmw.supabase.co"
SERVICE_KEY  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5oZHN3aWdwa2l3Ymd0eHVndG13Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODIyNDk1MCwiZXhwIjoyMTAzODAwOTUwfQ.FHOAh0j76uJL6ODO3M7qB-WDwCwLfk49jTKhTjqle7w"

CSV_PATH = Path(__file__).parent / "psychologytoday_ca_560.csv"
BATCH_SIZE = 50

def main():
    supabase = create_client(SUPABASE_URL, SERVICE_KEY)

    # Check table
    result = supabase.table('therapists').select('id', count='exact').execute()
    print(f"✅ therapists table: {result.count} existing rows")

    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    print(f"📄 Loaded {len(rows)} rows from CSV")

    records = []
    for r in rows:
        url = (r.get('url') or '').strip()
        name = (r.get('name') or '').strip()
        if not url or not name:
            continue
        records.append({
            'name': name,
            'credentials': (r.get('credentials') or '').strip(),
            'city': (r.get('city') or '').strip(),
            'state': (r.get('state') or 'CA').strip(),
            'zip': (r.get('zip') or '').strip(),
            'fees': (r.get('fee') or '').strip(),
            'online': str(r.get('online', '')).lower() in ('true', '1', 'yes'),
            'profile_url': url,
            'source': 'Psychology Today',
        })

    print(f"📋 Importing {len(records)} valid records...")
    inserted = skipped = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        try:
            supabase.table('therapists').upsert(batch, on_conflict='profile_url').execute()
            inserted += len(batch)
            print(f"  ✅ Batch {i//BATCH_SIZE+1}: {inserted}/{len(records)}")
        except Exception as e:
            print(f"  ⚠️  Batch failed: {e}")
            for rec in batch:
                try:
                    supabase.table('therapists').upsert(rec, on_conflict='profile_url').execute()
                    inserted += 1
                except Exception as e2:
                    print(f"    ❌ Skipped {rec['name']}: {e2}")
                    skipped += 1

    print(f"\n🎉 Done! Inserted/updated: {inserted}, Skipped: {skipped}")

if __name__ == '__main__':
    main()
