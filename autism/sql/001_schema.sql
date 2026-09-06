-- ============================================================================
-- autism_resources — the /autism library
-- Run in the Supabase SQL editor. Safe to re-run.
--
-- Sibling to `videos` / `books` / `therapists`, deliberately NOT merged with
-- them: the SEL finder matches on one axis (what the child is going through),
-- this one matches on two (need AND where the family is in the process).
-- ============================================================================

CREATE TABLE IF NOT EXISTS autism_resources (
  id            BIGSERIAL PRIMARY KEY,
  slug          TEXT NOT NULL UNIQUE,      -- e.g. 'book-uniquely-human'; the upsert key
  resource_type TEXT NOT NULL,             -- book|printable|tool|video|creator|provider|
                                           -- organization|course|event|community|app
  also_types    TEXT[] DEFAULT '{}',       -- when one record serves as two (org + community)

  title         TEXT NOT NULL,
  creator       TEXT,
  publisher     TEXT,
  year          INT,
  isbn          TEXT,

  url           TEXT,
  secondary_url TEXT,

  -- matching axis 1: what you are dealing with
  needs         TEXT[] DEFAULT '{}',
  audience      TEXT[] DEFAULT '{}',       -- parent|educator|clinician|autistic
  age_band      TEXT[] DEFAULT '{}',       -- early|elementary|teen|adult|all

  -- matching axis 2: where you are in the process
  stages        TEXT[] DEFAULT '{}',       -- suspecting|assessment|newly-diagnosed|
                                           -- school-years|teen-years|adulthood

  -- editorial layer: the credibility apparatus
  stance        TEXT NOT NULL DEFAULT 'unreviewed'
                CHECK (stance IN ('affirming','neutral','contested','portrayal-debated','unreviewed')),
  stance_note   TEXT,                      -- names WHO makes the criticism, never our verdict
  autistic_authored BOOLEAN DEFAULT FALSE,

  access        TEXT CHECK (access IN ('free','freemium','paid','subscription','insurance','varies')),
  region        TEXT,                      -- 'global' | 'US' | 'CA' | 'CA-LA' | ...

  summary       TEXT,
  why_it_helps  TEXT,
  source_authority TEXT,                   -- where we found it recommended
  confidence    TEXT CHECK (confidence IN ('high','medium','low')),

  -- withheld from release pending a check we could not perform ourselves
  publish_status TEXT,                     -- NULL = shippable | 'hold-needs-human'

  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── Row level security ──────────────────────────────────────────────────────
ALTER TABLE autism_resources ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read shippable autism resources" ON autism_resources;
CREATE POLICY "Public read shippable autism resources" ON autism_resources
  FOR SELECT USING (publish_status IS NULL);
-- Anything on hold stays invisible to the anon key until a human clears it.

-- ── Indexes ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_ar_needs     ON autism_resources USING GIN (needs);
CREATE INDEX IF NOT EXISTS idx_ar_stages    ON autism_resources USING GIN (stages);
CREATE INDEX IF NOT EXISTS idx_ar_audience  ON autism_resources USING GIN (audience);
CREATE INDEX IF NOT EXISTS idx_ar_age_band  ON autism_resources USING GIN (age_band);
CREATE INDEX IF NOT EXISTS idx_ar_type      ON autism_resources (resource_type);
CREATE INDEX IF NOT EXISTS idx_ar_stance    ON autism_resources (stance);
CREATE INDEX IF NOT EXISTS idx_ar_region    ON autism_resources (region);
CREATE INDEX IF NOT EXISTS idx_ar_access    ON autism_resources (access);

-- Free-text search across the fields a parent actually types against.
CREATE INDEX IF NOT EXISTS idx_ar_fts ON autism_resources
  USING GIN (to_tsvector('english',
    coalesce(title,'') || ' ' || coalesce(creator,'') || ' ' ||
    coalesce(summary,'') || ' ' || coalesce(why_it_helps,'')));

-- ── updated_at ──────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION touch_autism_resources() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_touch_autism_resources ON autism_resources;
CREATE TRIGGER trg_touch_autism_resources
  BEFORE UPDATE ON autism_resources
  FOR EACH ROW EXECUTE FUNCTION touch_autism_resources();
