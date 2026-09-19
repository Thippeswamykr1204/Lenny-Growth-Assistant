"""
BaseLLMProvider — the one shared interface both Ollama and Groq
implement, per architecture.md's provider abstraction. Deliberately thin
(one streaming method) since this project has exactly two providers and two
skills; a heavier agent framework would add ceremony without benefit here
(locked architecture decision, restated per instructions).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional


@dataclass
class ProviderError:
    """A structured, user-safe provider failure — never a raw SDK exception
    or stack trace, since that string may reach the client via chat.py's
    error SSE event."""
    message: str
    detail: Optional[str] = None  # server-side-only detail; caller decides whether to log it


@dataclass
class ProviderChunk:
    """One unit of a streamed response. Exactly one of `token` or `error`
    is set; `done=True` marks the final chunk of a successful stream.

    `usage` (Tier 5): best-effort token counts, only ever set alongside
    done=True, only when the provider SDK/API actually exposes them.
    Shape: {"prompt_tokens": int | None, "completion_tokens": int | None}.
    Left None rather than guessed — logging an absent count is more honest
    than logging a wrong one."""
    token: Optional[str] = None
    error: Optional[ProviderError] = None
    done: bool = False
    usage: Optional[dict] = None


class BaseLLMProvider(ABC):
    name: str  # e.g. "ollama" or "groq" — echoed back as provider_used

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        system_prompt: str,
        temperature: float = 0.3,
    ) -> AsyncIterator[ProviderChunk]:
        """
        messages: [{"role": "user"|"assistant", "content": str}, ...]
        Yields ProviderChunk tokens as they arrive, then a final
        ProviderChunk(done=True). On failure, yields a single
        ProviderChunk(error=...) and stops — never raises out of this
        generator, since callers (chat.py) must be able to turn any
        provider failure into a typed SSE error event.
        """
        raise NotImplementedError