# Tier 6 — Evaluation Harness

**Ask:** actually measure the two PRD-level success metrics — citation
accuracy and abstention correctness — that had been asserted since Tier 0
but never measured against real numbers.

## What actually happened

A session for this tier started from an outdated project snapshot that
was missing the entire resilience tier's output — `backend/app/core/
errors.py`, `backend/app/observability/context.py`, `docs/resilience.md`,
and all four resilience test files were absent from the working tree.
New evaluation-harness work was built for a time on top of this
incomplete base before the gap was noticed, meaning it was implicitly
building on top of a project state that had silently lost an entire
prior tier's work.

**Caught via an explicit file-diff against the previous known-good
export** — not discovered during this tier's own review pass — which
surfaced the missing resilience files by comparison rather than by
anything going visibly wrong in this tier's own output. The session was
restarted from the correct, complete base (with the resilience tier's
files present) and the evaluation-harness work below was redone against
it. This is a different, and more significant, incident than the
frontend tier's minor orphaned-file cleanup (`agent_transcripts/
07_frontend_ux.md`) — that one was a single leftover unused file caught
and deleted within its own tier, not a case of missing prior-tier output.

**What was actually built:**
- `evaluation/datasets/grounded_qa_eval.json`: 25 in-domain questions,
  each mapped to a real episode title/guest pulled directly from the
  actually-ingested Tier 2 corpus (not invented), plus 9 out-of-domain
  trivia questions with zero legitimate answer in a product/growth
  podcast archive.
- `evaluation/run_eval.py`: imports and calls the real
  `app.rag.retriever.retrieve` and `app.skills.grounded_qa.run_grounded_qa`
  directly — it does not reimplement retrieval or classification logic,
  so a passing eval run is evidence about the real code path, not a
  parallel simulation of it. Measures citation accuracy (expected episode
  present among retrieved sources), abstention correctness (out-of-domain
  question correctly triggers `abstain`, plus confirmation the provider
  was never called for that question), and p50/p95 latency. CLI:
  `--provider {ollama,anthropic}`, defaulting to
  `settings.default_llm_provider`.
- `evaluation/tests/test_scoring.py`: 12 tests against synthetic inputs,
  covering the scoring/classification logic itself independent of any
  live system.

**Verified:** the eval dataset's 25 in-domain questions checked against
`backend/scripts/download_transcripts.py`'s `SELECTED_SLUGS` and each
transcript's own YAML frontmatter — episode titles copied verbatim, not
fabricated. `test_scoring.py` run and passing.

**What was not verified, honestly:** `run_eval.py` itself has not been
run end-to-end in any session this project was built in — no session had
a live Postgres with the corpus ingested and a reachable
Ollama/Anthropic provider at the same time. The harness exists and is
wired correctly, but no real citation-accuracy/abstention-correctness/
latency numbers exist yet as of this tier. Carried forward honestly into
`docs/architecture.md` and the Tier 8 handoff rather than papered over —
see `07_frontend_ux.md`'s successor, the Tier 8 handoff notes, for where
this status ends up stated plainly for an evaluator.