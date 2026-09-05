# agent_transcripts/

This directory is the real build record for The Lenny Growth Assistant,
reconstructed tier-by-tier from the actual coding-agent sessions that
produced this repo. Each file below covers one tier: what was asked for,
what was actually built, what was verified versus only reasoned about,
and any real corrections along the way.

Two sessions are worth reading in full rather than skimming, because they
were genuine failures corrected mid-project, not smoothed-over retellings:

- **`05_resilience.md`** — a tier where a completion was claimed and the
  session log described files as written, but a follow-up verification
  pass found the target files did not exist on disk. Nothing had actually
  been written; the tools reported success while no output was produced.
  Caught before the next tier built on top of it, and redone for real.
- **`06_evaluation.md`** — a tier that started from a stale/incomplete
  project snapshot missing an entire prior tier's output (the resilience
  tier's `errors.py`, `context.py`, `docs/resilience.md`, and four test
  files were all absent), meaning new work was briefly built on top of a
  base that had silently lost a prior tier's work. Caught via an explicit
  file-diff against the previous known-good export, not discovered during
  that same tier's own review pass, and redone from the correct base.

There is also a smaller, contained incident worth noting for completeness,
but it's a different and less significant kind of thing: `07_frontend_ux.md`
describes a leftover orphaned `SandboxedIframe.ts` file sitting unused
alongside the correct `.tsx` component, caught and deleted as routine
cleanup during that tier's own review pass — not a stale-base incident,
and not conflated with the one above.

Every other file describes uneventful tiers — built, verified, moved on —
which is also part of an honest record; not every tier has a story.

All secrets, API keys, and credentials referenced in these logs have been
scrubbed and replaced with placeholders. No transcript below contains a
usable key of any kind.