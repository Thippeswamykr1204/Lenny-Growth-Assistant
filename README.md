# The Lenny Growth Assistant

A full-stack, grounded RAG assistant over Lenny's Podcast transcripts —
FastAPI + Postgres/pgvector backend, Next.js frontend, dual local/cloud
LLM providers, a Ship 30 for 30 writing skill, and a sandboxed artifact
viewer. Built as a Forward Deployed Engineer take-home; this README is
the handoff document for someone with zero prior context.

## Architecture, briefly

Chat request → retrieval (pgvector cosine similarity over transcript
chunks) → app-computed confidence gating (answer / qualified / abstain,
never model self-reported) → provider call (Ollama or Anthropic, never
silently swapped) → response streamed over SSE, with citations as
first-class evidence, not an afterthought. Ship 30 essays and Markdown/HTML
artifacts reuse the same retrieved evidence rather than re-retrieving.
HTML artifacts are sanitized server-side before persistence and rendered
in a sandboxed iframe with no origin access to the parent app.

Full depth — DB schema, API contracts, component boundaries, security
model, deployment topology — is in [`docs/architecture.md`](docs/architecture.md).
Product framing (persona, success metrics, assumptions, scope) is in
[`docs/PRD.md`](docs/PRD.md). UI/UX principles and interaction states are
in [`docs/design.md`](docs/design.md).

## Prerequisites

- **Docker & Docker Compose v24+** — this is the supported path; no local
  Python/Node install is required to run via Compose.
- For running outside Docker (backend/frontend dev servers, tests, the
  eval harness, or the ingestion scripts) instead: **Python 3.11+**,
  **Node 18.x or 20.x LTS**.
- **Ollama** (native install, not the optional Compose service) if you
  want to run the required local-model demo path outside Compose — see
  "Local model setup" below.

## Installation

```bash
git clone <this-repo-url> lenny-growth-assistant
cd lenny-growth-assistant
cp .env.example .env          # defaults are safe for local dev as-is
docker compose up             # db + backend + frontend
```

Then, in a second terminal, populate the knowledge base (one-time, or
whenever you want to refresh it):

```bash
docker compose exec backend python -m scripts.download_transcripts
docker compose exec backend python -m scripts.ingest
```

Verify it worked:

```bash
curl http://localhost:8000/api/health
```
Expect `200` with `database.status: "ok"` and
`transcript_chunks.status: "ok"` with a non-zero `row_count` once
ingestion has run. Open `http://localhost:3000` for the chat UI.

This is the exact sequence run against a clean checkout to write this
section — see the Tier 8 verification report at the bottom of this file
for what was actually re-run versus reasoned about.

## Environment variables

Every variable below is read somewhere in the codebase — this table is
kept in sync with `backend/app/core/config.py` by grepping the codebase
for every settings/env read and cross-checking against `.env.example`
each time this file changes. Full annotated defaults live in
[`.env.example`](.env.example); this table is the quick-reference.

| Variable | Required? | What it does | Default |
|---|---|---|---|
| `APP_ENV` | optional | `development` \| `production` | `development` |
| `LOG_LEVEL` | optional | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR` | `INFO` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | required | Compose `db` service credentials | `lenny` / `changeme_local_only` / `lenny_assistant` |
| `DATABASE_URL` | required | Async SQLAlchemy connection string; must use the `db` Docker hostname, not `localhost`, under Compose | matches the three above |
| `DB_HOST_PORT` | optional | Host-side port for the `db` container (avoids colliding with a local Postgres) | `5433` |
| `DEFAULT_LLM_PROVIDER` | required | `ollama` \| `anthropic`; per-request override via the chat payload | `ollama` |
| `OLLAMA_BASE_URL` | required if using Ollama | Ollama's API base URL | `http://ollama:11434` |
| `OLLAMA_MODEL` | required if using Ollama | Model tag to pull and use | `llama3.2:3b` |
| `LOCAL_AI_ENABLED` | optional | Whether `/api/health` probes Ollama | `false` |
| `ANTHROPIC_API_KEY` | required only if `DEFAULT_LLM_PROVIDER=anthropic` | Cloud provider auth; startup fails fast if missing and required | *(blank)* |
| `ANTHROPIC_MODEL` | optional | Anthropic model id | `claude-3-5-sonnet-20241022` |
| `EMBEDDING_MODEL` | optional | Sentence-transformers model for chunk/query embedding | `sentence-transformers/all-MiniLM-L6-v2` |
| `EMBEDDING_DIM` | optional | Must match the model output and the `vector(384)` DB column | `384` |
| `CHUNK_TARGET_TOKENS` / `CHUNK_OVERLAP_TOKENS` | optional | Transcript chunking parameters | `650` / `100` |
| `TRANSCRIPTS_SOURCE_REPO` | optional | Upstream transcript repo the download script pulls from | ChatPRD's transcripts repo |
| `TRANSCRIPTS_DIR` | optional | Local directory transcripts are downloaded to / ingested from | `data/transcripts` |
| `RETRIEVAL_TOP_K` | optional | Chunks retrieved per query | `5` |
| `SIMILARITY_THRESHOLD_HIGH` / `SIMILARITY_THRESHOLD_MODERATE` | optional | Confidence-gating thresholds — **still the original best-guess defaults, never empirically tuned; see "Evaluation" below** | `0.75` / `0.65` |
| `SHIP30_MIN_WORDS` / `SHIP30_MAX_WORDS` | optional | Ship 30 essay word-count validator bounds | `1100` / `1400` |
| `PROVIDER_TIMEOUT_SECONDS` | optional | Fallback timeout both providers inherit | `30` |
| `OLLAMA_TIMEOUT_SECONDS` / `ANTHROPIC_TIMEOUT_SECONDS` | optional | Per-provider timeout override | *(inherit fallback)* |
| `DB_POOL_TIMEOUT_SECONDS` | optional | Seconds to wait for a free DB connection before a typed failure | `5` |
| `MAX_PROMPT_CHARS` | optional | Max chat message length, validated pre-retrieval | `8000` |
| `NEXT_PUBLIC_API_URL` | required | Browser-facing backend URL (not the Docker hostname — read client-side) | `http://localhost:8000` |

## Local model setup (Ollama)

Required for the demo path. Two ways to run it:

**A. Native Ollama on your host** (recommended for actual local-model
quality/speed):
```bash
ollama pull llama3.2:3b
ollama serve            # if not already running as a service
```
Then in `.env`, set `OLLAMA_BASE_URL=http://host.docker.internal:11434`
(backend runs in Docker, Ollama runs on the host).

**B. Ollama as a Compose service** (self-contained, no native install):
```bash
docker compose --profile local-ai up
docker compose exec ollama ollama pull llama3.2:3b
```
Set `LOCAL_AI_ENABLED=true` in `.env` first so `/api/health` actually
probes it (`OLLAMA_BASE_URL=http://ollama:11434`, the Compose default,
already matches this path).

## Cloud model setup (Anthropic)

```bash
# in .env
DEFAULT_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```
Restart the backend. If `DEFAULT_LLM_PROVIDER=anthropic` and the key is
blank, the backend refuses to start (a `CRITICAL` log line, not a
confusing runtime failure on your first message) — see "Resilience &
troubleshooting" below.

## Run commands

**Docker Compose (full stack):**
```bash
docker compose up                       # db + backend + frontend
docker compose --profile local-ai up    # + local Ollama service
```

**Dev mode, outside Docker:**
```bash
# backend only
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://lenny:changeme_local_only@localhost:5433/lenny_assistant
uvicorn app.main:app --reload --port 8000

# frontend only
cd frontend
npm install
npm run dev
```

**Ingestion** (either mode — see full walkthrough in
[`docs/architecture.md`](docs/architecture.md) for what each step does):
```bash
cd backend
python -m scripts.download_transcripts        # or: python scripts/download_transcripts.py
python scripts/download_transcripts.py --force # re-download everything
python scripts/ingest.py
```

## How to run tests

**Backend (pytest):**
```bash
cd backend
pip install -r requirements.txt
pytest
```
Unit tests need no DB or LLM. Integration tests
(`test_sessions.py`, `test_retrieval.py`, `test_artifact_persistence.py`,
`test_health_resilience.py`) need a live Postgres at `DATABASE_URL` with
migrations applied — they self-skip with a clear message if the DB isn't
reachable. **As of this handoff pass: 61 passed, 9 skipped** (no live DB
in the environment this pass ran in) — see the verification report below
for the exact command and a real bug this dry-run found and fixed in the
skip logic itself.

**Frontend (vitest):**
```bash
cd frontend
npm install
npm test
```
Covers `chatTurnReducer`'s state transitions and the citation
expand/collapse interaction. **18 passed** as of this handoff pass.

**Evaluation harness** (measures the PRD's citation-accuracy and
abstention-correctness success metrics against the real retrieval/QA code
paths — not a unit test, needs a live DB with the corpus ingested and,
for the `ollama` run, a running Ollama with `OLLAMA_MODEL` pulled):
```bash
cd backend
python ../evaluation/run_eval.py                     # uses DEFAULT_LLM_PROVIDER
python ../evaluation/run_eval.py --provider ollama    # explicit override
python ../evaluation/run_eval.py --provider anthropic
```
The harness's own scoring logic has an independent unit suite:
```bash
cd evaluation && pytest tests/test_scoring.py
```

## Resilience & troubleshooting

Full failure-mode-by-failure-mode table lives in
[`docs/resilience.md`](docs/resilience.md). The six most likely first-run
issues, so a stuck evaluator doesn't have to go hunting:

1. **`port is already allocated` for 5432 on `docker compose up`.**
   Something on your machine (often a local Postgres.app/Homebrew
   install on macOS) already owns host port 5432. `db` binds to host
   port `5433` by default for exactly this reason. If 5433 is *also*
   taken, set `DB_HOST_PORT` in `.env`. `DATABASE_URL` is unaffected
   either way — it talks to the `db` service over the Docker network.
2. **`db` never becomes healthy.** Check `docker compose logs db` —
   usually a `POSTGRES_PASSWORD`/`POSTGRES_USER` mismatch against a
   previous run's volume. `docker compose down -v` resets the volume if
   you changed credentials.
3. **Backend can't reach the database.** Confirm `DATABASE_URL` uses the
   Compose hostname `db`, not `localhost`.
4. **`/api/health` shows `ollama: unreachable` when you don't want Ollama
   at all.** Confirm `LOCAL_AI_ENABLED=false` (or unset) — it should read
   `not_configured` in that case, not attempt a connection.
5. **Backend won't start at all, `CRITICAL` log about configuration.**
   `DEFAULT_LLM_PROVIDER=anthropic` with a blank `ANTHROPIC_API_KEY` — this
   is intentional fail-fast behavior, not a bug. Set the key or switch to
   `ollama`.
6. **Integration tests fail with a raw connection error instead of
   skipping.** Fixed as part of this handoff pass (see the verification
   report) — if you're on an older commit, the fix is: broaden the
   `_db_reachable()` exception catch in the four `tests/test_*.py`
   integration files beyond `OperationalError` to also catch
   `ConnectionRefusedError`/`OSError`, which is what a fully-absent DB
   (nothing listening on the port at all) actually raises.

**Reading structured logs:** every log line is one JSON object on stdout.
`docker compose logs backend`, filter by shared `request_id` to follow
one request end-to-end. Key fields: `provider`,
`retrieval_classification` (`answer`/`qualified`/`abstain`),
`retrieval_latency_ms`/`generation_latency_ms`, `prompt_tokens`/
`completion_tokens` (present when the provider SDK exposes them),
`level: "ERROR"`/`"CRITICAL"` with a server-side-only `exception` field.

## Manual UI test plan

A concrete click-through checklist lives in
[`docs/manual-test-plan.md`](docs/manual-test-plan.md) (kept separate
from this README since it's a working checklist someone follows live,
not reference documentation). Covers: create session → in-domain question
→ citations expand → out-of-domain question → abstention renders
distinctly → Ship30 essay → HTML artifact renders sandboxed with a
visible security status → each responsive breakpoint → full keyboard
navigation.

## Evaluation status

PRD.md's two top-line success metrics — citation accuracy ≥90% and
abstention correctness ≥90% — are measured by `evaluation/run_eval.py`
(Tier 6), which imports and calls the real retrieval/grounded-QA code
directly rather than reimplementing the logic. **Honest current status:
the harness has never been run end-to-end against a live DB + reachable
provider in this project's build history**, so no real numbers exist yet,
and `SIMILARITY_THRESHOLD_HIGH`/`SIMILARITY_THRESHOLD_MODERATE` remain
the original Tier 0 best-guess defaults (`0.75`/`0.65`) — changing them
without real eval numbers to justify the change would be an unjustified
guess dressed up as a tuned value. Run the command in "How to run tests"
above against your own ingested corpus to get the first real numbers, and
only adjust the thresholds from those. Full detail in
[`docs/architecture.md`](docs/architecture.md)'s Retrieval Design section.

## What's NOT built, and why

Pulled directly from `docs/PRD.md`'s explicit out-of-scope table — this
is a maturity signal about what was deliberately deferred, not an
oversight:

- **Multi-user auth / per-user isolation** — out of scope per PRD
  assumption #2; sessions are anonymous and client-tracked, matching the
  brief's take-home scope.
- **Live transcript refresh/scraping pipeline** — out of scope per PRD
  assumption #8; ingestion is an explicit, re-runnable script, not a
  background job watching for new episodes.
- **Horizontal scaling / multi-host deployment** — out of scope per PRD
  assumption #9; the architecture's stateless layers are designed to move
  behind a load balancer later (see `docs/architecture.md`'s "Future"
  notes), but that move isn't built.
- **HNSW vector index** — pgvector uses a flat index for now; corpus size
  (30 episodes) doesn't yet justify the index-only swap to HNSW.
- **Empirically-tuned confidence thresholds** — see "Evaluation status"
  above.

## Tier 8 verification report (this handoff pass)

What was actually re-run in this environment versus only reasoned about
statically, for anyone auditing this handoff:

- **Fresh-install dry run:** `pip install -r backend/requirements.txt`
  and `npm install` (frontend) both run for real in this pass and
  succeeded. `docker compose up` itself was **not** executed in this
  sandbox (no Docker daemon available here) — the Compose file, health
  endpoint contract, and service wiring were reviewed statically instead;
  this is the one step in "Installation" above not re-verified live in
  this specific pass, and is called out rather than silently assumed.
- **`.env.example` completeness:** grepped the entire `backend/` tree for
  every `Settings`-class field and every ad-hoc `os.getenv`/`os.environ`
  read, and the frontend for every `process.env` read, then diffed
  against `.env.example`'s variable list. Found 12 variables added in
  Tiers 2–4 (`EMBEDDING_MODEL`, `EMBEDDING_DIM`, `CHUNK_TARGET_TOKENS`,
  `CHUNK_OVERLAP_TOKENS`, `TRANSCRIPTS_SOURCE_REPO`, `TRANSCRIPTS_DIR`,
  `RETRIEVAL_TOP_K`, `SIMILARITY_THRESHOLD_HIGH`,
  `SIMILARITY_THRESHOLD_MODERATE`, `ANTHROPIC_MODEL`, `SHIP30_MIN_WORDS`,
  `SHIP30_MAX_WORDS`) that were read by the app but missing from
  `.env.example` — added them (this pass, see `.env.example`'s diff).
- **Backend test suite:** `DATABASE_URL=<dummy> pytest -q` from a clean
  install. First run: **9 hard failures**, not skips — a real bug, not a
  doc gap. `_db_reachable()` in the four integration test files
  (`test_sessions.py`, `test_retrieval.py`, `test_artifact_persistence.py`,
  `test_health_resilience.py`) only caught `sqlalchemy.exc.OperationalError`,
  but a fully-absent DB (nothing listening on the port) actually raises a
  bare `ConnectionRefusedError`/`OSError` that SQLAlchemy hadn't wrapped
  yet at that point in the connection lifecycle. Fixed by broadening the
  catch in all four files. Re-ran: **61 passed, 9 skipped, 0 failed.**
- **Frontend test suite:** `npm install && npm test` — this sandbox has
  working network egress to the npm registry (unlike the sandbox Tier 7
  was originally built in, where it did not — see
  `agent_transcripts/07_frontend_ux.md`). **18 passed, 0 failed.** This
  resolves Tier 7's previously-unverified status for real.
- **Ingestion script CLI:** `backend/scripts/ingest.py` takes no CLI
  arguments (reads config from env only) — README's bare
  `python scripts/ingest.py` matches. `download_transcripts.py`'s
  `argparse` setup (`--force`, no other flags) matches what README
  documents.
- **Eval harness CLI:** `evaluation/run_eval.py`'s `argparse` setup
  (`--provider {ollama,anthropic}`, default `None` → falls through to
  `settings.default_llm_provider`) matches what README documents exactly.
- **Secrets audit:** grepped the entire repository (not just
  `docker-compose.yml`/`.env.example`) for `sk-`, `api_key`, `password`,
  `secret`, `token`-shaped strings. Found only test fixtures using
  obviously-fake values (`sk-ant-fake` in
  `backend/tests/test_config_validation.py`) — no real secrets anywhere.
  `.gitignore` confirmed to exclude `.env`, `__pycache__/`,
  `.pytest_cache/`, `node_modules/`, `.next/`, and the Postgres data
  volume directory (`postgres_data/`), plus `ollama_data/` and
  `evaluation/reports/*.json` (real retrieved transcript text/API
  responses, never committed verbatim).
- **`docs/architecture.md` drift check:** found and corrected one real
  drift — the doc described client-side DOMPurify sanitization as a
  "defense in depth" layer, but the actual Tier 4 implementation moved
  sanitization server-side (`bleach`, in `artifact_generator.py`, before
  persistence) and never added a DOMPurify dependency to the frontend.
  Corrected in place; see that file's Artifact Security Model section.
- **Confidence-gating threshold status:** confirmed via `git blame`-equivalent
  reasoning across the agent transcripts and this pass's own attempt to
  run `evaluation/run_eval.py` (no live DB/provider available in this
  sandbox either) that the thresholds have never been tuned against real
  numbers. Stated plainly in `docs/architecture.md` and this README's
  "Evaluation status" section rather than left ambiguous.
- **`agent_transcripts/`:** assembled from the real tier-by-tier build
  history, including the two genuine incidents (Tier 2's claimed-but-
  unwritten ingestion scripts, Tier 7's stale-duplicate `SandboxedIframe.ts`)
  rather than a sanitized retelling. Final grep pass across the whole
  repo (not just this directory) for key-shaped strings before finishing,
  same pass as the secrets audit above.

Nothing broken was found in the *product* code paths this pass — the one
real bug (`_db_reachable()`'s exception handling) was in the test suite's
own skip logic, not in application behavior, and is now fixed.