"""
Retrieval: embed a query, run flat pgvector cosine similarity search against
transcript_chunks (locked decision: flat index, not HNSW), and classify the
result via app-side confidence gating (never model-self-reported confidence).

Confidence gating, per architecture.md (best-guess thresholds, configurable,
flagged as pending real eval — see config.py):
  - "answer":    top similarity >= high AND >=2 chunks clear moderate
  - "qualified": exactly 1 chunk clears moderate (but "answer" condition not met)
  - "abstain":   no chunk clears moderate
"""
import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.rag.embeddings import embed_query

logger = logging.getLogger("app.rag.retriever")

Classification = Literal["answer", "qualified", "abstain"]


@dataclass
class RetrievedChunk:
    episode_title: str
    guest_name: str | None
    locator: str | None
    chunk_text: str
    similarity: float


@dataclass
class RetrievalResult:
    classification: Classification
    chunks: list[RetrievedChunk]  # chunks clearing the moderate threshold, best first


def classify(chunks: list[RetrievedChunk], high: float, moderate: float) -> Classification:
    clearing_moderate = [c for c in chunks if c.similarity >= moderate]
    if not clearing_moderate:
        return "abstain"
    top = clearing_moderate[0].similarity
    if top >= high and len(clearing_moderate) >= 2:
        return "answer"
    return "qualified"


async def retrieve(session: AsyncSession, query: str, settings: Settings) -> RetrievalResult:
    query_vector = embed_query(query)
    vector_literal = "[" + ",".join(f"{x:.8f}" for x in query_vector) + "]"

    result = await session.execute(
        text(
            """
            SELECT episode_title, guest_name, locator, chunk_text,
                   1 - (embedding <=> CAST(:vector AS vector)) AS similarity
            FROM transcript_chunks
            ORDER BY embedding <=> CAST(:vector AS vector)
            LIMIT :top_k
            """
        ),
        {"vector": vector_literal, "top_k": settings.retrieval_top_k},
    )
    rows = result.fetchall()

    all_chunks = [
        RetrievedChunk(
            episode_title=r.episode_title,
            guest_name=r.guest_name,
            locator=r.locator,
            chunk_text=r.chunk_text,
            similarity=float(r.similarity),
        )
        for r in rows
    ]

    classification = classify(
        all_chunks, settings.similarity_threshold_high, settings.similarity_threshold_moderate
    )
    clearing_moderate = [c for c in all_chunks if c.similarity >= settings.similarity_threshold_moderate]

    logger.info(
        "retrieval complete",
        extra={
            "classification": classification,
            "top_k": settings.retrieval_top_k,
            "n_clearing_moderate": len(clearing_moderate),
            "top_similarity": all_chunks[0].similarity if all_chunks else None,
        },
    )

    return RetrievalResult(classification=classification, chunks=clearing_moderate)