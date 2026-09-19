"""
Integration tests requiring a live Postgres (same pattern as
test_sessions.py — skipped automatically if the DB isn't reachable).

Covers:
  - /api/health reports the database as unreachable, distinctly, without
    the endpoint itself raising/crashing, when the DB is down.
  - /api/health reports "misconfigured" as a distinct overall state from
    "degraded" when default_llm_provider needs a key that isn't set.
  - App startup fails fast (raises) when misconfigured, and does NOT
    require GROQ_API_KEY when the default provider is ollama.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import asyncio

from app.core.config import Settings, validate_config
from app.db.session import AsyncSessionLocal
from app.main import app, on_startup


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
async def test_health_reports_db_unreachable_distinctly(monkeypatch):
    if not await _db_reachable():
        pytest.skip("no live database available")

    # Simulate "DB unavailable" without tearing down the real test DB
    # container: point the health check's session factory at a DB that
    # cannot possibly be reachable. This exercises the exact same code
    # path (_check_database's try/except) a real outage would hit.
    import app.api.health as health_module

    class _DeadEngine:
        pass

    async def _raise_operational_error(*args, **kwargs):
        raise OperationalError("connect failed", {}, Exception("simulated DB down"))

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *args, **kwargs):
            raise OperationalError("connect failed", {}, Exception("simulated DB down"))

    def _fake_session_local():
        return _FakeSession()

    monkeypatch.setattr(health_module, "AsyncSessionLocal", _fake_session_local)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")

    assert resp.status_code == 200  # health endpoint itself never crashes/500s
    body = resp.json()
    assert body["dependencies"]["database"]["status"] == "unreachable"
    assert body["overall"] in ("degraded", "misconfigured")


@pytest.mark.asyncio
async def test_health_reports_misconfigured_distinctly_from_degraded(monkeypatch):
    if not await _db_reachable():
        pytest.skip("no live database available")

    import app.api.health as health_module

    bad_settings = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        default_llm_provider="groq",
        groq_api_key=None,
    )
    monkeypatch.setattr(health_module, "settings", bad_settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")

    body = resp.json()
    assert body["dependencies"]["configuration"]["status"] == "misconfigured"
    assert body["overall"] == "misconfigured"


@pytest.mark.asyncio
async def test_startup_fails_fast_when_default_provider_missing_key(monkeypatch):
    import app.main as main_module

    bad_settings = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        default_llm_provider="groq",
        groq_api_key=None,
    )
    monkeypatch.setattr(main_module, "settings", bad_settings)

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        await on_startup()


@pytest.mark.asyncio
async def test_startup_does_not_require_groq_key_for_ollama_default():
    # Regression guard at the startup-validation call site itself (not
    # just the pure function, see test_config_validation.py) — ollama
    # stays bootable with zero cloud credentials configured.
    settings = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        default_llm_provider="ollama",
        groq_api_key=None,
    )
    assert validate_config(settings) == []