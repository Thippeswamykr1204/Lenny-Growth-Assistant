"""No DB, no LLM — pure function test of the confidence-gating logic."""
from app.rag.retriever import RetrievedChunk, classify

HIGH = 0.75
MODERATE = 0.65


def _chunk(sim: float) -> RetrievedChunk:
    return RetrievedChunk(episode_title="ep", guest_name="g", locator="0:00", chunk_text="x", similarity=sim)


def test_answer_when_top_high_and_two_clear_moderate():
    chunks = [_chunk(0.80), _chunk(0.70), _chunk(0.40)]
    assert classify(chunks, HIGH, MODERATE) == "answer"


def test_qualified_when_only_one_clears_moderate():
    chunks = [_chunk(0.68), _chunk(0.40)]
    assert classify(chunks, HIGH, MODERATE) == "qualified"


def test_qualified_when_top_below_high_but_two_clear_moderate():
    chunks = [_chunk(0.70), _chunk(0.66)]
    assert classify(chunks, HIGH, MODERATE) == "qualified"


def test_abstain_when_none_clear_moderate():
    chunks = [_chunk(0.50), _chunk(0.30)]
    assert classify(chunks, HIGH, MODERATE) == "abstain"


def test_abstain_on_empty_results():
    assert classify([], HIGH, MODERATE) == "abstain"


def test_boundary_exactly_at_moderate_counts_as_clearing():
    chunks = [_chunk(0.65), _chunk(0.65)]
    assert classify(chunks, HIGH, MODERATE) == "qualified"  # top 0.65 < high 0.75