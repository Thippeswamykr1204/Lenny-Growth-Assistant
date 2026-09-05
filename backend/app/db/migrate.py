"""
Runs every migrations/*.sql file against the configured database, in
filename order (001_..., 002_..., ...).

Invoked automatically on backend startup (see app/main.py) so
`docker compose up` alone is sufficient to reach a healthy state with no
manual migration step — appropriate for this project's "boots cleanly"
goal, and safe because each script is written to be idempotent.

Tier 4 note: this was originally hardcoded to run only 001_init.sql.
Generalized to glob+sort the migrations directory so 002_artifact_security_
fields.sql (and any later migration) actually applies on startup too,
without editing this function again next time — the discipline of "new
schema changes go in a new numbered migration file" only works end-to-end
if the runner picks new files up automatically.

Also runnable standalone: `python -m app.db.migrate`
"""
import asyncio
import logging
from pathlib import Path

from sqlalchemy import text

from app.db.session import engine

logger = logging.getLogger("app.db.migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


async def run_migrations() -> None:
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    async with engine.begin() as conn:
        for sql_path in sql_files:
            sql = sql_path.read_text()
            # asyncpg's execute doesn't support multiple statements in one
            # call the way psycopg does, so split on statement boundaries.
            # This is a deliberately simple splitter appropriate for small,
            # hand-written migration scripts — not a general SQL parser.
            statements = [s.strip() for s in sql.split(";\n\n") if s.strip()]
            for statement in statements:
                await conn.execute(text(statement))
            logger.info("migration applied", extra={"source": sql_path.name})


if __name__ == "__main__":
    asyncio.run(run_migrations())