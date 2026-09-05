"""
Anthropic provider — calls the cloud API via the official SDK. Streaming,
per architecture.md. anthropic_api_key is OPTIONAL per .env.example, so a
missing key must not raise — it's a structured ProviderError, checked
before any SDK call is attempted.
"""
import logging

from app.providers.base import BaseLLMProvider, ProviderChunk, ProviderError

logger = logging.getLogger("app.providers.anthropic")


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None, model: str, timeout_seconds: float = 30.0):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def stream(self, messages, system_prompt, temperature=0.3):
        if not self.api_key:
            yield ProviderChunk(
                error=ProviderError(
                    message="Cloud provider isn't configured.",
                    detail="ANTHROPIC_API_KEY is not set",
                )
            )
            return

        try:
            import anthropic  # imported lazily so an absent key never even needs the SDK import to succeed
        except ImportError as exc:
            logger.error("anthropic SDK not installed", extra={"error": str(exc)})
            yield ProviderChunk(
                error=ProviderError(message="Cloud provider is unavailable right now.", detail=str(exc))
            )
            return

        client = anthropic.AsyncAnthropic(api_key=self.api_key, timeout=self.timeout_seconds)
        try:
            async with client.messages.stream(
                model=self.model,
                max_tokens=2048,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    if text:
                        yield ProviderChunk(token=text)
                # Usage is only available on the final assembled message,
                # not per-token — fetched here, after the stream completes,
                # best-effort (older SDK versions or a mocked client in
                # tests may not expose it).
                usage = None
                try:
                    final_message = await stream.get_final_message()
                    if final_message is not None and getattr(final_message, "usage", None):
                        usage = {
                            "prompt_tokens": final_message.usage.input_tokens,
                            "completion_tokens": final_message.usage.output_tokens,
                        }
                except Exception:  # noqa: BLE001 — usage capture is best-effort, never fatal
                    logger.debug("could not read anthropic usage from final message")
            yield ProviderChunk(done=True, usage=usage)
        except anthropic.AuthenticationError as exc:
            logger.warning("anthropic auth failed", extra={"error": str(exc)})
            yield ProviderChunk(
                error=ProviderError(message="Cloud provider rejected the API key.", detail=str(exc))
            )
        except anthropic.RateLimitError as exc:
            logger.warning("anthropic rate limited", extra={"error": str(exc)})
            yield ProviderChunk(
                error=ProviderError(message="Cloud provider is rate-limited right now.", detail=str(exc))
            )
        except anthropic.APITimeoutError as exc:
            logger.warning("anthropic timed out", extra={"error": str(exc)})
            yield ProviderChunk(
                error=ProviderError(message="Cloud provider took too long to respond.", detail=str(exc))
            )
        except Exception as exc:  # noqa: BLE001 — must never raise out of a streaming generator
            logger.exception("unexpected anthropic provider error")
            yield ProviderChunk(
                error=ProviderError(message="Cloud provider failed unexpectedly.", detail=str(exc))
            )