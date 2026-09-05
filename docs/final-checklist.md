# Final Pre-Submission Checklist

Covers the assignment brief's Section 6 deliverable table. Each row's
status was actually checked in this session against the repo as it
exists on disk right now — nothing below is marked verified on the
strength of an earlier tier's claim alone.

| # | Deliverable | Status | Notes |
|---|---|---|---|
| 1 | Public GitHub repository | **Not yet done** | This working tree is not currently a git repository (`git status` fails with "not a git repository"). Before submission: `git init`, commit, push to a public repo, and re-run the secrets grep (below) against the actual git history, not just the working tree — a secret that was committed and later removed can still exist in history. |
| 2 | `README.md` | **Verified** | Present, 371 lines, covers architecture overview, prerequisites, installation, environment variables, local (Ollama) and cloud (Anthropic) model setup, run commands, how to run tests, resilience/troubleshooting, manual UI test plan, evaluation status, what's-not-built, and a Tier 8 verification report. Read in full this session. |
| 3 | PRD (`docs/PRD.md`) | **Verified** | Present, 92 lines. Contains north star, persona/JTBD, success metrics, assumptions, scope table (P0/P1/P2/Won't build), user journey, risks/mitigations, and P0 acceptance criteria. Read in full this session. |
| 4 | `design.md` | **Verified** | Present, 49 lines. Covers UI principles, information architecture, interaction states (confident/qualified/abstained), responsive breakpoints, and accessibility. Read in full this session. |
| 5 | `architecture.md` | **Verified** | Present, 124 lines. Covers DB schema, API endpoints, agent/skill boundaries, provider abstraction, artifact security model, resilience (pointer to `docs/resilience.md`), and the six numbered Decisions. Confidence-gating status re-confirmed this session (see below) — still honestly stated as un-tuned defaults, not drifted toward sounding more finished. |
| 6 | Agent transcripts | **Verified, and corrected this session** | `agent_transcripts/README.md`, `02_ingestion.md`, `05_resilience.md`, and `06_evaluation.md` were factually corrected this session — the two real incidents (files claimed-written-but-absent during the resilience tier; a stale-base build during the evaluation-harness tier) were misattributed to the ingestion and frontend tiers respectively, and are now attributed correctly. All eight per-tier files plus the README were re-read end-to-end this session for internal consistency after the correction. Secrets scan of `agent_transcripts/` re-run this session: clean (see below). |
| 7 | Tests | **Verified** | `backend/tests/` has 12 test files covering config validation, retrieval, provider factory/resilience, health resilience, artifact sanitization/routing/persistence, sessions, confidence gating, and Ship 30 validators. `frontend/src/**/__tests__/` has 2 test files (state machine, source chip) plus Vitest config. `docs/manual-test-plan.md` exists as the short manual UI checklist (8 steps, read this session). Per the README's own Tier 8 verification report, both suites were actually run in that pass (backend: 61 passed / 9 skipped / 0 failed after a real bug fix; frontend: 18 passed / 0 failed) — not re-run again in this session, but the report describing that run was read and is internally consistent with the files it references. |
| 8 | Demo video | **Not yet done** | `docs/demo-script.md` was written this session (fits 2:00–2:45 spoken, within the assignment's 2–3 minute requirement) but no video file or YouTube link exists in this repo yet. Recording, camera-on, and the YouTube upload are still outstanding — do not mark this deliverable done until the actual video exists and the link is in the README. |

## What was freshly reconfirmed this session (not carried over from an earlier tier's claim)

- **Secrets grep, re-run:** searched the full tree for API-key-shaped
  strings, AWS keys, PEM private key headers, and inline password
  literals. One match: `README.md`'s documented example
  `ANTHROPIC_API_KEY=sk-ant-...`, which is a placeholder pattern in
  installation instructions, not a real key. No other matches. Clean.
- **Confidence-gating status, re-confirmed:** `docs/architecture.md`'s
  Retrieval Design section and the README's "Evaluation status" section
  both still state, honestly, that `SIMILARITY_THRESHOLD_HIGH` /
  `SIMILARITY_THRESHOLD_MODERATE` remain the original best-guess defaults
  (`0.75`/`0.65`), that `evaluation/run_eval.py` has never been run
  end-to-end against a live DB + reachable provider in this project's
  build history, and that changing the thresholds without real eval
  numbers would be an unjustified guess dressed up as tuned. This has not
  drifted toward sounding more finished than it is.
- **Agent transcript coherence:** re-read `agent_transcripts/README.md`
  plus `02_ingestion.md`, `05_resilience.md`, `06_evaluation.md`, and
  `07_frontend_ux.md` together end-to-end after the correction. The
  README's incident summary now points to the correct files, the two
  corrected per-tier files carry the incident narrative previously
  (incorrectly) attached elsewhere, and the smaller frontend cleanup is
  described as distinct from, not conflated with, the more significant
  stale-base incident.

## What still needs a human before this is actually submittable

1. Initialize git, commit, push to a public GitHub repo, and re-run the
   secrets grep against `git log -p` (this session only checked the
   working tree).
2. Record the 2–3 minute demo video from `docs/demo-script.md`, camera
   on, and upload it to YouTube; add the link to the README.
3. Optional but recommended before submission: actually run
   `evaluation/run_eval.py` against a live ingested DB + reachable
   provider at least once, so `docs/architecture.md`'s confidence-gating
   section can move from "best-guess, pending" to a real, cited number —
   this is not required to submit honestly (the current docs already say
   so plainly), but it would strengthen the submission.