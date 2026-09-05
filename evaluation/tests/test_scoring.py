"""
Unit tests for evaluation/run_eval.py's pure scoring logic.

No DB, no LLM, no live retrieval — synthetic InDomainResult/OutOfDomainResult
objects go straight into score()/_episode_matches()/_percentile(), the same
functions run_eval.py's live run calls. This is the one part of the eval
harness that's testable without Ollama/Postgres, per the tier's test scope.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_eval import (  # noqa: E402
    InDomainResult,
    OutOfDomainResult,
    _episode_matches,
    _percentile,
    score,
)


def _in(id_, match: bool, latency: float = 1.0) -> InDomainResult:
    return InDomainResult(
        id=id_,
        question="q",
        expected_episodes=["Some Episode"],
        classification="answer" if match else "abstain",
        retrieved_episodes=["Some Episode"] if match else [],
        episode_match=match,
        latency_seconds=latency,
    )


def _ood(id_, correct: bool, latency: float = 1.0) -> OutOfDomainResult:
    return OutOfDomainResult(
        id=id_,
        question="q",
        classification="abstain" if correct else "answer",
        abstained_correctly=correct,
        provider_was_called=not correct,
        latency_seconds=latency,
    )


def test_citation_accuracy_all_correct():
    results = [_in(f"q{i}", True) for i in range(5)]
    citation_acc, _, _, _ = score(results, [])
    assert citation_acc == 100.0


def test_citation_accuracy_partial():
    results = [_in("q1", True), _in("q2", True), _in("q3", False), _in("q4", False)]
    citation_acc, _, _, _ = score(results, [])
    assert citation_acc == 50.0


def test_citation_accuracy_empty_set_is_zero_not_crash():
    citation_acc, _, _, _ = score([], [])
    assert citation_acc == 0.0


def test_abstention_correctness_all_correct():
    results = [_ood(f"o{i}", True) for i in range(4)]
    _, abstention_acc, _, _ = score([], results)
    assert abstention_acc == 100.0


def test_abstention_correctness_partial():
    results = [_ood("o1", True), _ood("o2", True), _ood("o3", False)]
    _, abstention_acc, _, _ = score([], results)
    assert round(abstention_acc, 2) == 66.67


def test_combined_scoring_realistic_mix():
    in_domain = [_in(f"q{i}", i < 9, latency=0.5 + i * 0.1) for i in range(10)]
    out_domain = [_ood(f"o{i}", i < 9, latency=0.2) for i in range(10)]
    citation_acc, abstention_acc, p50, p95 = score(in_domain, out_domain)
    assert citation_acc == 90.0
    assert abstention_acc == 90.0
    assert p50 > 0
    assert p95 >= p50


def test_episode_matches_case_insensitive_substring():
    assert _episode_matches(
        ["The original growth hacker reveals his secrets | Sean Ellis"],
        ["the original growth hacker reveals his secrets | sean ellis"],
    )


def test_episode_matches_no_overlap_fails():
    assert not _episode_matches(["Episode A"], ["Episode B", "Episode C"])


def test_episode_matches_empty_retrieved_fails():
    assert not _episode_matches(["Episode A"], [])


def test_percentile_p50_p95_ordering():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    p50 = _percentile(values, 50)
    p95 = _percentile(values, 95)
    assert p50 == 5.5
    assert p95 > p50


def test_percentile_empty_list_returns_zero():
    assert _percentile([], 50) == 0.0


def test_percentile_single_value():
    assert _percentile([3.14], 95) == 3.14
