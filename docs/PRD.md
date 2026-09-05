# PRD.md — The Lenny Growth Assistant

## North Star
Give a growth PM a trustworthy, cited answer from Lenny's podcast archive in under 30 seconds — faster and more reliable than searching or listening themselves.

## Primary Persona & Job-to-be-Done
**Persona:** A growth/product PM (mid-to-senior) who has heard of relevant episodes but doesn't have time to scrub through hours of audio to find the specific tactic, framework, or quote they half-remember.

**Real JTBD:** "When I'm making a decision or writing something for my team, I want to pull a specific, attributable insight from someone who's actually done this — not a generic answer — so I can act on it or cite it without re-listening to a 90-minute episode."

This is not "I want a chatbot." It's closer to a research assistant with a fixed, trusted corpus. That framing drives most downstream decisions: grounding over fluency, abstention over guessing, citations as first-class UI, not footnotes.

## Success Metrics
1. **Citation/grounding accuracy ≥ 90%** on a fixed 25-question eval set with known expected source episodes.
2. **Abstention correctness ≥ 90%** on a held-out set of 8–10 deliberately out-of-domain questions.
3. **Time-to-first-token < 4s (local/Ollama), < 2s (cloud).**
4. **Artifact render safety: 0 XSS escapes** across a fixed adversarial test set of HTML artifact payloads.

Citation accuracy and abstention correctness are tracked as separate metrics because they fail in opposite directions (over-confident hallucination vs. over-cautious refusal); conflating them hides which failure mode the system actually has.

## Assumptions
1. Corpus size is small-to-medium (dozens to low hundreds of episodes); ingestion is a static, pre-downloaded transcript set, not live scraping.
2. Single-user / single-tenant evaluation context — no auth, no multi-user isolation.
3. Local LLM is the default demo path; cloud provider is a toggle, not the primary path.
4. Hardware for local inference is unconfirmed — defaults to `llama3.2:3b` as the safe P0 choice pending confirmation; quality trade-off vs. larger models documented explicitly.
5. "Sources" means episode + rough locator (title, guest, timestamp/section reference), not verified audio timestamps; UI handles a missing locator gracefully rather than fabricating one.
6. Ship 30 essay generation is explicit (user-triggered), not auto-detected from ordinary chat.
7. Artifact generation is explicit, same reasoning as #6.
8. No live transcript refresh pipeline — ingestion is a re-runnable script, not a scheduled job.
9. Single-machine evaluation deployment; deployment topology stays to single-host Docker Compose with a documented (not built) path to scale.

## Scope Table

| Tier | Item | Why |
|---|---|---|
| P0 | FastAPI backend, session + message persistence (Postgres) | Required, graded directly |
| P0 | Ingestion script: chunk → embed → store transcripts | Core of grounding |
| P0 | Retrieval (pgvector similarity search, top-K) with citation metadata | Core of grounding |
| P0 | Grounded chat with abstention logic | Directly graded metric |
| P0 | Provider abstraction (Ollama + one cloud provider), env-var toggle | Explicit requirement |
| P0 | Ship 30 skill as a distinct, structured tool | Explicit requirement |
| P0 | Artifact generation (Markdown + HTML) + sandboxed viewer | Explicit requirement, security-graded |
| P0 | Health endpoint (DB, Ollama, index status) | Explicit requirement |
| P0 | Docker Compose one-command startup, `.env.example` | Explicit requirement |
| P0 | Structured logging on retrieval/model/DB/artifact failures | Explicit requirement |
| P0 | Tests: retrieval, provider switching, abstention, ≥1 API integration test | Explicit requirement |
| P1 | Streaming token-by-token UI | Perceived latency, not correctness |
| P1 | Multi-turn follow-up context beyond naive history append | UX improvement |
| P1 | Provider badge in UI | Cheap, high trust value |
| P1 | Responsive tablet breakpoint polish | Nice, not core |
| P1 | Relevance-score display next to citations | Builds trust, low cost |
| P2 | HNSW/ANN index tuning, embedding cache invalidation | Irrelevant at assumed corpus size |
| P2 | Multi-user auth, per-user isolation | Out of scope per assumption #2 |
| P2 | Live transcript refresh/scraping pipeline | Out of scope per assumption #8 |
| P2 | Horizontal scaling / multi-host deployment | Out of scope per assumption #9 |
| Won't build | Real-time audio ingestion/transcription | No requirement for it |
| Won't build | Fine-tuning or model training | Retrieval + prompting covers the rubric |
| Won't build | Open-ended tool-calling agent framework | Two well-defined skills is the actual ask |
| Won't build | Full WYSIWYG artifact editor | Viewer, not editor, is what's asked for |

## Core User Journey
1. User opens app → new session auto-created or explicit "New Chat."
2. User submits a question.
3. System embeds query → retrieves top-K transcript chunks above similarity threshold — evidence gathered.
4. If evidence is thin/absent → explicit abstention, not a guess.
5. If sufficient → model synthesizes an answer with inline citations — insight delivered, sources visible.
6. User can follow up (session context preserved) or request transformation (Ship 30 essay / artifact).
7. Transformation runs against the same retrieved evidence, not a fresh ungrounded prompt — output rendered in the artifact pane.

## Key Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Hallucination when retrieval is weak/empty | Hard similarity threshold + explicit abstention instruction + out-of-domain test coverage |
| Local model (3B) reasoning weaker than cloud | Documented explicitly as an intentional trade-off; cloud toggle stays one line |
| Artifact HTML executes malicious script | `iframe sandbox="allow-scripts"` without `allow-same-origin`, plus DOMPurify as defense-in-depth |
| Ollama unavailable at demo time | Health check surfaces this clearly; structured error, not a silent hang |
| Chunking destroys context | Recursive chunking with overlap; chunk-level metadata carries episode/guest regardless of fragment content |
| Data leakage between sessions | Session ID scoping enforced at the query layer, tested explicitly |
| Cost/latency surprises from cloud provider | Documented in README, visible badge in UI (P1) |
| Ambiguous transcript source shape breaks ingestion | Ingestion built defensively — skip malformed files, log and continue |

## Acceptance Criteria (P0)
- **Ingestion:** populates `transcript_chunks` with non-null embeddings/metadata for ≥95% of source files; malformed files logged, not fatal.
- **Retrieval:** known in-domain questions return the expected source episode in ≥4/5 eval cases.
- **Abstention:** known out-of-domain questions produce an explicit "insufficient information" message in ≥9/10 eval cases.
- **Provider toggle:** changing `DEFAULT_LLM_PROVIDER` (or request header) changes which provider answers, with zero code changes.
- **Ship 30 skill:** produces a 1,100–1,400 word Markdown essay with H2/H3 headers, ≥1 bold-anchored bullet list, ≥1 attributed episode reference.
- **Artifact viewer:** an HTML artifact containing a script payload does not execute in the parent page context.
- **Sessions:** two concurrent sessions never see each other's history.
- **Health endpoint:** distinguishable status for DB down, Ollama unreachable, empty index — not one generic boolean.
- **Docker Compose:** `docker-compose up` on a clean checkout brings up all services and health reports healthy within a documented timeout.
