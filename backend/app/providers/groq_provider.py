"""
Groq provider — OpenAI-compatible chat completions endpoint, called via
httpx directly (same dependency-light pattern as OllamaProvider) rather
than pulling in the openai SDK for one extra provider. groq_api_key is
OPTIONAL per .env.example, so a missing key must not raise — it's a
structured ProviderError, checked before any HTTP call is attempted.
"""
import json
import logging

import httpx

from app.providers.base import BaseLLMProvider, ProviderChunk, ProviderError

logger = logging.getLogger("app.providers.groq")


class GroqProvider(BaseLLMProvider):
    name = "groq"

    def __init__(self, api_key: str | None, model: str, timeout_seconds: float = 30.0):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    async def stream(self, messages, system_prompt, temperature=0.3):
        if not self.api_key:
            yield ProviderChunk(
                error=ProviderError(
                    message="Cloud provider isn't configured.",
                    detail="GROQ_API_KEY is not set",
                )
            )
            return

        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "temperature": temperature,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST", self.base_url, json=payload, headers=headers
                ) as response:
                    if response.status_code == 401:
                        yield ProviderChunk(
                            error=ProviderError(message="Cloud provider rejected the API key.")
                        )
                        return
                    if response.status_code == 429:
                        yield ProviderChunk(
                            error=ProviderError(message="Cloud provider is rate-limited right now.")
                        )
                        return
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.warning("groq returned %s: %s", response.status_code, body[:500])
                        yield ProviderChunk(
                            error=ProviderError(
                                message="Cloud provider failed unexpectedly.",
                                detail=f"status={response.status_code}",
                            )
                        )
                        return

                    prompt_tokens = None
                    completion_tokens = None
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[len("data: "):].strip()
                        if data == "[DONE]":
                            break
                        chunk = json.loads(data)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            text = delta.get("content")
                            if text:
                                yield ProviderChunk(token=text)
                        usage = chunk.get("x_groq", {}).get("usage") or chunk.get("usage")
                        if usage:
                            prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                            completion_tokens = usage.get("completion_tokens", completion_tokens)

                    yield ProviderChunk(
                        done=True,
                        usage={"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
                        if prompt_tokens or completion_tokens
                        else None,
                    )
        except httpx.TimeoutException as exc:
            logger.warning("groq timed out", extra={"error": str(exc)})
            yield ProviderChunk(
                error=ProviderError(message="Cloud provider took too long to respond.", detail=str(exc))
            )
        except Exception as exc:  # noqa: BLE001 — must never raise out of a streaming generator
            logger.exception("unexpected groq provider error")
            yield ProviderChunk(
                error=ProviderError(message="Cloud provider failed unexpectedly.", detail=str(exc))
            )