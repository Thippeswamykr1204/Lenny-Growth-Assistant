"""
Tier 1 scope: app boots, talks to the DB, exposes /api/health, and logs in
structured JSON. No chat, retrieval, providers, or skills are wired here —
those routers get included in later tiers (see app/api/, app/rag/,
app/skills/, app/providers/ package placeholders).
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.middleware import RequestContextMiddleware
from app.api.sessions import router as sessions_router
from app.core.config import get_settings, validate_config
from app.db.migrate import run_migrations
from app.observability.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("app.main")

app = FastAPI(
    title="Lenny Growth Assistant API",
    version="0.1.0-foundation",
)

app.add_middleware(RequestContextMiddleware)

# Permissive for local dev across the Compose network; tightened when a
# real deployment target exists (Tier 5/production hardening, not now).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(sessions_router, prefix="/api", tags=["sessions"])
app.include_router(chat_router, prefix="/api", tags=["chat"])

# --- Deferred to later tiers (not built here, listed for traceability) ---
# Ship 30 for 30 skill, artifact generation/viewer, and any frontend chat UI
# beyond a bare sanity check are Tier 4/5 — not wired here.
# ingestion CLI entrypoint lives outside the API surface entirely         # Tier 2


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("starting up", extra={"app_env": settings.app_env})

    # Fail fast (Tier 5): validate_config() is the same function
    # /api/health calls at runtime (app/api/health.py's _check_configuration)
    # — one check, two call sites. A misconfigured required provider should
    # never surface for the first time as a confusing failure on someone's
    # first chat request; it should stop the process from coming up at all,
    # with a clear message in the startup logs.
    config_issues = validate_config(settings)
    if config_issues:
        for issue in config_issues:
            logger.critical("startup configuration invalid", extra={"detail": issue.detail})
        raise RuntimeError(config_issues[0].detail)

    await run_migrations()
    logger.info("startup complete")


@app.get("/")
async def root():
    return {
        "service": "lenny-growth-assistant-backend",
        "status": "foundation tier — no product features yet",
    }