"""
POST /api/chat/stream
POST /api/chat/transform   (Tier 4)

Retrieval -> grounded_qa -> typed SSE stream -> persistence, per
architecture.md. Typed events (not raw text chunks) so the frontend never
has to sniff string content to know what kind of thing arrived:

  status    {"type": "status", "stage": "retrieving" | "generating" | ...}
  source    {"type": "source", "episode_title", "guest_name", "locator", "similarity"}
            — one event per citation, emitted before generation starts
  token     {"type": "token", "text": "..."}
  artifact  {"type": "artifact", "artifact_id", "artifact_type", "security_status"}
            — Tier 4: emitted once generation + sanitization + persistence
            of a Ship30 essay or artifact completes
  error     {"type": "error", "message": "<user-safe>"}
  done      {"type": "done", "message_id": "...", "provider_used": "...", "qualified": bool}

On any provider failure, the real exception is logged server-side and only
ProviderError.message (already user-safe, see providers/base.py) reaches
the client — never a raw stack trace or SDK exception string.

Tier 4 design choice: /chat/transform is a NEW endpoint, not an overload of
/chat/stream's request shape. A transform request doesn't append a new
user message, doesn't run retrieval, and starts from an *existing*
assistant message's evidence rather than a fresh query — different enough
in shape and side effects that folding it into ChatRequest would mean a
pile of "only meaningful if X" optional fields on one model. A separate
endpoint keeps both request contracts honest about what they actually do,
while still sharing the same typed-SSE / _sse() / _persist_message()
machinery below.

Tier 4 also changes what the *assistant* message's `sources` JSONB stores:
previously the citation-lite dicts from grounded_qa.py's _sources_from()
(episode_title/guest_name/locator/similarity only). It now stores the full
retrieved chunk — including chunk_text — because /chat/transform needs the
exact evidence a QA turn already retrieved, not a fresh, ungrounded
retrieval (hard constraint). This is a superset of the old shape (nothing
that read episode_title/guest_name/locator/similarity breaks) and touches
only this file — grounded_qa.py and retriever.py are unchanged.
"""
import json
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.errors import DatabaseUnavailableError, to_sse_error
from app.db.session import AsyncSessionLocal
from app.observability.context import update_context
from app.providers.base import ProviderError
from app.providers.factory import UnknownProviderError, get_provider
from app.rag.retriever import RetrievalResult, RetrievedChunk, retrieve
from app.skills.artifact_generator import (
    ArtifactPayload,
    build_markdown_artifact,
    content_hash,
    generate_html_artifact,
    route_artifact_type,
    sanitize_html,
)
from app.skills.grounded_qa import ABSTENTION_MESSAGE, run_grounded_qa
from app.skills.ship30_writer import SHIP30_ABSTENTION_MESSAGE, run_ship30

router = APIRouter()
logger = logging.getLogger("app.api.chat")


class ChatRequest(BaseModel):
    session_id: str
    message: str
    provider: str | None = None  # explicit per-request override; app logic only


class TransformRequest(BaseModel):
    session_id: str
    message_id: str  # the prior ASSISTANT message whose evidence gets reused
    transform_type: str  # "ship30" | "artifact"
    artifact_type: str | None = None  # explicit "markdown" | "html"; only meaningful for transform_type="artifact"
    request_text: str | None = None  # optional free-text brief (fallback routing input + HTML generation brief)
    topic: str | None = None  # optional angle/narrowing; ship30 only
    provider: str | None = None  # explicit per-request override; app logic only


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _load_history(db, session_id: str) -> list[dict]:
    result = await db.execute(
        text(
            "SELECT role, content FROM messages WHERE session_id = :id "
            "AND role IN ('user', 'assistant') ORDER BY created_at ASC"
        ),
        {"id": session_id},
    )
    return [{"role": r.role, "content": r.content} for r in result.fetchall()]


async def _persist_message(db, session_id: str, role: str, content: str, sources=None, provider_used=None):
    result = await db.execute(
        text(
            "INSERT INTO messages (id, session_id, role, content, sources, provider_used) "
            "VALUES (:id, :session_id, :role, :content, :sources, :provider_used) RETURNING id"
        ),
        {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "role": role,
            "content": content,
            "sources": json.dumps(sources) if sources is not None else None,
            "provider_used": provider_used,
        },
    )
    row = result.fetchone()
    await db.commit()
    return str(row.id)


async def _persist_artifact(db, message_id: str, payload: ArtifactPayload) -> str:
    result = await db.execute(
        text(
            "INSERT INTO artifacts (id, message_id, artifact_type, content, content_hash, security_status) "
            "VALUES (:id, :message_id, :artifact_type, :content, :content_hash, :security_status) "
            "RETURNING id"
        ),
        {
            "id": str(uuid.uuid4()),
            "message_id": message_id,
            "artifact_type": payload.artifact_type,
            "content": payload.content,
            "content_hash": payload.content_hash,
            "security_status": payload.security_status,
        },
    )
    row = result.fetchone()
    await db.commit()
    return str(row.id)


def _chunk_to_stored_dict(c: RetrievedChunk) -> dict:
    """Full evidence, not just citation metadata — see module docstring
    (Tier 4 change to what `sources` stores)."""
    return {
        "episode_title": c.episode_title,
        "guest_name": c.guest_name,
        "locator": c.locator,
        "chunk_text": c.chunk_text,
        "similarity": round(c.similarity, 4),
    }


def _retrieval_from_stored_sources(sources: list[dict] | None) -> RetrievalResult:
    """Reconstructs a RetrievalResult from a previously-persisted message's
    `sources` column — this is how /chat/transform reuses a prior QA turn's
    evidence instead of running a fresh retrieval (hard constraint).

    Classification is re-derived from chunk count rather than re-stored,
    since the chunks here already cleared the moderate threshold when
    originally retrieved (retriever.py only ever persists chunks that did):
    empty -> "abstain", exactly one -> "qualified", two or more -> "answer".
    This mirrors classify()'s shape without importing model-specific
    thresholds that don't apply to already-filtered data.

    Rows written before this Tier 4 change only have citation-lite sources
    (no chunk_text) — those are tolerated as if no evidence were stored,
    degrading to "abstain" rather than crashing on a KeyError.
    """
    chunks = [
        RetrievedChunk(
            episode_title=s.get("episode_title", "unknown episode"),
            guest_name=s.get("guest_name"),
            locator=s.get("locator"),
            chunk_text=s["chunk_text"],
            similarity=float(s.get("similarity", 0.0)),
        )
        for s in (sources or [])
        if s.get("chunk_text")
    ]
    if not chunks:
        classification = "abstain"
    elif len(chunks) == 1:
        classification = "qualified"
    else:
        classification = "answer"
    return RetrievalResult(classification=classification, chunks=chunks)


async def _event_stream(req: ChatRequest):
    settings = get_settings()
    update_context(session_id=req.session_id)

    try:
        async with AsyncSessionLocal() as db:
            session_check = await db.execute(
                text("SELECT id FROM sessions WHERE id = :id"), {"id": req.session_id}
            )
            if session_check.fetchone() is None:
                yield _sse({"type": "error", "message": "Session not found."})
                return

            history = await _load_history(db, req.session_id)
            await _persist_message(db, req.session_id, "user", req.message)
    except SQLAlchemyError as exc:
        err = DatabaseUnavailableError(
            message="We're having trouble reaching the database right now. Please try again shortly.",
            detail=f"session lookup / user message persist failed: {exc}",
        )
        logger.error("database unavailable", extra={"detail": err.detail})
        yield _sse(to_sse_error(err))
        return

    yield _sse({"type": "status", "stage": "retrieving"})

    retrieval_start = time.perf_counter()
    try:
        async with AsyncSessionLocal() as db:
            retrieval = await retrieve(db, req.message, settings)
    except SQLAlchemyError as exc:
        err = DatabaseUnavailableError(
            message="We're having trouble reaching the database right now. Please try again shortly.",
            detail=f"retrieval query failed: {exc}",
        )
        logger.error("database unavailable during retrieval", extra={"detail": err.detail})
        yield _sse(to_sse_error(err))
        return
    except Exception:  # noqa: BLE001 — retrieval failure must not leak internals
        logger.exception("retrieval failed", extra={"session_id": req.session_id})
        yield _sse({"type": "error", "message": "Something went wrong looking up relevant transcripts."})
        return
    update_context(
        retrieval_latency_ms=round((time.perf_counter() - retrieval_start) * 1000, 2),
        retrieval_classification=retrieval.classification,
    )

    for chunk in retrieval.chunks:
        yield _sse(
            {
                "type": "source",
                "episode_title": chunk.episode_title,
                "guest_name": chunk.guest_name,
                "locator": chunk.locator,
                "similarity": round(chunk.similarity, 4),
                # Tier 7 addition: design.md's citation-expansion interaction needs the
                # underlying chunk text client-side. We already load it for retrieval —
                # this just stops discarding it before it reaches the SSE payload.
                "chunk_text": chunk.chunk_text,
             }
        )

    try:
        provider = get_provider(settings, override=req.provider)
    except UnknownProviderError as exc:
        logger.warning("unknown provider requested", extra={"provider": req.provider, "error": str(exc)})
        yield _sse({"type": "error", "message": "Requested provider is not recognized."})
        return

    update_context(provider=provider.name)
    qa_result = run_grounded_qa(req.message, retrieval, history, provider)

    if qa_result.is_abstention:
        logger.info("abstaining, no LLM call made", extra={"session_id": req.session_id})
        yield _sse({"type": "token", "text": ABSTENTION_MESSAGE})
        try:
            async with AsyncSessionLocal() as db:
                message_id = await _persist_message(
                    db, req.session_id, "assistant", ABSTENTION_MESSAGE, sources=[], provider_used=None
                )
        except SQLAlchemyError as exc:
            err = DatabaseUnavailableError(
                message="We're having trouble reaching the database right now. Please try again shortly.",
                detail=f"abstention message persist failed: {exc}",
            )
            logger.error("database unavailable", extra={"detail": err.detail})
            yield _sse(to_sse_error(err))
            return
        yield _sse({"type": "done", "message_id": message_id, "provider_used": None, "qualified": False})
        return

    yield _sse({"type": "status", "stage": "generating"})

    generation_start = time.perf_counter()
    full_text = []
    stream_error = None
    usage = None
    async for piece in qa_result.stream:
        if piece.error:
            logger.warning(
                "provider error during stream",
                extra={"provider": provider.name, "detail": piece.error.detail},
            )
            stream_error = piece.error
            break
        if piece.token:
            full_text.append(piece.token)
            yield _sse({"type": "token", "text": piece.token})
        if piece.done:
            usage = piece.usage
            break
    update_context(
        generation_latency_ms=round((time.perf_counter() - generation_start) * 1000, 2),
        prompt_tokens=(usage or {}).get("prompt_tokens"),
        completion_tokens=(usage or {}).get("completion_tokens"),
    )

    if stream_error:
        # Resilience decision (Tier 5), documented here since this is the
        # only place it applies: tokens already streamed to the client in
        # `full_text` are discarded, NOT persisted as a partial assistant
        # message. Rationale — history (_load_history) replays persisted
        # messages verbatim as conversation context on the next turn; a
        # silently-truncated assistant reply re-injected as if it were a
        # complete answer would misinform future turns more than an
        # obviously-missing one does. The user already sees the tokens
        # that did arrive (nothing is hidden from them, only not saved),
        # and gets a typed error event making the incompleteness explicit,
        # so the failure is visible without corrupting session context.
        # Trade-off: a retry re-runs retrieval + generation from scratch
        # rather than resuming — acceptable given these are short QA turns,
        # not long-running jobs.
        yield _sse({"type": "error", "message": stream_error.message})
        return

    assistant_text = "".join(full_text)
    try:
        async with AsyncSessionLocal() as db:
            message_id = await _persist_message(
                db,
                req.session_id,
                "assistant",
                assistant_text,
                # Full chunks (incl. chunk_text), not qa_result.sources' citation-lite
                # dicts — see module docstring for why (Tier 4: /chat/transform reuse).
                sources=[_chunk_to_stored_dict(c) for c in retrieval.chunks],
                provider_used=provider.name,
            )
    except SQLAlchemyError as exc:
        err = DatabaseUnavailableError(
            message="Your answer was generated, but we couldn't save it right now. It may not appear if you reload.",
            detail=f"assistant message persist failed: {exc}",
        )
        logger.error("database unavailable", extra={"detail": err.detail})
        yield _sse(to_sse_error(err))
        return

    yield _sse(
        {
            "type": "done",
            "message_id": message_id,
            "provider_used": provider.name,
            "qualified": qa_result.is_qualified,
        }
    )


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")
    settings = get_settings()
    if len(req.message) > settings.max_prompt_chars:
        raise HTTPException(
            status_code=422,
            detail=f"message must not exceed {settings.max_prompt_chars} characters",
        )
    return StreamingResponse(_event_stream(req), media_type="text/event-stream")


async def _transform_event_stream(req: TransformRequest):
    settings = get_settings()
    update_context(session_id=req.session_id)

    try:
        async with AsyncSessionLocal() as db:
            msg_result = await db.execute(
                text(
                    "SELECT id, role, content, sources FROM messages "
                    "WHERE id = :id AND session_id = :session_id"
                ),
                {"id": req.message_id, "session_id": req.session_id},
            )
            msg_row = msg_result.fetchone()
    except SQLAlchemyError as exc:
        err = DatabaseUnavailableError(
            message="We're having trouble reaching the database right now. Please try again shortly.",
            detail=f"transform source message lookup failed: {exc}",
        )
        logger.error("database unavailable", extra={"detail": err.detail})
        yield _sse(to_sse_error(err))
        return

    if msg_row is None:
        yield _sse({"type": "error", "message": "Message not found in this session."})
        return
    if msg_row.role != "assistant":
        yield _sse({"type": "error", "message": "Only an assistant answer can be transformed."})
        return

    retrieval = _retrieval_from_stored_sources(msg_row.sources)

    try:
        provider = get_provider(settings, override=req.provider)
    except UnknownProviderError as exc:
        logger.warning("unknown provider requested", extra={"provider": req.provider, "error": str(exc)})
        yield _sse({"type": "error", "message": "Requested provider is not recognized."})
        return
    update_context(provider=provider.name)

    if req.transform_type == "ship30":
        yield _sse({"type": "status", "stage": "writing_ship30"})
        result = await run_ship30(retrieval, provider, settings, topic=req.topic)

        if result.is_abstention:
            logger.info("ship30 transform abstained", extra={"message_id": req.message_id})
            yield _sse({"type": "error", "message": SHIP30_ABSTENTION_MESSAGE})
            return
        if result.content is None:
            reasons = "; ".join(result.validation.reasons) if result.validation else "generation failed"
            logger.warning("ship30 transform failed validation", extra={"reasons": reasons})
            yield _sse(
                {
                    "type": "error",
                    "message": "Couldn't produce an essay that met the Ship30 format requirements. "
                    "Try again, or narrow the topic.",
                }
            )
            return

        payload = build_markdown_artifact(result.content)
        try:
            async with AsyncSessionLocal() as db:
                new_message_id = await _persist_message(
                    db,
                    req.session_id,
                    "assistant",
                    result.content,
                    sources=msg_row.sources,
                    provider_used=provider.name,
                )
                artifact_id = await _persist_artifact(db, new_message_id, payload)
        except SQLAlchemyError as exc:
            err = DatabaseUnavailableError(
                message="The essay was generated, but we couldn't save it right now. It may not appear if you reload.",
                detail=f"ship30 artifact persist failed: {exc}",
            )
            logger.error("database unavailable", extra={"detail": err.detail})
            yield _sse(to_sse_error(err))
            return

        yield _sse(
            {
                "type": "artifact",
                "artifact_id": artifact_id,
                "artifact_type": payload.artifact_type,
                "security_status": payload.security_status,
            }
        )
        return

    if req.transform_type == "artifact":
        artifact_type = route_artifact_type(req.artifact_type, req.request_text)
        yield _sse({"type": "status", "stage": f"generating_{artifact_type}_artifact"})

        if artifact_type == "markdown":
            payload = build_markdown_artifact(req.request_text or msg_row.content)
            provider_used = None
        else:
            if retrieval.classification == "abstain":
                logger.info("html artifact transform abstained (no evidence)", extra={"message_id": req.message_id})
                yield _sse(
                    {"type": "error", "message": "There isn't enough grounded evidence to generate this artifact."}
                )
                return

            raw_html, error = await generate_html_artifact(retrieval, provider, req.request_text or msg_row.content)
            if error is not None or not raw_html:
                logger.warning(
                    "html artifact generation failed",
                    extra={"detail": error.detail if isinstance(error, ProviderError) else "empty response"},
                )
                yield _sse({"type": "error", "message": "Couldn't generate the artifact right now."})
                return

            sanitization = sanitize_html(raw_html)
            payload = ArtifactPayload(
                artifact_type="html",
                content=sanitization.clean_html,
                content_hash=content_hash(sanitization.clean_html),
                security_status=sanitization.security_status,
            )
            provider_used = provider.name

        try:
            async with AsyncSessionLocal() as db:
                new_message_id = await _persist_message(
                    db,
                    req.session_id,
                    "assistant",
                    payload.content,
                    sources=msg_row.sources,
                    provider_used=provider_used,
                )
                artifact_id = await _persist_artifact(db, new_message_id, payload)
        except SQLAlchemyError as exc:
            err = DatabaseUnavailableError(
                message="The artifact was generated, but we couldn't save it right now. It may not appear if you reload.",
                detail=f"artifact persist failed: {exc}",
            )
            logger.error("database unavailable", extra={"detail": err.detail})
            yield _sse(to_sse_error(err))
            return

        # Blocked artifacts are still persisted and still emitted as an
        # `artifact` event, never silently dropped — the frontend renders
        # security_status != "sanitized" as a visible explanation, not a
        # blank pane (hard constraint: no silent failure, but also no
        # pretending a blocked payload succeeded cleanly).
        yield _sse(
            {
                "type": "artifact",
                "artifact_id": artifact_id,
                "artifact_type": payload.artifact_type,
                "security_status": payload.security_status,
            }
        )
        return

    yield _sse({"type": "error", "message": "transform_type must be 'ship30' or 'artifact'."})


@router.post("/chat/transform")
async def chat_transform(req: TransformRequest):
    if req.transform_type not in ("ship30", "artifact"):
        raise HTTPException(status_code=422, detail="transform_type must be 'ship30' or 'artifact'")
    if req.transform_type == "artifact" and req.artifact_type not in (None, "markdown", "html"):
        raise HTTPException(status_code=422, detail="artifact_type must be 'markdown' or 'html' if provided")
    return StreamingResponse(_transform_event_stream(req), media_type="text/event-stream")