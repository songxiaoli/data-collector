-- ============================================================================
-- autism_providers — the service layer, kept separate from autism_resources
--
-- autism_resources is the library: editorial, slow-changing, shared by everyone,
-- and it holds books and videos that have no address. This table is the
-- opposite kind of object — place-bound, fast-changing, and maintained by
-- phone calls rather than by reading. Putting them in one table would mean
-- giving a 1993 book an "accepting new clients" column.
--
-- Identity comes from public bulk records rather than from a scraped directory:
--   NPI          CMS NPPES monthly file — federal, public domain
--   license      California DCA licensee files — public record by statute
-- Autism relevance comes from Regional Center vendor lists, which are public
-- because they record public spending.
-- Operational facts (accepting clients, wait, languages) can only come from the
-- provider's own site or a phone call, so they start NULL and stay NULL until
-- someone actually confirms them. A stale "accepts Medi-Cal: yes" is worse than
-- an empty column: it sends a family to waste a phone call.
--
-- The name is autism_providers, not providers. The same Supabase project also
-- holds `therapists`, which belongs to the SEL finder and is maintained by a
-- different pipeline on a different schedule. Nothing here reads or writes that
-- table except --crosscheck, which only counts. Two libraries, two tables, no
-- shared rows — the same split the repo now has between autism/ and the SEL
-- scripts.
-- ============================================================================

CREATE TABLE IF NOT EXISTS autism_providers (
  id              BIGSERIAL PRIMARY KEY,
  slug            TEXT NOT NULL UNIQUE,

  -- ── identity, from bulk public records ──────────────────────────────────
  npi             TEXT,                      -- CMS; also the best dedup key
  npi_type        TEXT CHECK (npi_type IN ('individual','organization')),
  license_no      TEXT,
  license_board   TEXT,                      -- e.g. 'Board of Psychology', 'SLPAB'
  license_status  TEXT,                      -- Current / Delinquent / Inactive / …
  license_expires DATE,

  name            TEXT NOT NULL,
  credentials     TEXT,
  organization    TEXT,                      -- employer or practice, when known

  -- ── where ───────────────────────────────────────────────────────────────
  address         TEXT,
  city            TEXT,
  county          TEXT,
  state           TEXT DEFAULT 'CA',
  zip             TEXT,
  region          TEXT,                      -- US-CA-<area>, same vocabulary as the library
  phone           TEXT,
  website         TEXT,

  -- ── what ────────────────────────────────────────────────────────────────
  taxonomies      TEXT[] DEFAULT '{}',       -- NUCC codes from NPPES
  disciplines     TEXT[] DEFAULT '{}',       -- our own plain words: slp, ot, psych, bcba, dev-peds
  services        TEXT[] DEFAULT '{}',       -- diagnostic, speech, ot, behavioural, parent-training…
  age_band        TEXT[] DEFAULT '{}',

  -- ── autism relevance ────────────────────────────────────────────────────
  -- relevance_tier says how we know this provider is relevant at all:
  --   1  the NUCC taxonomy itself names developmental disability, autism or
  --      early intervention — dev-behavioural paeds, I/DD psychology, early
  --      intervention agencies, DD clinics, respite, behaviour analysis
  --   2  a discipline families are routinely referred to for autism (SLP, OT,
  --      child psychiatry, neuropsych, audiology, AAC) where the taxonomy says
  --      nothing about autism. Listed, and labelled as exactly that
  --   3  general mental health and general clinics. Carried so a regional
  --      centre match can promote them, but held from publication until then
  -- Tier is relevance only. Whether a practice is community-contested is the
  -- stance flag's job, not this column's: most of tier 1 is behaviour analysis,
  -- which is both unambiguously autism-directed and unambiguously disputed.
  relevance_tier  SMALLINT CHECK (relevance_tier BETWEEN 1 AND 3),
  rc_vendor       BOOLEAN DEFAULT FALSE,
  rc_names        TEXT[] DEFAULT '{}',       -- which regional centres vendor them
  rc_vendor_no    TEXT,

  -- ── operational: NULL until a human confirms it ─────────────────────────
  languages           JSONB,                 -- [{"lang":"zh-Hans","level":"clinician"}]
  accepting_new       BOOLEAN,
  wait_weeks          INT,
  medi_cal            BOOLEAN,
  insurance_plans     TEXT[],
  telehealth          BOOLEAN,
  in_home             BOOLEAN,
  diagnosis_required  BOOLEAN,

  -- ── provenance: every operational claim needs one ───────────────────────
  verified_date   DATE,                      -- when a human last confirmed the row
  verified_by     TEXT,
  listing_status  TEXT NOT NULL DEFAULT 'listed'
                  CHECK (listing_status IN ('listed','claimed','verified')),
  claimed_by      TEXT,
  claimed_at      TIMESTAMPTZ,
  sources         JSONB DEFAULT '[]'::jsonb, -- [{"field","value","source","captured_at"}]
  confidence      TEXT CHECK (confidence IN ('high','medium','low')),
  publish_status  TEXT,                      -- NULL = shippable, same gate as the library

  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE autism_providers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read shippable autism providers" ON autism_providers;
CREATE POLICY "Public read shippable autism providers" ON autism_providers
  FOR SELECT USING (publish_status IS NULL);

CREATE INDEX IF NOT EXISTS idx_autism_prov_tier    ON autism_providers (relevance_tier);
CREATE INDEX IF NOT EXISTS idx_autism_prov_npi        ON autism_providers (npi);
CREATE INDEX IF NOT EXISTS idx_autism_prov_license    ON autism_providers (license_no);
CREATE INDEX IF NOT EXISTS idx_autism_prov_county     ON autism_providers (county);
CREATE INDEX IF NOT EXISTS idx_autism_prov_region     ON autism_providers (region);
CREATE INDEX IF NOT EXISTS idx_autism_prov_rc         ON autism_providers (rc_vendor);
CREATE INDEX IF NOT EXISTS idx_autism_prov_disciplines ON autism_providers USING GIN (disciplines);
CREATE INDEX IF NOT EXISTS idx_autism_prov_services   ON autism_providers USING GIN (services);
CREATE INDEX IF NOT EXISTS idx_autism_prov_languages  ON autism_providers USING GIN (languages);
CREATE INDEX IF NOT EXISTS idx_autism_prov_fts ON autism_providers
  USING GIN (to_tsvector('english', coalesce(name,'') || ' ' || coalesce(organization,'') || ' ' || coalesce(city,'')));

CREATE OR REPLACE FUNCTION touch_autism_providers() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_touch_autism_providers ON autism_providers;
CREATE TRIGGER trg_touch_autism_providers BEFORE UPDATE ON autism_providers
  FOR EACH ROW EXECUTE FUNCTION touch_autism_providers();
