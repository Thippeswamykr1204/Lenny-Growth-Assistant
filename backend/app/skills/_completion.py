"""
Shared helper: consume a BaseLLMProvider.stream() into a single string.

Ship30 and artifact-generation skills need a whole document to run
deterministic validators/sanitizers against, not token-by-token output to
a client — this reuses provider.stream() (the one existing call surface on
BaseLLMProvider, per architecture.md's provider abstraction) rather than
adding a second, non-streaming provider method. grounded_qa.py streams
directly to chat.py's SSE loop; this helper is for skills that need the
full text before deciding anything.
"""
from dataclasses import dataclass

from app.providers.base import BaseLLMProvider, ProviderError


@dataclass
class CompletionResult:
    text: str | None  # None iff error is set
    error: ProviderError | None


async def complete(
    provider: BaseLLMProvider,
    messages: list[dict],
    system_prompt: str,
    temperature: float = 0.4,
) -> CompletionResult:
    pieces: list[str] = []
    async for chunk in provider.stream(messages=messages, system_prompt=system_prompt, temperature=temperature):
        if chunk.error:
            return CompletionResult(text=None, error=chunk.error)
        if chunk.token:
            pieces.append(chunk.token)
        if chunk.done:
            break
    return CompletionResult(text="".join(pieces), error=None)