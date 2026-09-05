"""
Attaches a request_id to every incoming request so log lines emitted
during that request's lifecycle can be correlated (see
app/observability/logging.py). This is foundation plumbing only — no
request in Tier 1 does anything interesting enough to need it yet, but
every later tier's retrieval/provider/DB logging depends on this existing
now rather than being retrofitted later.
"""
import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.observability.context import reset_context

logger = logging.getLogger("app.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        # Fresh context per request (Tier 5): chat.py's handlers populate
        # session_id/provider/retrieval fields as the request progresses,
        # via app.observability.context.update_context — see that module's
        # docstring for why a ContextVar instead of threading kwargs.
        reset_context(request_id=request_id)
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
