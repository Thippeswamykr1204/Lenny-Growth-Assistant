"""
Request-scoped structured-log context (Tier 5).

Extends, not replaces, the existing JSON logging pattern
(app/observability/logging.py) and the existing request_id middleware
(app/api/middleware.py). Before this, request_id only reached a log line
if the caller manually passed `extra={"request_id": ...}` — true only in
middleware.py itself. Every retrieval/provider/DB log call in chat.py etc.
had no way to carry request_id, session_id, provider, or phase latency
without threading those values as explicit parameters through every
function in the call chain.

A ContextVar carries a small dict per async task (correctly isolated
across concurrent requests, unlike a plain module-level global). Call
sites update it with `update_context(**fields)` as they learn things
(session_id once the request body is parsed, provider once selected,
latency once a phase completes); JsonFormatter merges whatever is
currently in context into every log record automatically, so individual
logger.info(...) calls don't need to repeat fields that are already known.
Explicit `extra={...}` on a given call still wins if it sets the same key,
so nothing here can accidentally overwrite a more specific value.
"""
from contextvars import ContextVar
from typing import Any

_log_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})


def reset_context(**initial: Any) -> None:
    """Start a fresh context — called once per request, in the middleware,
    so no state leaks between requests sharing the same worker."""
    _log_context.set(dict(initial))


def update_context(**fields: Any) -> None:
    """Merge new fields into the current request's context. None values
    are dropped rather than stored, so an unknown token count doesn't
    overwrite a previously-known one with null."""
    current = dict(_log_context.get())
    current.update({k: v for k, v in fields.items() if v is not None})
    _log_context.set(current)


def get_context() -> dict[str, Any]:
    return dict(_log_context.get())
