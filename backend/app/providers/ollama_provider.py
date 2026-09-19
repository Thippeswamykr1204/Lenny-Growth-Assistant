"""
Ollama provider — calls the local Ollama HTTP chat API. Streaming, per
architecture.md. No cloud fallback on failure (locked decision): a
connection failure here surfaces as a ProviderChunk error, it never
silently reroutes to Groq.
"""
import json
import logging

import httpx

from app.providers.base import BaseLLMProvider, ProviderChunk, ProviderError

logger = logging.getLogger("app.providers.ollama")


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def stream(self, messages, system_prompt, temperature=0.3):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "stream": True,
            "options": {"temperature": temperature},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.warning(
                            "ollama returned non-200",
                            extra={"status": response.status_code, "body": body[:500].decode(errors="replace")},
                        )
                        yield ProviderChunk(
                            error=ProviderError(
                                message="The local model is unavailable right now.",
                                detail=f"ollama HTTP {response.status_code}",
                            )
                        )
                        return

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield ProviderChunk(token=content)
                        if chunk.get("done"):
                            # Ollama's final streamed line carries token counts
                            # (prompt_eval_count / eval_count) when the server
                            # reports them — not guaranteed on every version,
                            # so pull with .get() and let usage stay partial
                            # rather than fail the whole chunk.
                            usage = {
                                "prompt_tokens": chunk.get("prompt_eval_count"),
                                "completion_tokens": chunk.get("eval_count"),
                            }
                            yield ProviderChunk(done=True, usage=usage)
                            return
            yield ProviderChunk(done=True)
        except httpx.TimeoutException as exc:
            logger.warning("ollama request timed out", extra={"error": str(exc)})
            yield ProviderChunk(
                error=ProviderError(message="The local model took too long to respond.", detail=str(exc))
            )
        except httpx.ConnectError as exc:
            logger.warning("ollama unreachable", extra={"error": str(exc)})
            yield ProviderChunk(
                error=ProviderError(
                    message="The local model isn't reachable. Is Ollama running?", detail=str(exc)
                )
            )
        except Exception as exc:  # noqa: BLE001 — must never raise out of a streaming generator
            logger.exception("unexpected ollama provider error")
            yield ProviderChunk(
                error=ProviderError(message="The local model failed unexpectedly.", detail=str(exc))
            )