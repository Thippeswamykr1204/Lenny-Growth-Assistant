# Tier 5 — Resilience

**Ask:** handle missing keys, unavailable Ollama, model timeouts, empty
retrieval, and DB connection failures gracefully — no hangs, no bare
tracebacks reaching the client.

## What actually happened

The first pass of this tier is the incident this repo's build record is
supposed to be honest about, not hide.

**The session log described a completed tier:** `backend/app/core/
errors.py` and `backend/app/observability/context.py` were reported
written, the failure-mode matrix in `docs/resilience.md` was reported
authored against them, and the session's own summary claimed the typed
error path had been wired through the provider layer and exercised.

**A follow-up verification pass — re-viewing the files that were supposedly
written, the same discipline this project's handoff pass applies
everywhere — found neither `errors.py` nor `context.py` existed on disk.**
The tool calls that were supposed to create them had not actually landed;
the session's narrative text described work that the file-write step
never completed, and `docs/resilience.md`'s matrix had been drafted
against typed-error behavior that no code in the repo actually
implemented yet. Nothing in Tier 6 had been built on top of it yet, so
the blast radius was contained to this tier alone.

**Correction:** the tier was redone from scratch in a second session,
this time re-viewing each file immediately after writing it (the same
practice applied throughout every later tier) before reporting anything
as complete.

## What was actually built (second attempt, verified)

- `backend/app/providers/*`: every provider call wrapped so a timeout,
  connection refusal, or unexpected exception yields exactly one typed
  error chunk into the SSE stream rather than raising out of the
  streaming generator — `tests/test_provider_resilience.py` simulates
  all three against `OllamaProvider` directly.
- `backend/app/core/config.py`: startup fail-fast — if
  `DEFAULT_LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` is blank, the
  process logs a `CRITICAL` line and exits instead of booting and failing
  confusingly on the first chat message; `ollama` as default never
  requires the key (a regression this tier explicitly guards against in
  `test_config_validation.py`).
- `backend/app/api/health.py`: a `configuration` field distinct from
  dependency status — `"misconfigured"` (bad config) is a different
  `overall` state from `"degraded"` (a dependency that's just temporarily
  down), so an evaluator isn't left guessing which kind of broken they're
  looking at.
- `backend/app/observability/logging.py`: structured JSON logs, one
  object per line, with `request_id`/`session_id` correlation,
  `provider`, `retrieval_classification`, split
  `retrieval_latency_ms`/`generation_latency_ms`, and
  `prompt_tokens`/`completion_tokens` when the provider SDK exposes them
  (present rather than guessed when it doesn't).
- Provider timeout behavior: tokens already streamed before a timeout
  stay visible in the chat pane but are not persisted as a completed
  turn — documented explicitly in `docs/resilience.md` rather than left
  as an undocumented surprise.

**Verified this time, for real:** `errors.py` and `context.py` re-viewed
on disk after writing; full failure-mode matrix in `docs/resilience.md`
cross-checked against `test_provider_resilience.py`,
`test_config_validation.py`, and `test_health_resilience.py` — each row
in the matrix has a corresponding test, not just a design-doc claim.