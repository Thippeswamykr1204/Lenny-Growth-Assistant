"""
Typed application exceptions (Tier 5).

Before this, chat.py and health.py each shaped errors ad hoc: a try/except
around a provider or DB call, an inline user-safe string, and a
logger.warning/exception call with an inline detail string — repeated
independently in three-plus places with no shared shape. That's fine at
Tier 1-4 scale; at Tier 5 it becomes the thing this tier is explicitly
asked to fix.

Every exception here carries two separate strings:
  - `message`  — safe to send to the client, no internals, no stack trace.
  - `detail`   — server-side only, goes into structured logs, never into
                 an HTTP response body or SSE event.

This mirrors the shape ProviderError already used (providers/base.py) —
that pattern is reused here rather than inventing a second one, per the
hard constraint against parallel error-shaping conventions.
"""
from dataclasses import dataclass


@dataclass
class AppError(Exception):
    """Base for every typed application error. Not raised directly."""
    message: str  # user-safe
    detail: str | None = None  # internal only; logged, never returned to client

    def __str__(self) -> str:  # so logger.exception("...", exc_info=exc) is readable
        return self.detail or self.message


@dataclass
class ProviderUnavailableError(AppError):
    """The selected LLM provider could not be reached at all (connection
    refused, DNS failure, service down)."""
    pass


@dataclass
class ProviderTimeoutError(AppError):
    """The selected LLM provider was reachable but did not respond within
    its configured timeout."""
    pass


@dataclass
class DatabaseUnavailableError(AppError):
    """The Postgres connection pool could not obtain a connection, or a
    query failed because the database is down/unreachable."""
    pass


@dataclass
class RetrievalEmptyError(AppError):
    """Retrieval ran successfully but returned zero chunks above any
    threshold — distinct from a retrieval *failure* (that's
    DatabaseUnavailableError or a generic 500), and distinct from
    "qualified"/"abstain" classification (that's product logic in
    grounded_qa.py, already handled — this is the harder edge of literally
    nothing coming back, e.g. an empty transcript_chunks table)."""
    pass


@dataclass
class ConfigurationError(AppError):
    """Required configuration is missing or inconsistent — e.g. the
    configured default provider needs an API key that isn't set. Raised at
    startup (fail fast) rather than surfacing as a confusing failure on the
    first request that happens to hit it."""
    pass


@dataclass
class MalformedOutputError(AppError):
    """The model returned output that could not be used as-is — e.g. HTML
    artifact generation returned empty content or something the sanitizer
    couldn't parse into anything meaningful."""
    pass


@dataclass
class PromptValidationError(AppError):
    """The user-supplied prompt failed validation (empty, or exceeds the
    configured size limit) before any retrieval or provider call was made."""
    pass


def to_sse_error(exc: AppError) -> dict:
    """Typed SSE error events already exist (chat.py's `error` event); this
    just gives every AppError a single, consistent way to become one,
    instead of each call site hand-rolling the dict."""
    return {"type": "error", "message": exc.message}
