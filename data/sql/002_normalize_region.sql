-- ============================================================================
-- 002 — normalize the `region` vocabulary
--
-- The imported data carries three spellings of the United States (us / usa /
-- US), two of the UK and two of Australia, and — the dangerous one — a
-- lowercase 'ca' meaning CANADA sitting next to 'CA' meaning CALIFORNIA.
--
--   region = 'ca'  -> ACT (Autism Community Training), British Columbia
--   region = 'CA'  -> California, 41 rows
--
-- Any case-insensitive California filter (ilike 'CA%') pulls the Canadian
-- organization into California results. This migration removes the collision
-- by moving California onto the US-<state> convention already used elsewhere
-- in the table (US-MD, US-GA, US-TX, US-WA, US-MA, US-TN).
--
-- Run once, in the Supabase SQL editor. Idempotent.
-- ============================================================================

BEGIN;

-- California: CA -> US-CA, CA-<area> -> US-CA-<area>
UPDATE autism_resources SET region = 'US-CA'
  WHERE region = 'CA';
UPDATE autism_resources SET region = 'US-CA-' || substring(region from 4)
  WHERE region LIKE 'CA-%';

-- Countries, one spelling each
UPDATE autism_resources SET region = 'US'     WHERE region IN ('us','usa','USA');
UPDATE autism_resources SET region = 'UK'     WHERE region IN ('uk');
UPDATE autism_resources SET region = 'AU'     WHERE region IN ('au');
UPDATE autism_resources SET region = 'CANADA' WHERE region IN ('ca','canada','Canada');
UPDATE autism_resources SET region = 'EU'     WHERE region IN ('europe','Europe');
UPDATE autism_resources SET region = 'GLOBAL' WHERE region IN ('global','Global');

COMMIT;

-- Verify: expect US-CA (41), US-CA-* (60), US, GLOBAL, UK, AU, CANADA, …
--   SELECT region, count(*) FROM autism_resources GROUP BY region ORDER BY 2 DESC;
