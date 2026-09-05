# Tier 0 — Discovery & Scaffolding

**Ask:** turn the client brief (build "The Lenny Growth Assistant") into the
three discovery documents required before any code — `docs/PRD.md`,
`docs/architecture.md`, `docs/design.md` — plus lock the repo layout so
every later tier has a stable place to put things.

**What was actually built:**
- `docs/PRD.md`: persona (growth PM who needs a specific, attributable
  tactic without re-listening to a 90-minute episode), the two measurable
  success metrics later tiers would be graded against (citation accuracy,
  abstention correctness), 9 numbered assumptions where the client brief
  was silent (hardware for local inference, no multi-user auth, no live
  transcript refresh pipeline, single-host deployment, etc.), and an
  explicit out-of-scope table.
- `docs/architecture.md`: DB schema for `sessions` / `messages` /
  `artifacts`, the retrieval/confidence-gating design (top-K similarity
  search, three-way answer/qualified/abstain classification against two
  configurable thresholds), the provider abstraction shape
  (`LLMProviderInterface`, env-var default + per-request override, no
  silent fallback between providers), and the artifact security model
  (sandboxed iframe as the primary control).
- `docs/design.md`: the two-pane chat/artifact layout, the interaction
  state machine later implemented in Tier 7, and the three responsive
  breakpoints.
- Repo scaffold: `backend/app/{core,db,providers,rag,skills,api,domain,
  observability,artifacts}`, `frontend/src/{app,components,hooks,lib}`,
  `evaluation/`, `agent_transcripts/`, `docker-compose.yml`,
  `.env.example`.

**Decisions locked here that later tiers were held to:** provider routing
via `DEFAULT_LLM_PROVIDER` (never model-decided, never silent fallback on
failure), confidence gating as app-computed thresholds rather than
model self-reported confidence, and the iframe sandbox as the artifact
security model's primary control rather than sanitization alone.

**Verified:** all three docs reviewed against the brief's required
sections (deliverables #3/#4/#5 in the assignment); no code existed yet
to verify against.

**Not eventful.** No corrections needed this tier — the discovery
documents were the deliverable, and were internally consistent on first
pass.