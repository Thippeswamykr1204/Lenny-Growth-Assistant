"""
Structured (JSON) logging skeleton.

Nothing interesting gets logged in Tier 1 — this exists purely to set the
shape every later tier (retrieval, provider calls, ingestion, artifact
rendering) must log into, instead of ad-hoc print() or unstructured
logger.info(f"...") calls that don't survive contact with a real log
aggregator.

Minimum shape per PRD/architecture requirement: timestamp, level, message,
request_id. request_id is attached per-request via middleware (see
app/api/middleware.py) so every log line inside a request can be
correlated, which matters most for diagnosing retrieval/provider/DB
failures later — exactly the failure classes PRD.md calls out.
"""
import json
import logging
import sys
from datetime import datetime, timezone

from app.observability.context import get_context

# Fields JsonFormatter always looks for, either on the record's `extra` or
# in the request-scoped context (see app/observability/context.py). Tier 5
# adds session_id, provider, retrieval_classification, and the two phase
# latencies/token counts on top of the request_id that already existed —
# same mechanism, wider set of fields, so "why was this slow" or "why did
# this fail" is answerable from the log line alone.
_CONTEXT_FIELDS = (
    "request_id",
    "session_id",
    "provider",
    "retrieval_classification",
    "retrieval_latency_ms",
    "generation_latency_ms",
    "prompt_tokens",
    "completion_tokens",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Request-scoped context first (may be empty outside a request,
        # e.g. startup logs), then per-call `extra=` fields, which win on
        # conflict since they're the more specific value.
        ctx = get_context()
        for field in _CONTEXT_FIELDS:
            if field in ctx:
                payload[field] = ctx[field]
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload)


def configure_logging(log_level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level.upper())

    # Keep uvicorn's access/error logs flowing through the same JSON shape
    # rather than their default plain-text formatter.
    for uv_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(uv_logger_name)
        uv_logger.handlers = [handler]
        uv_logger.propagate = False
