#!/usr/bin/env python3
"""
Import psychologytoday_ca_enriched.csv into Supabase therapists table.

Setup (if not installed):
  pip3 install supabase --break-system-packages

Usage:
  python3 import_therapists_to_supabase.py

Step 1: Run this SQL in Supabase dashboard > SQL Editor first:

CREATE TABLE IF NOT EXISTS therapists (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT,
  credentials TEXT,
  city TEXT,
  state TEXT DEFAULT 'CA',
  zip TEXT,
  phone TEXT,
  bio TEXT,
  profile_url TEXT UNIQUE,
  photo TEXT,
  online BOOLEAN DEFAULT FALSE,
  age_groups TEXT,
  source TEXT DEFAULT 'Psychology Today',
  fees TEXT,
  payment_methods TEXT,
  insurance TEXT,
  education TEXT,
  top_specialties TEXT,
  expertise TEXT,
  therapy_types TEXT,
  client_age TEXT,
  participants TEXT,
  communities TEXT,
  languages TEXT,
  endorsement_count INTEGER DEFAULT 0,
  endorsements TEXT,
  summary TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS (optional but recommended)
ALTER TABLE therapists ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read" ON therapists FOR SELECT USING (true);
"""

import csv, os, sys
from pathlib import Path

try:
    from supabase import create_client
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "supabase", "--break-system-packages", "-q"])
    from supabase import create_client

SUPABASE_URL = "https://nhdswigpkiwbgtxugtmw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5oZHN3aWdwa2l3Ymd0eHVndG13Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODIyNDk1MCwiZXhwIjoyMTAzODAwOTUwfQ.FHOAh0j76uJL6ODO3M7qB-WDwCwLfk49jTKhTjqle7w"

CSV_PATH = Path(__file__).parent / "psychologytoday_ca_enriched.csv"
BATCH_SIZE = 20


def clean(val, default=''):
    if val is None:
        return default
    return str(val).strip() or default


def clean_list_field(val):
    """Clean up fields like 'Children (6 to 10)\n, Preteen\n, Teen'"""
    return ', '.join(p.strip() for p in str(val).replace('\n', '').split(',') if p.strip())


def transform(row):
    return {
        'name': clean(row.get('name')),
        'credentials': clean(row.get('credentials')),
        'city': clean(row.get('city')),
        'state': clean(row.get('state'), 'CA'),
        'zip': clean(row.get('zip')),
        'phone': clean(row.get('phone')),
        'bio': clean(row.get('bio')),
        'profile_url': clean(row.get('profileUrl')),
        'photo': clean(row.get('photo')),
        'online': str(row.get('online', '')).lower() in ('true', '1', 'yes'),
        'age_groups': clean(row.get('age_groups')),
        'source': clean(row.get('source'), 'Psychology Today'),
        'fees': clean(row.get('fees')),
        'payment_methods': clean(row.get('paymentMethods')),
        'insurance': clean(row.get('insurance')),
        'education': clean(row.get('education')),
        'top_specialties': clean(row.get('topSpecialties')),
        'expertise': clean(row.get('expertise')),
        'therapy_types': clean(row.get('therapyTypes')),
        'client_age': clean_list_field(row.get('clientAge', '')),
        'participants': clean_list_field(row.get('participants', '')),
        'communities': clean_list_field(row.get('communities', '')),
        'languages': clean(row.get('languages')),
        'endorsement_count': int(row.get('endorsementCount') or 0),
        'endorsements': clean(row.get('endorsements')),
        'summary': clean(row.get('summary')),
    }


def main():
    print(f"Connecting to Supabase: {SUPABASE_URL}")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Verify table exists
    try:
        result = supabase.table('therapists').select('id').limit(1).execute()
        print(f"✅ therapists table found ({len(result.data)} existing rows)")
    except Exception as e:
        print(f"❌ therapists table not found. Please run the CREATE TABLE SQL in the Supabase dashboard first.")
        print(f"   Error: {e}")
        sys.exit(1)

    # Read CSV
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    print(f"📄 Loaded {len(rows)} therapists from CSV")

    # Transform
    records = [transform(r) for r in rows]

    # Insert in batches
    inserted = 0
    skipped = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        try:
            result = supabase.table('therapists').upsert(batch, on_conflict='profile_url').execute()
            inserted += len(batch)
            print(f"  ✅ Batch {i//BATCH_SIZE + 1}: inserted {len(batch)} ({inserted}/{len(records)} total)")
        except Exception as e:
            print(f"  ⚠️  Batch {i//BATCH_SIZE + 1} failed: {e}")
            # Try one by one
            for rec in batch:
                try:
                    supabase.table('therapists').upsert(rec, on_conflict='profile_url').execute()
                    inserted += 1
                except Exception as e2:
                    print(f"    ❌ Skipped {rec['name']}: {e2}")
                    skipped += 1

    print(f"\n🎉 Done! Inserted: {inserted}, Skipped: {skipped}")


if __name__ == '__main__':
    main()
