"""
A simulated provider timeout (and connection failure) must yield exactly
one typed ProviderChunk(error=...) and stop — never raise out of the
streaming generator, since chat.py's _event_stream relies on that
guarantee to turn any provider failure into a typed SSE error event
instead of crashing mid-stream. No live Ollama/Anthropic and no DB needed.
"""
import httpx
import pytest

from app.providers.ollama_provider import OllamaProvider


class _RaisingStreamCtx:
    def __init__(self, exc: Exception):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *args):
        return False


async def _collect(provider, exc_to_raise, monkeypatch):
    def fake_stream(self, method, url, json=None):
        return _RaisingStreamCtx(exc_to_raise)

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    return [c async for c in provider.stream([{"role": "user", "content": "hi"}], "sys")]


@pytest.mark.asyncio
async def test_ollama_timeout_yields_single_typed_error_chunk(monkeypatch):
    provider = OllamaProvider(base_url="http://fake-ollama:11434", model="llama3.2:3b", timeout_seconds=0.01)
    chunks = await _collect(provider, httpx.TimeoutException("simulated timeout"), monkeypatch)

    assert len(chunks) == 1
    assert chunks[0].token is None
    assert chunks[0].done is False
    assert chunks[0].error is not None
    assert chunks[0].error.message  # user-safe message present
    assert "TimeoutException" not in chunks[0].error.message  # internals stay in .detail only


@pytest.mark.asyncio
async def test_ollama_unreachable_yields_single_typed_error_chunk(monkeypatch):
    provider = OllamaProvider(base_url="http://fake-ollama:11434", model="llama3.2:3b", timeout_seconds=0.01)
    chunks = await _collect(provider, httpx.ConnectError("simulated connection refused"), monkeypatch)

    assert len(chunks) == 1
    assert chunks[0].error is not None
    assert "running" in chunks[0].error.message.lower()


@pytest.mark.asyncio
async def test_ollama_unexpected_error_is_caught_not_raised(monkeypatch):
    """Anything not explicitly anticipated (a bug, a library change) must
    still degrade to a typed error chunk, not an unhandled exception
    escaping the async generator — that's the difference between a typed
    SSE error event and the whole StreamingResponse dying mid-stream."""
    provider = OllamaProvider(base_url="http://fake-ollama:11434", model="llama3.2:3b", timeout_seconds=0.01)
    chunks = await _collect(provider, RuntimeError("something unexpected"), monkeypatch)

    assert len(chunks) == 1
    assert chunks[0].error is not None
