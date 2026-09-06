-- ============================================================================
-- 002 — lock the `region` vocabulary
--
-- The first import carried three spellings of the United States (us / usa /
-- US), two of the UK and two of Australia, and — the dangerous one — a
-- lowercase 'ca' meaning CANADA sitting beside 'CA' meaning CALIFORNIA:
--
--     region = 'ca'  ->  ACT (Autism Community Training), British Columbia
--     region = 'CA'  ->  California
--
-- Any prefix or case-insensitive California filter pulled the Canadian
-- organization into California results. The data has since been rewritten so
-- California uses the US-<state> convention this table already used elsewhere
-- (US-MD, US-GA, US-TX), which makes `region LIKE 'US-CA%'` safe: no other
-- value can begin with those characters.
--
--     US-CA                California, statewide
--     US-CA-<area>         US-CA-LA, US-CA-Bay Area, US-CA-Central Valley, …
--     US, US-<state>       national, or another state
--     UK AU CANADA EU IE NZ IN
--     GLOBAL               not tied to a place
--
-- This migration only adds the guard. Run it in the Supabase SQL editor.
-- ============================================================================

-- Fail loudly if any legacy value survived, rather than adding a constraint
-- that silently permits them.
DO $$
DECLARE bad int;
BEGIN
  SELECT count(*) INTO bad FROM autism_resources
   WHERE region IS NOT NULL
     AND region NOT IN ('US','UK','AU','CANADA','EU','IE','NZ','IN','GLOBAL')
     AND region !~ '^US-[A-Z]{2}(-.+)?$';
  IF bad > 0 THEN
    RAISE EXCEPTION 'orphaned region values still present: % rows — re-run the importer first', bad;
  END IF;
END $$;

ALTER TABLE autism_resources DROP CONSTRAINT IF EXISTS autism_resources_region_vocab;
ALTER TABLE autism_resources ADD CONSTRAINT autism_resources_region_vocab
  CHECK (
    region IS NULL
    OR region IN ('US','UK','AU','CANADA','EU','IE','NZ','IN','GLOBAL')
    OR region ~ '^US-[A-Z]{2}(-.+)?$'
  );

-- SELECT region, count(*) FROM autism_resources GROUP BY region ORDER BY 2 DESC;
