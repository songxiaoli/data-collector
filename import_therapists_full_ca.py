#!/usr/bin/env python3
"""
Import full CA therapists CSV into Supabase therapists table.
Run from Mac Terminal: python3 import_therapists_full_ca.py
"""
import csv, sys
from pathlib import Path
from supabase import create_client

SUPABASE_URL = "https://nhdswigpkiwbgtxugtmw.supabase.co"
SERVICE_KEY  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5oZHN3aWdwa2l3Ymd0eHVndG13Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODIyNDk1MCwiZXhwIjoyMTAzODAwOTUwfQ.FHOAh0j76uJL6ODO3M7qB-WDwCwLfk49jTKhTjqle7w"
CSV_PATH = Path(__file__).parent / "psychologytoday_ca_full.csv"
BATCH_SIZE = 50

def main():
    client = create_client(SUPABASE_URL, SERVICE_KEY)

    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} rows from CSV")

    # Deduplicate by profile URL
    seen = set()
    unique_rows = []
    for row in rows:
        url = row.get('url', '').strip()
        if url and url not in seen:
            seen.add(url)
            unique_rows.append(row)

    print(f"After dedup: {len(unique_rows)} unique therapists")

    imported = 0
    errors = 0

    for i in range(0, len(unique_rows), BATCH_SIZE):
        batch = unique_rows[i:i+BATCH_SIZE]
        records = []
        for row in batch:
            records.append({
                'name': row.get('name', '').strip(),
                'credentials': row.get('credentials', '').strip(),
                'city': row.get('city', '').strip(),
                'state': row.get('state', 'CA').strip(),
                'zip': row.get('zip', '').strip(),
                'fees': row.get('fee', '').strip(),
                'online': row.get('online', 'no').strip(),
                'profile_url': row.get('url', '').strip(),
                'source': 'psychology_today',
            })

        try:
            result = client.table('therapists').upsert(
                records,
                on_conflict='profile_url'
            ).execute()
            imported += len(batch)
            if imported % 500 == 0 or imported == len(unique_rows):
                print(f"Imported {imported}/{len(unique_rows)}...")
        except Exception as e:
            print(f"Error at batch {i}: {e}")
            errors += 1

    print(f"\nDone! Imported {imported} therapists, {errors} errors")

if __name__ == '__main__':
    main()
