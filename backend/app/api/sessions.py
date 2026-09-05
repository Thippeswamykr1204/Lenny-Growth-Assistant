"""
POST /api/sessions, GET /api/sessions/{id}

Raw SQL via AsyncSessionLocal, consistent with health.py's pattern from
Tier 1 — no ORM models introduced here, since the schema is small and
already hand-written in migrations/001_init.sql.

Session scoping: every message query is WHERE session_id = :id. There is no
code path that can return another session's messages — covered by
backend/tests/test_sessions.py's isolation test.
"""
import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.db.session import AsyncSessionLocal

router = APIRouter()
logger = logging.getLogger("app.api.sessions")


class CreateSessionRequest(BaseModel):
    title: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: list | None
    provider_used: str | None
    created_at: str


class SessionOut(BaseModel):
    id: str
    title: str | None
    created_at: str
    updated_at: str


class SessionDetailOut(SessionOut):
    messages: list[MessageOut]


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_session(payload: CreateSessionRequest):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                "INSERT INTO sessions (id, title) VALUES (:id, :title) "
                "RETURNING id, title, created_at, updated_at"
            ),
            {"id": str(uuid.uuid4()), "title": payload.title},
        )
        row = result.fetchone()
        await db.commit()

    logger.info("session created", extra={"session_id": str(row.id)})
    return SessionOut(
        id=str(row.id),
        title=row.title,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
async def get_session(session_id: str):
    async with AsyncSessionLocal() as db:
        session_result = await db.execute(
            text("SELECT id, title, created_at, updated_at FROM sessions WHERE id = :id"),
            {"id": session_id},
        )
        session_row = session_result.fetchone()
        if session_row is None:
            raise HTTPException(status_code=404, detail="session not found")

        messages_result = await db.execute(
            text(
                "SELECT id, role, content, sources, provider_used, created_at "
                "FROM messages WHERE session_id = :id ORDER BY created_at ASC"
            ),
            {"id": session_id},
        )
        message_rows = messages_result.fetchall()

    return SessionDetailOut(
        id=str(session_row.id),
        title=session_row.title,
        created_at=session_row.created_at.isoformat(),
        updated_at=session_row.updated_at.isoformat(),
        messages=[
            MessageOut(
                id=str(m.id),
                role=m.role,
                content=m.content,
                sources=m.sources,
                provider_used=m.provider_used,
                created_at=m.created_at.isoformat(),
            )
            for m in message_rows
        ],
    )