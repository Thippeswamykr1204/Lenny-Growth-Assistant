"""No DB, no LLM — pure function tests of Ship30's deterministic validator,
mirroring test_confidence_gating.py's pattern for retriever.py's classify()."""
from app.rag.retriever import RetrievalResult, RetrievedChunk
from app.skills.ship30_writer import validate_essay

MIN_WORDS = 1100
MAX_WORDS = 1400


def _retrieval(guest="Jane Doe", episode="Scaling Growth Teams") -> RetrievalResult:
    chunk = RetrievedChunk(
        episode_title=episode,
        guest_name=guest,
        locator="12:34",
        chunk_text="some evidence text",
        similarity=0.8,
    )
    return RetrievalResult(classification="answer", chunks=[chunk])


def _words(n: int) -> str:
    return " ".join(["word"] * n)


def _conforming_essay(word_count: int, guest="Jane Doe", episode="Scaling Growth Teams") -> str:
    filler_needed = max(word_count - 40, 0)
    return (
        f"## The Hook\n\n"
        f"As {guest} explained on {episode}, most teams get this wrong.\n\n"
        f"- **Anchor one**: do the thing\n"
        f"- **Anchor two**: don't do the other thing\n\n"
        f"{_words(filler_needed)}\n"
    )


def test_passes_when_all_four_checks_clear():
    essay = _conforming_essay(1250)
    result = validate_essay(essay, _retrieval(), MIN_WORDS, MAX_WORDS)
    assert result.passed
    assert result.reasons == []
    assert MIN_WORDS <= result.word_count <= MAX_WORDS
    assert result.has_heading
    assert result.has_bullet_list
    assert result.has_attribution


def test_fails_when_too_short():
    essay = _conforming_essay(300)
    result = validate_essay(essay, _retrieval(), MIN_WORDS, MAX_WORDS)
    assert not result.passed
    assert any("word count" in r for r in result.reasons)


def test_fails_when_too_long():
    essay = _conforming_essay(2000)
    result = validate_essay(essay, _retrieval(), MIN_WORDS, MAX_WORDS)
    assert not result.passed
    assert any("word count" in r for r in result.reasons)


def test_fails_when_no_heading():
    essay = f"As Jane Doe explained on Scaling Growth Teams, teams get this wrong.\n\n- **Anchor**: fix it\n\n{_words(1150)}"
    result = validate_essay(essay, _retrieval(), MIN_WORDS, MAX_WORDS)
    assert not result.passed
    assert any("heading" in r for r in result.reasons)


def test_fails_when_no_bullet_list():
    essay = f"## The Hook\n\nAs Jane Doe explained on Scaling Growth Teams, teams get this wrong.\n\n{_words(1150)}"
    result = validate_essay(essay, _retrieval(), MIN_WORDS, MAX_WORDS)
    assert not result.passed
    assert any("bullet" in r for r in result.reasons)


def test_fails_when_no_attribution():
    essay = f"## The Hook\n\nMost teams get this wrong.\n\n- **Anchor**: fix it\n\n{_words(1150)}"
    result = validate_essay(essay, _retrieval(), MIN_WORDS, MAX_WORDS)
    assert not result.passed
    assert any("attribut" in r for r in result.reasons)


def test_attribution_matches_on_episode_title_alone():
    essay = f"## Hook\n\nScaling Growth Teams covered this well.\n\n- **Anchor**: fix it\n\n{_words(1150)}"
    result = validate_essay(essay, _retrieval(), MIN_WORDS, MAX_WORDS)
    assert result.has_attribution


def test_numbered_list_counts_as_bullet_list():
    essay = f"## Hook\n\nAs Jane Doe explained on Scaling Growth Teams:\n\n1. First step\n2. Second step\n\n{_words(1150)}"
    result = validate_essay(essay, _retrieval(), MIN_WORDS, MAX_WORDS)
    assert result.has_bullet_list


def test_multiple_failures_all_reported():
    essay = "Just a short sentence with no structure at all."
    result = validate_essay(essay, _retrieval(), MIN_WORDS, MAX_WORDS)
    assert not result.passed
    assert len(result.reasons) == 4  # word count, heading, bullet, attribution all fail