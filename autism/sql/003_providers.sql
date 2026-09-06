-- ============================================================================
-- providers — the service layer, kept separate from autism_resources
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
-- ============================================================================

CREATE TABLE IF NOT EXISTS providers (
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

  -- ── autism relevance, from Regional Center vendor lists ─────────────────
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

ALTER TABLE providers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read shippable providers" ON providers;
CREATE POLICY "Public read shippable providers" ON providers
  FOR SELECT USING (publish_status IS NULL);

CREATE INDEX IF NOT EXISTS idx_prov_npi        ON providers (npi);
CREATE INDEX IF NOT EXISTS idx_prov_license    ON providers (license_no);
CREATE INDEX IF NOT EXISTS idx_prov_county     ON providers (county);
CREATE INDEX IF NOT EXISTS idx_prov_region     ON providers (region);
CREATE INDEX IF NOT EXISTS idx_prov_rc         ON providers (rc_vendor);
CREATE INDEX IF NOT EXISTS idx_prov_disciplines ON providers USING GIN (disciplines);
CREATE INDEX IF NOT EXISTS idx_prov_services   ON providers USING GIN (services);
CREATE INDEX IF NOT EXISTS idx_prov_languages  ON providers USING GIN (languages);
CREATE INDEX IF NOT EXISTS idx_prov_fts ON providers
  USING GIN (to_tsvector('english', coalesce(name,'') || ' ' || coalesce(organization,'') || ' ' || coalesce(city,'')));

CREATE OR REPLACE FUNCTION touch_providers() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_touch_providers ON providers;
CREATE TRIGGER trg_touch_providers BEFORE UPDATE ON providers
  FOR EACH ROW EXECUTE FUNCTION touch_providers();
