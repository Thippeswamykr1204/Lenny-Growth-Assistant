-- 001_init.sql
--
-- Decision: raw, idempotent SQL over Alembic for this tier.
-- Reasoning (one sentence, per instructions): at foundation stage there is
-- exactly one schema state to reach (the four P0 tables from
-- architecture.md) and no history of prior versions to migrate between,
-- so Alembic's versioning machinery adds ceremony without benefit yet;
-- this script is re-run automatically on every backend startup (see
-- app/db/migrate.py) and is written to be safely re-runnable. If the
-- schema starts evolving across tiers with real prior state to preserve,
-- Alembic becomes the right call then — not now.
--
-- Idempotency approach: IF NOT EXISTS everywhere it's supported; DO
-- blocks with existence checks where Postgres doesn't support IF NOT
-- EXISTS directly (enum types).

CREATE EXTENSION IF NOT EXISTS vector;

-- role enum for messages.role
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'message_role') THEN
        CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system');
    END IF;
END$$;

-- artifact_type enum for artifacts.artifact_type
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'artifact_type') THEN
        CREATE TYPE artifact_type AS ENUM ('markdown', 'html');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role message_role NOT NULL,
    content TEXT NOT NULL,
    sources JSONB,
    provider_used TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);

-- Embedding dimension: 384, matching sentence-transformers/all-MiniLM-L6-v2
-- per the reference doc's suggested embedding model (architecture.md
-- references this as the default; not consumed by any logic in Tier 1).
-- If Tier 2 picks a different embedding model with a different dimension,
-- this column definition changes then — flagged here so it isn't a
-- silent assumption.
CREATE TABLE IF NOT EXISTS transcript_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_title TEXT NOT NULL,
    guest_name TEXT,
    chunk_text TEXT NOT NULL,
    locator TEXT,
    embedding VECTOR(384),
    source_file TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Flat index only (locked Tier 0 decision: no HNSW yet). No index created
-- here beyond the implicit table scan — pgvector similarity search on a
-- small corpus does not need an ANN index at this tier, and adding one
-- now would contradict the locked "flat index for P0" decision.

CREATE TABLE IF NOT EXISTS artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    artifact_type artifact_type NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_artifacts_message_id ON artifacts(message_id);
