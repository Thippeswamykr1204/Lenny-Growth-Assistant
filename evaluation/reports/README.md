# evaluation/reports/

`evaluation/run_eval.py` writes one timestamped JSON report per run here:

```
eval-<provider>-<YYYYMMDD-HHMMSS>.json
```

Each report contains the full `EvalSummary`: citation accuracy %, abstention
correctness %, latency p50/p95, the active similarity thresholds, and a
per-question breakdown (classification, matched/missed episode, latency,
retrieved episode titles) for both the in-domain and out-of-domain question
sets.

Report files in this directory are **gitignored** (see root `.gitignore`)
because they embed real retrieved transcript text and, when run against the
`anthropic` provider, real API responses — not something to commit verbatim.
This README and the directory itself are tracked so the structure survives
a fresh clone; re-run `evaluation/run_eval.py` to regenerate reports locally.

## How to read a report

- `citation_accuracy_pct` — of the in-domain questions, the % where at least
  one of the question's `expected_episodes` appeared among the episodes
  actually retrieved (i.e., real grounding, not just a plausible-sounding
  answer).
- `abstention_correctness_pct` — of the out-of-domain questions, the % that
  correctly triggered `classify() == "abstain"` (checked against the real
  confidence-gating code path in `app.rag.retriever`).
- `in_domain_results[].episode_match` / `out_of_domain_results[].abstained_correctly`
  — per-question pass/fail, so a shortfall is diagnosable at the question
  level, not just a single aggregate number.
- `out_of_domain_results[].provider_was_called` — should be `false` for
  every out-of-domain question; `true` means the abstention short-circuit in
  `app.skills.grounded_qa.run_grounded_qa` didn't fire and the LLM was
  called on a question it shouldn't have been.
