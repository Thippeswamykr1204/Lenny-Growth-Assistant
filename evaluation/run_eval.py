"""
Tier 6 evaluation harness.

Measures citation/retrieval accuracy and abstention correctness against
PRD.md's targets (both >= 90%) by driving the REAL production code paths:
app.rag.retriever.retrieve and app.skills.grounded_qa.run_grounded_qa,
through the same DB session / provider-factory machinery the API uses.
No retrieval or classification logic is reimplemented here — an eval
harness that tests a different code path than production proves nothing
(hard constraint, restated).

Usage:
    cd backend
    python ../evaluation/run_eval.py                     # uses DEFAULT_LLM_PROVIDER from .env
    python ../evaluation/run_eval.py --provider ollama    # explicit override, same mechanism
    python ../evaluation/run_eval.py --provider anthropic # matches settings.default_llm_provider values

Must be run with the backend's virtualenv / dependencies importable and
DATABASE_URL pointing at an ingested database (transcript_chunks populated
by backend/scripts/ingest.py) — this is a live-system eval, not a unit test.
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Allow running as `python evaluation/run_eval.py` from repo root OR from
# backend/ — both need backend/ on sys.path since evaluation/ sits outside
# the backend package.
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.providers.factory import get_provider  # noqa: E402
from app.rag.retriever import retrieve  # noqa: E402
from app.skills.grounded_qa import run_grounded_qa  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parent / "datasets" / "grounded_qa_eval.json"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"


class CallCountingProvider:
    """Thin wrapper around a real provider instance that counts stream()
    invocations, so the harness can assert "no provider call was made" on
    abstention without a second, parallel detection mechanism — it wraps
    the SAME provider object chat.py would use, it doesn't replace it."""

    def __init__(self, inner):
        self._inner = inner
        self.name = inner.name
        self.call_count = 0

    async def stream(self, *args, **kwargs):
        self.call_count += 1
        async for chunk in self._inner.stream(*args, **kwargs):
            yield chunk


@dataclass
class InDomainResult:
    id: str
    question: str
    expected_episodes: list[str]
    classification: str
    retrieved_episodes: list[str]
    episode_match: bool
    latency_seconds: float
    error: str | None = None


@dataclass
class OutOfDomainResult:
    id: str
    question: str
    classification: str
    abstained_correctly: bool
    provider_was_called: bool
    latency_seconds: float
    error: str | None = None


@dataclass
class EvalSummary:
    provider: str
    similarity_threshold_high: float
    similarity_threshold_moderate: float
    citation_accuracy_pct: float
    abstention_correctness_pct: float
    latency_p50_seconds: float
    latency_p95_seconds: float
    in_domain_total: int
    out_of_domain_total: int
    in_domain_results: list[InDomainResult] = field(default_factory=list)
    out_of_domain_results: list[OutOfDomainResult] = field(default_factory=list)


def _episode_matches(expected: list[str], retrieved: list[str]) -> bool:
    """Expected-episode match is judged on containment, not exact string
    equality: retrieved episode_title strings come straight from ingest.py's
    YAML frontmatter, but a question's expected_episodes entry only needs to
    identify the right episode, not reproduce every whitespace/quote quirk."""
    retrieved_lower = [r.lower() for r in retrieved]
    for exp in expected:
        exp_lower = exp.lower()
        if any(exp_lower in r or r in exp_lower for r in retrieved_lower):
            return True
    return False


async def _run_in_domain(session, settings, provider, item: dict) -> InDomainResult:
    start = time.monotonic()
    try:
        result = await retrieve(session, item["question"], settings)
        retrieved_episodes = list({c.episode_title for c in result.chunks})
        # Drive the real grounded_qa path too (not just retrieval) — consume
        # the stream fully so latency reflects the whole answer, matching
        # what a real user experiences, unless the classification abstained.
        qa = run_grounded_qa(item["question"], result, history=[], provider=provider)
        if qa.stream is not None:
            async for _ in qa.stream:
                pass
        elapsed = time.monotonic() - start
        return InDomainResult(
            id=item["id"],
            question=item["question"],
            expected_episodes=item["expected_episodes"],
            classification=result.classification,
            retrieved_episodes=retrieved_episodes,
            episode_match=_episode_matches(item["expected_episodes"], retrieved_episodes),
            latency_seconds=round(elapsed, 3),
        )
    except Exception as exc:  # noqa: BLE001 — eval must record, not crash, per-question failures
        elapsed = time.monotonic() - start
        return InDomainResult(
            id=item["id"],
            question=item["question"],
            expected_episodes=item["expected_episodes"],
            classification="error",
            retrieved_episodes=[],
            episode_match=False,
            latency_seconds=round(elapsed, 3),
            error=str(exc),
        )


async def _run_out_of_domain(session, settings, provider, item: dict) -> OutOfDomainResult:
    start = time.monotonic()
    counting_provider = CallCountingProvider(provider)
    try:
        result = await retrieve(session, item["question"], settings)
        qa = run_grounded_qa(item["question"], result, history=[], provider=counting_provider)
        if qa.stream is not None:
            async for _ in qa.stream:
                pass
        elapsed = time.monotonic() - start
        return OutOfDomainResult(
            id=item["id"],
            question=item["question"],
            classification=result.classification,
            abstained_correctly=(result.classification == "abstain"),
            provider_was_called=(counting_provider.call_count > 0),
            latency_seconds=round(elapsed, 3),
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - start
        return OutOfDomainResult(
            id=item["id"],
            question=item["question"],
            classification="error",
            abstained_correctly=False,
            provider_was_called=(counting_provider.call_count > 0),
            latency_seconds=round(elapsed, 3),
            error=str(exc),
        )


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(ordered) - 1)
    if f == c:
        return round(ordered[f], 3)
    return round(ordered[f] + (ordered[c] - ordered[f]) * (k - f), 3)


def score(
    in_domain_results: list[InDomainResult], out_of_domain_results: list[OutOfDomainResult]
) -> tuple[float, float, float, float]:
    """Pure scoring function, isolated so it can be unit tested without a
    live DB/LLM (see evaluation/tests/test_scoring.py)."""
    n_in = len(in_domain_results)
    citation_accuracy = (
        100.0 * sum(1 for r in in_domain_results if r.episode_match) / n_in if n_in else 0.0
    )
    n_ood = len(out_of_domain_results)
    abstention_correctness = (
        100.0 * sum(1 for r in out_of_domain_results if r.abstained_correctly) / n_ood
        if n_ood
        else 0.0
    )
    all_latencies = [r.latency_seconds for r in in_domain_results] + [
        r.latency_seconds for r in out_of_domain_results
    ]
    p50 = _percentile(all_latencies, 50)
    p95 = _percentile(all_latencies, 95)
    return round(citation_accuracy, 2), round(abstention_correctness, 2), p50, p95


async def run(provider_override: str | None) -> EvalSummary:
    settings = get_settings()
    provider = get_provider(settings, override=provider_override)
    dataset = json.loads(DATASET_PATH.read_text())

    in_domain_results: list[InDomainResult] = []
    out_of_domain_results: list[OutOfDomainResult] = []

    async with AsyncSessionLocal() as session:
        for item in dataset["in_domain"]:
            in_domain_results.append(await _run_in_domain(session, settings, provider, item))
        for item in dataset["out_of_domain"]:
            out_of_domain_results.append(
                await _run_out_of_domain(session, settings, provider, item)
            )

    citation_accuracy, abstention_correctness, p50, p95 = score(
        in_domain_results, out_of_domain_results
    )

    return EvalSummary(
        provider=provider.name,
        similarity_threshold_high=settings.similarity_threshold_high,
        similarity_threshold_moderate=settings.similarity_threshold_moderate,
        citation_accuracy_pct=citation_accuracy,
        abstention_correctness_pct=abstention_correctness,
        latency_p50_seconds=p50,
        latency_p95_seconds=p95,
        in_domain_total=len(in_domain_results),
        out_of_domain_total=len(out_of_domain_results),
        in_domain_results=in_domain_results,
        out_of_domain_results=out_of_domain_results,
    )


def _write_report(summary: EvalSummary) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out_path = REPORTS_DIR / f"eval-{summary.provider}-{ts}.json"
    out_path.write_text(json.dumps(asdict(summary), indent=2))
    return out_path


def _print_summary(summary: EvalSummary) -> None:
    print("=" * 72)
    print(f"Provider: {summary.provider}")
    print(
        f"Thresholds: high={summary.similarity_threshold_high} "
        f"moderate={summary.similarity_threshold_moderate}"
    )
    print(
        f"Citation accuracy:      {summary.citation_accuracy_pct}%  "
        f"({summary.in_domain_total} in-domain questions)"
    )
    print(
        f"Abstention correctness: {summary.abstention_correctness_pct}%  "
        f"({summary.out_of_domain_total} out-of-domain questions)"
    )
    print(f"Latency p50: {summary.latency_p50_seconds}s   p95: {summary.latency_p95_seconds}s")
    print("-" * 72)
    print("Per-question breakdown (in-domain):")
    for r in summary.in_domain_results:
        flag = "OK " if r.episode_match else "MISS"
        err = f"  ERROR: {r.error}" if r.error else ""
        print(f"  [{flag}] {r.id:6s} class={r.classification:9s} {r.latency_seconds:>6.2f}s  {r.question[:60]}{err}")
    print("Per-question breakdown (out-of-domain):")
    for r in summary.out_of_domain_results:
        flag = "OK " if r.abstained_correctly else "MISS"
        called = "PROVIDER-CALLED!" if r.provider_was_called else ""
        err = f"  ERROR: {r.error}" if r.error else ""
        print(f"  [{flag}] {r.id:6s} class={r.classification:9s} {r.latency_seconds:>6.2f}s  {called}{err}")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the grounded-QA evaluation harness.")
    parser.add_argument(
        "--provider",
        choices=["ollama", "anthropic"],
        default=None,
        help="Override settings.default_llm_provider (same selection mechanism as the API).",
    )
    args = parser.parse_args()

    summary = asyncio.run(run(args.provider))
    _print_summary(summary)
    out_path = _write_report(summary)
    print(f"\nFull report written to: {out_path}")


if __name__ == "__main__":
    main()
