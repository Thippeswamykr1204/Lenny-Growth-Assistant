# domain/

Deferred to Tier 2+. Will hold domain models / business logic for
sessions, messages, and transcript chunks that isn't pure DB schema
(app/db) or pure API contract (app/api) — e.g. the confidence-gating
logic described in architecture.md (answer / qualified / abstain).

Empty in Tier 1 by design: no retrieval or chat logic exists yet.
