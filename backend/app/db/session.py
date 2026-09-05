"""
Async DB engine/session factory. Tier 1 uses this only for the health
check's connectivity probe — no domain queries exist yet (that's Tier 2+
once transcript_chunks retrieval and message persistence logic is built).
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# pool_timeout (Tier 5): how long a caller waits for a connection to free
# up before SQLAlchemy raises TimeoutError, rather than blocking
# indefinitely if the DB is down/overloaded and the pool is exhausted.
# Settings-driven (db_pool_timeout_seconds), not a hardcoded literal, per
# the same discipline as every other timeout in this codebase.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_timeout=settings.db_pool_timeout_seconds,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
