-- ============================================================
-- SafarSmart — Full Supabase Schema
-- Run this entire script in: Supabase Dashboard → SQL Editor
-- ============================================================


-- ── 1. USERS TABLE ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION _update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION _update_updated_at();


-- ── 2. FEEDBACK TABLE ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS feedback (
    id         TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    type       TEXT NOT NULL DEFAULT 'app'
                   CHECK(type IN ('app','itinerary','fare_calculator')),
    rating     INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    category   TEXT,
    comment    TEXT,
    tags       JSONB,
    user_name  TEXT,
    user_email TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_type       ON feedback(type);
CREATE INDEX IF NOT EXISTS idx_feedback_rating     ON feedback(rating);


-- ── 3. ROW LEVEL SECURITY ────────────────────────────────────
-- Allow backend (anon key) to read/write all rows.
-- In production, tighten these policies.

ALTER TABLE users    ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;

-- users: only service/backend can access (anon can insert/select via API key)
DROP POLICY IF EXISTS "allow_all_users"    ON users;
CREATE POLICY "allow_all_users"    ON users    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "allow_all_feedback" ON feedback;
CREATE POLICY "allow_all_feedback" ON feedback FOR ALL USING (true) WITH CHECK (true);


-- ── 4. VERIFY ────────────────────────────────────────────────
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('users', 'feedback');
