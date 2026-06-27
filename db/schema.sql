CREATE TABLE IF NOT EXISTS system_registry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  system_name TEXT NOT NULL UNIQUE,
  railway_url TEXT,
  health_endpoint TEXT,
  last_sha TEXT,
  version TEXT,
  tags TEXT[],
  status TEXT DEFAULT 'unknown',
  last_heartbeat TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
