"""
Integration tests — require a live Postgres with migrations 001+002
applied (the same DATABASE_URL the app itself uses). Skipped automatically
if the DB isn't reachable, matching test_sessions.py's pattern.

Covers: an artifact row persisted via chat.py's _persist_artifact() helper
carries the exact content_hash and security_status computed by
artifact_generator.py -- i.e. the stamping described in this tier's
exit_criteria is actually written to the row, not just computed in memory.

This does NOT exercise the LLM-calling paths (ship30 essay writing, HTML
generation) -- those need a live provider (Ollama or Anthropic) and are
listed as "stated should work but not verified live" in the tier's
verification report. This test exercises the persistence layer directly,
the same way sanitize_html()/route_artifact_type() are tested directly in
test_artifact_sanitizer.py / test_artifact_routing.py without a live LLM.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import asyncio

from app.api.chat import _persist_artifact, _persist_message
from app.db.session import AsyncSessionLocal
from app.main import app
from app.skills.artifact_generator import build_markdown_artifact, content_hash, sanitize_html


async def _db_reachable() -> bool:
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return True
    except (OperationalError, ConnectionRefusedError, OSError, asyncio.TimeoutError):
        # OperationalError covers most DB-down cases once SQLAlchemy has
        # wrapped the DBAPI error; a bare ConnectionRefusedError/OSError is
        # what actually surfaces when nothing is listening on the port at
        # all (connection refused at the socket level, before SQLAlchemy's
        # wrapping kicks in) — both mean "no live DB", so both skip.
        return False


@pytest.mark.asyncio
async def test_markdown_artifact_persists_with_correct_hash_and_status():
    if not await _db_reachable():
        pytest.skip("no live database available")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = (await client.post("/api/sessions", json={"title": "artifact test"})).json()["id"]

    payload = build_markdown_artifact("## Hello\n\nSome markdown body.")

    async with AsyncSessionLocal() as db:
        message_id = await _persist_message(db, session_id, "assistant", payload.content)
        artifact_id = await _persist_artifact(db, message_id, payload)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT artifact_type, content, content_hash, security_status FROM artifacts WHERE id = :id"),
            {"id": artifact_id},
        )
        row = result.fetchone()

    assert row is not None
    assert row.artifact_type == "markdown"
    assert row.content == payload.content
    assert row.content_hash == payload.content_hash
    assert row.content_hash == content_hash(payload.content)
    assert row.security_status == "sanitized"


@pytest.mark.asyncio
async def test_blocked_html_artifact_persists_with_blocked_status_not_silently_sanitized():
    if not await _db_reachable():
        pytest.skip("no live database available")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = (await client.post("/api/sessions", json={"title": "blocked artifact test"})).json()["id"]

    raw_html = '<img src="x" onerror="alert(1)"><script src="https://evil.example/x.js"></script>'
    sanitization = sanitize_html(raw_html)
    assert sanitization.security_status == "blocked"  # sanity check on the fixture itself

    from app.skills.artifact_generator import ArtifactPayload

    payload = ArtifactPayload(
        artifact_type="html",
        content=sanitization.clean_html,
        content_hash=content_hash(sanitization.clean_html),
        security_status=sanitization.security_status,
    )

    async with AsyncSessionLocal() as db:
        message_id = await _persist_message(db, session_id, "assistant", payload.content)
        artifact_id = await _persist_artifact(db, message_id, payload)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT content, content_hash, security_status FROM artifacts WHERE id = :id"),
            {"id": artifact_id},
        )
        row = result.fetchone()

    assert row is not None
    assert row.security_status == "blocked"  # never silently reported as "sanitized"
    assert "onerror" not in row.content
    assert "evil.example" not in row.content


@pytest.mark.asyncio
async def test_artifact_row_links_to_its_message():
    if not await _db_reachable():
        pytest.skip("no live database available")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = (await client.post("/api/sessions", json={"title": "link test"})).json()["id"]

    payload = build_markdown_artifact("content")
    async with AsyncSessionLocal() as db:
        message_id = await _persist_message(db, session_id, "assistant", payload.content)
        artifact_id = await _persist_artifact(db, message_id, payload)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT message_id FROM artifacts WHERE id = :id"), {"id": artifact_id}
        )
        row = result.fetchone()
    assert str(row.message_id) == message_id