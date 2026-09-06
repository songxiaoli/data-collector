-- Create resources table for groups, workshops, courses
-- Run this in Supabase SQL editor

CREATE TABLE IF NOT EXISTS resources (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  resource_type TEXT NOT NULL DEFAULT 'group',  -- 'group', 'workshop', 'course'
  category TEXT,                                  -- 'parenting', 'adhd', 'autism', etc.
  description TEXT,
  credentials TEXT,
  city TEXT,
  state TEXT DEFAULT 'CA',
  zip TEXT,
  online TEXT DEFAULT 'no',
  profile_url TEXT UNIQUE,
  source TEXT DEFAULT 'psychology_today',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE resources ENABLE ROW LEVEL SECURITY;

-- Allow public read
CREATE POLICY "Allow public read" ON resources
  FOR SELECT USING (true);

-- Index for performance
CREATE INDEX IF NOT EXISTS idx_resources_category ON resources(category);
CREATE INDEX IF NOT EXISTS idx_resources_city ON resources(city);
CREATE INDEX IF NOT EXISTS idx_resources_resource_type ON resources(resource_type);
CREATE INDEX IF NOT EXISTS idx_resources_state ON resources(state);
