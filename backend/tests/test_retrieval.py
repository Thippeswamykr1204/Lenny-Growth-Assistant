"""
Integration test — requires a live Postgres with pgvector and Tier 1's
migration applied. Skipped automatically if unreachable. Seeds one known
transcript_chunks row with a hand-built embedding vector, then asserts
retrieve() returns it with the expected citation shape. Does not require
Ollama or Groq — retrieval never calls an LLM.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import asyncio

from app.core.config import Settings
from app.db.session import AsyncSessionLocal
from app.rag import embeddings as embeddings_module
from app.rag.retriever import retrieve


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
async def test_retrieval_returns_seeded_chunk_with_citation_shape(monkeypatch):
    if not await _db_reachable():
        pytest.skip("no live database available")

    # Query embedding must match a real 384-dim model; use the real model
    # via app.rag.embeddings to guarantee the vector space actually lines up
    # (a fake vector here would make the test pass for the wrong reason).
    from app.rag.embeddings import embed_query

    query = "how do you run a beta test with early users"
    query_vector = embed_query(query)

    source_file = f"data/transcripts/__test_seed__/{uuid.uuid4()}.md"
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO transcript_chunks "
                "(episode_title, guest_name, chunk_text, locator, embedding, source_file) "
                "VALUES (:t, :g, :c, :l, :e, :s)"
            ),
            {
                "t": "Test Episode",
                "g": "Test Guest",
                "c": query,  # identical text -> embedding should be its own nearest neighbor
                "l": "0:00",
                "e": "[" + ",".join(f"{x:.8f}" for x in query_vector) + "]",
                "s": source_file,
            },
        )
        await db.commit()

    settings = Settings(
        database_url="unused-here",
        similarity_threshold_high=0.75,
        similarity_threshold_moderate=0.1,  # low bar so this single seeded row clears it
        retrieval_top_k=5,
    )

    try:
        async with AsyncSessionLocal() as db:
            result = await retrieve(db, query, settings)

        assert len(result.chunks) >= 1
        top = result.chunks[0]
        assert top.episode_title == "Test Episode"
        assert top.guest_name == "Test Guest"
        assert top.locator == "0:00"
        assert top.similarity > 0.99  # identical text against itself
        assert result.classification in {"answer", "qualified"}
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM transcript_chunks WHERE source_file = :s"), {"s": source_file})
            await db.commit()