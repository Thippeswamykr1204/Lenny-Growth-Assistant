"""
Query-side embedding. MUST use the exact same model as backend/scripts/ingest.py
(settings.embedding_model, sentence-transformers/all-MiniLM-L6-v2, 384-dim) —
a mismatch here silently degrades retrieval quality with no error, since
cosine similarity between vectors from two different models is meaningless
but doesn't fail loudly. Both this module and ingest.py read the model name
from the same config field for exactly this reason; do not hardcode a
different string in either place.

Loaded once at module import (process-lifetime singleton), not per-request —
SentenceTransformer construction is expensive (model load), so a per-request
load would add hundreds of ms of latency to every query.
"""
import logging

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logger = logging.getLogger("app.rag.embeddings")

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        settings = get_settings()
        logger.info("loading query embedding model", extra={"model": settings.embedding_model})
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_query(query: str) -> list[float]:
    model = _get_model()
    vector = model.encode(query, show_progress_bar=False, normalize_embeddings=True)
    return vector.tolist()