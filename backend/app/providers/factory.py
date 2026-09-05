"""
Provider factory. Selection is pure app logic — env-var default
(settings.default_llm_provider) with an explicit per-request override
string, never the model choosing its own provider (locked decision).
"""
from app.core.config import Settings
from app.providers.base import BaseLLMProvider
from app.providers.cloud_provider import AnthropicProvider
from app.providers.ollama_provider import OllamaProvider


class UnknownProviderError(ValueError):
    pass


def get_provider(settings: Settings, override: str | None = None) -> BaseLLMProvider:
    provider_name = (override or settings.default_llm_provider).lower()

    if provider_name == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.resolved_ollama_timeout(),
        )
    if provider_name == "anthropic":
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            timeout_seconds=settings.resolved_anthropic_timeout(),
        )

    raise UnknownProviderError(f"unknown provider: {provider_name!r}")