# Tier 1 — Foundation

**Ask:** prove the project boots cleanly end to end before any product
feature exists — every Compose service up, every service able to reach
every other service, no ingestion/retrieval/chat/skills yet.

**What was actually built:**
- `docker-compose.yml`: `db` (pgvector/pgvector:pg16, host port 5433 to
  avoid colliding with a local Postgres install, healthcheck via
  `pg_isready`), `backend`, `frontend`, and an optional `ollama` service
  gated behind a `local-ai` Compose profile (a locked Tier 0 decision —
  Ollama is a toggle, not a forced dependency for every environment).
- `backend/app/core/config.py`: a single `pydantic-settings` `Settings`
  class as the one place every env var is declared, instead of `os.getenv()`
  scattered through the codebase.
- `backend/app/db/migrate.py` + `migrations/001_init.sql`: idempotent
  startup migration creating `sessions`, `messages`, `transcript_chunks`
  (with the `vector(384)` column and `pgvector` extension), and
  `artifacts`.
- `backend/app/api/health.py`: `/api/health` reporting `database` and
  `transcript_chunks` status (the latter `"ok"`-but-empty pre-ingestion),
  plus an `ollama` field that reads `"not_configured"` unless
  `LOCAL_AI_ENABLED=true`.
- `frontend/src/app/page.tsx`: a minimal page that fetches and displays
  `/api/health`, proving frontend → backend connectivity — no chat UI at
  this tier.

**Verified:** `docker compose up` brought up `db`/`backend`/`frontend`,
`curl localhost:8000/api/health` returned `200` with the expected shape,
`docker compose --profile local-ai up` brought up `ollama` additionally,
and restarting the backend twice confirmed the migration is safe to
re-run.

**Not eventful.** README was written and marked explicitly
`Status: foundation tier (Tier 1) only` at this point — the label that,
by Tier 8, needed removing since it had been stale since Tier 2.