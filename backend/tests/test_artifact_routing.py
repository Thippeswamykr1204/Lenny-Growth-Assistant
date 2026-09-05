"""No DB, no LLM — pure function tests of artifact_generator's deterministic
format routing (never model-decided, per architecture.md)."""
from app.skills.artifact_generator import route_artifact_type


def test_explicit_markdown_field_wins_outright():
    assert route_artifact_type("markdown", request_text="build me an interactive calculator") == "markdown"


def test_explicit_html_field_wins_outright():
    assert route_artifact_type("html", request_text="just summarize this") == "html"


def test_explicit_field_wins_even_with_no_request_text():
    assert route_artifact_type("html", request_text=None) == "html"


def test_no_explicit_field_falls_back_to_html_keyword():
    assert route_artifact_type(None, "turn this into an interactive HTML widget") == "html"


def test_no_explicit_field_falls_back_to_html_for_calculator():
    assert route_artifact_type(None, "create a calculator for CAC payback") == "html"


def test_no_explicit_field_falls_back_to_html_for_visual():
    assert route_artifact_type(None, "make a visual comparing these two frameworks") == "html"


def test_no_explicit_field_defaults_to_markdown_without_html_keywords():
    assert route_artifact_type(None, "turn this into a Ship 30 essay") == "markdown"


def test_no_explicit_field_and_no_request_text_defaults_to_markdown():
    assert route_artifact_type(None, None) == "markdown"


def test_invalid_explicit_field_falls_through_to_keyword_match():
    # An unrecognized value is treated the same as "not provided" — the
    # explicit-field short-circuit only fires on a valid app-defined value.
    assert route_artifact_type("pdf", "create an interactive dashboard") == "html"


def test_keyword_match_is_case_insensitive():
    assert route_artifact_type(None, "Build me an INTERACTIVE tool") == "html"