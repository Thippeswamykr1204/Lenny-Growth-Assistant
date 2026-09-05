-- 002_artifact_security_fields.sql
--
-- Adds artifact security stamping fields, needed by Tier 4's artifact
-- generation skill: every artifact row must carry a content_hash
-- (integrity signal) and a security_status (pending/sanitized/blocked) so
-- a blocked/neutralized generation is a queryable, honest fact stored on
-- the row itself, never something inferred later at render time.
--
-- New migration file, not an edit to 001_init.sql, per the same
-- discipline: idempotent, IF NOT EXISTS / existence-checked additions,
-- safely re-runnable on every backend startup.

ALTER TABLE artifacts
    ADD COLUMN IF NOT EXISTS content_hash TEXT;

ALTER TABLE artifacts
    ADD COLUMN IF NOT EXISTS security_status TEXT NOT NULL DEFAULT 'pending';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'artifacts_security_status_check'
    ) THEN
        ALTER TABLE artifacts
            ADD CONSTRAINT artifacts_security_status_check
            CHECK (security_status IN ('pending', 'sanitized', 'blocked'));
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_artifacts_security_status ON artifacts(security_status);