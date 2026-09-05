"""
GET /api/health

Per PRD.md acceptance criteria: returns distinguishable status per
dependency (DB, Ollama, transcript_chunks table), not a single boolean.
Fast by construction — connectivity/existence checks only, no LLM or
embedding calls.

Ollama is only checked when the local-ai profile is actually running,
controlled by the LOCAL_AI_ENABLED env var set in docker-compose.yml for
the `backend` service only when the `local-ai` profile is active. This
avoids failing health because nobody asked for local inference in this
environment (explicit Tier 1 requirement).
"""
import logging
import os

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings, validate_config
from app.db.session import AsyncSessionLocal

router = APIRouter()
logger = logging.getLogger("app.health")
settings = get_settings()


async def _check_database() -> dict:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 — health check must not raise
        logger.warning("database health check failed", extra={"error": str(exc)})
        return {"status": "unreachable", "detail": str(exc)}


async def _check_transcript_chunks_table() -> dict:
    # Tier 2 change: report row count, not just table existence — "table
    # exists" was true even before ingestion ever ran, so it couldn't
    # distinguish "ready" from "empty." status is "ok" only once ingestion
    # has actually produced rows.
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM transcript_chunks"))
            count = result.scalar_one()
        if count > 0:
            return {"status": "ok", "row_count": count}
        return {"status": "empty", "row_count": 0, "detail": "table exists but ingest.py has not run"}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "transcript_chunks health check failed", extra={"error": str(exc)}
        )
        return {"status": "not_queryable", "detail": str(exc)}


async def _check_ollama() -> dict:
    local_ai_enabled = os.getenv("LOCAL_AI_ENABLED", "false").lower() == "true"
    if not local_ai_enabled:
        return {"status": "not_configured", "detail": "local-ai profile not active"}

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
        if response.status_code == 200:
            return {"status": "ok"}
        return {"status": "unreachable", "detail": f"HTTP {response.status_code}"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("ollama health check failed", extra={"error": str(exc)})
        return {"status": "unreachable", "detail": str(exc)}


def _check_configuration() -> dict:
    # Reuses validate_config() — the exact same function main.py's startup
    # calls to fail fast (app/core/config.py) — so this can never drift
    # from what actually gates startup. In normal operation, if this ever
    # reports an issue the process should already have refused to start;
    # this exists so "misconfigured" is a distinct, inspectable state
    # rather than only ever a startup log line nobody was watching, and so
    # tests/operators can probe current config validity without restarting
    # the process.
    issues = validate_config(settings)
    if not issues:
        return {"status": "ok"}
    return {
        "status": "misconfigured",
        "detail": "; ".join(issue.detail or issue.message for issue in issues),
    }


@router.get("/health")
async def health():
    db_status = await _check_database()
    chunks_status = await _check_transcript_chunks_table()
    ollama_status = await _check_ollama()
    config_status = _check_configuration()

    dependencies = {
        "database": db_status,
        "transcript_chunks": chunks_status,
        "ollama": ollama_status,
        "configuration": config_status,
    }

    # Overall is a convenience rollup, never a replacement for the
    # per-dependency detail above (that detail is the actual requirement).
    # Ollama's "not_configured" state does not count against overall
    # health — it's expected and correct when local-ai isn't running.
    # "misconfigured" is reported as its own overall state (distinct from
    # "degraded") because it means the deployment itself is wrong, not
    # that a dependency happens to be down right now — different remediation.
    hard_dependencies_ok = db_status["status"] == "ok" and chunks_status["status"] == "ok"
    if config_status["status"] == "misconfigured":
        overall = "misconfigured"
    elif hard_dependencies_ok:
        overall = "ok"
    else:
        overall = "degraded"

    return {"overall": overall, "dependencies": dependencies}