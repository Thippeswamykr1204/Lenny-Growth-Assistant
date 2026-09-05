# Tier 3 — Retrieval & Grounded Chat

**Ask:** wire retrieval into an actual chat endpoint — sessions, streaming
responses, confidence-gated grounding, dual provider support.

**What was actually built:**
- `backend/app/rag/retriever.py`: top-K pgvector cosine similarity search
  plus the three-way `classify` function (answer / qualified / abstain)
  against `SIMILARITY_THRESHOLD_HIGH` / `SIMILARITY_THRESHOLD_MODERATE`.
- `backend/app/skills/grounded_qa.py`: `run_grounded_qa` — the abstain
  path is a code-path short-circuit before any provider is called, not a
  hope that the model declines on its own.
- `backend/app/providers/{base,ollama_provider,anthropic_provider}.py`
  and `backend/app/providers/factory.py`: a shared async
  generate/stream interface, `get_provider()` selecting on
  `DEFAULT_LLM_PROVIDER` or a per-request override — no silent fallback
  between providers on failure, per the Tier 0 lock.
- `backend/app/api/sessions.py` (`POST /api/sessions`,
  `GET /api/sessions/{id}`) and `backend/app/api/chat.py`
  (`POST /api/chat/stream`, SSE: `status` → `source` (one per retrieved
  chunk) → `token`* → `done`).
- Session isolation enforced at the query level (`WHERE session_id = :id`
  on every message fetch) — this is the behavior
  `tests/test_sessions.py::test_session_isolation_no_cross_session_leakage`
  exists to guard.

**Verified:** manual `curl` walk of create-session → ask in-domain
question → confirm `source` events precede `token` events → ask
out-of-domain question → confirm no `source`/provider-call events at all
on the abstain path, only against a live DB with Tier 2's corpus
ingested. Provider switch verified both via `.env` and via a
per-request `"provider"` override, confirming `done.provider_used`
reflects whichever was actually used.

**Not eventful.** No corrections needed — this tier explicitly re-viewed
every new file after writing it, a practice adopted directly from the
Tier 2 incident.