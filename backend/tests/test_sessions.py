"""
Integration tests — require a live Postgres with Tier 1's migration applied
(the same DATABASE_URL the app itself uses). Skipped automatically if the DB
isn't reachable, so `pytest` still runs cleanly in an environment with no DB
(e.g. a bare CI step before `docker compose up db`).

Covers the explicit PRD.md acceptance criterion: two sessions can never see
each other's messages.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import asyncio

from app.db.session import AsyncSessionLocal
from app.main import app


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
async def test_session_create_and_fetch():
    if not await _db_reachable():
        pytest.skip("no live database available")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/api/sessions", json={"title": "test session"})
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        fetch_resp = await client.get(f"/api/sessions/{session_id}")
        assert fetch_resp.status_code == 200
        body = fetch_resp.json()
        assert body["id"] == session_id
        assert body["messages"] == []


@pytest.mark.asyncio
async def test_session_isolation_no_cross_session_leakage():
    if not await _db_reachable():
        pytest.skip("no live database available")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_a = (await client.post("/api/sessions", json={"title": "A"})).json()["id"]
        session_b = (await client.post("/api/sessions", json={"title": "B"})).json()["id"]

    # Insert a message directly into session A only.
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO messages (id, session_id, role, content) "
                "VALUES (:id, :session_id, 'user', 'only in session A')"
            ),
            {"id": str(uuid.uuid4()), "session_id": session_a},
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body_a = (await client.get(f"/api/sessions/{session_a}")).json()
        body_b = (await client.get(f"/api/sessions/{session_b}")).json()

    assert len(body_a["messages"]) == 1
    assert body_a["messages"][0]["content"] == "only in session A"
    assert body_b["messages"] == []  # session B must never see session A's message


@pytest.mark.asyncio
async def test_fetch_unknown_session_returns_404():
    if not await _db_reachable():
        pytest.skip("no live database available")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/sessions/{uuid.uuid4()}")
    assert resp.status_code == 404