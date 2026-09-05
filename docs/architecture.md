# architecture.md — The Lenny Growth Assistant

## System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js, TS)                                          │
│  ┌───────────────────────┐   ┌────────────────────────────────┐ │
│  │ Chat Pane              │   │ Artifact Viewer (collapsible)   │ │
│  │ - session selector      │   │ - Markdown renderer             │ │
│  │ - message stream         │   │ - Sandboxed iframe (HTML)      │ │
│  │ - provider badge         │   │                                 │ │
│  └──────────┬──────────────┘   └────────────────────────────────┘ │
└─────────────┼──────────────────────────────────────────────────┘
              │ REST + SSE (streaming)
┌─────────────▼──────────────────────────────────────────────────┐
│  Backend (FastAPI)                                                │
│  ┌───────────────┐ ┌──────────────┐ ┌────────────────────────┐  │
│  │ API layer       │ │ Skills layer  │ │ Provider abstraction    │  │
│  │ /sessions       │ │ - QA skill    │ │ LLMProviderInterface     │  │
│  │ /chat           │ │ - Ship30 skill│ │  ├─ OllamaProvider       │  │
│  │ /health         │ │ - Artifact    │ │  └─ CloudProvider (Claude)│  │
│  │                 │ │   skill       │ │                          │  │
│  └───────┬─────────┘ └──────┬───────┘ └───────────┬──────────────┘  │
│          │                  │                     │                  │
│  ┌───────▼──────────────────▼─────────────────────▼──────────────┐ │
│  │ Retrieval layer: embed query → pgvector similarity search       │ │
│  │ → confidence gate (answer / qualified / abstain)                │ │
│  └───────────────────────────┬───────────────────────────────────┘ │
└──────────────────────────────┼──────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────┐
│  PostgreSQL + pgvector                                            │
│  sessions | messages | transcript_chunks (+embedding) | artifacts │
└─────────────────────────────────────────────────────────────────┘

┌────────────────────┐     (offline / re-runnable, not live)
│ Ingestion script     │──► parses transcript files → chunk → embed → insert
└────────────────────┘
```


## Database Schema (P0)

**sessions**
- `id` (UUID, PK)
- `title` (text, nullable)
- `created_at`, `updated_at` (timestamptz)

**messages**
- `id` (UUID, PK)
- `session_id` (FK → sessions, indexed)
- `role` (enum: user/assistant/system)
- `content` (text)
- `sources` (JSONB — array of `{episode, guest, locator, score}`; nullable)
- `provider_used` (text, nullable — column exists from day one so P1 doesn't require a migration)
- `created_at` (timestamptz)

**transcript_chunks**
- `id` (UUID, PK)
- `episode_title` (text)
- `guest_name` (text, nullable)
- `chunk_text` (text)
- `locator` (text — timestamp or section heading; nullable, UI handles null gracefully)
- `embedding` (vector, pgvector type)
- `source_file` (text — traceability back to raw ingest input)
- `created_at` (timestamptz)

**artifacts**
- `id` (UUID, PK)
- `message_id` (FK → messages)
- `artifact_type` (enum: markdown/html)
- `content` (text)
- `created_at` (timestamptz)

## Retrieval Design
- **Chunking:** recursive character/paragraph splitting, target 500–800 tokens, ~100-token overlap.
- **Indexing:** pgvector with cosine similarity, flat index for P0 (HNSW deferred — corpus size doesn't justify it yet).
- **Grounding/confidence decision logic:**
  - Retrieve top-K (K=5 default, configurable).
  - **Answer directly** if top similarity ≥ high threshold (e.g. 0.75) and ≥2 chunks clear a moderate threshold (e.g. 0.65).
  - **Qualified answer** if only 1 chunk clears the moderate threshold, or scores are borderline.
  - **Abstain** if no chunk clears the moderate threshold.
  - Thresholds are configurable constants (`SIMILARITY_THRESHOLD_HIGH=0.75`, `SIMILARITY_THRESHOLD_MODERATE=0.65` in `.env.example`/`config.py`), not hardcoded in `retriever.py`.
  - **Current status (as of the Tier 8 handoff pass): still the original Tier 0 best-guess defaults, never empirically tuned.** The Tier 6 evaluation harness (`evaluation/run_eval.py`) exists and is fully wired to the real retrieval/grounded-QA code paths, but has not been run end-to-end in any environment this project was built in — no session has had a live Postgres with the corpus ingested and a reachable Ollama/Anthropic provider at the same time. Changing these two numbers without a real eval run to justify the change would be an unjustified guess dressed up as a tuned value, so they are left at the defaults. Run `evaluation/run_eval.py` against a real ingested DB to get the first real numbers; only adjust the thresholds from those.

## Agent/Skill Boundaries
- **QA skill:** deterministic retrieval (app logic) → model only synthesizes the answer from provided chunks and applies citation formatting. Confidence gating is app logic, not model self-report.
- **Ship 30 skill:** takes the same retrieved evidence (not a fresh retrieval) plus a structured prompt template encoding the framework (hook, short paragraphs, bold anchors, actionable close).
- **Artifact skill:** decides format based on explicit user request, not a free-roaming per-turn decision.
- Retrieval, thresholding, and format routing are app logic (testable, deterministic); synthesis and prose quality are the model's job.

## Provider Abstraction
- Single `LLMProviderInterface` (async generate/stream methods).
- **Routing:** `DEFAULT_LLM_PROVIDER` env var at startup, overridable per-request via an explicit `provider` field — never inferred, never auto-fallback on failure (surface the failure instead).

## Artifact Security Model
- **Trusted:** chat pane (plain text/Markdown via `react-markdown`, no raw HTML injection).
- **Sandboxed:** any HTML/CSS artifact, rendered in an `iframe` with `sandbox="allow-scripts"` and **no** `allow-same-origin` — the single most important control, preventing a malicious artifact from reading parent cookies/localStorage or making authenticated requests as the app.
- **Defense in depth:** as built, sanitization happens server-side, not client-side — `bleach` (an allow-list HTML sanitizer) runs in `artifact_generator.py` at generation time, before the row is ever persisted, stripping disallowed tags/attributes and flagging the row `blocked` if it caught something dangerous. The original plan below this line described a client-side DOMPurify pass instead; that was superseded during Tier 4 in favor of sanitizing once, server-side, before persistence — the iframe sandbox (above) remains the primary control either way. No DOMPurify dependency exists in the frontend.
- **Explicitly blocked:** `allow-same-origin`, `allow-top-navigation`, `allow-popups`, form submission outside the sandbox.
- **Explicitly permitted:** script execution inside the isolated iframe context only, for genuinely interactive artifacts.

## Resilience
Full failure-mode matrix (Ollama/cloud/DB down, retrieval empty, LLM
timeout, malformed output, oversized/empty prompt, missing config at
startup) with implemented behavior and exact code paths: see
[`resilience.md`](./resilience.md) — kept as its own file rather than a
section here since it's edited independently of architectural decisions
and is the doc most likely to get grepped mid-incident.

## Decisions
1. **Flat similarity index over HNSW for P0.** Simplest thing that works, with a documented upgrade path.
2. **Confidence gating as app-computed thresholds, not model self-assessment.** Computed similarity scores are testable; model confidence self-reports are miscalibrated.
3. **`llama3.2:3b` as default local model.** Smallest model likely to run everywhere; quality trade-off documented, pending hardware confirmation.
4. **No automatic cloud fallback if local model fails.** Surface the failure explicitly; let the user manually toggle, so the "which model answered" UI claim stays true.
5. **Explicit, user-triggered skill invocation for Ship 30 and artifacts.** Simpler and more predictable than intent classification on every message.
6. **No auth/multi-tenancy.** Sessions stay anonymous; schema doesn't block adding a `user_id` column later without a rewrite.

## How This Evolves Toward Production Scale
- **Retrieval:** swap flat index for HNSW once corpus size or query volume justifies it — index-only change.
- **Ingestion:** one-shot script → scheduled job/webhook once there's a live feed; chunk/embed/insert logic unchanged.
- **Auth:** add `user_id` to `sessions`, gate API routes behind auth middleware; existing `session_id` scoping doesn't change shape.
- **Deployment:** Compose single-host today → provider/retrieval/API layers are stateless enough to move behind a load balancer with the DB as the only stateful piece.
- **Observability:** structured JSON logs today → ship to a real aggregator without changing logging calls, only the sink.